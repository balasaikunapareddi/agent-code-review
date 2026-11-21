"""Deterministic static checks — the layer under the LLM.

These catch the mechanical defects that should never need a model:
bare excepts, mutable defaults, SQL string building, hardcoded
secrets, missing timeouts, eval/exec, untracked TODOs, debug prints.

Design rules:
- Checks run on ADDED lines only. A review comments on what the PR
  introduces, not on pre-existing debt it happens to touch.
- Every check is a pure function of the parsed diff: same input, same
  findings, no network, no model. That is what makes the eval numbers
  reproducible.
- Confidence is honest: pattern-perfect checks score 0.9+, heuristic
  ones (debug prints) score low and are suppressed by default policy.
"""

from __future__ import annotations

import re
from typing import Callable

from .diff_parser import FileDiff
from .models import Category, Finding, Severity

CheckFn = Callable[[FileDiff], list[Finding]]


def _finding(
    fd: FileDiff,
    line: int,
    severity: Severity,
    category: Category,
    confidence: float,
    message: str,
    suggestion: str,
) -> Finding:
    return Finding(
        file=fd.path,
        line=line,
        severity=severity,
        category=category,
        confidence=confidence,
        message=message,
        suggestion=suggestion,
        source="static",
    )


def _is_python(fd: FileDiff) -> bool:
    return fd.path.endswith(".py")


def _is_test_file(fd: FileDiff) -> bool:
    p = fd.path
    return "/tests/" in p or p.startswith("tests/") or "test_" in p.rsplit("/", 1)[-1]


# --- individual checks -------------------------------------------------

_BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:")


def check_bare_except(fd: FileDiff) -> list[Finding]:
    if not _is_python(fd):
        return []
    out = []
    for line in fd.added_lines():
        if _BARE_EXCEPT_RE.match(line.content):
            out.append(
                _finding(
                    fd, line.new_lineno, Severity.MAJOR, Category.BUG, 0.95,
                    "Bare `except:` swallows every exception, including "
                    "KeyboardInterrupt and programming errors.",
                    "Catch the specific exception(s) you expect, e.g. "
                    "`except ValueError:`, and log or re-raise the rest.",
                )
            )
    return out


_MUTABLE_DEFAULT_RE = re.compile(
    r"def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|list\(\)|dict\(\)|set\(\))"
)


def check_mutable_default(fd: FileDiff) -> list[Finding]:
    if not _is_python(fd):
        return []
    out = []
    for line in fd.added_lines():
        if _MUTABLE_DEFAULT_RE.search(line.content):
            out.append(
                _finding(
                    fd, line.new_lineno, Severity.MAJOR, Category.BUG, 0.95,
                    "Mutable default argument is shared across all calls; "
                    "mutations leak between invocations.",
                    "Default to None and create the collection inside the "
                    "function body.",
                )
            )
    return out


_SQL_KEYWORD_RE = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", re.IGNORECASE
)
_EXECUTE_RE = re.compile(r"\.execute\s*\(")


def _looks_like_string_building(content: str) -> bool:
    return (
        'f"' in content
        or "f'" in content
        or ".format(" in content
        or re.search(r'["\']\s*%', content) is not None
        or re.search(r'["\']\s*\+', content) is not None
        or re.search(r'\+\s*["\']', content) is not None
    )


def check_sql_string_format(fd: FileDiff) -> list[Finding]:
    if not _is_python(fd):
        return []
    out = []
    for line in fd.added_lines():
        c = line.content
        is_sql = bool(_SQL_KEYWORD_RE.search(c)) or bool(_EXECUTE_RE.search(c))
        if is_sql and _looks_like_string_building(c):
            out.append(
                _finding(
                    fd, line.new_lineno, Severity.BLOCKER, Category.SECURITY, 0.9,
                    "SQL built by string formatting/concatenation — classic "
                    "SQL injection vector if any interpolated value is "
                    "user-controlled.",
                    "Use parameterized queries (placeholders + parameter "
                    "tuple) so values are never spliced into the SQL text.",
                )
            )
    return out


_SECRET_ASSIGN_RE = re.compile(
    r"(api_key|apikey|secret|password|passwd|access_token|auth_token)"
    r"\s*=\s*[\"']([^\"']{8,})[\"']",
    re.IGNORECASE,
)
_SECRET_FORMAT_RES = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
]
_PLACEHOLDER_HINTS = ("example", "changeme", "xxx", "placeholder", "your-", "<", "test")


