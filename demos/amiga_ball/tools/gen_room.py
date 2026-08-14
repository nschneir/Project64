#!/usr/bin/env python3
"""Generate chars.inc and screen.inc -- the wire-grid room (SPEC.md Section 4).

The room is one static picture: a purple wall grid above a light-blue floor
drawn in true perspective.  Nothing about it changes per frame, so it has no
business spending a bitmap and a per-frame budget (SPEC.md Section 1) -- it is
rasterised here, once, into a 320x200 1-bit canvas, sliced into 8x8 cells,
deduplicated, and shipped as a 2,048-byte character set plus a 1,000-byte
screen matrix.

All 256 glyphs are generated; nothing is copied from the character ROM, so
room_init has no $01 banking window to protect (SPEC.md Section 4.3).

Stdlib only, no arguments; writes ../chars.inc and ../screen.inc relative to
this file.  Fails loudly rather than emitting something short.
"""

import math
from pathlib import Path

# ---------------------------------------------------------------------------
# The three planes (SPEC.md Section 4, the rows/rasters table).

WALL_ROWS = range(0, 15)        # rasters  51-170, colour RAM $04 purple
HORIZON_ROW = 15                # rasters 171-178, the wall foot
FLOOR_ROWS = range(16, 25)      # rasters 179-250, colour RAM $0E light blue

# --- The wall grid (SPEC.md Section 4.1) -----------------------------------
# 10 verticals 32 px apart, 5 horizontals 24 px apart: a 32 x 24 px cell is
# 23.8 x 24.0 picture units at the NTSC pixel aspect ratio, square to within 1%.
WALL_VCOLS = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36]
WALL_HROWS = [0, 3, 6, 9, 12]

# --- The floor (SPEC.md Section 4.2) ---------------------------------------
VP = (160, 171)                 # vanishing point, screen x / raster y
DEPTH_K = 79                    # y(d) = 171 + K/d
DEPTHS = [1, 2, 3, 4, 5, 6, 8, 10]
FAN_J = [-2, -1, 0, 1, 2]       # x(y) = 160 + j*(80/79)*(y - 171)
FAN_BOTTOM_SPACING = 80         # px between fan lines where they meet raster 250

# The depth-line rasters SPEC.md Section 4.2 tabulates.  They are asserted
# against the formula below rather than trusted: d = 2 is an exact .5 tie
# (79/2 = 39.5) and the spec resolves it DOWNWARD, to raster 210 -- which its
# own "row.offset" column confirms as row 19, scanline 7 = 203 + 7.  Python's
# round() is banker's rounding and would return 40, i.e. raster 211, so the
# rounding here is round-half-down, ceil(x - 0.5), which reproduces all eight
# entries exactly.
DEPTH_RASTERS = [250, 210, 197, 191, 187, 184, 181, 179]

# --- The canvas (SPEC.md Section 2: standard text mode, 40x25) -------------
COLS, ROWS = 40, 25
W, H = COLS * 8, ROWS * 8       # 320 x 200
FIRST_RASTER = 51               # screen row R covers rasters 51+8R .. 58+8R,
                                # so canvas y = raster - 51
MAX_GLYPHS = 256


def depth_raster(d: int) -> int:
    """y(d) = 171 + K/d, rounded half DOWN -- see DEPTH_RASTERS."""
    return VP[1] + math.ceil(DEPTH_K / d - 0.5)


def fan_x(j: int, raster: int) -> float:
    """x(y) = 160 + j*(80/79)*(y - 171) -- SPEC.md Section 4.2."""
    return VP[0] + j * (FAN_BOTTOM_SPACING / DEPTH_K) * (raster - VP[1])


