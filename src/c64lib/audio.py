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

`capture` composes all of it — pin, record, log, disarm, restore, report —
and it rests on one fact that had never been measured with a sampler running
alongside the recorder: VICE's WAV writer paces on EMULATED time, not wall
clock. Live on an NTSC session (2026-08-04, tone.bas holding one gated
triangle): 120 frames requested, 120 logged, 2.000 s emulated, a 2.089 s WAV,
6.19 s of wall clock. The recording follows the register log's timeline and
not the clock on the wall, which is what makes a pitch or a duration read off
the two together mean anything. Checked against the audio and not only its
length: those registers predict 439.98 Hz and the WAV's dominant partial
measured 439.99 Hz (0.1 cents), which a wall-clock-paced recording could not
give.

The WAV covers a little MORE emulated time than the log does, at both ends.
The machine free-runs from the resume that arms the recorder until the
sampling loop's first halt, and again from the last sample until the recorder
is disarmed. That bracket measured 0.086-0.101 s across captures of 0.5 s,
1 s, and 2 s — round trips, so it does not grow with the capture.

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
import wave
from pathlib import Path

from .daemon_client import DaemonMonitorClient
from .machines import get_profile
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
    sample_rate_hz, warning}`, where `warning` is None or a line the caller
    must show.

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
    ran ~9.7x and most frames went unrecorded. Pinning real time is what
    makes the timeline exact; no measurement here can substitute for it.

    `sample_rate_hz` is samples per second of **wall clock**, which is not
    the machine's frame rate and is not supposed to equal it. The emulator
    advances only while resumed, so a pinned 200-frame log is 200 emulated
    frames — 3.3 seconds of emulated time on the NTSC machine measured —
    spread over the 9.1 seconds of wall clock it took: ~22 samples/s from a
    ~60 Hz machine, and no contradiction between them. That is how "200
    samples over 201 elapsed frames" and "~22 samples/s" are both true of
    that one log, and it is why a rate above the frame rate is the only
    inference it supports: above it the machine cannot have been at real
    time (nothing samples more often than once per frame), while anything
    below is inconclusive. The pinned figure is host-dependent — round-trip
    latency sets it, not the emulator — so there is no fixed value to
    assert; the useful separation is the size of the gap, ~22/s pinned
    against ~425/s warped for that same 200-frame log. A caller that knows
    the machine model can apply a tighter ceiling than this module's fixed
    60 Hz — 50 on a PAL machine — but only ever as a falsifier.

    `sample_rate_hz` is None if the whole log fit inside the clock's
    resolution, which is a rate no wall clock here can express.

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
    with session.monitor() as mon:
        # Timed inside the connection: opening and closing it is session
        # overhead, and folding that into the rate would drag short logs down
        # against the same ceiling a long one is judged by.
        started = time.monotonic()
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
    # None, never an infinity: this dict is `c64 --json audio sidlog` and the
    # MCP result, and `json.dumps` spells a float infinity `Infinity`, which
    # is not JSON. Reachable only if the whole log fit inside the clock's
    # resolution — which the warning then has to phrase without a number.
    rate = len(samples) / seconds if seconds > 0 else None
    warning = _sid_log_warning(len(samples), frames, rate)
    if warning is not None:
        print(f"c64: {warning}", file=sys.stderr)
    return {"path": path, "frames": len(samples), "requested": frames,
            "seconds": seconds, "sample_rate_hz": rate, "warning": warning}


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


def _sid_log_warning(written: int, requested: int,
                     rate: float | None) -> str | None:
    """The one thing the JSONL cannot say for itself: that its frame numbers
    may not be the machine's.

    One-sided by design (a sampling rate can prove the machine outran real
    time, never that it did not) — `sid_log_detail` returns the rate for the
    caller who needs the other half. A `rate` of None means the log fit
    inside the clock's resolution, which is faster than any real-time machine
    can go and is said in words, there being no number to print.
    """
    if written < requested:
        return (f"sid log timed out after {written} of {requested} frames; "
                f"raise the timeout, or check that the machine is running")
    if rate is not None and rate <= REALTIME_MAX_FPS * WARP_RATE_MARGIN:
        return None
    how_fast = (f"sampled {rate:.0f} frames/s" if rate is not None else
                f"sampled all {written} frames inside the clock's resolution")
    return (f"{how_fast}, faster than real time (a machine at 1x runs at most "
            f"{REALTIME_MAX_FPS:g} frames/s): this session is warped, where an "
            f"emulated frame is about as short as one sampling round trip, so "
            f"a frame can be dropped between records (200 samples covered 202 "
            f"elapsed frames when measured warped on an idle host, and more "
            f"slip under load) and the log's frame numbers count captured "
            f"frames, not elapsed ones. "
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


# --- report and capture ------------------------------------------------------

#: The artifact names a capture writes into its output directory. Pinned: the
#: report links them by name, demo evidence scripts read them, and the skill
#: tells agents to look for exactly these.
CAPTURE_WAV = "capture.wav"
CAPTURE_LOG = "sid-log.jsonl"
PIANO_ROLL = "piano-roll.png"
SPECTROGRAM = "spectrogram.png"

#: The machine a report assumes when nothing names one. PAL is the C64 most
#: music was written for, and a report has to pick something: the clock is not
#: recoverable from a register log, and the two are ~65 cents apart.
DEFAULT_REPORT_MODEL = "c64pal"

#: A canonical PCM WAV header with no sample data. VICE writes exactly this
#: much and no more when it records under warp, so it is the size that says
#: "0 frames" rather than "quiet".
WAV_HEADER_BYTES = 44

#: `write_report` is the authority on the verdict; this reads its answer back
#: rather than reimplementing the rule. The line is pinned by that function's
#: own tests.
_VERDICT = re.compile(r"^\*\*(PASS|FAIL)\*\*$", re.M)


def report_timing_for(model: str | None) -> dict:
    """`{"machine", "clock_hz", "fps"}` for a machine model, PAL for None.

    The one place a clock is chosen. Both numbers come from the machine
    profile table, never from a constant at a call site: a table built for
    the wrong machine transcribes every note about 65 cents out, which is a
    plausible-looking report rather than an error.
    """
    profile = get_profile(model or DEFAULT_REPORT_MODEL)
    return {"machine": profile.name, "clock_hz": profile.clock_hz,
            "fps": profile.fps}


def sid_report(log_path, outdir, wav_path=None, ref_path=None, *,
               timing: dict) -> dict:
    """Analyse a captured SID log (and its WAV, if there is one) into a report.

    Pure analysis — no session, no monitor: parse the log, transcribe it with
    `timing`'s clock, diff it against `ref_path` when there is one, look for
    anomalies, render the piano roll (and the spectrogram, when there is
    audio), and write `report.md` into `outdir`. Returns the artifact paths,
    the verdict, and the findings behind it.

    `ref_path` is optional and *skipped*, not passed on as None: `diff_score`
    has no "no reference" mode. A run without one is the anomaly-and-render
    mode — every reference-free check still applies, and an empty diff list is
    a legitimate PASS.

    `wav_path` is optional for the same kind of reason: a register log alone
    is a real mode (`c64 audio sidlog` produces one), and `write_report`
    treats `metrics=None` as render-only rather than as a failure.
    """
    # Imported here, not at module scope: this pulls in numpy and Pillow, and
    # `c64lib.cli` imports this module at startup. Measured on this host
    # 2026-08-04 with .venv/bin/python: `import c64lib.cli` 0.081 s, and
    # `import c64lib.sid_analysis` a further 0.080 s — doubling the startup of
    # every `c64` command for two of them.
    import yaml

    from . import sid_analysis

    outdir = Path(_abs(outdir))
    outdir.mkdir(parents=True, exist_ok=True)
    records = sid_analysis.parse_log(log_path)
    events = sid_analysis.transcribe(records, timing["clock_hz"])
    try:
        # `if ref_path` and not `diff_score(events, ref_path)` with a None:
        # there is no "no reference" reference, and passing one raises a bare
        # AttributeError from inside the diff.
        diffs = sid_analysis.diff_score(events, ref_path) if ref_path else []
    except yaml.YAMLError as e:
        # Neither an OSError nor a ValueError, so it would reach a front end
        # as a traceback; a hand-written score is exactly where a typo lands.
        raise AudioError(f"{ref_path} is not readable YAML ({e})") from e
    anomalies = sid_analysis.find_anomalies(events, records)

    roll = outdir / PIANO_ROLL
    sid_analysis.render_piano_roll(events, roll, timing["fps"])
    metrics = spectrogram = None
    if wav_path is not None:
        try:
            metrics = sid_analysis.wav_metrics(wav_path)
            spectrogram = outdir / SPECTROGRAM
            sid_analysis.render_spectrogram(wav_path, spectrogram)
        except wave.Error as e:
            # Not an OSError and not a ValueError, so it would reach a front
            # end as a traceback: a truncated or non-RIFF file is a report.
            raise AudioError(f"{wav_path} is not a readable WAV ({e})") from e
    # After the renders: the report links the artifacts that exist beside it.
    report = sid_analysis.write_report(outdir, events, diffs, anomalies, metrics)

    verdict, failures = _read_verdict(report)
    return {
        "outdir": str(outdir), "report": str(report),
        "verdict": verdict, "failures": failures,
        "log": _abs(log_path), "wav": _abs(wav_path) if wav_path else None,
        "piano_roll": str(roll),
        "spectrogram": str(spectrogram) if spectrogram else None,
        "events": len(events),
        "notes": sum(1 for e in events if e.note != sid_analysis.REST),
        "diffs": diffs, "anomalies": anomalies,
        # Without the RMS profile: it is one number per 0.1 s of audio, which
        # is hundreds of floats in a payload an agent reads. `report.md` has
        # its min/median/max, and `sid_analysis.wav_metrics` has all of it.
        "metrics": ({k: v for k, v in metrics.items() if k != "rms_db_profile"}
                    if metrics is not None else None),
        **timing,
    }


def _read_verdict(report_path) -> tuple[str, list[str]]:
    """The verdict and its reasons, read back out of the written report.

    `write_report` owns the rule — no clipping, no anomalies, no diffs, no
    unexpected silence — and reimplementing it here is how the two drift
    apart. The verdict is the last section, so every `- ` line after it is one
    of its reasons.
    """
    text = Path(report_path).read_text()
    found = _VERDICT.search(text)
    if found is None:
        raise AudioError(f"{report_path} has no verdict line: the report was "
                         f"written, but it cannot be judged")
    return found.group(1), [line[2:] for line in text[found.end():].splitlines()
                            if line.startswith("- ")]


def capture(session, seconds: float, outdir, ref_path=None) -> dict:
    """Record the session's audio for `seconds` of EMULATED time and report.

    The end-to-end verification path: pin real time, arm the WAV recorder,
    log the SID registers for `round(seconds * fps)` frames, disarm, restore
    the session's speed and warp, then analyse both artifacts into
    `outdir/report.md`. Returns `sid_report`'s payload plus what the capture
    itself cost.

    `seconds` is emulated time, and wall clock is the larger number by far.
    The machine advances only while resumed, and the sampling loop resumes it
    one frame at a time, so a frame costs a round trip. Measured end to end on
    an NTSC session (2026-08-04), pin and report included: a 2 s capture — 120
    frames — cost 6.19 s of wall clock, and a 1 s capture 3.55-3.70 s over
    four runs. Budget for that rather than for `seconds`, and hold the session
    for the duration.

    `emulated_s` (the log's frames over the machine's frame rate) is what both
    artifacts cover; the WAV covers that plus a bracket of round trips at each
    end — see this module's docstring for the measurement.

    Everything the pin touches is restored on the way out, including from a
    failure mid-capture — `pinned_record_stop` disarms the recorder and unpins
    in one step, and it runs in a `finally`.

    Raises AudioError if VICE produced no WAV samples. That is not a flake to
    retry: under warp VICE writes a header and no frames at all, so an empty
    WAV means the capture window was not at real time. The register log is
    left in place either way.
    """
    seconds = float(seconds)
    timing = report_timing_for(session.model)
    frames = round(seconds * timing["fps"])
    if frames < 1:
        raise ValueError(
            f"seconds must cover at least one frame: {seconds:g}s of a "
            f"{timing['fps']:g} fps machine rounds to {frames} frames")
    outdir = Path(_abs(outdir))
    outdir.mkdir(parents=True, exist_ok=True)
    wav, log = outdir / CAPTURE_WAV, outdir / CAPTURE_LOG

    started = time.monotonic()
    pinned_record_start(session, wav)
    try:
        detail = sid_log_detail(session, frames, log)
    finally:
        # A failure to unpin replaces a failure to sample, which loses the
        # root cause (Python keeps it as __context__). Deliberate: a session
        # left at 1x with its recorder armed is the more urgent of the two,
        # and it is the one the next command will trip over.
        stopped = pinned_record_stop(session)
    wall_clock = time.monotonic() - started

    recorded = stopped.get("bytes")
    if recorded is None or recorded <= WAV_HEADER_BYTES:
        what = ("missing" if recorded is None else
                f"{recorded} bytes — a WAV header and no samples")
        raise AudioError(
            f"VICE recorded no audio: {wav} is {what}. Under warp VICE writes "
            f"a 0-frame WAV, so the capture window was not at real time — "
            f"check that nothing re-warped the session mid-capture. The "
            f"register log is still at {log}")

    out = sid_report(log, outdir, wav_path=wav, ref_path=ref_path, timing=timing)
    return {**out,
            "frames": detail["frames"], "requested_frames": frames,
            # Emulated time is what the WAV and the log both cover; wall clock
            # is what it cost. They are not the same number and the gap is
            # large — see this function's docstring.
            "emulated_s": detail["frames"] / timing["fps"],
            "wall_clock_s": wall_clock,
            "wav_bytes": recorded,
            "log_warning": detail["warning"]}
