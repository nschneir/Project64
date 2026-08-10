import shutil
from dataclasses import replace
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


def _vic():
    # No override hook: the one this helper used to carry (`**over` writing
    # `v[k] = val`) indexed a bytearray with the keyword *name*, so any call
    # that actually passed an override would have raised TypeError. Nothing
    # ever did — every caller in this file and in test_cli_sprite.py calls
    # `_vic()` bare. Removed rather than repaired; add a typed one when a test
    # needs it.
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


# Overrides go through dataclasses.replace rather than a `dict` of kwargs: a
# dict mixing the int fields (x, pointer, color) with the bool ones widens to
# `dict[str, int]`, and splatting that back into SpriteState offers an int for
# every `bool` field. `replace` keeps each field's own type.
_BASE_STATE = SpriteState(index=0, enabled=True, x=0, y=0, pointer=13,
                          block_addr=832, color=1, multicolor=False,
                          expand_x=False, expand_y=False, behind_text=False)


def _state(**over):
    return replace(_BASE_STATE, **over)


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


def test_from_image_multicolor_maps_extra_and_transparent_pixels():
    """The two fallback paths in the multicolor converter, which the
    roundtrip tests never reach because they feed back exactly four colors:
    a fifth color collapses to whichever of the four pairs is nearest in RGB,
    and a transparent pixel is background (pair 00), same as an unmapped one.
    """
    from PIL import Image

    from c64lib.sprites import sprite_from_image
    img = Image.new("RGBA", (12, 21), (*C64_PALETTE[0], 255))   # edges -> bg 0
    for color in (1, 2, 3):                        # -> pairs 01, 10, 11
        img.putpixel((color, 1), (*C64_PALETTE[color], 255))
    img.putpixel((4, 1), (*C64_PALETTE[5], 255))   # 5th color: nearest is 2
    img.putpixel((5, 1), (0, 0, 0, 0))             # transparent: pair 00
    data, lines = sprite_from_image(img, multicolor=True)
    # row 1 pairs: 00 01 10 11 | 10 00 00 00 | 00 00 00 00
    assert data[3:6] == bytes([0b00011011, 0b10000000, 0])
    assert data[0:3] == bytes(3)                   # row 0 is all background
    assert "background (00) = color 0" in lines[1]


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


# --- c64 charset encode (charset.py) ---

def test_charset_multicolor_row_encodes_two_bits_per_pixel():
    from c64lib.charset import encode_row, parse_charset
    glyphs = parse_charset("name: g\n.123\n" + "....\n" * 7)
    assert glyphs == [("g", [".123", "....", "....", "....",
                             "....", "....", "....", "...."], True)]
    # '.123' -> 00 01 10 11 -> 0b00011011 (multicolor-text pair order:
    # 00=$D021, 01=$D022, 10=$D023, 11=cell color — hardware.md's table)
    assert encode_row(".123") == 0b00011011


def test_charset_hires_row_encodes_one_bit_per_pixel():
    from c64lib.charset import encode_row, parse_charset
    glyphs = parse_charset("name: g\n####....\n" + "........\n" * 7,
                           multicolor=False)
    assert glyphs[0][1][0] == "####...."
    assert encode_row("####....", multicolor=False) == 0xF0


def test_charset_bare_label_headers_comments_and_blanks():
    from c64lib.charset import parse_charset
    text = "# a comment\n\nsquid:\n" + "3333\n" * 8 + "\nname: bolt\n" + "1111\n" * 8
    names = [g.name for g in parse_charset(text)]
    assert names == ["squid", "bolt"]     # file order IS screen-code order


def test_charset_errors_name_the_glyph_and_line():
    import pytest

    from c64lib.charset import CharsetError, parse_charset
    with pytest.raises(CharsetError, match=r"glyph 'g'.*has 7 rows"):
        parse_charset("name: g\n" + "....\n" * 7)
    with pytest.raises(CharsetError, match=r"line 2: 5 characters"):
        parse_charset("name: g\n....5\n" + "....\n" * 7)
    with pytest.raises(CharsetError, match=r"illegal legend"):
        parse_charset("name: g\n..x.\n" + "....\n" * 7)
    with pytest.raises(CharsetError, match="pixel row before any"):
        parse_charset("....\n")
    with pytest.raises(CharsetError, match="no glyphs"):
        parse_charset("# empty\n")
    with pytest.raises(CharsetError, match=r"duplicate glyph name 'g'"):
        parse_charset("name: g\n" + "....\n" * 8 + "name: g\n" + "....\n" * 8)


