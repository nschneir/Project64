"""c64lib.packaging: source -> runnable .prg / autostart-first disk image."""

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from c64lib.packaging import PackageError, cbm_title, package_program

needs_cc65 = pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed")
needs_petcat = pytest.mark.skipif(
    shutil.which("petcat") is None, reason="petcat not installed")
needs_c1541 = pytest.mark.skipif(
    shutil.which("c1541") is None and not os.environ.get("C64_TOOLS_C1541"),
    reason="c1541 not installed")

HELLO_ASM = Path("tests/programs/hello-asm/program.s")
HELLO_BAS = Path("tests/programs/hello-basic/program.bas")


def test_cbm_title_rules():
    assert cbm_title("snake") == "SNAKE"
    assert cbm_title("hi there-2") == "HI THERE-2"
    with pytest.raises(PackageError):
        cbm_title("")
    with pytest.raises(PackageError):
        cbm_title("x" * 17)
    with pytest.raises(PackageError):
        cbm_title('bad"name')
    with pytest.raises(PackageError):
        cbm_title("em—dash")           # no em dash in PETSCII


def test_bad_output_extension_fails_before_building(tmp_path):
    with pytest.raises(PackageError) as e:
        package_program(HELLO_ASM, out=tmp_path / "x.tap")
    assert ".tap" in str(e.value) and ".d64" in str(e.value)


@needs_cc65
def test_package_prg_only(tmp_path):
    out = package_program(HELLO_ASM, out=tmp_path / "hello.prg", title="hello")
    assert out["image"] is None and out["title"] == "HELLO"
    assert Path(out["prg"]).read_bytes()[:2] == b"\x01\x08"
    assert out["run"] == f"x64sc -ntsc {tmp_path / 'hello.prg'}"


@needs_cc65
@needs_c1541
def test_package_d64_autostart_first(tmp_path):
    from c64lib.disk import list_files
    out = package_program(HELLO_ASM, out=tmp_path / "hello.d64", title="hello")
    assert out["image"] == str(tmp_path / "hello.d64")
    # The run hint must pin the model: stock x64sc's default model need not
    # match, and frame timing differs between the video standards.
    assert out["run"] == f"x64sc -ntsc {tmp_path / 'hello.d64'}"
    d = list_files(out["image"])
    assert d["files"], "image has no files"
    assert d["files"][0]["name"] == "hello"      # first file = autostart target
    assert d["files"][0]["type"].lower().startswith("prg")
    assert Path(out["prg"]).exists()             # the intermediate .prg is kept


@needs_petcat
@needs_c1541
def test_package_bas_source(tmp_path):
    out = package_program(HELLO_BAS, out=tmp_path / "hi.d64")
    assert out["title"] == "PROGRAM"             # defaults to the source stem
    assert Path(out["prg"]).read_bytes()[:2] == b"\x01\x08"


@pytest.mark.vice
@needs_cc65
@needs_c1541
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed")
def test_packaged_disk_boots_live(tmp_path, monkeypatch):
    """The spec's acceptance test: a packaged d64 autostarts in stock VICE."""
    from c64lib.session import Session
    from tests.vice_helpers import wait_for_text
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    out = package_program(HELLO_ASM, out=tmp_path / "hello.d64", title="hello")
    s = Session.launch(model="c64", name="pkgtest", headless=True, warp=True)
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                mon.autostart(Path(out["image"]).resolve(), run=True)
            finally:
                mon.resume()
        wait_for_text(s, "HELLO FROM ASM", timeout=45.0)
    finally:
        s.stop()


def test_crt_format_comes_from_the_output_extension(tmp_path):
    """A .crt output picks the cartridge path without an explicit --format."""
    out = tmp_path / "hello.crt"
    with patch("c64lib.packaging.build_cart", return_value={"crt": str(out)}) as bc:
        assert package_program(HELLO_ASM, out=out)["crt"] == str(out)
    bc.assert_called_once_with(Path(HELLO_ASM), out=out, cart_type="8k",
                               title=None)


def test_wrap_sends_a_native_source_down_the_launcher_path(tmp_path):
    out = tmp_path / "hello.crt"
    with patch("c64lib.packaging.wrap_prg", return_value={"crt": str(out)}) as wp:
        package_program(HELLO_ASM, out=out, wrap=True, cart_type="16k",
                        model="c64pal")
    wp.assert_called_once_with(Path(HELLO_ASM), out=out, cart_type="16k",
                               title=None, model="c64pal")


def test_a_prg_source_is_always_wrapped(tmp_path):
    prg = tmp_path / "game.prg"
    prg.write_bytes(b"\x01\x08rest")
    with patch("c64lib.packaging.wrap_prg", return_value={"crt": "g.crt"}) as wp:
        package_program(prg, fmt="crt")
    wp.assert_called_once_with(prg, out=prg.with_suffix(".crt"), cart_type="8k",
                               title=None, model="c64")


def test_wrap_without_a_cartridge_format_is_an_error(tmp_path):
    with pytest.raises(PackageError) as e:
        package_program(HELLO_ASM, out=tmp_path / "x.prg", wrap=True)
    assert "--format crt" in str(e.value)


def test_unknown_format_names_the_supported_ones(tmp_path):
    with pytest.raises(PackageError) as e:
        package_program(HELLO_ASM, out=tmp_path / "x.prg", fmt="tap")
    assert "'prg'" in str(e.value) and "'crt'" in str(e.value)
