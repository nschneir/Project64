#!/usr/bin/env python3
"""Generate sprites.inc -- the ball's 16 rotation frames, 4 sprite blocks each.

The sphere is genuinely texture-mapped: one ray per sprite texel, intersected
with the unit sphere, converted to latitude/longitude and checked for checker
parity (SPEC.md Section 5.2).  It happens here, once, in float, instead of 60
times a second in 8-bit integers -- which is the whole reason the C64 can show
this at all (SPEC.md Section 1).

Stdlib only, no arguments; writes ../sprites.inc relative to this file.
"""

import math
from pathlib import Path

# ---------------------------------------------------------------------------
# Geometry (SPEC.md Sections 3.2 and 5.2).

TEXW = 24               # texels across the 2x2 block: 12 per multicolour sprite
TEXH = 42               # texel rows down the block: 2 x 21
SPH_TOP = 3             # first texel row the sphere occupies ...
SPH_ROWS = 36           # ... and how many.  Three blank rows top and bottom are
                        # what make the ball round: 24 texels x 4 px = 96 px wide
                        # against 36 rows x 2 px = 72 px tall is 0.991 of a true
                        # circle at the NTSC pixel aspect ratio of 0.7435.
RX = 12.0               # horizontal radius, in texels
RY = 18.0               # vertical radius, in texel rows

# Centre of the sphere in the same coordinates the ray cast samples in: texel
# (c, r) is sampled at (c + 0.5, r + 0.5), so the centre of a 24 x 42 block is
# (12.0, 21.0).
#
# SPEC.md Section 5.2 writes these as (11.5, 20.5), which is half a texel up and
# left of the block centre and does not survive its own Section 3.2: with
# CX = 11.5 the disc's left limb falls at c = -1, off the block, so the equator
# is clipped into a flat vertical edge ~14 rows tall, and with CY = 20.5 the
# sphere spans rows 2-38 (37 rows), not the 3-38 (36) that Section 3.2's
# roundness of 0.991 is computed from.  These values are the ones that make
# Section 3.2 true; the discrepancy is reported rather than silently absorbed.
CX = 12.0
CY = 21.0

N_LON = 16              # longitude segments, 22.5 deg each
N_LAT = 8               # latitude bands, 22.5 deg each
FRAMES = 16
SPAN_DEG = 45.0         # the texture's rotation period is 45 deg, not 360:
                        # 22.5 deg maps every checker onto its opposite-parity
                        # neighbour, so 45 deg returns the identical image
                        # (SPEC.md Section 5.3).

# Multicolour bit pairs (SPEC.md Section 3.3).
TRANSPARENT = 0b00
RIM = 0b01              # $D025, black -- the one-texel dark limb
RED = 0b10              # $D027-$D02A, per sprite
WHITE = 0b11            # $D026, shared

PAIR_CHAR = {TRANSPARENT: ".", RIM: "#", RED: "R", WHITE: "W"}

BLOCK0 = 160            # $2800 / 64 -- sprites.inc is linked first into SPRITES
ROWS_PER_BLOCK = 21
QUADRANTS = (("TL", 0, 0), ("TR", 12, 0), ("BL", 0, 21), ("BR", 12, 21))


def shade(frame: int) -> list[list[int]]:
    """The TEXH x TEXW pair grid for one rotation frame."""
    rot = math.radians(SPAN_DEG * frame / FRAMES)
    inside = [[False] * TEXW for _ in range(TEXH)]
    pairs = [[TRANSPARENT] * TEXW for _ in range(TEXH)]

    for r in range(TEXH):
        ny = (r + 0.5 - CY) / RY
        for c in range(TEXW):
            nx = (c + 0.5 - CX) / RX
            d = nx * nx + ny * ny
            if d > 1.0:
                continue
            inside[r][c] = True
            nz = math.sqrt(max(0.0, 1.0 - d))     # near hit, z toward the viewer
            lat = math.asin(max(-1.0, min(1.0, ny)))   # spin axis vertical
            lon = math.atan2(nx, nz) + rot
            lat_i = int(math.floor((lat + math.pi / 2) / (math.pi / 8))) % N_LAT
            lon_i = int(math.floor((lon + 2 * math.pi) / (math.pi / 8))) % N_LON
            pairs[r][c] = RED if (lat_i + lon_i) & 1 else WHITE

    # The rim runs after the checker so it always wins at the limb: the
    # silhouette is what the eye reads as "sphere" at 4x2 px texels, and it must
    # not depend on which checker happens to land there.  A neighbour off the
    # grid counts as outside -- the sphere touches columns 0 and 23 at the
    # equator, and without that the rim would break open exactly there.
    out = [row[:] for row in pairs]
    for r in range(TEXH):
        for c in range(TEXW):
            if not inside[r][c]:
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if not (0 <= rr < TEXH and 0 <= cc < TEXW) or not inside[rr][cc]:
                    out[r][c] = RIM
                    break
    return out


