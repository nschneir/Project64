"""--json works before OR after the subcommand (the trailing position is
what people type first), and an exception no command caught still lands as a
JSON error object rather than a traceback over empty stdout."""

import json
from unittest.mock import Mock, patch

import click
import pytest
from click.testing import CliRunner

from c64lib.cli import JsonAwareGroup, fail, main
from c64lib.session import SessionError
from tests.conftest import assert_json_error


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    return tmp_path


def test_json_after_subcommand_on_a_sessionless_command():
    result = CliRunner().invoke(main, ["session", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"sessions": []}


def test_json_before_subcommand_still_works():
    result = CliRunner().invoke(main, ["--json", "session", "list"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"sessions": []}


def test_json_available_on_nested_group_commands():
    basic = main.commands["basic"]
    # click types Group.commands as dict[str, Command]; `basic` is a group.
    assert isinstance(basic, click.Group)
    cmd = basic.commands["check"]
    assert "--json" in {o for p in cmd.params for o in getattr(p, "opts", [])}


def test_json_end_to_end_on_a_nested_group_command(tmp_path):
    """Registering the option isn't enough — the trailing flag must
    actually flip ctx.obj["json"] for a command reached through a nested
    group (main -> basic -> check), not just a top-level one."""
    src = tmp_path / "clean.bas"
    src.write_text('10 print "hi"\n')
    result = CliRunner().invoke(main, ["basic", "check", str(src), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data == {"issues": [], "errors": 0, "warnings": 0, "tokenized_bytes": 13}


def test_json_after_reg_group_used_as_a_leaf_command():
    """`reg` is declared with invoke_without_command=True and behaves as a
    leaf command when no subcommand is given — it must accept trailing
    --json too, not just its `set` subcommand. Regression guard: this used
    to fail with "Error: No such option '--json'" because JsonAwareGroup
    only equipped its *subcommands*, not itself, with the trailing flag."""
    mon = Mock()
    mon.registers.return_value = {"PC": 0x0801, "A": 0x2A}
    fake = Mock()
    fake.name, fake.model, fake.socket = "c64", "c64", None
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        result = CliRunner().invoke(main, ["reg", "--json"])
    assert result.exit_code == 0, result.output
    assert "No such option" not in result.output
    assert json.loads(result.output)["registers"]["PC"] == 0x0801


def test_session_available_on_nested_group_commands():
    basic = main.commands["basic"]
    assert isinstance(basic, click.Group)
    cmd = basic.commands["check"]
    assert "--session" in {o for p in cmd.params for o in getattr(p, "opts", [])}


def test_session_after_subcommand_targets_the_named_session():
    """`c64 mem get basex 1 --session inv` used to die with Click's
    'Did you mean --json?' — the dogfood's most-hit ergonomic trap."""
    mon = Mock()
    mon.memory_read.return_value = bytes([7])
    fake = Mock()
    fake.name, fake.model, fake.labels, fake.socket = "inv", "c64", None, None
    fake.profile.screen_cols, fake.profile.screen_rows = 40, 25
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "get", "$0400", "--session", "inv"])
    assert r.exit_code == 0, r.output
    S.attach.assert_called_once_with("inv")


def test_dash_s_after_subcommand_works_too():
    mon = Mock()
    mon.memory_read.return_value = bytes([7])
    fake = Mock()
    fake.name, fake.model, fake.labels, fake.socket = "inv", "c64", None, None
    fake.profile.screen_cols, fake.profile.screen_rows = 40, 25
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "get", "$0400", "-s", "inv"])
    assert r.exit_code == 0, r.output
    S.attach.assert_called_once_with("inv")


def test_trailing_dash_s_wins_over_a_leading_one():
    """Both positions accepted means both can be given at once. Click runs
    main's callback first and the trailing callback overwrites it, so the
    trailing spelling wins — pinned so the precedence is not accidental."""
    mon = Mock()
    mon.memory_read.return_value = bytes([7])
    fake = Mock()
    fake.name, fake.model, fake.labels, fake.socket = "b", "c64", None, None
    fake.profile.screen_cols, fake.profile.screen_rows = 40, 25
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["-s", "a", "mem", "get", "$0400",
                                      "-s", "b"])
    assert r.exit_code == 0, r.output
    S.attach.assert_called_once_with("b")


# --- the last-chance error boundary ---------------------------------------

def _boom_cli(exc: BaseException) -> click.Group:
    """A `main` look-alike built on the real group class: `boom` raises `exc`
    with nothing catching it, `nested boom` does the same one group deeper, and
    `polite` reports through `fail()`. Synthetic because the guard is generic —
    it must hold for a command that has not been written yet."""
    @click.group(cls=JsonAwareGroup)
    @click.option("--json", "json_out", is_flag=True)
    @click.pass_context
    def cli(ctx: click.Context, json_out: bool) -> None:
        ctx.obj = {"json": json_out, "session": None}

    @cli.command("boom")
    def boom() -> None:
        raise exc

    @cli.group("nested")
    def nested() -> None:
        pass

    @nested.command("boom")
    def nested_boom() -> None:
        raise exc

    @cli.command("polite")
    @click.pass_context
    def polite(ctx: click.Context) -> None:
        fail(ctx, "no such thing; run `c64 help` for the list")

    return cli