def test_charset_format_glyphs_emits_the_consumer_shape():
    """chars.s copies with `cpx #(glyphs_end - glyphs)` — one leading label,
    one end label, glyph data contiguous in authoring order."""
    from c64lib.charset import format_glyphs, parse_charset
    text = format_glyphs(parse_charset("name: g\n.123\n" + "....\n" * 7),
                         first_code=64)
    assert "glyphs:" in text and "glyphs_end:" in text
    assert "; code 64: g" in text
    assert "        .byte   %00011011    ; .123" in text
    assert text.endswith("\n") and "c64 charset encode" in text.splitlines()[0]


# --- the sheet grammars: per-block modes, and naming the block that is wrong ---

def _mc_block(name: str, mode: str = "") -> str:
    return f"{name}:{mode}\n" + "....\n" * 8


def test_charset_mixed_modes_in_one_sheet():
    """A game whose maze charset is multicolor and whose HUD glyphs are hires
    used to need two invocations and two output blocks; a block may now name
    its own mode, so the design picks the mode instead of the tool."""
    from c64lib.charset import encode_row, parse_charset
    sheet = ("wall:multicolor\n" + ".123\n" * 8
             + "\nletter:hires\n" + "##......\n" * 8)
    glyphs = parse_charset(sheet)
    assert [(g.name, g.multicolor) for g in glyphs] == [("wall", True),
                                                        ("letter", False)]
    hires_only = parse_charset("letter:\n" + "##......\n" * 8, multicolor=False)
    assert [encode_row(r, False) for r in glyphs[1].rows] == \
           [encode_row(r, False) for r in hires_only[0].rows]


def test_charset_bare_header_follows_file_mode():
    from c64lib.charset import parse_charset
    sheet = "squid:\n" + "##......\n" * 8
    assert parse_charset(sheet, multicolor=False)[0].multicolor is False
    assert parse_charset(_mc_block("squid"))[0].multicolor is True


def test_charset_rejects_unknown_mode():
    import pytest

    from c64lib.charset import CharsetError, parse_charset
    with pytest.raises(CharsetError, match=(
            r"^charset sheet line 3: unknown mode 'mono' — "
            r"use 'hires' or 'multicolor'$")):
        parse_charset("# a sheet\n\nwall:mono\n" + ".123\n" * 8)


def _sprite_rows(n: int) -> str:
    return ("." * 12 + "\n") * n


def test_sprite_encode_names_the_short_block():
    """A sheet of 27 shapes reporting only "must be 21 rows, got 14" costs a
    hand bisection; the block index and its first line end that."""
    import pytest

    from c64lib.sprites import encode_sheet
    sheet = (_sprite_rows(21) + "\n\n"          # lines 1-21, blanks 22-23
             + _sprite_rows(14) + "\n"          # lines 24-37
             + _sprite_rows(21))
    with pytest.raises(ValueError, match=(
            r"^sprite 2 \(line 24\): art must be 21 rows, got 14$")):
        encode_sheet(sheet)


def test_sprite_encode_first_block_still_reported():
    import pytest

    from c64lib.sprites import encode_sheet
    with pytest.raises(ValueError,
                       match=r"^sprite 1 \(line 1\): art must be 21 rows, got 3$"):
        encode_sheet(_sprite_rows(3))


def test_sprite_encode_sheet_round_trips_every_block():
    from c64lib.sprites import encode_sheet, encode_sprite
    rows = ["." * 12] * 21
    assert encode_sheet(_sprite_rows(21) + "\n" + _sprite_rows(21)) == \
           [encode_sprite(rows), encode_sprite(rows)]