class Canvas:
    """A 320x200 1-bit canvas addressed in RASTERS, not canvas rows.

    Every number in SPEC.md Section 4 is a raster line, so the translation to
    canvas coordinates happens in exactly one place: here.
    """

    def __init__(self) -> None:
        self.px = [bytearray(W) for _ in range(H)]

    def plot(self, x: int, raster: int) -> None:
        y = raster - FIRST_RASTER
        if 0 <= x < W and 0 <= y < H:
            self.px[y][x] = 1

    def hline(self, raster: int, x0: int = 0, x1: int = W - 1) -> None:
        for x in range(x0, x1 + 1):
            self.plot(x, raster)

    def vline(self, x: int, r0: int, r1: int) -> None:
        for raster in range(r0, r1 + 1):
            self.plot(x, raster)


def draw_room() -> Canvas:
    c = Canvas()

    # --- wall: verticals the full height of rows 0-14, closed at the bottom
    # by the horizon (SPEC.md Section 4.1).
    for col in WALL_VCOLS:
        c.vline(col * 8, FIRST_RASTER, FIRST_RASTER + 8 * (HORIZON_ROW) - 1)

    # --- wall: horizontals on the TOP scanline of rows 0, 3, 6, 9, 12.
    for row in WALL_HROWS:
        c.hline(FIRST_RASTER + 8 * row)

    # --- the horizon: raster 171, the top scanline of row 15.  It is both the
    # foot of the wall and the d = infinity depth line.
    c.hline(VP[1])

    # --- floor: lines of constant distance, piling up toward the horizon.
    for d in DEPTHS:
        c.hline(depth_raster(d))

    # --- floor: the five convergent lines.  Each scanline draws the x span the
    # line covers over that scanline -- the far endpoint is left to the next
    # scanline, so the line is connected without being drawn twice.  At
    # |j| = 2 the slope is 2.03 px of x per raster, so one pixel per raster
    # would be a dotted line, not a line.
    for j in FAN_J:
        for raster in range(VP[1], DEPTH_RASTERS[0] + 1):
            xa = round(fan_x(j, raster))
            xb = round(fan_x(j, raster + 1)) if raster < DEPTH_RASTERS[0] else xa
            if xa == xb:
                span = [xa]
            else:
                step = 1 if xb > xa else -1
                span = list(range(xa, xb, step))
            for x in span:
                c.plot(min(max(x, 0), W - 1), raster)   # clipped to 0..319

    return c


def slice_cells(c: Canvas) -> tuple[list[bytes], list[int]]:
    """Cut the canvas into 8x8 cells, dedupe, return (glyphs, screen matrix).

    The all-zero pattern is forced to code 0 whether or not it is used, so a
    screen matrix of zeros is an empty room (SPEC.md Section 4.3).  Every other
    pattern takes the next code in first-use order.
    """
    blank = bytes(8)
    glyphs: list[bytes] = [blank]
    code_of: dict[bytes, int] = {blank: 0}
    screen: list[int] = []

    for row in range(ROWS):
        for col in range(COLS):
            pattern = bytes(
                sum(c.px[row * 8 + r][col * 8 + b] << (7 - b) for b in range(8))
                for r in range(8)
            )
            code = code_of.get(pattern)
            if code is None:
                code = len(glyphs)
                code_of[pattern] = code
                glyphs.append(pattern)
            screen.append(code)
    return glyphs, screen


def picture(byte: int) -> str:
    return "".join("#" if byte & (1 << (7 - b)) else "." for b in range(8))


