import json

from agent_code_review.agent import review_diff
from agent_code_review.report import render_json, render_markdown

from conftest import load_sample


def test_markdown_buggy_review():
    result = review_diff(load_sample("buggy_pr"))
    md = render_markdown(result)
    assert "## Code Review — BLOCK" in md
    assert "### Blocking findings" in md
    # inline-comment format: file:line — [severity] message
    assert "app/orders.py:6 — [blocker]" in md
    assert "app/orders.py:21 — [blocker]" in md
    assert "Suggestion:" in md
    # the debug print is suppressed, and the report says so
    assert "Suppressed below confidence threshold: 1" in md


def test_markdown_clean_review():
    result = review_diff(load_sample("clean_pr"))
    md = render_markdown(result)
    assert "## Code Review — APPROVE" in md
    assert "### Blocking findings" not in md
    assert "No findings" in md


def test_json_round_trip():
    result = review_diff(load_sample("security_pr"))
    payload = json.loads(render_json(result))
    assert payload["verdict"] == "block"
    assert payload["counts"]["blocker"] == 3
    assert payload["report"]["findings"][0]["severity"] == "blocker"
    assert payload["stats"]["files_changed"] == 1
