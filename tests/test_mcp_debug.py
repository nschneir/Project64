from unittest.mock import Mock, patch

import pytest

from c64lib.monitor import StopInfo
from c64lib.protocol import CP_EXEC, CP_LOAD, CP_STORE, Checkpoint
from tests.test_mcp_scaffold import call_tool


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def _fake(labels=None):
    s = Mock()
    s.name, s.model, s.labels = "c64", "c64", labels
    s.profile.basic_version = "2.0"
    s.profile.screen_cols = 40
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def _ck(number=1, start=0x040D, op=CP_EXEC, hit=False):
    return Checkpoint(number=number, hit=hit, start=start, end=start, stop=True,
                      enabled=True, op=op, temporary=False, hit_count=0,
                      ignore_count=0, has_condition=False, memspace=0)


def test_break_add_symbolic(tmp_path):
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:040d .start\n")
    s, mon = _fake(labels=str(lbl))
    mon.checkpoint_set.return_value = _ck()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_break_add", {"ref": "start"})
    assert err is False and out["id"] == 1
    mon.checkpoint_set.assert_called_once_with(0x040D, op=CP_EXEC, temporary=False)
    mon.release.assert_called_once()


def test_watch_add_store(tmp_path):
    s, mon = _fake()
    mon.checkpoint_set.return_value = _ck(op=CP_STORE, start=0x0400)
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_watch_add",
                             {"ref": "$0400", "on_store": True, "length": 40})
    assert err is False
    mon.checkpoint_set.assert_called_once_with(0x0400, 0x0400 + 39, op=CP_STORE)


def test_step_stays_stopped():
    s, mon = _fake()
    mon.step.return_value = {"PC": 0x0412}
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_step", {"count": 2})
    assert err is False and out["registers"]["PC"] == 0x0412 and out["stopped"] is True
    mon.step.assert_called_once_with(2, over=False)
    mon.resume.assert_not_called()


def test_until_timeout_returns_error():
    s, mon = _fake()
    mon.checkpoint_set.return_value = _ck(start=0x2000)
    mon.wait_for_stop.return_value = None
    mon.checkpoint_list.return_value = []
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_until", {"ref": "$2000", "timeout": 1})
    assert err is True and "timeout" in out["raw"].lower()


def test_wait_break_fires():
    s, mon = _fake()
    mon.checkpoint_list.return_value = []
    mon.wait_for_stop.return_value = StopInfo(pc=0x040D, checkpoint=5)
    mon.registers.return_value = {"PC": 0x040D}
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_wait_break", {"timeout": 2})
    assert err is False and out["fired"] == "break" and out["checkpoint"] == 5


def test_wait_text_timeout_not_error():
    s, mon = _fake()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.ops.read_screen_text", return_value="STUCK"), \
         patch("c64lib.ops.time.sleep"):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_text", {"text": "NEVER", "timeout": 0.3})
    assert err is False
    assert out["fired"] is None and "STUCK" in out["screen"]


def test_wait_text_since_forwarded():
    s, mon = _fake()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.wait_for_text",
               return_value={"fired": "text", "elapsed": 0.1}) as wft:
        S.attach.return_value = s
        err, out = call_tool("c64_wait_text", {"text": "TOO HIGH", "since": True})
    assert err is False and out["fired"] == "text"
    wft.assert_called_once_with(s, "TOO HIGH", 30.0, since=True)


def test_until_timeout_error_is_loud():
    s, _ = _fake()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.run_until",
               return_value={"registers": None, "reached": 0, "count": 2}):
        S.attach.return_value = s
        err, out = call_tool("c64_until", {"ref": "$040d", "count": 2,
                                           "timeout": 0.1})
    assert err is True
    assert "left RUNNING" in out["raw"] and "branch away" in out["raw"]


def test_key_hold_zero_frames_is_a_no_op_not_a_timeout():
    """`frames=0` must reach the caller as an honest no-op, the same as it
    does over the CLI: nothing is poked, no checkpoint is armed, so the
    fake "timeout: only 0/0 frame(s) … checkpoint removed" error the
    registers-is-None check used to raise is a lie about the machine."""
    s, mon = _fake()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_key_hold", {"key": "d", "at": "$0819",
                                              "frames": 0})
    assert err is False, out
    assert out == {"frames": 0, "requested": 0, "machine": "untouched"}
    mon.memory_write.assert_not_called()


def test_wait_break_timeout_reports_running():
    s, _ = _fake()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.wait_for_break",
               return_value={"fired": None, "timeout": 0.1}):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_break", {"timeout": 0.1})
    assert err is False and out["fired"] is None
    assert out["machine"] == "running"


def test_break_and_watch_clear_tools():
    s, mon = _fake()
    mon.checkpoint_list.return_value = [
        _ck(number=1), _ck(number=2, op=CP_LOAD | CP_STORE)]
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_break_clear", {})
    assert err is False and out == {"removed": [1], "count": 1}
    mon.checkpoint_list.return_value = [
        _ck(number=1), _ck(number=2, op=CP_LOAD | CP_STORE)]
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_watch_clear", {})
    assert err is False and out == {"removed": [2], "count": 1}


def test_call_tool_runs_routine():
    s, mon = _fake()
    fired = {"fired": True, "registers": {"PC": 0x0400, "A": 42}, "trap": 0x0400}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.call_routine", return_value=fired) as cr:
        S.attach.return_value = s
        err, out = call_tool("c64_call", {"routine": "$2000", "a": 5})
    assert not err, out
    assert cr.call_args.args[1] == 0x2000 and cr.call_args.kwargs["a"] == 5
    assert out["registers"]["A"] == 42 and out["fired"] is True


def test_wait_idle_fires_and_reports_elapsed():
    s, mon = _fake()
    mon.registers.return_value = {"PC": 0xE5D1}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.ops.time.sleep"):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_idle", {"timeout": 5})
    assert err is False and out["fired"] == "idle"


def test_wait_idle_timeout_is_data_not_an_error():
    """Parity with c64_wait_text: a timeout hands back what it saw (here the
    PCs, which name the wedge) instead of raising."""
    s, mon = _fake()
    mon.registers.return_value = {"PC": 0x033C}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.ops.time.sleep"):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_idle", {"timeout": 0.3})
    assert err is False
    assert out["fired"] is None and 0x033C in out["last_pcs"]
    assert out["machine"] == "running"
