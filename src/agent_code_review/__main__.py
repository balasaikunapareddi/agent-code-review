"""CLI: review a diff file or a git repo ref range.

    python -m agent_code_review path/to/change.diff
    python -m agent_code_review --repo . --range HEAD~1..HEAD
    python -m agent_code_review change.diff --json --live

Exit code is 1 when the severity policy blocks the change, so the
CLI can gate CI the same way it would gate a merge button.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agent import review_diff, review_repo
from .report import render_json, render_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-code-review")
    parser.add_argument("diff", nargs="?", help="path to a unified diff file")
    parser.add_argument("--repo", help="path to a git repository to review")
    parser.add_argument(
        "--range", default="HEAD~1..HEAD", help="git ref range (with --repo)"
    )
    parser.add_argument("--live", action="store_true", help="use the live Gemini model")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="confidence threshold below which findings are suppressed",
    )
    args = parser.parse_args(argv)

    if args.repo:
        result = review_repo(
            args.repo,
            ref_range=args.range,
            live=args.live,
            confidence_threshold=args.threshold,
        )
    elif args.diff:
        result = review_diff(
            Path(args.diff).read_text(),
            live=args.live,
            confidence_threshold=args.threshold,
        )
    else:
        parser.error("give a diff file or --repo")

    print(render_json(result) if args.json else render_markdown(result))
    return 1 if result.verdict == "block" else 0


if __name__ == "__main__":
    sys.exit(main())
