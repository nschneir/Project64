"""ROM identification and the curated C64 ROM label database.

Licensing posture (spec §2): this module ships annotations only — names and
addresses, nothing else. The names follow the long-standing convention of
Commodore's own BASIC/KERNAL sources and the community references built on
them, so a label here reads the same as it does in published documentation.
No ROM bytes and no prose or comment text from any disassembly ever enter the
repo; ROM bytes are read from the USER'S running emulator at runtime.
"""

from __future__ import annotations

import hashlib
from importlib import resources

from .symbols import parse_labels

_LABEL_FILES = {"2.0": "basic2.lbl"}

# BASIC and KERNAL ROMs; char ROM ($D000) is banked under I/O — never hash it.
_REGIONS = {"basic": (0xA000, 0x2000), "kernal": (0xE000, 0x2000)}


def rom_labels(basic_version: str) -> dict[str, int]:
    fname = _LABEL_FILES.get(basic_version)
    if not fname:
        return {}
    text = (resources.files("c64lib") / "data" / "rom_labels" / fname).read_text(encoding="utf-8")
    return parse_labels(text)


def identify(mon) -> dict:
    info = {
        "basic": mon.resource_get("BasicName"),
        "kernal": mon.resource_get("KernalName"),
        "chargen": mon.resource_get("ChargenName"),
    }
    hashes = {}
    for key, (start, length) in _REGIONS.items():
        hashes[key] = hashlib.sha1(mon.memory_read(start, length)).hexdigest()[:12]
    info["hashes"] = hashes
    return info
