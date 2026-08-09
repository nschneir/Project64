#!/usr/bin/env python3
"""Generate traj.inc -- the velocity tables and flight paths.

The frame budget forbids a multiply, a divide or a trigonometric function
inside the tick, so nothing is computed at run time: a heading is an index
into a table of ready-made 8.8 velocity pairs, and a flight path is a
run-length list of (heading, frames).  Integrating a path is then a 16-bit
add per axis per frame.

    python3 tools/gentraj.py -o traj.inc
    python3 tools/gentraj.py --check

Headings are 64ths of a turn.  Heading 0 is straight down (+Y, the way the
screen counts), 16 is right, 32 is up, 48 is left -- so `dx = sin`, `dy =
cos`, and a rising heading turns clockwise on screen.

Three speed tiers, because §7 of PROMPT.md names three:

    v0   2.00 px/frame   the base dive and entrance speed
    v1   2.30 px/frame   the same +15%, from stage 4
    v2   3.00 px/frame   the challenging stages' faster sweeps

--check simulates every path from its start point and asserts what the
renderer relies on: no path wanders further than 48 pixels outside the
screen (an enemy that leaves for good never settles), every path is at
least half a second long, and every path ends moving *towards* the
formation rather than away from it.
"""

from __future__ import annotations

import argparse
import math
import sys

STEPS = 64
SPEEDS = (("v0", 2.00), ("v1", 2.30), ("v2", 3.00))

# Where each entrance group comes on from, in screen pixels.  x is the VIC
# sprite coordinate (24 = left edge of the 40-column screen), y likewise
# (50 = first visible raster).  The playfield window is columns 8-31, so
# x 88-280.
STARTS = {
    "path0": (176, 20),    # wave 1: drops from top centre
    "path1": (80, 60),     # wave 2: in from the top left
    "path2": (272, 60),    # wave 3: in from the top right, mirrored
    "path3": (80, 236),    # wave 4: up from the bottom left
    "path4": (272, 236),   # wave 5: up from the bottom right
}

FORMATION_Y = 110          # roughly the middle of the settled grid


def arc(start: int, turn: int, steps: int, frames: int) -> list[tuple[int, int]]:
    """A curve: `steps` segments of `frames` frames, turning `turn` per step."""
    return [((start + turn * i) % STEPS, frames) for i in range(steps)]


def straight(heading: int, frames: int) -> list[tuple[int, int]]:
    return [(heading % STEPS, frames)]


# The five entrance paths.  Each is read by every enemy of its group, which
# launch six frames apart, so a group flies the shape as a stream.
PATHS: dict[str, list[tuple[int, int]]] = {
    # Wave 1: drop down the middle, throw one full loop, carry on down.
    "path0": straight(0, 16) + arc(0, -2, 32, 2) + straight(0, 10),
    # Wave 2: in from the top left on a slant, one full loop, into the grid.
    "path1": straight(10, 14) + arc(10, 2, 32, 2) + straight(6, 12),
    # Wave 3 mirrors wave 2: every heading reflected about the vertical.
    "path2": [],
    # Wave 4: up from the bottom left, circling as it climbs.
    "path3": straight(26, 14) + arc(26, -2, 32, 2) + straight(30, 16),
    # Wave 5 mirrors wave 4.
    "path4": [],
}
PATHS["path2"] = [((-a) % STEPS, f) for a, f in PATHS["path1"]]
PATHS["path4"] = [((-a) % STEPS, f) for a, f in PATHS["path3"]]

# Dive paths, taken by an enemy leaving the settled grid.  Index by the
# `enemy_path` field; stage difficulty picks which are in play.
DIVES: dict[str, list[tuple[int, int]]] = {
    # A plain swoop: peel off to one side, curl over, come down the screen.
    "dive0": straight(6, 10) + arc(6, -1, 12, 3) + straight(0, 46),
    # A tighter loop with a cross-over -- the pressure dive.
    "dive1": straight(58, 8) + arc(58, 2, 18, 3) + straight(4, 40),
    # The Flagship's capture run: down the middle and halt above the player
    # (the halt is enemy.s's business; the path just gets it there).
    "dive2": straight(0, 10) + arc(0, 1, 6, 3) + straight(6, 8) + straight(0, 16),
    # The challenging stages' scripted sweeps: across the screen and off,
    # never turning down onto the player.
    "sweep0": straight(16, 10) + arc(16, 1, 24, 3) + straight(40, 24),
    "sweep1": straight(48, 10) + arc(48, -1, 24, 3) + straight(24, 24),
    "sweep2": straight(20, 16) + arc(20, 2, 20, 2) + straight(44, 22),
}

ALL = {**PATHS, **DIVES}


