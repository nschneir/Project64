"""Live symbolic-debug-loop test: breakpoint in hello-asm, step, inspect, wait."""

import json
import os
import shutil
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from c64lib.build import build_asm
from c64lib.cli import main as cli_main
from c64lib.ops import run_until, wait_for_break
from c64lib.session import Session
from c64lib.symbols import load_labels
from tests.vice_helpers import wait_for_text

pytestmark = [
    pytest.mark.vice,
    pytest.mark.skipif(
        not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
        reason="x64sc not installed",
    ),
    pytest.mark.skipif(
        shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
        reason="cc65 not installed",
    ),
]


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s = Session.launch(model="c64", name="dbgtest", headless=True, warp=True)
    wait_for_text(s, "READY.")
    yield s
    s.stop()


def test_symbolic_debug_loop(session, tmp_path):
    # build with -g: local labels must be in the label file
    res = build_asm(Path("tests/programs/hello-asm/program.s"), out_prg=tmp_path / "dbg.prg")
    labels = load_labels(res.labels)
    assert {"start", "loop", "msg"} <= set(labels)
    session.set_labels_path(str(res.labels))

    # breakpoint at 'start', then autostart (checkpoints survive autostart)
    with session.monitor() as mon:
        try:
            ck = mon.checkpoint_set(labels["start"])
            mon.autostart(res.prg.resolve(), run=True)
        finally:
            mon.resume()

    # wait for the hit, inspect, step, read memory symbolically
    mon = session.monitor()
    try:
        hit = next((c for c in mon.checkpoint_list() if c.hit), None)
        if hit is None:
            mon.resume()
            info = mon.wait_for_stop(timeout=45.0)
            assert info is not None, "breakpoint never hit"
            assert info.checkpoint == ck.number
        regs = mon.registers()
        assert regs["PC"] == labels["start"]

        regs = mon.step(2)                       # ldx #0 ; lda msg,x
        assert regs["PC"] == labels["start"] + 5

        msg = mon.memory_read(labels["msg"], 14)
        assert msg == b"HELLO FROM ASM"

        mon.checkpoint_delete(ck.number)
        mon.resume()
    finally:
        mon.close()

    # program completes after resume
    wait_for_text(session, "HELLO FROM ASM", timeout=30.0)


def test_watchpoint_on_screen_ram(session, tmp_path):
    res = build_asm(Path("tests/programs/hello-asm/program.s"), out_prg=tmp_path / "w.prg")
    from c64lib.protocol import CP_STORE

    with session.monitor() as mon:
        try:
            ck = mon.checkpoint_set(0x8000, 0x83E7, op=CP_STORE)
            mon.autostart(res.prg.resolve(), run=True)
        finally:
            mon.resume()

    mon = session.monitor()
    try:
        hit = next((c for c in mon.checkpoint_list() if c.hit), None)
        if hit is None:
            mon.resume()
            info = mon.wait_for_stop(timeout=45.0)
            assert info is not None, "watchpoint never hit"
        mon.checkpoint_delete(ck.number)
        mon.resume()
    finally:
        mon.close()


def test_mem_symbol_roundtrip_live(session, tmp_path):
    """cli.md promises mem ADDR takes a symbol; prove it against a live C64."""
    res = build_asm(Path("tests/programs/hello-asm/program.s"),
                    out_prg=tmp_path / "m.prg")
    session.set_labels_path(str(res.labels))
    r = CliRunner().invoke(cli_main, ["--json", "mem", "write", "msg", "$2A"])
    assert r.exit_code == 0, r.output
    r = CliRunner().invoke(cli_main, ["--json", "mem", "read", "msg", "1"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["hex"] == "2a"


HOT_LOOP = """\
        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000
        .segment "CODE"
start:
mainloop:
        inc     $033A
        jmp     mainloop
"""


def test_checkpoint_halt_reliability_under_warp(session, tmp_path):
    """Regression for the demo-04 dogfooding failure (2026-07-10): under
    --warp --headless, wait --break registered the hit but did not halt —
    the connect-stop/resume event race in ops.wait_for_break swallowed
    genuine checkpoint stops. Hammer it: every trial must halt."""
    src = tmp_path / "hot.s"
    src.write_text(HOT_LOOP)
    res = build_asm(src)
    labels = load_labels(res.labels)
    with session.monitor() as mon:
        try:
            mon.autostart(res.prg.resolve(), run=True)
        finally:
            mon.resume()
    time.sleep(3.0)  # autostart LOAD+RUN takes a few emulated seconds

    with session.monitor() as mon:
        ck = mon.checkpoint_set(labels["mainloop"])
        mon.resume()
    try:
        for i in range(20):
            out = wait_for_break(session, timeout=10.0)
            assert out["fired"] == "break", f"trial {i}: wait --break timed out"
            assert out["checkpoint"] == ck.number, f"trial {i}: wrong checkpoint"
            with session.monitor() as mon:
                mon.resume()  # run to the next hit
    finally:
        with session.monitor() as mon:
            mon.checkpoint_delete(ck.number)
            mon.resume()


def test_until_reliability_and_count_under_warp(session, tmp_path):
    """run_until must halt every time under warp, and --count must advance
    exactly N loop iterations (WS2+WS3)."""
    src = tmp_path / "hot2.s"
    src.write_text(HOT_LOOP)
    res = build_asm(src)
    labels = load_labels(res.labels)
    with session.monitor() as mon:
        try:
            mon.autostart(res.prg.resolve(), run=True)
        finally:
            mon.resume()
    time.sleep(3.0)

    for i in range(20):
        out = run_until(session, labels["mainloop"], timeout=10.0)
        assert out["registers"] is not None, f"until trial {i} timed out"
        assert out["registers"]["PC"] == labels["mainloop"], f"until trial {i}"

    # count semantics, end to end: the loop body is `inc $033A ; jmp mainloop`,
    # so the counter advances by exactly N between two stops N frames apart.
    # The reads happen over SEPARATE monitor connections — the session daemon
    # is what makes this exact (spec acceptance; pre-daemon this read +158).
    with session.monitor() as mon:
        c0 = mon.memory_read(0x033A, 1)[0]
        mon.release()                    # parked; must stay parked
    out = run_until(session, labels["mainloop"], timeout=15.0, count=5)
    assert out["registers"] is not None and out["reached"] == 5
    with session.monitor() as mon:
        c1 = mon.memory_read(0x033A, 1)[0]
        mon.release()
    assert (c1 - c0) % 256 == 5
    with session.monitor() as mon:
        mon.resume()                     # leave the machine running
