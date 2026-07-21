"""Live disk and ROM tooling tests against real x64sc + c1541."""

import os
import shutil
from pathlib import Path

import pytest

from c64lib.basic import tokenize
from c64lib.disasm import disassemble
from c64lib.disk import create_image, get_file, list_files, put_file
from c64lib.romdoc import identify, rom_labels
from c64lib.session import Session
from c64lib.text import ascii_to_petscii
from tests.vice_helpers import wait_for_text

pytestmark = [
    pytest.mark.vice,
    pytest.mark.skipif(
        not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
        reason="x64sc not installed",
    ),
    pytest.mark.skipif(shutil.which("c1541") is None, reason="c1541 not installed"),
]


def _make_disk(tmp_path, image_name):
    prg = tokenize(Path("tests/programs/hello-basic/program.bas"), tmp_path / "d.prg", "4.0")
    img = create_image(tmp_path / image_name, label="work", disk_id="01")
    put_file(img, prg, "demo")
    return img, prg


def _load_and_run(s):
    with s.monitor() as mon:
        try:
            mon.keyboard_feed(ascii_to_petscii('LOAD"DEMO",8\nRUN\n'))
        finally:
            mon.resume()
    wait_for_text(s, "HELLO FROM BASIC", timeout=45.0)


@pytest.mark.parametrize("image_name,model", [("t.d64", "c64"), ("t.d81", "c64")])
def test_disk_attach_at_launch(tmp_path, monkeypatch, image_name, model):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    img, prg = _make_disk(tmp_path, image_name)
    s = Session.launch(model=model, name="dsk", headless=True, warp=True,
                       disk8=str(img))
    try:
        wait_for_text(s, "READY.")
        _load_and_run(s)
    finally:
        s.stop()
    # host round-trip: read the file back out and compare
    out = get_file(img, "demo", tmp_path / "back.prg")
    assert out.read_bytes() == prg.read_bytes()
    assert list_files(img)["files"][0]["name"] == "demo"


def test_disk_boot_mid_session(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    img, _ = _make_disk(tmp_path, "boot.d64")
    s = Session.launch(model="c64", name="boot", headless=True, warp=True)
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                mon.autostart(img.resolve(), run=True)
            finally:
                mon.resume()
        wait_for_text(s, "HELLO FROM BASIC", timeout=45.0)
    finally:
        s.stop()


def test_rom_identify_and_disasm(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model="c64", name="rom", headless=True, warp=True)
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                info = identify(mon)
                data = mon.memory_read(0xFFD2, 3)
            finally:
                mon.resume()
        assert info["basic"].endswith(".bin") and "4" in info["basic"]
        assert len(info["hashes"]["kernal"]) == 12
        lines = disassemble(data, 0xFFD2, rom_labels("4.0"))
        assert lines[0] == "CHROUT:"
        assert "jmp" in lines[1]
    finally:
        s.stop()


def test_dos_error_codes_via_ds(tmp_path, monkeypatch):
    """basic-internals.md claims DOPEN of a missing file yields DS=62
    FILE NOT FOUND — provoke it on a real attached image."""
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    img = create_image(tmp_path / "err.d64", label="err")
    s = Session.launch(model="c64", name="dos", headless=True, warp=True,
                       disk8=str(img))
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                mon.keyboard_feed(ascii_to_petscii('dopen#1,"nosuch"\nprint ds;ds$\n'))
            finally:
                mon.resume()
        text = wait_for_text(s, "FILE NOT FOUND", timeout=30.0)
        assert "62" in text
    finally:
        s.stop()
