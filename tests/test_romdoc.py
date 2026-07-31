import hashlib
import re
from importlib import resources
from unittest.mock import Mock

import pytest

from c64lib import romdoc
from c64lib.romdoc import identify, rom_labels
from c64lib.symbols import parse_labels

#: Where a C64 label can legitimately point: zero page, the BASIC/KERNAL
#: work areas and vectors, the two ROMs, and the I/O block. Anything else
#: (the stack, screen RAM, the RAM under BASIC) is either not a fixed
#: address or not something a ROM label should be naming.
_LEGAL_RANGES = ((0x0000, 0x00FF), (0x0200, 0x03FF),
                 (0xA000, 0xBFFF), (0xD000, 0xDFFF), (0xE000, 0xFFFF))

_LINE_RE = re.compile(r"^al C:([0-9a-f]{4}) \.([A-Z0-9_]+)$")


def _label_file_text(fname: str) -> str:
    return (resources.files("c64lib") / "data" / "rom_labels" / fname).read_text()


@pytest.mark.parametrize("fname", sorted(romdoc._LABEL_FILES.values()))
def test_label_file_hygiene(fname):
    """Every shipped label file parses, is unique both ways, and points
    somewhere a C64 label can legitimately point.

    The DB is hand-authored and grows a tranche at a time, so the failure
    modes are clerical: a typo'd line that silently parses to nothing, a
    name reused at a second address (the later line wins and the earlier
    label vanishes from lookups), two names for one address, or a digit
    dropped from an address so it lands in the RAM under BASIC.
    """
    text = _label_file_text(fname)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    labels = parse_labels(text)

    # every non-blank line is a label line in the file's house format --
    # `al C:xxxx .NAME`, lowercase hex, uppercase name
    matched = [(ln, _LINE_RE.match(ln)) for ln in lines]
    bad = [ln for ln, m in matched if m is None]
    assert not bad, f"{fname}: malformed lines: {bad}"
    assert len(labels) == len(lines), f"{fname}: {len(lines)} lines parsed to " \
                                     f"{len(labels)} labels"

    # `m is not None` for every line — that is what the assert above just
    # established. Matching once and reusing it also drops two extra regex
    # passes over the whole label file.
    hits = [m for _, m in matched if m is not None]
    names = [m.group(2) for m in hits]
    dup_names = sorted({n for n in names if names.count(n) > 1})
    assert not dup_names, f"{fname}: duplicate names: {dup_names}"

    addrs = [int(m.group(1), 16) for m in hits]
    dup_addrs = sorted({f"${a:04x}" for a in addrs if addrs.count(a) > 1})
    assert not dup_addrs, f"{fname}: duplicate addresses: {dup_addrs}"

    illegal = [f"{n} ${a:04x}" for n, a in zip(names, addrs, strict=True)
               if not any(lo <= a <= hi for lo, hi in _LEGAL_RANGES)]
    assert not illegal, f"{fname}: addresses outside the legal ranges: {illegal}"


@pytest.mark.parametrize("fname", sorted(romdoc._LABEL_FILES.values()))
def test_label_file_is_address_ordered(fname):
    """Address order is how the file is read and edited: a new label goes
    beside its neighbours, which is what makes a wrong region obvious."""
    addrs = [int(m.group(1), 16) for m in
             (_LINE_RE.match(ln) for ln in _label_file_text(fname).splitlines()
              if ln.strip()) if m]
    assert addrs == sorted(addrs), f"{fname}: labels are not in address order"


def test_rom_labels_basic2_has_jump_table():
    labels = rom_labels("2.0")
    assert labels["CHROUT"] == 0xFFD2
    assert labels["GETIN"] == 0xFFE4
    assert labels["PLOT"] == 0xFFF0
    assert labels["SCNKEY"] == 0xFF9F
    assert labels["RESET_VEC"] == 0xFFFC
    assert labels["TXTTAB"] == 0x002B


def test_rom_labels_unknown_version_empty():
    assert rom_labels("4.0") == {}
    assert rom_labels("1.0") == {}


def test_rom_labels_basic2_has_dispatch_tables():
    labels = rom_labels("2.0")
    assert labels["STMDSP"] == 0xA00C
    assert labels["FUNDSP"] == 0xA052
    assert labels["OPTAB"] == 0xA080
    assert labels["RESLST"] == 0xA09E
    assert labels["GOTO"] == 0xA8A0
    assert labels["LIST"] == 0xA69C
    assert labels["LOAD_STMT"] == 0xE168


def test_rom_labels_basic2_has_function_handlers():
    labels = rom_labels("2.0")
    assert labels["SGN"] == 0xBC39
    assert labels["USR"] == 0x0310
    assert labels["CHRD"] == 0xB6EC
    assert labels["MIDD"] == 0xB737
    assert labels["RND"] == 0xE097


def test_identify_reads_resources_and_hashes():
    mon = Mock()
    mon.resource_get.side_effect = lambda n: {
        "BasicName": "basic-901226-01.bin", "KernalName": "kernal-901227-03.bin",
        "ChargenName": "chargen-901225-01.bin",
    }[n]
    mon.memory_read.side_effect = lambda start, ln: bytes([start >> 8]) * ln
    info = identify(mon)
    assert info["basic"] == "basic-901226-01.bin"
    assert info["kernal"] == "kernal-901227-03.bin"
    assert info["chargen"] == "chargen-901225-01.bin"
    expected = hashlib.sha1(bytes([0xA0]) * 0x2000).hexdigest()[:12]
    assert info["hashes"]["basic"] == expected
    assert set(info["hashes"]) == {"basic", "kernal"}
    mon.memory_read.assert_any_call(0xA000, 0x2000)
    mon.memory_read.assert_any_call(0xE000, 0x2000)
