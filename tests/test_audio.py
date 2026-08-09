"""Unit tests for c64lib.audio.

Three behaviours carry the whole module: the exact resource sequence VICE
needs to arm its WAV recorder (arg BEFORE name, or it drops vicesnd.wav in
the process CWD), the warp/speed pin — under warp VICE writes a 0-frame
WAV, so a capture that forgets to clear warp fails silently — and the
per-frame SID sampling loop, whose one frame per resume is the only frame
clock the binary monitor offers (see FakeMachine).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import threading
import time
import wave
from pathlib import Path
from unittest.mock import Mock, call, patch

import numpy as np
import pytest
import yaml
from click.testing import CliRunner

from c64lib import audio, sid_analysis
from c64lib.audio import (
    AudioError,
    capture,
    pin_realtime,
    pinned_record_start,
    pinned_record_stop,
    record_start,
    record_stop,
    restore_speed,
    sid_log,
    sid_log_detail,
)
from c64lib.build import build_asm
from c64lib.cli import main
from c64lib.daemon_client import DaemonMonitorClient
from c64lib.ops import wait_for_mem
from c64lib.session import Session, SessionError
from tests.test_mcp_scaffold import call_tool
from tests.vice_helpers import timeout_scale


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


# --- a stand-in for VICE's text monitor -------------------------------------

class FakeTextMonitor:
    """VICE's text monitor as the real one behaves: no banner, an
    asynchronous and repeated `(C:$xxxx) ` prompt echo, and a `warp` command
    that reports state when given no argument. Records every line sent."""

    def __init__(self, warp: bool = True):
        self.warp = warp
        self.lines: list[str] = []
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(4)
        self.port = self._srv.getsockname()[1]
        self._closed = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._closed:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            with conn:
                self._converse(conn)

    def _converse(self, conn: socket.socket) -> None:
        conn.sendall(b"(C:$e5d4) ")
        buf = b""
        while True:
            try:
                data = conn.recv(4096)
            except OSError:
                return
            if not data:
                return
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("ascii", "replace").strip()
                self.lines.append(line)
                try:
                    conn.sendall(self.reply(line) + b"(C:$e5d4) ")
                except OSError:
                    return
                if line == "x":
                    return

    def reply(self, line: str) -> bytes:
        if line == "warp on":
            self.warp = True
        elif line == "warp off":
            self.warp = False
        elif line == "warp":
            return b"Warp mode is " + (b"on" if self.warp else b"off") + b".\n"
        return b""

    def settle(self, timeout: float = 2.0) -> None:
        """Wait for the client's parting `x` to be logged.

        `close()` does drain the reply to `x`, so the line is normally already
        recorded by the time it returns — but the drain gives up after 50 ms,
        and this server logs the line on its own thread, so a loaded host can
        still have `close()` return first. Belt and braces before any
        assertion on `lines`.
        """
        end = time.monotonic() + timeout
        while time.monotonic() < end and self.lines[-1:] != ["x"]:
            time.sleep(0.01)

    def close(self) -> None:
        self._closed = True
        self._srv.close()


class StubbornTextMonitor(FakeTextMonitor):
    """A VICE that acknowledges `warp off` and stays warped anyway."""

    def reply(self, line: str) -> bytes:
        return super().reply("warp" if line == "warp" else "")


class WithholdingTextMonitor(FakeTextMonitor):
    """VICE mid-stall, as the wire traces caught it: the first bare `warp`
    query gets no answer at all — the reply is withheld, not lost — while the
    prompt echo keeps flowing, and asking again is answered normally.
    `withhold` is how many queries go unanswered before one is."""

    withhold = 1

    def __init__(self, warp: bool = True):
        super().__init__(warp)
        self.queries = 0

    def reply(self, line: str) -> bytes:
        if line == "warp":
            self.queries += 1
            if self.queries <= self.withhold:
                return b""
        return super().reply(line)


class MuteTextMonitor(WithholdingTextMonitor):
    """A text monitor that never answers `warp` at all — the stall no retry
    can rescue, which must still fail rather than hang."""

    withhold = 1 << 30


@pytest.fixture
def vice_text(request):
    cls = getattr(request, "param", FakeTextMonitor)
    srv = cls()
    yield srv
    srv.close()


#: What a FRESH VICE answers for the resources audio.py reads — measured on
#: a headless session that had never run a text monitor. The address has a
#: factory default, so reading one back is no evidence that anybody set it;
#: a fake that starts it empty hides a whole class of bug (it did).
VICE_DEFAULTS = {"MonitorServerAddress": "ip4://127.0.0.1:6510",
                 "MonitorServer": 0, "Speed": 100}


def _fake_session(speed: int = 100, pid: int = 4242, **resources):
    """A Session whose monitor() hands out one Mock. Resources behave like
    VICE's: they start at their factory defaults, and what was set is what
    reads back — so a second capture sees the text monitor the first one
    actually switched on."""
    s = Mock()
    s.name, s.model, s.socket, s.pid = "c64", "c64", None, pid
    mon = Mock()
    values = {**VICE_DEFAULTS, "Speed": speed, **resources}
    mon.resource_get.side_effect = lambda n: values[n]
    mon.resource_set.side_effect = values.__setitem__
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def _names(mon) -> list[str]:
    """The resource names set, in order — the sequence IS the contract."""
    return [c.args[0] for c in mon.resource_set.call_args_list]


def _port(srv):
    """Patch the free-port picker so audio.py points VICE at our fake."""
    return patch("c64lib.audio._free_port", return_value=srv.port)


# --- record_start / record_stop ---------------------------------------------

def test_record_start_sets_the_arg_before_the_device_name(tmp_path):
    """Arming with no arg drops vicesnd.wav into VICE's CWD; the order is
    the whole point of this function."""
    s, mon = _fake_session()
    wav = tmp_path / "boot.wav"
    assert record_start(s, str(wav)) == str(wav)
    assert mon.resource_set.call_args_list == [
        call("SoundRecordDeviceArg", str(wav)),
        call("SoundRecordDeviceName", "wav"),
    ]


def test_record_start_makes_a_relative_path_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s, mon = _fake_session()
    assert record_start(s, "out.wav") == str(tmp_path / "out.wav")
    assert mon.resource_set.call_args_list[0] == call(
        "SoundRecordDeviceArg", str(tmp_path / "out.wav"))


def test_record_start_leaves_the_machine_running(tmp_path):
    """Samples only accumulate while the machine runs, and every binary
    monitor command halts it."""
    s, mon = _fake_session()
    record_start(s, str(tmp_path / "a.wav"))
    mon.resume.assert_called_once()


def test_record_stop_clears_the_device_name():
    s, mon = _fake_session()
    record_stop(s)
    assert mon.resource_set.call_args_list == [call("SoundRecordDeviceName", "")]


# --- pin_realtime / restore_speed -------------------------------------------

def test_pin_realtime_starts_the_text_monitor_then_clears_warp(vice_text):
    s, mon = _fake_session(speed=100)
    with _port(vice_text):
        saved = pin_realtime(s)
    assert saved == {"warp": True, "speed": 100}
    # address must be set before the server is switched on
    assert _names(mon) == ["MonitorServerAddress", "MonitorServer", "Speed"]
    assert mon.resource_set.call_args_list[:2] == [
        call("MonitorServerAddress", f"ip4://127.0.0.1:{vice_text.port}"),
        call("MonitorServer", 1),
    ]
    assert mon.resource_set.call_args_list[2] == call("Speed", 100)
    assert vice_text.warp is False
    # read state, clear it, confirm it, leave the monitor
    vice_text.settle()
    assert vice_text.lines == ["warp", "warp off", "warp", "x"]


def test_pin_realtime_reuses_the_listener_it_already_switched_on(vice_text):
    """MonitorServer stays on for the session's life; a second capture must
    reuse that listener, not point VICE somewhere new."""
    s, mon = _fake_session(MonitorServer=1,
                           MonitorServerAddress=f"ip4://127.0.0.1:{vice_text.port}")
    with patch("c64lib.audio._free_port",
               side_effect=AssertionError("picked a new port")):
        pin_realtime(s)
    assert _names(mon) == ["MonitorServer", "Speed"]


def test_pin_realtime_never_trusts_vices_default_text_monitor_address(vice_text):
    """`MonitorServerAddress` reads `ip4://127.0.0.1:6510` on a session that
    has never run a text monitor, so treating "an address is set" as "our
    listener is up" points EVERY session at 6510 — where only the first VICE
    to bind wins and every other session's client silently drives that
    emulator instead. `MonitorServer` is the signal that separates the two."""
    s, mon = _fake_session()          # MonitorServer 0, address 6510
    with _port(vice_text):
        pin_realtime(s)
    assert mon.resource_set.call_args_list[0] == call(
        "MonitorServerAddress", f"ip4://127.0.0.1:{vice_text.port}")
    assert vice_text.port != 6510 and vice_text.lines[0] == "warp"


def test_pin_realtime_saves_a_non_default_speed(vice_text):
    s, mon = _fake_session(speed=200)
    with _port(vice_text):
        saved = pin_realtime(s)
    assert saved["speed"] == 200
    assert call("Speed", 100) in mon.resource_set.call_args_list


def test_pin_realtime_skips_the_warp_command_when_warp_is_already_off(vice_text):
    vice_text.warp = False
    s, _ = _fake_session()
    with _port(vice_text):
        saved = pin_realtime(s)
    assert saved["warp"] is False
    vice_text.settle()
    assert vice_text.lines == ["warp", "x"]


@pytest.mark.parametrize("vice_text", [StubbornTextMonitor], indirect=True)
def test_pin_realtime_raises_when_warp_will_not_clear(vice_text):
    """The failure this guards against is silent: a warped capture yields a
    0-frame WAV, not a fast one."""
    s, _ = _fake_session()
    with _port(vice_text), pytest.raises(AudioError, match="warp"):
        pin_realtime(s)


@pytest.mark.parametrize("vice_text", [StubbornTextMonitor], indirect=True)
def test_a_failed_pin_puts_the_speed_back(vice_text):
    """Nobody holds the saved state until pin_realtime returns, so a pin
    that fails half way has to undo itself — there is no one else left who
    could."""
    s, mon = _fake_session(speed=200)
    with _port(vice_text), pytest.raises(AudioError):
        pin_realtime(s)
    assert mon.resource_set.call_args_list[-1] == call("Speed", 200)


def test_a_failed_speed_pin_leaves_warp_alone(vice_text):
    """Warp is cleared last, so the step most likely to fail — two binary
    monitor round trips, where a live TimeoutError has been seen — happens
    while the machine is still as the caller handed it over."""
    s, mon = _fake_session()

    def refuse(name, value):
        if name == "Speed":
            raise TimeoutError("timed out")

    mon.resource_set.side_effect = refuse
    with _port(vice_text), pytest.raises(TimeoutError):
        pin_realtime(s)
    assert vice_text.warp is True
    vice_text.settle()
    assert "warp off" not in vice_text.lines


def test_pin_realtime_reports_an_unreachable_text_monitor():
    s, _ = _fake_session()
    with socket.socket() as probe:            # a port with nothing listening
        probe.bind(("127.0.0.1", 0))
        dead = probe.getsockname()[1]
    with patch("c64lib.audio._free_port", return_value=dead), \
         patch("c64lib.audio._TextMonitor._CONNECT_TIMEOUT", 0.3), \
         pytest.raises(AudioError, match="text monitor"):
        pin_realtime(s)


def test_restore_speed_puts_back_both_halves(vice_text):
    vice_text.warp = False
    s, mon = _fake_session()
    with _port(vice_text):
        restore_speed(s, {"warp": True, "speed": 200})
    assert call("Speed", 200) in mon.resource_set.call_args_list
    assert vice_text.warp is True
    vice_text.settle()
    assert vice_text.lines == ["warp on", "warp", "x"]


def test_restore_speed_leaves_warp_off_when_the_session_was_not_warped(vice_text):
    """A session booted without -warp must not come back warped."""
    vice_text.warp = False
    s, mon = _fake_session()
    with _port(vice_text):
        restore_speed(s, {"warp": False, "speed": 100})
    assert call("Speed", 100) in mon.resource_set.call_args_list
    assert vice_text.lines == []          # no text-monitor traffic at all


# --- the withheld warp readback ----------------------------------------------

@pytest.mark.parametrize("vice_text", [WithholdingTextMonitor], indirect=True)
def test_the_warp_readback_is_re_sent_when_the_first_reply_is_withheld(vice_text):
    """The measured wedge: VICE withholds the `warp on` confirmation until
    more input arrives, so waiting longer never gets it (a 30 s timeout stalled
    the full 30.1 s) and only re-sending does. Asking again rescued 39 of 39
    stalls across 240 measured cycles — see the wedge investigation. Without
    it this raises, the socket is torn down mid-stall, and that session's text
    monitor never answers again."""
    vice_text.warp = False
    s, mon = _fake_session()
    with _port(vice_text), \
         patch.object(audio._TextMonitor, "_REPLY_TIMEOUT", 0.2):
        restore_speed(s, {"warp": True, "speed": 200})
    assert call("Speed", 200) in mon.resource_set.call_args_list
    assert vice_text.warp is True                  # the restore completed
    vice_text.settle()
    # the second `warp` is the retry: one query answered nothing, one answered
    assert vice_text.lines == ["warp on", "warp", "warp", "x"]


@pytest.mark.parametrize("vice_text", [MuteTextMonitor], indirect=True)
def test_a_readback_nobody_answers_fails_cleanly_instead_of_hanging(vice_text):
    """The retry is bounded: two attempts at the same reply timeout, then an
    AudioError that names what happened. A monitor that has genuinely stopped
    answering must still cost a fixed amount of time."""
    s, _ = _fake_session()
    started = time.monotonic()
    with _port(vice_text), \
         patch.object(audio._TextMonitor, "_REPLY_TIMEOUT", 0.2), \
         pytest.raises(AudioError, match="did not report a warp state"):
        pin_realtime(s)
    elapsed = time.monotonic() - started
    assert elapsed < 2.0, f"took {elapsed:.2f}s for two 0.2s attempts"
    vice_text.settle()
    assert vice_text.lines.count("warp") == 2      # asked twice, then gave up
    assert vice_text.lines[-1] == "x"              # and let go of the monitor


# --- the composed start/stop the MCP tool and CLI use ------------------------

def test_pinned_record_start_pins_before_it_arms(vice_text, tmp_path):
    s, mon = _fake_session()
    wav = tmp_path / "cap.wav"
    with _port(vice_text):
        out = pinned_record_start(s, str(wav))
    assert out == {"wav": str(wav), "pinned": {"warp": True, "speed": 100}}
    assert _names(mon) == ["MonitorServerAddress", "MonitorServer", "Speed",
                           "SoundRecordDeviceArg", "SoundRecordDeviceName"]
    assert vice_text.warp is False


def test_pinned_record_stop_disarms_then_restores(vice_text, tmp_path):
    s, mon = _fake_session()
    wav = tmp_path / "cap.wav"
    with _port(vice_text):
        pinned_record_start(s, str(wav))
        wav.write_bytes(b"RIFF" + bytes(60))
        mon.resource_set.reset_mock()
        out = pinned_record_stop(s)
    assert out == {"wav": str(wav), "bytes": 64,
                   "restored": {"warp": True, "speed": 100}}
    # disarm, unpin the speed, then re-warp (the address is already set, so
    # only the server switch is touched the second time round)
    assert _names(mon) == ["SoundRecordDeviceName", "Speed", "MonitorServer"]
    assert mon.resource_set.call_args_list[0] == call("SoundRecordDeviceName", "")
    assert vice_text.warp is True


def test_pinned_record_stop_forgets_the_pin_so_it_cannot_be_restored_twice(
        vice_text, tmp_path):
    s, _ = _fake_session()
    with _port(vice_text):
        pinned_record_start(s, str(tmp_path / "cap.wav"))
        pinned_record_stop(s)
        again = pinned_record_stop(s)
    assert again == {"wav": None, "bytes": None, "restored": None}


def test_a_second_start_keeps_the_first_pins_saved_state(vice_text, tmp_path):
    """The second pin only re-reads what the first one imposed (warp off,
    speed 100). Saving that would strand the session unwarped for good."""
    s, _ = _fake_session(speed=200)
    with _port(vice_text):
        pinned_record_start(s, str(tmp_path / "one.wav"))
        out = pinned_record_start(s, str(tmp_path / "two.wav"))
        assert out["pinned"] == {"warp": True, "speed": 200}
        assert pinned_record_stop(s)["restored"] == {"warp": True, "speed": 200}
    assert vice_text.warp is True


def test_a_pin_left_behind_by_a_dead_session_is_discarded(vice_text, tmp_path):
    """A session killed between start and stop leaves its sidecar in place.
    The next session to take that name must not inherit a dead machine's
    saved state in preference to what it just read live."""
    s, _ = _fake_session(pid=222, speed=200)
    audio._pin_path(s).write_text(json.dumps(
        {"warp": True, "speed": 50, "wav": "/gone.wav", "pid": 111}))
    with _port(vice_text):
        out = pinned_record_start(s, str(tmp_path / "cap.wav"))
    assert out["pinned"] == {"warp": True, "speed": 200}


def test_a_dead_sessions_pin_cannot_warp_its_replacement(vice_text, tmp_path):
    """The concrete break: pinned while warped, killed, replaced by a
    session booted WITHOUT --warp. Honouring the corpse's `warp: true`
    would warp a session that never was — the one thing restore_speed
    exists to refuse."""
    vice_text.warp = False                       # the replacement is unwarped
    s, _ = _fake_session(pid=222)
    audio._pin_path(s).write_text(json.dumps(
        {"warp": True, "speed": 100, "wav": "/gone.wav", "pid": 111}))
    with _port(vice_text):
        pinned_record_start(s, str(tmp_path / "cap.wav"))
        out = pinned_record_stop(s)
    assert out["restored"] == {"warp": False, "speed": 100}
    assert vice_text.warp is False


def test_stopping_a_session_clears_its_audio_pin():
    """Session.stop() prunes the sidecar, so a name that comes back cannot
    come back holding a pin."""
    from c64lib.session import Session, audio_pin_path
    audio_pin_path("gone").write_text('{"pid": 1}')
    dead = Session(name="gone", pid=424242, port=1, model="c64")
    with patch("c64lib.session._pid_alive", return_value=False):
        dead.stop()
    assert not audio_pin_path("gone").exists()


def test_an_unreadable_pin_is_reported_not_swallowed(vice_text, capsys):
    """A truncated sidecar (crash mid-write) means nobody will unpin the
    session; saying nothing leaves it at 1x with no diagnostic."""
    s, _ = _fake_session()
    audio._pin_path(s).write_text('{"warp": tru')
    out = pinned_record_stop(s)
    assert out["restored"] is None
    assert "unreadable" in capsys.readouterr().err
    assert not audio._pin_path(s).exists()


def test_a_pin_that_cannot_be_opened_is_kept_not_deleted(vice_text, capsys, tmp_path):
    """A read that fails for reasons outside the file's CONTENT — permissions,
    a flaky filesystem — says nothing about whether the restore state is
    intact, and it very likely is. Deleting it there turned a transient error
    into a permanently unpinnable session; keep it and say so."""
    s, _ = _fake_session()
    path = audio._pin_path(s)
    path.write_text(json.dumps({"warp": True, "speed": 100, "pid": s.pid}))
    with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
        out = pinned_record_stop(s)
    assert out["restored"] is None
    err = capsys.readouterr().err
    assert "could not be read" in err and "left in place" in err
    assert "is unreadable" not in err
    assert path.exists(), "a transient read error must not destroy the pin"


def test_a_pin_without_a_pid_stamp_is_an_upgrade_not_a_corruption(vice_text, capsys):
    """A sidecar written before the pid stamp existed is perfectly readable —
    it just cannot be shown to belong to this session. Reporting it as
    "unreadable" described a file that parsed fine."""
    s, _ = _fake_session()
    audio._pin_path(s).write_text(json.dumps({"warp": True, "speed": 200}))
    out = pinned_record_stop(s)
    assert out["restored"] is None
    err = capsys.readouterr().err
    assert "predates the session-pid stamp" in err
    assert "unreadable" not in err
    assert not audio._pin_path(s).exists()


def test_load_all_prunes_a_dead_sessions_audio_pin():
    """`stop()` clears the sidecar, but a killed session never reaches
    `stop()` — which is the common way a record ends up dead. Inert either
    way thanks to the pid stamp, so this is housekeeping: without it a
    `<name>.audio` outlives every session whose name is never reused."""
    from c64lib.session import Session, audio_pin_path, sessions_dir
    (sessions_dir() / "ghost.json").write_text(json.dumps(
        {"name": "ghost", "pid": 424242, "port": 1, "model": "c64"}))
    audio_pin_path("ghost").write_text(json.dumps({"pid": 424242}))
    with patch("c64lib.session._pid_alive", return_value=False):
        assert Session.list_all() == []
    assert not (sessions_dir() / "ghost.json").exists()
    assert not audio_pin_path("ghost").exists()


def test_the_pin_sidecar_is_not_read_back_as_a_session_record(vice_text, tmp_path):
    """Session._load_all() parses every *.json in the session directory, so
    a pin file named `<session>.audio.json` there breaks every later `c64`
    command with `KeyError: 'name'` — found live, hence this test."""
    from c64lib.session import Session
    s, _ = _fake_session()
    with _port(vice_text):
        pinned_record_start(s, str(tmp_path / "cap.wav"))
    assert audio._pin_path(s).exists()
    assert Session.list_all() == []


def test_pinned_record_start_unpins_when_arming_fails(vice_text, tmp_path):
    """A failed capture must not leave the session pinned at 1x."""
    s, mon = _fake_session(speed=200)

    def refuse(name, value):
        if name == "SoundRecordDeviceArg":
            raise RuntimeError("no such resource")

    mon.resource_set.side_effect = refuse
    with _port(vice_text), pytest.raises(RuntimeError, match="no such resource"):
        pinned_record_start(s, str(tmp_path / "cap.wav"))
    assert vice_text.warp is True                          # warp put back
    assert call("Speed", 200) in mon.resource_set.call_args_list   # and speed
    assert not audio._pin_path(s).exists()                 # no pin left behind


# --- MCP tool ---------------------------------------------------------------

def test_mcp_audio_record_start(tmp_path):
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.pinned_record_start",
               return_value={"wav": "/tmp/a.wav", "pinned": {}}) as start:
        S.attach.return_value = s
        err, out = call_tool("c64_audio_record",
                             {"action": "start", "path": "/tmp/a.wav"})
    assert err is False and out["wav"] == "/tmp/a.wav"
    start.assert_called_once_with(s, "/tmp/a.wav")


def test_mcp_audio_record_stop():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.pinned_record_stop",
               return_value={"wav": "/tmp/a.wav", "bytes": 64,
                             "restored": None}) as stop:
        S.attach.return_value = s
        err, out = call_tool("c64_audio_record", {"action": "stop"})
    assert err is False and out["bytes"] == 64
    stop.assert_called_once_with(s)


def test_mcp_audio_record_start_really_pins_the_session(vice_text, tmp_path):
    """The "always pin" contract, asserted at the MCP layer itself.

    Every other test here patches `pinned_record_start` wholesale, so the
    front ends were only ever checked for forwarding their arguments to
    *something* — a tool wired to bare `record_start` would have passed them
    all, and produced a 0-frame WAV on every warped session. This one lets
    the real composition run against the fake VICE and reads the outcome off
    the machine: warp cleared, Speed pinned, recorder armed last.
    """
    s, mon = _fake_session()
    wav = tmp_path / "mcp.wav"
    with patch("c64lib.mcp_server.Session") as S, _port(vice_text):
        S.attach.return_value = s
        err, out = call_tool("c64_audio_record",
                             {"action": "start", "path": str(wav)})
    assert err is False and out["wav"] == str(wav)
    assert vice_text.warp is False, "the MCP tool armed a recorder under warp"
    assert _names(mon) == ["MonitorServerAddress", "MonitorServer", "Speed",
                           "SoundRecordDeviceArg", "SoundRecordDeviceName"]
    assert call("Speed", 100) in mon.resource_set.call_args_list


def test_cli_audio_record_start_really_pins_the_session(vice_text, tmp_path):
    """The same contract at the CLI layer, for the same reason."""
    s, mon = _fake_session()
    wav = tmp_path / "cli.wav"
    with patch("c64lib.cli.Session") as S, _port(vice_text):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "record", "--start", str(wav)])
    assert r.exit_code == 0, r.output
    assert vice_text.warp is False, "the CLI armed a recorder under warp"
    assert _names(mon) == ["MonitorServerAddress", "MonitorServer", "Speed",
                           "SoundRecordDeviceArg", "SoundRecordDeviceName"]
    assert call("Speed", 100) in mon.resource_set.call_args_list


def test_cli_audio_record_stop_really_unpins_the_session(vice_text, tmp_path):
    """And the other end of it: `--stop` has to put the session back, not
    merely disarm the recorder and report a file size."""
    s, mon = _fake_session()
    wav = tmp_path / "cli.wav"
    with patch("c64lib.cli.Session") as S, _port(vice_text):
        S.attach.return_value = s
        assert CliRunner().invoke(
            main, ["audio", "record", "--start", str(wav)]).exit_code == 0
        wav.write_bytes(b"RIFF" + bytes(60))
        mon.resource_set.reset_mock()
        r = CliRunner().invoke(main, ["audio", "record", "--stop"])
    assert r.exit_code == 0, r.output
    assert vice_text.warp is True, "the CLI left the session unwarped"
    assert _names(mon) == ["SoundRecordDeviceName", "Speed", "MonitorServer"]


def test_mcp_audio_record_start_needs_a_path():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_audio_record", {"action": "start"})
    assert err is True and "path" in str(out)


def test_mcp_audio_record_rejects_an_unknown_action():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_audio_record", {"action": "pause"})
    assert err is True and "pause" in str(out)


# --- CLI --------------------------------------------------------------------

def test_cli_audio_record_start(tmp_path):
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.pinned_record_start",
               return_value={"wav": "/tmp/a.wav",
                             "pinned": {"warp": True, "speed": 100}}) as start:
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["--json", "audio", "record",
                                      "--start", "/tmp/a.wav"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["wav"] == "/tmp/a.wav"
    start.assert_called_once_with(s, "/tmp/a.wav")


def test_cli_audio_record_stop_reports_the_file():
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.pinned_record_stop",
               return_value={"wav": "/tmp/a.wav", "bytes": 147456 * 4,
                             "restored": {"warp": True, "speed": 100}}):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "record", "--stop"])
    assert r.exit_code == 0, r.output
    assert "/tmp/a.wav" in r.output


def test_cli_audio_record_needs_exactly_one_of_start_and_stop():
    for args in (["audio", "record"], ["audio", "record", "--start", "a.wav",
                                       "--stop"]):
        r = CliRunner().invoke(main, args)
        assert r.exit_code == 1, r.output
        assert "--start" in r.output


def test_cli_audio_record_reports_a_capture_failure():
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.pinned_record_start",
               side_effect=AudioError("warp would not clear")):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "record", "--start", "a.wav"])
    assert r.exit_code == 1
    assert "warp would not clear" in r.output


@pytest.mark.parametrize("argv,target", [
    (["audio", "record", "--start", "a.wav"], "pinned_record_start"),
    (["audio", "record", "--stop"], "pinned_record_stop"),
    (["audio", "sidlog", "10", "s.jsonl"], "sid_log_detail"),
    (["audio", "capture", "1", "out"], "capture"),
])
def test_cli_audio_reports_a_session_error_instead_of_a_traceback(argv, target):
    """SessionError derives from Exception, NOT RuntimeError, so it was one
    name short of every handler here. Every `session.monitor()` inside these
    commands can raise it from a failed daemon respawn."""
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch(f"c64lib.cli.{target}",
               side_effect=SessionError("daemon did not come back")):
        S.attach.return_value = s
        r = CliRunner().invoke(main, argv)
    assert r.exception is None or isinstance(r.exception, SystemExit), \
        f"{argv} let a SessionError escape: {r.exception!r}"
    assert r.exit_code == 1
    assert "daemon did not come back" in r.output


# --- per-frame SID logging ---------------------------------------------------

class FakeMachine:
    """VICE as its binary monitor really behaves, which is not how the plan
    assumed it behaves.

    An asynchronous monitor command is picked up at the next vsync, so the
    machine only ever halts at the top of a frame: `$D012` reads 12 at every
    halt, forever (600 consecutive polls on a live boot screen, LIN 12 /
    CYC 0-2 in every `registers()`), and a `$D012`-wrap loop would spin until
    its deadline without recording a single frame. What the halt does give is
    an exact frame clock: one resume advances exactly one frame (the KERNAL
    jiffy at $A0 ticked +1 per resume).

    So this fake advances one scripted frame per resume, answers a SID block
    read with that frame's registers, and reports 12 for any raster read.
    `calls` records the interleaving, which is the contract under test.
    """

    RASTER_AT_HALT = 12

    def __init__(self, states, delay: float = 0.0):
        self.states = [bytes(s) for s in states]
        self.delay = delay
        self.frame = -1
        self.calls: list = []

    def resume(self) -> None:
        self.calls.append("resume")
        self.frame += 1
        if self.delay:
            time.sleep(self.delay)

    def memory_read(self, start: int, length: int, **kw) -> bytes:
        self.calls.append((start, length))
        if start != audio.SID_BASE:
            return bytes([self.RASTER_AT_HALT]) * length
        assert self.frame >= 0, "sampled a frame the machine was never run to"
        return self.states[self.frame % len(self.states)]


def _machine_session(machine: FakeMachine):
    """A Session whose monitor() hands out `machine` — a direct connection,
    so `sid_log` takes its client-side loop."""
    s = Mock()
    s.name, s.model, s.socket, s.pid = "c64", "c64", None, 4242
    s.monitor.return_value.__enter__ = Mock(return_value=machine)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s


def _states(count: int) -> list[bytes]:
    """`count` distinguishable SID blocks: frame n has n+1 in $D400."""
    return [bytes([n + 1] + [0] * 24) for n in range(count)]


def _rows(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_sid_log_writes_one_frame_record_per_frame(tmp_path):
    """The consumer's contract: one JSONL line per frame, `frame` counting
    from 0, `regs` the whole 25-byte block with `regs[0]` at $D400."""
    out = tmp_path / "sid.jsonl"
    written = sid_log(_machine_session(FakeMachine(_states(5))), 5, str(out))
    assert written == 5
    rows = _rows(out)
    assert [r["frame"] for r in rows] == [0, 1, 2, 3, 4]
    assert [r["regs"][0] for r in rows] == [1, 2, 3, 4, 5]
    assert all(len(r["regs"]) == 25 for r in rows)


def test_sid_log_advances_one_frame_per_sample(tmp_path):
    """One resume, one 25-byte read, per frame — and a resume at the end, so
    the machine is left running rather than halted at the last sample."""
    m = FakeMachine(_states(3))
    sid_log(_machine_session(m), 3, str(tmp_path / "sid.jsonl"))
    assert m.calls == ["resume", (0xD400, 25)] * 3 + ["resume"]


def test_sid_log_does_not_poll_the_raster(tmp_path):
    """The plan's pinned frame detection — poll $D012, a smaller value marks
    a new frame — cannot work here: every binary-monitor halt is at raster
    line 12, so the wrap never happens and the loop would record nothing.
    This fake would happily serve $D012 reads; the loop must not need them."""
    m = FakeMachine(_states(4))
    assert sid_log(_machine_session(m), 4, str(tmp_path / "sid.jsonl")) == 4
    assert not [c for c in m.calls if c != "resume" and c[0] == 0xD012]


def test_sid_log_output_parses_as_frame_records(tmp_path):
    """sid_analysis.parse_log is the only consumer and it raises on anything
    that is not a 25-register frame record — including a stray warning line."""
    from c64lib.sid_analysis import parse_log
    out = tmp_path / "sid.jsonl"
    sid_log(_machine_session(FakeMachine(_states(6))), 6, str(out))
    records = parse_log(out)
    assert [r.frame for r in records] == [0, 1, 2, 3, 4, 5]
    assert records[2].regs[0] == 3 and len(records[2].regs) == 25


def test_sid_log_warns_that_a_warped_session_may_have_dropped_frames(
        tmp_path, capsys):
    """A loop that samples one frame per round trip cannot outrun the frame
    rate, so a rate above 60/s proves the machine is running faster than real
    time — the regime where an emulated frame is no longer than a round trip
    and one can slip past between records (measured live: 200 samples over
    202 elapsed frames warped, 201 at real time). The log cannot show that
    gap, so the warning has to, and it has to say what to do about it."""
    detail = sid_log_detail(_machine_session(FakeMachine(_states(20))), 20,
                            str(tmp_path / "sid.jsonl"))
    assert detail["frames"] == 20
    warning = detail["warning"]
    assert warning and "faster than real time" in warning
    assert "dropped" in warning and "pin_realtime" in warning
    assert warning in capsys.readouterr().err


def test_sid_log_is_quiet_when_the_session_runs_at_real_time(tmp_path, capsys):
    """20 ms per frame is real time; nothing to warn about."""
    detail = sid_log_detail(_machine_session(FakeMachine(_states(3), delay=0.02)),
                            3, str(tmp_path / "sid.jsonl"))
    assert detail["warning"] is None
    assert capsys.readouterr().err == ""


def test_sid_log_reports_the_sampling_rate_it_measured(tmp_path):
    """The warning is a one-sided test — it proves the machine outran real
    time, never that it did not, so a warped session sampled slowly (loaded
    host, busy daemon) drops most of its frames silently. The measured rate
    is returned so a caller can apply the falsifying half itself.

    It is samples per second of wall clock, NOT emulated frames per second:
    the emulator only advances between round trips, so a pinned log measures
    ~22/s from a 60 Hz machine (the canonical 200-frame log: 200 samples over
    9.1 s). Nothing should ever assert it equals the machine's frame rate."""
    m = FakeMachine(_states(4), delay=0.02)
    detail = sid_log_detail(_machine_session(m), 4, str(tmp_path / "sid.jsonl"))
    assert detail["warning"] is None                 # slow: nothing to flag
    assert detail["sample_rate_hz"] == pytest.approx(
        detail["frames"] / detail["seconds"])
    assert 20 < detail["sample_rate_hz"] < 60        # ~50/s at 20 ms a frame


