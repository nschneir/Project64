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

`capture` composes all of it — pin, record, log, disarm, restore, report —
and it rests on one fact that had never been measured with a sampler halting
the machine alongside the recorder: VICE's WAV writer paces on EMULATED time,
not wall clock. **This docstring is the one home for that measurement.** The
front ends (`c64 audio capture --help`, `c64_audio_capture`) and
`docs/cli.md` carry the cost a caller has to budget for and name this
docstring for the evidence behind it, so there is one place to correct when
it is re-measured.

The run (2026-08-04, NTSC session, a BASIC loop holding one gated triangle
with `$D400/$D401` = 7218): 120 frames requested, 120 logged, 2.000 s of
emulated time, a 2.0887 s WAV (100256 frames of 48 kHz 16-bit mono), 6.19 s
of wall clock. Had the recorder paced on wall clock it would have had to
account for the ~4.1 s the machine never generated.

Checked against the audio and not only its length. Those registers predict
7218 * 1022727 / 2**24 = 440.0041 Hz (A4 +0.016 cents), and the WAV's
dominant partial fell in the FFT bin holding that prediction — bin 919 of
0.4788 Hz bins over the 2.0887 s window, where the prediction sits at bin
919.02. The agreement is therefore within the measurement's own resolution
(±0.94 cents), which is all a single bin can say, and it is decisive against
a uniform stretch to 6.19 s, which would put the tone near 148 Hz, some 610
bins away.

The instrument is `sid_analysis.dominant_partial_hz` — one rFFT over the
whole mono mixdown, DC excluded — so that number is re-derivable from this
repo rather than from a probe script that no longer exists. `c64 audio
report --peak-hz` is the same measurement from the command line.

Filling wall clock instead of stretching it is excluded by the DURATION, not
by the spectrum: the file is 2.0887 s, so it holds no 4.1 s of padding or
repeats to find. (Repeats would smear the partial too; silence-padding would
leave it exactly where it is, which is why the length carries that half of
the argument.)

What that establishes is RATE alignment: the WAV and the log share a time
base, so a duration or a pitch read off the two together means something. It
is not OFFSET alignment. The WAV covers a little more emulated time than the
log does — the machine free-runs from the resume that arms the recorder until
the sampling loop's first halt, and again from the last sample until the
recorder is disarmed — and only the SUM of those two windows was measured,
never the split between them. A WAV timestamp therefore maps to a log frame
only to within that bracket, which is ONE-signed: the WAV strictly contains
the log window, so a log frame sits somewhere in [0, +0.103 s] into the WAV,
never before it. Nothing here depends on the offset; anything that
cross-reads the piano roll against the spectrogram would, and would need the
head measured first.

The bracket, as WAV duration minus the log's frames over the frame rate:
0.1013 s at 0.5 s; 0.0860, 0.1027, 0.0860, 0.0860 s across four 1 s captures;
0.0887 s at 2 s. It does not scale with capture length — as expected of round
trips — but the spread within one length (0.0860 to 0.1027 s at 1 s) is as
wide as the spread across lengths, so these six points are jitter-dominated:
they support "not proportional to the capture" and cannot exclude a small
proportional term.
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

#: The KERNAL jiffy clock, `$A0-$A2` most-significant byte first — the only
#: counter of EMULATED time the binary monitor can reach. VICE's binary
#: monitor has no cycle or frame counter of its own (see the module
#: docstring); the text monitor's register line does carry a cycle
#: `STOPWATCH`, and it is deliberately not used here: reading it costs a
#: text-monitor open, and at real time that round trip is worth several
#: frames of the very lead-in it would be measuring.
JIFFY_BASE = 0xA0
JIFFY_BYTES = 3
#: What the KERNAL runs the jiffy at, on BOTH machines: reset sets CIA 1
#: timer A to 16421 cycles on PAL and 17045 on NTSC, and each divides its
#: clock to 60.00 Hz. So it is a clock, not a frame counter — 1.2 ticks per
#: frame on PAL — and a lead-in in frames goes through seconds, never
#: straight across. (`basic_lint`'s W160 rests on the same 60.00.)
JIFFY_HZ = 60.0
_JIFFY_WRAP = 1 << (8 * JIFFY_BYTES)
#: A lead-in longer than this is not a lead-in: the jiffy is being used by
#: the program as ordinary zero-page storage, and the delta is somebody
#: else's data. Ten emulated minutes against an arming that costs a fraction
#: of an emulated second, so it excludes garbage without ever cutting off a
#: real measurement — including a warped session's, where the same wall
#: clock buys ~10x the emulated frames.
_MAX_LEAD_IN_JIFFIES = round(JIFFY_HZ * 600)
#: The sampling loop's own first resume, which happens after the last jiffy
#: read and produces log frame 0. It is counted rather than measured because
#: measuring it would cost another round trip — i.e. another frame.
_LEAD_IN_LOOP_FRAMES = 1

#: The fastest frame rate a supported machine has at real time (NTSC 60; PAL
#: is 50). The sampling loop takes at most one sample per frame, so an
#: observed rate above this is proof the session is running faster than real
#: time — the only regime in which the loop drops frames.
REALTIME_MAX_FPS = 60.0
#: Slack on that comparison, so a machine at exactly real time never warns.
WARP_RATE_MARGIN = 1.05

#: Wall clock the sampling loop allows itself per requested frame, and its
#: floor.
#:
#: NOT the ~15x headroom that 0.25 s against a 1/60 s frame would suggest:
#: 1/60 s is an EMULATED frame and this budget is wall clock, which is the
#: conflation three fix rounds went into removing elsewhere. A pinned frame
#: costs a monitor round trip — 45.5 ms on the canonical 200-frame log (200
#: samples over 9.1 s of wall clock) — so the real headroom is
#: 0.25 / 0.0455 = 5.5x: that log needs 9.1 s against its 50 s budget. Still
#: ample for what the budget is for, which is bounding a machine that has
#: stopped advancing rather than pacing a healthy one.
SID_LOG_FRAME_BUDGET = 0.25
SID_LOG_MIN_TIMEOUT = 15.0