def test_render_sheet_matches_inline_rendering():
    """Numbering runs on across sprites: the second block starts a full
    sprite (21 rows) past the first, so a two-sprite file is one ascending
    listing rather than two that overwrite each other."""
    from c64lib.sprites import encode_sheet, render_sheet
    sprites = encode_sheet(_sprite_rows(21) + "\n" + _sprite_rows(21))
    text = render_sheet(sprites, fmt="basic", start_line=100)
    numbers = [int(ln.split()[0]) for ln in text.splitlines() if ln.strip()]
    assert len(numbers) == 42
    assert numbers[0] == 100 and numbers[21] == 100 + 21 * 10
    assert numbers == sorted(numbers) and len(set(numbers)) == 42
    assert text.endswith("\n")


def test_render_sheet_asm_joins_with_blank_line():
    from c64lib.sprites import encode_sheet, format_bytes, render_sheet
    sprites = encode_sheet(_sprite_rows(21) + "\n" + _sprite_rows(21))
    text = render_sheet(sprites)
    assert text == "\n\n".join(
        format_bytes(data, "asm", index=i) for i, data in enumerate(sprites)) + "\n"
    assert "sprite0: .byte %" in text and "sprite1: .byte %" in text


def test_render_sheet_rejects_a_bad_format():
    from c64lib.sprites import encode_sheet, render_sheet
    sprites = encode_sheet(_sprite_rows(21))
    with pytest.raises(ValueError, match=r"^unknown format 'c'; use 'asm' or 'basic'$"):
        render_sheet(sprites, fmt="c")


# ---- sheet ergonomics: named blocks, comments, a visible background --------

def _mc(rows: str) -> str:
    return rows


def test_sprite_sheet_named_blocks_carry_their_own_mode():
    """One sheet, both modes: a `name:hires` block is 24 wide and a
    `name:multicolor` one is 12, the way charset sheets already work."""
    from c64lib.sprites import encode_sheet, encode_sprite
    sheet = ("fighter:hires\n" + ("#" * 24 + "\n") * 21
             + "\ndrone:multicolor\n" + ("#" * 12 + "\n") * 21)
    assert encode_sheet(sheet) == [encode_sprite(["#" * 24] * 21, multicolor=False),
                                   encode_sprite(["#" * 12] * 21, multicolor=True)]


def test_sprite_sheet_bare_header_takes_the_file_mode():
    from c64lib.sprites import encode_sheet, encode_sprite
    sheet = "drone:\n" + ("#" * 24 + "\n") * 21
    assert encode_sheet(sheet, multicolor=False) == \
        [encode_sprite(["#" * 24] * 21, multicolor=False)]


def test_sprite_sheet_rejects_an_unknown_mode():
    from c64lib.sprites import encode_sheet
    with pytest.raises(ValueError, match=(
            r"^sprite sheet line 2: unknown mode 'mono' — "
            r"use 'hires' or 'multicolor'$")):
        encode_sheet("# a sheet\ndrone:mono\n" + ("#" * 12 + "\n") * 21)


def test_sprite_sheet_rejects_a_duplicate_name():
    from c64lib.sprites import encode_sheet
    sheet = ("drone:\n" + ("#" * 12 + "\n") * 21
             + "\ndrone:\n" + ("#" * 12 + "\n") * 21)
    with pytest.raises(ValueError,
                       match=r"^duplicate sprite name 'drone' at line 24$"):
        encode_sheet(sheet)


def test_sprite_sheet_comment_lines_are_skipped():
    from c64lib.sprites import encode_sheet, encode_sprite
    sheet = ("# La Galaxia -- every shape, as readable art\n"
             "#   . background   # sprite colour\n"
             "\n"
             "drone:\n" + ("#" * 12 + "\n") * 21)
    assert encode_sheet(sheet) == [encode_sprite(["#" * 12] * 21)]


def test_sprite_sheet_an_all_hash_row_is_art_not_a_comment():
    """`#` is both the comment marker and a legend character, so a line is a
    comment only when it holds something the legend does not — an all-`#` row
    is a solid line of sprite-color pixels and must survive."""
    from c64lib.sprites import encode_sheet
    sheet = "drone:\n" + ("#" * 12 + "\n") * 21
    assert encode_sheet(sheet)[0] == b"\xaa" * 63


def test_sprite_sheet_visible_background_encodes_the_same_bytes():
    """`--background .` only renames pair 00; the bytes are the space sheet's."""
    from c64lib.sprites import encode_sheet
    spaces = ("   ###   ###\n" + " " * 12 + "\n") * 10 + " " * 12 + "\n"
    dots = spaces.replace(" ", ".")
    assert encode_sheet(dots, background=".") == encode_sheet(spaces)


