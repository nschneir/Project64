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
from collections import Counter
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
        """Which window this packet occupies.

        "lo" for the $8000 window, "hi" for $A000 — and for the $E000 that same
        window maps to in Ultimax mode.
        """
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
        if size > total - CHIP_HEADER_LEN:
            raise CartError(
                f"{path}: CHIP packet at ${off:06x} declares {size} data bytes "
                f"but the packet holds only {total - CHIP_HEADER_LEN} — "
                f"malformed image")
        start = off + CHIP_HEADER_LEN
        chips.append(Chip(bank=_u16(raw, off + 10), load_addr=_u16(raw, off + 12),
                          size=size, chip_type=_u16(raw, off + 8), offset=off,
                          data=raw[start:start + size]))
        off += total
    # The name field is a fixed 32 bytes: cartconv NUL-terminates it, but other
    # writers pad with spaces, so strip both rather than report "GAME        ".
    name = (raw[0x20:0x20 + CRT_NAME_LEN].split(b"\x00")[0]
            .decode("ascii", "replace").rstrip())
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
    """The bytes of one CHIP packet — packet-granular, not window-granular.

    A 16K cartridge is normally ONE $4000 packet loaded at $8000 (measured
    cartconv output), so `window="lo"` returns all 16384 bytes and
    `window="hi"` raises: there is no second packet to name. The container also
    permits a two-packet $8000/$A000 16K layout, and for such an image the two
    windows dump separately, 8192 bytes each.
    """
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


CARTCONV_TIMEOUT = 120                # a 1 MB EasyFlash convert takes ~1s


def run_cartconv(args: list[str]) -> str:
    exe = _cartconv()
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True,
                           timeout=CARTCONV_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise CartError(
            f"cartconv did not finish within {CARTCONV_TIMEOUT}s "
            f"({' '.join(args)})") from None
    except UnicodeDecodeError as e:
        # cartconv's output is ASCII in every measured case, but a corrupt
        # image can make it echo raw bytes — an environment failure, not a
        # traceback the caller should have to decode.
        raise CartError(f"cartconv produced undecodable output: {e}") from None
    except OSError as e:
        raise CartError(f"cannot run cartconv ({exe}): {e}") from None
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
    try:
        size = raw.stat().st_size
    except OSError as e:
        raise CartError(f"{raw}: {e}") from None
    if size != ct.image_bytes:
        raise CartError(
            f"{raw}: {size} bytes, but a {ct.name} image must be exactly "
            f"{ct.image_bytes} bytes")
    # The name field is 32 BYTES, not 32 characters: a non-ASCII title fits
    # fewer letters than it looks like it should.
    n_bytes = len(name.encode("utf-8"))
    if n_bytes > CRT_NAME_LEN:
        raise CartError(
            f"cartridge name {name!r} is {n_bytes} bytes; the .crt name "
            f"field holds {CRT_NAME_LEN}")
    run_cartconv(["-t", ct.cartconv_type, "-i", str(raw), "-o", str(out),
                  "-n", name])
    return out


# "CBM80" in the PETSCII form the KERNAL reset routine scans for at $8004.
CBM80_SIGNATURE = bytes([0xC3, 0xC2, 0xCD, 0x38, 0x30])

_GENERIC_SIZES = (0x2000, 0x3000, 0x4000)


def _vector(data: bytes, offset: int) -> int | None:
    if len(data) < offset + 2:
        return None
    return int.from_bytes(data[offset:offset + 2], "little")


def _verify_cbm80_boot(chip: Chip, top: int) -> list[str]:
    """The autostart header an 8K/16K cartridge boots through, at $8000."""
    reasons: list[str] = []
    if chip.data[4:9] != CBM80_SIGNATURE:
        reasons.append(
            "no CBM80 autostart signature at $8004: the KERNAL will ignore "
            "this cartridge and boot to BASIC")
    cold = _vector(chip.data, 0)
    if cold is not None and not (chip.load_addr <= cold <= top):
        # Named from the packet, not hard-coded: a misplaced image's cold
        # vector is at the front of wherever it actually loads.
        reasons.append(
            f"cold vector ${cold:04X} at ${chip.load_addr:04X} points outside "
            f"the cartridge (${chip.load_addr:04X}-${top:04X})")
    return reasons


def _verify_split_16k(crt: Crt) -> list[str]:
    """The two-packet 16K layout: $8000 and $A000, 8192 bytes each.

    Our builder emits the single $4000 packet cartconv produces, but the
    container permits the split form and real-world images use it — reporting
    one as broken would be a false positive, not a caught bug.
    """
    reasons: list[str] = []
    lo, hi = sorted(crt.chips, key=lambda c: c.load_addr)
    if (lo.load_addr, hi.load_addr) != (ROML_ADDR, ROMH_ADDR):
        reasons.append(
            f"a two-packet 16K cartridge loads at $8000 and $A000; this one "
            f"loads at ${lo.load_addr:04X} and ${hi.load_addr:04X}")
        return reasons
    for chip in (lo, hi):
        if chip.size != BANK_WINDOW:
            reasons.append(
                f"the ${chip.load_addr:04X} packet of a two-packet 16K "
                f"cartridge is {BANK_WINDOW} bytes; this one is "
                f"{chip.size} bytes")
    return reasons + _verify_cbm80_boot(lo, ROMH_ADDR + hi.size - 1)


