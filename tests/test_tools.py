import json

from agent_code_review.diff_parser import parse_diff
from agent_code_review.tools import (
    ReviewDeps,
    get_file_context_impl,
    list_changed_files_impl,
    run_static_checks_impl,
)

from conftest import load_sample


def _deps(name):
    text = load_sample(name)
    return ReviewDeps(diff_text=text, files=parse_diff(text))


def test_list_changed_files():
    payload = json.loads(list_changed_files_impl(_deps("buggy_pr")))
    assert payload["stats"]["files_changed"] == 1
    assert payload["files"][0]["path"] == "app/orders.py"
    assert payload["files"][0]["additions"] == 32


def test_run_static_checks_tool_returns_json_findings():
    findings = json.loads(run_static_checks_impl(_deps("security_pr")))
    assert len(findings) == 3
    assert all(f["source"] == "static" for f in findings)
    assert {f["line"] for f in findings} == {3, 8, 13}


def test_get_file_context_around_line():
    ctx = get_file_context_impl(_deps("buggy_pr"), "app/orders.py", 21, radius=2)
    assert "SELECT * FROM orders" in ctx
    assert "21" in ctx


def test_get_file_context_unknown_file():
    ctx = get_file_context_impl(_deps("buggy_pr"), "nope.py", 1)
    assert "No changed file" in ctx


def test_get_file_context_outside_hunks():
    ctx = get_file_context_impl(_deps("buggy_pr"), "app/orders.py", 999)
    assert "not inside any diff hunk" in ctx
