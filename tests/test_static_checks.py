from agent_code_review.diff_parser import parse_diff
from agent_code_review.models import Category, Severity
from agent_code_review.static_checks import (
    check_bare_except,
    check_debug_print,
    check_eval_exec,
    check_hardcoded_secret,
    check_missing_timeout,
    check_mutable_default,
    check_sql_string_format,
    check_todo_without_ticket,
    run_static_checks,
)

from conftest import make_diff


def one_file(path, added):
    (fd,) = parse_diff(make_diff(path, added))
    return fd


# --- bare except --------------------------------------------------------

def test_bare_except_fires():
    fd = one_file("a.py", ["try:", "    x()", "except:", "    pass"])
    findings = check_bare_except(fd)
    assert len(findings) == 1
    assert findings[0].line == 3
    assert findings[0].severity == Severity.MAJOR
    assert findings[0].category == Category.BUG


def test_specific_except_ok():
    fd = one_file("a.py", ["try:", "    x()", "except ValueError:", "    pass"])
    assert check_bare_except(fd) == []


# --- mutable default ----------------------------------------------------

def test_mutable_default_fires():
    fd = one_file("a.py", ["def f(items=[]):", "    return items"])
    findings = check_mutable_default(fd)
    assert len(findings) == 1
    assert findings[0].line == 1


def test_mutable_default_dict_and_factory_fire():
    fd = one_file("a.py", ["def f(a={}, b=list()):", "    pass"])
    assert len(check_mutable_default(fd)) == 1


def test_none_and_tuple_defaults_ok():
    fd = one_file("a.py", ["def f(items=None, pair=()):", "    pass"])
    assert check_mutable_default(fd) == []


# --- SQL string building --------------------------------------------------

def test_sql_fstring_fires():
    fd = one_file("a.py", ['cursor.execute(f"SELECT * FROM t WHERE id = {uid}")'])
    findings = check_sql_string_format(fd)
    assert len(findings) == 1
    assert findings[0].severity == Severity.BLOCKER
    assert findings[0].category == Category.SECURITY


def test_sql_concat_fires():
    fd = one_file("a.py", ['cursor.execute("DELETE FROM t WHERE id = " + uid)'])
    assert len(check_sql_string_format(fd)) == 1


def test_sql_percent_format_fires():
    fd = one_file("a.py", ['q = "SELECT * FROM t WHERE id = %s" % uid'])
    assert len(check_sql_string_format(fd)) == 1


def test_parameterized_sql_ok():
    fd = one_file("a.py", ['cursor.execute("SELECT * FROM t WHERE id = ?", (uid,))'])
    assert check_sql_string_format(fd) == []


def test_plain_sql_string_ok():
    fd = one_file("a.py", ['cursor.execute("SELECT * FROM t")'])
    assert check_sql_string_format(fd) == []


# --- hardcoded secrets ----------------------------------------------------

def test_secret_assignment_fires():
    fd = one_file("a.py", ['api_key = "abcd1234efgh5678"'])
    findings = check_hardcoded_secret(fd)
    assert len(findings) == 1
    assert findings[0].severity == Severity.BLOCKER


def test_secret_env_lookup_ok():
    fd = one_file("a.py", ['api_key = os.environ["API_KEY"]'])
    assert check_hardcoded_secret(fd) == []


def test_secret_placeholder_ok():
    fd = one_file("a.py", ['password = "changeme-please"'])
    assert check_hardcoded_secret(fd) == []


def test_known_key_format_fires_anywhere():
    fd = one_file("config.txt", ['aws_id = "AKIAQ7X2M9PL4RD8KZ3W"'])
    assert len(check_hardcoded_secret(fd)) == 1


# --- missing timeout ------------------------------------------------------

def test_missing_timeout_fires():
    fd = one_file("a.py", ["resp = requests.get(url)"])
    findings = check_missing_timeout(fd)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MAJOR


def test_timeout_same_line_ok():
    fd = one_file("a.py", ["resp = requests.get(url, timeout=5)"])
    assert check_missing_timeout(fd) == []


def test_timeout_multiline_call_ok():
    fd = one_file(
        "a.py",
        [
            "resp = requests.get(",
            "    url,",
            "    timeout=5,",
            ")",
        ],
    )
    assert check_missing_timeout(fd) == []


def test_multiline_call_without_timeout_fires_at_opener():
    fd = one_file(
        "a.py",
        [
            "resp = requests.post(",
            "    url,",
            "    json=payload,",
            ")",
        ],
    )
    findings = check_missing_timeout(fd)
    assert len(findings) == 1
    assert findings[0].line == 1


# --- eval / exec ------------------------------------------------------------

def test_eval_fires():
    fd = one_file("a.py", ["result = eval(user_input)"])
    findings = check_eval_exec(fd)
    assert len(findings) == 1
    assert findings[0].severity == Severity.BLOCKER


def test_literal_eval_ok():
    fd = one_file("a.py", ["result = ast.literal_eval(user_input)"])
    assert check_eval_exec(fd) == []


def test_method_eval_ok():
    fd = one_file("a.py", ["model.eval()"])
    assert check_eval_exec(fd) == []


# --- TODO without ticket ----------------------------------------------------

def test_todo_without_ticket_fires():
    fd = one_file("a.py", ["# TODO: fix this later"])
    findings = check_todo_without_ticket(fd)
    assert len(findings) == 1
    assert findings[0].severity == Severity.NIT


def test_todo_with_ticket_ok():
    fd = one_file("a.py", ["# TODO(#123): fix this later"])
    assert check_todo_without_ticket(fd) == []


def test_todo_with_jira_key_ok():
    fd = one_file("a.py", ["# FIXME PROJ-42: broken on Tuesdays"])
    assert check_todo_without_ticket(fd) == []


# --- debug print --------------------------------------------------------------

def test_debug_print_fires_low_confidence():
    fd = one_file("app/main.py", ['print("hello")'])
    findings = check_debug_print(fd)
    assert len(findings) == 1
    assert findings[0].confidence < 0.7  # suppressed by default policy


def test_print_in_tests_ok():
    fd = one_file("tests/test_main.py", ['print("hello")'])
    assert check_debug_print(fd) == []


# --- scope rules ----------------------------------------------------------------

def test_checks_ignore_deleted_lines():
    text = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1,2 +1,1 @@\n-except:\n+except ValueError:\n"
    )
    (fd,) = parse_diff(text)
    assert run_static_checks([fd]) == []


def test_python_checks_skip_non_python_files():
    fd = one_file("notes.txt", ["except:", "def f(x=[]):"])
    assert check_bare_except(fd) == []
    assert check_mutable_default(fd) == []