def test_sid_log_times_the_loop_not_the_connection(tmp_path):
    """`seconds` and the rate cover the sampling loop alone. Folding the
    session's open/close into them would drag a short log's rate down
    against the same ceiling a long log is judged by."""
    m = FakeMachine(_states(2), delay=0.01)
    s = _machine_session(m)
    slow_open = s.monitor.return_value.__enter__

    def dawdle():
        time.sleep(0.2)              # a session that takes its time opening
        return slow_open()

    s.monitor.return_value.__enter__ = Mock(side_effect=dawdle)
    detail = sid_log_detail(s, 2, str(tmp_path / "sid.jsonl"))
    assert detail["seconds"] < 0.1   # ~0.02 s of loop, not 0.22 s of session


def test_sid_log_never_reports_a_non_finite_rate(tmp_path):
    """A float infinity is not JSON — `json.dumps` spells it `Infinity` —
    and this dict is both `c64 --json audio sidlog` and an MCP result. The
    warning must not print one either: "sampled inf frames/s" is not a
    sentence."""
    with patch("c64lib.audio.time.monotonic", return_value=1.0):
        detail = sid_log_detail(_machine_session(FakeMachine(_states(2))), 2,
                                str(tmp_path / "sid.jsonl"))
    assert detail["sample_rate_hz"] is None
    json.dumps(detail, allow_nan=False)          # raises on a bare Infinity
    assert "inf" not in detail["warning"]
    assert "inside the clock's resolution" in detail["warning"]


