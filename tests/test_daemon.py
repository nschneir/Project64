"""PetDaemon unit tests: dispatch, state machine, idle pump — all with a
mocked MonitorClient; the IPC leg is a real socketpair."""

import collections
import json
import os
import socket
import tempfile
import threading
import time
from typing import cast
from unittest.mock import Mock

import pytest

from c64lib.daemon import RUNNING, STOPPED, PetDaemon, _connect_vice, main
from c64lib.daemon_client import DaemonMonitorClient
from c64lib.monitor import StopInfo
from c64lib.protocol import Command, ResponseType
from c64lib.rpc import UNKNOWN_METHOD, UnknownDaemonMethod, raise_remote
from tests.fake_vice import FakeVice, resp_frame


def _hit_event(number=3):
    """A CHECKPOINT_GET event with the hit flag set — VICE's signature for
    a genuine stop=True checkpoint park."""
    return Mock(response_type=Command.CHECKPOINT_GET,
                body=bytes([number, 0, 0, 0, 1]))


def _daemon(state=RUNNING) -> tuple[PetDaemon, Mock]:
    # Configure the Mock directly rather than reaching back through `d.mon`:
    # `PetDaemon.mon` is declared `MonitorClient`, so every `.return_value` /
    # `.assert_called_once()` reached that way is a mock attribute on a type
    # that does not declare one. Same object either way (`__init__` just
    # assigns), and the annotation carries `Mock` out to the callers.
    mon = Mock()
    # No listening socket: these daemons are driven through `_handle` on a
    # socketpair, so `listen` is never touched. The cast keeps that "unused
    # here" rather than widening `PetDaemon.listen` to Optional for every
    # caller — the real daemon always has one (`main` binds it before
    # constructing).
    d = PetDaemon(mon, cast(socket.socket, None), "t")
    d.state = state
    mon.events = collections.deque()
    mon.poll_events.return_value = []     # _restore pumps before deciding
    return d, mon


def _talk(d):
    a, b = socket.socketpair()
    t = threading.Thread(target=d._handle, args=(a,), daemon=True)
    t.start()
    f = b.makefile("rwb")
    hello = json.loads(f.readline())
    return b, f, t, hello


def _rpc(f, method, *args, **kwargs):
    f.write((json.dumps({"id": 1, "method": method, "args": list(args),
                         "kwargs": kwargs}) + "\n").encode())
    f.flush()
    return json.loads(f.readline())


def test_hello_greeting():
    d, _ = _daemon()
    b, f, t, hello = _talk(d)
    assert hello["hello"] == "c64-daemon" and hello["version"] == 1
    b.close(); t.join(timeout=2)


def test_dispatch_and_bytes_marshalling():
    d, mon = _daemon()
    mon.memory_read.return_value = b"\x2a"
    b, f, t, _ = _talk(d)
    resp = _rpc(f, "memory_read", 0x0400, 1)
    assert resp["ok"] == {"__bytes__": "Kg=="}
    mon.memory_read.assert_called_once_with(0x0400, 1)
    b.close(); t.join(timeout=2)


def test_unknown_method_rejected():
    d, _ = _daemon()
    b, f, t, _ = _talk(d)
    resp = _rpc(f, "os_system", "rm -rf /")
    assert resp["err"] == "ValueError"
    b.close(); t.join(timeout=2)


def test_unknown_method_carries_the_structural_code():
    """A client falls back to its own loop on this and only this. The `code`
    is what says so — the message stays for a client too old to read it."""
    d, _ = _daemon()
    b, f, t, _ = _talk(d)
    resp = _rpc(f, "no_such_method")
    assert resp["code"] == UNKNOWN_METHOD
    assert "unknown daemon method" in resp["msg"]
    with pytest.raises(UnknownDaemonMethod):
        raise_remote(resp["err"], resp["msg"], resp.get("code"))
    b.close(); t.join(timeout=2)


