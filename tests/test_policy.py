from agent_code_review.models import Category, Finding, Severity
from agent_code_review.policy import apply_policy, deduplicate


def f(severity=Severity.MAJOR, confidence=0.9, line=1, category=Category.BUG,
      source="static", message="m"):
    return Finding(
        file="a.py", line=line, severity=severity, category=category,
        confidence=confidence, message=message, suggestion="s", source=source,
    )


def test_blocker_blocks_merge():
    result = apply_policy([f(severity=Severity.BLOCKER)])
    assert result.verdict == "block"
    assert len(result.blocking) == 1


def test_major_blocks_merge():
    result = apply_policy([f(severity=Severity.MAJOR)])
    assert result.verdict == "block"


def test_minor_and_nit_approve():
    result = apply_policy([
        f(severity=Severity.MINOR, line=1),
        f(severity=Severity.NIT, line=2),
    ])
    assert result.verdict == "approve"
    assert len(result.kept) == 2


def test_low_confidence_suppressed_not_dropped():
    result = apply_policy([f(confidence=0.4)])
    assert result.kept == []
    assert len(result.suppressed) == 1
    assert result.verdict == "approve"


def test_suppressed_blocker_does_not_block():
    result = apply_policy([f(severity=Severity.BLOCKER, confidence=0.3)])
    assert result.verdict == "approve"


def test_custom_threshold():
    result = apply_policy([f(confidence=0.4)], confidence_threshold=0.3)
    assert len(result.kept) == 1
    assert result.suppressed == []


def test_dedup_keeps_higher_confidence():
    low = f(confidence=0.8, message="agent version", source="agent")
    high = f(confidence=0.95, message="static version", source="static")
    deduped = deduplicate([low, high])
    assert len(deduped) == 1
    assert deduped[0].message == "static version"


def test_dedup_tie_prefers_static_source():
    agent = f(confidence=0.9, message="agent", source="agent")
    static = f(confidence=0.9, message="static", source="static")
    deduped = deduplicate([agent, static])
    assert len(deduped) == 1
    assert deduped[0].source == "static"


def test_dedup_keeps_different_categories_on_same_line():
    a = f(category=Category.BUG)
    b = f(category=Category.SECURITY)
    assert len(deduplicate([a, b])) == 2


def test_sorting_blockers_first_then_line():
    result = apply_policy([
        f(severity=Severity.NIT, line=1),
        f(severity=Severity.BLOCKER, line=9),
        f(severity=Severity.MAJOR, line=3),
        f(severity=Severity.BLOCKER, line=2),
    ])
    order = [(x.severity, x.line) for x in result.kept]
    assert order == [
        (Severity.BLOCKER, 2),
        (Severity.BLOCKER, 9),
        (Severity.MAJOR, 3),
        (Severity.NIT, 1),
    ]


def test_counts():
    result = apply_policy([
        f(severity=Severity.BLOCKER, line=1),
        f(severity=Severity.BLOCKER, line=2),
        f(severity=Severity.NIT, line=3),
    ])
    counts = result.counts()
    assert counts["blocker"] == 2
    assert counts["nit"] == 1
    assert counts["major"] == 0
