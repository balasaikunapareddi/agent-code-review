"""Severity policy, confidence suppression, and deduplication.

This is the layer that keeps an AI reviewer usable in production:

- The severity policy decides what blocks a merge (blocker + major).
  The model proposes severities; code owns the verdict.
- Confidence thresholding suppresses low-confidence findings instead
  of posting them. Suppressed findings are counted and reported, not
  silently dropped — you can audit what the reviewer chose not to say.
- Deduplication collapses the same issue reported by both the static
  layer and the agent (or twice by the agent) into one comment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Finding, Severity

SEVERITY_RANK: dict[Severity, int] = {
    Severity.BLOCKER: 0,
    Severity.MAJOR: 1,
    Severity.MINOR: 2,
    Severity.NIT: 3,
}

BLOCKING_SEVERITIES = {Severity.BLOCKER, Severity.MAJOR}

DEFAULT_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class PolicyResult:
    kept: list[Finding] = field(default_factory=list)
    suppressed: list[Finding] = field(default_factory=list)
    verdict: str = "approve"  # "approve" | "block"

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.kept if f.severity in BLOCKING_SEVERITIES]

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in Severity}
        for f in self.kept:
            out[f.severity.value] += 1
        return out


def _dedup_key(f: Finding) -> tuple:
    return (f.file, f.line, f.category)


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """Collapse duplicates on (file, line, category).

    When the static layer and the agent both flag the same line for the
    same class of problem, keep the higher-confidence version (ties go
    to the higher severity, then to the static finding — deterministic
    beats generated when both are equally sure).
    """
    best: dict[tuple, Finding] = {}
    for f in findings:
        key = _dedup_key(f)
        existing = best.get(key)
        if existing is None:
            best[key] = f
            continue
        challenger = (f.confidence, -SEVERITY_RANK[f.severity], f.source == "static")
        incumbent = (
            existing.confidence,
            -SEVERITY_RANK[existing.severity],
            existing.source == "static",
        )
        if challenger > incumbent:
            best[key] = f
    return list(best.values())


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (SEVERITY_RANK[f.severity], f.file, f.line),
    )


def apply_policy(
    findings: list[Finding],
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> PolicyResult:
    """Dedup, suppress low-confidence noise, sort, decide the verdict."""
    deduped = deduplicate(findings)
    kept = [f for f in deduped if f.confidence >= confidence_threshold]
    suppressed = [f for f in deduped if f.confidence < confidence_threshold]
    kept = sort_findings(kept)
    suppressed = sort_findings(suppressed)
    verdict = (
        "block"
        if any(f.severity in BLOCKING_SEVERITIES for f in kept)
        else "approve"
    )
    return PolicyResult(kept=kept, suppressed=suppressed, verdict=verdict)
