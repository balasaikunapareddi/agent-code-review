"""The reviewer agent and the review pipeline around it.

Pipeline shape (the production pattern this repo demonstrates):

    diff text
      -> parse (code)
      -> static checks (code)          ----+
      -> agent review (LLM or mock)    ----+-> merge -> dedup ->
         with typed tools                   confidence suppression ->
                                            severity policy -> verdict

The agent's findings never bypass policy: whatever the model says,
code decides what gets posted and whether the merge blocks. Static
findings are merged in directly as well, so a live model that ignores
its tools cannot lose the deterministic layer's catches.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext

from .diff_parser import diff_stats, parse_diff
from .mock_model import build_mock_model
from .models import Finding, ReviewReport
from .policy import DEFAULT_CONFIDENCE_THRESHOLD, PolicyResult, apply_policy
from .prompts import REVIEW_REQUEST_PREFIX, REVIEW_REQUEST_SUFFIX, SYSTEM_PROMPT
from .static_checks import run_static_checks
from .tools import (
    ReviewDeps,
    get_file_context_impl,
    list_changed_files_impl,
    run_static_checks_impl,
)

DEFAULT_LIVE_MODEL = "gemini-3.5-flash-lite"


@dataclass
class ReviewResult:
    report: ReviewReport
    policy: PolicyResult
    stats: dict = field(default_factory=dict)

    @property
    def findings(self) -> list[Finding]:
        return self.policy.kept

    @property
    def suppressed(self) -> list[Finding]:
        return self.policy.suppressed

    @property
    def verdict(self) -> str:
        return self.policy.verdict


def _live_model():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Live mode needs GEMINI_API_KEY in the environment. "
            "Mock mode (the default) needs no key and no network."
        )
    try:
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider
    except ImportError as exc:  # pragma: no cover - live mode only
        raise RuntimeError(
            "Live mode needs the Google provider: "
            "pip install 'agent-code-review[live]'"
        ) from exc
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_LIVE_MODEL)
    return GoogleModel(model_name, provider=GoogleProvider(api_key=api_key))


def build_agent(live: bool = False) -> Agent:
    """Build the reviewer agent. Mock by default; live needs GEMINI_API_KEY."""
    model = _live_model() if live else build_mock_model()
    agent = Agent(
        model,
        output_type=ReviewReport,
        deps_type=ReviewDeps,
        system_prompt=SYSTEM_PROMPT,
        name="code_reviewer",
    )

    @agent.tool
    def list_changed_files(ctx: RunContext[ReviewDeps]) -> str:
        """List the files in this diff with addition/deletion counts."""
        return list_changed_files_impl(ctx.deps)

    @agent.tool
    def run_static_checks(ctx: RunContext[ReviewDeps]) -> str:
        """Run the deterministic static checks; returns JSON findings."""
        return run_static_checks_impl(ctx.deps)

    @agent.tool
    def get_file_context(
        ctx: RunContext[ReviewDeps], file: str, line: int, radius: int = 5
    ) -> str:
        """Show diff lines around a new-file line number in a changed file."""
        return get_file_context_impl(ctx.deps, file, line, radius)

    return agent


def review_diff(
    diff_text: str,
    live: bool = False,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    agent: Agent | None = None,
) -> ReviewResult:
    """Review a unified diff end to end and return the policy-filtered result."""
    files = parse_diff(diff_text)
    deps = ReviewDeps(diff_text=diff_text, files=files)
    static_findings = run_static_checks(files)

    agent = agent if agent is not None else build_agent(live=live)
    prompt = REVIEW_REQUEST_PREFIX + diff_text + REVIEW_REQUEST_SUFFIX
    run = agent.run_sync(prompt, deps=deps)
    agent_report: ReviewReport = run.output

    merged = static_findings + list(agent_report.findings)
    policy = apply_policy(merged, confidence_threshold=confidence_threshold)

    final_report = ReviewReport(
        summary=agent_report.summary,
        findings=policy.kept,
        verdict=policy.verdict,  # policy owns the verdict, not the model
    )
    return ReviewResult(
        report=final_report, policy=policy, stats=diff_stats(files)
    )


def get_git_diff(repo_path: str, ref_range: str = "HEAD~1..HEAD") -> str:
    """Unified diff for a ref range in a local git repo."""
    proc = subprocess.run(
        ["git", "-C", repo_path, "diff", ref_range],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git diff failed in {repo_path!r}: {proc.stderr.strip()}"
        )
    return proc.stdout


def review_repo(
    repo_path: str,
    ref_range: str = "HEAD~1..HEAD",
    live: bool = False,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> ReviewResult:
    """Review the diff of a ref range in a local git repository."""
    return review_diff(
        get_git_diff(repo_path, ref_range),
        live=live,
        confidence_threshold=confidence_threshold,
    )


class CodeReviewerAgent:
    """The code-review agent: a Pydantic AI agent inside the review pipeline.

    Construct with a model mode (deterministic mock by default; live
    Gemini when ``live=True``) and a confidence threshold, then call
    :meth:`review` with diff text or :meth:`review_repo` with a git ref
    range. The underlying agent is built by :func:`build_agent` — system
    prompt in ``prompts.py``, typed tools over the parsed diff — and
    everything after the model runs (merge, dedup, confidence
    suppression, severity policy, verdict) is deterministic code in
    :func:`review_diff`.
    """

    def __init__(
        self,
        live: bool = False,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ):
        self.live = live
        self.confidence_threshold = confidence_threshold
        self.agent = build_agent(live=live)

    def review(self, diff_text: str) -> ReviewResult:
        """Review a unified diff and return the policy-filtered result."""
        return review_diff(
            diff_text,
            live=self.live,
            confidence_threshold=self.confidence_threshold,
            agent=self.agent,
        )

    def review_repo(
        self, repo_path: str, ref_range: str = "HEAD~1..HEAD"
    ) -> ReviewResult:
        """Review the diff of a ref range in a local git repository."""
        return review_diff(
            get_git_diff(repo_path, ref_range),
            live=self.live,
            confidence_threshold=self.confidence_threshold,
            agent=self.agent,
        )