#: Sanity ceiling on a single log. Nothing composes anywhere near it — a 30 s
#: capture is ~1500 frames (~37 KB) — but the whole log is held in memory as
#: one list on the daemon side and travels back as ONE base64 RPC line, and
#: both scale with this number, as does the default budget. At the ceiling
#: that is 36000 frames: 10 minutes of NTSC, ~900 KB of registers, a ~1.2 MB
#: response line, and a 2.5-hour budget. Past it the request is a bug, not a
#: capture.
MAX_SID_LOG_FRAMES = 36_000

_ADDRESS = re.compile(r"ip4://127\.0\.0\.1:(\d+)")
_WARP_STATE = re.compile(r"Warp mode is (on|off)\.")


class AudioError(RuntimeError):
    """A capture could not be armed, or warp could not be cleared."""


class PinnedStopError(AudioError):
    """What `pinned_record_stop` raises when a half of it fails, carrying
    WHICH: `restore_error` and `disarm_error` hold the underlying exceptions
    (None for a half that succeeded), and `wav_complete` says whether the
    capture WAV was confirmed closed and finalized despite them. `capture`
    branches on that field — complete evidence survives a failed restore;
    incomplete evidence is fatal — where it used to infer the same from
    whether the pin sidecar was still on disk, an inference the
    both-halves-failed case fooled."""

    def __init__(self, restore_error: BaseException | None = None,
                 disarm_error: BaseException | None = None, *,
                 wav_complete: bool):
        self.restore_error = restore_error
        self.disarm_error = disarm_error
        self.wav_complete = wav_complete
        parts = []
        if restore_error is not None:
            parts.append(f"the restore failed "
                         f"({type(restore_error).__name__}: {restore_error})")
        if disarm_error is not None:
            parts.append(f"the recorder would not disarm "
                         f"({type(disarm_error).__name__}: {disarm_error})")
        parts.append("the recording is complete on disk" if wav_complete else
                     "the recording could not be confirmed complete")
        super().__init__("; ".join(parts))


def parse_frame_writes(specs) -> dict[int, list[tuple[int, int]]]:
    """`--at-frame N 'ADDR=VAL[,ADDR=VAL…]'` tokens as `{frame: [(addr, val)]}`.

    `specs` is an iterable of `(frame, spec)` pairs — Click's `nargs=2`
    option tuples, and the MCP tool's `{frame: spec}` items — so both front
    ends read one parser and cannot drift. Numbers are `ops.parse_number`'s:
    decimal, `$d404`, or `0xd404`.

    Repeats of a frame MERGE, in the order given, because two `--at-frame 6`
    flags mean two writes at frame 6 and not "the second one wins". Order
    inside a frame is preserved for the same reason a poke sequence has one:
    the gate bit is normally written after the frequency.

    Every rejection here is a mistake that would otherwise be found after
    the capture window closed, which is the most expensive moment for it.
    """
    from .ops import parse_number

    out: dict[int, list[tuple[int, int]]] = {}
    for raw_frame, raw_spec in specs:
        try:
            frame = parse_number(raw_frame)
        except ValueError as e:
            raise ValueError(f"frame {raw_frame!r} is not a number ({e})") from e
        if frame < 0:
            raise ValueError(f"frame {frame} must be at least 0: writes are "
                             f"scheduled against the log's own frame numbers, "
                             f"which count from 0")
        for token in str(raw_spec).split(","):
            addr_s, sep, val_s = token.partition("=")
            if not sep or not addr_s.strip():
                raise ValueError(
                    f"--at-frame needs ADDR=VAL, got {token.strip()!r}: "
                    f"e.g. '$d404=$11' or '53280=1,53281=0'")
            try:
                addr, value = parse_number(addr_s), parse_number(val_s)
            except ValueError as e:
                raise ValueError(f"{token.strip()!r} is not a number "
                                 f"({e}); use decimal, $hex, or 0xhex") from e
            if not 0 <= addr <= 0xFFFF:
                raise ValueError(f"address {addr} in {token.strip()!r} is "
                                 f"outside 0-65535")
            if not 0 <= value <= 0xFF:
                raise ValueError(f"value {value} in {token.strip()!r} is "
                                 f"outside 0-255: a write is one byte")
            out.setdefault(frame, []).append((addr, value))
    return out


def _check_frame_writes(writes, frames: int) -> None:
    """Refuse a schedule the window cannot reach — before anything is pinned.

    `_check_reference`'s reasoning applied to the other pre-window mistake: a
    frame number past the end of the log is a capture that spends its whole
    real-time window doing exactly nothing it was asked to do, and says so
    only afterwards.
    """
    late = sorted(f for f in (writes or {}) if f >= frames)
    if late:
        raise ValueError(
            f"--at-frame {late[0]} is outside this capture's window: it logs "
            f"frames 0-{frames - 1}. Ask for a longer capture, or aim the "
            f"write earlier")


def _read_jiffy(session) -> int | None:
    """The machine's own emulated-time counter, or None if it cannot be read.

    Best effort by construction: this exists to REPORT what a capture cost,
    and a measurement must never be the reason a capture fails, so every
    failure below becomes a None that `capture` reports as "not measured".
    """
    try:
        with session.monitor() as mon:
            try:
                raw = bytes(mon.memory_read(JIFFY_BASE, JIFFY_BYTES))
            finally:
                # resume, not release: the capture needs the machine running,
                # and every binary-monitor command halts it.
                mon.resume()
    except Exception:                       # noqa: BLE001 - see the docstring
        return None
    return int.from_bytes(raw, "big") if len(raw) == JIFFY_BYTES else None


