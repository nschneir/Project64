import hashlib
from unittest.mock import Mock

from c64lib.romdoc import identify, rom_labels


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