def test_sid_log_keeps_the_frames_it_got_when_it_runs_out_of_time(tmp_path):
    """A short log beats no log, but the shortfall is never silent."""
    out = tmp_path / "sid.jsonl"
    detail = sid_log_detail(_machine_session(FakeMachine(_states(4), delay=0.05)),
                            100, str(out), timeout=0.2)
    assert 0 < detail["frames"] < 100
    assert detail["requested"] == 100
    # "stopped", not "timed out": the daemon also stops a log early when its
    # client goes away, and the advice has to fit that cause too.
    assert f"stopped after {detail['frames']} of 100 frames" in detail["warning"]
    assert "raise the timeout" in detail["warning"]
    assert "interrupted" in detail["warning"]
    assert len(_rows(out)) == detail["frames"]


def test_sid_log_rejects_a_frame_count_below_one(tmp_path):
    with pytest.raises(ValueError, match="at least 1"):
        sid_log(_machine_session(FakeMachine(_states(1))), 0,
                str(tmp_path / "sid.jsonl"))


def test_sid_log_names_the_spent_budget_when_it_samples_nothing(tmp_path):
    """The only way out with an empty log: both loops take at least one
    sample unless the deadline had already passed. A machine that cannot
    advance fails the other way — it fills a whole log with identical
    frames — so the message must not offer that as the explanation."""
    out = tmp_path / "sid.jsonl"
    machine = FakeMachine(_states(2))
    with pytest.raises(AudioError, match="timeout"):
        sid_log_detail(_machine_session(machine), 2, str(out), timeout=0)
    assert not out.exists()
    # The REAL branch, not an injected empty list: the loop body never ran,
    # so the only monitor traffic is the resume that leaves it running.
    assert machine.calls == ["resume"]


