"""Audio capture: arm VICE's WAV recorder, hold the machine at real time,
and log the SID's registers frame by frame.

Three capture primitives, deliberately separate. `record_start`/`record_stop`
arm and disarm the recorder through the binary monitor's resource interface;
`pin_realtime`/`restore_speed` take the emulator off warp for the capture
window and put it back; `sid_log` samples the chip's registers frame by
frame, and changes neither speed nor recorder. The orchestrator composes
them — `record_start`
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

Why `sid_log` does not poll `$D012`, though every reference (this project's
own skill notes included) says a raster value wrapping to a smaller one
marks a new frame: it does on real hardware, and it is unobservable from
VICE's *binary monitor*. An asynchronous monitor command is picked up at
the next vsync, so the machine only ever halts at the top of a frame.
Measured live on a boot screen: 600 consecutive `$D012` reads all returned
12 — with and without read side effects — and every `registers()` came back
`LIN 12, CYC 0-2`. A wrap-detecting loop would spin to its deadline and log
nothing.

The same behaviour hands over a better frame clock than the raster ever
was: one resume advances exactly one frame, and every sample is therefore
taken at a frame boundary, with no polling at all. It holds because the
machine advances only while resumed — it cannot outrun a loop that owns its
run windows. Measured against the KERNAL jiffy, bracketed inside one
monitor session: 200 samples over 201 elapsed frames at real time (every
frame), and 200 over 202 warped.

That second figure is the whole reason `sid_log_detail` returns a warning.
Warped, an emulated frame (~2 ms) is about as long as one sampling round
trip, so the machine can reach the next vsync before the next read is
queued and a frame goes unrecorded; at real time the frame is many times
the round trip and nothing slips. Nothing in the binary monitor can count
what was missed — it has no cycle or frame counter, and the jiffy belongs
to the KERNAL IRQ, which is exactly what a music player takes over — so the
warning says which regime the log came from instead of offering a frame
number it cannot stand behind.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
from pathlib import Path

from .daemon_client import DaemonMonitorClient
from .monitor import MonitorError
from .session import audio_pin_path

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

#: The SID register block, `$D400-$D418`: read whole, once per frame, in a
#: single 25-byte request. `regs[0]` is `$D400`.
SID_BASE = 0xD400
SID_REGISTERS = 25

#: The fastest frame rate a supported machine has at real time (NTSC 60; PAL
#: is 50). The sampling loop takes at most one sample per frame, so an
#: observed rate above this is proof the session is running faster than real
#: time — the only regime in which the loop drops frames.
REALTIME_MAX_FPS = 60.0
#: Slack on that comparison, so a machine at exactly real time never warns.
WARP_RATE_MARGIN = 1.05

#: Wall-clock the sampling loop allows itself per requested frame, and its
#: floor. Real time a frame costs 1/60 s, so this is ~15x headroom; the
#: budget exists to bound a machine that has stopped advancing, not to pace
#: a healthy one.
SID_LOG_FRAME_BUDGET = 0.25
SID_LOG_MIN_TIMEOUT = 15.0

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

    @staticmethod
    def _listening_port(mon) -> int | None:
        """The port of a text monitor THIS session already has open, or None.

        `MonitorServerAddress` alone proves nothing: it ships with a factory
        default of `ip4://127.0.0.1:6510` on a session that has never run a
        text monitor, so trusting it points every session at 6510 — where
        only the first VICE to bind wins and every other session's client
        silently drives that emulator instead (reproduced live: two
        sessions, one listener, both clients connected to it). It is
        `MonitorServer == 1` that says the listener is ours and open.
        """
        try:
            if int(mon.resource_get("MonitorServer")) != 1:
                return None
            found = _ADDRESS.search(str(mon.resource_get("MonitorServerAddress")))
        except (MonitorError, KeyError, ValueError, TypeError):
            return None
        return int(found.group(1)) if found else None

    @classmethod
    def open(cls, session) -> _TextMonitor:
        with session.monitor() as mon:
            try:
                port = cls._listening_port(mon)
                if port is None:
                    port = _free_port()
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
        wedged VICE in 2 of 3 attempts; with it, 8 of 8 were clean.

        The reply to `x` is read before the shutdown, not left in the
        receive queue: closing a socket with unread data sends an RST rather
        than a FIN, which is the likeliest mechanism behind the wedge (one
        was reproduced here after a command had already timed out — VICE
        left halted, its text monitor answering nothing, so the binary
        monitor's resume never lands).
        """
        try:
            self._send("x")
            self._drain()
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


def _read_speed(session) -> int:
    with session.monitor() as mon:
        try:
            return int(mon.resource_get(SPEED))
        finally:
            mon.resume()


