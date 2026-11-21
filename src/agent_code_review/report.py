"""Render a ReviewResult as a markdown review or JSON.

The markdown is shaped like a real PR review: verdict up top,
blocking findings first, then every finding in inline-comment format
(`file:line — [severity] message`) so it can be pasted into a PR or
mapped onto a forge's review-comment API. Suppressed (low-confidence)
findings are counted, not hidden.
"""

from __future__ import annotations

import json

from .agent import ReviewResult
from .models import Finding


def _inline(f: Finding) -> str:
    return f"{f.file}:{f.line} — [{f.severity.value}] {f.message}"


def render_markdown(result: ReviewResult) -> str:
    counts = result.policy.counts()
    verdict_word = "BLOCK" if result.verdict == "block" else "APPROVE"
    lines: list[str] = []
    lines.append(f"## Code Review — {verdict_word}")
    lines.append("")
    lines.append(result.report.summary)
    lines.append("")
    lines.append(
        f"Files changed: {result.stats.get('files_changed', 0)} "
        f"(+{result.stats.get('additions', 0)}/-{result.stats.get('deletions', 0)}) · "
        f"Findings: {counts['blocker']} blocker, {counts['major']} major, "
        f"{counts['minor']} minor, {counts['nit']} nit · "
        f"Suppressed below confidence threshold: {len(result.suppressed)}"
    )
    lines.append("")

    blocking = result.policy.blocking
    if blocking:
        lines.append("### Blocking findings")
        lines.append("")
        for f in blocking:
            lines.append(f"- {_inline(f)}")
            if f.suggestion:
                lines.append(f"  - Suggestion: {f.suggestion}")
        lines.append("")

    if result.findings:
        lines.append("### All findings (inline comments)")
        lines.append("")
        for f in result.findings:
            lines.append(f"- {_inline(f)}")
            if f.suggestion:
                lines.append(f"  - Suggestion: {f.suggestion}")
        lines.append("")
    else:
        lines.append("No findings at or above the confidence threshold.")
        lines.append("")

    if result.suppressed:
        lines.append(
            f"_{len(result.suppressed)} low-confidence finding(s) were "
            "suppressed by policy and not posted._"
        )
        lines.append("")

    return "\n".join(lines)


def render_json(result: ReviewResult) -> str:
    payload = {
        "verdict": result.verdict,
        "stats": result.stats,
        "counts": result.policy.counts(),
        "report": result.report.model_dump(mode="json"),
        "suppressed": [f.model_dump(mode="json") for f in result.suppressed],
    }
    return json.dumps(payload, indent=2)
