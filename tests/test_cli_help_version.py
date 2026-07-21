"""--version, --help, and the `c64 help` subcommand."""

from click.testing import CliRunner

from c64lib import __version__
from c64lib.cli import main


def test_version_flag_reports_package_version():
    r = CliRunner().invoke(main, ["--version"])
    assert r.exit_code == 0
    assert r.output.strip() == f"c64 {__version__}"


def test_help_flag_lists_commands():
    r = CliRunner().invoke(main, ["--help"])
    assert r.exit_code == 0
    assert "Commands:" in r.output and "session" in r.output


def test_help_command_matches_help_flag():
    runner = CliRunner()
    via_cmd = runner.invoke(main, ["help"]).output
    via_flag = runner.invoke(main, ["--help"]).output
    assert via_cmd == via_flag


def test_help_command_drills_into_subcommands():
    # prog_name mirrors the console script (the entry point runs as `c64`).
    r = CliRunner().invoke(main, ["help", "session", "start"], prog_name="c64")
    assert r.exit_code == 0
    assert "Usage: c64 session start" in r.output


def test_help_command_unknown_path_errors():
    r = CliRunner().invoke(main, ["help", "nope"])
    assert r.exit_code == 1
    assert "no such command: nope" in r.output


def test_subcommand_help_flag_works():
    r = CliRunner().invoke(main, ["session", "start", "--help"], prog_name="c64")
    assert r.exit_code == 0
    assert "Usage: c64 session start" in r.output
