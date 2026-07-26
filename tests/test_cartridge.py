import subprocess

import pytest

from c64lib import cartridge as cart_mod
from c64lib.cartridge import (
    CBM80_SIGNATURE,
    CartError,
    Chip,
    bin_to_crt,
    cart_dump,
    cart_info,
    cart_verify,
    describe_mode,
    get_cart_type,
    parse_crt,
    run_cartconv,
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


def test_rejects_a_chip_packet_whose_size_field_overruns_the_packet(tmp_path):
    # A size field bigger than the packet body bleeds into the NEXT packet.
    # The file length still adds up, so the truncation check cannot see it.
    first = bytearray(chip_packet(0, 0x8000, b"\xFF" * 0x2000))
    first[14:16] = (0x3000).to_bytes(2, "big")   # claims $3000, carries $2000
    path = make_crt(tmp_path, chips=[bytes(first),
                                     chip_packet(1, 0x8000, b"\xFF" * 0x2000)])
    with pytest.raises(CartError, match="declares 12288 data bytes"):
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


def good_8k_body(entry=0x8009):
    body = bytearray(b"\xFF" * 0x2000)
    body[0:2] = entry.to_bytes(2, "little")      # cold vector
    body[2:4] = entry.to_bytes(2, "little")      # warm vector
    body[4:9] = CBM80_SIGNATURE
    return bytes(body)


def ef_hi_body(reset=0xE010):
    body = bytearray(b"\xFF" * 0x2000)
    body[0x1FFA:0x1FFC] = reset.to_bytes(2, "little")   # NMI
    body[0x1FFC:0x1FFE] = reset.to_bytes(2, "little")   # RESET
    body[0x1FFE:0x2000] = reset.to_bytes(2, "little")   # IRQ
    return bytes(body)


def test_verify_passes_a_well_formed_8k_cart(tmp_path):
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, good_8k_body())])
    assert cart_verify(path) == []


def test_verify_catches_a_missing_cbm80_signature(tmp_path):
    body = bytearray(good_8k_body())
    body[4:9] = b"\xFF" * 5
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, bytes(body))])
    reasons = cart_verify(path)
    assert len(reasons) == 1
    # Measured: without it the KERNAL boots straight to BASIC and says nothing.
    assert "CBM80" in reasons[0] and "boot to BASIC" in reasons[0]


def test_verify_catches_a_cold_vector_outside_the_window(tmp_path):
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, good_8k_body(0x1234))])
    assert any("cold vector $1234" in r for r in cart_verify(path))


def test_verify_catches_a_wrong_sized_generic_image(tmp_path):
    path = make_crt(tmp_path,
                    chips=[chip_packet(0, 0x8000, good_8k_body()[:0x1000])])
    assert any("4096 bytes" in r for r in cart_verify(path))


def test_verify_catches_a_generic_cart_with_extra_packets(tmp_path):
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, good_8k_body()),
                                     chip_packet(1, 0x8000, good_8k_body())])
    assert any("2 CHIP packets" in r for r in cart_verify(path))


def test_verify_checks_the_ultimax_reset_vector(tmp_path):
    body = bytearray(b"\xFF" * 0x2000)
    body[0x1FFC:0x1FFE] = (0x0801).to_bytes(2, "little")   # points at RAM
    path = make_crt(tmp_path, exrom=1, game=0,
                    chips=[chip_packet(0, 0xE000, bytes(body))])
    assert any("reset vector $0801" in r for r in cart_verify(path))