def _lead_in_frames(before: int | None, after: int | None,
                    fps: float) -> int | None:
    """Emulated frames between two jiffy readings, plus the loop's own resume.

    None rather than a guess whenever the jiffy cannot answer. The frozen
    case is the one that matters: the jiffy is incremented by the KERNAL's
    IRQ handler, and a music player that takes the IRQ over — which is most
    of them — stops it dead. A capture of such a program reports no lead-in;
    it does not report a plausible zero, and it does not report the 15 frames
    somebody else measured on some other program.
    """
    if before is None or after is None:
        return None
    delta = (after - before) % _JIFFY_WRAP        # 24 bits, ~77 hours
    if not 0 < delta <= _MAX_LEAD_IN_JIFFIES:
        return None
    return round(delta / JIFFY_HZ * fps) + _LEAD_IN_LOOP_FRAMES


def _abs(path) -> str:
    """Absolute, but not resolved: VICE only needs a rooted path, and
    following symlinks would hand back `/private/tmp/...` for a `/tmp/...`
    the caller asked for."""
    return os.path.abspath(os.path.expanduser(str(path)))


def _free_port() -> int:
    """A port nothing is listening on right now.

    Racy by construction, and knowingly so: the port is bound, read back and
    released here, then handed to VICE a few round trips later. Two sessions
    opening their text monitors at the same moment can draw the same number,
    and the loser then binds nothing and connects to the WINNER's listener —
    silently driving another emulator for the rest of its life, which is the
    `MonitorServerAddress` default-port failure in miniature (see
    `_listening_port`). The ephemeral range makes that about 1 in 16000 per
    concurrent pair, and closing it properly needs VICE to report the port it
    actually bound, which the resource interface does not offer.

    Left as a documented hazard rather than a guard because the pattern is
    codebase-wide — `session.py`'s VICE monitor port is drawn the same way —
    so a local fix here would buy a false sense of coverage.
    """
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
    #: Re-sends of the bare `warp` query when its reply does not arrive. One,
    #: because one was always enough: 39 of 39 measured stalls answered the
    #: first re-send, and the second attempt that was configured alongside it
    #: never fired. See `warp_state`, which is the only thing that reads this.
    _READBACK_RETRIES = 1

    #: How long the socket must stay quiet before a matched reply is taken as
    #: the newest one. See `_await`.
    _SETTLE = 0.05

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
        """The LAST match in the reply window, or None.

        Last, not first, and this is the point of the `_SETTLE` pause: the
        pre-send `_drain` bounds its own wait at 50 ms, so a reply VICE
        withheld from the PREVIOUS command can still be sitting in the kernel
        buffer when the next one goes out — and `warp_state`'s re-send is a
        measured, deliberate source of exactly that (the withheld line turns
        up only once more input is written). Matching the first thing that
        parses would hand the previous command's answer back as this one's.
        So a match starts a short quiet timer instead of returning, and any
        fresher match supersedes it.

        What that does NOT do is give this channel a sequence boundary. VICE
        emits its prompt asynchronously and repeatedly, so nothing positional
        is trustworthy here and replies are matched by content — which cannot
        distinguish two identical lines. It closes the stale-reply window; it
        does not make the channel ordered.
        """
        deadline = time.monotonic() + self._REPLY_TIMEOUT
        buf = ""
        found: re.Match[str] | None = None
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return found
            self._sock.settimeout(left)
            try:
                data = self._sock.recv(4096)
            except OSError:
                return found                # timed out, or the socket failed
            if not data:
                return found                # clean EOF
            buf += data.decode("ascii", "replace")
            matches = list(pattern.finditer(buf))
            if matches:
                found = matches[-1]
                # Bounded from the FIRST match, not reset per match: this is a
                # settle window, not an open-ended wait for a better answer.
                deadline = min(deadline, time.monotonic() + self._SETTLE)

    def warp_state(self) -> bool:
        """True when warp is on. A bare `warp` is the only readback of live
        warp state VICE 3.10 has.

        The query is RE-SENT once when no reply arrives, and that retry is
        load-bearing — do not simplify it away. VICE does not lose this
        reply, it withholds it until more input arrives on the socket:
        measured 2026-08-04/05 (see
        `.superpowers/sdd/2026-08-02-sid-audio-verification/wedge-investigation.md`
        for the wire traces), the missing `Warp mode is on.` line turned up
        only after the next byte was written, and a run with the timeout
        raised to 30 s waited the full 30.1 s and still got nothing. So
        waiting longer does not work; asking again does. Across 240
        pin/unpin cycles the first reply was missing 39 times and a single
        re-send rescued 39 of 39, ~50 ms each, with no session lost. All 39
        were the `warp on` confirmation `set_warp` makes from
        `restore_speed`; the `warp off` readback `pin_realtime` makes never
        stalled once in the same measurement. (`pinned_record_stop` now
        re-warps while the recorder is still armed, keeping its restore out
        of the window those 39 lived in; this retry stays as the defense for
        every other path through `restore_speed`.)

        Re-sending is safe because a bare `warp` is a pure query — it reports
        state and changes none — so the worst a duplicate costs is one extra
        prompt echo and one extra state line. The echo `_send`'s drain
        swallows; the state line is why `_await` takes the LAST match rather
        than the first, so a duplicate cannot be read as the NEXT command's
        answer.

        Without it the raise below tears the socket down mid-stall and that
        session's text monitor stops answering for the rest of its life:
        10 of 1663 opens (0.60%) in the un-retried population, every one of
        them fatal to the session's audio.
        """
        # Bounded, not open-ended: two attempts, each capped by the same
        # `_REPLY_TIMEOUT` the single attempt used, so a monitor that has
        # genuinely stopped answering still fails in ~6 s instead of hanging.
        for _ in range(1 + self._READBACK_RETRIES):
            try:
                self._send("warp")
            except OSError as e:
                # `_await` reports a clean EOF exactly as it reports a
                # timeout, so a retry can find itself writing to a socket the
                # peer has already closed. Retrying was pointless there and
                # `sendall`'s bare error would say nothing about the readback;
                # this does.
                raise AudioError(f"VICE's text monitor closed the connection "
                                 f"while its warp state was being read: "
                                 f"{e}") from e
            found = self._await(_WARP_STATE)
            if found is not None:
                return found.group(1) == "on"
        raise AudioError("VICE's text monitor did not report a warp state, "
                         "twice: the query was re-sent once and neither reply "
                         "arrived")

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
                   timeout: float | None = None, *, writes=None) -> dict:
    """`sid_log` with its measurements: `{path, frames, requested, seconds,
    sample_rate_hz, warning}`, where `warning` is None or a line the caller
    must show.

    `writes` is `{frame: [(addr, value), …]}` — memory writes performed at
    named frames of the window, which is what `c64 audio capture --at-frame`
    schedules. They land while the machine is HALTED, immediately before the
    resume that runs that frame, so frame N is the first LOGGED frame whose
    registers show their effect. Nothing else can reach the machine while a
    capture is open — the daemon runs the whole loop on one round trip — so
    a short effect is reachable this way and no other.

    The file opens with a one-line clock stamp — `{"machine", "clock_hz",
    "fps"}`, taken from the session's own model — and is otherwise one JSONL
    `FrameRecord` per frame: `{"frame": n, "regs": [25 ints]}`, `regs[0]`
    being `$D400`. Nothing else. No trailing note, and not the warning:
    `sid_analysis.parse_log` skips the stamp and raises on any other line
    that is not a frame record.

    The stamp is what lets `c64 audio report` re-score a log months later
    without a session to name the machine — the same registers are A4 on
    NTSC and G#4 +35 cents on PAL, so a re-score that assumed PAL renamed
    every note of an NTSC capture and looked plausible doing it.

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
    against ~425/s warped for that same 200-frame log.

    The warning's own ceiling is FIXED at `REALTIME_MAX_FPS` (60, the fastest
    supported machine) times `WARP_RATE_MARGIN`, so it fires above 63/s and
    nowhere else. On a PAL session that leaves a real gap: 50 to 63 samples a
    second is already proof the machine was not running at 50 fps, and
    nothing here says so. A caller that knows the machine model should apply
    that model's frame rate as its own ceiling — always as a falsifier, never
    as a target.

    `sample_rate_hz` is None when the whole log fit inside the clock's
    resolution — a rate no wall clock here can express, so there is no number
    to report and the warning has to say it in words.

    The machine is left RUNNING, with exactly one resume after the final
    sample and no round trip after that: the log's last record is the last
    frame this function is accountable for, and the machine free-runs from
    there. Samples only exist while it runs, and every binary-monitor
    command halts it.
    """
    frames = int(frames)
    if frames < 1:
        raise ValueError(f"frames must be at least 1, got {frames!r}")
    if frames > MAX_SID_LOG_FRAMES:
        # Bounded in code, not by convention: the daemon holds the whole log
        # in memory and returns it as one line. See MAX_SID_LOG_FRAMES.
        raise ValueError(
            f"frames must be at most {MAX_SID_LOG_FRAMES}, got {frames}: the "
            f"whole log is held in memory and returned in one response, and "
            f"{MAX_SID_LOG_FRAMES} frames is already about ten minutes of "
            f"emulated time")
    _check_frame_writes(writes, frames)
    path = _abs(jsonl_path)
    budget = (float(timeout) if timeout is not None
              else max(SID_LOG_MIN_TIMEOUT, frames * SID_LOG_FRAME_BUDGET))
    with session.monitor() as mon:
        # Timed inside the connection: opening and closing it is session
        # overhead, and folding that into the rate would drag short logs down
        # against the same ceiling a long one is judged by.
        started = time.monotonic()
        samples = _sample_frames(mon, frames, budget, writes)
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
    # Spelled out rather than filtered from `report_timing_for`: this is a
    # FILE FORMAT, and it must not gain a field because the timing dict did.
    # `sid_analysis.log_timing` reads exactly these three back, and
    # `test_sid_log_stamp_does_not_disturb_the_frame_records` is the round
    # trip that keeps the writer and the reader honest about it.
    clock = report_timing_for(session.model)
    stamp = {"machine": clock["machine"], "clock_hz": clock["clock_hz"],
             "fps": clock["fps"]}
    Path(path).write_text(
        json.dumps(stamp, separators=(",", ":")) + "\n"
        + "".join(
            json.dumps({"frame": n, "regs": list(regs)},
                       separators=(",", ":")) + "\n"
            for n, regs in enumerate(samples)))
    # None, never an infinity: this dict is `c64 --json audio sidlog` and the
    # MCP result, and `json.dumps` spells a float infinity `Infinity`, which
    # is not JSON. Reachable only if the whole log fit inside the clock's
    # resolution — which the warning then has to phrase without a number.
    rate = len(samples) / seconds if seconds > 0 else None
    warning = _sid_log_warning(len(samples), frames, rate)
    if warning is not None:
        # Library code writing to stderr, deliberately: the controller's rule
        # for this feature is "return payload AND stderr", because a warning
        # about a timeline nobody can see has to reach a human even when the
        # caller only looks at `frames`. It is also in the return value, so a
        # programmatic caller loses nothing. If it ever has to be silenced,
        # move the print to `cli.py` and `mcp_server.py` and let this dict be
        # the single source — do not add a `quiet=` flag here.
        print(f"c64: {warning}", file=sys.stderr)
    return {"path": path, "frames": len(samples), "requested": frames,
            "seconds": seconds, "sample_rate_hz": rate, "warning": warning}


