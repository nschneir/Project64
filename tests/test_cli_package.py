import json
from unittest.mock import patch

from click.testing import CliRunner

from c64lib.cli import main
from c64lib.packaging import PackageError

SRC = "tests/programs/hello-asm/program.s"


def test_package_json_passthrough(tmp_path):
    ret = {"prg": "x.prg", "image": "x.d64", "title": "X", "run": "x64sc x.d64"}
    with patch("c64lib.cli.package_program", return_value=ret) as pp:
        r = CliRunner().invoke(main, [
            "--json", "package", SRC, "-o", str(tmp_path / "x.d64"), "--title", "x"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == ret
    pp.assert_called_once()
    _, kwargs = pp.call_args
    assert kwargs["title"] == "x" and kwargs["model"] == "c64"


def test_package_human_output_includes_run_command():
    ret = {"prg": "s.prg", "image": "s.d64", "title": "S", "run": "x64sc s.d64"}
    with patch("c64lib.cli.package_program", return_value=ret):
        r = CliRunner().invoke(main, ["package", SRC])
    assert r.exit_code == 0
    assert "x64sc s.d64" in r.output


def test_package_error_is_actionable():
    with patch("c64lib.cli.package_program",
               side_effect=PackageError("title 'X'*20 max out at 16")):
        r = CliRunner().invoke(main, ["--json", "package", SRC])
    assert r.exit_code == 1
    assert "16" in json.loads(r.output)["error"]
