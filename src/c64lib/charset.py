"""Charset glyph encoding: ASCII art in, ca65 `.byte` rows out.

The charset twin of sprites.encode_sprite. Multicolor text glyphs
(`$D016` bit 4) are 8 rows of 4 pixel pairs; pair values map to colors as
fixed by the hardware: 00 = background ($D021), 01 = $D022, 10 = $D023,
11 = the low 3 bits of the cell's color-RAM nybble. Hires glyphs are 8
rows of 8 single-bit pixels.

The legend deliberately differs from the sprite one (' .#+', where '.'
is pair 01): charset blocks are name:-delimited so rows cannot contain
spaces, '.' is the natural "background", and the two hardware modes
order their colors differently anyway. Legend: '.123' multicolor,
'.#' hires.
"""

from __future__ import annotations

_MC_LEGEND = {".": 0b00, "1": 0b01, "2": 0b10, "3": 0b11}
_HIRES_LEGEND = {".": 0, "#": 1}
ROWS_PER_GLYPH = 8


class CharsetError(ValueError):
    """A sheet that does not describe 8-row glyphs in the legend."""


def parse_charset(text: str, multicolor: bool = True) -> list[tuple[str, list[str]]]:
    """Split a glyph sheet into ordered (name, rows) blocks, validating each.

    A block is a `name: x` (or bare `x:`) header plus exactly 8 rows of
    exactly 4 (multicolor) or 8 (hires) legend characters. Blank lines are
    ignored; so are `#` comment lines — but a comment cannot consist solely
    of legend characters at exactly row width (it would BE a row), which
    only matters in hires mode where '#' is a legend character.
    File order is screen-code order.
    """
    width = 4 if multicolor else 8
    legend = _MC_LEGEND if multicolor else _HIRES_LEGEND
    glyphs: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    name: str | None = None
    rows: list[str] = []

    def close(lineno: int) -> None:
        if name is None:
            return
        if len(rows) != ROWS_PER_GLYPH:
            raise CharsetError(
                f"glyph {name!r} (ending at line {lineno}) has {len(rows)} "
                f"rows, expected {ROWS_PER_GLYPH}")
        glyphs.append((name, list(rows)))

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        is_row_shaped = len(line) == width and set(line) <= set(legend)
        if not stripped or (stripped.startswith("#") and not is_row_shaped):
            continue                            # blank line or comment
        if not is_row_shaped and (stripped.endswith(":")
                                  or stripped.startswith("name:")):
            close(lineno)
            name = stripped.removeprefix("name:").strip().rstrip(":")
            if name in seen:
                raise CharsetError(
                    f"duplicate glyph name {name!r} at line {lineno}")
            seen.add(name)
            rows = []
            continue
        if name is None:
            raise CharsetError(
                f"line {lineno}: pixel row before any `name:` line")
        if is_row_shaped:
            rows.append(line)
            continue
        if len(line) != width:
            raise CharsetError(
                f"glyph {name!r} line {lineno}: {len(line)} characters, "
                f"expected exactly {width} ({line!r})")
        bad = sorted(set(line) - set(legend))
        raise CharsetError(
            f"glyph {name!r} line {lineno}: illegal legend characters {bad} "
            f"(legend is {''.join(legend)})")
    close(len(text.splitlines()))
    if not glyphs:
        raise CharsetError("no glyphs found")
    return glyphs


def encode_row(row: str, multicolor: bool = True) -> int:
    """Pack one art row into one charset byte (MSB = leftmost pixel)."""
    legend, bits = (_MC_LEGEND, 2) if multicolor else (_HIRES_LEGEND, 1)
    value = 0
    for ch in row:
        value = (value << bits) | legend[ch]
    return value


def format_glyphs(glyphs: list[tuple[str, list[str]]], first_code: int = 0,
                  multicolor: bool = True) -> str:
    """Render glyph blocks as one contiguous labeled ca65 block.

    One leading `glyphs:` label and one `glyphs_end:` — the consumer
    indexes off the base and sizes the copy with `glyphs_end - glyphs`
    (see demos/invaders/chars.s), so no per-glyph labels and no count byte.
    """
    mode = "multicolor" if multicolor else "hires"
    out = [
        f"; {len(glyphs)} {mode} glyphs, 8 bytes each, screen codes "
        f"{first_code}-{first_code + len(glyphs) - 1} — c64 charset encode",
        "; patch over a RAM charset at CHARSET + code*8",
        "",
        "glyphs:",
    ]
    for offset, (name, rows) in enumerate(glyphs):
        out.append(f"        ; code {first_code + offset}: {name}")
        for row in rows:
            out.append(f"        .byte   %{encode_row(row, multicolor):08b}"
                       f"    ; {row}")
    out.append("glyphs_end:")
    out.append("")
    return "\n".join(out)
