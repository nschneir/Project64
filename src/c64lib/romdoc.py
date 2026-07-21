"""ROM identification and the curated PET ROM label database.

Licensing posture (spec §2): this module ships only annotations we authored
(names + addresses). ROM bytes are read from the USER'S running emulator at
runtime and are never written to the repo.
"""

from __future__ import annotations

import hashlib
from importlib import resources

from .symbols import parse_labels

_LABEL_FILES = {"4.0": "basic4.lbl", "2.0": "basic2.lbl"}

# hash regions skip the I/O window at $E800-$EFFF
_REGIONS = {"basic": (0xB000, 0x3000), "editor": (0xE000, 0x0800), "kernal": (0xF000, 0x1000)}


def rom_labels(basic_version: str) -> dict[str, int]:
    fname = _LABEL_FILES.get(basic_version)
    if not fname:
        return {}
    text = (resources.files("c64lib") / "data" / "rom_labels" / fname).read_text()
    return parse_labels(text)


def identify(mon) -> dict:
    info = {
        "basic": mon.resource_get("BasicName"),
        "kernal": mon.resource_get("KernalName"),
        "editor": mon.resource_get("EditorName"),
    }
    hashes = {}
    for key, (start, length) in _REGIONS.items():
        hashes[key] = hashlib.sha1(mon.memory_read(start, length)).hexdigest()[:12]
    info["hashes"] = hashes
    return info
