from unittest.mock import Mock, call, patch

import pytest

from tests.test_cli_inspect import _vic_reads
from tests.test_mcp_scaffold import call_tool


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def _fake_session(labels=None):
    s = Mock()
    s.name, s.model, s.pid, s.port, s.labels = "c64", "c64", 1, 6502, labels
    s.loaded_prg, s.loaded_at, s.loaded_deps = None, 0.0, None
    s.profile.basic_version = "2.0"
    s.profile.screen_cols, s.profile.screen_rows = 40, 25
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def test_session_start():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.launch.return_value = s
        err, out = call_tool("c64_session_start", {"model": "c64"})
    assert err is False
    assert out == {"name": "c64", "model": "c64", "pid": s.pid, "port": 6502,
                   "symbols": None}
    S.launch.assert_called_once_with(model="c64", name=None, headless=True,
                                     warp=True, disk8=None, cart=None)


def test_session_stop_all():
    """CLI lockstep with `c64 session stop --all`: one call clears every
    session, including any whose emulator is already gone."""
    with patch("c64lib.mcp_server.Session") as S:
        S.stop_all.return_value = ["a", "b"]
        err, out = call_tool("c64_session_stop", {"all": True})
    assert err is False and out == {"stopped": ["a", "b"]}
    S.attach.assert_not_called()


def test_session_stop_all_with_a_name_is_an_error():
    with patch("c64lib.mcp_server.Session") as S:
        err, out = call_tool("c64_session_stop", {"all": True, "name": "boo"})
    assert err is True and "all" in out["raw"] and "boo" in out["raw"]
    S.stop_all.assert_not_called()
    S.attach.assert_not_called()


def test_session_stop_one_still_returns_a_bare_name():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_session_stop", {})
    assert err is False and out == {"stopped": "c64"}
    s.stop.assert_called_once()


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
    lbl.write_text("al C:0400 .screen\n", encoding="utf-8")
    s, mon = _fake_session(labels=str(lbl))
    mon.memory_read.side_effect = _vic_reads(bytes([1, 2]))
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_read", {"addr": "screen", "length": 2})
    assert err is False
    assert out["addr"] == 0x0400 and out["hex"] == "0102"
    # auto encoding adds the $DD00/$D018 reads screen_base() makes
    assert call(0x0400, 2) in mon.memory_read.call_args_list


def test_reg_get_includes_pc_symbol(tmp_path):
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:040d .start\n", encoding="utf-8")
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
    mon.memory_read.side_effect = _vic_reads(bytes([42, 0]), screen=0xC000)
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_read", {"addr": "$0400", "length": 2})
    assert err is False and out["bytes"] == [42, 0] and out["hex"] == "2a00"
    # CLI lockstep: `values` mirrors `bytes` so `mem get`-shaped code works
    assert out["values"] == out["bytes"]


def test_mem_read_reports_the_resolved_text_encoding():
    """CLI parity: `--as`/`encoding` and the resolved gloss, so an MCP client
    reading screen RAM is told the bytes are screen codes, not ASCII."""
    s, mon = _fake_session()
    mon.memory_read.side_effect = _vic_reads(b"\x13\x01\x0c\x05\x13")
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_read", {"addr": "$0400", "length": 5})
        assert err is False and out["text_encoding"] == "screen"
        err, out = call_tool("c64_mem_read", {"addr": "$0400", "length": 5,
                                              "encoding": "ascii"})
        assert err is False and out["text_encoding"] == "ascii"
        err, out = call_tool("c64_mem_read", {"addr": "$0400", "length": 5,
                                              "encoding": "nonsense"})
    assert err is True


def test_mem_find_tool():
    s, mon = _fake_session()
    mon.memory_read.return_value = b"\x2a\x00"
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_find",
                             {"values": ["$2a"], "start": "$0400", "length": 2})
    assert err is False and out["matches"] == [0x0400]


def test_mem_find_names_the_bad_byte_token():
    """Lockstep with `c64 mem find`: the MCP side parses through
    ops.parse_byte_values, so a junk token is named rather than surfacing
    a bare int() error that says nothing about WHICH value was wrong."""
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_mem_find",
                             {"values": ["$2a", "nope"], "start": "$0400"})
    assert err is True and "byte 1" in out["raw"] and "nope" in out["raw"]


def test_status_tool():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state", return_value="running"):
        S.attach.return_value = s
        err, out = call_tool("c64_status", {})
    assert err is False and out["state"] == "running" and out["name"] == "c64"


def test_reg_get_names_the_rom_region_for_a_pc_outside_ram():
    """CLI parity: `pc_region` tells an agent that a bare $E5D1 is KERNAL,
    reported whether or not a symbol matched; null for a PC in RAM."""
    s, mon = _fake_session()
    mon.registers.return_value = {"PC": 0xE5D1}
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_reg_get", {})
        assert err is False and out["pc_region"] == "KERNAL ROM"
        mon.registers.return_value = {"PC": 0x0810}
        err, out = call_tool("c64_reg_get", {})
    assert err is False and out["pc_region"] is None


def test_reg_get_reports_state():
    s, mon = _fake_session()
    mon.registers.return_value = {"PC": 0x040D}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state", return_value="running"):
        S.attach.return_value = s
        err, out = call_tool("c64_reg_get", {})
    assert out["state"] == "running"
