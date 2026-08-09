#!/usr/bin/env python3
"""Turn the readable sprite sheet in tools/sprites.txt into the exact-width
sheets `c64 sprite encode` expects.

`c64 sprite encode` is the standard encoder and still does the encoding; what
it does not read is a *maintainable* sheet.  Its format has no names, no
comments, and background pixels are spaces, so every row's width is carried
by trailing whitespace that no editor shows and several strip.  Twenty-one
sprites is 441 rows of that.  So the art here is authored with a visible
background character and a name per shape, and this script emits the two
mode-specific sheets the encoder reads:

    python3 tools/gensprites.py tools/sprites.txt -o tools/
    python3 tools/gensprites.py tools/sprites.txt --check

Source legend (same in both modes; `.` is what the encoder wants as a space):

    .   transparent background
    #   the sprite's own colour ($D027+n)
    1   shared multicolour 1 ($D025)     -- multicolour shapes only
    2   shared multicolour 2 ($D026)     -- multicolour shapes only

A `name:` header starts a shape; `name:hires` or `name:multicolor` sets its
mode, and a bare `name:` takes the file's default (multicolour).  Rows are
right-padded with background to the mode's width and shapes are padded to 21
rows, so the art only has to be as wide and as tall as the shape really is.

The two emitted sheets keep source order within their mode, which is the
order `c64 sprite encode` numbers them in and the order sprites.s assigns
blocks in — so the printed manifest is the block map.
"""

from __future__ import annotations

import argparse
import os
import sys

ROWS = 21
WIDTH = {"hires": 24, "multicolor": 12}
# source glyph -> the character `c64 sprite encode` wants for it
EMIT = {".": " ", "#": "#", "1": ".", "2": "+"}
HIRES_OK = set(".#")
MC_OK = set(".#12")


def parse(path: str, default_mode: str) -> list[tuple[str, str, list[str]]]:
    shapes: list[tuple[str, str, list[str]]] = []
    name: str | None = None
    mode = default_mode
    rows: list[str] = []

    def flush() -> None:
        if name is not None:
            shapes.append((name, mode, rows))

    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n").rstrip()
            # `#` is both the comment marker and a legend character, so a
            # line only counts as a comment when it holds something the
            # legend does not -- an all-`#` row is art.
            if not line or (
                line.startswith("#")
                and not (len(line) >= 8 and set(line) <= MC_OK)
            ):
                continue
            # Art is only ever `.#12`, so any letter marks a header:
            # `fighter:hires`, `drone0:multicolor`, or a bare `drone0:`.
            if any(c.isalpha() for c in line):
                flush()
                head = line.strip().rstrip(":")
                name, _, suffix = head.partition(":")
                name = name.strip()
                mode = suffix.strip() or default_mode
                if mode not in WIDTH:
                    sys.exit(
                        f"{path}:{lineno}: unknown mode '{mode}' -- "
                        "use 'hires' or 'multicolor'"
                    )
                rows = []
                continue
            if name is None:
                sys.exit(f"{path}:{lineno}: art before any `name:` header")
            ok = HIRES_OK if mode == "hires" else MC_OK
            bad = set(line) - ok
            if bad:
                sys.exit(
                    f"{path}:{lineno}: '{name}' row {len(rows) + 1} has "
                    f"{sorted(bad)} -- legend is {''.join(sorted(ok))}"
                )
            if len(line) > WIDTH[mode]:
                sys.exit(
                    f"{path}:{lineno}: '{name}' row {len(rows) + 1} is "
                    f"{len(line)} wide, max {WIDTH[mode]} for {mode}"
                )
            if len(rows) >= ROWS:
                sys.exit(f"{path}:{lineno}: '{name}' has more than {ROWS} rows")
            rows.append(line)
    flush()
    return shapes


def check(path: str, shapes: list[tuple[str, str, list[str]]]) -> None:
    if not shapes:
        sys.exit(f"{path}: no shapes")
    names: set[str] = set()
    for name, _, rows in shapes:
        if name in names:
            sys.exit(f"{path}: '{name}' is defined twice")
        names.add(name)
        if not any("#" in r or "1" in r or "2" in r for r in rows):
            sys.exit(f"{path}: '{name}' is blank")


def render(shapes: list[tuple[str, str, list[str]]], mode: str) -> str:
    blocks = []
    for _, m, rows in shapes:
        if m != mode:
            continue
        w = WIDTH[mode]
        padded = [r.ljust(w, ".") for r in rows] + ["." * w] * (ROWS - len(rows))
        blocks.append("\n".join("".join(EMIT[c] for c in r) for r in padded))
    return "\n\n".join(blocks) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("-o", "--outdir", help="write the two generated sheets here")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--mode", default="multicolor", choices=sorted(WIDTH))
    args = ap.parse_args()

    shapes = parse(args.source, args.mode)
    check(args.source, shapes)

    hires = [s for s in shapes if s[1] == "hires"]
    mc = [s for s in shapes if s[1] == "multicolor"]
    for label, group in (("hires", hires), ("multicolor", mc)):
        for i, (name, *_) in enumerate(group):
            print(f"{label:>10} {i:>2}  {name}")
    if args.check:
        print(f"{args.source}: {len(shapes)} shapes, ok")
        return
    if not args.outdir:
        sys.exit("need -o OUTDIR (or --check)")
    for label, group in (("hires", hires), ("multicolor", mc)):
        if not group:
            continue
        path = os.path.join(args.outdir, f"sprites-{label}.gen.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render(shapes, label))
        print(f"wrote {path}: {len(group)} sprites")


if __name__ == "__main__":
    main()
