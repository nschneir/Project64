import re

import pytest

from c64lib.cart_build import (
    VECTORS_SIZE,
    _used_bytes,
    boot_stub_source,
    cart_linker_config,
    cart_title,
    has_own_startup,
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


def test_cart_title_uppercases_and_bounds_length():
    assert cart_title("game") == "GAME"
    with pytest.raises(CartError, match="32"):
        cart_title("x" * 33)
    with pytest.raises(CartError, match="empty"):
        cart_title("   ")
