import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from c64lib.cartridge import CartError, cart_info, cart_verify
from c64lib.cli import main
from c64lib.packaging import PackageError, package_program

SRC = "tests/programs/hello-asm/program.s"

needs_cart_build = pytest.mark.skipif(
    not all(shutil.which(t) or os.environ.get(f"C64_TOOLS_{t.upper()}")
            for t in ("ca65", "ld65", "cartconv")),
    reason="needs the cc65 suite and VICE's cartconv")

CART_RET = {"crt": "g.crt", "bin": "g.bin", "labels": "g.lbl", "title": "G",
            "cart_type": "8k", "run": "x64sc -ntsc -cartcrt g.crt",
            "bytes": 300, "free": 7892}


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


def test_package_threads_the_cart_options_through(tmp_path):
    with patch("c64lib.cli.package_program", return_value=CART_RET) as pp:
        r = CliRunner().invoke(main, [
            "package", SRC, "-o", str(tmp_path / "g.crt"), "--format", "crt",
            "--cart-type", "16k", "--wrap"])
    assert r.exit_code == 0, r.output
    _, kwargs = pp.call_args
    assert kwargs["fmt"] == "crt" and kwargs["cart_type"] == "16k"
    assert kwargs["wrap"] is True


def test_package_crt_human_output_reports_the_budget(tmp_path):
    with patch("c64lib.cli.package_program", return_value=CART_RET):
        r = CliRunner().invoke(main, ["package", SRC, "-o", str(tmp_path / "g.crt")])
    assert r.exit_code == 0, r.output
    assert "g.crt" in r.output and "7,892 free" in r.output
    assert "x64sc -ntsc -cartcrt g.crt" in r.output


def test_package_crt_json_is_the_cartridge_dict(tmp_path):
    with patch("c64lib.cli.package_program", return_value=CART_RET):
        r = CliRunner().invoke(main, ["--json", "package", SRC,
                                      "-o", str(tmp_path / "g.crt")])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == CART_RET


def test_package_cart_error_is_reported(tmp_path):
    with patch("c64lib.cli.package_program",
               side_effect=CartError("a 16K cartridge maps ROM over $A000")):
        r = CliRunner().invoke(main, ["--json", "package", SRC,
                                      "-o", str(tmp_path / "g.crt")])
    assert r.exit_code == 1
    assert "$A000" in json.loads(r.output)["error"]


def test_package_rejects_cart_type_outside_a_cartridge(tmp_path):
    """--cart-type used to be silently ignored for non-cartridge output; it is
    as loud as --wrap now, so a typo'd format cannot pass unnoticed. The check
    itself lives in package_program (so the MCP tool gets it too), which is why
    these three tests exercise the real one instead of a mock."""
    r = CliRunner().invoke(main, ["--json", "package", SRC, "-o",
                                  str(tmp_path / "x.d64"),
                                  "--cart-type", "16k"])
    assert r.exit_code == 1
    assert "--cart-type" in json.loads(r.output)["error"]
    assert not list(tmp_path.iterdir())          # nothing was built


def test_package_rejects_area_where_it_cannot_apply(tmp_path):
    """--area rewrites the .prg linker config, which a tokenized .bas and a
    cartridge never go through. Loud, for the same reason --cart-type is."""
    bas = tmp_path / "p.bas"
    bas.write_text('10 print "hi"\n', encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "package", str(bas), "-o",
                                  str(tmp_path / "x.prg"),
                                  "--area", "HIGH=$4000:$2000"])
    assert r.exit_code == 1
    assert json.loads(r.output)["error"] == (
        "--area applies to assembly sources only")
    r = CliRunner().invoke(main, ["--json", "package", SRC, "-o",
                                  str(tmp_path / "g.crt"),
                                  "--area", "HIGH=$4000:$2000"])
    assert r.exit_code == 1
    assert "--area does not apply to cartridges" in json.loads(r.output)["error"]


def test_package_cart_type_defaults_to_8k_for_a_cartridge(tmp_path):
    """The sentinel changes only the outside-a-cartridge case: the CLI forwards
    it untouched and inside a cartridge it still means 8k."""
    with patch("c64lib.cli.package_program", return_value=CART_RET) as pp:
        r = CliRunner().invoke(main, ["package", SRC, "-o",
                                      str(tmp_path / "g.crt")])
    assert r.exit_code == 0, r.output
    assert pp.call_args.kwargs["cart_type"] is None
    with patch("c64lib.packaging.build_cart", return_value=CART_RET) as bc:
        package_program(SRC, out=tmp_path / "g.crt")
    assert bc.call_args.kwargs["cart_type"] == "8k"


def test_package_format_prg_with_a_crt_output_names_the_conflict(tmp_path):
    r = CliRunner().invoke(main, ["--json", "package", SRC, "--format", "prg",
                                  "-o", str(tmp_path / "x.crt")])
    assert r.exit_code == 1
    err = json.loads(r.output)["error"]
    assert "--format prg" in err and "cartridge" in err
    assert not list(tmp_path.iterdir())


def test_package_format_crt_with_a_disk_output_is_rejected(tmp_path):
    """A cartridge written to a .d64 name is a mislabeled file, not a disk."""
    r = CliRunner().invoke(main, ["--json", "package", SRC, "--format", "crt",
                                  "-o", str(tmp_path / "x.d64")])
    assert r.exit_code == 1
    assert ".d64" in json.loads(r.output)["error"]
    assert not list(tmp_path.iterdir())


def test_package_rejects_an_unsupported_format(tmp_path):
    r = CliRunner().invoke(main, ["package", SRC, "--format", "d64"])
    assert r.exit_code != 0
    assert "d64" in r.output


@needs_cart_build
def test_package_wraps_a_program_into_a_bootable_crt(tmp_path):
    out = tmp_path / "hello.crt"
    r = CliRunner().invoke(main, ["--json", "package", SRC, "-o", str(out),
                                  "--wrap", "--title", "HELLO"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["cart_type"] == "8k" and data["title"] == "HELLO"
    assert Path(data["crt"]) == out and out.exists()
    assert cart_verify(out) == []
    assert cart_info(out)["name"] == "HELLO"


@needs_cart_build
def test_package_format_crt_infers_the_output_path(tmp_path):
    src = tmp_path / "hello.s"
    src.write_text(Path(SRC).read_text(encoding="utf-8"), encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "package", str(src), "--format", "crt",
                                  "--wrap"])
    assert r.exit_code == 0, r.output
    assert Path(json.loads(r.output)["crt"]) == src.with_suffix(".crt")
