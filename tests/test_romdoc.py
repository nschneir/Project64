import hashlib
from unittest.mock import Mock

from c64lib.romdoc import identify, rom_labels


def test_rom_labels_basic4_has_jump_table():
    labels = rom_labels("4.0")
    assert labels["CHROUT"] == 0xFFD2
    assert labels["GETIN"] == 0xFFE4
    assert labels["RESET_VEC"] == 0xFFFC
    assert labels["TXTTAB"] == 0x0028


def test_rom_labels_unknown_version_empty():
    assert rom_labels("1.0") == {}


def test_identify_reads_resources_and_hashes():
    mon = Mock()
    mon.resource_get.side_effect = lambda n: {
        "BasicName": "basic-4.bin", "KernalName": "kernal-4.bin",
        "EditorName": "edit-4.bin",
    }[n]
    mon.memory_read.side_effect = lambda start, ln: bytes([start >> 8]) * ln
    info = identify(mon)
    assert info["basic"] == "basic-4.bin"
    assert info["kernal"] == "kernal-4.bin"
    expected = hashlib.sha1(bytes([0xB0]) * 0x3000).hexdigest()[:12]
    assert info["hashes"]["basic"] == expected
    mon.memory_read.assert_any_call(0xB000, 0x3000)
    mon.memory_read.assert_any_call(0xE000, 0x0800)
    mon.memory_read.assert_any_call(0xF000, 0x1000)