def test_a_refused_scheduled_write_is_not_the_unknown_method_handshake():
    """`_frame_writes` rejects an out-of-range write with a ValueError, and a
    client that read that as "old daemon" would re-run the whole capture
    window locally — performing the writes the daemon just refused."""
    d, _ = _daemon()
    b, f, t, _ = _talk(d)
    resp = _rpc(f, "sid_log_at", 3, 1.0, {"1": [[0xD404, 999]]})
    assert resp["err"] == "ValueError" and "code" not in resp
    assert "out of range" in resp["msg"]
    with pytest.raises(ValueError) as e:
        raise_remote(resp["err"], resp["msg"], resp.get("code"))
    assert not isinstance(e.value, UnknownDaemonMethod)
    b.close(); t.join(timeout=2)


def test_step_sets_stopped_resume_sets_running():
    d, mon = _daemon()
    mon.step.return_value = {"PC": 0x0410}
    b, f, t, _ = _talk(d)
    _rpc(f, "step", 1)
    assert d.state == STOPPED
    _rpc(f, "resume")
    assert d.state == RUNNING
    mon.resume.assert_called_once()
    b.close(); t.join(timeout=2)


def test_release_running_resumes_stopped_noop():
    d, mon = _daemon(state=RUNNING)
    b, f, t, _ = _talk(d)
    _rpc(f, "release")
    mon.resume.assert_called_once()
    d.state = STOPPED
    _rpc(f, "release")
    mon.resume.assert_called_once()    # unchanged: parked stays parked
    b.close(); t.join(timeout=2)


def test_disconnect_restores_by_state():
    d, mon = _daemon(state=RUNNING)
    b, f, t, _ = _talk(d)
    # Close the makefile too: while it holds a socket reference the peer never
    # sees EOF. (Production clients are separate processes whose exit delivers
    # EOF; here client and daemon share one process.)
    f.close(); b.close(); t.join(timeout=2)
    mon.resume.assert_called_once()    # safety net resumed

    d2, mon2 = _daemon(state=STOPPED)
    b2, f2, t2, _ = _talk(d2)
    f2.close(); b2.close(); t2.join(timeout=2)
    mon2.resume.assert_not_called()    # parked machine left parked


def test_wait_for_stop_hit_sets_stopped():
    d, mon = _daemon()
    mon.wait_for_stop.return_value = StopInfo(pc=0x1000, checkpoint=3)
    b, f, t, _ = _talk(d)
    resp = _rpc(f, "wait_for_stop", 1.0)
    assert resp["ok"]["__stopinfo__"]["pc"] == 0x1000
    assert d.state == STOPPED
    b.close(); t.join(timeout=2)


def test_quit_ends_daemon_without_restore():
    d, mon = _daemon(state=RUNNING)
    mon.quit.return_value = None       # real MonitorClient.quit() returns None
    b, f, t, _ = _talk(d)
    resp = _rpc(f, "quit")
    assert "ok" in resp
    t.join(timeout=2)
    assert d._quitting is True
    mon.resume.assert_not_called()
    b.close()


def test_pump_flips_state_and_requeues():
    d, mon = _daemon(state=RUNNING)
    mon.events = collections.deque()
    ev = Mock(response_type=ResponseType.STOPPED)
    mon.poll_events.return_value = [ev]
    assert d._pump_vice_events() is True
    assert d.state == STOPPED and list(mon.events) == [ev]


def test_pump_reports_vice_death():
    d, mon = _daemon()
    mon.poll_events.side_effect = ConnectionError("gone")
    assert d._pump_vice_events() is False


def test_restore_parks_on_checkpoint_hit_during_tenure():
    """A stop=True checkpoint that fires DURING a client's tenure (daemon
    blocked on the IPC socket, event unread) must be noticed at restore
    time — a blind resume would destroy the park (seen live as a parked
    machine read at the loop's jmp instead of mainloop)."""
    d, mon = _daemon(state=RUNNING)
    mon.poll_events.return_value = [
        _hit_event(), Mock(response_type=ResponseType.STOPPED)]
    d._restore()
    assert d.state == STOPPED
    mon.resume.assert_not_called()


