"""Sprite decoding, rendering, and PNG conversion (VIC-II sprites).

All shape data is 63 bytes: 21 rows of 3 bytes (24 hires pixels, or 12
double-wide multicolor pixel pairs). Multicolor pair values map to colors
as fixed by the hardware: 00 = background ($D021), 01 = $D025,
10 = the sprite's own color ($D027+n), 11 = $D026.
"""

from __future__ import annotations

from dataclasses import dataclass

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
