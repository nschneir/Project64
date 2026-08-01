"""--json works before OR after the subcommand (the trailing position is
what people type first)."""

import json
from unittest.mock import Mock, patch

import click
import pytest
from click.testing import CliRunner

from c64lib.cli import main


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