def test_sprite_sheet_background_frees_the_dot_and_digits_spell_the_pairs():
    """With `.` claimed for pair 00 the sheet spells 01/10/11 as `1 2 3` —
    the same digit-is-the-pair-value legend charset sheets use."""
    from c64lib.sprites import encode_sheet
    row = ".123" * 3
    sheet = (row + "\n") * 21
    assert encode_sheet(sheet, background=".")[0][:3] == \
        (0b00011011_00011011_00011011).to_bytes(3, "big")


def test_sprite_sheet_hires_visible_background():
    from c64lib.sprites import encode_sheet
    sheet = ("." * 20 + "####" + "\n") * 21
    assert encode_sheet(sheet, multicolor=False, background=".")[0][:3] == \
        b"\x00\x00\x0f"


def test_sprite_sheet_names_reach_the_rendering():
    from c64lib.sprites import (
        encode_sheet,
        encode_sheet_blocks,
        parse_sprite_sheet,
        render_sheet,
    )
    sheet = ("fighter:hires\n" + ("#" * 24 + "\n") * 21
             + "\ndrone:multicolor\n" + ("#" * 12 + "\n") * 21)
    blocks = parse_sprite_sheet(sheet)
    assert [b.name for b in blocks] == ["fighter", "drone"]
    assert [b.multicolor for b in blocks] == [False, True]
    text = render_sheet(encode_sheet_blocks(sheet))
    assert "; sprite 0 (fighter), 24x21 hires" in text
    assert "; sprite 1 (drone), 24x21 multicolor" in text
    assert encode_sheet(sheet) == [b.data for b in encode_sheet_blocks(sheet)]


def test_sprite_sheet_positional_blocks_are_unchanged():
    """No header, no comment, spaces for background: the old sheet still
    parses, still numbers by position, and still renders without a name."""
    from c64lib.sprites import encode_sheet, render_sheet
    sheet = (" " * 12 + "\n") * 21 + "\n" + ("#" * 12 + "\n") * 21
    sprites = encode_sheet(sheet)
    assert len(sprites) == 2
    text = render_sheet(sprites)
    assert "; sprite 0, 24x21 multicolor (63 bytes" in text


def test_sprite_sheet_row_before_any_header_after_one_is_still_positional():
    """A sheet that names some blocks and not others keeps counting: the
    unnamed block is `sprite1` and says so."""
    from c64lib.sprites import encode_sheet, parse_sprite_sheet
    sheet = ("drone:\n" + ("#" * 12 + "\n") * 21
             + "\n" + ("#" * 12 + "\n") * 21)
    assert [b.name for b in parse_sprite_sheet(sheet)] == ["drone", None]
    assert len(encode_sheet(sheet)) == 2


def test_sprite_sheet_rejects_a_header_with_no_art():
    """Two headers in a row is a typo, not an empty sprite — charset sheets
    reject the same shape rather than silently dropping the block."""
    from c64lib.sprites import encode_sheet
    with pytest.raises(ValueError,
                       match=r"^sprite 'drone' \(line 1\) has no art rows$"):
        encode_sheet("drone:\n\nwasp:\n" + ("#" * 12 + "\n") * 21)


def test_sprite_sheet_errors_name_the_block():
    from c64lib.sprites import encode_sheet
    sheet = "drone:\n" + ("#" * 12 + "\n") * 14
    with pytest.raises(ValueError, match=(
            r"^sprite 1 'drone' \(line 1\): art must be 21 rows, got 14$")):
        encode_sheet(sheet)


def test_charset_format_glyphs_label_renames_both_ends():
    from c64lib.charset import format_glyphs, parse_charset
    glyphs = parse_charset("name: g\n" + ".123\n" * 8)
    text = format_glyphs(glyphs, label="fontgly")
    assert "fontgly:" in text and "fontgly_end:" in text
    assert "glyphs:" not in text


def test_charset_format_glyphs_default_label_is_glyphs():
    from c64lib.charset import format_glyphs, parse_charset
    glyphs = parse_charset("name: g\n" + ".123\n" * 8)
    text = format_glyphs(glyphs)
    assert "glyphs:" in text and "glyphs_end:" in text