def test_sid_log_runs_the_loop_in_the_daemon_when_there_is_one(tmp_path):
    """Per-frame RPCs cost ~0.5 s a frame; the loop belongs on the daemon's
    own VICE connection, exactly like `run_until`."""
    mon = Mock(spec=DaemonMonitorClient)
    mon.sid_log.return_value = [bytes([7] + [0] * 24)] * 3
    out = tmp_path / "sid.jsonl"
    assert sid_log(_machine_session(mon), 3, str(out)) == 3
    assert mon.sid_log.call_count == 1
    # BOTH arguments: the daemon cannot compute the budget for itself, so a
    # regression in `max(SID_LOG_MIN_TIMEOUT, frames * SID_LOG_FRAME_BUDGET)`
    # would only ever show up here. 3 frames is under the floor, so the
    # floor is what travels.
    assert mon.sid_log.call_args.args == (3, audio.SID_LOG_MIN_TIMEOUT)
    mon.memory_read.assert_not_called()
    assert _rows(out)[0]["regs"][0] == 7
    # The daemon loop already left the machine running. A resume on top of it
    # would cost a round trip and let two more unlogged frames pass after the
    # last record — which is the window Task 6 has to bracket.
    mon.resume.assert_not_called()


@pytest.mark.parametrize("frames,expected", [
    (3, 15.0),        # under the floor: SID_LOG_MIN_TIMEOUT wins
    (60, 15.0),       # 60 * 0.25 = 15.0, the crossover
    (200, 50.0),      # 200 * 0.25, the pinned-log size the docstrings quote
    (1800, 450.0),    # a 30 s NTSC capture
])
def test_sid_log_budgets_wall_clock_per_requested_frame(tmp_path, frames, expected):
    """`max(SID_LOG_MIN_TIMEOUT, frames * SID_LOG_FRAME_BUDGET)`, spelled out
    at both sides of the floor. The budget is what the daemon enforces, and
    nothing else measures it."""
    mon = Mock(spec=DaemonMonitorClient)
    mon.sid_log.return_value = [bytes(25)] * frames
    sid_log(_machine_session(mon), frames, str(tmp_path / "sid.jsonl"))
    assert mon.sid_log.call_args.args == (frames, pytest.approx(expected))


def test_sid_log_refuses_a_frame_count_past_the_sanity_ceiling(tmp_path):
    """The whole log lives in memory on the daemon and comes back as one
    base64 line, and the budget scales with it — `frames = 1_000_000` is a
    250,000 s budget and a ~36 MB response. Bounded in code now, not by
    convention."""
    mon = Mock(spec=DaemonMonitorClient)
    with pytest.raises(ValueError, match="at most 36000"):
        sid_log(_machine_session(mon), audio.MAX_SID_LOG_FRAMES + 1,
                str(tmp_path / "sid.jsonl"))
    mon.sid_log.assert_not_called()


def test_sid_log_falls_back_to_the_client_loop_on_an_older_daemon(tmp_path):
    """An unknown method is a ValueError from the daemon — the same
    daemon-first-else-local shape `ops.run_until` uses."""
    mon = Mock(spec=DaemonMonitorClient)
    mon.sid_log.side_effect = ValueError("unknown daemon method 'sid_log'")
    mon.memory_read.return_value = bytes([9] + [0] * 24)
    out = tmp_path / "sid.jsonl"
    assert sid_log(_machine_session(mon), 2, str(out)) == 2
    assert mon.memory_read.call_args_list == [call(0xD400, 25)] * 2
    assert _rows(out)[1]["regs"][0] == 9


# --- MCP tool / CLI for the sid log ------------------------------------------

def test_mcp_sid_log(tmp_path):
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.sid_log_detail",
               return_value={"path": "/tmp/s.jsonl", "frames": 50,
                             "requested": 50, "seconds": 1.0,
                             "sample_rate_hz": 50.0, "warning": None}) as log:
        S.attach.return_value = s
        err, out = call_tool("c64_sid_log", {"frames": 50,
                                             "path": "/tmp/s.jsonl"})
    assert err is False and out["frames"] == 50
    log.assert_called_once_with(s, 50, "/tmp/s.jsonl")


#: What a real `sid_log_detail` hands back, and prints to stderr, when the
#: sampling loop stopped short. The paragraph is long, which is the point:
#: printed twice it fills a screen.
SIDLOG_WARNING = ("sid log stopped after 40 of 50 frames; raise the timeout, "
                  "check that the machine is running, or — if the command was "
                  "interrupted — run it again")


def _warning_detail(session, frames, path):
    """`sid_log_detail`'s two halves: the stderr line the library owns (see
    its `print`, and the test above that pins it) and the returned dict."""
    print(f"c64: {SIDLOG_WARNING}", file=sys.stderr)
    return {"path": "/tmp/s.jsonl", "frames": 40, "requested": 50,
            "seconds": 0.1, "sample_rate_hz": 400.0, "warning": SIDLOG_WARNING}


def test_cli_audio_sidlog_reports_the_count_and_points_at_the_warning():
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.sid_log_detail", side_effect=_warning_detail):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "sidlog", "50", "/tmp/s.jsonl"])
    assert r.exit_code == 0, r.output
    assert "40" in r.output and "/tmp/s.jsonl" in r.output
    assert "warning:" in r.output and "stderr" in r.output


def test_cli_audio_sidlog_says_the_warning_once_not_twice():
    """`sid_log_detail` prints the whole paragraph to stderr — the documented
    rule for this feature — so the human line repeating it puts the same text
    on the screen twice. `audio capture` settled the identical duplication by
    making its second surface a pointer; this is that, for sidlog."""
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.sid_log_detail", side_effect=_warning_detail):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "sidlog", "50", "/tmp/s.jsonl"])
    assert r.output.count("raise the timeout") == 1


def test_cli_audio_sidlog_json_still_carries_the_whole_warning():
    """The pointer is a human-output rule only: `--json` is what a script
    reads, and it must not be told to go look at a stream it is not capturing."""
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.sid_log_detail", side_effect=_warning_detail):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["--json", "audio", "sidlog", "50",
                                      "/tmp/s.jsonl"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["warning"] == SIDLOG_WARNING


def test_cli_audio_sidlog_reports_a_capture_failure():
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.sid_log_detail",
               side_effect=AudioError("the machine is stopped")):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "sidlog", "10", "/tmp/s.jsonl"])
    assert r.exit_code == 1
    assert "the machine is stopped" in r.output


def test_module_exposes_only_the_capture_surface():
    """The text-monitor channel is a capture-time detail of this module, not
    a new public surface — it must not appear on MonitorClient."""
    from c64lib.monitor import MonitorClient
    assert not hasattr(MonitorClient, "warp")
    assert audio._TextMonitor.__name__.startswith("_")


# --- the report wrapper and the capture orchestrator -------------------------

#: $D400/$D401 for A4 on the NTSC machine: 440 Hz * 2**24 / 1022727 = 7217.93,
#: which rounds to 7218 -> 7218 * 1022727 / 2**24 = 440.0041 Hz, sharp by
#: 0.016 cents. Read with the PAL clock the SAME registers are
#: 7218 * 985248 / 2**24 = 423.88 Hz — G#4 (415.30) sharp by 35.4 cents, not
#: A4 — which is what makes one pair of registers a test of which clock the
#: transcription used.
A4_NTSC_REG = 7218
#: Triangle (bit 4) with the gate on (bit 0).
TRIANGLE_GATED = 0x11


def _voice1(reg16: int = A4_NTSC_REG, control: int = TRIANGLE_GATED) -> bytes:
    """A SID block sounding one note on voice 1 and nothing on voices 2-3."""
    regs = [0] * 25
    regs[0], regs[1], regs[4] = reg16 & 0xFF, reg16 >> 8, control
    regs[24] = 0x0F                      # $D418: full volume
    return bytes(regs)


def _write_wav(path, seconds: float, rate: int = 22050, hz: float = 440.0,
               amplitude: int = 16000, silent_after: float | None = None) -> None:
    """A real mono 16-bit WAV of a sine — what `wav_metrics` and the
    spectrogram read. Not silence by default: a silent capture is a FAIL
    verdict, which would hide the artifact this is standing in for.

    `amplitude=0` writes digital silence, and `silent_after` cuts the sine
    dead at that many seconds and pads the rest with zeros — a note whose
    envelope decayed while the gate stayed held.
    """
    import math
    import struct
    import wave
    count = round(seconds * rate)
    loud = count if silent_after is None else round(silent_after * rate)
    pcm = b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * hz * i / rate))
                          if i < loud else 0)
        for i in range(count))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)