def test_restore_ignores_bare_stopped_noise():
    """VICE emits a bare STOPPED for the momentary halt EVERY monitor
    command causes. At restore time that noise describes the very
    command-stop restore exists to undo — treating it as a park wedges
    the machine stopped forever (seen live: checkpoint_set's noise parked
    the session and the checkpoint never fired)."""
    d, mon = _daemon(state=RUNNING)
    mon.poll_events.return_value = [Mock(response_type=ResponseType.STOPPED)]
    d._restore()
    assert d.state == RUNNING
    mon.resume.assert_called_once()


def test_restore_resumed_cancels_stale_hit():
    """A hit whose events were still in flight when an explicit resume ran
    (c64 continue racing a fresh hit) must not re-park: the RESUMED that
    follows it is the truth."""
    d, mon = _daemon(state=RUNNING)
    mon.poll_events.return_value = [
        _hit_event(), Mock(response_type=ResponseType.STOPPED),
        Mock(response_type=ResponseType.RESUMED)]
    d._restore()
    assert d.state == RUNNING
    mon.resume.assert_called_once()


def test_restore_never_unparks():
    """A step/finish park (state already STOPPED) must stand no matter what
    events are pending — step's own RESUMED/STOPPED chatter included."""
    d, mon = _daemon(state=STOPPED)
    mon.poll_events.return_value = [Mock(response_type=ResponseType.RESUMED)]
    d._restore()
    assert d.state == STOPPED
    mon.resume.assert_not_called()


def test_pump_late_noise_heals_to_running():
    """Tenure noise delivered late lands in the IDLE pump as STOPPED
    followed by the RESUMED of the restore that undid it — last state wins,
    or the session falsely parks (the original full-suite flake: inspection
    read the machine frozen at the loop's jmp)."""
    d, mon = _daemon(state=RUNNING)
    mon.poll_events.return_value = [
        Mock(response_type=ResponseType.STOPPED),
        Mock(response_type=ResponseType.RESUMED)]
    assert d._pump_vice_events() is True
    assert d.state == RUNNING


def test_idle_wait_treats_closed_vice_socket_as_death():
    """If the VICE socket closes while the daemon idles (fileno -1), select
    used to raise ValueError and crash the daemon with a traceback. It must
    instead report VICE-gone so serve_forever shuts down cleanly."""
    d, mon = _daemon(state=RUNNING)
    a, b = socket.socketpair()
    d.listen = a
    mon._sock = b
    b.close()                          # VICE socket yanked out from under us
    assert d._idle_wait() is False     # returns cleanly (was ValueError: fd -1)
    a.close()


def test_idle_wait_treats_a_closed_monitor_as_death():
    """The other half of the same shutdown: `MonitorClient.close()` clears
    `_sock` to None, and select() answers None with TypeError — which the
    ValueError/OSError guard does not catch, so the daemon crashed with a
    traceback instead of exiting cleanly. A monitor with no socket is the
    same VICE-gone situation as a yanked one, and gets the same clean False."""
    d, mon = _daemon(state=RUNNING)
    a, b = socket.socketpair()
    d.listen = a
    mon._sock = None                   # the monitor was closed under us
    assert d._idle_wait() is False     # returns cleanly (was TypeError)
    a.close()
    b.close()


def test_handle_survives_client_gone_before_hello():
    """A command client that vanishes before reading the greeting used to
    crash the whole session daemon with BrokenPipeError (the hello send is
    outside _serve_client's try). _handle must swallow it and stay usable."""
    d, mon = _daemon(state=RUNNING)
    a, b = socket.socketpair()
    b.close()                     # peer gone before the daemon writes hello
    d._handle(a)                  # must NOT raise
    assert d._quitting is False   # session is fine; only that client is gone
    mon.resume.assert_called_once()  # RUNNING restored after the dropped client
    a.close()


