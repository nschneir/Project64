#!/usr/bin/env python3
"""Run every art/table generator, in order, and fail on the first that fails.

One command regenerates every .inc the demo commits, so "is the committed art
still what the generator produces?" is a `git diff` rather than an argument.

Task 1 wires up gen_sprites.py; Tasks 2-5 each add their own generator to
GENERATORS as they land.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

GENERATORS = [
    "gen_sprites.py",           # sprites.inc  -- 16 rotation frames (Task 1)
]


def main() -> int:
    for name in GENERATORS:
        print(f"--- {name}")
        result = subprocess.run([sys.executable, str(HERE / name)])
        if result.returncode != 0:
            print(f"{name} failed with exit {result.returncode}", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