def check_hardcoded_secret(fd: FileDiff) -> list[Finding]:
    out = []
    for line in fd.added_lines():
        c = line.content
        hit = None
        m = _SECRET_ASSIGN_RE.search(c)
        if m and not any(h in m.group(2).lower() for h in _PLACEHOLDER_HINTS):
            hit = "credential assigned a string literal"
        else:
            for rx in _SECRET_FORMAT_RES:
                if rx.search(c):
                    hit = "string matching a known API-key format"
                    break
        if hit:
            out.append(
                _finding(
                    fd, line.new_lineno, Severity.BLOCKER, Category.SECURITY, 0.85,
                    f"Hardcoded secret in source ({hit}). Secrets in git "
                    "history are compromised secrets.",
                    "Load the credential from the environment or a secret "
                    "manager, and rotate this one — it is already in the diff.",
                )
            )
    return out


_HTTP_CALL_RE = re.compile(
    r"\b(requests|httpx)\.(get|post|put|patch|delete|head|request)\s*\("
)


def check_missing_timeout(fd: FileDiff) -> list[Finding]:
    if not _is_python(fd):
        return []
    out = []
    added = fd.added_lines()
    for i, line in enumerate(added):
        if not _HTTP_CALL_RE.search(line.content):
            continue
        # Gather the full call: HTTP calls are often split across
        # lines, and `timeout=` may sit a few lines below the opener.
        call_text = line.content
        depth = call_text.count("(") - call_text.count(")")
        j = i + 1
        while depth > 0 and j < len(added) and j - i <= 8:
            call_text += "\n" + added[j].content
            depth += added[j].content.count("(") - added[j].content.count(")")
            j += 1
        if "timeout" not in call_text:
            out.append(
                _finding(
                    fd, line.new_lineno, Severity.MAJOR, Category.BUG, 0.9,
                    "HTTP call without a timeout can hang the worker "
                    "indefinitely on a slow or dead peer.",
                    "Pass an explicit timeout, e.g. `timeout=10` (or a "
                    "(connect, read) tuple).",
                )
            )
    return out


_EVAL_EXEC_RE = re.compile(r"(?<![\w.])(eval|exec)\s*\(")


def check_eval_exec(fd: FileDiff) -> list[Finding]:
    if not _is_python(fd):
        return []
    out = []
    for line in fd.added_lines():
        c = line.content
        if "literal_eval" in c:
            continue
        if _EVAL_EXEC_RE.search(c):
            out.append(
                _finding(
                    fd, line.new_lineno, Severity.BLOCKER, Category.SECURITY, 0.9,
                    "`eval`/`exec` executes arbitrary code; if the input "
                    "is influenced by a user this is remote code execution.",
                    "Use `ast.literal_eval` for data, or an explicit "
                    "dispatch table for behavior.",
                )
            )
    return out


_TODO_RE = re.compile(r"\b(TODO|FIXME|XXX)\b")
_TICKET_RE = re.compile(r"\(#\d+\)|[A-Z][A-Z0-9]+-\d+")


def check_todo_without_ticket(fd: FileDiff) -> list[Finding]:
    out = []
    for line in fd.added_lines():
        c = line.content
        if _TODO_RE.search(c) and not _TICKET_RE.search(c):
            out.append(
                _finding(
                    fd, line.new_lineno, Severity.NIT, Category.STYLE, 0.8,
                    "TODO/FIXME without a ticket reference tends to become "
                    "permanent.",
                    "Attach a ticket, e.g. `TODO(#123): ...`, or do the "
                    "work in this change.",
                )
            )
    return out


_PRINT_RE = re.compile(r"^\s*print\s*\(")


def check_debug_print(fd: FileDiff) -> list[Finding]:
    if not _is_python(fd) or _is_test_file(fd):
        return []
    out = []
    for line in fd.added_lines():
        if _PRINT_RE.match(line.content):
            out.append(
                _finding(
                    fd, line.new_lineno, Severity.MINOR, Category.STYLE, 0.55,
                    "Bare `print` in non-test code — usually leftover "
                    "debugging (low confidence: CLIs legitimately print).",
                    "Use the logging module, or remove if it was for "
                    "debugging.",
                )
            )
    return out


CHECKS: list[CheckFn] = [
    check_bare_except,
    check_mutable_default,
    check_sql_string_format,
    check_hardcoded_secret,
    check_missing_timeout,
    check_eval_exec,
    check_todo_without_ticket,
    check_debug_print,
]


def run_static_checks(files: list[FileDiff]) -> list[Finding]:
    """Run every deterministic check over every changed file."""
    findings: list[Finding] = []
    for fd in files:
        if fd.is_binary or fd.is_deleted_file:
            continue
        for check in CHECKS:
            findings.extend(check(fd))
    return findings
