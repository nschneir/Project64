"""Audio capture: arm VICE's WAV recorder, and hold the machine at real time.

Two primitives, deliberately separate. `record_start`/`record_stop` arm and
disarm the recorder through the binary monitor's resource interface;
`pin_realtime`/`restore_speed` take the emulator off warp for the capture
window and put it back. The orchestrator composes them — `record_start`
does not pin by itself, because a caller who has already pinned (a long
capture that records several takes) must not be re-pinned per take. The
front ends (`c64 audio record`, `c64_audio_record`) always pin, since an
agent reaching for them wants a listenable file, not a warped one.

Why warp needs its own channel: sessions boot with `-warp`, and on VICE
3.10 warp is not a resource — `WarpMode`/`Warp` do not exist, and `Speed`
is a different axis entirely (a warped session already reads `Speed ==
100`). The only lever is the `warp` command of VICE's *text* monitor,
which can be started at runtime over the binary monitor. That matters more
than it sounds: while warped VICE writes a **0-frame** WAV — not
time-compressed audio, nothing at all — so a capture that fails to clear
warp fails silently. `pin_realtime` therefore confirms warp is off before
returning, and refuses the capture if it cannot.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
from pathlib import Path

from .monitor import MonitorError
from .session import sessions_dir

#: VICE's recorder: the output path (set FIRST — arming with no arg drops a
#: `vicesnd.wav` into the VICE process's working directory) and the driver
#: name, `"wav"` to arm and `""` to disarm.
REC_ARG = "SoundRecordDeviceArg"
REC_NAME = "SoundRecordDeviceName"

#: `Speed` is a percentage; 100 is real time. It does not clear warp — see
#: the module docstring — but it is the throttle that applies once warp is
#: off, so a capture pins it too.
SPEED = "Speed"
REALTIME_SPEED = 100

_ADDRESS = re.compile(r"ip4://127\.0\.0\.1:(\d+)")
_WARP_STATE = re.compile(r"Warp mode is (on|off)\.")


class AudioError(RuntimeError):
    """A capture could not be armed, or warp could not be cleared."""


def _abs(path) -> str:
    """Absolute, but not resolved: VICE only needs a rooted path, and
    following symlinks would hand back `/private/tmp/...` for a `/tmp/...`
    the caller asked for."""
    return os.path.abspath(os.path.expanduser(str(path)))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _TextMonitor:
    """VICE's text monitor, started at runtime over the binary monitor.

    A capture-time implementation detail of this module: warp is reachable
    nowhere else on 3.10 (see the module docstring), and one command —
    `warp` — is all this class exists to send. It is deliberately not on
    `MonitorClient` and not exposed over the daemon RPC.

    Setting `MonitorServerAddress` then `MonitorServer` opens the listener
    immediately, with no launch-line flag; the two monitors coexist and
    attaching does not pause the machine. `MonitorServer` stays on for the
    session's life, so a later capture reuses the address already set.
    """

    _CONNECT_TIMEOUT = 5.0
    _REPLY_TIMEOUT = 3.0

    def __init__(self, sock: socket.socket):
        self._sock = sock

    @classmethod
    def open(cls, session) -> _TextMonitor:
        with session.monitor() as mon:
            try:
                try:
                    current = str(mon.resource_get("MonitorServerAddress"))
                except (MonitorError, KeyError, ValueError):
                    current = ""          # never set on this session yet
                known = _ADDRESS.search(current)
                port = int(known.group(1)) if known else _free_port()
                if not known:
                    mon.resource_set("MonitorServerAddress",
                                     f"ip4://127.0.0.1:{port}")
                mon.resource_set("MonitorServer", 1)   # harmless when already 1
            finally:
                # resume, not release: every binary-monitor command halts the
                # machine, and a capture needs it running.
                mon.resume()
        deadline = time.monotonic() + cls._CONNECT_TIMEOUT
        while True:
            try:
                sock = socket.create_connection(("127.0.0.1", port),
                                                timeout=cls._REPLY_TIMEOUT)
                return cls(sock)
            except OSError as e:
                if time.monotonic() >= deadline:
                    raise AudioError(
                        f"VICE's text monitor never accepted a connection on "
                        f"port {port}: {e}") from e
                time.sleep(0.1)

    def _drain(self) -> None:
        """Swallow the prompt echo left over from the previous command. It
        is asynchronous and repeated (`(C:$e5d4) (C:$e5d4) `), so replies are
        matched by content, never by position."""
        self._sock.settimeout(0.05)
        for _ in range(64):
            try:
                if not self._sock.recv(4096):
                    return
            except OSError:
                return

    def _send(self, line: str) -> None:
        self._drain()
        self._sock.sendall(line.encode("ascii") + b"\n")

    def _await(self, pattern: re.Pattern[str]) -> re.Match[str] | None:
        deadline = time.monotonic() + self._REPLY_TIMEOUT
        buf = ""
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            self._sock.settimeout(left)
            try:
                data = self._sock.recv(4096)
            except OSError:
                return None
            if not data:
                return None
            buf += data.decode("ascii", "replace")
            found = pattern.search(buf)
            if found:
                return found

    def warp_state(self) -> bool:
        """True when warp is on. A bare `warp` is the only readback of live
        warp state VICE 3.10 has."""
        self._send("warp")
        found = self._await(_WARP_STATE)
        if found is None:
            raise AudioError("VICE's text monitor did not report a warp state")
        return found.group(1) == "on"

    def set_warp(self, on: bool) -> None:
        """Set warp and confirm it took — the failure this guards against is
        silent (a warped capture yields an empty WAV, not a fast one)."""
        self._send("warp on" if on else "warp off")
        if self.warp_state() is not on:
            raise AudioError(
                f"VICE ignored 'warp {'on' if on else 'off'}'; "
                f"warp is still {'on' if not on else 'off'}")

    def close(self) -> None:
        """Teardown order is load-bearing: `x` to leave the monitor, then
        `shutdown(SHUT_RDWR)`, then close. Closing without the shutdown
        wedged VICE in 2 of 3 attempts; with it, 8 of 8 were clean."""
        try:
            self._send("x")
        except OSError:
            pass
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()


# --- the four primitives -----------------------------------------------------

def record_start(session, wav_path) -> str:
    """Arm VICE's WAV recorder on `wav_path`; returns the absolute path.

    Does NOT pin the speed: compose it with `pin_realtime`, or use
    `pinned_record_start`. Samples only accumulate while the machine runs,
    so the machine is left running.
    """
    path = _abs(wav_path)
    with session.monitor() as mon:
        try:
            mon.resource_set(REC_ARG, path)      # arg first, always
            mon.resource_set(REC_NAME, "wav")
        finally:
            mon.resume()
    return path


def record_stop(session) -> None:
    """Disarm the recorder, finalizing the WAV.

    There is no readback worth trusting here — `resource_get` cannot tell a
    one-byte NUL string from an empty one — so confirm a stop by the file:
    it stops growing and its header is finalized.
    """
    with session.monitor() as mon:
        try:
            mon.resource_set(REC_NAME, "")
        finally:
            mon.resume()


def pin_realtime(session) -> dict:
    """Take the machine off warp and pin `Speed` to 100 for a capture.

    Returns the state to hand back to `restore_speed`:
    `{"warp": bool, "speed": int}` — warp as the text monitor reported it
    (sessions normally boot warped, but `Session.launch(warp=False)` and
    `c64 session start` without `--warp` do not), and `Speed` as it read.
    Raises AudioError if warp cannot be cleared, rather than let the
    capture come back as a 0-frame WAV.
    """
    text = _TextMonitor.open(session)
    try:
        warp = text.warp_state()
        if warp:
            text.set_warp(False)
    finally:
        text.close()
    with session.monitor() as mon:
        try:
            speed = mon.resource_get(SPEED)
            mon.resource_set(SPEED, REALTIME_SPEED)
        finally:
            mon.resume()
    return {"warp": warp, "speed": int(speed)}


def restore_speed(session, saved: dict) -> None:
    """Put back what `pin_realtime` saved: `Speed` always, warp only when it
    was on (re-warping a session that was never warped would be a change,
    not a restore)."""
    with session.monitor() as mon:
        try:
            mon.resource_set(SPEED, int(saved.get("speed", REALTIME_SPEED)))
        finally:
            mon.resume()
    if saved.get("warp"):
        text = _TextMonitor.open(session)
        try:
            text.set_warp(True)
        finally:
            text.close()


# --- start/stop as the front ends use them -----------------------------------

def _pin_path(session) -> Path:
    """Where a pinned recording remembers what to restore. Start and stop
    are separate processes for the CLI, so the saved state outlives neither
    unless it is on disk; a sidecar beside the session record is how this
    codebase already keeps per-session scratch state (`<name>.respawns`).

    The extension is NOT `.json`, deliberately: `Session._load_all()` reads
    every `*.json` in this directory as a session record, so a `.json`
    sidecar here breaks `c64` altogether (`KeyError: 'name'`).
    """
    return sessions_dir() / f"{session.name}.audio"


def _read_pin(session) -> dict | None:
    path = _pin_path(session)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _clear_pin(session) -> None:
    _pin_path(session).unlink(missing_ok=True)


def pinned_record_start(session, wav_path) -> dict:
    """Pin the machine to real time, then arm the recorder — the order both
    front ends need. A failure to arm unpins before it propagates, so a
    broken capture never leaves the session stuck at 1x."""
    path = _abs(wav_path)
    saved = pin_realtime(session)
    earlier = _read_pin(session)
    if earlier is not None:
        # A start with no stop in between: this pin only re-read the values
        # the first one already imposed, so the first one's saved state is
        # the real pre-capture state. Keep it, or the session never gets
        # its warp back.
        saved = {"warp": earlier.get("warp", False),
                 "speed": earlier.get("speed", REALTIME_SPEED)}
    _pin_path(session).write_text(json.dumps({**saved, "wav": path}))
    try:
        record_start(session, path)
    except Exception:
        _clear_pin(session)
        restore_speed(session, saved)
        raise
    return {"wav": path, "pinned": saved}


def pinned_record_stop(session) -> dict:
    """Disarm the recorder and undo the pin. Reports the WAV's size, which
    is the only honest evidence that the recording stopped and landed."""
    saved = _read_pin(session)
    try:
        record_stop(session)
    finally:
        if saved is not None:
            # restore first, forget second: a restore that fails leaves the
            # pin on disk, so a second `stop` can try again rather than
            # stranding the session at 1x with nothing to put back.
            restore_speed(session, saved)
            _clear_pin(session)
    wav = (saved or {}).get("wav")
    size = os.path.getsize(wav) if wav and os.path.exists(wav) else None
    restored = ({"warp": saved.get("warp", False),
                 "speed": saved.get("speed", REALTIME_SPEED)}
                if saved is not None else None)
    return {"wav": wav, "bytes": size, "restored": restored}
