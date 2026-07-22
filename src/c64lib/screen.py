"""Read the C64 screen as text (via screen RAM) or as a PNG (via display get)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .machines import MachineProfile
from .monitor import MonitorClient
from .text import screen_to_text


def read_screen_text(mon: MonitorClient, profile: MachineProfile,
                     style: str = "unicode", ansi_reverse: bool = False) -> str:
    size = profile.screen_cols * profile.screen_rows
    data = mon.memory_read(profile.screen_addr, size)
    return screen_to_text(data, profile.screen_cols, style, ansi_reverse)


def read_screen_codes(mon: MonitorClient, profile: MachineProfile) -> list[list[int]]:
    """The raw screen-code matrix (rows x cols) — exact values for
    asserting on glyphs without decoding ambiguity."""
    size = profile.screen_cols * profile.screen_rows
    data = mon.memory_read(profile.screen_addr, size)
    c = profile.screen_cols
    return [list(data[i:i + c]) for i in range(0, size, c)]


def save_screenshot_png(mon: MonitorClient, path: str | Path,
                        scale: int = 1) -> tuple[int, int]:
    width, height, pixels = mon.display()
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
