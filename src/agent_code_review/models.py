"""Structured review data model.

Findings are data, not prose: every finding carries a file, a line, a
severity, a category, and a confidence. That is what lets downstream
code (severity policy, suppression, dedup, evals) treat a review like
any other pipeline output instead of parsing paragraphs.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    NIT = "nit"


class Category(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERF = "perf"
    STYLE = "style"
    DESIGN = "design"


class Finding(BaseModel):
    """One review comment, anchored to a line in the new file."""

    file: str = Field(description="Path of the changed file (new-file path).")
    line: int = Field(ge=1, description="Line number in the new file.")
    severity: Severity
    category: Category
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="How sure the reviewer is this is a real issue (0-1).",
    )
    message: str = Field(description="What is wrong, in one or two sentences.")
    suggestion: str = Field(
        default="", description="Concrete fix the author can apply."
    )
    source: str = Field(
        default="agent",
        description="Where the finding came from: 'static' or 'agent'.",
    )


class ReviewReport(BaseModel):
    """The agent's structured output: a summary plus typed findings."""

    summary: str = Field(
        description="Two or three sentences: what the change does and the "
        "overall assessment."
    )
    findings: list[Finding] = Field(default_factory=list)
    verdict: Literal["approve", "block"] = Field(
        default="approve",
        description="Advisory verdict from the reviewer. The severity "
        "policy recomputes the authoritative verdict in code.",
    )
