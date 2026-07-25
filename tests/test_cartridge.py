import pytest

from c64lib.cartridge import (
    CartError,
    Chip,
    cart_dump,
    cart_info,
    describe_mode,
    parse_crt,
)


def chip_packet(bank: int, addr: int, data: bytes, chip_type: int = 0) -> bytes:
    return (b"CHIP"
            + (16 + len(data)).to_bytes(4, "big")
            + chip_type.to_bytes(2, "big")
            + bank.to_bytes(2, "big")
            + addr.to_bytes(2, "big")
            + len(data).to_bytes(2, "big")
            + data)


def make_crt(tmp_path, *, name="TESTCART", hardware=0, exrom=0, game=1,
             chips=(), filename="test.crt"):
    """A .crt built from the measured layout: 16-byte magic, $40 header,
    then back-to-back CHIP packets."""
    header = bytearray(b"C64 CARTRIDGE   ")
    header += (0x40).to_bytes(4, "big")
    header += bytes([0x01, 0x00])
    header += hardware.to_bytes(2, "big")
    header += bytes([exrom, game])
    header += bytes(6)
    header += name.encode("ascii").ljust(32, b"\x00")
    assert len(header) == 0x40
    path = tmp_path / filename
    path.write_bytes(bytes(header) + b"".join(chips))
    return path


def test_parses_a_plain_8k_cart(tmp_path):
    body = bytes([0x09, 0x80, 0x09, 0x80, 0xC3, 0xC2, 0xCD, 0x38, 0x30])
    body = body.ljust(0x2000, b"\xFF")
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, body)])
    crt = parse_crt(path)
    assert crt.name == "TESTCART"
    assert (crt.hardware, crt.exrom, crt.game) == (0, 0, 1)
    assert crt.version == (1, 0)
    assert crt.mode == "8k"
    assert crt.banks == (0,)
    assert len(crt.chips) == 1
    assert crt.chips[0].load_addr == 0x8000 and crt.chips[0].size == 0x2000


def test_sixteen_k_is_one_four_thousand_byte_packet(tmp_path):
    # Measured: cartconv emits ONE $4000 packet for a 16K cart, not two.
    path = make_crt(tmp_path, game=0,
                    chips=[chip_packet(0, 0x8000, b"\xFF" * 0x4000)])
    crt = parse_crt(path)
    assert crt.mode == "16k"
    assert len(crt.chips) == 1 and crt.chips[0].size == 0x4000


def test_parses_easyflash_banks_and_windows(tmp_path):
    chips = [chip_packet(0, 0xA000, b"\xFF" * 0x2000, chip_type=2),
             chip_packet(2, 0x8000, b"A" + b"\xFF" * 0x1FFF, chip_type=2),
             chip_packet(2, 0xA000, b"a" + b"\xFF" * 0x1FFF, chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    crt = parse_crt(path)
    assert crt.mode == "ultimax"          # EasyFlash boots in Ultimax
    assert crt.banks == (0, 2)            # sparse banks are normal output
    assert crt.chip(2, "lo").data[:1] == b"A"
    assert crt.chip(2, "hi").data[:1] == b"a"
    assert crt.chip(1, "lo") is None


def test_window_property_splits_on_a000():
    assert Chip(0, 0x8000, 1, 0, 0, b"x").window == "lo"
    assert Chip(0, 0xA000, 1, 0, 0, b"x").window == "hi"
    assert Chip(0, 0xE000, 1, 0, 0, b"x").window == "hi"


def test_describe_mode_covers_every_line_pair():
    assert describe_mode(0, 1) == "8k"
    assert describe_mode(0, 0) == "16k"
    assert describe_mode(1, 0) == "ultimax"
    assert describe_mode(1, 1) == "off"


def test_rejects_a_file_that_is_not_a_crt(tmp_path):
    p = tmp_path / "nope.crt"
    p.write_bytes(b"not a cartridge at all, really")
    with pytest.raises(CartError, match="not a .crt image"):
        parse_crt(p)


def test_rejects_a_truncated_chip_packet(tmp_path):
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, b"\xFF" * 0x2000)])
    path.write_bytes(path.read_bytes()[:5000])       # cut mid-packet
    with pytest.raises(CartError, match="truncated"):
        parse_crt(path)


def test_rejects_garbage_where_a_chip_packet_should_start(tmp_path):
    path = make_crt(tmp_path, chips=[b"XXXX" + bytes(24)])
    with pytest.raises(CartError, match="expected a CHIP packet"):
        parse_crt(path)


def test_cart_info_reports_header_and_every_packet(tmp_path):
    chips = [chip_packet(0, 0xA000, b"\xFF" * 0x2000, chip_type=2),
             chip_packet(5, 0x8000, b"\xFF" * 0x2000, chip_type=2)]
    path = make_crt(tmp_path, name="EFTEST", hardware=32, exrom=1, game=0,
                    chips=chips)
    info = cart_info(path)
    assert info["name"] == "EFTEST"
    assert info["hardware"] == 32
    assert info["hardware_name"] == "EasyFlash"
    assert info["mode"] == "ultimax"
    assert info["banks"] == [0, 5]
    assert info["chips"][1] == {"bank": 5, "window": "lo", "load_addr": "$8000",
                                "size": 8192, "type": "flash", "offset": 8272}


def test_cart_dump_extracts_one_window(tmp_path):
    chips = [chip_packet(1, 0x8000, b"L" + b"\xFF" * 0x1FFF, chip_type=2),
             chip_packet(1, 0xA000, b"H" + b"\xFF" * 0x1FFF, chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    assert cart_dump(path, 1, "lo")[:1] == b"L"
    assert cart_dump(path, 1, "hi")[:1] == b"H"


def test_cart_dump_names_the_missing_bank(tmp_path):
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, b"\xFF" * 0x2000)])
    with pytest.raises(CartError, match="no lo window in bank 3"):
        cart_dump(path, 3, "lo")