def test_verify_passes_a_well_formed_easyflash(tmp_path):
    chips = [chip_packet(0, 0xA000, ef_hi_body(), chip_type=2),
             chip_packet(0, 0x8000, b"\xFF" * 0x2000, chip_type=2),
             chip_packet(7, 0x8000, b"\xFF" * 0x2000, chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    assert cart_verify(path) == []       # sparse bank 7 is fine, not a gap


def test_verify_requires_easyflash_bank_zero_hi(tmp_path):
    # Measured: EasyFlash boots through $FFFC in bank 0's HIROM window.
    chips = [chip_packet(0, 0x8000, b"\xFF" * 0x2000, chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    assert any("bank 0 has no HIROM" in r for r in cart_verify(path))


def test_verify_catches_duplicate_bank_windows(tmp_path):
    chips = [chip_packet(0, 0xA000, ef_hi_body(), chip_type=2),
             chip_packet(3, 0x8000, b"\xFF" * 0x2000, chip_type=2),
             chip_packet(3, 0x8000, b"\xFF" * 0x2000, chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    assert any("bank 3 lo appears twice" in r for r in cart_verify(path))


def test_verify_catches_an_out_of_range_bank(tmp_path):
    chips = [chip_packet(0, 0xA000, ef_hi_body(), chip_type=2),
             chip_packet(70, 0x8000, b"\xFF" * 0x2000, chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    assert any("bank 70" in r for r in cart_verify(path))


def test_verify_catches_both_lines_inactive(tmp_path):
    path = make_crt(tmp_path, exrom=1, game=1,
                    chips=[chip_packet(0, 0x8000, good_8k_body())])
    assert any("nothing will be mapped" in r for r in cart_verify(path))


def test_verify_reports_an_empty_image(tmp_path):
    path = make_crt(tmp_path, chips=[])
    assert any("no CHIP packets" in r for r in cart_verify(path))


def test_verify_names_a_hardware_type_this_tool_does_not_build(tmp_path):
    """Anything but generic/EasyFlash gets one honest reason, not a wrong one:
    applying the generic rules to an Ocean cart would invent faults."""
    path = make_crt(tmp_path, hardware=5,
                    chips=[chip_packet(0, 0x8000, good_8k_body())])
    reasons = cart_verify(path)
    assert len(reasons) == 1
    assert "hardware type 5" in reasons[0] and "cart info" in reasons[0]


def test_verify_accepts_both_16k_layouts(tmp_path):
    """cartconv emits one $4000 packet, but the container permits the split
    $8000/$A000 pair and real images use it — calling that broken would be a
    false positive, not a caught bug."""
    single = make_crt(tmp_path, game=0, filename="single.crt",
                      chips=[chip_packet(0, 0x8000, good_8k_body().ljust(0x4000, b"\xFF"))])
    assert cart_verify(single) == []
    split = make_crt(tmp_path, game=0, filename="split.crt",
                     chips=[chip_packet(0, 0x8000, good_8k_body()),
                            chip_packet(0, 0xA000, b"\xFF" * 0x2000)])
    assert cart_verify(split) == []


def test_verify_checks_the_split_16k_geometry(tmp_path):
    """A two-packet image that is not the $8000/$A000 pair is still wrong."""
    path = make_crt(tmp_path, game=0,
                    chips=[chip_packet(0, 0x8000, good_8k_body()),
                           chip_packet(1, 0x8000, b"\xFF" * 0x2000)])
    assert any("loads at $8000 and $8000" in r for r in cart_verify(path))


def test_verify_checks_the_split_16k_window_sizes(tmp_path):
    path = make_crt(tmp_path, game=0,
                    chips=[chip_packet(0, 0x8000, good_8k_body()),
                           chip_packet(0, 0xA000, b"\xFF" * 0x1000)])
    assert any("$A000 packet" in r and "4096 bytes" in r
               for r in cart_verify(path))


def test_verify_a_16k_cold_vector_may_point_into_romh(tmp_path):
    """The split layout is one 16K cartridge: $8000-$BFFF is all of it."""
    ok = make_crt(tmp_path, game=0, filename="ok.crt",
                  chips=[chip_packet(0, 0x8000, good_8k_body(0xB000)),
                         chip_packet(0, 0xA000, b"\xFF" * 0x2000)])
    assert cart_verify(ok) == []
    bad = make_crt(tmp_path, game=0, filename="bad.crt",
                   chips=[chip_packet(0, 0x8000, good_8k_body(0xC000)),
                          chip_packet(0, 0xA000, b"\xFF" * 0x2000)])
    assert any("cold vector $C000" in r for r in cart_verify(bad))


def test_verify_reports_three_or_more_packets(tmp_path):
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, good_8k_body())] * 3)
    assert any("3 CHIP packets" in r for r in cart_verify(path))


def test_verify_catches_an_ultimax_cart_at_the_wrong_address(tmp_path):
    """Wrong geometry is ONE fault: with no $2000 window at $E000 there is no
    $FFFC to read, so a vector complaint would be invented."""
    path = make_crt(tmp_path, exrom=1, game=0,
                    chips=[chip_packet(0, 0x8000, b"\x00" * 0x2000)])
    reasons = cart_verify(path)
    assert len(reasons) == 1
    assert "maps ROMH at $E000" in reasons[0]
    assert "reset vector" not in reasons[0]


def test_verify_catches_a_wrong_sized_ultimax_cart(tmp_path):
    path = make_crt(tmp_path, exrom=1, game=0,
                    chips=[chip_packet(0, 0xE000, b"\x00" * 0x1000)])
    reasons = cart_verify(path)
    assert len(reasons) == 1 and "4096 bytes" in reasons[0]


def test_verify_catches_a_generic_cart_at_the_wrong_address(tmp_path):
    path = make_crt(tmp_path,
                    chips=[chip_packet(0, 0xA000, good_8k_body(0xA009))])
    assert any("maps ROML at $8000" in r for r in cart_verify(path))


def test_verify_survives_a_packet_too_short_to_hold_a_vector(tmp_path):
    """_vector returns None rather than reading past the end — a one-byte
    packet is reported for its size, not with a garbage vector."""
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, b"\x00")])
    reasons = cart_verify(path)
    assert any("this one is 1 bytes" in r for r in reasons)
    assert not any("cold vector" in r for r in reasons)


def test_verify_reports_an_easyflash_off_header_once(tmp_path):
    """EXROM=1/GAME=1 is one wrong header, so it gets one reason: the generic
    'nothing will be mapped'. Adding 'this image declares off' on top made a
    single fault read as two."""
    chips = [chip_packet(0, 0xA000, ef_hi_body(), chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=1, chips=chips)
    reasons = cart_verify(path)
    assert len(reasons) == 1 and "nothing will be mapped" in reasons[0]


def test_verify_still_reports_a_wrong_but_active_easyflash_mode(tmp_path):
    chips = [chip_packet(0, 0xA000, ef_hi_body(), chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=0, game=1, chips=chips)
    assert any("declares 8k" in r for r in cart_verify(path))


def test_verify_reports_a_tripled_window_once_with_the_count(tmp_path):
    chips = [chip_packet(0, 0xA000, ef_hi_body(), chip_type=2)]
    chips += [chip_packet(3, 0x8000, b"\xFF" * 0x2000, chip_type=2)] * 3
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    dup = [r for r in cart_verify(path) if "bank 3 lo appears" in r]
    assert dup == ["bank 3 lo appears 3 times"]


def test_verify_catches_an_easyflash_window_at_a_wrong_address(tmp_path):
    chips = [chip_packet(0, 0xA000, ef_hi_body(), chip_type=2),
             chip_packet(1, 0xC000, b"\xFF" * 0x2000, chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    assert any("windows are $8000 and $A000" in r for r in cart_verify(path))


def test_verify_catches_a_short_easyflash_window(tmp_path):
    chips = [chip_packet(0, 0xA000, ef_hi_body(), chip_type=2),
             chip_packet(1, 0x8000, b"\xFF" * 0x1000, chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    assert any("bank 1 lo is 4096 bytes" in r for r in cart_verify(path))


def test_verify_catches_an_easyflash_reset_vector_outside_romh(tmp_path):
    chips = [chip_packet(0, 0xA000, ef_hi_body(reset=0x0801), chip_type=2)]
    path = make_crt(tmp_path, hardware=32, exrom=1, game=0, chips=chips)
    assert any("reset vector $0801" in r for r in cart_verify(path))


def test_the_name_field_survives_space_padding(tmp_path):
    """cartconv NUL-terminates the 32-byte name; other writers pad with
    spaces, and reporting `GAME            ` as the title is wrong either way.
    """
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, b"\xFF" * 0x2000)])
    raw = bytearray(path.read_bytes())
    raw[0x20:0x40] = b"SPACED".ljust(32, b" ")
    path.write_bytes(bytes(raw))
    assert parse_crt(path).name == "SPACED"
    assert cart_info(path)["name"] == "SPACED"


def test_get_cart_type_lists_what_it_knows(tmp_path):
    assert get_cart_type("8k").image_bytes == 0x2000
    with pytest.raises(CartError, match="available: 16k, 8k, easyflash, ultimax"):
        get_cart_type("nes")


def test_cart_dump_rejects_an_unknown_window(tmp_path):
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, b"\xFF" * 0x2000)])
    with pytest.raises(CartError, match="must be 'lo' or 'hi'"):
        cart_dump(path, 0, "mid")


def test_parse_rejects_an_out_of_range_header_length(tmp_path):
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, b"\xFF" * 0x2000)])
    raw = bytearray(path.read_bytes())
    raw[0x10:0x14] = (0x100000).to_bytes(4, "big")
    path.write_bytes(bytes(raw))
    with pytest.raises(CartError, match="header length"):
        parse_crt(path)


