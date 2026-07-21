"""FT2: Unicode screen decoding (+ ascii fallback, ANSI reverse).

Every glyph asserted here was verified on-screen against a live 4032
during the Ms. Muncher dogfood (charset grid + fusion tests).
"""
import pytest

from c64lib.text import screen_code_to_char, screen_to_text

UNICODE_CASES = [
    (81, "●"), (87, "○"), (83, "♥"), (90, "◆"), (65, "♠"), (88, "♣"),
    (64, "─"), (93, "│"),
    (85, "╭"), (73, "╮"), (74, "╰"), (75, "╯"),                 # arcs
    (112, "┌"), (110, "┐"), (109, "└"), (122, "┘"),             # sharp
    (107, "├"), (115, "┤"), (114, "┬"), (113, "┴"), (91, "┼"),
    (102, "▒"), (94, "π"), (86, "╳"), (77, "╲"), (78, "╱"),
    (97, "▌"), (98, "▄"), (99, "▔"), (100, "▁"),
    (108, "▗"), (123, "▖"), (124, "▝"), (126, "▘"), (127, "▚"),
    (95, "◣"), (105, "◤"),
]

REVERSE_CASES = [
    (225, "▐"),   # reverse of ▌: the complement half
    (226, "▀"),   # reverse of ▄
    (236, "▛"),   # reverse of ▗ (three-quarter blocks: the muncher ball!)
    (251, "▜"),   # reverse of ▖
    (252, "▙"),   # reverse of ▝
    (254, "▟"),   # reverse of ▘
    (223, "◥"),   # reverse of ◣
    (233, "◢"),   # reverse of ◤
    (160, "█"),   # reverse space = solid block
    (209, "◘"),   # reverse ball
    (215, "◙"),   # reverse ring (frightened ghosts)
]


@pytest.mark.parametrize("code,ch", UNICODE_CASES)
def test_unicode_graphics(code, ch):
    assert screen_code_to_char(code) == ch


@pytest.mark.parametrize("code,ch", REVERSE_CASES)
def test_reverse_video_complements(code, ch):
    assert screen_code_to_char(code) == ch


def test_letters_digits_unchanged():
    assert screen_code_to_char(1) == "A"
    assert screen_code_to_char(48) == "0"
    assert screen_code_to_char(46) == "."


def test_ascii_style_is_the_old_behavior():
    assert screen_code_to_char(81, style="ascii") == "·"
    assert screen_code_to_char(64, style="ascii") == "-"
    assert screen_code_to_char(1, style="ascii") == "A"


def test_reverse_without_complement_keeps_base_glyph():
    # reverse-video 'A' (129) has no Unicode inverse: same glyph by default
    assert screen_code_to_char(129) == "A"


def test_ansi_reverse_wraps_unmapped_reverses():
    s = screen_code_to_char(129, ansi_reverse=True)
    assert s == "\x1b[7mA\x1b[27m"
    # mapped complements never need the escape
    assert screen_code_to_char(225, ansi_reverse=True) == "▐"


def test_screen_to_text_unicode_row():
    # ╭─╮ over ● ○: the kind of row the muncher maze produces
    data = bytes([85, 64, 73]) + bytes([32] * 37) + bytes([81, 32, 87])
    out = screen_to_text(data, 40)
    assert out.splitlines()[0] == "╭─╮"
    assert out.splitlines()[1] == "● ○"
