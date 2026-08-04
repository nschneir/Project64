"""DaemonMonitorClient round-trips against a real PetDaemon (mocked
MonitorClient) over a real unix socket."""

import collections
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from c64lib.daemon import STOPPED, PetDaemon
from c64lib.daemon_client import DaemonMonitorClient
from c64lib.monitor import MonitorClient, MonitorError, StopInfo
from c64lib.protocol import CP_EXEC, Checkpoint


@pytest.fixture
def served():
    """(client, mock_mon, daemon) with the daemon handling one connection."""
    mon = Mock()
    mon.events = collections.deque()
    mon.poll_events.return_value = []      # _restore pumps before deciding
    sock_path = str(Path(tempfile.mkdtemp(prefix="c64-dc-")) / "d.sock")
    listen = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listen.bind(sock_path)
    listen.listen(1)
    d = PetDaemon(mon, listen, "t")

    def run():
        client, _ = listen.accept()
        d._handle(client)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    c = DaemonMonitorClient(sock_path)
    yield c, mon, d
    c.close()
    t.join(timeout=2)
    listen.close()


def test_memory_read_bytes_round_trip(served):
    c, mon, _ = served
    mon.memory_read.return_value = b"\x2a\x00"
    assert c.memory_read(0x0400, 2) == b"\x2a\x00"
    mon.memory_read.assert_called_once_with(0x0400, 2)


def test_memory_write_sends_bytes(served):
    c, mon, _ = served
    mon.memory_write.return_value = None    # real MonitorClient returns None
    c.memory_write(0x0400, b"\x01\x02")
    mon.memory_write.assert_called_once_with(0x0400, b"\x01\x02")


def test_checkpoint_set_round_trip(served):
    c, mon, _ = served
    ck = Checkpoint(number=4, hit=False, start=0x040F, end=0x040F, stop=True,
                    enabled=True, op=CP_EXEC, temporary=False, hit_count=0,
                    ignore_count=0, has_condition=False, memspace=0)
    mon.checkpoint_set.return_value = ck
    out = c.checkpoint_set(0x040F, op=CP_EXEC, temporary=False)
    assert out == ck and isinstance(out, Checkpoint)
    mon.checkpoint_set.assert_called_once_with(0x040F, None, op=CP_EXEC,
                                               temporary=False)


def test_exception_maps_to_local_type(served):
    c, mon, _ = served
    mon.registers.side_effect = TimeoutError("no response to REGISTERS_GET")
    with pytest.raises(TimeoutError):
        c.registers()


def test_wait_for_stop_round_trip_sets_stopped(served):
    c, mon, d = served
    mon.wait_for_stop.return_value = StopInfo(pc=0x1000, checkpoint=7)
    assert c.wait_for_stop(2.0) == StopInfo(pc=0x1000, checkpoint=7)
    assert d.state == STOPPED


def test_autostart_sends_str_path(served):
    c, mon, _ = served
    mon.autostart.return_value = None       # real MonitorClient returns None
    c.autostart(Path("/tmp/x.prg"), run=True)
    mon.autostart.assert_called_once_with("/tmp/x.prg", run=True)


def test_release_restores_running(served):
    c, mon, _ = served
    c.release()
    mon.resume.assert_called_once()


def test_not_a_daemon_socket_raises(tmp_path_factory):
    d = tempfile.mkdtemp(prefix="c64-dc-")
    path = str(Path(d) / "bogus.sock")
    listen = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listen.bind(path)
    listen.listen(1)

    def run():
        cl, _ = listen.accept()
        cl.sendall(b'{"nope": 1}\n')
        cl.close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    with pytest.raises(ConnectionError):
        DaemonMonitorClient(path)
    t.join(timeout=2)
    listen.close()


def test_close_delivers_eof_so_next_client_is_served_promptly():
    """THE hang regression: close() must close the makefile too, or the fd
    stays open, the daemon never sees EOF, and the NEXT client's hello read
    times out while the old client object is still referenced — exactly the
    wait_for_text loop pattern (`with session.monitor() as mon:` per poll)."""
    vice_a, vice_b = socket.socketpair()   # quiet stand-in for the VICE sock
    mon = Mock()
    mon._sock = vice_a
    mon.ping.return_value = None
    mon.events = collections.deque()
    mon.poll_events.return_value = []
    sock_path = str(Path(tempfile.mkdtemp(prefix="c64-dc-")) / "d.sock")
    listen = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listen.bind(sock_path)
    listen.listen(1)
    d = PetDaemon(mon, listen, "t")
    th = threading.Thread(target=d.serve_forever, daemon=True)
    th.start()
    try:
        c1 = DaemonMonitorClient(sock_path, timeout=2.0)
        c1.ping()
        c1.close()
        # c1 stays referenced (like `mon` after a with-block) — only a real
        # fd close can deliver EOF. The next client must be greeted fast.
        c2 = DaemonMonitorClient(sock_path, timeout=2.0)
        c2.ping()
        c2.close()
        assert c1 is not None              # keep c1 alive to the very end
    finally:
        listen.close()
        vice_a.close()
        vice_b.close()


def test_direct_monitorclient_release_aliases_resume():
    m = MonitorClient.__new__(MonitorClient)
    calls = []
    m.resume = lambda: calls.append(1)
    m.release()
    assert calls == [1]


# --- passthrough methods and failure modes (reuse the `served` fixture) -------

