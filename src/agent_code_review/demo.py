"""One-command demo: review the three sample PRs, print the eval table.

    python -m agent_code_review.demo

Samples:
- clean_pr     — a tidy change; the reviewer should approve it quietly.
- buggy_pr     — seven seeded defects (one is a logic bug only the
                 live LLM layer can catch, so mock recall is 6/7).
- security_pr  — hardcoded secret, eval() on input, SQL concatenation.

Runs fully offline in mock mode. Set GEMINI_API_KEY and pass --live
for real-model reviews.
"""

from __future__ import annotations

import sys

from .agent import review_diff
from .evals import SAMPLES_DIR, render_eval_table, run_evals
from .report import render_markdown

SAMPLES = ["clean_pr", "buggy_pr", "security_pr"]


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    live = "--live" in argv
    mode = "live (Gemini)" if live else "mock (offline, deterministic)"
    print(f"=== agent-code-review demo — {mode} ===\n")

    for sample in SAMPLES:
        diff_text = (SAMPLES_DIR / f"{sample}.diff").read_text()
        result = review_diff(diff_text, live=live)
        print(f"----- {sample} -----")
        print(render_markdown(result))

    print("----- seeded-bug eval -----")
    evals = run_evals(live=live)
    print(render_eval_table(evals))
    for e in evals:
        for miss in e.missed:
            print(f"missed in {e.sample}: {miss}")


if __name__ == "__main__":
    main()
