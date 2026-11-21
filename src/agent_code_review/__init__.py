"""agent-code-review: a production-pattern AI code reviewer.

Deterministic static checks under an LLM layer, structured findings
with severity + confidence, false-positive suppression, and a
seeded-bug eval benchmark. Mock mode is the default (no key, no
network); set GEMINI_API_KEY for live reviews.
"""

from .agent import ReviewResult, build_agent, review_diff, review_repo
from .models import Category, Finding, ReviewReport, Severity

__all__ = [
    "Category",
    "Finding",
    "ReviewReport",
    "ReviewResult",
    "Severity",
    "build_agent",
    "review_diff",
    "review_repo",
]

__version__ = "0.1.0"
