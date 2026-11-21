import shutil
import subprocess

import pytest

from agent_code_review.agent import review_diff, review_repo
from agent_code_review.models import Category, Severity

from conftest import load_sample


def test_mock_review_buggy_pr_blocks_with_expected_findings():
    result = review_diff(load_sample("buggy_pr"))
    assert result.verdict == "block"
    by_line = {f.line: f for f in result.findings}
    assert by_line[6].category == Category.SECURITY
    assert by_line[6].severity == Severity.BLOCKER
    assert by_line[10].category == Category.BUG
    assert by_line[14].category == Category.BUG
    assert by_line[21].category == Category.SECURITY
    assert by_line[28].category == Category.BUG
    assert by_line[36].severity == Severity.NIT
    # the debug print is below the confidence threshold
    assert 38 not in by_line
    assert len(result.suppressed) == 1
    # the seeded off-by-one is a logic bug: mock mode honestly misses it
    assert 33 not in by_line


def test_mock_review_clean_pr_approves_quietly():
    result = review_diff(load_sample("clean_pr"))
    assert result.verdict == "approve"
    assert result.findings == []
    assert result.suppressed == []


def test_mock_review_security_pr_three_blockers():
    result = review_diff(load_sample("security_pr"))
    assert result.verdict == "block"
    assert len(result.findings) == 3
    assert all(f.severity == Severity.BLOCKER for f in result.findings)
    assert all(f.category == Category.SECURITY for f in result.findings)


def test_live_mode_without_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        review_diff(load_sample("clean_pr"), live=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_review_repo_end_to_end(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True
        )

    git("init", "-q")
    git("config", "user.email", "dev@example.com")
    git("config", "user.name", "Dev")
    (repo / "a.py").write_text("def f():\n    return 1\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    (repo / "a.py").write_text(
        "def f():\n    try:\n        return 1\n    except:\n        return 0\n"
    )
    git("add", "-A")
    git("commit", "-qm", "change")

    result = review_repo(str(repo))
    assert result.verdict == "block"
    assert any(f.line == 4 for f in result.findings)