class FakeVice(FakeMachine):
    """FakeMachine plus VICE's resource surface and its WAV recorder.

    One object with ONE ordered call trace, because a capture's contract is
    the order: pin (warp off, Speed 100) before the recorder is armed, every
    sample inside the armed window, the recorder disarmed before the speed
    goes back. Two separate mocks could each be right and still compose
    wrongly.

    The recorder writes a real WAV covering the frames that elapsed while it
    was armed — the emulated duration, which is what VICE's own recorder
    produces and what the live alignment check confirmed. It is a stand-in
    for VICE, not evidence about it.
    """

    def __init__(self, states, fps: float = 60.0, delay: float = 0.0,
                 records: bool | str = True, **resources):
        super().__init__(states, delay)
        self.resources = {**VICE_DEFAULTS, **resources}
        self.fps = fps
        self.records = records
        self.wav_path: str | None = None
        self.armed_at: int | None = None

    def resource_get(self, name: str):
        self.calls.append(("get", name))
        return self.resources[name]

    def resource_set(self, name: str, value) -> None:
        self.calls.append(("set", name, value))
        self.resources[name] = value
        if name == audio.REC_ARG:
            self.wav_path = value
        elif name == audio.REC_NAME:
            if value == "wav":
                self.armed_at = self.frame
            elif self.armed_at is not None:
                if self.records and self.wav_path:
                    # records="header" is the warped VICE: a finalized WAV
                    # holding a header and no frames at all.
                    seconds = (0.0 if self.records == "header"
                               else (self.frame - self.armed_at) / self.fps)
                    _write_wav(self.wav_path, seconds)
                self.armed_at = None

    @property
    def sets(self) -> list[str]:
        """The resource names set, in order — the sequence IS the contract."""
        return [c[1] for c in self.calls if c[0] == "set"]

    def index_of(self, name: str, value) -> int:
        return self.calls.index(("set", name, value))


def _capture_session(vice: FakeVice, model: str = "c64", pid: int = 4242):
    """A Session whose monitor() hands out `vice` for both its resource and
    its memory traffic, with a real machine profile behind `.profile`."""
    from c64lib.machines import get_profile
    s = Mock()
    s.name, s.model, s.socket, s.pid = "c64", model, None, pid
    s.profile = get_profile(model)
    s.monitor.return_value.__enter__ = Mock(return_value=vice)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s


def _log(path, states, first_frame: int = 0) -> None:
    """A sid-log.jsonl as `sid_log` writes one."""
    Path(path).write_text("".join(
        json.dumps({"frame": first_frame + n, "regs": list(regs)}) + "\n"
        for n, regs in enumerate(states)))


PAL = 985248
NTSC = 1022727


# --- sid_report ---------------------------------------------------------------

def test_sid_report_writes_every_artifact_it_can_and_a_verdict(tmp_path):
    """The wrapper's whole job: parse, transcribe, render, and hand back the
    paths plus the verdict the report reached."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 30)
    _write_wav(tmp_path / "capture.wav", 0.5)
    out = audio.sid_report(log, tmp_path, wav_path=tmp_path / "capture.wav",
                           timing=audio.report_timing_for("c64"))
    assert out["verdict"] == "PASS" and out["failures"] == []
    assert Path(out["report"]).name == "report.md"
    assert Path(out["piano_roll"]).exists() and Path(out["spectrogram"]).exists()
    assert out["machine"] == "c64" and out["clock_hz"] == NTSC and out["fps"] == 60
    assert "A4" in Path(out["report"]).read_text()


def test_sid_report_transcribes_with_the_clock_it_was_given(tmp_path):
    """One pair of registers, two machines: 65 cents apart is a different
    note name, so a report built on the wrong clock is visibly wrong."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 30)
    ntsc = audio.sid_report(log, tmp_path / "ntsc",
                            timing=audio.report_timing_for("c64"))
    pal = audio.sid_report(log, tmp_path / "pal",
                           timing=audio.report_timing_for("c64pal"))
    assert "A4" in Path(ntsc["report"]).read_text()
    assert "G#4" in Path(pal["report"]).read_text()
    assert pal["clock_hz"] == PAL and pal["fps"] == 50


def test_sid_report_without_a_wav_is_a_render_only_pass(tmp_path):
    """No audio is a legitimate mode, not a failure: no spectrogram, no
    metrics, and the verdict still stands on the register log alone."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 20)
    out = audio.sid_report(log, tmp_path, timing=audio.report_timing_for("c64"))
    assert out["verdict"] == "PASS"
    assert out["spectrogram"] is None and out["metrics"] is None
    assert not (tmp_path / "spectrogram.png").exists()
    assert "register log only" in Path(out["report"]).read_text()


def test_sid_report_never_calls_the_diff_without_a_reference_score(tmp_path):
    """`diff_score(events, None)` raises a bare AttributeError — there is no
    "empty reference" to pass, so the diff has to be skipped outright."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 20)
    with patch("c64lib.sid_analysis.diff_score",
               side_effect=AssertionError("diffed without a reference")) as diff:
        out = audio.sid_report(log, tmp_path, timing=audio.report_timing_for("c64"))
    diff.assert_not_called()
    assert out["diffs"] == [] and out["verdict"] == "PASS"


def test_sid_report_fails_on_a_reference_score_that_does_not_match(tmp_path):
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 30)
    ref = tmp_path / "score.yaml"
    ref.write_text("voices:\n  1:\n    - {note: C4, frames: 30}\n")
    out = audio.sid_report(log, tmp_path, ref_path=ref,
                           timing=audio.report_timing_for("c64"))
    assert out["verdict"] == "FAIL"
    assert out["diffs"] and "C4" in out["diffs"][0]
    assert any("reference score" in reason for reason in out["failures"])


def test_sid_report_reports_anomalies_from_the_register_log(tmp_path):
    """A gate held over a zero frequency for 51 frames is the stuck-gate
    anomaly — reference-free, so it is the check a run with no score keeps."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1(reg16=0)] * 60)
    out = audio.sid_report(log, tmp_path, timing=audio.report_timing_for("c64"))
    assert out["verdict"] == "FAIL"
    assert any("stuck gate" in a for a in out["anomalies"])


def test_sid_report_flags_a_note_the_recording_says_never_sounded(tmp_path):
    """The WAV-aware anomaly, end to end — and the reason the order inside
    `sid_report` matters: the check reads the WAV's silence windows, so the
    recording has to be measured BEFORE the anomalies are looked for. With
    the metrics computed afterwards the check never saw a recording at all.

    5 s of NTSC log (300 frames at 60 fps) holding one gated note over a WAV
    that sounds for 2 s and is silent for the remaining 3."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 300)
    wav = tmp_path / "capture.wav"
    _write_wav(wav, 5.0, silent_after=2.0)
    out = audio.sid_report(log, tmp_path, wav_path=wav,
                           timing=audio.report_timing_for("c64"))
    assert out["verdict"] == "FAIL"
    assert len(out["anomalies"]) == 1
    assert "gated for 300 frames" in out["anomalies"][0]
    assert "never sounded" in out["anomalies"][0]


def test_sid_report_keeps_passing_a_note_that_sounds_all_the_way_through(tmp_path):
    """The same log over a WAV that never goes quiet. Without this the test
    above would pass just as well against a check that fires on every note."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 300)
    wav = tmp_path / "capture.wav"
    _write_wav(wav, 5.0)
    out = audio.sid_report(log, tmp_path, wav_path=wav,
                           timing=audio.report_timing_for("c64"))
    assert out["verdict"] == "PASS" and out["anomalies"] == []


def test_sid_report_says_when_nothing_played_at_all(tmp_path):
    """The attract-screen capture: no voice gated, a silent recording, and a
    PASS that checked nothing. Still a PASS — but the payload carries the
    fact, and the report's notice is a block quote, so a verdict with no
    reasons still reads back as a verdict with no reasons."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [bytes(25)] * 60)
    wav = tmp_path / "capture.wav"
    _write_wav(wav, 1.0, amplitude=0)
    out = audio.sid_report(log, tmp_path, wav_path=wav,
                           timing=audio.report_timing_for("c64"))
    assert out["verdict"] == "PASS" and out["failures"] == []
    assert out["nothing_played"] is True
    assert out["notes"] == 0
    assert "**Nothing played.**" in Path(out["report"]).read_text()


def test_sid_report_does_not_say_nothing_played_when_a_note_sounded(tmp_path):
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 30)
    wav = tmp_path / "capture.wav"
    _write_wav(wav, 0.5)
    out = audio.sid_report(log, tmp_path, wav_path=wav,
                           timing=audio.report_timing_for("c64"))
    assert out["nothing_played"] is False
    assert "Nothing played" not in Path(out["report"]).read_text()


# --- capture ------------------------------------------------------------------

def test_capture_pins_arms_samples_disarms_then_restores(vice_text, tmp_path):
    """The order is the contract. Warp off and Speed 100 BEFORE the recorder
    is armed (while warped VICE writes a 0-frame WAV), every sample strictly
    inside the armed window, and the recorder disarmed before the speed goes
    back."""
    vice = FakeVice([_voice1()] * 8)
    with _port(vice_text):
        audio.capture(_capture_session(vice), 0.1, tmp_path)
    assert vice.sets == ["MonitorServerAddress", "MonitorServer", "Speed",
                         "SoundRecordDeviceArg", "SoundRecordDeviceName",
                         "SoundRecordDeviceName", "Speed", "MonitorServer"]
    armed = vice.index_of("SoundRecordDeviceName", "wav")
    disarmed = vice.index_of("SoundRecordDeviceName", "")
    samples = [i for i, c in enumerate(vice.calls) if c == (audio.SID_BASE, 25)]
    assert samples and armed < min(samples) and max(samples) < disarmed
    assert vice_text.warp is True                     # and warp is put back


def test_capture_writes_the_five_pinned_artifacts(vice_text, tmp_path):
    """The names are pinned: the report links them, demo evidence scripts
    reference them, and an agent is told to look for them."""
    vice = FakeVice([_voice1()] * 12)
    with _port(vice_text):
        out = audio.capture(_capture_session(vice), 0.2, tmp_path / "cap")
    assert sorted(p.name for p in (tmp_path / "cap").iterdir()) == [
        "capture.wav", "piano-roll.png", "report.md", "sid-log.jsonl",
        "spectrogram.png"]
    assert out["verdict"] == "PASS"
    assert Path(out["wav"]).name == "capture.wav"
    assert Path(out["log"]).name == "sid-log.jsonl"
    assert out["unpin_error"] is None      # the session was put back


def test_capture_takes_its_frame_count_from_the_machines_frame_rate(
        vice_text, tmp_path):
    """`round(seconds * fps)` — and fps comes from the machine profile, so
    the same half second is 30 frames on the NTSC machine and 25 on PAL."""
    for model, expected in (("c64", 30), ("c64pal", 25)):
        vice = FakeVice([_voice1()] * 4, fps=60.0 if model == "c64" else 50.0)
        out_dir = tmp_path / model
        with _port(vice_text):
            out = audio.capture(_capture_session(vice, model=model), 0.5, out_dir)
        assert out["requested_frames"] == expected
        assert len(_rows(out_dir / "sid-log.jsonl")) == expected
        assert out["machine"] == model
        assert out["emulated_s"] == pytest.approx(expected / out["fps"])


def test_capture_transcribes_with_the_machines_clock(vice_text, tmp_path):
    """The registers are the same; only the clock differs. A table built for
    the wrong machine is uniformly off by about 65 cents — one note name."""
    reports = {}
    for model in ("c64", "c64pal"):
        vice = FakeVice([_voice1()] * 4, fps=60.0 if model == "c64" else 50.0)
        with _port(vice_text):
            out = audio.capture(_capture_session(vice, model=model), 0.2,
                                tmp_path / model)
        reports[model] = Path(out["report"]).read_text()
    assert "A4" in reports["c64"] and "G#4" not in reports["c64"]
    assert "G#4" in reports["c64pal"]


