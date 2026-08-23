import os
import shutil
import struct
from pathlib import Path

import pytest

from c64lib.session import Session
from c64lib.text import ascii_to_petscii
from tests.vice_helpers import timeout_scale, wait_for_text

REF = Path("skills/c64-development/references")


def test_docs_exist_and_state_vectors():
    mm = (REF / "memory-maps.md").read_text(encoding="utf-8")
    for needle in ("FFFA", "FFFC", "FFFE", "0400-07E7", "D400", "DC00"):
        assert needle in mm
    zp = (REF / "zero-page.md").read_text(encoding="utf-8")
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

    section = (REF / "zero-page.md").read_text(encoding="utf-8").split(
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


#: A program that owns the machine: no ROM calls, no return to BASIC, and no
#: zero page of its own — but interrupts left enabled, so the KERNAL's jiffy
#: update, keyboard scan and cursor blink all keep running over the seeded
#: bytes. The GO byte lets the harness seed them before the clock starts.
_OWNED_MACHINE_ASM = """\
JIFFY   = $A2
GO      = $C001
DONE    = $C000

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #0
        sta     DONE
        sta     count
        sta     count+1
        sta     GO
wgo:    lda     GO
        beq     wgo
loop:   lda     JIFFY
tick:   cmp     JIFFY
        beq     tick
        inc     count
        bne     nohi
        inc     count+1
nohi:   lda     count+1
        cmp     #$02                    ; 600 frames = $0258
        bcc     loop
        bne     fin
        lda     count
        cmp     #$58
        bcc     loop
fin:    lda     #$5A
        sta     DONE
hold:   jmp     hold
count:  .res    2
"""

#: Bytes the KERNAL's own interrupt handler maintains every frame. They are
#: not free on an owned machine either, and a row claiming one would be a
#: doc bug this test refuses rather than a measurement it re-runs.
_IRQ_OWNED = {0xA0, 0xA1, 0xA2, 0xC5, 0xC6, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF}


def _owned_machine_claims() -> list[int]:
    """The addresses the owned-machine table claims, parsed from the doc so
    the two cannot drift. Each row states its own byte count, which is
    checked against its range — a table that miscounts is a doc bug."""
    import re

    text = (REF / "zero-page.md").read_text(encoding="utf-8")
    section = text.split("## Free zero page once your program owns the machine")[1]
    section = section.split("\n## ")[0]
    claimed: list[int] = []
    for row in re.finditer(
            r"^\|\s*([0-9A-F]{2})(?:-([0-9A-F]{2}))?\s*\|\s*(\d+)\s*\|",
            section, re.M):
        lo = int(row.group(1), 16)
        hi = int(row.group(2), 16) if row.group(2) else lo
        span = list(range(lo, hi + 1))
        assert len(span) == int(row.group(3)), (
            f"row ${lo:02X}-${hi:02X} says {row.group(3)} bytes, spans {len(span)}")
        claimed += span
    assert claimed, "no address rows under the owned-machine heading"
    return claimed


def test_owned_machine_table_excludes_the_irq_bytes():
    """The KERNAL IRQ runs whatever else the program owns, so the bytes it
    maintains can never appear here — a cheap guard that costs no emulator."""
    stolen = sorted(_IRQ_OWNED.intersection(_owned_machine_claims()))
    assert not stolen, ("the owned-machine table claims bytes the KERNAL IRQ "
                        f"maintains: {[f'${a:02x}' for a in stolen]}")


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
@pytest.mark.parametrize("model", ["c64", "c64pal"])
def test_user_zp_bytes_survive_owned_machine_live(tmp_path, monkeypatch, model):
    """The table's premise, measured rather than reasoned: with no BASIC
    running and no ROM routine called, far more of the zero page is free than
    the under-BASIC table admits — and the KERNAL's interrupt handler, which
    keeps running, is the thing that decides how much."""
    import time as _t

    from c64lib.build import build_asm

    claimed = _owned_machine_claims()
    src = tmp_path / "zpown.s"
    src.write_text(_OWNED_MACHINE_ASM, encoding="utf-8")
    prg = Path(build_asm(src).prg).resolve()

    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model=model, name=f"zpown-{model}", headless=True,
                       warp=True)
    try:
        wait_for_text(s, "READY.")
        with s.monitor() as mon:
            try:
                mon.autostart(prg, run=True)
            finally:
                mon.resume()
        _wait_byte(s, 0xC000, 0x00, "the program never reached its GO spin")

        sentinels = {a: ((0xA5 + i * 7) % 255) + 1
                     for i, a in enumerate(claimed)}
        with s.monitor() as mon:
            try:
                for a, v in sentinels.items():
                    mon.memory_write(a, bytes([v]))
                mon.memory_write(0xC001, b"\x01")        # release the clock
            finally:
                mon.resume()
        _t.sleep(1.0)
        with s.monitor() as mon:                          # give the scan work
            try:
                mon.keyboard_feed(ascii_to_petscii("abc\n"))
            finally:
                mon.resume()
        _wait_byte(s, 0xC000, 0x5A, "the program never reported 600 frames")

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


def _wait_byte(s, addr: int, want: int, message: str, timeout: float = 60.0):
    import time as _t

    deadline = _t.monotonic() + timeout * timeout_scale()
    while _t.monotonic() < deadline:
        with s.monitor() as mon:
            try:
                got = mon.memory_read(addr, 1)[0]
            finally:
                mon.resume()
        if got == want:
            return
        _t.sleep(0.25)
    raise AssertionError(message)


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
