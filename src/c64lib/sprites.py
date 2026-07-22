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


def sprite_image(data: bytes, state: SpriteState, shared: dict, scale: int = 1):
    """Render a 63-byte shape to a PIL image (24x21 logical pixels)."""
    from PIL import Image

    img = Image.new("RGB", (24, 21))
    bg = C64_PALETTE[shared["background"]]
    if state.multicolor:
        pair_colors = {0: bg,
                       1: C64_PALETTE[shared["mc_color1"]],
                       2: C64_PALETTE[state.color],
                       3: C64_PALETTE[shared["mc_color2"]]}
    for y in range(21):
        bits = _row_bits(data, y)
        if state.multicolor:
            for p in range(12):
                c = pair_colors[(bits >> (22 - 2 * p)) & 3]
                img.putpixel((2 * p, y), c)
                img.putpixel((2 * p + 1, y), c)
        else:
            fg = C64_PALETTE[state.color]
            for x in range(24):
                img.putpixel((x, y), fg if bits & (1 << (23 - x)) else bg)
    if scale > 1:
        img = img.resize((24 * scale, 21 * scale), Image.NEAREST)
    return img


def _luminance(px) -> float:
    r, g, b = px[0], px[1], px[2]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _nearest_palette(px) -> int:
    return min(range(16), key=lambda i: sum(
        (a - b) ** 2 for a, b in zip(px[:3], C64_PALETTE[i], strict=True)))


def _emit(rows_bytes: list[bytes], header: list[str]) -> list[str]:
    lines = list(header)
    for i, row in enumerate(rows_bytes):
        bits = ", ".join(f"%{b:08b}" for b in row)
        lines.append(f"sprite0: .byte {bits}" if i == 0
                      else f"         .byte {bits}")
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
    edge = [grid[y][x] for y in range(21) for x in range(12)
            if (x in (0, 11) or y in (0, 20)) and grid[y][x] is not None]
    background = max(set(edge), key=edge.count) if edge else 0
    order: list[int] = []
    for y in range(21):
        for x in range(12):
            c = grid[y][x]
            if c is not None and c != background and c not in order:
                order.append(c)
    order = order[:3]
    pair_of = {background: 0, None: 0}
    for i, c in enumerate(order):
        pair_of[c] = i + 1                     # 01, 10, 11 in raster order
    rows = []
    for y in range(21):
        bits = 0
        for x in range(12):
            c = grid[y][x]
            pv = pair_of.get(c)
            if pv is None:                     # extra color: nearest of the 4
                chosen = min([background, *order], key=lambda k: sum(
                    (a - b) ** 2 for a, b in zip(C64_PALETTE[c], C64_PALETTE[k], strict=True)))
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
    return Image.LANCZOS
