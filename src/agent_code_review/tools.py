"""Typed tools the reviewer agent can call.

The tools are thin wrappers over the deterministic layers (diff
parser, static checks). They take the parsed diff from the run
dependencies, so the model never has to paste the diff back and forth
— it asks questions about it instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .diff_parser import FileDiff, diff_stats
from .static_checks import run_static_checks


@dataclass
class ReviewDeps:
    """Dependencies carried through one review run."""

    diff_text: str
    files: list[FileDiff]

    def file_by_path(self, path: str) -> FileDiff | None:
        for fd in self.files:
            if fd.path == path:
                return fd
        return None


def list_changed_files_impl(deps: ReviewDeps) -> str:
    """JSON summary of the change: files, line counts, binary/rename flags."""
    payload = {
        "stats": diff_stats(deps.files),
        "files": [
            {
                "path": fd.path,
                "old_path": fd.old_path,
                "is_new_file": fd.is_new_file,
                "is_deleted_file": fd.is_deleted_file,
                "is_binary": fd.is_binary,
                "is_rename": fd.is_rename,
                "additions": len(fd.added_lines()),
                "deletions": len(fd.removed_lines()),
            }
            for fd in deps.files
        ],
    }
    return json.dumps(payload, indent=2)


def run_static_checks_impl(deps: ReviewDeps) -> str:
    """JSON list of deterministic findings (the layer under the LLM)."""
    findings = run_static_checks(deps.files)
    return json.dumps([f.model_dump(mode="json") for f in findings], indent=2)


def get_file_context_impl(
    deps: ReviewDeps, file: str, line: int, radius: int = 5
) -> str:
    """Lines around `line` in the new file, as they appear in the diff."""
    fd = deps.file_by_path(file)
    if fd is None:
        return f"No changed file named {file!r} in this diff."
    rows: list[str] = []
    for hunk in fd.hunks:
        for dl in hunk.lines:
            if dl.new_lineno is None:
                continue
            if abs(dl.new_lineno - line) <= radius:
                marker = "+" if dl.kind == "add" else " "
                rows.append(f"{dl.new_lineno:>5} {marker} {dl.content}")
    if not rows:
        return f"Line {line} of {file} is not inside any diff hunk."
    return "\n".join(rows)
