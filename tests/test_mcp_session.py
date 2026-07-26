from unittest.mock import Mock, patch

import pytest

from tests.test_mcp_scaffold import call_tool


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def _fake_session(labels=None):
    s = Mock()
    s.name, s.model, s.pid, s.port, s.labels = "c64", "c64", 1, 6502, labels
    s.loaded_prg, s.loaded_at, s.loaded_deps = None, 0.0, None
    s.profile.basic_version = "2.0"
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def test_session_start():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.launch.return_value = s
        err, out = call_tool("c64_session_start", {"model": "c64"})
    assert err is False and out["name"] == "c64" and out["port"] == 6502
    S.launch.assert_called_once_with(model="c64", name=None, headless=True,
                                     warp=True, disk8=None, cart=None)


def test_screen_text():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.read_screen_text", return_value="READY."):
        S.attach.return_value = s
        err, out = call_tool("c64_screen_text", {})
    assert err is False and out["text"] == "READY."
    mon.release.assert_called_once()


def test_no_session_is_actionable_error(tmp_path):
    err, out = call_tool("c64_screen_text", {})
    assert err is True
    assert "session" in out["raw"].lower()


def test_mem_read_symbolic(tmp_path):
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:0400 .screen\n")
    s, mon = _fake_session(labels=str(lbl))
    mon.memory_read.return_value = bytes([1, 2])
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_read", {"addr": "screen", "length": 2})
    assert err is False
    assert out["addr"] == 0x0400 and out["hex"] == "0102"
    mon.memory_read.assert_called_once_with(0x0400, 2)


def test_reg_get_includes_pc_symbol(tmp_path):
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:040d .start\n")
    s, mon = _fake_session(labels=str(lbl))
    mon.registers.return_value = {"PC": 0x040D, "A": 1}
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_reg_get", {})
    assert out["registers"]["PC"] == 0x040D and out["pc_symbol"] == "start"


def test_mem_write():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_write", {"addr": "$0400", "values": [8, 9]})
    assert err is False and out["written"] == 2
    mon.memory_write.assert_called_once_with(0x0400, bytes([8, 9]))


def test_mem_read_includes_bytes():
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([42, 0])
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_read", {"addr": "$0400", "length": 2})
    assert err is False and out["bytes"] == [42, 0] and out["hex"] == "2a00"


def test_mem_find_tool():
    s, mon = _fake_session()
    mon.memory_read.return_value = b"\x2a\x00"
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_find",
                             {"values": ["$2a"], "start": "$0400", "length": 2})
    assert err is False and out["matches"] == [0x0400]


def test_status_tool():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state", return_value="running"):
        S.attach.return_value = s
        err, out = call_tool("c64_status", {})
    assert err is False and out["state"] == "running" and out["name"] == "c64"


def test_reg_get_reports_state():
    s, mon = _fake_session()
    mon.registers.return_value = {"PC": 0x040D}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state", return_value="running"):
        S.attach.return_value = s
        err, out = call_tool("c64_reg_get", {})
    assert out["state"] == "running"
