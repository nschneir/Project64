"""Read the C64 screen as text (via screen RAM) or as a PNG (via display get)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .machines import MachineProfile
from .monitor import MonitorClient
from .text import screen_to_text


def screen_base(mon: MonitorClient) -> int:
    """The live screen RAM base: VIC bank (CIA2 $DD00 bits 0-1, inverted)
    plus the screen slot in $D018 bits 4-7. Follows programs that relocate
    the screen; $0400 is only the power-on default."""
    bank = (~mon.memory_read(0xDD00, 1)[0]) & 3
    slot = (mon.memory_read(0xD018, 1)[0] >> 4) & 0x0F
    return bank * 0x4000 + slot * 0x0400


def read_screen_text(mon: MonitorClient, profile: MachineProfile,
                     style: str = "unicode", ansi_reverse: bool = False) -> str:
    size = profile.screen_cols * profile.screen_rows
    data = mon.memory_read(screen_base(mon), size)
    return screen_to_text(data, profile.screen_cols, style, ansi_reverse)


def read_screen_codes(mon: MonitorClient, profile: MachineProfile) -> list[list[int]]:
    """The raw screen-code matrix (rows x cols) — exact values for
    asserting on glyphs without decoding ambiguity."""
    size = profile.screen_cols * profile.screen_rows
    data = mon.memory_read(screen_base(mon), size)
    c = profile.screen_cols
    return [list(data[i:i + c]) for i in range(0, size, c)]


def save_screenshot_png(mon: MonitorClient, path: str | Path,
                        scale: int = 1, border: bool = False) -> tuple[int, int]:
    """Save the emulated display as a PNG. By default captures the 320x200
    inner screen; border=True captures the whole frame, so `POKE 53280`
    border colors are visible."""
    width, height, pixels = mon.display(full=border)
    palette = mon.palette()
    img = Image.new("P", (width, height))
    flat = []
    for r, g, b in palette:
        flat += [r, g, b]
    img.putpalette(flat)
    img.putdata(list(pixels))
    if scale > 1:                     # nearest-neighbour: crisp fat pixels
        img = img.resize((width * scale, height * scale), Image.NEAREST)
    img.save(Path(path), format="PNG")
    return img.width, img.height
