from unittest.mock import Mock

from PIL import Image

from c64lib.machines import get_profile
from c64lib.screen import number_screen_text, read_screen_text, save_screenshot_png


def test_number_screen_text_adds_a_ruler_and_row_indices():
    out = number_screen_text("READY.\n\nTOO HIGH").splitlines()
    assert out[0] == "   " + "".join(str(c % 10) for c in range(40))
    assert out[1] == " 0|READY."
    assert out[2] == " 1|"
    assert out[3] == " 2|TOO HIGH"


def test_read_screen_text_uses_profile_geometry():
    profile = get_profile("c64")
    mon = Mock()
    screen = bytes([18, 5, 1, 4, 25, 46]) + bytes([32] * (1000 - 6))  # "READY."
    mon.memory_read.side_effect = lambda a, n: {
        0xDD00: bytes([0b11]), 0xD018: bytes([0x15]), 0x0400: screen}[a]
    text = read_screen_text(mon, profile)
    mon.memory_read.assert_any_call(0x0400, 1000)
    assert text.splitlines()[0] == "READY."


def test_read_screen_text_follows_relocation():
    profile = get_profile("c64")
    mon = Mock()
    screen = bytes([13, 15, 22, 5, 4]) + bytes([32] * (1000 - 5))  # "MOVED"
    mon.memory_read.side_effect = lambda a, n: {
        0xDD00: bytes([0b11]), 0xD018: bytes([0x35]), 0x0C00: screen}[a]
    text = read_screen_text(mon, profile)
    mon.memory_read.assert_any_call(0x0C00, 1000)
    assert text.splitlines()[0] == "MOVED"


def test_save_screenshot_png(tmp_path):
    mon = Mock()
    mon.display.return_value = (2, 2, bytes([0, 1, 1, 0]))
    mon.palette.return_value = [(0, 0, 0), (0, 255, 0)]
    out = tmp_path / "shot.png"
    w, h = save_screenshot_png(mon, out)
    assert (w, h) == (2, 2)
    img = Image.open(out).convert("RGB")
    assert img.size == (2, 2)
    assert img.getpixel((1, 0)) == (0, 255, 0)
    assert img.getpixel((0, 0)) == (0, 0, 0)


def test_read_screen_text_styles():
    profile = get_profile("c64")
    mon = Mock()
    mon.memory_read.return_value = bytes([85, 64, 73]) + bytes([32] * 997)
    assert read_screen_text(mon, profile).splitlines()[0] == "╭─╮"
    mon.memory_read.return_value = bytes([85, 64, 73]) + bytes([32] * 997)
    assert read_screen_text(mon, profile, style="ascii").splitlines()[0] == "·-·"


def test_read_screen_codes_matrix():
    from c64lib.screen import read_screen_codes
    profile = get_profile("c64")
    mon = Mock()
    mon.memory_read.return_value = bytes(range(40)) + bytes([32] * 960)
    m = read_screen_codes(mon, profile)
    assert len(m) == 25 and all(len(r) == 40 for r in m)
    assert m[0][:3] == [0, 1, 2] and m[1][0] == 32


def test_save_screenshot_png_border_requests_full_frame(tmp_path):
    mon = Mock()
    mon.display.side_effect = lambda full=False: (
        (4, 4, bytes([1] * 4 + [1, 0, 0, 1] + [1, 0, 0, 1] + [1] * 4)) if full
        else (2, 2, bytes([0, 0, 0, 0]))
    )
    mon.palette.return_value = [(0, 0, 0), (255, 0, 0)]
    out = tmp_path / "bordered.png"
    w, h = save_screenshot_png(mon, out, border=True)
    assert (w, h) == (4, 4)
    img = Image.open(out).convert("RGB")
    assert img.getpixel((0, 0)) == (255, 0, 0)   # border pixel present
    assert img.getpixel((1, 1)) == (0, 0, 0)     # inner pixel still there


def test_save_screenshot_png_scale(tmp_path):
    mon = Mock()
    mon.display.return_value = (2, 2, bytes([0, 1, 1, 0]))
    mon.palette.return_value = [(0, 0, 0), (0, 255, 0)]
    out = tmp_path / "shot3x.png"
    w, h = save_screenshot_png(mon, out, scale=3)
    assert (w, h) == (6, 6)
    img = Image.open(out).convert("RGB")
    # nearest-neighbour: whole 3x3 cell keeps the source pixel colour
    assert img.getpixel((3, 0)) == (0, 255, 0)
    assert img.getpixel((5, 2)) == (0, 255, 0)
    assert img.getpixel((2, 2)) == (0, 0, 0)