@pytest.mark.parametrize("exc, fragment", [
    (ValueError("bad LENGTH 'zz'"), "bad LENGTH 'zz'"),
    (KeyError("port"), "port"),            # str(KeyError) is the bare quoted key
    (OSError("registry unreadable"), "registry unreadable"),
    # SessionError subclasses none of the three, so the tuple names it:
    (SessionError("session record is unreadable"), "session record is unreadable"),
    # An argless raise: `str(ValueError())` is '', and `{"error": ""}` is a
    # payload that parses and says nothing. The class name is the floor.
    (ValueError(), "ValueError"),
])
def test_an_escaped_input_error_still_lands_in_the_json_contract(exc, fragment):
    r = CliRunner().invoke(_boom_cli(exc), ["boom", "--json"])
    assert fragment in assert_json_error(r)["error"]


def test_an_escaped_error_from_a_nested_group_is_reported_exactly_once():
    """Every nested group is a `JsonAwareGroup` too (`group_class = type`), so
    the guard is inherited at every level. The inner one reports and exits;
    `SystemExit` is not caught, so the outer one must not report again — two
    concatenated objects on stdout would not parse."""
    r = CliRunner().invoke(_boom_cli(ValueError("bad LENGTH 'zz'")),
                           ["nested", "boom", "--json"])
    assert assert_json_error(r)["error"] == "bad LENGTH 'zz'"


def test_the_escaped_traceback_still_reaches_stderr():
    """The payload says what broke; the traceback says where. stderr is the
    only place it can go without making stdout unparseable."""
    r = CliRunner().invoke(_boom_cli(ValueError("bad LENGTH 'zz'")),
                           ["boom", "--json"])
    assert "Traceback (most recent call last)" in r.stderr
    assert "ValueError: bad LENGTH 'zz'" in r.stderr


def test_a_fail_call_is_not_double_reported():
    """`fail()` exits by raising `SystemExit`; catching that would append the
    guard's own payload to the one the command already wrote."""
    r = CliRunner().invoke(_boom_cli(ValueError("never raised")), ["polite", "--json"])
    assert assert_json_error(r)["error"] == "no such thing; run `c64 help` for the list"
    assert "Traceback" not in r.stderr


def test_an_escaped_error_without_json_stays_human():
    r = CliRunner().invoke(_boom_cli(ValueError("bad LENGTH 'zz'")), ["boom"])
    assert r.exit_code == 1
    assert r.stdout == "", "a --json-less caller got machine output on stdout"
    assert "error: bad LENGTH 'zz'" in r.stderr


def test_a_failure_before_the_group_callback_is_still_reported():
    """`ctx.obj` is None until the group callback fills it, and the guard wraps
    that callback too — so the json flag is read defensively. Indexing
    `ctx.obj` here would replace the report with a `TypeError`."""
    @click.group(cls=JsonAwareGroup)
    def cli() -> None:
        raise ValueError("bad --session name ''")

    @cli.command("boom")
    def boom() -> None:
        pass

    r = CliRunner().invoke(cli, ["boom"])
    assert r.exit_code == 1
    assert "error: bad --session name ''" in r.stderr


def test_a_genuine_bug_is_not_dressed_up_as_an_input_error():
    """The tuple never widens to bare `Exception`, so a defect that is not
    input-shaped stays a traceback instead of posing as user error. `RuntimeError`
    specifically must stay out for a second reason: `ctx.exit()` raises
    `click.exceptions.Exit`, which subclasses it, so catching `RuntimeError`
    would turn every `ctx.exit(1)` into `{"error": "1"}`."""
    r = CliRunner().invoke(_boom_cli(RuntimeError("monitor client is confused")),
                           ["boom", "--json"])
    assert isinstance(r.exception, RuntimeError)
    assert r.stdout == ""


def test_session_commands_keep_their_own_dash_s_meaning():
    """session start/ensure/stop already use -s as the --name alias; the
    injected trailing --session must not clobber them (guard by opts)."""
    session_grp = main.commands["session"]
    # click types Group.commands as dict[str, Command]; `session` is a group.
    assert isinstance(session_grp, click.Group)
    for name in ("start", "ensure", "stop"):
        cmd = session_grp.commands[name]
        opts = {o for p in cmd.params for o in getattr(p, "opts", [])}
        assert "-s" in opts                      # still the --name alias
        assert "--session" not in opts           # not double-registered
