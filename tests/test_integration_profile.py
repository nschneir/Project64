"""Live proof: c64 profile measures a hand-computable routine exactly.

The reference routine costs 507 cycles: ldx#100 (2) + 99 taken dex/bne
iterations (99*5) + the final dex/bne fall-through (4) + rts (6).
The program blanks the screen ($D011 bit 4 off) so no badlines land in
the window, and profile masks IRQs by default, so the count is exact.
"""
import json
import os
import shutil

import pytest
from click.testing import CliRunner

from c64lib.cli import main

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

SRC = """\
        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  sei
        lda     #$0b            ; screen off: no badline DMA in the window
        sta     $d011
        lda     #1
        sta     $03f0           ; ready marker for the test
idle:   jmp     idle

prof:   ldx     #100
ploop:  dex
        bne     ploop
        rts
"""


def _boot(tmp_path, name, loop_count):
    """Assemble+run the reference program with `ldx #loop_count`, then wait
    for its ready marker. Returns once the machine is parked in `idle`."""
    src = tmp_path / name
    src.write_text(SRC.replace("ldx     #100", f"ldx     #{loop_count}"))
    r = CliRunner().invoke(main, ["run", str(src)])
    assert r.exit_code == 0, r.output
    r = CliRunner().invoke(main, ["wait", "--mem", "$03F0=1", "--timeout", "30"])
    assert r.exit_code == 0, r.output


def _profile(*args):
    r = CliRunner().invoke(main, ["--json", "profile", "prof", *args])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)


def test_profile_measures_a_known_cost_routine(session, tmp_path):
    _boot(tmp_path, "prof.s", 100)
    out = _profile()
    assert out["irq_masked"] is True
    assert out["cycles"] == 507, out


def test_profile_samples_prices_every_arrival_live(session, tmp_path):
    """The sample loop runs inside the daemon and re-arms the fake-JSR
    bracket in place between arrivals — stack, SP, I flag, PC and the CIA
    cascade. Only a real chip model can prove the re-arm: a fixed-cost
    routine sampled five times must be the same hand-computed 507 every
    time, with min == mean == max and no drift down the run."""
    _boot(tmp_path, "profsamp.s", 100)
    out = _profile("--samples", "5")
    assert out["samples"] == [507] * 5, out
    assert out["min"] == 507 and out["max"] == 507 and out["mean"] == 507.0
    assert out["count"] == 5
    # No single number above one sample; `cycles` survives at --samples 1.
    assert "cycles" not in out
    assert _profile("--samples", "1")["cycles"] == 507


def test_profile_is_repeatable_and_scales_with_the_loop_count(session, tmp_path):
    """Same routine three times = the same number (a cycle counter that
    drifts is worthless), and a 10x smaller loop costs the hand-computed
    57 cycles: ldx#10 (2) + 9*5 + 4 + rts (6)."""
    _boot(tmp_path, "prof3.s", 100)
    assert [_profile()["cycles"] for _ in range(3)] == [507, 507, 507]
    _boot(tmp_path, "prof10.s", 10)
    assert _profile()["cycles"] == 57