def _sample_frames(mon, frames: int, timeout: float,
                   writes=None) -> list[bytes]:
    """Daemon-side loop when there is a daemon, client-side when there is
    not — `ops.run_until`'s shape, for `ops.run_until`'s reason: a per-frame
    RPC costs about 0.5 s, which would make a 50-frame log take half a
    minute. A pre-sid_log daemon answers ValueError; take the local loop.

    `writes` travels WITH the loop for the same reason the loop is one RPC:
    a client that stepped in at frame N to poke would spend two round trips
    doing it, and at real time that is frames the log never sees. A daemon
    too old for scheduled writes answers ValueError from the `sid_log_at`
    method it does not have, and the fallback below performs them properly
    rather than dropping them — a silently unaimed capture is worse than a
    slow one.

    Each branch leaves the machine running on its own, so the caller adds no
    resume of its own: a second one would cost a round trip and let two more
    unlogged frames pass after the final record."""
    if isinstance(mon, DaemonMonitorClient):
        try:
            return mon.sid_log(frames, timeout, writes=writes)
        except ValueError:
            pass
    return _sample_frames_client(mon, frames, timeout, writes)


def _sample_frames_client(mon, frames: int, timeout: float,
                          writes=None) -> list[bytes]:
    """The loop the daemon runs on its own VICE connection, here on a direct
    one. Deliberately not the `$D012` poll the plan called for: see this
    module's docstring — every halt is at raster line 12, so the wrap that
    was meant to mark a frame never happens, while the halt itself already
    is the frame boundary.

    A scheduled write goes out BEFORE the resume that runs its frame, so the
    frame runs with the value in place and the read that follows samples what
    it left behind: frame N is the first logged frame showing the effect."""
    deadline = time.monotonic() + timeout
    scheduled = dict(writes or {})
    out: list[bytes] = []
    try:
        while len(out) < frames and time.monotonic() < deadline:
            for addr, value in scheduled.get(len(out), ()):
                mon.memory_write(addr, bytes([value]))
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
        # Three causes reach here and only two of them are the caller's: the
        # budget ran out, the machine stopped advancing, or the daemon saw
        # this client go away mid-log and stopped (daemon.py `_sid_log`).
        # Naming the third is what keeps the advice honest — "raise the
        # timeout" is no help to a Ctrl-C'd capture.
        return (f"sid log stopped after {written} of {requested} frames; "
                f"raise the timeout, check that the machine is running, or — "
                f"if the command was interrupted — run it again")
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
        raw = path.read_text()
    except OSError as e:
        # KEPT, not deleted. This failure says nothing about the file's
        # contents — a permission problem, a full or flaky filesystem — so the
        # restore state is very likely still intact and still the only record
        # of what to put back. Deleting it here would turn a transient error
        # into a permanently unpinnable session.
        print(f"c64: audio pin {path} could not be read ({e}); it is left in "
              f"place, so `c64 audio record --stop` can try again once the "
              f"cause is fixed. Until then the session may still be unwarped",
              file=sys.stderr)
        return None
    try:
        state = json.loads(raw)
        if not isinstance(state, dict):
            raise TypeError(f"a JSON {type(state).__name__}, not an object")
    except (ValueError, TypeError) as e:
        # Content, not access: nothing here is recoverable, and leaving it
        # would re-report the same complaint on every later command.
        print(f"c64: audio pin {path} is unreadable ({e}); the session may "
              f"still be unwarped — restart it if audio timing matters",
              file=sys.stderr)
        path.unlink(missing_ok=True)
        return None
    if "pid" not in state:
        # Written before the pid stamp existed. The file is perfectly
        # readable — it just cannot be matched to a session, which is the
        # whole point of the stamp — so this is an upgrade, not corruption,
        # and it must not be reported as "unreadable".
        print(f"c64: audio pin {path} predates the session-pid stamp, so it "
              f"cannot be shown to belong to this session; discarding it "
              f"rather than restoring a stranger's warp. Restart the session "
              f"if its audio timing matters", file=sys.stderr)
        path.unlink(missing_ok=True)
        return None
    if state["pid"] != session.pid:
        path.unlink(missing_ok=True)
        return None
    return state


