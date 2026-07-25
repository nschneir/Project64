"""Commodore 64 cartridge images (.crt).

The container is a documented binary format, so info/verify/dump parse it
directly — no cartconv round trip. Only *building* an image shells out, the
same way build.py wraps ca65/ld65.

Layout measured against VICE 3.10 cartconv output:
16-byte magic, big-endian header length ($40), version, hardware type,
EXROM/GAME line bytes, a 32-byte name, then back-to-back CHIP packets.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class CartError(Exception):
    pass


CRT_MAGIC = b"C64 CARTRIDGE   "       # the trailing spaces are part of it
CRT_HEADER_LEN = 0x40
CRT_NAME_LEN = 32
CHIP_MAGIC = b"CHIP"
CHIP_HEADER_LEN = 16

CHIP_ROM, CHIP_RAM, CHIP_FLASH = 0, 1, 2
_CHIP_TYPE_NAMES = {CHIP_ROM: "rom", CHIP_RAM: "ram", CHIP_FLASH: "flash"}

HW_GENERIC = 0
HW_EASYFLASH = 32
_HW_NAMES = {HW_GENERIC: "Generic C64 Cartridge", HW_EASYFLASH: "EasyFlash"}

BANK_WINDOW = 0x2000                  # every cartridge window is 8 KiB
ROML_ADDR = 0x8000
ROMH_ADDR = 0xA000
ULTIMAX_ROMH_ADDR = 0xE000
EF_MAX_BANKS = 64
EF_IMAGE_BYTES = EF_MAX_BANKS * 2 * BANK_WINDOW      # cartconv accepts only this


@dataclass(frozen=True)
class CartType:
    """Geometry for one supported cartridge type.

    `cartconv_type` is the string cartconv actually accepts: measured, it
    rejects "ultimax" and "easyflash" in favour of "ulti" and "easy".
    """

    name: str
    cartconv_type: str
    hardware: int
    exrom: int
    game: int
    windows: tuple[int, ...]          # load addresses, in image order
    max_banks: int
    image_bytes: int                  # exact raw size cartconv demands


CART_TYPES: dict[str, CartType] = {
    "8k": CartType("8k", "normal", HW_GENERIC, 0, 1, (ROML_ADDR,), 1, 0x2000),
    "16k": CartType("16k", "normal", HW_GENERIC, 0, 0,
                    (ROML_ADDR, ROMH_ADDR), 1, 0x4000),
    "ultimax": CartType("ultimax", "ulti", HW_GENERIC, 1, 0,
                        (ULTIMAX_ROMH_ADDR,), 1, 0x2000),
    "easyflash": CartType("easyflash", "easy", HW_EASYFLASH, 1, 0,
                          (ROML_ADDR, ROMH_ADDR), EF_MAX_BANKS, EF_IMAGE_BYTES),
}


def get_cart_type(name: str) -> CartType:
    try:
        return CART_TYPES[name]
    except KeyError:
        raise CartError(
            f"unknown cartridge type {name!r}; available: "
            f"{', '.join(sorted(CART_TYPES))}"
        ) from None


def describe_mode(exrom: int, game: int) -> str:
    """Decode the EXROM/GAME line pair into a memory mode. 0 = asserted."""
    return {(0, 1): "8k", (0, 0): "16k", (1, 0): "ultimax",
            (1, 1): "off"}.get((exrom, game), "unknown")


@dataclass(frozen=True)
class Chip:
    bank: int
    load_addr: int
    size: int
    chip_type: int
    offset: int                       # byte offset of the packet in the file
    data: bytes

    @property
    def window(self) -> str:
        """"lo" for the $8000 window, "hi" for $A000 (and the $E000 the same
        window maps to in Ultimax mode)."""
        return "hi" if self.load_addr >= ROMH_ADDR else "lo"


@dataclass(frozen=True)
class Crt:
    path: Path
    name: str
    hardware: int
    exrom: int
    game: int
    version: tuple[int, int]
    chips: tuple[Chip, ...]

    @property
    def mode(self) -> str:
        return describe_mode(self.exrom, self.game)

    @property
    def banks(self) -> tuple[int, ...]:
        return tuple(sorted({c.bank for c in self.chips}))

    def chip(self, bank: int, window: str) -> Chip | None:
        for c in self.chips:
            if c.bank == bank and c.window == window:
                return c
        return None


def _u16(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o + 2], "big")


def _u32(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o + 4], "big")


def parse_crt(path: str | Path) -> Crt:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise CartError(f"{path}: {e}") from None
    if len(raw) < CRT_HEADER_LEN or raw[:len(CRT_MAGIC)] != CRT_MAGIC:
        raise CartError(
            f"{path}: not a .crt image (missing the 'C64 CARTRIDGE' signature)")
    hdr_len = _u32(raw, 0x10)
    if hdr_len < CRT_HEADER_LEN or hdr_len > len(raw):
        raise CartError(
            f"{path}: header length {hdr_len} is out of range for a "
            f"{len(raw)}-byte file")
    chips: list[Chip] = []
    off = hdr_len
    while off < len(raw):
        if raw[off:off + 4] != CHIP_MAGIC:
            raise CartError(
                f"{path}: expected a CHIP packet at offset ${off:06x}, "
                f"found {raw[off:off + 4]!r}")
        total = _u32(raw, off + 4)
        if total < CHIP_HEADER_LEN or off + total > len(raw):
            raise CartError(
                f"{path}: CHIP packet at ${off:06x} claims {total} bytes but "
                f"only {len(raw) - off} remain — truncated image")
        size = _u16(raw, off + 14)
        start = off + CHIP_HEADER_LEN
        chips.append(Chip(bank=_u16(raw, off + 10), load_addr=_u16(raw, off + 12),
                          size=size, chip_type=_u16(raw, off + 8), offset=off,
                          data=raw[start:start + size]))
        off += total
    name = raw[0x20:0x20 + CRT_NAME_LEN].split(b"\x00")[0].decode("ascii", "replace")
    return Crt(path=path, name=name, hardware=_u16(raw, 0x16),
               exrom=raw[0x18], game=raw[0x19],
               version=(raw[0x14], raw[0x15]), chips=tuple(chips))


def cart_info(path: str | Path) -> dict:
    crt = parse_crt(path)
    return {
        "path": str(crt.path),
        "name": crt.name,
        "hardware": crt.hardware,
        "hardware_name": _HW_NAMES.get(crt.hardware, f"type {crt.hardware}"),
        "version": f"{crt.version[0]}.{crt.version[1]}",
        "exrom": crt.exrom,
        "game": crt.game,
        "mode": crt.mode,
        "banks": list(crt.banks),
        "chips": [
            {"bank": c.bank, "window": c.window, "load_addr": f"${c.load_addr:04X}",
             "size": c.size, "type": _CHIP_TYPE_NAMES.get(c.chip_type, str(c.chip_type)),
             "offset": c.offset}
            for c in crt.chips
        ],
        "total_bytes": sum(c.size for c in crt.chips),
    }


def cart_dump(path: str | Path, bank: int, window: str = "lo") -> bytes:
    if window not in ("lo", "hi"):
        raise CartError(f"window must be 'lo' or 'hi', not {window!r}")
    crt = parse_crt(path)
    chip = crt.chip(bank, window)
    if chip is None:
        have = ", ".join(f"{c.bank}{c.window}" for c in crt.chips) or "none"
        raise CartError(
            f"{crt.path}: no {window} window in bank {bank} (present: {have})")
    return chip.data


def _cartconv() -> str:
    exe = os.environ.get("C64_TOOLS_CARTCONV") or shutil.which("cartconv")
    if not exe:
        raise CartError(
            "cartconv not found. It ships with VICE — install VICE 3.5+ "
            "(macOS: brew install vice; Debian/Ubuntu: apt install vice) "
            "or set C64_TOOLS_CARTCONV."
        )
    return exe


def run_cartconv(args: list[str]) -> str:
    r = subprocess.run([_cartconv(), *args], capture_output=True, text=True)
    out = r.stdout + r.stderr
    # cartconv exits 0 even for "this file seems broken" (measured), so treat
    # any Error: line as a failure regardless of the return code.
    if r.returncode != 0 or "Error:" in out:
        raise CartError(f"cartconv failed ({' '.join(args)}):\n{out.strip()}")
    return out


def bin_to_crt(raw: str | Path, out: str | Path, cart_type: str,
               name: str) -> Path:
    """Convert an exactly-sized raw ROM image to a .crt."""
    ct = get_cart_type(cart_type)
    raw, out = Path(raw), Path(out)
    size = raw.stat().st_size
    if size != ct.image_bytes:
        raise CartError(
            f"{raw}: {size} bytes, but a {ct.name} image must be exactly "
            f"{ct.image_bytes} bytes")
    if len(name) > CRT_NAME_LEN:
        raise CartError(
            f"cartridge name {name!r} is {len(name)} chars; the .crt name "
            f"field holds {CRT_NAME_LEN}")
    run_cartconv(["-t", ct.cartconv_type, "-i", str(raw), "-o", str(out),
                  "-n", name])
    return out
