#!/usr/bin/env python3
"""Run every art/table generator, in order, and fail on the first that fails.

One command regenerates every .inc the demo commits, so "is the committed art
still what the generator produces?" is a `git status` rather than an argument:

    python3 demos/amiga_ball/tools/generate.py
    git status --short demos/amiga_ball/

A clean tree after that pair is the whole claim -- the committed .byte rows are
the generators' current output and not a snapshot of some earlier version of the
maths.  A generator dropped from the list below cannot make that claim, and its
.inc drifts silently until someone reads the pixels: `sound.inc` was in exactly
that position when Task 5 landed, which is why the list is now the complete one
and why a new generator has to be added here as well as written.

Order is the order the .inc files matter in, which is the order they are
included by amiga_ball.s -- sprites before shadow, because sprites.inc is linked
first into the SPRITES area so that its first block is $2800/64 = 160 and
shadow.inc's is 224.  Nothing here reads another generator's output, so the
order is documentation rather than a dependency; it stays in this shape so a
failure part-way through leaves an obvious "how far did it get".

Failure is loud and immediate: the first non-zero exit stops the run and is
returned as this script's own exit status, rather than being reported at the end
after four more generators have written files against a broken assumption.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

GENERATORS = [
    "gen_sprites.py",           # sprites.inc              16 rotation frames
    "gen_room.py",              # chars.inc + screen.inc   charset and the room
    "gen_bounce.py",            # bounce.inc               the 8.8 bounce table
    "gen_shadow.py",            # shadow.inc               4 shadow shapes
    "gen_sound.py",             # sound.inc                2 cutoff sweeps
]


def main() -> int:
    for name in GENERATORS:
        script = HERE / name
        if not script.is_file():
            print(f"missing generator: {script}", file=sys.stderr)
            return 1
        # flush=True on every banner: this script's stdout is block-buffered
        # when the run is piped, but the children write to the same pipe
        # unbuffered, so without the flush the five banners arrive after all
        # five generators' output and say nothing about which one printed what.
        print(f"--- {name}", flush=True)
        result = subprocess.run([sys.executable, str(script)])
        if result.returncode != 0:
            print(f"{name} failed with exit {result.returncode}", file=sys.stderr)
            return result.returncode
    print(f"--- {len(GENERATORS)} generators, all clean", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
