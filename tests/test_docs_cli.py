from pathlib import Path

from tests.doc_helpers import all_command_paths, documented_paths

DOC = Path("docs/cli.md")


def test_every_command_documented_and_vice_versa():
    documented = documented_paths(DOC.read_text())
    actual = all_command_paths()
    missing = actual - documented
    stale = documented - actual
    assert not missing, f"commands lacking a '### `c64 ...`' entry: {sorted(missing)}"
    assert not stale, f"documented commands that do not exist: {sorted(stale)}"


def test_inventory_size_sanity():
    assert len(all_command_paths()) >= 35


def test_session_commands_share_name_option():
    """WS4: one spelling (-s/--name) works on every session-targeting command."""
    from c64lib.cli import main as cli
    for cmd_name in ("start", "stop"):
        cmd = cli.commands["session"].commands[cmd_name]
        names = {o for p in cmd.params for o in getattr(p, "opts", [])}
        assert "--name" in names and "-s" in names, \
            f"session {cmd_name} lacks -s/--name (has {sorted(names)})"


def test_cli_md_names_every_machine_profile():
    from c64lib.machines import PROFILES
    text = DOC.read_text()
    for name in PROFILES:
        assert f"`{name}`" in text, f"docs/cli.md never names {name}"