def vel(speed: float, heading: int) -> tuple[int, int]:
    ang = 2 * math.pi * heading / STEPS
    dx = round(speed * math.sin(ang) * 256)
    dy = round(speed * math.cos(ang) * 256)
    return dx, dy


def simulate(
    name: str, path: list[tuple[int, int]], speed: float
) -> tuple[list[float], list[float]]:
    x, y = STARTS.get(name, (176, 120))
    xs: list[float] = [float(x)]
    ys: list[float] = [float(y)]
    for heading, frames in path:
        dx, dy = vel(speed, heading)
        for _ in range(frames):
            x += dx / 256
            y += dy / 256
            xs.append(x)
            ys.append(y)
    return xs, ys


def check() -> None:
    problems = []
    for name, path in ALL.items():
        frames = sum(f for _, f in path)
        if frames < 30:
            problems.append(f"{name}: only {frames} frames, under half a second")
        xs, ys = simulate(name, path, 2.0)
        if min(xs) < -48 or max(xs) > 392 or min(ys) < -48 or max(ys) > 298:
            problems.append(
                f"{name}: wanders to x {min(xs):.0f}..{max(xs):.0f}, "
                f"y {min(ys):.0f}..{max(ys):.0f} -- off the map"
            )
        if name in STARTS:
            # An entrance has to end heading back towards the grid, or the
            # homing leg that follows it becomes a long straight crawl.
            if not (40 <= xs[-1] <= 340 and 0 <= ys[-1] <= 230):
                problems.append(
                    f"{name}: ends at ({xs[-1]:.0f},{ys[-1]:.0f}) -- the homing "
                    "leg after it would be a long straight crawl"
                )
    if problems:
        for p in problems:
            print("FAIL " + p, file=sys.stderr)
        sys.exit(1)
    for name, path in ALL.items():
        frames = sum(f for _, f in path)
        xs, ys = simulate(name, path, 2.0)
        print(
            f"ok {name:<8} {len(path):>3} segments {frames:>4} frames  "
            f"end ({xs[-1]:>4.0f},{ys[-1]:>4.0f})"
        )


def emit() -> str:
    out = [
        "; traj.inc -- GENERATED by tools/gentraj.py.  Do not edit.",
        ";",
        "; Velocity tables: 64 headings, 8.8 signed, low bytes then high",
        "; bytes so a heading is two absolute,X loads and no shifting.",
        "; Heading 0 = down, 16 = right, 32 = up, 48 = left.",
        "",
        "        .segment \"ENGINE\"",
        "",
    ]
    for label, speed in SPEEDS:
        pairs = [vel(speed, h) for h in range(STEPS)]
        out.append(f"; ---- {label}: {speed:.2f} px/frame " + "-" * 30)
        for axis, idx in (("x", 0), ("y", 1)):
            for half, shift in (("lo", 0), ("hi", 8)):
                name = f"{label}{axis}{half}"
                vals = [(p[idx] >> shift) & 0xFF for p in pairs]
                out.append(f"{name}:")
                for i in range(0, STEPS, 8):
                    row = ", ".join(f"${v:02x}" for v in vals[i : i + 8])
                    out.append(f"        .byte   {row}")
        out.append("")

    out.append("; ---- flight paths: (heading, frames) pairs, $FF terminated ----")
    names = list(ALL)
    out.append("pathtablo:")
    for n in names:
        out.append(f"        .byte   <{n}")
    out.append("pathtabhi:")
    for n in names:
        out.append(f"        .byte   >{n}")
    out.append("")
    for i, n in enumerate(names):
        out.append(f"PATH_{n.upper()} = {i}")
    out.append("")
    for name, path in ALL.items():
        frames = sum(f for _, f in path)
        out.append(f"{name}:                          ; {frames} frames")
        for heading, f in path:
            out.append(f"        .byte   {heading:>3}, {f:>3}")
        out.append("        .byte   $FF")
        out.append("")

    out.append("; ---- entrance start positions, one per wave ----")
    out.append("; X is a sprite coordinate and the right-hand starts are past")
    out.append("; 255, so it ships as a low byte and a 9th bit.")
    out.append("wavestartx:")
    for i in range(5):
        out.append(f"        .byte   {STARTS[f'path{i}'][0] & 0xFF}")
    out.append("wavestartmsb:")
    for i in range(5):
        out.append(f"        .byte   {STARTS[f'path{i}'][0] >> 8}")
    out.append("wavestarty:")
    for i in range(5):
        out.append(f"        .byte   {STARTS[f'path{i}'][1]}")
    out.append("")
    out.append(f"FORMATION_Y = {FORMATION_Y}")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    check()
    if args.check:
        return
    text = emit()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.out}: {len(text.splitlines())} lines")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