def emit_chars(glyphs: list[bytes]) -> tuple[str, int]:
    lines = [
        "; chars.inc -- GENERATED by tools/gen_room.py.  Do not edit: change the",
        "; generator and re-run it.",
        ";",
        "; 256 glyphs x 8 bytes = 2,048 bytes, linked at $2000 by",
        "; --area 'CHARS=$2000:$0800'.  $2000 rather than $1000 or $1800 because",
        "; the character ROM's 4 KB image covers both of those bases in bank 0 and",
        "; $1800 fails SILENTLY, drawing the ROM's lowercase (SPEC.md Section 2).",
        ";",
        f"; {len(glyphs)} of the 256 codes are used; the rest are zero.  Code 0 is",
        "; blank by construction, so a screen matrix of zeros is an empty room",
        "; (SPEC.md Section 4.3).  Nothing here is copied from the character ROM,",
        "; which is why room_init has no $01 banking window to protect.",
        "",
        '        .segment "CHARS"',
        "",
        "charset:",
    ]

    data = bytearray()
    for code in range(MAX_GLYPHS):
        if code < len(glyphs):
            pattern = glyphs[code]
            lines.append(f"; code {code}")
            for byte in pattern:
                lines.append(f"        .byte %{byte:08b}   ; {picture(byte)}")
        else:
            pattern = bytes(8)
            lines.append("        .byte $00,$00,$00,$00,$00,$00,$00,$00"
                         f"   ; code {code} unused")
        data += pattern
    lines.append("charset_end:")
    lines.append("")
    return "\n".join(lines), len(data)


def emit_screen(screen: list[int], glyph_count: int) -> tuple[str, int]:
    lines = [
        "; screen.inc -- GENERATED by tools/gen_room.py.  Do not edit: change the",
        "; generator and re-run it.",
        ";",
        "; The 1,000-byte screen matrix room_init copies to $0400.  It lives in",
        "; RODATA rather than at $0400 directly because $0400 is where the VIC",
        "; reads and the KERNAL has already written; a copy at init is 1,000 bytes",
        "; of ROM-free work done once (SPEC.md Section 4.3).",
        ";",
        f"; Rows 0-14 are the wall, row 15 the horizon, rows 16-24 the floor.",
        f"; {glyph_count} distinct glyphs; 0 is blank.",
        "",
        '        .segment "RODATA"',
        "",
        "screen_map:",
    ]
    for row in range(ROWS):
        cells = screen[row * COLS:(row + 1) * COLS]
        if row < HORIZON_ROW:
            what = "wall"
        elif row == HORIZON_ROW:
            what = "horizon"
        else:
            what = "floor"
        body = ",".join(f"${v:02X}" for v in cells)
        lines.append(f"        .byte {body}   ; row {row:2d}  "
                     f"rasters {FIRST_RASTER + 8 * row}-"
                     f"{FIRST_RASTER + 8 * row + 7}  {what}")
    lines.append("screen_map_end:")
    lines.append("")
    return "\n".join(lines), len(screen)


def main() -> None:
    # The spec's depth-line table is a claim about the formula: check it.
    computed = [depth_raster(d) for d in DEPTHS]
    assert computed == DEPTH_RASTERS, \
        f"depth rasters {computed} != SPEC.md Section 4.2 table {DEPTH_RASTERS}"

    canvas = draw_room()
    glyphs, screen = slice_cells(canvas)

    # --- asserts: fail loudly rather than emit something short -------------
    assert len(glyphs) <= MAX_GLYPHS, \
        f"{len(glyphs)} distinct glyphs, and the VIC has only {MAX_GLYPHS}"
    for row in (0, 15, 20):
        assert any(screen[row * COLS:(row + 1) * COLS]), \
            f"screen row {row} is entirely blank -- nothing was rasterised into it"

    chars_text, chars_bytes = emit_chars(glyphs)
    screen_text, screen_bytes = emit_screen(screen, len(glyphs))
    assert chars_bytes == 2048, f"chars.inc is {chars_bytes} bytes, expected 2048"
    assert screen_bytes == 1000, \
        f"screen.inc is {screen_bytes} bytes, expected 1000"

    here = Path(__file__).resolve().parent.parent
    (here / "chars.inc").write_text(chars_text)
    (here / "screen.inc").write_text(screen_text)

    print(f"glyphs: {len(glyphs)} of {MAX_GLYPHS}")
    print(f"{here / 'chars.inc'}: {chars_bytes} bytes")
    print(f"{here / 'screen.inc'}: {screen_bytes} bytes")
    print(f"depth-line rasters: {computed}")


if __name__ == "__main__":
    main()