def test_serve_forever_survives_bad_client_and_serves_next():
    """End to end: one client that connects and vanishes must not take down
    the daemon — the next command must still be greeted and served."""
    vice_a, vice_b = socket.socketpair()   # stand-in VICE sock; stays quiet
    mon = Mock()
    mon._sock = vice_a
    mon.ping.return_value = None
    mon.events = collections.deque()
    mon.poll_events.return_value = []
    sock_path = os.path.join(tempfile.mkdtemp(prefix="c64-sf-"), "d.sock")
    listen = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listen.bind(sock_path)
    listen.listen(1)
    d = PetDaemon(mon, listen, "t")
    th = threading.Thread(target=d.serve_forever, daemon=True)
    th.start()
    try:
        bad = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        bad.connect(sock_path)
        bad.close()                # vanish before reading hello
        time.sleep(0.2)            # let the daemon accept + drop it
        good = DaemonMonitorClient(sock_path)   # reads hello in __init__
        good.ping()                # a real round-trip proves it still serves
        good.close()
        assert th.is_alive()       # the bad client did not kill the daemon
    finally:
        listen.close()
        vice_a.close()
        vice_b.close()


def _vice_handlers():
    """Enough of a fake VICE for connect+ping+resume+quit. VICE echoes the
    command code as the response type, so Command.X doubles as the rtype
    (matches tests/test_monitor.py's frame convention)."""
    return {
        Command.PING: lambda b, rid: [resp_frame(Command.PING, 0, rid)],
        Command.EXIT: lambda b, rid: [resp_frame(Command.EXIT, 0, rid)],
        Command.QUIT: lambda b, rid: [resp_frame(Command.QUIT, 0, rid)],
    }


def test_connect_vice_gives_up_when_nothing_listens():
    # no listener at all -> every attempt fails -> ConnectionError preserving
    # the last underlying error (exercises the full ~8s retry loop)
    with pytest.raises(ConnectionError, match="could not reach VICE"):
        _connect_vice(port=1)


def test_connect_vice_succeeds_and_sets_operational_timeout():
    fake = FakeVice(_vice_handlers())
    mon = _connect_vice(fake.port)
    try:
        assert mon.timeout == 5.0
    finally:
        mon.close()
        fake.close()


def test_main_serves_then_quits():
    fake = FakeVice(_vice_handlers())
    # A short socket dir: macOS caps AF_UNIX sun_path at ~104 bytes and
    # pytest's tmp_path blows past it (flake caught by Fable). mkdtemp under
    # /tmp is short and collision-free.
    sockdir = tempfile.mkdtemp(dir="/tmp")
    sock = os.path.join(sockdir, "s.sock")
    t = threading.Thread(
        target=main,
        args=(["--name", "t", "--vice-port", str(fake.port), "--socket", sock],),
        daemon=True)
    t.start()
    deadline = time.monotonic() + 5
    while not os.path.exists(sock) and time.monotonic() < deadline:
        time.sleep(0.05)
    client = DaemonMonitorClient(sock)
    client.quit()
    client.close()
    t.join(timeout=5)
    assert not t.is_alive()
    assert not os.path.exists(sock)     # main() cleaned up its socket
    fake.close()
    os.rmdir(sockdir)                   # empty now that main() unlinked the socket


def test_connection_error_marshalled_and_daemon_quits():
    d, mon = _daemon()
    mon.memory_read.side_effect = ConnectionError("x64sc died")
    b, f, t, _ = _talk(d)
    resp = _rpc(f, "memory_read", 0x0400, 1)
    assert resp["err"] == "ConnectionError" and "x64sc died" in resp["msg"]
    t.join(timeout=2)
    assert d._quitting is True          # daemon gives up; nothing to restore
    b.close()


def test_status_verb_reports_state_without_touching_vice():
    for state in (RUNNING, STOPPED):
        d, mon = _daemon(state=state)
        b, f, t, _ = _talk(d)
        assert _rpc(f, "status")["ok"] == {"state": state}
        assert not mon.method_calls        # zero VICE traffic
        b.close(); t.join(timeout=2)
