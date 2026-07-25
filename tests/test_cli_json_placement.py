"""--json works before OR after the subcommand (the trailing position is
what people type first)."""

import json

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
    cmd = main.commands["basic"].commands["check"]
    assert "--json" in {o for p in cmd.params for o in getattr(p, "opts", [])}
