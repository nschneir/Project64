from unittest.mock import Mock, patch

import pytest

from tests.test_mcp_scaffold import call_tool


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def _vic():
    v = bytearray(0x2F)
    v[0x00], v[0x01] = 100, 120
    v[0x02], v[0x03] = 44, 55
    v[0x10] = 0b00000010
    v[0x15] = 0b00000011
    v[0x20], v[0x21] = 14, 6
    v[0x25], v[0x26] = 10, 11
    v[0x27], v[0x28] = 7, 2
    return bytes(v)


def _fake_session():
    s = Mock()
    s.name, s.model, s.labels = "c64", "c64", None
    s.profile.screen_addr = 0x0400
    s.profile.screen_cols = 40
    mon = Mock()
    mem = {0xDD00: bytes([0b11]), 0xD018: bytes([0x15]), 0xD000: _vic(),
           0x07F8: bytes([13, 0x80, 0, 0, 0, 0, 0, 0]),
           0x0340: bytes([0b10000000, 0, 0] + [0] * 60)}
    mon.memory_read.side_effect = lambda a, n: mem[a][:n]
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def test_sprite_status():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_sprite_status", {})
    assert err is False
    assert len(out["sprites"]) == 8
    assert out["sprites"][1]["x"] == 300
    assert out["shared"]["background"] == 6
    mon.release.assert_called()


def test_sprite_show():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_sprite_show", {"index": 0, "block": "$0340"})
    assert err is False
    assert len(out["rows"]) == 21 and out["rows"][0][0] == "█"
    assert out["block_addr"] == 0x0340


def test_sprite_png(tmp_path):
    s, _ = _fake_session()
    dest = tmp_path / "s.png"
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_sprite_png",
                             {"index": 0, "path": str(dest),
                              "scale": 2, "block": "$0340"})
    assert err is False
    assert (out["width"], out["height"]) == (48, 42)
    from PIL import Image
    assert Image.open(dest).size == (48, 42)


def test_sprite_bad_index_is_error():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_sprite_show", {"index": 9})
    assert err is True
    assert "0-7" in out["raw"]


def test_sprite_from_png_needs_no_session(tmp_path):
    from PIL import Image
    src = tmp_path / "in.png"
    img = Image.new("RGB", (24, 21), (255, 255, 255))
    img.putpixel((0, 0), (0, 0, 0))
    img.save(src)
    err, out = call_tool("c64_sprite_from_png", {"image": str(src)})
    assert err is False
    assert len(out["bytes"]) == 63 and out["bytes"][0] == 0b10000000
    assert any(".byte %10000000" in ln for ln in out["rows"])