def test_capture_restores_the_session_when_the_log_fails(vice_text, tmp_path):
    """A capture that dies half way must not leave the session pinned at 1x
    with the recorder still armed.

    The session is found at Speed 200 on purpose: at the default 100 the
    restore is indistinguishable from the pin, and the assertion would hold
    even if nothing were put back.
    """
    vice = FakeVice([_voice1()] * 4, Speed=200)
    with _port(vice_text), \
         patch("c64lib.audio.sid_log_detail",
               side_effect=AudioError("the machine is stopped")), \
         pytest.raises(AudioError, match="the machine is stopped"):
        audio.capture(_capture_session(vice), 0.2, tmp_path)
    assert vice.sets[-3:] == ["SoundRecordDeviceName", "Speed", "MonitorServer"]
    assert vice.resources["SoundRecordDeviceName"] == ""      # disarmed
    assert vice.resources["Speed"] == 200                     # as it was found
    assert vice_text.warp is True                             # and re-warped


def test_capture_reports_an_unpin_failure_and_keeps_the_sampling_failure(
        vice_text, tmp_path, capsys):
    """When the monitor stops answering — the wedge — both the log and the
    unpin fail. The sampling failure is the root cause and the one that
    propagates; the unpin failure is not swallowed with it, because a session
    left at 1x is what the next command trips over.

    The whole of `pinned_record_stop` is stubbed out here, so the pin sidecar
    it would have cleared is still on disk — which is how `capture` reads this
    as a restore that failed rather than a disarm that did."""
    vice = FakeVice([_voice1()] * 4)
    with _port(vice_text), \
         patch("c64lib.audio.sid_log_detail",
               side_effect=AudioError("the machine is stopped")), \
         patch("c64lib.audio.pinned_record_stop",
               side_effect=TimeoutError("timed out")), \
         pytest.raises(AudioError, match="the machine is stopped"):
        audio.capture(_capture_session(vice), 0.2, tmp_path)
    err = capsys.readouterr().err
    assert "could not be unpinned" in err and "timed out" in err


def test_capture_survives_an_unpin_that_fails_and_says_so(vice_text, tmp_path,
                                                          capsys):
    """A failed unpin is reported, not fatal. By the time the restore runs the
    WAV and the register log are complete — every unpin stall measured in the
    wedge investigation fired after the recording had landed — so failing here
    would throw away good evidence over a session that is merely still at real
    time. The pin sidecar is left behind on purpose: `c64 audio record --stop`
    can retry the unpin, which it cannot do without it."""
    vice = FakeVice([_voice1()] * 12)
    s = _capture_session(vice)
    with _port(vice_text), \
         patch("c64lib.audio.restore_speed",
               side_effect=TimeoutError("timed out")):
        out = audio.capture(s, 0.2, tmp_path / "cap")
    assert sorted(p.name for p in (tmp_path / "cap").iterdir()) == [
        "capture.wav", "piano-roll.png", "report.md", "sid-log.jsonl",
        "spectrogram.png"]
    assert out["verdict"] == "PASS"
    assert out["wav_bytes"] > audio.WAV_HEADER_BYTES
    assert "could not be unpinned" in out["unpin_error"]
    assert "timed out" in out["unpin_error"]
    assert "record --stop" in out["unpin_error"]      # and how to retry it
    assert out["unpin_error"] in capsys.readouterr().err
    assert audio._pin_path(s).exists()                # left for that retry


def test_capture_still_fails_when_the_recorder_will_not_disarm(vice_text,
                                                               tmp_path):
    """The other half of `pinned_record_stop`, and NOT the same failure.
    Disarming is what finalizes the WAV, so a recorder VICE would not stop
    leaves a file it may still be writing — there is nothing complete to judge
    and no unpin left to retry (the restore succeeded, so the sidecar is gone,
    which is exactly how `capture` tells the two apart). It raises, as it did
    before a failed restore was made survivable."""
    vice = FakeVice([_voice1()] * 12)
    s = _capture_session(vice)
    with _port(vice_text), \
         patch("c64lib.audio.record_stop",
               side_effect=TimeoutError("timed out")), \
         pytest.raises(TimeoutError, match="timed out"):
        audio.capture(s, 0.2, tmp_path / "cap")
    assert not (tmp_path / "cap" / "report.md").exists()   # no verdict claimed
    assert (tmp_path / "cap" / "sid-log.jsonl").exists()   # the log is kept
    assert not audio._pin_path(s).exists()                 # the restore ran
    assert vice_text.warp is True                          # and put warp back


def test_read_verdict_refuses_a_report_with_no_verdict_line(tmp_path):
    """The verdict is read back out of the report because `write_report` owns
    the rule. If that line ever moves, this has to say so rather than hand
    back a report nobody judged."""
    report = tmp_path / "report.md"
    report.write_text("# SID audio verification\n\nno verdict here\n")
    with pytest.raises(AudioError, match="no verdict line"):
        audio._read_verdict(report)


def test_capture_leaves_no_pin_behind(vice_text, tmp_path):
    """The sidecar exists so a crashed capture can still be unpinned; a
    capture that finished must not leave one for the next command to honour."""
    vice = FakeVice([_voice1()] * 4)
    s = _capture_session(vice)
    with _port(vice_text):
        audio.capture(s, 0.2, tmp_path)
    assert not audio._pin_path(s).exists()


def test_capture_refuses_a_window_shorter_than_one_frame(vice_text, tmp_path):
    vice = FakeVice([_voice1()])
    with _port(vice_text), pytest.raises(ValueError, match="at least one frame"):
        audio.capture(_capture_session(vice), 0.001, tmp_path)
    assert vice.sets == []          # and it never touched the machine


@pytest.mark.parametrize("recorder, expected", [
    ("header", "44 bytes"),        # what a warped VICE actually leaves behind
    (False, "missing"),            # the recorder never wrote at all
])
def test_capture_diagnoses_a_wav_with_no_samples(vice_text, tmp_path,
                                                 recorder, expected):
    """The failure this whole module is built around: under warp VICE writes
    a 0-frame WAV — a header and nothing else — so an empty file is a capture
    failure to diagnose, never an empty tune. The register log is kept."""
    vice = FakeVice([_voice1()] * 4, records=recorder)
    with _port(vice_text), pytest.raises(AudioError) as raised:
        audio.capture(_capture_session(vice), 0.2, tmp_path)
    assert "warp" in str(raised.value) and "capture.wav" in str(raised.value)
    assert expected in str(raised.value)
    assert (tmp_path / "sid-log.jsonl").exists()      # the log survives
    assert vice_text.warp is True                     # and the session is back


def test_capture_passes_the_reference_score_through(vice_text, tmp_path):
    vice = FakeVice([_voice1()] * 4)
    ref = tmp_path / "score.yaml"
    ref.write_text("voices:\n  1:\n    - {note: C4}\n")
    with _port(vice_text):
        out = audio.capture(_capture_session(vice), 0.2, tmp_path / "cap",
                            ref_path=ref)
    assert out["verdict"] == "FAIL" and out["diffs"]


def test_capture_rejects_a_bad_reference_before_it_opens_the_window(
        vice_text, tmp_path):
    """The score used to be read only inside `sid_report`, i.e. after the
    whole real-time window — so a typo cost a minute of wall clock before it
    was named. Nothing may be pinned or armed for a score that cannot parse."""
    vice = FakeVice([_voice1()] * 4)
    ref = tmp_path / "score.yaml"
    ref.write_text("voices:\n  4: [{note: C4}]\n")
    with _port(vice_text), pytest.raises(ValueError, match="voice 4"):
        audio.capture(_capture_session(vice), 0.2, tmp_path / "cap", ref_path=ref)
    assert vice.sets == []
    assert not (tmp_path / "cap" / "capture.wav").exists()


def test_capture_names_unreadable_reference_yaml_before_the_window(
        vice_text, tmp_path):
    """The other half of the same pre-parse, and the one `sid_report` already
    translates out of a bare `yaml.YAMLError`."""
    vice = FakeVice([_voice1()] * 4)
    ref = tmp_path / "score.yaml"
    ref.write_text("voices: {1: [\n")
    with _port(vice_text), pytest.raises(AudioError, match="not readable YAML"):
        audio.capture(_capture_session(vice), 0.2, tmp_path / "cap", ref_path=ref)
    assert vice.sets == []


def test_capture_reports_the_wall_clock_it_cost(vice_text, tmp_path):
    """Emulated time and wall clock diverge sharply while sampling — the
    machine only advances between round trips — so a caller who wants to
    know what a capture cost cannot divide frames by fps."""
    vice = FakeVice([_voice1()] * 4)
    with _port(vice_text):
        out = audio.capture(_capture_session(vice), 0.2, tmp_path)
    assert out["frames"] == 12 and out["emulated_s"] == pytest.approx(0.2)
    assert out["wall_clock_s"] > 0


# --- MCP tools ----------------------------------------------------------------

def test_mcp_sid_report_defaults_to_pal_with_no_session(tmp_path):
    """No session names a machine, so the report assumes PAL — and says so,
    because a wrong clock is a uniformly detuned transcription, not an error."""
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.sid_report",
               return_value={"verdict": "PASS"}) as report:
        err, out = call_tool("c64_sid_report", {"log": "/tmp/s.jsonl",
                                                "outdir": "/tmp/out"})
    assert err is False and out["verdict"] == "PASS"
    S.attach.assert_not_called()
    assert report.call_args.kwargs["timing"]["clock_hz"] == PAL


def test_mcp_sid_report_uses_the_named_sessions_clock(tmp_path):
    from c64lib.machines import get_profile
    s, _ = _fake_session()
    s.profile = get_profile("c64")
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.sid_report",
               return_value={"verdict": "PASS"}) as report:
        S.attach.return_value = s
        call_tool("c64_sid_report", {"log": "/tmp/s.jsonl", "outdir": "/tmp/o",
                                     "session": "c64"})
    assert report.call_args.kwargs["timing"]["clock_hz"] == NTSC


def test_mcp_sid_report_peak_hz_needs_wav():
    """A dominant partial is a property of the recording, so peak_hz without a
    wav is refused — and refused BEFORE the analysis runs, the way the CLI
    checks its flag before calling sid_report, so a bad call costs nothing."""
    with patch("c64lib.mcp_server.Session"), \
         patch("c64lib.mcp_server.sid_report",
               return_value={"verdict": "PASS"}) as report:
        err, out = call_tool("c64_sid_report", {"log": "/tmp/s.jsonl",
                                                "outdir": "/tmp/out",
                                                "peak_hz": True})
    assert err is True
    assert "peak_hz needs wav" in str(out)
    report.assert_not_called()


def test_mcp_sid_report_peak_hz_threads_through():
    """With a wav, peak_hz adds the CLI's --peak-hz measurement to the same
    payload — one `peak` object beside the verdict."""
    peak = {"peak_hz": 440.0, "bin_hz": 1.0, "bin": 440,
            "resolution_cents": 1.97, "seconds": 1.0}
    with patch("c64lib.mcp_server.Session"), \
         patch("c64lib.mcp_server.sid_report",
               return_value={"verdict": "PASS"}), \
         patch("c64lib.sid_analysis.dominant_partial_hz",
               return_value=peak) as dominant:
        err, out = call_tool("c64_sid_report", {"log": "/tmp/s.jsonl",
                                                "outdir": "/tmp/out",
                                                "wav": "/tmp/cap.wav",
                                                "peak_hz": True})
    assert err is False and out["peak"] == peak
    dominant.assert_called_once_with("/tmp/cap.wav")