@pytest.mark.parametrize("method,args,monattr", [
    ("reset", (True,), "reset"),
    ("keyboard_feed", (b"RUN\r",), "keyboard_feed"),
    ("vice_info", (), "vice_info"),
    ("checkpoint_toggle", (1, False), "checkpoint_toggle"),
    ("condition_set", (1, "A == 0"), "condition_set"),
    ("resource_set", ("Speed", 90), "resource_set"),
])
def test_passthrough_methods(served, method, args, monattr):
    c, mon, _ = served
    getattr(mon, monattr).return_value = "ok"   # JSON-serializable; void methods ignore it
    getattr(c, method)(*args)
    assert getattr(mon, monattr).called


def test_display_and_palette_marshalling(served):
    c, mon, _ = served
    mon.display.return_value = (320, 200, b"\x00\x01")
    assert c.display() == (320, 200, b"\x00\x01")
    # full travels as a keyword, like the other trailing flags (reset, step)
    mon.display.assert_called_once_with(full=False)
    mon.display.reset_mock()
    mon.display.return_value = (384, 272, b"\x02\x03")
    assert c.display(True) == (384, 272, b"\x02\x03")
    mon.display.assert_called_once_with(full=True)
    mon.palette.return_value = [(0, 0, 0), (255, 255, 255)]
    assert c.palette() == [(0, 0, 0), (255, 255, 255)]


def test_quit_swallows_connection_teardown(served):
    c, mon, _ = served
    mon.quit.side_effect = ConnectionError("gone")
    c.quit()                    # must not raise


def test_remote_exception_reraises(served):
    c, mon, _ = served
    mon.memory_read.side_effect = MonitorError(0x01, 0x02)
    with pytest.raises(MonitorError):
        c.memory_read(0x0400, 1)


def test_daemon_gone_raises_connection_error(served):
    c, mon, _ = served
    # shutdown (not close): close leaves the fd open via the makefile ref, so
    # the request would still reach the daemon. SHUT_RDWR makes the client's
    # own send fail (BrokenPipe) — the real "connection dead" path.
    c._sock.shutdown(socket.SHUT_RDWR)
    with pytest.raises((ConnectionError, OSError)):
        c.registers()


def test_wait_for_stop_stretches_socket_timeout(served):
    c, mon, _ = served
    mon.wait_for_stop.return_value = None
    assert c.wait_for_stop(0.1) is None


def test_status_roundtrip(served):
    c, _, _ = served
    assert c.status() == "running"


# --- run_until: the count loop lives daemon-side (one RPC per call) -----------

def _ck(number=4, hit=False, hit_count=0):
    return Checkpoint(number=number, hit=hit, start=0x0419, end=0x0419,
                      stop=True, enabled=True, op=CP_EXEC, temporary=False,
                      hit_count=hit_count, ignore_count=0, has_condition=False,
                      memspace=0)


def test_run_until_counts_hits_daemon_side(served):
    c, mon, d = served
    mon.checkpoint_set.return_value = _ck()
    mon.wait_for_stop.return_value = StopInfo(pc=0x0419, checkpoint=4)
    mon.registers.return_value = {"PC": 0x0419, "A": 0}
    out = c.run_until(0x0419, 5.0, 3)
    assert out == {"registers": {"PC": 0x0419, "A": 0}, "reached": 3, "count": 3}
    # the loop ran inside the daemon: one resume per requested arrival
    assert mon.resume.call_count == 3
    mon.checkpoint_delete.assert_called_once_with(4)
    assert d.state == STOPPED


def test_run_until_timeout_leaves_running_and_deletes_checkpoint(served):
    c, mon, d = served
    mon.checkpoint_set.return_value = _ck()
    mon.wait_for_stop.return_value = None           # never arrives
    mon.checkpoint_list.return_value = [_ck()]      # durable flag never set
    out = c.run_until(0x0419, 0.3, 2)
    assert out["registers"] is None
    assert out["reached"] == 0 and out["count"] == 2
    mon.checkpoint_delete.assert_called_once_with(4)
    assert d.state == "running"


def test_run_until_durable_flag_fallback(served):
    """A lost STOPPED event must not lose the arrival: the checkpoint's
    hit/hit_count flags are the durable source of truth (same contract as
    the old client-side loop)."""
    c, mon, d = served
    mon.checkpoint_set.return_value = _ck()
    mon.wait_for_stop.return_value = None           # event lost
    mon.checkpoint_list.return_value = [_ck(hit=True, hit_count=1)]
    mon.registers.return_value = {"PC": 0x0419}
    out = c.run_until(0x0419, 5.0, 1)
    assert out["reached"] == 1 and out["registers"] == {"PC": 0x0419}
    assert d.state == STOPPED


# --- sid_log: the per-frame sampling loop also lives daemon-side --------------

def test_sid_log_samples_one_frame_per_resume_daemon_side(served):
    """A binary-monitor halt always lands at the top of a frame, so one
    resume is exactly one frame and one 25-byte read is one sample. Per-frame
    RPCs would cost ~0.5 s a frame, hence the daemon-side loop."""
    c, mon, d = served
    mon.memory_read.return_value = bytes(range(25))
    out = c.sid_log(4, 5.0)
    assert out == [bytes(range(25))] * 4
    assert mon.memory_read.call_args_list == [call(0xD400, 25)] * 4
    # four sampled frames plus the resume that leaves the machine running
    assert mon.resume.call_count == 5
    assert d.state == "running"


def test_sid_log_returns_what_it_has_at_the_deadline(served):
    """A machine that will not advance must not hang the client: the loop
    stops at its deadline and hands back the frames it did get."""
    c, mon, d = served

    def slow(*a, **kw):
        time.sleep(0.05)
        return bytes(25)

    mon.memory_read.side_effect = slow
    out = c.sid_log(100, 0.25)
    assert 0 < len(out) < 100
    assert d.state == "running"
