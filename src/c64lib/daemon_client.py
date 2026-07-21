"""Client side of the session monitor daemon: a MonitorClient look-alike
whose every method is one JSON-RPC call over the session's unix socket.
Returned by Session.monitor() when the session has a daemon."""

from __future__ import annotations

import itertools
import json
import socket

from . import rpc

DEFAULT_TIMEOUT = 10.0


class DaemonMonitorClient:
    def __init__(self, socket_path: str, timeout: float = DEFAULT_TIMEOUT):
        self.socket_path = socket_path
        self.timeout = timeout
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect(socket_path)
        self._file = self._sock.makefile("rwb")
        self._ids = itertools.count(1)
        hello = json.loads(self._file.readline() or b"{}")
        if hello.get("hello") != "c64-daemon":
            self.close()
            raise ConnectionError(f"{socket_path} is not a c64 session daemon")

    # --- plumbing ---------------------------------------------------------

    def _call(self, method: str, *args, _timeout: float | None = None, **kwargs):
        rid = next(self._ids)
        rpc.send_line(self._file, {
            "id": rid, "method": method,
            "args": rpc.encode_value(list(args)),
            "kwargs": rpc.encode_value(kwargs),
        })
        if _timeout is not None:
            self._sock.settimeout(_timeout)
        try:
            line = self._file.readline()
        finally:
            if _timeout is not None:
                self._sock.settimeout(self.timeout)
        if not line:
            raise ConnectionError("session daemon closed the connection")
        resp = json.loads(line)
        if resp.get("id") != rid:
            raise ConnectionError("session daemon protocol desync")
        if "err" in resp:
            rpc.raise_remote(resp["err"], resp.get("msg", ""))
        return rpc.decode_value(resp.get("ok"))

    def close(self) -> None:
        # The makefile MUST be closed too: the underlying fd stays open until
        # both the socket object and every makefile() object are closed, and
        # a lingering fd means the daemon never sees EOF for this connection —
        # it stays blocked in readline() and the next client's hello times
        # out, misdiagnosed as a dead daemon (then the respawn can't reach
        # VICE because this perfectly healthy daemon still holds the slot).
        try:
            self._file.close()
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    def __enter__(self) -> DaemonMonitorClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- MonitorClient surface ---------------------------------------------

    def ping(self) -> None:
        self._call("ping")

    def memory_read(self, start, length, **kw) -> bytes:
        return self._call("memory_read", start, length, **kw)

    def memory_write(self, start, data, **kw) -> None:
        self._call("memory_write", start, data, **kw)

    def resume(self) -> None:
        self._call("resume")

    def release(self) -> None:
        self._call("release")

    def registers(self) -> dict:
        return self._call("registers")

    def set_register(self, name, value) -> None:
        self._call("set_register", name, value)

    def reset(self, hard: bool = False) -> None:
        self._call("reset", hard=hard)

    def keyboard_feed(self, petscii: bytes) -> None:
        self._call("keyboard_feed", petscii)

    def display(self):
        w, h, px = self._call("display")
        return w, h, px

    def palette(self):
        return [tuple(c) for c in self._call("palette")]

    def vice_info(self) -> str:
        return self._call("vice_info")

    def quit(self) -> None:
        try:
            self._call("quit")
        except (ConnectionError, TimeoutError, OSError):
            pass                       # daemon/VICE may exit before replying

    def resource_get(self, name):
        return self._call("resource_get", name)

    def autostart(self, path, run: bool = True) -> None:
        self._call("autostart", str(path), run=run)

    def checkpoint_set(self, start, end=None, **kw):
        return self._call("checkpoint_set", start, end, **kw)

    def checkpoint_delete(self, number) -> None:
        self._call("checkpoint_delete", number)

    def checkpoint_toggle(self, number, enabled) -> None:
        self._call("checkpoint_toggle", number, enabled)

    def checkpoint_list(self) -> list:
        return self._call("checkpoint_list")

    def condition_set(self, number, expr) -> None:
        self._call("condition_set", number, expr)

    def step(self, count: int = 1, over: bool = False) -> dict:
        return self._call("step", count, over=over)

    def finish(self) -> dict:
        return self._call("finish")

    def wait_for_stop(self, timeout: float):
        return self._call("wait_for_stop", timeout, _timeout=timeout + 5.0)

    def run_until(self, addr: int, timeout: float, count: int = 1) -> dict:
        """Daemon-side frame stepping: the whole count loop is one RPC.
        Raises ValueError against a pre-run_until daemon (caller falls back)."""
        return self._call("run_until", addr, timeout, count,
                          _timeout=timeout + 5.0)

    def status(self) -> str:
        """The daemon's tracked machine state: 'running' or 'stopped'.
        Answered daemon-side; no VICE traffic."""
        return self._call("status")["state"]
