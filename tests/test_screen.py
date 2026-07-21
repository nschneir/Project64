from unittest.mock import Mock

from PIL import Image

from c64lib.machines import get_profile
from c64lib.screen import read_screen_text, save_screenshot_png


def test_read_screen_text_uses_profile_geometry():
    profile = get_profile("c64")
    mon = Mock()
    screen = bytes([18, 5, 1, 4, 25, 46]) + bytes([32] * (1000 - 6))  # "READY."
    mon.memory_read.return_value = screen
    text = read_screen_text(mon, profile)
    mon.memory_read.assert_called_once_with(0x0400, 1000)
    assert text.splitlines()[0] == "READY."


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
