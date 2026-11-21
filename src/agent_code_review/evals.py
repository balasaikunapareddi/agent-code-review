"""Seeded-bug eval benchmark.

"Does the reviewer work?" is a measurement question, not a vibe. The
sample PRs ship with a manifest of known defects (file, line,
category, expected severity). The eval runs the reviewer over each
sample and reports:

- recall — fraction of seeded defects the reviewer found;
- precision — fraction of posted findings that match a seeded defect
  (findings on the clean PR are false positives by definition);
- clean-PR blockers — the headline precision proxy: a reviewer that
  blocks clean code gets muted, whatever its recall;
- severity accuracy — of the defects found, how often the severity
  matched the manifest's expectation.

A finding matches a seeded defect when file and category agree and
the line is within ±2 (reviewers reasonably anchor to the statement,
not always the exact token).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .agent import review_diff
from .models import Category, Finding, Severity

LINE_TOLERANCE = 2

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"


@dataclass
class SeededBug:
    file: str
    line: int
    category: Category
    severity: Severity
    description: str


@dataclass
class SampleEval:
    sample: str
    seeded: int
    found: int
    false_positives: int
    blockers: int
    severity_matches: int
    missed: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return 1.0 if self.seeded == 0 else self.found / self.seeded

    @property
    def precision(self) -> float:
        total = self.found + self.false_positives
        return 1.0 if total == 0 else self.found / total

    @property
    def severity_accuracy(self) -> float:
        return 1.0 if self.found == 0 else self.severity_matches / self.found


def load_manifest(samples_dir: Path = SAMPLES_DIR) -> dict[str, list[SeededBug]]:
    raw = json.loads((samples_dir / "manifest.json").read_text())
    manifest: dict[str, list[SeededBug]] = {}
    for sample, bugs in raw.items():
        manifest[sample] = [
            SeededBug(
                file=b["file"],
                line=int(b["line"]),
                category=Category(b["category"]),
                severity=Severity(b["severity"]),
                description=b["description"],
            )
            for b in bugs
        ]
    return manifest


def _matches(finding: Finding, bug: SeededBug) -> bool:
    return (
        finding.file == bug.file
        and finding.category == bug.category
        and abs(finding.line - bug.line) <= LINE_TOLERANCE
    )


def evaluate_sample(
    sample: str,
    diff_text: str,
    seeded: list[SeededBug],
    live: bool = False,
) -> SampleEval:
    result = review_diff(diff_text, live=live)
    findings = result.findings

    matched_bugs: set[int] = set()
    matched_findings: set[int] = set()
    severity_matches = 0
    for bi, bug in enumerate(seeded):
        for fi, finding in enumerate(findings):
            if fi in matched_findings:
                continue
            if _matches(finding, bug):
                matched_bugs.add(bi)
                matched_findings.add(fi)
                if finding.severity == bug.severity:
                    severity_matches += 1
                break

    missed = [
        seeded[bi].description
        for bi in range(len(seeded))
        if bi not in matched_bugs
    ]
    return SampleEval(
        sample=sample,
        seeded=len(seeded),
        found=len(matched_bugs),
        false_positives=len(findings) - len(matched_findings),
        blockers=sum(1 for f in findings if f.severity == Severity.BLOCKER),
        severity_matches=severity_matches,
        missed=missed,
    )


def run_evals(
    samples_dir: Path = SAMPLES_DIR, live: bool = False
) -> list[SampleEval]:
    manifest = load_manifest(samples_dir)
    evals: list[SampleEval] = []
    for sample, seeded in sorted(manifest.items()):
        diff_text = (samples_dir / f"{sample}.diff").read_text()
        evals.append(evaluate_sample(sample, diff_text, seeded, live=live))
    return evals


def render_eval_table(evals: list[SampleEval]) -> str:
    lines = [
        "| Sample | Seeded | Found | Recall | Precision | Severity acc. | Blockers |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in evals:
        lines.append(
            f"| {e.sample} | {e.seeded} | {e.found} | {e.recall:.3f} | "
            f"{e.precision:.3f} | {e.severity_accuracy:.3f} | {e.blockers} |"
        )
    total_seeded = sum(e.seeded for e in evals)
    total_found = sum(e.found for e in evals)
    total_fp = sum(e.false_positives for e in evals)
    overall_recall = total_found / total_seeded if total_seeded else 1.0
    overall_precision = (
        total_found / (total_found + total_fp) if (total_found + total_fp) else 1.0
    )
    lines.append(
        f"| **overall** | {total_seeded} | {total_found} | "
        f"{overall_recall:.3f} | {overall_precision:.3f} | — | — |"
    )
    return "\n".join(lines)


def main() -> None:
    evals = run_evals()
    print(render_eval_table(evals))
    for e in evals:
        for miss in e.missed:
            print(f"missed in {e.sample}: {miss}")


if __name__ == "__main__":
    main()
