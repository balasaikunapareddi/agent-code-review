"""Deterministic mock model for offline runs.

Stands in for the LLM so the full agent loop — system prompt, tool
calls, structured output — runs with no API key and no network. The
mock behaves like a disciplined reviewer: it calls the static-checks
tool first, then reports exactly what the deterministic layer found.
It does not invent logic-level findings; that is the honest boundary
of mock mode (see the real-vs-mocked table in the README). The seeded
off-by-one in the sample PRs is missed in mock mode for exactly this
reason, and the eval numbers show it.
"""

from __future__ import annotations

import json

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def _static_findings_from(messages) -> list[dict] | None:
    """Return parsed findings if the static-checks tool already ran."""
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and part.tool_name == "run_static_checks":
                try:
                    return json.loads(str(part.content))
                except (json.JSONDecodeError, TypeError):
                    return []
    return None


def mock_model_function(messages, info: AgentInfo) -> ModelResponse:
    findings = _static_findings_from(messages)
    if findings is None:
        # First turn: ask the deterministic layer what it found.
        return ModelResponse(
            parts=[ToolCallPart(tool_name="run_static_checks", args={})]
        )

    # Second turn: emit the structured report.
    blockers = sum(1 for f in findings if f.get("severity") == "blocker")
    majors = sum(1 for f in findings if f.get("severity") == "major")
    if findings:
        summary = (
            f"Deterministic review found {len(findings)} issue(s) "
            f"({blockers} blocker, {majors} major). Logic-level review "
            "requires live mode; mock mode reports static findings only."
        )
    else:
        summary = (
            "No issues found by the deterministic checks. Logic-level "
            "review requires live mode; mock mode reports static "
            "findings only."
        )
    verdict = "block" if (blockers or majors) else "approve"
    output_tool = info.output_tools[0].name
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool_name=output_tool,
                args={
                    "summary": summary,
                    "findings": findings,
                    "verdict": verdict,
                },
            )
        ]
    )


def build_mock_model() -> FunctionModel:
    return FunctionModel(mock_model_function, model_name="mock-reviewer")
