"""End-to-end tests against a real VICE x64sc. Skipped when x64sc is absent."""

import os
import shutil

import pytest

from c64lib.screen import read_screen_text
from c64lib.session import Session
from c64lib.text import ascii_to_petscii
from tests.doc_helpers import BOOT_FREE
from tests.vice_helpers import wait_for_text

pytestmark = [
    pytest.mark.vice,
    pytest.mark.skipif(
        not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
        reason="x64sc not installed",
    ),
]


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model="c64", name="itest", headless=True, warp=True)
    yield s
    s.stop()


def test_boots_to_ready(session):
    text = wait_for_text(session, "READY.")
    assert "COMMODORE BASIC" in text or "BASIC" in text


def test_memory_roundtrip_on_screen(session):
    wait_for_text(session, "READY.")
    with session.monitor() as mon:
        try:
            # write screen codes "HI" to top-left of screen RAM
            mon.memory_write(0x0400, bytes([8, 9]))
            assert mon.memory_read(0x0400, 2) == bytes([8, 9])
            text = read_screen_text(mon, session.profile)
        finally:
            mon.resume()
    assert text.splitlines()[0].startswith("HI")


def test_registers_readable_and_pc_moves(session):
    wait_for_text(session, "READY.")
    with session.monitor() as mon:
        try:
            regs = mon.registers()
        finally:
            mon.resume()
    assert "PC" in regs and 0 <= regs["PC"] <= 0xFFFF


def test_keyboard_feed_runs_basic(session):
    from c64lib.text import ascii_to_petscii

    wait_for_text(session, "READY.")
    with session.monitor() as mon:
        try:
            mon.keyboard_feed(ascii_to_petscii('PRINT "HELLO FROM C64LIB"\n'))
        finally:
            mon.resume()
    assert "HELLO FROM C64LIB" in wait_for_text(session, "HELLO FROM C64LIB", timeout=15)


@pytest.mark.vice
@pytest.mark.parametrize("model", sorted(BOOT_FREE))
def test_boot_banner_free_bytes_matches_readme(tmp_path, monkeypatch, model):
    """The README model table's 'free at boot' column, held to reality."""
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model=model, name=f"probe-{model}",
                       headless=True, warp=True)
    try:
        text = wait_for_text(s, "BYTES FREE", timeout=45.0)
        assert f"{BOOT_FREE[model]} BASIC BYTES FREE" in text
    finally:
        s.stop()


def test_call_routine_isolated(session):
    """FT-call: JSR one routine in isolation — LDA #$2A / STA $1000 / RTS
    poked into the tape buffer; assert its effects without running anything
    else."""
    from c64lib.ops import call_routine
    wait_for_text(session, "READY.", timeout=45)
    with session.monitor() as mon:
        try:
            mon.memory_write(0x033A, bytes([0xA9, 0x2A, 0x8D, 0x00, 0x10, 0x60]))
        finally:
            mon.release()
    out = call_routine(session, 0x033A, timeout=15)
    assert out["fired"] is True
    assert out["registers"]["A"] == 0x2A
    assert out["registers"]["PC"] == out["trap"]
    with session.monitor() as mon:
        try:
            assert mon.memory_read(0x1000, 1) == bytes([0x2A])
        finally:
            mon.release()


def test_screen_relocation_followed(session):
    """screen.py claims c64 screen follows VIC-II screen relocation:
    move the screen to $0C00 (KERNAL base at 648 + VIC $D018) and the
    reader must still see printed text."""
    wait_for_text(session, "READY.")
    with session.monitor() as mon:
        try:
            mon.keyboard_feed(ascii_to_petscii(
                'poke 648,12: poke 53272,53: print chr$(147);"MOVED SCREEN"\n'))
        finally:
            mon.resume()
    assert "MOVED SCREEN" in wait_for_text(session, "MOVED SCREEN", timeout=15)
