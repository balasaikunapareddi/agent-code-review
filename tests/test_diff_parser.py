from agent_code_review.diff_parser import diff_stats, parse_diff

from conftest import load_sample


def test_multi_file_diff():
    text = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1,1 +1,1 @@\n-old\n+new\n"
        "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n"
        "@@ -1,1 +1,2 @@\n ctx\n+added\n"
    )
    files = parse_diff(text)
    assert [f.path for f in files] == ["a.py", "b.py"]
    assert files[0].added_lines()[0].content == "new"
    assert files[1].added_lines()[0].content == "added"


def test_new_file_line_numbers():
    text = (
        "diff --git a/x.py b/x.py\n--- /dev/null\n+++ b/x.py\n"
        "@@ -0,0 +1,3 @@\n+one\n+two\n+three\n"
    )
    (fd,) = parse_diff(text)
    assert fd.is_new_file
    assert [l.new_lineno for l in fd.added_lines()] == [1, 2, 3]


def test_deleted_file():
    text = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n-one\n-two\n"
    )
    (fd,) = parse_diff(text)
    assert fd.is_deleted_file
    assert fd.path == "x.py"
    assert len(fd.removed_lines()) == 2


def test_rename():
    text = (
        "diff --git a/old.py b/new.py\n"
        "similarity index 90%\n"
        "rename from old.py\n"
        "rename to new.py\n"
        "--- a/old.py\n+++ b/new.py\n"
        "@@ -1,1 +1,1 @@\n-a\n+b\n"
    )
    (fd,) = parse_diff(text)
    assert fd.is_rename
    assert fd.old_path == "old.py"
    assert fd.new_path == "new.py"
    assert fd.path == "new.py"


def test_binary_file():
    text = (
        "diff --git a/logo.png b/logo.png\n"
        "Binary files a/logo.png and b/logo.png differ\n"
    )
    (fd,) = parse_diff(text)
    assert fd.is_binary
    assert fd.hunks == []


def test_context_and_deletion_line_numbers():
    text = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
        "@@ -10,3 +20,3 @@\n ctx\n-gone\n+fresh\n"
    )
    (fd,) = parse_diff(text)
    lines = fd.hunks[0].lines
    assert lines[0].new_lineno == 20 and lines[0].old_lineno == 10
    assert lines[1].kind == "del" and lines[1].new_lineno is None
    assert lines[1].old_lineno == 11
    assert lines[2].kind == "add" and lines[2].new_lineno == 21


def test_plain_diff_without_git_header():
    text = "--- a/x.py\n+++ b/x.py\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    (fd,) = parse_diff(text)
    assert fd.path == "x.py"
    assert fd.added_lines()[0].content == "b"


def test_no_newline_marker_ignored():
    text = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
        "@@ -1,1 +1,1 @@\n-a\n\\ No newline at end of file\n+b\n"
    )
    (fd,) = parse_diff(text)
    assert [l.content for l in fd.added_lines()] == ["b"]


def test_sample_diffs_parse_with_expected_stats():
    clean = parse_diff(load_sample("clean_pr"))
    assert diff_stats(clean)["files_changed"] == 1
    assert diff_stats(clean)["additions"] == 26

    buggy = parse_diff(load_sample("buggy_pr"))
    stats = diff_stats(buggy)
    assert stats["files_changed"] == 1
    assert stats["additions"] == 32
    assert stats["deletions"] == 1
