#!/usr/bin/env python3
"""Count lit pixels in the 1812 demo's bitmap, from a `c64 mem read` dump.

The prompt's "nothing is ever cleared" proof has to be counted off a dump,
not judged by eye, and the accumulation claim is about the *total* — so this
reads the 8000 bytes of $2000-$3F3F and reports how many multicolour pixels
are non-background, plus a checksum that pins a canvas byte for byte.

    c64 mem read '$2000' 8000 --json | python3 tools/litcount.py
    c64 mem read '$2000' 8000 --json | python3 tools/litcount.py --rows
    c64 mem read '$2000' 8000 --json | python3 tools/litcount.py --sample 64

--rows    print the lit extent (first and last lit multicolour x) per row,
          which is how a fill bug shows itself as a truncated shape.
--sample  print N bitmap addresses that are lit, as `addr=value` pairs, for
          the "still lit later" persistence check.

Stdlib only.  Reads the dump on stdin so it composes with the CLI.
"""

from __future__ import annotations

import json
import sys

BITMAP = 0x2000
ROWS = 200
CELLS = 40


def load(stream) -> list[int]:
    """Accept `c64 mem read --json` output, or a plain hex dump."""
    text = stream.read()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        out = []
        for line in text.splitlines():
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            body = line.split(":", 1)[1]
            for tok in body.split():
                if len(tok) == 2:
                    try:
                        out.append(int(tok, 16))
                    except ValueError:
                        break
        return out
    for key in ("bytes", "values", "data"):
        if key in obj:
            return list(obj[key])
    raise SystemExit(f"no byte array in the JSON payload (keys: {sorted(obj)})")


def addr_of(y: int, cell: int) -> int:
    """Multicolour bitmap byte for pixel row y, cell column `cell`."""
    return BITMAP + (y & 248) * 40 + (y & 7) + 8 * cell


def lit_pixels(b: int) -> int:
    """Non-background multicolour pixels in one byte (bit-pair != 00)."""
    return sum(1 for s in (0, 2, 4, 6) if (b >> s) & 3)


def main(argv: list[str]) -> int:
    data = load(sys.stdin)
    if len(data) < 8000:
        print(f"warning: only {len(data)} bytes, expected 8000", file=sys.stderr)

    def byte_at(y: int, cell: int) -> int:
        i = addr_of(y, cell) - BITMAP
        return data[i] if 0 <= i < len(data) else 0

    total = sum(lit_pixels(v) for v in data[:8000])
    checksum = 0
    for i, v in enumerate(data[:8000]):
        checksum = ((checksum * 33) ^ v) & 0xFFFFFFFF

    if "--rows" in argv:
        for y in range(ROWS):
            first = last = None
            for cell in range(CELLS):
                v = byte_at(y, cell)
                for s, px in ((6, 0), (4, 1), (2, 2), (0, 3)):
                    if (v >> s) & 3:
                        x = cell * 4 + px
                        if first is None:
                            first = x
                        last = x
            if first is not None and last is not None:
                print(f"row {y:3d}: x {first:3d}..{last:3d}  width {last - first + 1}")
        return 0

    if "--sample" in argv:
        n = int(argv[argv.index("--sample") + 1])
        shown = 0
        step = max(1, 8000 // max(1, n * 4))
        for i in range(0, 8000, step):
            if shown >= n:
                break
            if data[i]:
                print(f"${BITMAP + i:04x}={data[i]:02x}")
                shown += 1
        return 0

    print(f"lit={total} checksum={checksum:08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
