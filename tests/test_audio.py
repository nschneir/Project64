"""Unit tests for c64lib.audio.

Two behaviours carry the whole module: the exact resource sequence VICE
needs to arm its WAV recorder (arg BEFORE name, or it drops vicesnd.wav in
the process CWD), and the warp/speed pin — under warp VICE writes a
0-frame WAV, so a capture that forgets to clear warp fails silently.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from unittest.mock import Mock, call, patch

import pytest
from click.testing import CliRunner

from c64lib import audio
from c64lib.audio import (
    AudioError,
    pin_realtime,
    pinned_record_start,
    pinned_record_stop,
    record_start,
    record_stop,
    restore_speed,
)
from c64lib.cli import main
from tests.test_mcp_scaffold import call_tool


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
        """Wait for the client's parting `x` to be logged. close() sends it
        and returns without waiting for a reply, so a test that asserts on
        `lines` immediately would race the server thread."""
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


def test_module_exposes_only_the_capture_surface():
    """The text-monitor channel is a capture-time detail of this module, not
    a new public surface — it must not appear on MonitorClient."""
    from c64lib.monitor import MonitorClient
    assert not hasattr(MonitorClient, "warp")
    assert audio._TextMonitor.__name__.startswith("_")
