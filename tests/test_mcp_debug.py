import json
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


def _cli(session, argv: list[str]) -> dict:
    """Run one `--json` CLI command against `session`, returning its payload."""
    from click.testing import CliRunner

    from c64lib.cli import main
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = session
        r = CliRunner().invoke(main, ["--json", *argv])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)


def test_break_list_tool_payload_matches_the_cli():
    """`c64_break_list` emitted the raw `op` bitmask where `c64 break list
    --json` emits the `exec|load|store` string — same key, same command, two
    types. Both front ends drive the *same* fake session here, so the payloads
    are compared whole; no key is excused.
    """
    s, mon = _fake()
    mon.checkpoint_list.return_value = [
        _ck(number=1, op=CP_EXEC),
        _ck(number=2, start=0x0400, op=CP_LOAD | CP_STORE),
    ]
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, mcp_payload = call_tool("c64_break_list", {})
    assert err is False
    assert mcp_payload == _cli(s, ["break", "list"])
    assert [b["op"] for b in mcp_payload["breakpoints"]] == ["exec", "load|store"]


def test_watch_add_tool_payload_matches_the_cli():
    """`c64_watch_add` omitted `op` altogether where `c64 watch add --json`
    reports it. Same fake session on both sides, so compared whole.
    """
    s, mon = _fake()
    mon.checkpoint_set.return_value = _ck(number=3, start=0x0400,
                                          op=CP_LOAD | CP_STORE)
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, mcp_payload = call_tool("c64_watch_add", {"ref": "$0400", "length": 40})
    assert err is False
    assert mcp_payload == _cli(s, ["watch", "add", "$0400", "--length", "40"])
    assert mcp_payload["op"] == "load|store"


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
         patch("c64lib.mcp_server.machine_state", return_value="running"), \
         patch("c64lib.ops.read_screen_text", return_value="STUCK"), \
         patch("c64lib.ops.time.sleep"):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_text", {"text": "NEVER", "timeout": 0.3})
    assert err is False
    assert out["fired"] is None and "STUCK" in out["screen"]
    # A machine that ran the whole window genuinely never printed the text;
    # pointing the client at c64_continue there would be a wrong answer.
    assert out["machine"] == "running" and "diagnosis" not in out


def test_wait_text_timeout_says_the_machine_was_stopped():
    """CLI/MCP lockstep on the same footgun `c64_wait_mem` already reports: a
    wait polls the screen and never resumes the CPU, so a machine halted for
    the whole window could print nothing. The timeout is data here, so the
    `diagnosis` key is the only place that prose can live."""
    s, _ = _fake()
    timed_out = {"fired": None, "timeout": 0.3, "screen": "READY."}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state", return_value="stopped"), \
         patch("c64lib.mcp_server.wait_for_text", return_value=dict(timed_out)):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_text", {"text": "NEVER", "timeout": 0.3})
    assert err is False, out
    assert out["machine"] == "stopped"
    assert "STOPPED for the whole wait" in out["diagnosis"]
    assert "c64_continue" in out["diagnosis"], "no way out is named"


def test_wait_idle_timeout_says_the_machine_was_stopped():
    """The other half of the lockstep. A stopped machine cannot reach direct
    mode and is not wedged, so "running" here would point the client at the
    wedge hunt (disassemble the loop, step it) on a PC that cannot move."""
    s, _ = _fake()
    timed_out = {"fired": None, "timeout": 0.3, "last_pcs": [0x033C, 0x033C]}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state", return_value="stopped"), \
         patch("c64lib.mcp_server.wait_for_idle", return_value=dict(timed_out)):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_idle", {"timeout": 0.3})
    assert err is False, out
    assert out["machine"] == "stopped"
    assert "STOPPED for the whole wait" in out["diagnosis"]
    assert "c64_continue" in out["diagnosis"], "no way out is named"


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


def test_key_hold_releases_by_default_over_mcp():
    """CLI/MCP lockstep: the tool defaults to releasing the key, forwards
    the same `release` argument, and passes `released` back to the caller."""
    s, _ = _fake()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.key_hold",
               return_value={"frames": 2, "requested": 2, "released": True,
                             "registers": {"PC": 0x0819}}) as kh:
        S.attach.return_value = s
        err, out = call_tool("c64_key_hold", {"key": "d", "at": "$0819",
                                              "frames": 2})
    assert err is False, out
    assert kh.call_args.kwargs["release"] is True
    assert out["released"] is True and out["frames"] == 2


def test_key_hold_timeout_reports_the_key_state_over_mcp():
    """Same lockstep on the error path: the timeout says the key was let
    go, and with release=false it names $CB and the poke that clears it
    (an MCP error is text only — there is no extras dict to carry it)."""
    s, _ = _fake()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.key_hold",
               return_value={"frames": 1, "requested": 5, "released": True,
                             "registers": None}):
        S.attach.return_value = s
        err, out = call_tool("c64_key_hold", {"key": "d", "at": "$0819",
                                              "frames": 5})
    assert err is True
    assert "left RUNNING" in out["raw"] and "key released" in out["raw"]

    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.key_hold",
               return_value={"frames": 0, "requested": 3, "released": False,
                             "registers": None}):
        S.attach.return_value = s
        err, out = call_tool("c64_key_hold", {"key": "d", "at": "$0819",
                                              "frames": 3, "release": False})
    assert err is True
    assert "$CB" in out["raw"] and "c64_mem_write" in out["raw"]


def test_key_hold_release_false_is_forwarded_over_mcp():
    s, _ = _fake()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.key_hold",
               return_value={"frames": 1, "requested": 1, "released": False,
                             "registers": {"PC": 0x0819}}) as kh:
        S.attach.return_value = s
        err, out = call_tool("c64_key_hold", {"key": "d", "at": "$0819",
                                              "release": False})
    assert err is False, out
    assert kh.call_args.kwargs["release"] is False
    assert out["released"] is False


def test_key_hold_negative_frames_is_an_error():
    """`frames < 0` is the one hold length that is neither work nor a
    no-op: it must come back as an error naming `frames`, with nothing
    poked — not as a silent success like `frames=0`."""
    s, mon = _fake()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_key_hold", {"key": "d", "at": "$0819",
                                              "frames": -1})
    assert err is True
    assert "frames" in out["raw"]
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


def test_call_tool_timeout_is_an_error():
    """A routine that never returned is a failure, not a payload with
    fired=false: a client that does not inspect `fired` would otherwise read
    a runaway routine as a completed call. Same contract as c64_until and
    c64_profile, and the same wording as `c64 call`'s exit-1 message."""
    s, _ = _fake()
    never = {"fired": False, "registers": None, "trap": 0x2000}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.call_routine", return_value=never):
        S.attach.return_value = s
        err, out = call_tool("c64_call", {"routine": "$2000", "timeout": 0.1})
    assert err is True
    # byte-identical to `c64 call`'s fail() message (FastMCP prefixes the raw
    # text with "Error executing tool c64_call: ").
    assert out["raw"].endswith(
        "call $2000: never returned in 0.1s — machine left running (runaway "
        "routine? check the address is a subroutine ending in RTS)")


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
         patch("c64lib.mcp_server.machine_state", return_value="running"), \
         patch("c64lib.ops.time.sleep"):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_idle", {"timeout": 0.3})
    assert err is False
    assert out["fired"] is None and 0x033C in out["last_pcs"]
    # Patched, because an unpatched Mock session makes `machine_state` return a
    # Mock: it compares unequal to "stopped" and "running" falls out however
    # the arm is wired. Same pin as `test_wait_text_timeout_not_error`.
    assert out["machine"] == "running" and "diagnosis" not in out