def test_mcp_audio_capture():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.capture",
               return_value={"verdict": "PASS", "report": "/tmp/o/report.md"}) as cap:
        S.attach.return_value = s
        err, out = call_tool("c64_audio_capture", {"seconds": 2.0,
                                                   "outdir": "/tmp/o"})
    assert err is False and out["verdict"] == "PASS"
    cap.assert_called_once_with(s, 2.0, "/tmp/o", ref_path=None)


# --- CLI ----------------------------------------------------------------------

def test_cli_audio_report_assumes_pal_when_no_session_is_named(tmp_path):
    """A register log does not carry its clock and no session names one, so
    the report falls back to PAL — and says which machine it read it as."""
    log = tmp_path / "sid-log.jsonl"
    _log(log, [_voice1()] * 4)
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.sid_report",
               return_value={"verdict": "PASS", "report": "/tmp/o/report.md",
                             "diffs": [], "anomalies": [], "notes": 1,
                             "machine": "c64pal", "clock_hz": PAL,
                             "fps": 50}) as report:
        r = CliRunner().invoke(main, ["audio", "report", str(log), "/tmp/o"])
    assert r.exit_code == 0, r.output
    S.attach.assert_not_called()
    assert report.call_args.kwargs["timing"]["clock_hz"] == PAL
    assert "PASS" in r.output and "c64pal" in r.output


def test_cli_audio_report_measures_the_peak_with_peak_hz(tmp_path):
    """The alignment gate's instrument, reachable from the command line.

    A 440 Hz tone over 1 s of 44100 gives 1 Hz bins, so the answer is bin
    440 exactly — which is the check an agent runs against what the registers
    predict for the same capture.
    """
    log = tmp_path / "sid.jsonl"
    log.write_text(json.dumps({"frame": 0, "regs": [0] * 25}) + "\n")
    wav = tmp_path / "capture.wav"
    tone = np.sin(2 * np.pi * 440.0 * np.arange(44100) / 44100) * 0.5
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(44100)
        out.writeframes(np.round(tone * 32767).astype("<i2").tobytes())
    r = CliRunner().invoke(main, ["--json", "audio", "report", str(log),
                                  str(tmp_path / "out"), "--wav", str(wav),
                                  "--peak-hz"])
    assert r.exit_code == 0, r.output
    peak = json.loads(r.output)["peak"]
    assert peak["bin"] == 440
    assert peak["peak_hz"] == pytest.approx(440.0)
    assert peak["bin_hz"] == pytest.approx(1.0)
    assert peak["resolution_cents"] == pytest.approx(1.967, abs=0.01)


def test_cli_audio_report_peak_hz_needs_a_wav(tmp_path):
    log = tmp_path / "sid.jsonl"
    log.write_text(json.dumps({"frame": 0, "regs": [0] * 25}) + "\n")
    r = CliRunner().invoke(main, ["audio", "report", str(log),
                                  str(tmp_path / "out"), "--peak-hz"])
    assert r.exit_code == 1
    assert "--wav" in r.output


def test_cli_audio_capture_reports_the_verdict():
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.capture",
               return_value={"verdict": "FAIL", "report": "/tmp/o/report.md",
                             "diffs": ["voice 1 event 1: expected C4"],
                             "anomalies": [], "frames": 120,
                             "emulated_s": 2.0, "wall_clock_s": 5.5}) as cap:
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "capture", "2", "/tmp/o"])
    assert r.exit_code == 1, r.output          # a FAIL verdict is a failure
    assert "/tmp/o/report.md" in r.output and "expected C4" in r.output
    cap.assert_called_once_with(s, 2.0, "/tmp/o", ref_path=None)


def test_cli_audio_capture_warns_when_nothing_played():
    """A PASS over an empty capture is the one verdict that means nothing:
    no note sounded, so no check had anything to disagree with. Exit 0 — it
    is not a failure — with the warning on the same screen as the PASS."""
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.capture",
               return_value={"verdict": "PASS", "report": "/tmp/o/report.md",
                             "diffs": [], "anomalies": [], "frames": 60,
                             "nothing_played": True,
                             "emulated_s": 1.0, "wall_clock_s": 2.8}):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "capture", "1", "/tmp/o"])
    assert r.exit_code == 0, r.output
    assert "warning: nothing played" in r.output


def test_cli_audio_capture_is_quiet_about_a_capture_that_played():
    """Same payload with the flag false — so the warning above is the flag
    and not a line printed under every verdict."""
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.capture",
               return_value={"verdict": "PASS", "report": "/tmp/o/report.md",
                             "diffs": [], "anomalies": [], "frames": 60,
                             "nothing_played": False,
                             "emulated_s": 1.0, "wall_clock_s": 2.8}):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "capture", "1", "/tmp/o"])
    assert r.exit_code == 0, r.output
    assert "nothing played" not in r.output


def test_cli_audio_capture_passes_the_reference_score():
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.capture",
               return_value={"verdict": "PASS", "report": "/tmp/o/report.md",
                             "diffs": [], "anomalies": [], "frames": 60,
                             "emulated_s": 1.0, "wall_clock_s": 2.8}) as cap:
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "capture", "1", "/tmp/o",
                                      "--ref", "score.yaml"])
    assert r.exit_code == 0, r.output
    cap.assert_called_once_with(s, 1.0, "/tmp/o", ref_path="score.yaml")


def test_cli_audio_capture_shows_an_unpin_failure_under_the_verdict():
    """A PASS verdict is about the audio; a session left pinned is about the
    machine that produced it, and it outlives the command. The capture still
    succeeds — exit 0, report written — and the verdict carries a flag for it.

    A pointer, not a copy: `capture` has already printed the whole sentence to
    stderr, and repeating it here would say it twice in the one situation
    where the operator is already reading carefully."""
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.capture",
               return_value={"verdict": "PASS", "report": "/tmp/o/report.md",
                             "diffs": [], "anomalies": [], "frames": 60,
                             "emulated_s": 1.0, "wall_clock_s": 2.8,
                             "unpin_error": "the session could not be "
                                            "unpinned (TimeoutError: ...)"}):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "capture", "1", "/tmp/o"])
    assert r.exit_code == 0, r.output
    assert "warning: this session could not be unpinned" in r.output
    assert "unpin_error" in r.output              # and where the reason is
    assert "TimeoutError" not in r.output         # said once, not twice


def test_cli_audio_capture_reports_a_capture_failure():
    s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.capture",
               side_effect=AudioError("VICE wrote a 0-frame WAV")):
        S.attach.return_value = s
        r = CliRunner().invoke(main, ["audio", "capture", "1", "/tmp/o"])
    assert r.exit_code == 1
    assert "0-frame WAV" in r.output


# --- live: the whole path against a real emulator -----------------------------

#: PAL reg16 values for the fixture's arpeggio: `hz = reg16 * 985248 / 2**24`
#: puts these within 3 cents of C4/E4/G4. They are PAL values, which is why
#: the fixture insists on a PAL machine — NTSC's clock is the higher one
#: (1022727 Hz, +65 cents), so the same registers sound ~65 cents SHARP there
#: and transcribe as C#4/F4/G#4 sitting ~35 cents under each.
ARPEGGIO = {"C4": 4455, "E4": 5613, "G4": 6685}
#: Frames per arpeggio note, and the fixture's video rate (PAL).
#: `tests/data/arpeggio-score.yaml` pins the same 50 by hand — change one and
#: the other has to move with it.
NOTE_FRAMES, PAL_FPS = 50, 50
#: Frames of C4 the fixture sounds after the test releases it, before the
#: arpeggio walks on. This is the margin that keeps the capture from opening
#: on silence — see `test_capture_hears_a_live_arpeggio` for why that matters
#: and `_pin_and_arm` for what it has to cover (measured: 14 frames).
HOLD_FRAMES = 100
CAPTURE_SECONDS = 4.0
#: Tape-buffer bytes the fixture and the test hand each other: the fixture
#: raises READY_FLAG once voice 1 is sounding, the test raises GO_FLAG to
#: release the arpeggio.
READY_FLAG, GO_FLAG = 0x03F0, 0x03F1
#: Sawtooth, per the fixture contract (control $21 = sawtooth + gate).
SAWTOOTH = 0x20
ARPEGGIO_SCORE = Path(__file__).parent / "data" / "arpeggio-score.yaml"

#: The fixture program. Assembly rather than BASIC because the notes are
#: timed in whole frames: this counts raster wraps, so a note is exactly
#: NOTE_FRAMES frames long and the transcription can be checked against a
#: pinned duration. A BASIC loop's per-iteration cost is not frame-quantized,
#: so its note lengths would drift and could only be asserted loosely.
#:
#: It is inline for the same reason `tests/test_integration_profile.py`'s
#: reference routine is: `tests/programs/` is the *auto-collected* example
#: library (`c64 test programs` builds and runs every directory in it against
#: an expect.txt screen gate), and this program draws nothing, ends in an
#: endless loop, and needs a handshake from its test — it belongs to this
#: test, not to that suite.
ARPEGGIO_SRC = f"""\
        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"

READY   = ${READY_FLAG:04x}             ; raised once voice 1 is sounding C4
GO      = ${GO_FLAG:04x}             ; the test raises this to start the walk

C4      = {ARPEGGIO["C4"]}
E4      = {ARPEGGIO["E4"]}
G4      = {ARPEGGIO["G4"]}
HOLD    = {HOLD_FRAMES}
NOTE    = {NOTE_FRAMES}

start:  sei                     ; the frame wait polls the raster itself
        lda #$00
        sta GO
        sta $d405               ; attack 0 / decay 0
        lda #$f0
        sta $d406               ; sustain 15 / release 0: a flat, steady note
        lda #$0f
        sta $d418               ; volume
        lda #<C4
        sta $d400
        lda #>C4
        sta $d401
        lda #$21                ; sawtooth + gate on
        sta $d404
        lda #$01
        sta READY               ; C4 is sounding; the capture may open now

hold:   jsr frame               ; sound C4 until the test says go
        lda GO
        beq hold

        ldx #HOLD               ; still C4, covering the capture's own startup
        jsr frames
        lda #<E4
        sta $d400
        lda #>E4
        sta $d401
        ldx #NOTE
        jsr frames
        lda #<G4
        sta $d400
        lda #>G4
        sta $d401
        ldx #NOTE
        jsr frames
        lda #$20                ; gate off, waveform unchanged
        sta $d404
idle:   jmp idle

frames: jsr frame
        dex
        bne frames
        rts

;; One video frame: leave raster line 255, then wait for it to come round
;; again. Line 255 happens exactly once per frame on PAL and on NTSC.
frame:  lda #$ff
:       cmp $d012
        beq :-
:       cmp $d012
        bne :-
        rts
"""


@pytest.fixture
def pal_session(home):
    """This test's own PAL emulator, not conftest's shared machine.

    Three reasons it cannot be shared: the fixture's registers are only an
    arpeggio at the PAL clock (the shared machine is NTSC), a capture pins
    the session's speed and clears its warp for ten seconds, and the program
    masks interrupts and never returns to READY.

    Depends on `home` rather than trusting autouse ordering: the session
    record lands in whatever C64_TOOLS_HOME is set when it launches, and this
    file's `home` is what keeps it out of the developer's real sessions.
    """
    s = Session.launch(model="c64pal", name="arpeggio", headless=True,
                       warp=True)
    try:
        yield s
    finally:
        s.stop()


def _load_arpeggio(session, tmp_path) -> None:
    """Assemble and autostart the fixture, and return once it is sounding."""
    src = tmp_path / "arpeggio.s"
    src.write_text(ARPEGGIO_SRC)
    built = build_asm(src, basic_start=session.profile.basic_start)
    with session.monitor() as mon:
        try:
            mon.autostart(built.prg, run=True)
        finally:
            mon.resume()
    wait_for_mem(session, READY_FLAG, 1, timeout=60.0 * timeout_scale())


