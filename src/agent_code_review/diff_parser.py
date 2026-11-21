"""Unified-diff parser.

Everything downstream (static checks, file context, eval matching)
works off this structure, so line numbers are computed exactly once:
each added line knows its line number in the new file, which is what
review comments anchor to.

Handles the shapes real PR diffs take: multiple files, new/deleted
files (``/dev/null``), renames, binary files, and plain ``diff -u``
output without ``diff --git`` headers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class DiffLine:
    kind: str  # "add" | "del" | "context"
    content: str
    new_lineno: int | None  # None for deletions
    old_lineno: int | None  # None for additions


@dataclass
class Hunk:
    old_start: int
    new_start: int
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    old_path: str | None
    new_path: str | None
    is_binary: bool = False
    is_rename: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        """The path review comments anchor to (new path, else old)."""
        return self.new_path or self.old_path or "<unknown>"

    @property
    def is_new_file(self) -> bool:
        return self.old_path is None

    @property
    def is_deleted_file(self) -> bool:
        return self.new_path is None

    def added_lines(self) -> list[DiffLine]:
        return [
            line
            for hunk in self.hunks
            for line in hunk.lines
            if line.kind == "add"
        ]

    def removed_lines(self) -> list[DiffLine]:
        return [
            line
            for hunk in self.hunks
            for line in hunk.lines
            if line.kind == "del"
        ]

    def line_at(self, new_lineno: int) -> DiffLine | None:
        for hunk in self.hunks:
            for line in hunk.lines:
                if line.new_lineno == new_lineno:
                    return line
        return None


def _clean_path(raw: str) -> str | None:
    path = raw.strip()
    if path == "/dev/null":
        return None
    # Strip the a/ b/ prefixes git adds, plus any trailing timestamp
    # that plain `diff -u` appends after a tab.
    path = path.split("\t")[0]
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def parse_diff(diff_text: str) -> list[FileDiff]:
    """Parse unified diff text into per-file structures."""
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    new_lineno = 0
    old_lineno = 0

    def start_file() -> FileDiff:
        fd = FileDiff(old_path=None, new_path=None)
        files.append(fd)
        return fd

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            current = start_file()
            hunk = None
            # "diff --git a/old b/new" — paths may contain spaces, so
            # only use this as a fallback; ---/+++ lines win below.
            parts = raw[len("diff --git ") :].split(" b/", 1)
            if len(parts) == 2:
                current.old_path = _clean_path(parts[0])
                current.new_path = _clean_path("b/" + parts[1])
            continue

        if raw.startswith("rename from "):
            if current is None:
                current = start_file()
            current.is_rename = True
            current.old_path = raw[len("rename from ") :].strip()
            continue
        if raw.startswith("rename to "):
            if current is None:
                current = start_file()
            current.is_rename = True
            current.new_path = raw[len("rename to ") :].strip()
            continue

        if raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            if current is None:
                current = start_file()
            current.is_binary = True
            continue

        if raw.startswith("--- "):
            # A --- line after hunks means a new file section in plain
            # diff -u output (no `diff --git` header).
            if current is None or current.hunks:
                current = start_file()
            current.old_path = _clean_path(raw[4:])
            hunk = None
            continue
        if raw.startswith("+++ "):
            if current is None:
                current = start_file()
            current.new_path = _clean_path(raw[4:])
            continue

        m = _HUNK_RE.match(raw)
        if m:
            if current is None:
                current = start_file()
            old_lineno = int(m.group(1))
            new_lineno = int(m.group(3))
            hunk = Hunk(old_start=old_lineno, new_start=new_lineno)
            current.hunks.append(hunk)
            continue

        if hunk is None or current is None:
            continue  # index lines, mode lines, etc.

        if raw.startswith("\\"):
            continue  # "\ No newline at end of file"
        if raw.startswith("+"):
            hunk.lines.append(
                DiffLine("add", raw[1:], new_lineno, None)
            )
            new_lineno += 1
        elif raw.startswith("-"):
            hunk.lines.append(
                DiffLine("del", raw[1:], None, old_lineno)
            )
            old_lineno += 1
        elif raw.startswith(" ") or raw == "":
            content = raw[1:] if raw.startswith(" ") else raw
            hunk.lines.append(
                DiffLine("context", content, new_lineno, old_lineno)
            )
            new_lineno += 1
            old_lineno += 1
        # Anything else inside a hunk is malformed; ignore it rather
        # than guessing.

    return files


def diff_stats(files: list[FileDiff]) -> dict:
    return {
        "files_changed": len(files),
        "additions": sum(len(f.added_lines()) for f in files),
        "deletions": sum(len(f.removed_lines()) for f in files),
        "binary_files": sum(1 for f in files if f.is_binary),
    }