def _write_speed(session, percent: int) -> None:
    with session.monitor() as mon:
        try:
            mon.resource_set(SPEED, int(percent))
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

    All or nothing: until this returns, nobody holds the state needed to
    undo a half-applied pin, so a failure part way through rolls back what
    landed before it re-raises. Warp is cleared LAST for the same reason —
    the step most likely to fail (two binary-monitor round trips over the
    daemon, where a `TimeoutError` has been seen live) happens while the
    machine is still in the state the caller handed us.
    """
    text = _TextMonitor.open(session)
    try:
        warp = text.warp_state()
        speed = _read_speed(session)
        try:
            _write_speed(session, REALTIME_SPEED)
            if warp:
                text.set_warp(False)
        except Exception:
            _unpin_best_effort(session, text, warp, speed)
            raise
    finally:
        text.close()
    return {"warp": warp, "speed": speed}


def _unpin_best_effort(session, text: _TextMonitor, warp: bool,
                       speed: int) -> None:
    """Undo a partly-applied pin. Best effort by definition: it runs while
    something is already failing, and that first failure is the one worth
    raising, so a failed undo is swallowed rather than masking it."""
    for undo in (lambda: _write_speed(session, speed),
                 lambda: text.set_warp(True) if warp else None):
        try:
            undo()
        except Exception:
            pass


def restore_speed(session, saved: dict) -> None:
    """Put back what `pin_realtime` saved: `Speed` always, warp only when it
    was on (re-warping a session that was never warped would be a change,
    not a restore)."""
    _write_speed(session, int(saved.get("speed", REALTIME_SPEED)))
    if saved.get("warp"):
        text = _TextMonitor.open(session)
        try:
            text.set_warp(True)
        finally:
            text.close()


# --- per-frame SID logging ---------------------------------------------------

def sid_log(session, frames: int, jsonl_path, timeout: float | None = None) -> int:
    """Log the SID's registers once per video frame; returns frames written.

    The pinned surface the capture orchestrator calls. `sid_log_detail` is
    the same capture with the numbers a front end reports (and the warning a
    front end must show) — this one answers the only question a composing
    caller has.
    """
    return sid_log_detail(session, frames, jsonl_path, timeout)["frames"]


def sid_log_detail(session, frames: int, jsonl_path,
                   timeout: float | None = None) -> dict:
    """`sid_log` with its measurements: `{path, frames, requested, seconds,
    fps, warning}`, where `warning` is None or a line the caller must show.

    The file is one JSONL `FrameRecord` per frame — `{"frame": n, "regs":
    [25 ints]}`, `regs[0]` being `$D400` — and nothing else. No header, no
    trailing note, not even the warning: `sid_analysis.parse_log` raises on
    any line that is not a frame record.

    Frame numbers count from 0 and are the captured frames, which are the
    elapsed frames as long as a round trip is short against a frame. At real
    time it is, by a wide margin (200 of 201 elapsed frames measured);
    warped the two are comparable and a frame can go missing (200 of 202),
    which is what the warning is for — a compressed timeline must not pass
    for an exact one.

    **A `None` warning is not evidence of an exact timeline.** The warning
    is a one-sided test: it fires when sampling *outran* real time, which
    only a warped session can do. It cannot fire for a warped session that
    sampled slowly — a loaded host, a busy daemon — where the machine still
    ran ~9.7x and most frames went unrecorded. Only pinning real time makes
    the timeline exact, so `fps` (the measured sampling rate, frames per
    wall-clock second) is returned for a caller that pinned: assert it is
    near the machine's frame rate and the log is confirmed, not assumed.

    The machine is left RUNNING, with exactly one resume after the final
    sample and no round trip after that: the log's last record is the last
    frame this function is accountable for, and the machine free-runs from
    there. Samples only exist while it runs, and every binary-monitor
    command halts it.
    """
    frames = int(frames)
    if frames < 1:
        raise ValueError(f"frames must be at least 1, got {frames!r}")
    path = _abs(jsonl_path)
    budget = (float(timeout) if timeout is not None
              else max(SID_LOG_MIN_TIMEOUT, frames * SID_LOG_FRAME_BUDGET))
    started = time.monotonic()
    with session.monitor() as mon:
        samples = _sample_frames(mon, frames, budget)
    seconds = time.monotonic() - started
    if not samples:
        # Reachable only when the deadline had already passed at loop entry:
        # both loops run at least one iteration otherwise. A machine that
        # cannot advance does NOT land here — a checkpoint-parked one hands
        # back a resume immediately and fills a full log with identical
        # frames instead (which the rate warning then blames on warp).
        raise AudioError(
            f"sampled no SID frames: the {budget:g}s budget was already spent "
            f"when sampling began — `timeout` must be positive")
    Path(path).write_text("".join(
        json.dumps({"frame": n, "regs": list(regs)}, separators=(",", ":")) + "\n"
        for n, regs in enumerate(samples)))
    rate = len(samples) / seconds if seconds > 0 else float("inf")
    warning = _sid_log_warning(len(samples), frames, rate)
    if warning is not None:
        print(f"c64: {warning}", file=sys.stderr)
    return {"path": path, "frames": len(samples), "requested": frames,
            "seconds": seconds, "fps": rate, "warning": warning}


def _sample_frames(mon, frames: int, timeout: float) -> list[bytes]:
    """Daemon-side loop when there is a daemon, client-side when there is
    not — `ops.run_until`'s shape, for `ops.run_until`'s reason: a per-frame
    RPC costs about 0.5 s, which would make a 50-frame log take half a
    minute. A pre-sid_log daemon answers ValueError; take the local loop.

    Each branch leaves the machine running on its own, so the caller adds no
    resume of its own: a second one would cost a round trip and let two more
    unlogged frames pass after the final record."""
    if isinstance(mon, DaemonMonitorClient):
        try:
            return mon.sid_log(frames, timeout)
        except ValueError:
            pass
    return _sample_frames_client(mon, frames, timeout)


def _sample_frames_client(mon, frames: int, timeout: float) -> list[bytes]:
    """The loop the daemon runs on its own VICE connection, here on a direct
    one. Deliberately not the `$D012` poll the plan called for: see this
    module's docstring — every halt is at raster line 12, so the wrap that
    was meant to mark a frame never happens, while the halt itself already
    is the frame boundary."""
    deadline = time.monotonic() + timeout
    out: list[bytes] = []
    try:
        while len(out) < frames and time.monotonic() < deadline:
            mon.resume()
            out.append(mon.memory_read(SID_BASE, SID_REGISTERS))
    finally:
        mon.resume()      # left running, exactly as the daemon loop leaves it
    return out


def _sid_log_warning(written: int, requested: int, rate: float) -> str | None:
    """The one thing the JSONL cannot say for itself: that its frame numbers
    may not be the machine's.

    One-sided by design (a sampling rate can prove the machine outran real
    time, never that it did not) — `sid_log_detail` returns the rate for the
    caller who needs the other half.
    """
    if written < requested:
        return (f"sid log timed out after {written} of {requested} frames; "
                f"raise the timeout, or check that the machine is running")
    if rate <= REALTIME_MAX_FPS * WARP_RATE_MARGIN:
        return None
    return (f"sampled {rate:.0f} frames/s, faster than real time (a machine "
            f"at 1x runs at most {REALTIME_MAX_FPS:g} frames/s): this session "
            f"is warped, where an emulated frame is about as short as one "
            f"sampling round trip, so a frame can be dropped between records "
            f"(200 samples covered 202 elapsed frames when measured on an "
            f"idle host, and more slip under load) and the "
            f"log's frame numbers count captured frames, not elapsed ones. "
            f"Pin real time first (c64lib.audio.pin_realtime, `c64 audio "
            f"record --start`, or a capture through c64_audio_capture): at 1x "
            f"a frame is many times the round trip, and every frame landed")


# --- start/stop as the front ends use them -----------------------------------

def _pin_path(session) -> Path:
    """Where a pinned recording remembers what to restore. Start and stop
    are separate processes for the CLI, so the saved state outlives neither
    unless it is on disk; a sidecar beside the session record is how this
    codebase already keeps per-session scratch state (`<name>.respawns`).
    `Session.stop()` clears it, which is why the path is defined in
    `session.py` — see `audio_pin_path` there for the naming constraint.
    """
    return audio_pin_path(session.name)


def _write_pin(session, state: dict) -> None:
    """Record the pin, stamped with the pid it belongs to."""
    _pin_path(session).write_text(json.dumps({**state, "pid": session.pid}))


def _read_pin(session) -> dict | None:
    """The pin this session is holding, or None.

    A sidecar from a *different* pid is stale — the session it described is
    gone (killed, crashed, or stopped before its recording did) and this
    name has been reused. Honouring it would restore a dead machine's warp
    onto a new one, which is the very thing `restore_speed` refuses to do.
    Prune it instead, the way `Session._load_all()` prunes dead records.
    """
    path = _pin_path(session)
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text())
        pid = state["pid"]
    except (OSError, ValueError, TypeError, KeyError) as e:
        # Not silent: an unreadable pin means nobody will unpin the session,
        # so it may still be sitting at real time with warp off.
        print(f"c64: audio pin {path} is unreadable ({e}); the session may "
              f"still be unwarped — restart it if audio timing matters",
              file=sys.stderr)
        path.unlink(missing_ok=True)
        return None
    if pid != session.pid:
        path.unlink(missing_ok=True)
        return None
    return state


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
    _write_pin(session, {**saved, "wav": path})
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
