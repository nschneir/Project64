import re

import pytest

from c64lib.cart_build import (
    VECTORS_SIZE,
    _used_bytes,
    boot_stub_source,
    cart_linker_config,
    cart_title,
    has_own_startup,
    launcher_source,
    wrap_prg,
)
from c64lib.cartridge import CartError


def test_8k_config_fills_one_window_at_8000():
    cfg = cart_linker_config("8k")
    assert "start = $8000, size = $2000" in cfg
    assert "fill = yes, fillval = $FF" in cfg
    assert "$A000" not in cfg


def test_16k_config_adds_the_a000_window():
    cfg = cart_linker_config("16k")
    assert "start = $8000, size = $2000" in cfg
    assert "start = $A000, size = $2000" in cfg
    assert "ROMH:" in cfg          # the segment authors put $A000 data in


def test_ultimax_config_puts_romh_at_e000_and_reserves_the_vectors():
    cfg = cart_linker_config("ultimax")
    assert "start = $E000, size = $1FFA" in cfg
    assert "start = $FFFA, size = $0006" in cfg
    assert "VECTORS:" in cfg


@pytest.mark.parametrize("cart_type", ["8k", "16k", "ultimax"])
def test_every_config_gives_bss_a_ram_home(cart_type):
    """The docstring tells authors to put mutable state in a BSS segment, so
    every config has to declare one — ld65 refuses to link without it."""
    cfg = cart_linker_config(cart_type)
    assert "RAM:" in cfg
    assert "BSS:" in cfg
    assert "load = RAM" in cfg
    assert "type = bss" in cfg


def test_ram_areas_clear_the_screen_and_respect_the_ultimax_limit():
    # RAMTAS clears $0200-$03FF and CINT clears the $0400-$07FF screen, so BSS
    # starts above them at $0800. Under an Ultimax cart only $0000-$0FFF is RAM.
    for cart_type in ("8k", "16k"):
        assert "start = $0800, size = $7800" in cart_linker_config(cart_type)
    assert "start = $0800, size = $0800" in cart_linker_config("ultimax")


def test_unknown_cart_type_lists_the_known_ones():
    with pytest.raises(CartError, match="available: 16k, 8k, easyflash, ultimax"):
        cart_linker_config("nes")


def test_cbm80_stub_carries_the_signature_and_kernal_init():
    src = boot_stub_source("8k")
    assert '.import cart_main' in src
    assert "$C3,$C2,$CD,$38,$30" in src
    for routine in ("$FDA3", "$FD50", "$FD15", "$FF5B"):
        assert routine in src
    # Whitespace-tolerant: the stub is column-aligned assembly.
    assert re.search(r"jmp\s+cart_main", src)


def test_ultimax_stub_has_vectors_and_no_kernal_calls():
    src = boot_stub_source("ultimax")
    assert '.segment "VECTORS"' in src
    # An Ultimax cart replaces the KERNAL: it must not call into it.
    for routine in ("$FDA3", "$FD50", "$FD15", "$FF5B"):
        assert routine not in src
    assert "$C3,$C2,$CD,$38,$30" not in src     # no CBM80 scan in Ultimax


def test_startup_detection_is_the_opt_out(tmp_path):
    plain = tmp_path / "plain.s"
    plain.write_text('.segment "CODE"\ncart_main: rts\n')
    own = tmp_path / "own.s"
    own.write_text('.segment "STARTUP"\n        .word start\n')
    assert has_own_startup([plain]) is False
    assert has_own_startup([own]) is True
    assert has_own_startup([plain, own]) is True


def test_startup_detection_ignores_a_comment(tmp_path):
    p = tmp_path / "c.s"
    p.write_text('; we could add .segment "STARTUP" here one day\nnop\n')
    assert has_own_startup([p]) is False


def test_used_bytes_counts_a_reserved_tail_as_spent():
    """An Ultimax image ends with the reset vectors, which are never $FF.

    Applying the fill heuristic to them would report every Ultimax cart as
    completely full, however small the program is.
    """
    image = b"\xA9\x15" + b"\xFF" * (0x2000 - 8) + b"\x00\xE0\x00\xE0\x00\xE0"
    assert len(image) == 0x2000
    assert _used_bytes(image, VECTORS_SIZE) == 2 + VECTORS_SIZE
    # Without the reservation the non-$FF tail hides the whole fill region.
    assert _used_bytes(image) == 0x2000


def test_used_bytes_measures_each_bank_window_separately():
    """A 16K image is two independent $2000 windows, not one 16K block.

    A single byte of ROMH data must not make the whole ROML fill region count
    as used — that over-reported a nearly empty cart by about 8 KB.
    """
    roml = b"\xA9\x15" + b"\xFF" * (0x2000 - 2)
    romh = b"\x2A" + b"\xFF" * (0x2000 - 1)
    assert _used_bytes(roml + romh) == 3


def test_cart_title_uppercases_and_bounds_length():
    assert cart_title("game") == "GAME"
    with pytest.raises(CartError, match="32"):
        cart_title("x" * 33)
    with pytest.raises(CartError, match="empty"):
        cart_title("   ")


def test_basic_launcher_chains_through_the_interpreter():
    src = launcher_source(0x0801, 0x0825, "basic")
    # Measured boot sequence for a wrapped BASIC program.
    for token in ("$E453", "$E3BF", "$A659", "$A7AE"):
        assert token in src
    assert "$2D" in src and "$32" in src        # VARTAB..STREND get set
    assert ".incbin" in src


def test_ml_launcher_jumps_to_the_load_address():
    src = launcher_source(0xC000, 0xC100, "ml")
    # Whitespace-tolerant: the launcher is column-aligned assembly.
    assert re.search(r"jmp\s+\$C000", src)
    # A machine-code program does not touch the BASIC pointers.
    assert "$A7AE" not in src


def test_wrap_rejects_ultimax(tmp_path):
    prg = tmp_path / "p.prg"
    prg.write_bytes(bytes([0x01, 0x08]) + b"\x00" * 8)
    with pytest.raises(CartError, match="Ultimax"):
        wrap_prg(prg, cart_type="ultimax", title="P")


def test_wrap_rejects_a_program_too_big_for_the_window(tmp_path):
    prg = tmp_path / "big.prg"
    prg.write_bytes(bytes([0x01, 0x08]) + b"\x00" * 9000)
    with pytest.raises(CartError, match="--cart-type 16k"):
        wrap_prg(prg, cart_type="8k", title="BIG")


def test_wrap_rejects_a_truncated_prg(tmp_path):
    prg = tmp_path / "t.prg"
    prg.write_bytes(b"\x01")
    with pytest.raises(CartError, match="load address"):
        wrap_prg(prg, cart_type="8k", title="T")
