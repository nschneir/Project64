#!/usr/bin/env python3
"""mazes.txt (ASCII art, left half only) -> mazes.inc (nibble-packed rows).

The four playfields are left-right symmetric, so only columns 0-13 are
authored; the full 28-wide row is `left + reversed(left)`.  Two tiles pack
into one byte (high nibble = even column), so a row is 7 bytes and a maze
is 154.

Run with --check to validate only, --print to dump the full mazes.

Legend
    #  wall                  .  dot
    o  energizer             ' ' empty passage (no dot)
    ^  dot, no upward turn   T  tunnel passage (slow zone, no dot)
    -  ghost-house door      =  ghost-house interior

Validation is the point of this script: a maze with an unreachable dot or a
broken tunnel is a bug you would otherwise find by playing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# tile codes, matching the equates in maze.s
T_EMPTY, T_DOT, T_ENER, T_WALL, T_DOOR, T_HOUSE, T_NOUP, T_TUNNEL = range(8)

CODE = {
    " ": T_EMPTY,
    ".": T_DOT,
    "o": T_ENER,
    "#": T_WALL,
    "-": T_DOOR,
    "=": T_HOUSE,
    "^": T_NOUP,
    "T": T_TUNNEL,
}

HALF, WIDTH, HEIGHT = 14, 28, 22
WALKABLE = {T_EMPTY, T_DOT, T_ENER, T_NOUP, T_TUNNEL}

# Fixed across all four mazes: the ghost house, the tunnel row, and the
# spawn tiles the engine hardcodes.
HOUSE_ROWS = (9, 10, 11, 12)
TUNNEL_ROW = 11
PLAYER_START = (13, 16)
GHOST_HOME = (13, 8)


class MazeError(Exception):
    pass


def read_mazes(path: Path) -> list[list[str]]:
    blocks: list[list[str]] = []
    cur: list[str] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.rstrip("\n")
        if line.startswith(";") or (not line.strip() and not cur):
            continue
        if not line.strip():
            if cur:
                blocks.append(cur)
                cur = []
            continue
        if len(line) != HALF:
            raise MazeError(f"{path}:{lineno}: row is {len(line)} chars, need {HALF}: {line!r}")
        bad = set(line) - set(CODE)
        if bad:
            raise MazeError(f"{path}:{lineno}: unknown tile chars {sorted(bad)}")
        cur.append(line)
    if cur:
        blocks.append(cur)
    for i, b in enumerate(blocks):
        if len(b) != HEIGHT:
            raise MazeError(f"maze {i + 1}: {len(b)} rows, need {HEIGHT}")
    if len(blocks) != 4:
        raise MazeError(f"need exactly 4 mazes, found {len(blocks)}")
    return blocks


def expand(half: list[str]) -> list[str]:
    return [row + row[::-1] for row in half]


def grid(full: list[str]) -> list[list[int]]:
    return [[CODE[c] for c in row] for row in full]


def validate(idx: int, half: list[str]) -> tuple[int, int]:
    full = expand(half)
    g = grid(full)
    name = f"maze {idx + 1}"

    def die(msg: str) -> None:
        raise MazeError(f"{name}: {msg}")

    if any(t != T_WALL for t in g[0]) or any(t != T_WALL for t in g[HEIGHT - 1]):
        die("top and bottom rows must be solid wall")
    for r in range(HEIGHT):
        edge = g[r][0]
        if r == TUNNEL_ROW:
            if edge != T_TUNNEL:
                die(f"row {r} is the tunnel row; column 0 must be T")
        elif edge != T_WALL:
            die(f"row {r} column 0 must be wall (only row {TUNNEL_ROW} opens)")

    # the house is fixed geometry the engine hardcodes
    want = {
        9: "##--##",
        10: "#====#",
        11: "#====#",
        12: "######",
    }
    for r, pattern in want.items():
        got = "".join(full[r][11:17])
        if got != pattern:
            die(f"row {r} columns 11-16 must be {pattern!r}, got {got!r}")

    if g[GHOST_HOME[1]][GHOST_HOME[0]] not in WALKABLE:
        die(f"ghost home {GHOST_HOME} is not walkable")
    if g[PLAYER_START[1]][PLAYER_START[0]] not in WALKABLE:
        die(f"player start {PLAYER_START} is not walkable")

    energizers = sum(row.count(T_ENER) for row in g)
    if energizers != 4:
        die(f"{energizers} energizers, need exactly 4")

    # every walkable tile must be reachable from the player's start
    seen: set[tuple[int, int]] = set()
    stack: list[tuple[int, int]] = [PLAYER_START]
    while stack:
        c, r = stack.pop()
        if (c, r) in seen:
            continue
        seen.add((c, r))
        for dc, dr in ((0, -1), (-1, 0), (0, 1), (1, 0)):
            nc, nr = c + dc, r + dr
            if r == TUNNEL_ROW:
                nc %= WIDTH
            if not (0 <= nc < WIDTH and 0 <= nr < HEIGHT):
                continue
            if g[nr][nc] in WALKABLE:
                stack.append((nc, nr))
    walkable = {(c, r) for r in range(HEIGHT) for c in range(WIDTH) if g[r][c] in WALKABLE}
    orphans = sorted(walkable - seen)
    if orphans:
        die(f"{len(orphans)} unreachable walkable tiles, first at {orphans[0]}")

    # a dead end is a walkable tile with exactly one walkable neighbour: the
    # arcade maze has none, and one is always an authoring slip
    dead = []
    for c, r in sorted(walkable):
        n = 0
        for dc, dr in ((0, -1), (-1, 0), (0, 1), (1, 0)):
            nc, nr = c + dc, r + dr
            if r == TUNNEL_ROW:
                nc %= WIDTH
            if 0 <= nc < WIDTH and 0 <= nr < HEIGHT and g[nr][nc] in WALKABLE:
                n += 1
        if n <= 1:
            dead.append((c, r))
    if dead:
        die(f"{len(dead)} dead-end tiles, first at {dead[0]}")

    dots = sum(row.count(T_DOT) + row.count(T_NOUP) + row.count(T_ENER) for row in g)
    if not 0 < dots < 256:
        die(f"{dots} dots does not fit a byte counter")
    return dots, energizers


def pack(half: list[str]) -> list[list[int]]:
    rows = []
    for row in half:
        out = []
        for i in range(0, HALF, 2):
            out.append((CODE[row[i]] << 4) | CODE[row[i + 1]])
        rows.append(out)
    return rows


def emit(blocks: list[list[str]], dots: list[int]) -> str:
    lines = [
        "; mazes.inc -- generated by tools/genmaze.py from tools/mazes.txt.",
        "; Do not edit by hand.  Four mazes, left half only (the engine",
        "; mirrors columns 14-27); two tile nibbles per byte, 7 bytes a row.",
        "",
        "mazeptr_lo:",
        "        .byte   " + ", ".join(f"<maze{i + 1}" for i in range(4)),
        "mazeptr_hi:",
        "        .byte   " + ", ".join(f">maze{i + 1}" for i in range(4)),
        "",
        "; dots (including energizers) each maze starts with",
        "mazedots:",
        "        .byte   " + ", ".join(str(d) for d in dots),
        "",
    ]
    for i, half in enumerate(blocks):
        lines.append(f"maze{i + 1}:")
        for r, packed in enumerate(pack(half)):
            art = half[r].replace(" ", "_")
            lines.append("        .byte   " + ", ".join(f"${b:02x}" for b in packed) + f"  ; {art}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    ap.add_argument("--print", action="store_true", help="dump the expanded mazes")
    ap.add_argument("--src", default=str(HERE / "mazes.txt"))
    ap.add_argument("--out", default=str(HERE.parent / "mazes.inc"))
    a = ap.parse_args()

    try:
        blocks = read_mazes(Path(a.src))
        dots = []
        for i, half in enumerate(blocks):
            d, _ = validate(i, half)
            dots.append(d)
    except MazeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if a.print:
        for i, half in enumerate(blocks):
            print(f"--- maze {i + 1}: {dots[i]} dots ---")
            print("    " + "".join(str(c % 10) for c in range(WIDTH)))
            for r, row in enumerate(expand(half)):
                print(f"{r:2d}  {row}")
            print()

    for i, d in enumerate(dots):
        print(f"maze {i + 1}: {d} dots")
    if not a.check:
        Path(a.out).write_text(emit(blocks, dots))
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
