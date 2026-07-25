from dataclasses import replace
from unittest.mock import Mock, patch

from PIL import Image

from c64lib import mcp_server
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


def _fake_session(cols: int):
    """A session whose profile is NOT 40 columns wide, so a hardcoded 40
    anywhere on the screen path shows up as a wrong ruler."""
    fake = Mock()
    fake.name, fake.model = "wide", "wide"
    fake.profile = replace(get_profile("c64"), screen_cols=cols)
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def _numbering_spy(seen: dict):
    def spy(text, cols=40):
        seen["cols"] = cols
        return number_screen_text(text, cols)
    return spy


def test_cli_numbered_uses_profile_screen_cols():
    """`c64 screen --numbered` must number against the machine profile's
    width, not number_screen_text's 40-column default."""
    from click.testing import CliRunner

    from c64lib.cli import main

    fake, mon = _fake_session(22)
    seen: dict = {}
    with patch("c64lib.cli.Session") as S, \
            patch("c64lib.cli.read_screen_text", return_value="HI\nTHERE"), \
            patch("c64lib.cli.number_screen_text",
                  side_effect=_numbering_spy(seen)):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["screen", "--numbered"])
    assert r.exit_code == 0, r.output
    assert seen["cols"] == 22                       # profile value, not 40
    assert r.output.splitlines()[0] == "   " + "0123456789" * 2 + "01"
    mon.release.assert_called_once()


def test_mcp_screen_text_numbered_uses_profile_screen_cols():
    """Same threading through the MCP tool, which numbers outside the
    monitor block."""
    fake, mon = _fake_session(22)
    seen: dict = {}
    with patch("c64lib.mcp_server.Session") as S, \
            patch("c64lib.mcp_server.read_screen_text", return_value="HI"), \
            patch("c64lib.mcp_server.number_screen_text",
                  side_effect=_numbering_spy(seen)):
        S.attach.return_value = fake
        out = mcp_server.c64_screen_text(numbered=True)
    assert seen["cols"] == 22                       # profile value, not 40
    assert out["text"].splitlines()[0] == "   " + "0123456789" * 2 + "01"
    mon.release.assert_called_once()