def _clear_pin(session) -> None:
    _pin_path(session).unlink(missing_ok=True)


def pinned_record_start(session, wav_path) -> dict:
    """Pin the machine to real time, then arm the recorder — the order both
    front ends need. A failure to arm unpins before it propagates, so a
    broken capture never leaves the session stuck at 1x.

    Pin FIRST is the measured-good order; do not flip it without new
    evidence. Arming before the pin was tried (2026-08-09) on the theory
    that it would close the sub-second real-time-no-consumer gap between
    the pin and the arm; its one live trial wedged the binary monitor, but
    a control run of THIS order minutes later wedged identically — the
    bursty, host-correlated timeout mode the wedge investigation left
    unattributed — so that trial is inconclusive, not a refutation. What
    IS measured: this order crossed the gap in ~500 pin/unpin cycles with
    zero binary-monitor wedges, every stall being the `warp on` readback
    that `_TextMonitor.warp_state`'s retry rescues, so there is no
    demonstrated upside to flipping and an undischarged risk in doing so
    (a recorder armed under warp may not survive the unwarp as a sound
    consumer). The arm-failure rollback below runs `restore_speed` inside
    the gap's window; the retry shields its readback too.

    The gap's *cause* is gone as of 2026-08-10, which is why the ordering
    question is now academic rather than urgent. This is the step the
    la-galaxia dogfood run found hanging every time, and its reproducer is
    a host reporting no audio output device (`ioreg -rc IOAudioDevice`
    counts 0 nodes, `system_profiler SPAudioDataType` comes back empty):
    warped work was untouched — builds, tests, 14 evidence captures,
    thousands of frame-stepped ticks — while every real-time operation
    wedged, and `audio record --start` is the first one a capture reaches.
    That upgraded the flow-control mechanism from hypothesis to confirmed:
    VICE's sound device paces the emulation loop at real time, so with
    coreaudio open on nothing, the buffer never drains and the loop stops
    answering its binary monitor. `Session.launch` now gives every headless
    session a sound device that needs no host consumer at all
    (`-sounddev dump -soundarg os.devnull` — see the comment there, which
    is also where the measurement against `dummy` lives), so the window
    this docstring is about no longer depends on anything outside VICE.
    The retry and the pin-first order stay: both are cheap, both are
    measured, and neither's evidence is superseded by removing the
    dependency."""
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


