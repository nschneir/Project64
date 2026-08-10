"""Sprite decoding, rendering, and PNG conversion (VIC-II sprites).

All shape data is 63 bytes: 21 rows of 3 bytes (24 hires pixels, or 12
double-wide multicolor pixel pairs). Multicolor pair values map to colors
as fixed by the hardware: 00 = background ($D021), 01 = $D025,
10 = the sprite's own color ($D027+n), 11 = $D026.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from .basic_tokens import MAX_LINE_NUMBER
from .charset import parse_block_header

# Pepto palette (colodore lineage) — index = C64 color number.
C64_PALETTE = [
    (0, 0, 0), (255, 255, 255), (104, 55, 43), (112, 164, 178),
    (111, 61, 134), (88, 141, 67), (53, 40, 121), (184, 199, 111),
    (111, 79, 37), (67, 57, 0), (154, 103, 89), (68, 68, 68),
    (108, 108, 108), (154, 210, 132), (108, 94, 181), (149, 149, 149),
]


@dataclass(frozen=True)
class SpriteState:
    index: int
    enabled: bool
    x: int
    y: int
    pointer: int
    block_addr: int
    color: int
    multicolor: bool
    expand_x: bool
    expand_y: bool
    behind_text: bool


def read_sprite_states(mon, screen_base: int) -> tuple[list[SpriteState], dict]:
    """Decode $D000-$D02E plus the sprite pointers at screen_base+$3F8."""
    vic = mon.memory_read(0xD000, 0x2F)
    ptrs = mon.memory_read(screen_base + 0x3F8, 8)
    states = []
    for n in range(8):
        bit = 1 << n
        states.append(SpriteState(
            index=n,
            enabled=bool(vic[0x15] & bit),
            x=vic[2 * n] + (256 if vic[0x10] & bit else 0),
            y=vic[2 * n + 1],
            pointer=ptrs[n],
            block_addr=ptrs[n] * 64,
            color=vic[0x27 + n] & 0x0F,
            multicolor=bool(vic[0x1C] & bit),
            expand_x=bool(vic[0x1D] & bit),
            expand_y=bool(vic[0x17] & bit),
            behind_text=bool(vic[0x1B] & bit),
        ))
    shared = {"mc_color1": vic[0x25] & 0x0F, "mc_color2": vic[0x26] & 0x0F,
              "background": vic[0x21] & 0x0F, "border": vic[0x20] & 0x0F}
    return states, shared


def read_sprite_block(mon, block_addr: int) -> bytes:
    return mon.memory_read(block_addr, 63)


_MC_GLYPHS = {0: "·", 1: "▒", 2: "█", 3: "▓"}


def _row_bits(data: bytes, row: int) -> int:
    b = data[row * 3: row * 3 + 3]
    return (b[0] << 16) | (b[1] << 8) | b[2]


def sprite_ascii(data: bytes, multicolor: bool) -> list[str]:
    """21 rows of 24 characters; multicolor pairs are drawn double-wide."""
    rows = []
    for r in range(21):
        bits = _row_bits(data, r)
        if multicolor:
            row = "".join(_MC_GLYPHS[(bits >> (22 - 2 * p)) & 3] * 2
                          for p in range(12))
        else:
            row = "".join("█" if bits & (1 << (23 - c)) else "·"
                          for c in range(24))
        rows.append(row)
    return rows


# Encode legends. Accept the plain-ASCII authoring set, the digit-is-the-
# pair-value set charset sheets use ('.123'), AND the glyphs `sprite_ascii`
# emits, so `c64 sprite show` output round-trips through encode.
_MC_ENCODE = {" ": 0, ".": 1, "#": 2, "+": 3,   # friendly
              "1": 1, "2": 2, "3": 3,           # digit == the pair's value
              "·": 0, "▒": 1, "█": 2, "▓": 3}    # == _MC_GLYPHS (show output)
_HIRES_ENCODE = {" ": 0, "#": 1, "·": 0, "█": 1}

#: what `--background`/`background=` defaults to. A space is invisible, which
#: is the whole reason the option exists.
DEFAULT_BACKGROUND = " "


def _encode_legend(multicolor: bool, background: str) -> dict[str, int]:
    """The legend for one mode, with `background` claimed for pair 00.

    The claim overrides: '.' means pair 01 by default, and `background='.'`
    makes it 00 — which is why the digits above exist, so '1' still spells
    pair 01 in a sheet whose background is a visible dot. A space always
    reads as background; nothing else in either legend maps to 0, so there
    is nothing for it to shadow.
    """
    if len(background) != 1:
        raise ValueError(
            f"background must be one character, got {background!r}")
    legend = dict(_MC_ENCODE if multicolor else _HIRES_ENCODE)
    legend[background] = 0
    return legend


def _mc_pixels(row: str, legend: dict[str, int]) -> list[int]:
    # Accept 12 glyphs (one/pixel) or 24 (the doubled form `show` emits).
    if len(row) == 24:
        row = row[::2]           # collapse each doubled pair
    if len(row) != 12:
        raise ValueError("multicolor sprite art must be 12 or 24 chars/row")
    try:
        return [legend[ch] for ch in row]
    except KeyError as e:
        raise ValueError(f"unknown multicolor sprite glyph {e.args[0]!r}") from None


ROWS_PER_SPRITE = 21


class Shape(NamedTuple):
    """One block of a sheet: where it starts, what it is called, its art.

    `name` is None for a positional block — a sheet that never writes a
    header still parses, and those blocks are still numbered by position.
    """

    lineno: int
    name: str | None
    rows: list[str]
    multicolor: bool


class EncodedSprite(NamedTuple):
    """One encoded block: 63 bytes plus what the renderer needs to label it."""

    name: str | None
    multicolor: bool
    data: bytes


def _row_width(multicolor: bool) -> int:
    return 12 if multicolor else 24


def parse_sprite_sheet(text: str, multicolor: bool = True,
                       background: str = DEFAULT_BACKGROUND) -> list[Shape]:
    """Split a sheet into its blocks, honoring `name:` headers and comments.

    A block ends at a truly EMPTY line or at the next header — a row of
    all-background pixels is a legitimate 12/24-character row of spaces (or
    of `background`), and must not be confused with the blank line between
    sprites. Rows are kept exactly as written (no stripping); with the
    default space background, trailing spaces are significant.

    A header is `fighter:hires`, `drone:multicolor` or a bare `drone:`,
    spelled and parsed exactly as a charset sheet's (`charset.
    parse_block_header` is the one parser). A bare header takes the file's
    mode, so `--hires` still means what it meant; a named one sets its own,
    so a game's hires ship and its multicolor aliens are one sheet.

    `#` starts a comment — but `#` is also a legend character, so a line
    counts as a comment only when it holds something the legend does not.
    An all-`#` row is a solid line of sprite-color pixels, and this sheet
    format hit that trap twice before the rule was written down.

    The line number travels with the block so a rejection can point at the
    art rather than at the sheet: a file of 27 shapes reporting only "must
    be 21 rows" costs a hand bisection to place.
    """
    legends = {mc: set(_encode_legend(mc, background)) for mc in (False, True)}
    sheet: list[Shape] = []
    current: list[str] = []
    seen: set[str] = set()
    start = 0
    name: str | None = None
    block_mc = multicolor

    def close() -> None:
        """Flush the open block. A header with no rows yet stays pending, so
        a blank line between a header and its art is just a blank line."""
        nonlocal current, name, block_mc
        if current:
            sheet.append(Shape(start, name, current, block_mc))
            current, name, block_mc = [], None, multicolor

    def no_art_yet() -> None:
        """A name the sheet never drew is a typo'd header, not an empty
        sprite — charset sheets reject the same shape rather than dropping it."""
        if name is not None and not current:
            raise ValueError(f"sprite {name!r} (line {start}) has no art rows")

    for lineno, line in enumerate(text.splitlines(), start=1):
        # Row-shaped: the block's own width (or the 24-character doubled form
        # `show` emits for multicolor) and nothing outside the legend.
        is_row = (len(line) in (_row_width(block_mc), 24)
                  and set(line) <= legends[block_mc])
        stripped = line.strip()
        if is_row:
            if not current and name is None:
                start = lineno                   # a positional block starts here
            current.append(line)
            continue
        if not stripped:
            close()                              # blank line: block boundary
            continue
        if stripped.startswith("#"):
            continue                             # comment — checked before the
        if ":" in stripped:                      # header, since `#` is legal in
            close()                              # both and a comment can hold a
            no_art_yet()                         # colon ("# ---- hires: ...")
            name, block_mc = parse_block_header(
                stripped, lineno, multicolor, kind="sprite", error=ValueError)
            if name in seen:
                raise ValueError(
                    f"duplicate sprite name {name!r} at line {lineno}")
            seen.add(name)
            start = lineno
            continue
        if not current and name is None:
            start = lineno
        current.append(line)                     # malformed: encode_* names it
    close()
    no_art_yet()
    return sheet


def encode_sheet_blocks(text: str, multicolor: bool = True,
                        background: str = DEFAULT_BACKGROUND
                        ) -> list[EncodedSprite]:
    """Encode every block in a sheet, naming the block that is wrong.

    Blocks are numbered from 1 the way a reader counts them; the emitted
    `spriteN:` labels are 0-based, which is exactly why the message carries
    the line number too — and the block's own name, once it has one.
    """
    out: list[EncodedSprite] = []
    for index, shape in enumerate(parse_sprite_sheet(
            text, multicolor=multicolor, background=background), start=1):
        named = f" {shape.name!r}" if shape.name else ""
        where = f"sprite {index}{named} (line {shape.lineno})"
        if len(shape.rows) != ROWS_PER_SPRITE:
            raise ValueError(f"{where}: art must be {ROWS_PER_SPRITE} rows, "
                             f"got {len(shape.rows)}")
        try:
            data = encode_sprite(shape.rows, multicolor=shape.multicolor,
                                 background=background)
        except ValueError as e:
            raise ValueError(f"{where}: {e}") from None
        out.append(EncodedSprite(shape.name, shape.multicolor, data))
    return out


def encode_sheet(text: str, multicolor: bool = True,
                 background: str = DEFAULT_BACKGROUND) -> list[bytes]:
    """The bytes of every block in a sheet, in file order."""
    return [block.data for block in
            encode_sheet_blocks(text, multicolor=multicolor,
                                background=background)]


def encode_sprite(art: list[str], multicolor: bool = True,
                  background: str = DEFAULT_BACKGROUND) -> bytes:
    """Encode ASCII-art rows to 63 sprite bytes (the inverse of `sprite_ascii`).

    Accepts the friendly authoring legend (' .#+' / ' #'), the digit legend
    charset sheets use ('.123', digit == pair value), or the glyphs
    `sprite_ascii` emits ('·▒█▓' / '█·'), so `c64 sprite show` output
    round-trips through `encode_sprite`. `background` picks the character
    that means pair 00 — pass '.' to author with a visible background, which
    is what makes a row's width countable. `art` must have exactly 21 rows.
    """
    if len(art) != 21:
        raise ValueError(f"sprite art must be 21 rows, got {len(art)}")
    legend = _encode_legend(multicolor, background)
    out = bytearray()
    for row in art:
        bits = 0
        if multicolor:
            for px in _mc_pixels(row, legend):
                bits = (bits << 2) | px
        else:
            if len(row) != 24:
                raise ValueError(f"hires sprite art must be 24 chars/row, got {len(row)}")
            try:
                for ch in row:
                    bits = (bits << 1) | legend[ch]
            except KeyError as e:
                raise ValueError(f"unknown hires sprite glyph {e.args[0]!r}") from None
        out += bits.to_bytes(3, "big")
    return bytes(out)          # 63 bytes; pad byte 64 is the caller's call


def format_bytes(data: bytes, fmt: str, index: int = 0,
                 multicolor: bool = True, start_line: int | None = None,
                 line_step: int = 10, name: str | None = None) -> str:
    """Render sprite bytes as ready-to-place source, one sprite row per line.

    `fmt` is 'asm' (ca65 `.byte %...`, 3 bytes/row per line, under a
    `spriteN:` label with a header comment — the same shape `c64 sprite
    from-png` emits, so hand- and image-authored sprites look identical in
    source) or 'basic' (`data` lines, 3 bytes/row per line, decimal). `index`
    names the label / header sprite number when a file holds several sprites;
    `multicolor` only affects the header wording.

    `name`, when the sheet gave the block one, is echoed in the asm header
    comment — `; sprite 5 (captured), ...` — so a generated include reads as
    the block map the sheet already is. The label stays positional
    (`sprite5:`), because that is what a consumer's `.incbin`-free source
    indexes off.

    `basic` rows are keyword-lowercase, per the petcat convention the rest
    of the toolchain uses: an uppercase `DATA` is shifted PETSCII and
    tokenizes to `STR$ ATN ATN`, so the listing would not run.

    They are unnumbered by default — a bare `data` line will not store in a
    real BASIC program either, so pass `start_line` to number them
    (`line_step` apart, 10 by default, leaving room to insert later) and the
    block pastes straight into a `.bas` source.
    """
    if fmt not in ("asm", "basic"):
        raise ValueError(f"unknown format {fmt!r}; use 'asm' or 'basic'")
    rows = [data[i:i + 3] for i in range(0, len(data), 3)]
    if fmt == "asm":
        mode = "multicolor" if multicolor else "hires"
        called = f" ({name})" if name else ""
        header = [
            f"; sprite {index}{called}, 24x21 {mode} (63 bytes: 3 bytes x 21 rows)"
            " — c64 sprite encode",
            "; place in a 64-byte block; pointer = block_address / 64",
        ]
        return "\n".join(_emit(rows, header, index))
    lines = ["data " + ",".join(str(b) for b in row) for row in rows]
    if start_line is None:
        return "\n".join(lines)
    if start_line < 0 or line_step < 1:
        raise ValueError("start_line must be >= 0 and line_step >= 1")
    numbers = [start_line + i * line_step for i in range(len(lines))]
    if numbers[-1] > MAX_LINE_NUMBER:
        raise ValueError(
            f"line numbers would reach {numbers[-1]}, past the BASIC maximum "
            f"{MAX_LINE_NUMBER}; lower start_line or line_step")
    return "\n".join(f"{n} {line}"
                     for n, line in zip(numbers, lines, strict=True))


def render_sheet(sprites: Sequence[bytes | EncodedSprite], fmt: str = "asm",
                 multicolor: bool = True, start_line: int | None = None,
                 line_step: int = 10) -> str:
    """Render a whole encoded sheet as one paste-ready block, trailing newline.

    Blocks are separated by a blank line and the numbering runs on across
    sprites (21 rows each) so a multi-sprite file comes out as one ascending
    listing, not three restarts. Rejects a bad `fmt` / line number the way
    `format_bytes` does.

    Takes either bare 63-byte blocks — then `multicolor` is the whole
    sheet's mode — or the `EncodedSprite`s `encode_sheet_blocks` returns,
    each carrying its own name and mode, so a sheet that mixed hires and
    multicolor renders each block the way it was encoded.
    """
    blocks = [s if isinstance(s, EncodedSprite) else EncodedSprite(None, multicolor, s)
              for s in sprites]
    return "\n\n".join(
        format_bytes(block.data, fmt, index=i, multicolor=block.multicolor,
                     start_line=(None if start_line is None
                                 else start_line + i * ROWS_PER_SPRITE * line_step),
                     line_step=line_step, name=block.name)
        for i, block in enumerate(blocks)) + "\n"


def sprite_image(data: bytes, state: SpriteState, shared: dict, scale: int = 1):
    """Render a 63-byte shape to a PIL image (24x21 logical pixels)."""
    from PIL import Image

    img = Image.new("RGB", (24, 21))
    bg = C64_PALETTE[shared["background"]]
    # None = hires; the shared mc_* entries are only read in multicolor mode,
    # so a caller rendering a hires sprite need not supply them.
    pair_colors = None
    if state.multicolor:
        pair_colors = {0: bg,
                       1: C64_PALETTE[shared["mc_color1"]],
                       2: C64_PALETTE[state.color],
                       3: C64_PALETTE[shared["mc_color2"]]}
    for y in range(21):
        bits = _row_bits(data, y)
        if pair_colors is not None:
            for p in range(12):
                c = pair_colors[(bits >> (22 - 2 * p)) & 3]
                img.putpixel((2 * p, y), c)
                img.putpixel((2 * p + 1, y), c)
        else:
            fg = C64_PALETTE[state.color]
            for x in range(24):
                img.putpixel((x, y), fg if bits & (1 << (23 - x)) else bg)
    if scale > 1:
        img = img.resize((24 * scale, 21 * scale), Image.Resampling.NEAREST)
    return img


def _luminance(px) -> float:
    r, g, b = px[0], px[1], px[2]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _nearest_palette(px) -> int:
    return min(range(16), key=lambda i: sum(
        (a - b) ** 2 for a, b in zip(px[:3], C64_PALETTE[i], strict=True)))


def _emit(rows_bytes: list[bytes], header: list[str], index: int = 0) -> list[str]:
    label = f"sprite{index}:"
    cont = " " * len(label)
    lines = list(header)
    for i, row in enumerate(rows_bytes):
        bits = ", ".join(f"%{b:08b}" for b in row)
        lines.append(f"{label} .byte {bits}" if i == 0
                      else f"{cont} .byte {bits}")
    return lines


def sprite_from_image(img, multicolor: bool) -> tuple[bytes, list[str]]:
    """Convert any PIL image to 63 sprite bytes + ready-to-paste ca65 rows.

    Hires: pixel set where alpha >= 128 and luminance < 128. Multicolor:
    background = the most common edge color; the remaining colors get pair
    values 01/10/11 in first-appearance (raster) order — the emitted
    header records the mapping.
    """
    img = img.convert("RGBA")
    if not multicolor:
        img = img.resize((24, 21), _resample())
        rows = []
        for y in range(21):
            bits = 0
            for x in range(24):
                px = img.getpixel((x, y))
                if px[3] >= 128 and _luminance(px) < 128:
                    bits |= 1 << (23 - x)
            rows.append(bits.to_bytes(3, "big"))
        header = [
            "; sprite, 24x21 hires (63 bytes: 3 bytes x 21 rows)"
            " — c64 sprite from-png",
            "; place in a 64-byte block; pointer = block_address / 64",
        ]
        return b"".join(rows), _emit(rows, header)

    img = img.resize((12, 21), _resample())
    grid = [[_nearest_palette(img.getpixel((x, y))) if img.getpixel((x, y))[3] >= 128
             else None for x in range(12)] for y in range(21)]
    border_px = [grid[y][x] for y in range(21) for x in range(12)
                 if x in (0, 11) or y in (0, 20)]
    edge = [c for c in border_px if c is not None]      # opaque edge pixels
    background = max(set(edge), key=edge.count) if edge else 0
    order: list[int] = []
    for y in range(21):
        for x in range(12):
            c = grid[y][x]
            if c is not None and c != background and c not in order:
                order.append(c)
    order = order[:3]
    pair_of = {background: 0}
    for i, c in enumerate(order):
        pair_of[c] = i + 1                     # 01, 10, 11 in raster order
    rows = []
    for y in range(21):
        bits = 0
        for x in range(12):
            c = grid[y][x]
            if c is None:                      # transparent: show background
                pv = 0
            else:
                pv = pair_of.get(c)
                if pv is None:                 # extra color: nearest of the 4
                    px = C64_PALETTE[c]        # same for every candidate
                    chosen = min([background, *order], key=lambda k: sum(
                        (a - b) ** 2
                        for a, b in zip(px, C64_PALETTE[k], strict=True)))
                    pv = pair_of[chosen]
            bits |= pv << (22 - 2 * x)
        rows.append(bits.to_bytes(3, "big"))
    names = {1: "01 ($D025)", 2: "10 (sprite color)", 3: "11 ($D026)"}
    header = [
        "; sprite, 12x21 multicolor pairs (63 bytes) — c64 sprite from-png",
        f"; background (00) = color {background}; "
        + "; ".join(f"{names[i + 1]} = color {c}" for i, c in enumerate(order)),
        "; place in a 64-byte block; pointer = block_address / 64",
    ]
    return b"".join(rows), _emit(rows, header)


def _resample():
    from PIL import Image
    return Image.Resampling.LANCZOS
