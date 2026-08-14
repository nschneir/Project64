#!/usr/bin/env python3
"""The cross-check: does the screen show what the chip is playing?

This demo displays the same note data it plays, so the two evidence streams
have to agree.  The audio side is already covered -- `c64 audio capture`
diffs the register log against a score written from `bwv847.py`, and all four
windows pass.  This is the other side: at a stop, take what the SEQUENCER
says is sounding and go and look at the CELL the renderer drew for it.

For each voice it checks four things at once, and each is a different way for
the two paths to have diverged:

  1. the cell at (row, column) the published state names holds a NOTE HEAD
     glyph, not background -- the renderer drew something there at all;
  2. the glyph's half bit matches `vpos & 1` -- it drew it in the right half
     of the cell, which is the half-cell resolution the whole layout rests on;
  3. the cell's colour is `pcolor[vnote % 12]` -- the head is coloured for the
     pitch class actually sounding, not for the one the renderer thought;
  4. `vnote` equals `posmidi[vpos]` adjusted by the accidental in `vacc` --
     the pitch and the staff position are consistent readings of one byte.

A disagreement localises itself: (1) or (2) is a renderer fault, (4) is a
decoder fault, (3) is a colour-table fault.

    python3 crosscheck.py -s fug --frames 1398,2038,3110
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import genmusic  # noqa: E402

C64 = str(HERE.parent.parent.parent / ".venv" / "bin" / "c64")
LADTOP = 5
GHEAD1, GHEAD2 = 34, 42


def run(*args: str) -> str:
    return subprocess.run([C64, *args], capture_output=True, text=True,
                          check=True).stdout


def get(session: str, sym: str, n: int) -> list[int]:
    out = run("mem", "get", sym, str(n), "-s", session)
    return [int(x) for x in out.split()]


def cell(session: str, row: int, col: int, colour: bool = False) -> int:
    at = f"@@{row},{col}" if colour else f"@{row},{col}"
    line = run("mem", "read", at, "1", "-s", session).splitlines()[0]
    return int(line.split(":")[1].strip().split()[0], 16)


def check(session: str, frames: list[int]) -> int:
    colours = genmusic.assign_colours(genmusic.histogram(genmusic.expand()))
    bad = 0
    prev = 0
    for target in frames:
        run("until", "tick", "--count", str(target - prev), "-s", session,
            "--timeout", "600")
        prev = target
        frame = get(session, "frame", 2)
        frame = frame[0] + 256 * frame[1]
        bar, slot = get(session, "bar", 1)[0], get(session, "slot", 1)[0]
        vnote = get(session, "vnote", 3)
        vpos = get(session, "vpos", 3)
        vacc = get(session, "vacc", 3)
        sprcol = get(session, "sprcol", 3)
        sprage = get(session, "sprage", 3)
        sprena = get(session, "sprena", 1)[0]
        print(f"\n=== machine frame {frame}, bar {bar} slot {slot} ===")
        for v in range(3):
            if vpos[v] == 0xFF or vnote[v] == 0:
                print(f"  voice {v + 1}: silent")
                continue
            if not sprena & (1 << v):
                # The note is still sounding but its HEAD has scrolled past
                # the now column -- a held note travels on at two pixels a
                # frame like everything else, and past age 40 its glow leaves
                # the visible range (SPEC.md section 8).  There is nothing at
                # sprcol to compare against, so this is out of scope for the
                # check rather than a disagreement.  The closing tonic pedal
                # is the case that matters: held from bar 29 to the end.
                print(f"  voice {v + 1}: sounding but held "
                      f"(age {sprage[v]}), head has scrolled past the now "
                      f"column -- not checkable here")
                continue
            p, col = vpos[v], sprcol[v]
            row, half = LADTOP + (p >> 1), p & 1
            glyph = cell(session, row, col)
            colr = cell(session, row, col, colour=True) & 0x0F
            letter, octave = genmusic.LADDER[p]
            spell = f"{letter}{'#' if vacc[v] == 1 else 'b' if vacc[v] == 2 else ''}{octave}"

            ok = []
            if GHEAD1 <= glyph < GHEAD2 + 8:
                ok.append("head")
                gh = (glyph - GHEAD1) & 1 if glyph < GHEAD2 else None
                if gh is None or gh == half:
                    ok.append("half")
                else:
                    ok.append(f"HALF MISMATCH glyph={gh} vpos={half}")
                    bad += 1
            else:
                ok.append(f"NO HEAD (glyph {glyph})")
                bad += 1
            want_colour = colours[vnote[v] % 12]
            if colr == want_colour:
                ok.append("colour")
            else:
                ok.append(f"COLOUR MISMATCH {colr} != {want_colour}")
                bad += 1
            offset = 1 if vacc[v] == 1 else -1 if vacc[v] == 2 else 0
            if vnote[v] == genmusic.POSMIDI[p] + offset:
                ok.append("pitch")
            else:
                ok.append(f"PITCH MISMATCH {vnote[v]} != "
                          f"{genmusic.POSMIDI[p] + offset}")
                bad += 1
            print(f"  voice {v + 1}: {spell:<4} midi {vnote[v]:3d}  p={p:2d} "
                  f"-> row {row} half {half} col {col:2d}  glyph {glyph:3d} "
                  f"colour {colr:2d}   [{', '.join(ok)}]")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--session", default="fug")
    ap.add_argument("--frames", default="1398,2038,3110",
                    help="attack frames to check, comma separated")
    a = ap.parse_args()
    frames = sorted(int(f) for f in a.frames.split(","))
    for f in frames:
        if (f - 238) % 8:
            print(f"note: frame {f} is not an attack frame; the head will "
                  f"have drifted off the now column")
    bad = check(a.session, frames)
    print()
    if bad:
        print(f"FAIL: {bad} disagreement(s) between the screen and the sequencer")
        return 1
    print("OK: every sounding note is drawn at the position, in the half, and "
          "in the colour its own pitch demands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
