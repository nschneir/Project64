"""PETSCII character conversions.

Screen RAM holds *screen codes* (not PETSCII): 0='@', 1-26='A'-'Z',
27-31='[' '\\' ']' up-arrow left-arrow, 32-63 match ASCII 0x20-0x3F,
64-127 are graphics glyphs, bit 7 = reverse video.
This is the uppercase/graphics character set; lowercase mode is out of
scope for v1 (tracked for the business-keyboard models).

Decoding styles:

- ``unicode`` (default): graphics map to their Unicode box-drawing /
  block-element / geometric equivalents, so mazes, sprites, and blobs are
  readable straight from ``c64 screen``. Reverse-video codes map to the
  complementary glyph where one exists (▌↔▐, ▄↔▀, quadrant ↔ ¾-block,
  ◣↔◥ …); other reverse codes keep the base glyph, or gain an ANSI
  inverse-video wrap with ``ansi_reverse=True``.
- ``ascii``: the old conservative mapping (graphics collapse to ``·``),
  kept for pipelines that expect pure ASCII.
"""

from __future__ import annotations

_LOW = "@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_"          # codes 0-31 (^ = up arrow, _ = left arrow)
_MID = ' !"#$%&\'()*+,-./0123456789:;<=>?'          # codes 32-63
GRAPHICS_PLACEHOLDER = "·"

# graphics codes with a reasonable pure-ASCII equivalent (legacy style)
_GRAPHICS_ASCII = {64: "-", 66: "|", 91: "+", 96: " "}

# Unicode equivalents for the graphics range 64-127. The load-bearing
# glyphs (arcs, lines, tees, blocks, quadrants, suits, ball/ring/heart,
# diagonal fills) were verified cell-by-cell on a live 4032; the long
# tail of line-weight variants maps to the nearest Unicode form.
_GRAPHICS_UNI = {
    64: "─", 65: "♠", 66: "│", 67: "─", 68: "─", 69: "─", 70: "─",
    71: "│", 72: "│", 73: "╮", 74: "╰", 75: "╯", 76: "└", 77: "╲",
    78: "╱", 79: "┌", 80: "┐", 81: "●", 82: "─", 83: "♥", 84: "│",
    85: "╭", 86: "╳", 87: "○", 88: "♣", 89: "│", 90: "◆", 91: "┼",
    92: "░", 93: "│", 94: "π", 95: "◣",
    96: " ", 97: "▌", 98: "▄", 99: "▔", 100: "▁", 101: "▏", 102: "▒",
    103: "▕", 104: "░", 105: "◤", 106: "▕", 107: "├", 108: "▗",
    109: "└", 110: "┐", 111: "▂", 112: "┌", 113: "┴", 114: "┬",
    115: "┤", 116: "▎", 117: "▍", 118: "▏", 119: "▔", 120: "▃",
    121: "▂", 122: "┘", 123: "▖", 124: "▝", 125: "│", 126: "▘",
    127: "▚",
}

# reverse-video codes whose pixel-complement exists as its own glyph
_REVERSE_UNI = {
    160: "█",                     # reverse space: solid
    209: "◘", 215: "◙",           # inverse ball / ring
    223: "◥", 233: "◢",           # inverse diagonal fills
    225: "▐", 226: "▀",           # inverse half blocks
    230: "▓",                     # inverse checkerboard: denser shade
    236: "▛", 251: "▜", 252: "▙", 254: "▟",  # inverse quadrants: 3/4 blocks
}

_ANSI_REV, _ANSI_OFF = "\x1b[7m", "\x1b[27m"


def screen_code_to_char(code: int, style: str = "unicode",
                        ansi_reverse: bool = False) -> str:
    if style == "unicode" and code >= 128 and code in _REVERSE_UNI:
        return _REVERSE_UNI[code]
    reverse = code >= 128
    base = code & 0x7F
    if base < 32:
        ch = _LOW[base]
    elif base < 64:
        ch = _MID[base - 32]
    elif style == "unicode":
        ch = _GRAPHICS_UNI.get(base, GRAPHICS_PLACEHOLDER)
    else:
        ch = _GRAPHICS_ASCII.get(base, GRAPHICS_PLACEHOLDER)
    if reverse and ansi_reverse and style == "unicode":
        return f"{_ANSI_REV}{ch}{_ANSI_OFF}"
    return ch


def screen_to_text(data: bytes, cols: int, style: str = "unicode",
                   ansi_reverse: bool = False) -> str:
    rows = []
    for i in range(0, len(data), cols):
        row = "".join(screen_code_to_char(c, style, ansi_reverse)
                      for c in data[i : i + cols])
        rows.append(row.rstrip())
    return "\n".join(rows).rstrip("\n")


def ascii_to_petscii(s: str) -> bytes:
    out = bytearray()
    for ch in s:
        if ch in ("\n", "\r"):
            out.append(0x0D)
            continue
        ch = ch.upper()
        code = ord(ch)
        if 0x20 <= code <= 0x5D:  # space..'?', '@', 'A'-'Z', '[' '\\' ']'
            out.append(code)
        else:
            raise ValueError(f"cannot map {ch!r} to PETSCII for keyboard input")
    return bytes(out)
