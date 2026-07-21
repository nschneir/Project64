import os
import shutil
import struct
from pathlib import Path

import pytest

from c64lib.session import Session
from c64lib.text import ascii_to_petscii
from tests.vice_helpers import wait_for_text

REF = Path("skills/pet-development/references")


def test_docs_exist_and_state_vectors():
    mm = (REF / "memory-maps.md").read_text()
    for needle in ("FFFA", "FFFC", "FFFE", "8000-83E7", "E810", "E880"):
        assert needle in mm
    zp = (REF / "zero-page.md").read_text()
    for needle in ("TXTTAB", "VARTAB", "28/29", "026F"):
        assert needle in zp


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
def test_zero_page_chain_and_vectors_live(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model="c64", name="zp", headless=True, warp=True)
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                mon.keyboard_feed(ascii_to_petscii('10 a=1\n'))
            finally:
                mon.resume()
        wait_for_text(s, "10 A=1")
        with s.monitor() as mon:
            try:
                zp = mon.memory_read(0x28, 10)
                reset_vec = mon.memory_read(0xFFFC, 2)
            finally:
                mon.resume()
        txttab, vartab, arytab, strend, fretop = struct.unpack("<5H", zp)
        assert txttab == 0x0401                    # doc claim: TXTTAB = $0401
        assert txttab < vartab <= arytab <= strend <= fretop
        assert vartab - txttab > 5                 # our one-liner is in there
        reset = struct.unpack("<H", reset_vec)[0]
        assert 0xF000 <= reset <= 0xFFFF           # doc claim: kernal reset vector
    finally:
        s.stop()


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
def test_book_sourced_facts_live(tmp_path, monkeypatch):
    """Assert the West-sourced BASIC 4 facts in the reference docs against a
    real running machine: jiffy clock location/direction, IRQ RAM vector,
    hardware vector targets, and a kernal jump-table target."""
    import time

    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model="c64", name="facts", headless=True, warp=True)
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                ti1 = mon.memory_read(0x8D, 3)
            finally:
                mon.resume()
        time.sleep(0.5)
        with s.monitor() as mon:
            try:
                ti2 = mon.memory_read(0x8D, 3)
                irq_ram = mon.memory_read(0x90, 2)
                vectors = mon.memory_read(0xFFFA, 6)
                open_jmp = mon.memory_read(0xFFC0, 3)
            finally:
                mon.resume()
        # TI at $8D-$8F, most-significant byte FIRST, ticking upward (doc: zero-page.md)
        t1 = (ti1[0] << 16) | (ti1[1] << 8) | ti1[2]
        t2 = (ti2[0] << 16) | (ti2[1] << 8) | ti2[2]
        assert t2 > t1, f"jiffy clock not ticking MSB-first at $8D: {ti1.hex()} -> {ti2.hex()}"
        # IRQ RAM vector ($90) = $E455 on BASIC 4 (doc: zero-page.md, rom-routines.md)
        assert struct.unpack("<H", irq_ram)[0] == 0xE455
        # hardware vectors NMI/RESET/IRQ = FD49/FD16/E442 on BASIC 4 (doc: rom-routines.md)
        nmi, reset, irq = struct.unpack("<3H", vectors)
        assert (nmi, reset, irq) == (0xFD49, 0xFD16, 0xE442)
        # kernal OPEN at $FFC0 is JMP $F560 on BASIC 4 (doc: rom-routines.md)
        assert open_jmp == bytes([0x4C, 0x60, 0xF5])
    finally:
        s.stop()


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
def test_basic1_jiffy_clock_location_live(tmp_path, monkeypatch):
    """BASIC 1 (pet2001) keeps TI at $0200-$0202, not $8D (doc: zero-page.md)."""
    import time

    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model="pet2001", name="b1", headless=True, warp=True)
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                ti1 = mon.memory_read(0x0200, 3)
            finally:
                mon.resume()
        time.sleep(0.5)
        with s.monitor() as mon:
            try:
                ti2 = mon.memory_read(0x0200, 3)
            finally:
                mon.resume()
        t1 = (ti1[0] << 16) | (ti1[1] << 8) | ti1[2]
        t2 = (ti2[0] << 16) | (ti2[1] << 8) | ti2[2]
        assert t2 > t1, f"BASIC 1 jiffy clock not ticking at $0200: {ti1.hex()} -> {ti2.hex()}"
    finally:
        s.stop()


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
@pytest.mark.parametrize("model", ["c64", "pet8032"])
def test_user_zp_bytes_survive_basic_live(tmp_path, monkeypatch, model):
    """The bytes zero-page.md names as free for user ML pointers really do
    survive heavy BASIC activity."""
    import re

    section = (REF / "zero-page.md").read_text().split(
        "## Free zero page for user ML pointers")[1]
    row = re.search(r"\|\s*([0-9A-F]{2})-([0-9A-F]{2})\s*\|", section)
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
@pytest.mark.parametrize("model,sta97,table_load", [
    # zero-page.md's $97 claim: BASIC 4's scanner stores decoded PETSCII
    # (the byte before `sta $97` comes off the decode-table load path at
    # $E73E); BASIC 2's stores the raw matrix index (table at $E6F7 feeds
    # only the keyboard buffer). Pin the documented scanner addresses so
    # ROM-set drift can't silently invalidate the doc.
    ("c64", 0xE556, (0xBD, 0x3E, 0xE7)),   # lda $E73E,x in the scan loop
    ("pet3032", 0xE6C8, (0xBD, 0xF7, 0xE6)),   # lda $E6F7,x AFTER the store
])
def test_keydown_97_scanner_addresses_live(tmp_path, monkeypatch, model,
                                           sta97, table_load):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model=model, name=f"kd-{model}", headless=True,
                       warp=True)
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                assert mon.memory_read(sta97, 2) == b"\x85\x97", \
                    f"{model}: no `sta $97` at ${sta97:04X} — ROM changed?"
                rom = mon.memory_read(0xE000, 0x1000)
            finally:
                mon.resume()
        assert bytes(table_load) in rom, \
            f"{model}: decode-table load {table_load} not in editor ROM"
    finally:
        s.stop()
