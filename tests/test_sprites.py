import shutil
from unittest.mock import Mock

import pytest

from c64lib.basic import detokenize, tokenize
from c64lib.sprites import (
    C64_PALETTE,
    SpriteState,
    encode_sprite,
    format_bytes,
    read_sprite_block,
    read_sprite_states,
    sprite_ascii,
)


def _mock_mon(vic: bytes, pointers: bytes):
    mon = Mock()
    mon.memory_read.side_effect = lambda a, n: {
        0xD000: vic[:n], 0x07F8: pointers[:n]}[a]
    return mon


def _vic(**over):
    v = bytearray(0x2F)
    v[0x00], v[0x01] = 100, 120          # sprite 0 x/y
    v[0x02], v[0x03] = 44, 55            # sprite 1 x/y
    v[0x10] = 0b00000010                 # sprite 1 x MSB set
    v[0x15] = 0b00000011                 # sprites 0+1 enabled
    v[0x1C] = 0b00000010                 # sprite 1 multicolor
    v[0x17] = 0b00000001                 # sprite 0 expand-y
    v[0x1B] = 0b00000001                 # sprite 0 behind text
    v[0x20], v[0x21] = 14, 6             # border, background
    v[0x25], v[0x26] = 10, 11            # mc shared colors
    v[0x27], v[0x28] = 7, 2              # sprite 0/1 colors
    for k, val in over.items():
        v[k] = val
    return bytes(v)


def test_palette_shape():
    assert len(C64_PALETTE) == 16
    assert C64_PALETTE[0] == (0, 0, 0)          # black
    assert C64_PALETTE[1] == (255, 255, 255)    # white


def test_read_sprite_states_decodes_registers():
    mon = _mock_mon(_vic(), bytes([13, 0x80, 0, 0, 0, 0, 0, 0]))
    states, shared = read_sprite_states(mon, 0x0400)
    s0, s1 = states[0], states[1]
    assert s0 == SpriteState(index=0, enabled=True, x=100, y=120, pointer=13,
                             block_addr=13 * 64, color=7, multicolor=False,
                             expand_x=False, expand_y=True, behind_text=True)
    assert s1.x == 44 + 256 and s1.multicolor and s1.color == 2
    assert s1.block_addr == 0x80 * 64
    assert states[2].enabled is False
    assert shared == {"mc_color1": 10, "mc_color2": 11,
                      "background": 6, "border": 14}


def test_read_sprite_states_uses_live_screen_base():
    mon = Mock()
    vic = _vic()
    mon.memory_read.side_effect = lambda a, n: {
        0xD000: vic[:n], 0x0FF8: bytes([9] * 8)}[a]
    states, _ = read_sprite_states(mon, 0x0C00)
    assert states[0].pointer == 9


def test_read_sprite_block_reads_63_bytes():
    mon = Mock()
    mon.memory_read.return_value = bytes(range(63))
    assert read_sprite_block(mon, 0x0340) == bytes(range(63))
    mon.memory_read.assert_called_once_with(0x0340, 63)


def test_sprite_ascii_hires():
    data = bytes([0b10000000, 0, 0b00000001] + [0] * 60)  # corners of row 0
    rows = sprite_ascii(data, multicolor=False)
    assert len(rows) == 21 and all(len(r) == 24 for r in rows)
    assert rows[0][0] == "█" and rows[0][23] == "█"
    assert rows[0][1:23] == "·" * 22 and rows[1] == "·" * 24


def test_sprite_ascii_multicolor_pairs():
    data = bytes([0b00011011] + [0] * 62)   # pairs 00 01 10 11 in row 0
    rows = sprite_ascii(data, multicolor=True)
    assert len(rows) == 21 and all(len(r) == 24 for r in rows)
    assert rows[0][:8] == "··▒▒██▓▓"


def _state(**over):
    base = dict(index=0, enabled=True, x=0, y=0, pointer=13, block_addr=832,
                color=1, multicolor=False, expand_x=False, expand_y=False,
                behind_text=False)
    base.update(over)
    return SpriteState(**base)


_SHARED = {"mc_color1": 10, "mc_color2": 11, "background": 6, "border": 14}


def test_sprite_image_hires_pixels_and_scale():
    from c64lib.sprites import sprite_image
    data = bytes([0b10000000, 0, 0] + [0] * 60)
    img = sprite_image(data, _state(color=1), _SHARED, scale=1)
    assert img.size == (24, 21)
    assert img.getpixel((0, 0)) == C64_PALETTE[1]      # set -> sprite color
    assert img.getpixel((1, 0)) == C64_PALETTE[6]      # clear -> background
    img4 = sprite_image(data, _state(color=1), _SHARED, scale=4)
    assert img4.size == (96, 84)
    assert img4.getpixel((3, 3)) == C64_PALETTE[1]     # nearest-neighbour


def test_sprite_image_multicolor_pairs():
    from c64lib.sprites import sprite_image
    data = bytes([0b00011011] + [0] * 62)              # 00 01 10 11
    img = sprite_image(data, _state(color=7, multicolor=True), _SHARED, scale=1)
    assert img.getpixel((0, 0)) == C64_PALETTE[6]      # 00 background
    assert img.getpixel((2, 0)) == C64_PALETTE[10]     # 01 mc_color1
    assert img.getpixel((4, 0)) == C64_PALETTE[7]      # 10 sprite color
    assert img.getpixel((6, 0)) == C64_PALETTE[11]     # 11 mc_color2
    assert img.getpixel((3, 0)) == img.getpixel((2, 0))  # pair is 2 wide