def test_parse_names_a_file_it_cannot_read(tmp_path):
    with pytest.raises(CartError, match="No such file"):
        parse_crt(tmp_path / "absent.crt")


def test_cartconv_is_only_looked_for_when_it_is_needed(monkeypatch):
    monkeypatch.delenv("C64_TOOLS_CARTCONV", raising=False)
    monkeypatch.setattr(cart_mod.shutil, "which", lambda _name: None)
    with pytest.raises(CartError, match="cartconv not found"):
        run_cartconv(["--types"])


def test_cartconv_failure_carries_its_own_output(monkeypatch, tmp_path):
    fake = tmp_path / "cartconv"
    fake.write_text("")
    monkeypatch.setenv("C64_TOOLS_CARTCONV", str(fake))

    def fail(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, "", "Error: unknown type\n")

    monkeypatch.setattr(cart_mod.subprocess, "run", fail)
    # Measured: cartconv exits 0 even for a broken conversion, so the Error:
    # line is the only signal there is.
    with pytest.raises(CartError, match="unknown type"):
        run_cartconv(["-t", "nope"])


@pytest.mark.parametrize("boom,match", [
    (subprocess.TimeoutExpired("cartconv", 120), "did not finish within"),
    (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"), "undecodable"),
    (OSError("Permission denied"), "cannot run cartconv"),
])
def test_cartconv_environment_failures_are_cart_errors(monkeypatch, tmp_path,
                                                      boom, match):
    """A hung, unreadable or unexecutable cartconv is an environment problem
    the caller can report — not a traceback out of subprocess."""
    fake = tmp_path / "cartconv"
    fake.write_text("")
    monkeypatch.setenv("C64_TOOLS_CARTCONV", str(fake))

    def raise_it(cmd, **kw):
        raise boom

    monkeypatch.setattr(cart_mod.subprocess, "run", raise_it)
    with pytest.raises(CartError, match=match):
        run_cartconv(["-i", "x"])


def test_bin_to_crt_reports_a_missing_input(tmp_path):
    with pytest.raises(CartError, match="No such file"):
        bin_to_crt(tmp_path / "gone.bin", tmp_path / "o.crt", "8k", "X")


def test_bin_to_crt_demands_the_exact_image_size(tmp_path):
    raw = tmp_path / "short.bin"
    raw.write_bytes(b"\x00" * 100)
    with pytest.raises(CartError, match="must be exactly 8192 bytes"):
        bin_to_crt(raw, tmp_path / "o.crt", "8k", "X")


def test_bin_to_crt_measures_the_name_in_bytes(tmp_path):
    """The .crt name field is 32 BYTES: a name that is 32 characters but 34
    bytes would be silently truncated by cartconv."""
    raw = tmp_path / "ok.bin"
    raw.write_bytes(b"\x00" * 0x2000)
    with pytest.raises(CartError, match="34 bytes"):
        bin_to_crt(raw, tmp_path / "o.crt", "8k", "ÄÖ" + "X" * 30)
