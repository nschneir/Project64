import pytest

from c64lib.text import ascii_to_petscii, screen_code_to_char, screen_to_text


def test_screen_code_letters_and_symbols():
    # Commodore screen codes: 0='@', 1..26='A'..'Z', 27='[', 28='\\', 29=']'
    assert screen_code_to_char(0) == "@"
    assert screen_code_to_char(1) == "A"
    assert screen_code_to_char(26) == "Z"
    assert screen_code_to_char(27) == "["
    # 32..63 = ' ' .. '?' (matches ASCII 0x20..0x3F)
    assert screen_code_to_char(32) == " "
    assert screen_code_to_char(33) == "!"
    assert screen_code_to_char(48) == "0"
    assert screen_code_to_char(63) == "?"


def test_reverse_video_bit_stripped():
    assert screen_code_to_char(0x81) == "A"  # reverse 'A'


def test_graphics_codes_become_dot():
    # legacy ascii style collapses graphics; unicode style decodes them
    assert screen_code_to_char(97, style="ascii") == "·"
    assert screen_code_to_char(97) == "▌"


def test_screen_to_text_rows():
    # "HI" on row 0, "OK" on row 1 of a 4-col screen, rest spaces (code 32)
    row0 = bytes([8, 9, 32, 32])
    row1 = bytes([15, 11, 32, 32])
    assert screen_to_text(row0 + row1, cols=4) == "HI\nOK"


def test_ascii_to_petscii_basic():
    assert ascii_to_petscii("RUN\n") == b"RUN\r"
    assert ascii_to_petscii('print "hi"') == b'PRINT "HI"'


def test_ascii_to_petscii_rejects_unmappable():
    with pytest.raises(ValueError):
        ascii_to_petscii("naïve")


def test_screen_decode_matches_documented_behavior():
    """Pins the claims in petscii.md's 'How c64 screen decodes' section."""
    from c64lib import text
    # reverse video without a Unicode complement keeps the base glyph
    assert text.screen_code_to_char(0x81) == "A"
    # reverse-space $A0 (the solid block) decodes as a solid block
    assert text.screen_code_to_char(0xA0) == "█"
    # legacy ascii style: unmapped graphics render as the placeholder
    unmapped = next(c for c in range(64, 128) if c not in text._GRAPHICS_ASCII)
    assert text.screen_code_to_char(unmapped, style="ascii") == text.GRAPHICS_PLACEHOLDER


def test_petscii_doc_has_decoder_section():
    from pathlib import Path
    doc = Path("skills/c64-development/references/petscii.md").read_text()
    assert "How `c64 screen` decodes" in doc
    assert "$A0" in doc