def test_from_image_hires_threshold():
    from PIL import Image

    from c64lib.sprites import sprite_from_image
    img = Image.new("RGB", (24, 21), (255, 255, 255))
    for x in range(8):
        img.putpixel((x, 0), (0, 0, 0))            # dark = set
    data, lines = sprite_from_image(img, multicolor=False)
    assert len(data) == 63
    assert data[0] == 0b11111111 and data[1] == 0
    assert any(".byte %11111111" in ln for ln in lines)
    assert any("pointer = block_address / 64" in ln for ln in lines)


def test_from_image_resizes_arbitrary_input():
    from PIL import Image

    from c64lib.sprites import sprite_from_image
    img = Image.new("RGBA", (240, 210), (0, 0, 0, 0))  # fully transparent
    data, _ = sprite_from_image(img, multicolor=False)
    assert data == bytes(63)                            # transparent = clear


def test_from_png_roundtrip_hires():
    from c64lib.sprites import sprite_from_image, sprite_image
    data = bytes((i * 37) % 256 for i in range(63))
    shared = {"mc_color1": 10, "mc_color2": 11, "background": 1, "border": 14}
    img = sprite_image(data, _state(color=0), shared, scale=1)  # black on white
    back, _ = sprite_from_image(img, multicolor=False)
    assert back == data


def test_from_image_multicolor_quantizes_to_pairs():
    from c64lib.sprites import sprite_from_image, sprite_image
    data = bytes([0b00011011, 0, 0] * 21)
    back, lines = sprite_from_image(
        sprite_image(data, _state(color=2, multicolor=True), _SHARED, scale=1),
        multicolor=True)
    assert back == data
    assert any("multicolor" in ln for ln in lines)


def test_multicolor_row_encodes_two_bits_per_pixel():
    art = [" .#+" + " " * 8] + ["            "] * 20
    data = encode_sprite(art, multicolor=True)
    assert len(data) == 63
    # ' .#+' -> 00 01 10 11 -> 0b00011011
    assert data[0] == 0b00011011


def test_hires_row_encodes_one_bit_per_pixel():
    art = ["#" * 8 + " " * 16] + [" " * 24] * 20
    data = encode_sprite(art, multicolor=False)
    assert data[0] == 0xFF and data[1] == 0x00


def test_encode_accepts_show_glyphs_and_roundtrips_multicolor():
    data = bytes((i * 37) % 256 for i in range(63))
    art = sprite_ascii(data, multicolor=True)      # 24-char doubled rows
    assert encode_sprite(art, multicolor=True) == data


def test_encode_accepts_show_glyphs_and_roundtrips_hires():
    data = bytes((i * 29) % 256 for i in range(63))
    art = sprite_ascii(data, multicolor=False)     # 24-char █/·
    assert encode_sprite(art, multicolor=False) == data


def test_wrong_dimensions_rejected():
    import pytest
    with pytest.raises(ValueError):
        encode_sprite(["###"], multicolor=True)


def test_wrong_row_width_rejected():
    import pytest
    # 21 rows so the row-count check passes; one row is the wrong width so the
    # per-row width branch trips.
    mc = [" " * 12] * 20 + [" " * 10]
    with pytest.raises(ValueError, match="12 or 24 chars/row"):
        encode_sprite(mc, multicolor=True)
    hi = [" " * 24] * 20 + [" " * 23]
    with pytest.raises(ValueError, match="hires sprite art must be 24 chars/row"):
        encode_sprite(hi, multicolor=False)


def test_unknown_glyph_rejected():
    import pytest
    mc = [" " * 12] * 20 + ["X" + " " * 11]
    with pytest.raises(ValueError, match="unknown multicolor sprite glyph 'X'"):
        encode_sprite(mc, multicolor=True)
    hi = [" " * 24] * 20 + ["X" + " " * 23]
    with pytest.raises(ValueError, match="unknown hires sprite glyph 'X'"):
        encode_sprite(hi, multicolor=False)


def test_screen_base_banks_and_slots():
    from c64lib.screen import screen_base
    mon = Mock()
    # ($DD00 & 3, $D018) -> expected base
    cases = {(0b11, 0x15): 0x0400,          # bank 0, slot 1 (power-on)
             (0b11, 0x35): 0x0C00,          # bank 0, slot 3
             (0b10, 0x15): 0x4400,          # bank 1
             (0b00, 0x15): 0xC400}          # bank 3, slot 1
    for (dd00, d018), want in cases.items():
        mon.memory_read.side_effect = lambda a, n, dd00=dd00, d018=d018: {
            0xDD00: bytes([dd00]), 0xD018: bytes([d018])}[a]
        assert screen_base(mon) == want, f"dd00={dd00:02b} d018=${d018:02x}"


def test_format_bytes_basic_is_lowercase(tmp_path):
    """An uppercase `DATA` is shifted PETSCII: the C64 tokenizes it as
    STR$ ATN ATN and the listing cannot run, so the rows must come out
    lowercase whether or not they are numbered."""
    data = bytes(range(63))
    plain = format_bytes(data, "basic")
    assert plain.startswith("data ") and "DATA" not in plain
    assert format_bytes(data, "basic", start_line=1000).splitlines()[0] \
        == "1000 data 0,1,2"


def test_format_bytes_basic_numbered_survives_petcat(tmp_path):
    """The whole point of --start-line: the block pastes into a .bas and
    tokenizes back to the same DATA statements."""
    if shutil.which("petcat") is None:
        pytest.skip("petcat not installed")
    numbered = format_bytes(bytes(range(63)), "basic", start_line=1000)
    src = tmp_path / "d.bas"
    src.write_text("10 read a : print a\n" + numbered + "\n")
    listing = detokenize(tokenize(src, tmp_path / "d.prg", "2.0"), "2.0").lower()
    assert "data 0,1,2" in listing
    assert "atn" not in listing          # the uppercase-DATA failure mode
