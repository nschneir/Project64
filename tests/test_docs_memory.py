import os
import shutil
import struct
from pathlib import Path

import pytest

from c64lib.session import Session
from c64lib.text import ascii_to_petscii
from tests.vice_helpers import wait_for_text

REF = Path("skills/c64-development/references")


def test_docs_exist_and_state_vectors():
    mm = (REF / "memory-maps.md").read_text()
    for needle in ("FFFA", "FFFC", "FFFE", "0400-07E7", "D400", "DC00"):
        assert needle in mm
    zp = (REF / "zero-page.md").read_text()
    for needle in ("TXTTAB", "VARTAB", "2B/2C", "0277"):
        assert needle in zp


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
def test_zero_page_chain_and_vectors_live(session):
    s = session
    with s.monitor() as mon:
        try:
            mon.keyboard_feed(ascii_to_petscii('10 a=1\n'))
        finally:
            mon.resume()
    wait_for_text(s, "10 A=1")
    with s.monitor() as mon:
        try:
            zp = mon.memory_read(0x2B, 10)
            memsiz = mon.memory_read(0x37, 2)
            reset_vec = mon.memory_read(0xFFFC, 2)
        finally:
            mon.resume()
    txttab, vartab, arytab, strend, fretop = struct.unpack("<5H", zp)
    assert txttab == 0x0801                    # doc claim: TXTTAB = $0801
    assert txttab < vartab <= arytab <= strend <= fretop
    assert vartab - txttab > 5                 # our one-liner is in there
    assert struct.unpack("<H", memsiz)[0] == 0xA000   # doc claim: MEMSIZ
    reset = struct.unpack("<H", reset_vec)[0]
    assert 0xE000 <= reset <= 0xFFFF           # doc claim: KERNAL reset vector


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
def test_book_sourced_facts_live(session):
    """Assert the book-sourced C64 facts in the reference docs against a
    real running machine: jiffy clock location/direction, banking port
    default, RAM vectors, hardware vector targets, and the KERNAL
    jump-table's RAM-vector dispatch."""
    import time

    s = session
    with s.monitor() as mon:
        try:
            ti1 = mon.memory_read(0xA0, 3)
        finally:
            mon.resume()
    time.sleep(0.5)
    with s.monitor() as mon:
        try:
            ti2 = mon.memory_read(0xA0, 3)
            port = mon.memory_read(0x01, 1)
            cinv = mon.memory_read(0x0314, 2)
            vectors = mon.memory_read(0xFFFA, 6)
            open_jmp = mon.memory_read(0xFFC0, 3)
        finally:
            mon.resume()
    # TI at $A0-$A2, most-significant byte FIRST, ticking upward (doc: zero-page.md)
    t1 = (ti1[0] << 16) | (ti1[1] << 8) | ti1[2]
    t2 = (ti2[0] << 16) | (ti2[1] << 8) | ti2[2]
    assert t2 > t1, f"jiffy clock not ticking MSB-first at $A0: {ti1.hex()} -> {ti2.hex()}"
    # 6510 port default $37 (doc: zero-page.md)
    assert port == b"\x37"
    # CINV ($0314) = $EA31 (doc: zero-page.md, kernal-routines.md)
    assert struct.unpack("<H", cinv)[0] == 0xEA31
    # hardware vectors NMI/RESET/IRQ = FE43/FCE2/FF48 (doc: kernal-routines.md)
    nmi, reset, irq = struct.unpack("<3H", vectors)
    assert (nmi, reset, irq) == (0xFE43, 0xFCE2, 0xFF48)
    # KERNAL OPEN at $FFC0 dispatches through the RAM vector at $031A
    # (doc: zero-page.md low-memory table)
    assert open_jmp == bytes([0x6C, 0x1A, 0x03])


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
@pytest.mark.parametrize("model", ["c64", "c64pal"])
def test_user_zp_bytes_survive_basic_live(tmp_path, monkeypatch, model):
    """The bytes zero-page.md names as free for user ML pointers really do
    survive heavy BASIC activity."""
    import re

    section = (REF / "zero-page.md").read_text().split(
        "## Free zero page for user ML pointers")[1]
    row = re.search(r"\|\s*([0-9A-F]{2})-([0-9A-F]{2})\s*\|", section)
    assert row, "no $xx-$xx range row under the free-zero-page heading"
    lo, hi = int(row.group(1), 16), int(row.group(2), 16)
    claimed = list(range(lo, hi + 1))

    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model=model, name=f"zp-{model}", headless=True,
                       warp=True)
    try:
        wait_for_text(s, "READY.")
        sentinels = {a: ((0xA5 + i * 7) % 255) + 1
                     for i, a in enumerate(claimed)}
        with s.monitor() as mon:
            try:
                for a, v in sentinels.items():
                    mon.memory_write(a, bytes([v]))
            finally:
                mon.resume()
        exercise = ('10 for i=1 to 50: a=rnd(1)*100: next\n'
                    '20 a$="": for i=1 to 30: a$=a$+chr$(65+(i and 15)): next\n'
                    '30 for i=1 to 5: b$=a$+a$: next\n'
                    '40 print int(a); sqr(a)\n'
                    '50 get k$\n'
                    '60 print "ZPDONE"\n'
                    'run\n')
        with s.monitor() as mon:
            try:
                mon.keyboard_feed(ascii_to_petscii(exercise))
            finally:
                mon.resume()
        wait_for_text(s, "ZPDONE", timeout=60)
        import time as _t
        _t.sleep(2)
        with s.monitor() as mon:
            try:
                after = {a: mon.memory_read(a, 1)[0] for a in claimed}
            finally:
                mon.resume()
        clobbered = {f"${a:02x}": (sentinels[a], after[a])
                     for a in claimed if after[a] != sentinels[a]}
        assert not clobbered, f"doc-claimed ZP bytes clobbered: {clobbered}"
    finally:
        s.stop()


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
def test_current_key_cb_live(session):
    """zero-page.md's $CB claim: the KERNAL keyboard scan maintains the
    current key's matrix code at $CB, 64 = no key. Idle machine reads 64,
    and the `sty $cb` store exists in the KERNAL scan code (SCNKEY keeps
    the matrix index in Y)."""
    with session.monitor() as mon:
        try:
            cb = mon.memory_read(0xCB, 1)
            rom = mon.memory_read(0xE000, 0x2000)
        finally:
            mon.resume()
    assert cb == bytes([64]), f"idle $CB expected 64, got {cb[0]}"
    assert bytes([0x84, 0xCB]) in rom, "no `sty $cb` in KERNAL ROM?"