def _verify_generic(crt: Crt) -> list[str]:
    reasons: list[str] = []
    # parse_crt guarantees chip.size == len(chip.data) for every packet it
    # returns (it rejects a size field that overruns its packet), so there is
    # no declares-vs-carries case left to check here.
    if len(crt.chips) == 2 and crt.mode == "16k":
        return _verify_split_16k(crt)
    if len(crt.chips) != 1:
        reasons.append(
            f"a generic cartridge holds one CHIP packet (or, for 16K, two: "
            f"$8000 and $A000); this image has {len(crt.chips)} CHIP packets")
        return reasons
    chip = crt.chips[0]
    if crt.mode == "ultimax":
        if chip.load_addr != ULTIMAX_ROMH_ADDR:
            reasons.append(
                f"an Ultimax cartridge maps ROMH at $E000; this one loads at "
                f"${chip.load_addr:04X}")
        if chip.size != BANK_WINDOW:
            reasons.append(
                f"an Ultimax cartridge is {BANK_WINDOW} bytes; this one is "
                f"{chip.size} bytes")
        if reasons:
            # The reset vector lives in the last words of a correctly placed
            # $2000 window. With the geometry already wrong there is no such
            # address, so reading one would report a second, invented fault.
            return reasons
        vec_addr = chip.load_addr + BANK_WINDOW - 4
        reset = _vector(chip.data, 0x1FFC)
        if reset is not None and not (ULTIMAX_ROMH_ADDR <= reset <= 0xFFFF):
            reasons.append(
                f"reset vector ${reset:04X} at ${vec_addr:04X} points outside "
                f"the ROMH window ($E000-$FFFF) — the CPU will start executing "
                f"RAM")
        return reasons
    if chip.load_addr != ROML_ADDR:
        reasons.append(
            f"an 8K/16K cartridge maps ROML at $8000; this one loads at "
            f"${chip.load_addr:04X}")
    if chip.size not in _GENERIC_SIZES:
        sizes = ", ".join(str(s) for s in _GENERIC_SIZES)
        reasons.append(
            f"a generic cartridge is {sizes} bytes; this one is {chip.size} bytes")
    return reasons + _verify_cbm80_boot(chip, chip.load_addr + chip.size - 1)


def _verify_easyflash(crt: Crt) -> list[str]:
    reasons: list[str] = []
    counts = Counter((c.bank, c.window) for c in crt.chips)
    for (bank, window), n in counts.items():
        # One duplicated window is one fault, however many copies carry it:
        # reporting per extra packet said "appears twice" twice for a triple.
        if n > 1:
            times = "twice" if n == 2 else f"{n} times"
            reasons.append(f"bank {bank} {window} appears {times}")
    for chip in crt.chips:
        if not 0 <= chip.bank < EF_MAX_BANKS:
            reasons.append(
                f"bank {chip.bank} is outside the EasyFlash range "
                f"(0-{EF_MAX_BANKS - 1})")
        if chip.load_addr not in (ROML_ADDR, ROMH_ADDR):
            reasons.append(
                f"bank {chip.bank} loads at ${chip.load_addr:04X}; EasyFlash "
                f"windows are $8000 and $A000")
        if chip.size != BANK_WINDOW:
            reasons.append(
                f"bank {chip.bank} {chip.window} is {chip.size} bytes; every "
                f"EasyFlash window is {BANK_WINDOW} bytes")
    # "off" is one cause with one reason: cart_verify already reported that
    # neither line is asserted, and saying it again in EasyFlash words makes a
    # single wrong header byte look like two independent faults.
    if crt.mode not in ("ultimax", "off"):
        reasons.append(
            f"an EasyFlash cartridge boots in Ultimax mode (EXROM=1, GAME=0); "
            f"this image declares {crt.mode}")
    boot = crt.chip(0, "hi")
    if boot is None:
        reasons.append(
            "an EasyFlash cartridge boots through the reset vector at $FFFC, "
            "which lives in bank 0's HIROM window — but bank 0 has no HIROM "
            "packet")
    else:
        reset = _vector(boot.data, 0x1FFC)
        if reset is not None and not (ULTIMAX_ROMH_ADDR <= reset <= 0xFFFF):
            reasons.append(
                f"reset vector ${reset:04X} at $FFFC points outside the ROMH "
                f"window ($E000-$FFFF)")
    return reasons


def cart_verify(path: str | Path) -> list[str]:
    """Static pre-flight for a .crt: [] means it should boot.

    Every rule here corresponds to a failure that is silent on real hardware —
    a cartridge with no CBM80 signature simply boots to BASIC, and an EasyFlash
    with no bank 0 HIROM never runs a single instruction.
    """
    crt = parse_crt(path)
    reasons: list[str] = []
    if not crt.chips:
        reasons.append("image contains no CHIP packets")
        return reasons
    if crt.mode == "off":
        reasons.append(
            "EXROM and GAME are both inactive: nothing will be mapped")
    if crt.hardware == HW_EASYFLASH:
        reasons += _verify_easyflash(crt)
    elif crt.hardware == HW_GENERIC:
        reasons += _verify_generic(crt)
    else:
        reasons.append(
            f"hardware type {crt.hardware} is not one this tool builds; "
            f"`c64 cart info` still decodes it")
    return reasons