def _sink_path(session) -> Path:
    """Where a stop's throwaway sink recording lands: beside the pin sidecar,
    never in the caller's output directory, so a crash cannot leave a stray
    WAV among the capture artifacts."""
    return _pin_path(session).with_name(f"{session.name}.sink.wav")


def _wav_finalized(path) -> bool:
    """True when the header's RIFF and data sizes agree with the bytes on
    disk — what VICE's asynchronous close eventually patches in. Until then
    both fields hold the placeholder `llll` (0x6c6c6c6c), which `wave` reads
    as five hours of audio. Canonical 44-byte PCM header assumed, which is
    the one VICE writes (see WAV_HEADER_BYTES)."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            hdr = f.read(44)
    except OSError:
        return False
    if len(hdr) < 44:
        return False
    riff = int.from_bytes(hdr[4:8], "little")
    data = int.from_bytes(hdr[40:44], "little")
    return riff == size - 8 and data == size - 44


#: How long a stop waits for VICE to patch the WAV header after the recorder
#: closes. Measured at 33-55 ms over 40 closes while sound was live; the cap
#: is ~40x that, so hitting it means the close was never serviced at all.
_FINALIZE_TIMEOUT = 2.0


def _await_finalized(wav_path) -> None:
    """`record_stop`'s own contract — "confirm a stop by the file" — made
    real: VICE finalizes the header asynchronously, ~50 ms after the close is
    serviced, and the close is only serviced while the sound layer runs. A
    missing file is not waited for (the recorder never wrote; `capture`
    diagnoses that), but a header that never settles is refused: handing it
    on would present five hours of phantom audio as evidence."""
    if not os.path.exists(wav_path):
        return
    deadline = time.monotonic() + _FINALIZE_TIMEOUT
    while not _wav_finalized(wav_path):
        if time.monotonic() >= deadline:
            raise AudioError(
                f"VICE did not finalize {wav_path} within "
                f"{_FINALIZE_TIMEOUT:g}s: its header still disagrees with "
                f"its size, so the recording cannot be trusted yet. The "
                f"session was restored; the header lands when VICE next "
                f"services sound (or exits)")
        time.sleep(0.01)


def pinned_record_stop(session) -> dict:
    """Undo the pin, then disarm the recorder. Reports the WAV's size, which
    is the only honest evidence that the recording stopped and landed.

    The order — sink, restore, disarm — is the fix for two measured races,
    and both halves are load-bearing:

    - The recorder is the consumer draining VICE's sound device, which is
      the emulation loop's flow control at real time. A restore made with no
      consumer armed put the `warp on` readback where it stalled 39 times in
      240 measured pin/unpin cycles (0 in ~877 readbacks made with one; see
      `_TextMonitor.warp_state`). So something stays armed across the
      restore. (As of 2026-08-10 a headless session's playback device is a
      sink that always drains — see `Session.launch` — so that dependency
      is gone at the source for the sessions the front ends make. The sink
      dance stays: the second race below is not about the host device at
      all, and a windowed session still uses the host's.)
    - VICE finalizes a closed WAV asynchronously (~50 ms), and only while
      the sound layer is being serviced — a recorder disarmed under warp can
      leave the placeholder header on disk until the session exits. So the
      capture WAV is closed at real time, by re-arming the recorder onto a
      throwaway sink; the disarm that follows the restore closes only the
      sink, whose header nobody reads.

    The sink is best-effort: if it cannot be armed, the restore still runs
    (the readback retry stands guard) and the disarm closes the capture WAV
    itself — later than ideal, which is what the finalize check at the end
    is for.

    A failure of either half raises `PinnedStopError`, which names the half
    and whether the WAV is safe — both halves are always attempted, so a
    failed restore still disarms, and a failed restore leaves the pin on
    disk for a second `stop` to retry.
    """
    saved = _read_pin(session)
    wav = (saved or {}).get("wav")
    sink = None
    if saved is not None:
        try:
            record_start(session, _sink_path(session))
            sink = _sink_path(session)
        except Exception as e:
            print(f"c64: the throwaway sink recording could not be armed "
                  f"({type(e).__name__}: {e}); restoring anyway — the WAV "
                  f"will be finalized by the disarm instead", file=sys.stderr)
    restore_error: BaseException | None = None
    if saved is not None:
        try:
            # restore first, forget second: a restore that fails leaves the
            # pin on disk, so a second `stop` can try again rather than
            # stranding the session at 1x with nothing to put back.
            restore_speed(session, saved)
            _clear_pin(session)
        except Exception as e:
            restore_error = e
    disarm_error: BaseException | None = None
    try:
        record_stop(session)
    except Exception as e:
        disarm_error = e
    finally:
        if sink is not None:
            sink.unlink(missing_ok=True)
    if restore_error is not None or disarm_error is not None:
        # Confirm what can still be confirmed before reporting: the WAV is
        # closed if the sink took it over or the disarm went through, and
        # only a closed, finalized file may be called complete.
        complete = False
        if wav and os.path.exists(wav) and (sink is not None
                                            or disarm_error is None):
            try:
                _await_finalized(wav)
                complete = True
            except AudioError:
                pass
        raise PinnedStopError(restore_error, disarm_error,
                              wav_complete=complete)
    if wav:
        _await_finalized(wav)
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

#: A canonical PCM WAV header with no sample data — and the header VICE
#: writes: a 0.601 s capture came back as 57772 bytes, which is 28864 frames
#: of 48 kHz 16-bit mono (57728 bytes) plus exactly 44. A file this size or
#: smaller carries no audio at all, which is what a warped window produces.
WAV_HEADER_BYTES = 44

#: `write_report` is the authority on the verdict; this reads its answer back
#: rather than reimplementing the rule. The line is pinned by that function's
#: own tests.
_VERDICT = re.compile(r"^\*\*(PASS|FAIL)\*\*$", re.M)


def report_timing_for(model: str | None) -> dict:
    """`{"machine", "clock_hz", "fps", "clock_source"}` for a machine model,
    PAL for None.

    The one place a clock is chosen. Both numbers come from the machine
    profile table, never from a constant at a call site: a table built for
    the wrong machine transcribes every note about 65 cents out, which is a
    plausible-looking report rather than an error.

    `clock_source` says WHERE the choice came from — `"session"` when a model
    was named, `"default"` when nothing did — because the failure this whole
    field exists for is silent. A report that assumed PAL and one that was
    told PAL read identically otherwise, and only the first is a guess.
    """
    profile = get_profile(model or DEFAULT_REPORT_MODEL)
    return {"machine": profile.name, "clock_hz": profile.clock_hz,
            "fps": profile.fps,
            "clock_source": "session" if model else "default"}


def report_timing_from(log_path, model: str | None = None) -> dict:
    """The clock to read a log with: a named model first, then the log's own
    stamp, then PAL.

    The order is the point. `-s NAME` is an OVERRIDE — a caller who names a
    session means it — and everything else is the log speaking for itself.
    Before the stamp existed the only fallback was PAL, so a re-score run
    after the session had stopped silently renamed every note of an NTSC
    capture; `clock_source == "log"` is that failure made visible even when
    the answer is right.

    A stamp naming a machine this build does not have is ignored rather than
    trusted: `get_profile` is the authority on what a machine's clock is, and
    a hand-edited header must not be able to invent one.
    """
    if model:
        return report_timing_for(model)
    from .sid_analysis import log_timing
    try:
        stamped = log_timing(log_path)
    except OSError:
        stamped = None
    if stamped:
        try:
            return {**report_timing_for(stamped["machine"]),
                    "clock_source": "log"}
        except (KeyError, ValueError):
            pass
    return report_timing_for(None)


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
    import yaml

    # Imported here, not at module scope: this pulls in numpy and Pillow, and
    # `c64lib.cli` imports this module at startup. Measured on this host
    # 2026-08-04 with .venv/bin/python: `import c64lib.cli` 0.081 s, and
    # `import c64lib.sid_analysis` a further 0.080 s — doubling the startup of
    # every `c64` command for two of them.
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
    # After the metrics, not before: one of the anomaly checks reads a note the
    # log calls sounding against the levels the recording actually reached, so
    # the WAV has to have been measured first. Without one it is skipped and
    # every register-only check still runs.
    anomalies = sid_analysis.find_anomalies(events, records, fps=timing["fps"],
                                            metrics=metrics)

    roll = outdir / PIANO_ROLL
    sid_analysis.render_piano_roll(events, roll, timing["fps"])
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
        # Not derivable from `notes` alone: a log with no gated voice over a
        # WAV with audio in it is `$D418` sample playback, which the
        # transcription cannot see and this must not call silent. The rule
        # lives in `sid_analysis`, next to the report's own notice.
        "nothing_played": sid_analysis.nothing_played(events, metrics),
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


def _unpin_warning(error: PinnedStopError) -> str:
    """What a capture says when the stop failed but the recording is safe —
    it only fires on `wav_complete` reports, so it can claim the artifacts
    without hedging.

    Names the half that failed and the remedy that applies. A failed RESTORE
    leaves the pin sidecar on disk, so `c64 audio record --stop` is a real
    second chance rather than advice to restart. A failed disarm alone is a
    leftover, not a loss: the sink recorder it could not stop writes nothing
    under warp, and the next recording re-arms over it.
    """
    what = f"the session could not be unpinned ({error})"
    if error.restore_error is not None:
        return (f"{what}: the recording and the register log are on disk, "
                f"but the machine may still be at real time with warp off. "
                f"Run `c64 audio record --stop` on it to retry the unpin, "
                f"or restart the session")
    return (f"{what}: the artifacts are complete and the session was "
            f"restored; the leftover sink recorder writes nothing under "
            f"warp, and the next recording re-arms over it")


def _check_reference(ref_path) -> None:
    """Read the reference score BEFORE a capture window opens.

    `sid_report` reads it at the end, which is the right place there and the
    wrong one to find a typo: a capture holds the session at real time for a
    minute or more, and a score that cannot parse would cost all of it before
    the diff ever opened the file. The artifacts do survive that (`c64 audio
    report` re-runs the analysis over them), so this buys wall clock, not
    evidence.

    Deliberately `sid_analysis.load_score` and not a second parser: it is
    exactly what `diff_score` reads a reference through, so nothing can pass
    here and fail there. Entry contents are still the diff's to check.
    YAMLError is translated the way `sid_report` translates it.
    """
    import yaml

    from . import sid_analysis
    try:
        sid_analysis.load_score(ref_path)
    except yaml.YAMLError as e:
        raise AudioError(f"{ref_path} is not readable YAML ({e})") from e


def capture(session, seconds: float, outdir, ref_path=None, writes=None) -> dict:
    """Record the session's audio for `seconds` of EMULATED time and report.

    The end-to-end verification path: pin real time, arm the WAV recorder,
    log the SID registers for `round(seconds * fps)` frames, disarm, restore
    the session's speed and warp, then analyse both artifacts into
    `outdir/report.md`. Returns `sid_report`'s payload plus what the capture
    itself cost.

    `seconds` is emulated time, and wall clock is the larger number by far.
    The machine advances only while resumed, and the sampling loop resumes it
    one frame at a time, so a frame costs a round trip. Measured on an NTSC
    session (2026-08-04): 30 frames cost 2.44 s, 60 frames 3.55-3.70 s over
    four runs, and 120 frames 6.19 s — a least-squares fit through those six
    points is ~42 ms per frame on ~1.1 s of fixed cost. Budget for that rather
    than for `seconds`, and hold the session for the duration.

    `wall_clock_s` is that measurement's bracket exactly, and those figures
    are that field: it starts just before the pin and stops just after the
    unpin. It does NOT cover rendering the report — the whole command for the
    120-frame run took 6.32 s against the field's 6.19 s — nor attaching to
    the session, nor validating the arguments before it.

    `emulated_s` (the log's frames over the machine's frame rate) is what both
    artifacts cover; the WAV covers that plus a bracket of round trips at each
    end, and is rate-aligned to the log rather than offset-aligned — see this
    module's docstring, which is where that measurement lives.

    Everything the pin touches is restored on the way out, including from a
    failure mid-capture — `pinned_record_stop` unpins and disarms the recorder
    in one step, and it runs in a `finally`.

    A failed unpin is reported, not fatal, WHEN the evidence survived it —
    `pinned_record_stop` says which half failed and whether the WAV is
    complete, and a complete WAV means the report is still written and
    `unpin_error` carries the reason (also printed to stderr; a failed
    restore leaves the pin sidecar on disk for `c64 audio record --stop` to
    retry). It is None on every capture that put its session back. A caller
    that cares about the session's state afterwards — anything reusing it —
    must read that field; the verdict is about the audio, not the machine.

    An unpin that lost the evidence still raises: when the stop's throwaway
    sink never armed and the disarm failed too, the file still being written
    is the capture WAV — nothing complete to report a verdict on.

    Raises AudioError if VICE produced no WAV samples. That is not a flake to
    retry: under warp VICE writes a header and no frames at all, so an empty
    WAV means the capture window was not at real time. The register log is
    left in place either way.

    A `ref_path` is parsed before anything is pinned or armed — see
    `_check_reference` — so a malformed score costs no wall clock at all.
    `writes` is checked against the window in the same place and for the same
    reason.

    `writes` — `{frame: [(addr, value), …]}`, which `parse_frame_writes`
    builds from `--at-frame` — is the only way to make something happen
    INSIDE the window. Nothing outside may touch the session while it is
    open (the daemon runs the whole sampling loop on one round trip, and a
    second client would be waiting on it), and arming costs emulated frames
    before frame 0, so an effect shorter than that lead-in is otherwise over
    before the log starts. Frame N is the first logged frame that shows the
    write; see `sid_log_detail`.

    `lead_in_frames` is that cost, measured per capture rather than quoted:
    the KERNAL jiffy read before the pin against the jiffy read after the
    arm, converted through 60.00 Hz to the machine's frames, plus the
    sampling loop's own first resume. It is None when the jiffy cannot answer
    — a program that owns the IRQ freezes it — and it INCLUDES the two round
    trips it costs to take, which is a frame or so of the number it reports.
    Precision is about a frame either way: the jiffy quantizes to 1/60 s.
    """
    seconds = float(seconds)
    timing = report_timing_for(session.model)
    frames = round(seconds * timing["fps"])
    if frames < 1:
        raise ValueError(
            f"seconds must cover at least one frame: {seconds:g}s of a "
            f"{timing['fps']:g} fps machine rounds to {frames} frames")
    if ref_path is not None:
        # Before the pin, not after the window: see `_check_reference`.
        _check_reference(ref_path)
    _check_frame_writes(writes, frames)
    outdir = Path(_abs(outdir))
    outdir.mkdir(parents=True, exist_ok=True)
    wav, log = outdir / CAPTURE_WAV, outdir / CAPTURE_LOG

    started = time.monotonic()
    jiffy_before = _read_jiffy(session)
    pinned_record_start(session, wav)
    # The last look before the window: everything from here to frame 0 is
    # one resume, so this reading and the loop's own first resume bracket the
    # lead-in.
    jiffy_armed = _read_jiffy(session)
    unpin_error: str | None = None
    try:
        detail = sid_log_detail(session, frames, log, writes=writes)
    finally:
        try:
            recorded = pinned_record_stop(session)["bytes"]
        except PinnedStopError as e:
            # WHETHER the evidence survived decides whether this capture
            # does, and the stop's own report says so — it used to be
            # inferred from whether the pin sidecar was still on disk, an
            # inference the both-halves-failed case fooled.
            #
            # Incomplete -> the capture WAV is still being written (the sink
            # never armed and the disarm failed) or its header never
            # settled: nothing complete to judge. Re-raise.
            #
            # Complete -> the evidence is safe; only the machine's state is
            # in question. Report and carry on: a failed restore leaves the
            # sidecar for `c64 audio record --stop` to retry, and a failed
            # sink disarm is a leftover the next recording re-arms over.
            if not e.wav_complete:
                raise
            unpin_error = _unpin_warning(e)
            print(f"c64: {unpin_error}", file=sys.stderr)
            recorded = os.path.getsize(wav) if os.path.exists(wav) else None
    wall_clock = time.monotonic() - started

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
            # The frames the arming burned before frame 0 — None when the
            # machine's own clock could not answer. See this function's
            # docstring for what it is measured from and what it costs.
            "lead_in_frames": _lead_in_frames(jiffy_before, jiffy_armed,
                                              timing["fps"]),
            "log_warning": detail["warning"],
            "unpin_error": unpin_error}
