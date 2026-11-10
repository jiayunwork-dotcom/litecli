import os
import tempfile

import pytest

import litecli.packages.special
from litecli.packages import special
from litecli.packages.special.main import CommandNotFound, Verbosity, parse_special_command


@pytest.fixture(autouse=True)
def reset_session_settings():
    """Restore the session-level settings after every test in this module."""
    yield
    special.set_headers_enabled(True)
    special.set_echo_enabled(False)
    special.set_null_value(None)


def test_once_command():
    with pytest.raises(TypeError):
        litecli.packages.special.execute(None, ".once")

    with pytest.raises(OSError):
        litecli.packages.special.execute(None, ".once /proc/access-denied")

    litecli.packages.special.write_once("hello world")  # write without file set
    # keep Windows from locking the file with delete=False
    with tempfile.NamedTemporaryFile(delete=False) as f:
        litecli.packages.special.execute(None, ".once " + f.name)
        litecli.packages.special.write_once("hello world")
        if os.name == "nt":
            assert f.read() == b"hello world\r\n"
        else:
            assert f.read() == b"hello world\n"

        litecli.packages.special.execute(None, ".once -o " + f.name)
        litecli.packages.special.write_once("hello world line 1")
        litecli.packages.special.write_once("hello world line 2")
        f.seek(0)
        if os.name == "nt":
            assert f.read() == b"hello world line 1\r\nhello world line 2\r\n"
        else:
            assert f.read() == b"hello world line 1\nhello world line 2\n"
    # delete=False means we should try to clean up
    try:
        if os.path.exists(f.name):
            os.remove(f.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


def test_pipe_once_command():
    with pytest.raises(IOError):
        litecli.packages.special.execute(None, "\\pipe_once")

    with pytest.raises(OSError):
        litecli.packages.special.execute(None, "\\pipe_once /proc/access-denied")

    if os.name == "nt":
        litecli.packages.special.execute(None, '\\pipe_once python -c "import sys; print(len(sys.stdin.read().strip()))"')
        litecli.packages.special.write_pipe_once("hello world")
        litecli.packages.special.unset_pipe_once_if_written()
    else:
        with tempfile.NamedTemporaryFile() as f:
            litecli.packages.special.execute(None, "\\pipe_once tee " + f.name)
            litecli.packages.special.write_pipe_once("hello world")
            litecli.packages.special.unset_pipe_once_if_written()
            f.seek(0)
            assert f.read() == b"hello world\n"


@pytest.mark.parametrize(
    "sql,expected",
    [
        (r"\d table_name", ("\\d", Verbosity.NORMAL, "table_name")),
        (r"\d+ table_name", ("\\d", Verbosity.VERBOSE, "table_name")),
        (r"\?", ("\\?", Verbosity.NORMAL, "")),
        (r"\llm Question", ("\\llm", Verbosity.NORMAL, "Question")),
        (r"\llm-", ("\\llm", Verbosity.SUCCINCT, "")),
        (r"\llm+", ("\\llm", Verbosity.VERBOSE, "")),
    ],
)
def test_parse_special_command(sql, expected):
    """
    Ensure parse_special_command correctly splits the command and mode.
    """
    result = parse_special_command(sql)
    assert result == expected


def test_parse_special_command_edge_cases():
    # mycli-compatible behavior: no ValueError on special characters; it parses leniently.
    sql = r"\llm* Question"
    assert parse_special_command(sql) == ("\\llm*", Verbosity.NORMAL, "Question")

    sql = r"\llm+- Question"
    # '+' in command sets verbosity; strip('+-') removes both suffixes
    assert parse_special_command(sql) == ("\\llm", Verbosity.VERBOSE, "Question")


def test_headers_default_and_toggle():
    assert special.is_headers_enabled() is True

    special.execute(None, ".headers off")
    assert special.is_headers_enabled() is False

    special.execute(None, ".headers ON")
    assert special.is_headers_enabled() is True

    special.execute(None, ".headers OfF")
    assert special.is_headers_enabled() is False


@pytest.mark.parametrize("arg", ["", "yes", "no", "1", "0", "on off", "on\nx"])
def test_headers_invalid_argument_keeps_state(arg, capsys):
    assert special.is_headers_enabled() is True
    special.execute(None, ".headers " + arg)
    out = capsys.readouterr().out
    assert ".headers" in out
    # State is untouched, including when already disabled.
    assert special.is_headers_enabled() is True

    special.set_headers_enabled(False)
    special.execute(None, ".headers " + arg)
    capsys.readouterr()
    assert special.is_headers_enabled() is False


def test_echo_default_and_toggle():
    assert special.is_echo_enabled() is False

    special.execute(None, ".echo on")
    assert special.is_echo_enabled() is True

    special.execute(None, ".echo OFF")
    assert special.is_echo_enabled() is False


@pytest.mark.parametrize("arg", ["", "yes", "no", "1", "0", "off on", "true"])
def test_echo_invalid_argument_keeps_state(arg, capsys):
    special.execute(None, ".echo " + arg)
    assert ".echo" in capsys.readouterr().out
    assert special.is_echo_enabled() is False

    special.set_echo_enabled(True)
    special.execute(None, ".echo " + arg)
    capsys.readouterr()
    assert special.is_echo_enabled() is True


def test_echo_sql_prints_only_when_enabled(capsys):
    special.echo_sql("select 1")
    assert capsys.readouterr().out == ""

    special.set_echo_enabled(True)
    special.echo_sql("select 1")
    assert capsys.readouterr().out == "select 1\n"


def test_nullvalue_default_is_unset():
    assert special.get_null_value() is None


def test_nullvalue_takes_rest_as_literal_text():
    special.execute(None, ".nullvalue N/A")
    assert special.get_null_value() == "N/A"

    # Quotes are ordinary characters, internal whitespace is preserved and
    # surrounding whitespace is trimmed.
    special.execute(None, ".nullvalue 'N A'")
    assert special.get_null_value() == "'N A'"

    special.execute(None, ".nullvalue   N  A  ")
    assert special.get_null_value() == "N  A"

    # No argument means an empty string, distinct from the unset sentinel.
    special.execute(None, ".nullvalue")
    assert special.get_null_value() == ""


def test_print_collapses_whitespace_and_keeps_quotes(capsys):
    special.execute(None, ".print hello   world")
    assert capsys.readouterr().out == "hello world\n"

    special.execute(None, ".print  a\tb  c ")
    assert capsys.readouterr().out == "a b c\n"

    special.execute(None, ".print 'quoted text'")
    assert capsys.readouterr().out == "'quoted text'\n"


@pytest.mark.parametrize("arg", ["", "   "])
def test_print_without_text_outputs_nothing(arg, capsys):
    special.execute(None, ".print" + arg)
    assert capsys.readouterr().out == ""


def test_show_reports_defaults(capsys):
    special.execute(None, ".show")
    assert capsys.readouterr().out == 'echo: off\nheaders: on\nnullvalue: ""\n'


def test_show_reports_current_values(capsys):
    special.execute(None, ".echo on")
    special.execute(None, ".headers off")
    special.execute(None, ".nullvalue N/A")
    special.execute(None, ".show")
    assert capsys.readouterr().out == 'echo: on\nheaders: off\nnullvalue: "N/A"\n'


def test_show_empty_nullvalue_after_unset(capsys):
    special.execute(None, ".nullvalue")
    special.execute(None, ".show")
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == 'nullvalue: ""'


@pytest.mark.parametrize("command", [".HEADERS", ".Headers", ".ECHO", ".NULLVALUE", ".PRINT", ".SHOW"])
def test_uppercase_commands_are_not_registered(command):
    with pytest.raises(CommandNotFound):
        special.execute(None, command + " on")