def block_bytes(grid: list[list[int]], col0: int, row0: int) -> bytes:
    """One 64-byte sprite block: 21 rows of 3 bytes, then a pad byte.

    A multicolour sprite row is 24 bits read as 12 pairs, high pair first, so
    pair k of a byte sits at bits 7-2k..6-2k.  Byte 63 is $00 padding: a sprite
    is 63 bytes of data but a pointer can only select a 64-byte block, so the
    pad is what keeps the next block aligned (SPEC.md Section 5.3).
    """
    data = bytearray()
    for r in range(row0, row0 + ROWS_PER_BLOCK):
        for b in range(3):
            byte = 0
            for k in range(4):
                byte |= grid[r][col0 + b * 4 + k] << (6 - 2 * k)
            data.append(byte)
    data.append(0x00)
    return bytes(data)


def picture(grid: list[list[int]], row: int, col0: int) -> str:
    return "".join(PAIR_CHAR[grid[row][col0 + i]] for i in range(12))


def main() -> None:
    frames = [shade(f) for f in range(FRAMES)]

    lines = [
        "; sprites.inc -- GENERATED by tools/gen_sprites.py.  Do not edit: change",
        "; the generator and re-run it.",
        ";",
        f"; {FRAMES} rotation frames x 4 sprite blocks x 64 bytes = "
        f"{FRAMES * 4 * 64:,} bytes.  This",
        "; file is linked FIRST into the SPRITES area at $2800, so a sprite",
        "; pointer -- which holds block = address / 64, never the address itself",
        f"; -- starts at $2800 / 64 = {BLOCK0}.  Frame f occupies blocks",
        f"; {BLOCK0}+4f (TL), {BLOCK0 + 1}+4f (TR), {BLOCK0 + 2}+4f (BL), "
        f"{BLOCK0 + 3}+4f (BR).",
        ";",
        "; Multicolour bit pairs (SPEC.md Section 3.3):",
        ";   00 . transparent          10 R $D027-$D02A red   (per sprite)",
        ";   01 # $D025 black, the rim  11 W $D026 white       (shared)",
        ";",
        f"; The sphere is a ray cast per texel against the unit sphere, {N_LON}",
        f"; longitude segments by {N_LAT} latitude bands, checker parity",
        f"; (lon + lat) & 1.  {SPAN_DEG:g} deg spans the texture's whole rotation",
        f"; period, so the step is {SPAN_DEG / FRAMES:g} deg per frame.",
        "",
        '        .segment "SPRITES"',
        "",
        "sprite_frames:",
    ]

    total = bytearray()
    for f, grid in enumerate(frames):
        rot = SPAN_DEG * f / FRAMES
        for q, (name, col0, row0) in enumerate(QUADRANTS):
            block = BLOCK0 + 4 * f + q
            lines.append(f"; frame {f:2d}  rot {rot:6.3f} deg  {name}  "
                         f"block {block} = ${block * 64:04X}")
            data = block_bytes(grid, col0, row0)
            total += data
            for i in range(ROWS_PER_BLOCK):
                b0, b1, b2 = data[i * 3:i * 3 + 3]
                lines.append(f"        .byte %{b0:08b}, %{b1:08b}, %{b2:08b}"
                             f"   ; {picture(grid, row0 + i, col0)}")
            lines.append("        .byte $00                              "
                         "      ; pad to 64")
    lines.append("sprite_frames_end:")
    lines.append("")

    # --- asserts: fail loudly rather than emit something short -------------
    assert len(total) == FRAMES * 4 * 64, \
        f"emitted {len(total)} bytes, expected {FRAMES * 4 * 64}"
    for f, grid in enumerate(frames):
        flat = [p for row in grid for p in row]
        assert RED in flat, f"frame {f} has no red checker"
        assert WHITE in flat, f"frame {f} has no white checker"
    half = FRAMES * 4 * 64 // FRAMES
    assert total[0:half] != total[8 * half:9 * half], \
        "frame 0 and frame 8 are identical -- the rotation is not being applied"

    out = Path(__file__).resolve().parent.parent / "sprites.inc"
    out.write_text("\n".join(lines))

    # Diagnostics: the sphere's extent is the claim SPEC.md Section 3.2 makes,
    # so print it rather than assert a number the geometry might drift from.
    occupied = [r for r in range(TEXH)
                if any(p != TRANSPARENT for p in frames[0][r])]
    widest = max(sum(1 for p in frames[0][r] if p != TRANSPARENT)
                 for r in range(TEXH))
    print(f"{out}: {len(total)} bytes")
    print(f"sphere rows {occupied[0]}-{occupied[-1]} "
          f"({len(occupied)} rows, expected {SPH_TOP}-{SPH_TOP + SPH_ROWS - 1}"
          f" = {SPH_ROWS}), widest row {widest} texels")


if __name__ == "__main__":
    main()
