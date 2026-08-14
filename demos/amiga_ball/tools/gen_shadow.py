#!/usr/bin/env python3
"""Generate shadow.inc -- the ball's four contact-shadow shapes.

Sprites 4 and 5 sit side by side, hires (not in $D01C) and X-expanded, which
makes a 96 px wide, 21 raster tall pair sampled at 48 horizontal texels: two
screen pixels per texel, and the finest edge this demo can draw anywhere
(SPEC.md Section 7).  Each of the four shapes is a filled ellipse centred on the
pair centre and on sprite row 10 -- the contact line, raster 236 with the pair's
Y register at 225 -- and the four of them shrink toward that point as the ball
rises.

Stdlib only, no arguments; writes ../shadow.inc relative to this file.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Geometry (SPEC.md Section 7).

SIZES = [(96, 14), (80, 12), (64, 10), (48, 8)]   # (width in screen px, height
                                                  # in rasters), selected by the
                                                  # ball's height band h.
PAIR_W = 96             # screen px across the X-expanded hires pair ...
TEXELS = 48             # ... at 2 px each, so 48 texels, 24 per sprite.
ROWS = 21               # sprite rows; a sprite is 21 rasters whatever else it is
CENTRE_ROW = 10         # row 10 of 21.  The pair's Y register is 225, and the
                        # VIC displays a sprite's first row on raster Y+1 (it
                        # starts the sprite's DMA on the line where $D012 equals
                        # Y and shows the fetched data on the next one), so this
                        # row lands on raster 236 -- the same raster the ball's
                        # bottom reaches at contact.  SPEC.md Sections 6.1 and 7
                        # both write 235; measured on the machine, a 21-row hires
                        # sprite at Y = 100 occupies rasters 101-121.

# Centre of the pair in texel-index coordinates.  Texel k is sampled at index k,
# so 48 texels run 0..47 and their centre is 23.5 -- between texels, which is
# what makes the shape mirror exactly (texel k pairs with 47-k) instead of
# leaning one texel to a side.
CENTRE_X = (TEXELS - 1) / 2.0

BLOCK0 = 224            # $3800 / 64 -- shadow.inc is linked immediately AFTER
                        # sprites.inc, whose 16 x 4 x 64 = 4,096 bytes fill
                        # $2800-$37FF exactly.
BYTES_PER_BLOCK = 64
HALVES = (("left", 0), ("right", 24))


def ellipse(width_px: int, height_rows: int) -> list[list[bool]]:
    """The ROWS x TEXELS bit grid for one shadow size.

    Horizontal semi-axis is width/4 -- half the width, in texels, and a texel is
    2 px.  Vertical semi-axis is height/2, in rasters.  A texel is lit when its
    centre falls inside the ellipse, which is what makes the widths come out
    exact: at row 10 the lit run is 48, 40, 32 and 24 texels, i.e. 96, 80, 64
    and 48 px, the four widths SPEC.md Section 7 tabulates.

    The row counts do NOT come out exact, and that is a property of the spec,
    not of this code: the heights are even (14, 12, 10, 8) but the shape is
    symmetric about the integer row CENTRE_ROW, and a symmetric run about an
    integer centre always has an ODD length.  Sampling row centres gives
    13/11/9/7 lit rows; treating a raster as covered when the ellipse merely
    grazes it gives 15/13/11/9.  Neither is 14.  Centring on the contact line is
    the property that matters (the shadow must not drift a raster between
    sizes), so the row count is the one that gives, and the shorter of the two
    is taken so a shape never spills past its stated height.
    """
    rx = width_px / 4.0
    ry = height_rows / 2.0
    grid = []
    for r in range(ROWS):
        dy = (r - CENTRE_ROW) / ry
        row = []
        for k in range(TEXELS):
            dx = (k - CENTRE_X) / rx
            row.append(dx * dx + dy * dy <= 1.0)
        grid.append(row)
    return grid


def block_bytes(grid: list[list[bool]], col0: int) -> bytes:
    """One 64-byte sprite block: 21 rows of 3 bytes, then a pad byte.

    A hires sprite row is 24 bits, leftmost texel in bit 7 of the first byte --
    no pairing, unlike the ball's multicolour blocks.  Byte 63 is $00 padding: a
    sprite is 63 bytes of data but a pointer can only select a 64-byte block, so
    the pad is what keeps the next block aligned.
    """
    data = bytearray()
    for r in range(ROWS):
        for b in range(3):
            byte = 0
            for k in range(8):
                if grid[r][col0 + b * 8 + k]:
                    byte |= 1 << (7 - k)
            data.append(byte)
    data.append(0x00)
    return bytes(data)


def picture(grid: list[list[bool]], row: int, col0: int) -> str:
    return "".join("#" if grid[row][col0 + i] else "." for i in range(24))


def row_width(grid: list[list[bool]], row: int) -> int:
    return sum(grid[row])


def main() -> None:
    grids = [ellipse(w, h) for w, h in SIZES]
    counts = [sum(row_width(g, r) for r in range(ROWS)) for g in grids]

    lines = [
        "; shadow.inc -- GENERATED by tools/gen_shadow.py.  Do not edit: change",
        "; the generator and re-run it.",
        ";",
        f"; {len(SIZES)} shadow sizes x 2 sprite blocks x {BYTES_PER_BLOCK} "
        f"bytes = {len(SIZES) * 2 * BYTES_PER_BLOCK} bytes.  This file",
        "; is linked immediately AFTER sprites.inc, which fills $2800-$37FF, so",
        "; these blocks start at $3800.  A sprite pointer holds block =",
        f"; address / 64, never the address itself, so that is block $3800 / 64 =",
        f"; {BLOCK0}, and size s, half n occupies block {BLOCK0} + 2s + n",
        "; (n = 0 left, 1 right) -- the numbering SPEC.md Section 7 selects with.",
        ";",
        "; Sprites 4 and 5 are HIRES (not in $D01C) and X-expanded: 24 bits per",
        "; row, 48 texels across the pair, 2 screen px each.  One colour, $0B",
        "; dark gray, because the floor is black and nothing can be darker than",
        "; black -- the patch reads as shadow because $D01B puts the floor grid",
        "; in front of it.",
        ";",
        "; size  h band   ellipse   block L  block R   lit texels",
    ]
    for s, (w, h) in enumerate(SIZES):
        band = ("0-25", "26-51", "52-77", "78+")[s]
        lines.append(f";   {s}    {band:<7}  {w:>2}x{h:<2}     "
                     f"{BLOCK0 + 2 * s:<8} {BLOCK0 + 2 * s + 1:<8}  "
                     f"{counts[s]:>4}")
    lines += [
        ";",
        f"; Row {CENTRE_ROW} of 21 is the widest row of every size.  The pair's Y",
        "; register is fixed at 225 and the VIC shows a sprite's first row on",
        f"; raster Y+1, so row {CENTRE_ROW} lands on raster 236 -- the contact",
        "; line, and the raster the ball's own bottom reaches at contact.",
        "",
        '        .segment "SPRITES"',
        "",
        "shadow_shapes:",
    ]

    total = bytearray()
    for s, ((w, h), grid) in enumerate(zip(SIZES, grids)):
        for n, (name, col0) in enumerate(HALVES):
            block = BLOCK0 + 2 * s + n
            lines.append(f"; size {s}  {w}x{h}  {name:<5} half  "
                         f"block {block} = ${block * BYTES_PER_BLOCK:04X}")
            data = block_bytes(grid, col0)
            total += data
            for r in range(ROWS):
                b0, b1, b2 = data[r * 3:r * 3 + 3]
                lines.append(f"        .byte %{b0:08b}, %{b1:08b}, %{b2:08b}"
                             f"   ; {picture(grid, r, col0)}")
            lines.append("        .byte $00                              "
                         "      ; pad to 64")
    lines.append("shadow_shapes_end:")
    lines.append("")

    # --- asserts: fail loudly rather than emit something short -------------
    want = len(SIZES) * 2 * BYTES_PER_BLOCK
    assert len(total) == want, f"emitted {len(total)} bytes, expected {want}"

    for s in range(1, len(SIZES)):
        assert counts[s] < counts[s - 1], (
            f"size {s} lights {counts[s]} texels, size {s - 1} lights "
            f"{counts[s - 1]} -- the shadows are not shrinking")

    for s, grid in enumerate(grids):
        for r in range(ROWS):
            for k in range(TEXELS):
                assert grid[r][k] == grid[r][TEXELS - 1 - k], (
                    f"size {s} row {r} texel {k} is not mirrored about the "
                    f"pair centre {CENTRE_X}")

    for s, grid in enumerate(grids):
        widest = max(row_width(grid, r) for r in range(ROWS))
        assert row_width(grid, CENTRE_ROW) == widest, (
            f"size {s} is widest at {widest} texels but row {CENTRE_ROW} has "
            f"only {row_width(grid, CENTRE_ROW)} -- the ellipse is off the "
            f"contact line")

    # The seam is the one thing a split can get wrong: texels 23 and 24 are the
    # last of the left block and the first of the right, and on the centre row
    # both must be lit or the pair shows a hairline of floor down its middle.
    for s, grid in enumerate(grids):
        assert grid[CENTRE_ROW][23] and grid[CENTRE_ROW][24], \
            f"size {s} has a gap at the seam on row {CENTRE_ROW}"

    out = Path(__file__).resolve().parent.parent / "shadow.inc"
    out.write_text("\n".join(lines))

    print(f"{out}: {len(total)} bytes")
    for s, ((w, h), grid) in enumerate(zip(SIZES, grids)):
        rows = [r for r in range(ROWS) if row_width(grid, r)]
        print(f"  size {s}  {w:>2}x{h:<2}  lit texels {counts[s]:>4}  "
              f"widest row {row_width(grid, CENTRE_ROW)} texels "
              f"({row_width(grid, CENTRE_ROW) * 2} px)  "
              f"rows {rows[0]}-{rows[-1]} ({len(rows)} of {h} stated)")


if __name__ == "__main__":
    main()
