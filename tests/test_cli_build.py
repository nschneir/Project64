import json
from unittest.mock import patch

from click.testing import CliRunner

from c64lib.build import Area, BuildError, BuildResult
from c64lib.cli import main


def test_build_json(tmp_path):
    src = tmp_path / "p.s"
    src.write_text("; x\n")
    res = BuildResult(prg=tmp_path / "p.prg", labels=tmp_path / "p.lbl")
    with patch("c64lib.cli.build_asm", return_value=res) as ba:
        r = CliRunner().invoke(main, ["--json", "build", str(src)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["prg"].endswith("p.prg") and out["labels"].endswith("p.lbl")
    ba.assert_called_once_with(src, out_prg=None, basic_start=0x0801, areas=[])


def test_build_area_reaches_the_linker(tmp_path):
    src = tmp_path / "p.s"
    src.write_text("; x\n")
    res = BuildResult(prg=tmp_path / "p.prg", labels=tmp_path / "p.lbl")
    with patch("c64lib.cli.build_asm", return_value=res) as ba:
        r = CliRunner().invoke(main, ["--json", "build", str(src),
                                      "--area", "HIGH=$4000:$2000",
                                      "--area", "TOP=$6000:$1000"])
    assert r.exit_code == 0, r.output
    assert ba.call_args.kwargs["areas"] == [Area("HIGH", 0x4000, 0x2000),
                                            Area("TOP", 0x6000, 0x1000)]


def test_build_bad_area_exits_one(tmp_path):
    """A --area that cannot link is rejected before ca65 runs, in terms of
    the flag rather than of the config the toolset generated behind it."""
    src = tmp_path / "p.s"
    src.write_text("; x\n")
    r = CliRunner().invoke(main, ["--json", "build", str(src), "--area", "HIGH"])
    assert r.exit_code == 1
    assert json.loads(r.output)["error"] == (
        "--area needs NAME=START:SIZE, got 'HIGH'")


def test_build_error_exit_code(tmp_path):
    src = tmp_path / "p.s"
    src.write_text("bogus\n")
    with patch("c64lib.cli.build_asm", side_effect=BuildError("ca65 failed:\nsyntax error")):
        r = CliRunner().invoke(main, ["--json", "build", str(src)])
    assert r.exit_code == 1
    assert "syntax error" in json.loads(r.output)["error"]