def _pin_and_arm(session, wav_path) -> None:
    """Pin the machine to real time *before* the fixture is released.

    The order matters as much as the pin. The capture has to open while the
    fixture is already sounding, so that the whole arpeggio is inside the
    window: the release and the capture have to be a known number of
    *emulated* frames apart, and on a warped session they are not — warp runs
    ~9.7x, so the same fraction of a second of setup is ~10x the frames, and a
    stalled warp readback (retried, but seen live) would put the whole
    arpeggio behind the capture window before it opened. At real time the gap
    is 14 frames against HOLD_FRAMES of cover.

    An unscored *leading* rest is now exempt from the diff the way a trailing
    one always was, so opening a few frames early costs window rather than
    cascading a wrong-note diff down the voice — but window is exactly what
    this fixture has none of to spare.

    The pin has to arm a recorder to survive, which is why this takes a path:
    a headless VICE at real time with nothing consuming its sound output stops
    answering its binary monitor within a second (`Session.launch(warp=False)`
    times out on this host for the same reason). `capture()` re-arms the
    recorder onto its own WAV, and its `pinned_record_stop` reads the pin this
    one wrote, so the session still gets its warp back at the end.
    """
    pinned_record_start(session, wav_path)


def _release_arpeggio(session) -> None:
    with session.monitor() as mon:
        try:
            mon.memory_write(GO_FLAG, b"\x01")
        finally:
            mon.resume()


def _dominant_hz(wav_path, start_s: float, end_s: float) -> float:
    """The loudest frequency in a slice of a WAV. A sawtooth's fundamental is
    its loudest partial, so this is the note the recording actually holds."""
    import numpy as np

    with wave.open(str(wav_path)) as w:
        rate, channels = w.getframerate(), w.getnchannels()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    mono = samples.astype(float).reshape(-1, channels).mean(axis=1)
    window = mono[int(start_s * rate):int(end_s * rate)]
    window = (window - window.mean()) * np.hanning(len(window))
    spectrum = np.abs(np.fft.rfft(window))
    return float(np.fft.rfftfreq(len(window), 1 / rate)[int(np.argmax(spectrum))])


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_capture_hears_a_live_arpeggio(pal_session, tmp_path):
    """The whole path against a real emulator: a program that plays a known
    arpeggio comes back as that arpeggio, with a PASS against a reference
    score and five artifacts on disk.

    Slow by design — the capture window runs at real time and each of its 200
    frames costs a monitor round trip, so this takes ~20 s of wall clock for
    4 s of emulated audio.
    """
    _load_arpeggio(pal_session, tmp_path)
    _pin_and_arm(pal_session, tmp_path / "prewarm.wav")
    _release_arpeggio(pal_session)

    outdir = tmp_path / "capture"
    out = capture(pal_session, CAPTURE_SECONDS, outdir,
                  ref_path=str(ARPEGGIO_SCORE))

    # The verdict, and the findings it was reached from.
    assert out["verdict"] == "PASS", out["failures"]
    assert out["diffs"] == [] and out["anomalies"] == []
    assert "**PASS**" in (outdir / "report.md").read_text()
    # A capture that put its session back: the verdict is about the audio,
    # this is about the machine that produced it.
    assert out["unpin_error"] is None

    # The machine the analysis read the log as, and every artifact — nothing
    # beside them, so a stray WAV or a renamed one is a failure.
    assert (out["machine"], out["clock_hz"], out["fps"]) == ("c64pal", PAL, 50)
    assert out["frames"] == out["requested_frames"] == round(
        CAPTURE_SECONDS * PAL_FPS)
    assert sorted(p.name for p in outdir.iterdir()) == [
        "capture.wav", "piano-roll.png", "report.md", "sid-log.jsonl",
        "spectrogram.png"]
    assert all((outdir / name).stat().st_size > 0 for name in
               ("piano-roll.png", "spectrogram.png"))

    with wave.open(str(outdir / "capture.wav")) as wav:
        assert wav.getnframes() > 0
        wav_seconds = wav.getnframes() / wav.getframerate()
    # Rate-aligned to the log, not offset-aligned: same duration, but do not
    # read sample N as frame N (see c64lib.audio's module docstring). The
    # tolerance covers the bracket of round trips at each end of the window,
    # measured at 0.089 s on a 4 s capture.
    assert abs(wav_seconds - out["emulated_s"]) < 0.25, wav_seconds
    assert out["metrics"]["clipped_samples"] == 0

    # The transcription itself, re-derived from the log the capture wrote.
    records = sid_analysis.parse_log(outdir / "sid-log.jsonl")
    events = sid_analysis.transcribe(records, PAL)
    voice1 = [e for e in events if e.voice == 1]
    assert [e.note for e in voice1[:3]] == ["C4", "E4", "G4"]
    # Anything after the arpeggio is the fixture's closing silence.
    assert all(e.note == "rest" for e in voice1[3:])
    assert all(e.note == "rest" for e in events if e.voice != 1)
    heard = {e.note: e for e in voice1[:3]}
    # C4 is however much of the opening note the capture caught — the rest of
    # it is the arm latency this test budgets HOLD_FRAMES for. Asserting half
    # of that budget is left, rather than merely "some", is what notices the
    # latency growing: at 99 frames of arm this would still catch a 1-frame C4
    # and pass, having silently spent the whole margin.
    assert heard["C4"].frames > HOLD_FRAMES // 2, heard["C4"].frames
    # The two notes the fixture times itself are exact: one `resume` advances
    # exactly one frame, so the log is contiguous in emulated time and a note
    # is as long as the program made it. If this ever fails by one frame, the
    # suspect is the sampling loop missing a sample, NOT the fixture's timing
    # — `diff_score` compares `frames` with no tolerance, so the same miss
    # also turns the verdict to FAIL. Diagnose it there; do not loosen this.
    assert heard["E4"].frames == heard["G4"].frames == NOTE_FRAMES
    for note in ("C4", "E4", "G4"):
        event = heard[note]
        assert event.waveform == SAWTOOTH
        assert event.gate_frames == event.frames        # gated throughout
        assert abs(event.cents_off) < 5, (note, event.cents_off)

    # The recording holds the notes the register log claims. Measured over the
    # middle of each note, which is far enough inside it to absorb the WAV's
    # ~0.1 s offset against the log.
    for note in ("E4", "G4"):
        event = heard[note]
        middle = (event.start_frame + event.frames / 2) / PAL_FPS
        heard_hz = _dominant_hz(outdir / "capture.wav", middle - 0.2,
                                middle + 0.2)
        want_hz = ARPEGGIO[note] * PAL / 2**24
        assert abs(heard_hz - want_hz) < want_hz * 0.02, (note, heard_hz)

    # The diff is doing work, on both halves of what the score asserts: the
    # same transcription against a score with one note changed has to come
    # back with that note in it, and against a score with one *duration*
    # changed with that duration in it. Without the first, a diff_score that
    # always returned [] would make everything above pass; without the second,
    # one that ignored `frames` would — and `frames` is half the reference.
    wrong_note = yaml.safe_load(ARPEGGIO_SCORE.read_text())
    wrong_note["voices"][1][1]["note"] = "D4"
    assert any("D4" in diff
               for diff in sid_analysis.diff_score(events, wrong_note))

    wrong_frames = yaml.safe_load(ARPEGGIO_SCORE.read_text())
    wrong_frames["voices"][1][1]["frames"] = 7
    assert any("7 frames" in diff
               for diff in sid_analysis.diff_score(events, wrong_frames))


# --- audio score ----------------------------------------------------------

THREE_VOICE_SCORE = """
voices:
  1:
    - {note: E4, frames: 7}
    - {note: rest, frames: 1}
    - {note: A4, frames: 7}
  2:
    - {note: A2, frames: 15}
  3: []
"""


def _score_file(tmp_path, text=THREE_VOICE_SCORE):
    path = tmp_path / "score.yaml"
    path.write_text(text)
    return str(path)


def test_audio_score_reports_one_line_per_voice(tmp_path):
    """The cheap half of the loop: a capture costs several times its emulated
    length in wall clock, so a score's arithmetic has to be checkable without
    spending one."""
    r = CliRunner().invoke(main, ["audio", "score", _score_file(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "voice 1: 3 entries, 15 frames, first E4, last A4" in r.output
    assert "voice 2: 1 entry, 15 frames, first A2, last A2" in r.output
    assert "voice 3: 0 entries, 0 frames, silent" in r.output
    assert "total: 4 entries, 30 frames across 3 voices" in r.output


def test_audio_score_counts_an_undurationed_entry_but_not_its_frames(tmp_path):
    """`frames` is optional per entry — the window's first and last notes are
    normally scored without one. The entry still exists, so it counts toward
    `entries`; there is no duration to add, so it must not perturb `frames`."""
    text = "voices:\n  1:\n    - {note: E4}\n    - {note: A4, frames: 9}\n"
    r = CliRunner().invoke(main, ["--json", "audio", "score",
                                  _score_file(tmp_path, text)])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["voices"]["1"] == {
        "entries": 2, "frames": 9, "first": "E4", "last": "A4"}


def test_audio_score_json_payload(tmp_path):
    r = CliRunner().invoke(main, ["--json", "audio", "score",
                                  _score_file(tmp_path)])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {
        "voices": {
            "1": {"entries": 3, "frames": 15, "first": "E4", "last": "A4"},
            "2": {"entries": 1, "frames": 15, "first": "A2", "last": "A2"},
            # An empty list is the positive claim "this voice sits out", so it
            # is present with nothing in it. A voice the score OMITS is absent
            # from the payload entirely — omitting one claims nothing.
            "3": {"entries": 0, "frames": 0, "first": None, "last": None},
        },
        "entries": 4,
        "frames": 30,
    }


def test_audio_score_omitted_voice_is_absent_rather_than_empty(tmp_path):
    r = CliRunner().invoke(main, ["--json", "audio", "score",
                                  _score_file(tmp_path, "voices:\n  2: []\n")])
    assert json.loads(r.output)["voices"] == {
        "2": {"entries": 0, "frames": 0, "first": None, "last": None}}


def test_audio_score_rejects_a_voice_the_sid_does_not_have(tmp_path):
    """`load_score` is the single reader for a score's shape and the source of
    every complaint about it — this command must not grow a second parser, so
    the message has to arrive verbatim."""
    r = CliRunner().invoke(main, ["audio", "score",
                                  _score_file(tmp_path, "voices:\n  4: []\n")])
    assert r.exit_code == 1
    assert "voice 4" in r.output + r.stderr
    assert "the SID's voices are 1, 2, 3" in r.output + r.stderr


def test_audio_score_names_the_entry_that_has_no_note(tmp_path):
    """An entry-level slip is not `load_score`'s to catch (it checks shape,
    not contents), and the whole point of this command is to find it before a
    capture does. The label must say which entry."""
    text = "voices:\n  1:\n    - {note: E4, frames: 7}\n    - {frames: 7}\n"
    r = CliRunner().invoke(main, ["audio", "score", _score_file(tmp_path, text)])
    assert r.exit_code == 1
    assert "voice 1 event 2" in r.output + r.stderr


def test_audio_score_needs_no_session(tmp_path):
    """Pure analysis, like `audio report`. It must not attach."""
    with patch("c64lib.cli.attach") as attach_mock:
        r = CliRunner().invoke(main, ["audio", "score", _score_file(tmp_path)])
    assert r.exit_code == 0, r.output
    attach_mock.assert_not_called()
