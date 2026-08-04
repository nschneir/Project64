"""Pure analysis of captured SID register logs: transcription, diff, anomalies.

A capture writes one JSONL line per video frame holding the whole SID register
block (``$D400-$D418``). This module turns that log into something an agent can
check without ears: note events per voice, a diff against a reference score, and
a list of anomalies.

Nothing here talks to VICE — no session, monitor, or daemon imports — so every
function is testable from synthetic register logs.

Voice ``v`` (1-3) lives at ``$D400 + 7*(v-1)``: ``+0/+1`` frequency lo/hi,
``+4`` control (bit 0 = gate, bits 4-7 = waveform). The oscillator frequency is
``reg16 * clock_hz / 2**24``; the clock is always passed in, never assumed,
because it differs between PAL and NTSC machines.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import yaml

#: Registers per log line: the full ``$D400-$D418`` block.
LOG_REGISTERS = 25
#: Voices, in report order.
VOICES = (1, 2, 3)
#: The SID phase accumulator is 24 bits, so ``hz = reg16 * clock / 2**24``.
ACCUMULATOR_RANGE = 2**24

GATE_BIT = 0x01
WAVEFORM_MASK = 0xF0

#: Name of a stretch of frames with no audible pitch.
REST = "rest"

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_A4_HZ = 440.0
_A4_MIDI = 69

#: A gate held over a zero frequency for longer than this is a stuck gate: a
#: real note release drops the gate, and a real note has a frequency.
MAX_ZERO_FREQUENCY_FRAMES = 50
#: Beyond this a note is audibly out of tune rather than quantization noise.
MAX_CENTS_OFF = 15.0
#: Short detuned blips are slides and arpeggios, not tuning errors.
MIN_DETUNE_FRAMES = 25


@dataclass(frozen=True)
class FrameRecord:
    """One captured frame: ``regs[0]`` is ``$D400``."""

    frame: int
    regs: tuple[int, ...]


@dataclass(frozen=True)
class NoteEvent:
    """A run of frames on one voice that sounded the same pitch (or none).

    ``frames`` counts every frame in the run; ``gate_frames`` counts only those
    with the gate bit set, so a ``rest`` with ``gate_frames > 0`` is a gate held
    over silence. ``waveform`` is the control register's waveform bits (mask
    ``0xF0``) as of the run's first frame, and ``cents_off`` is the mean
    deviation from the equal-tempered pitch (``0.0`` for a rest).
    """

    voice: int
    note: str
    start_frame: int
    frames: int
    waveform: int
    gate_frames: int
    cents_off: float


def parse_log(path: str | Path) -> list[FrameRecord]:
    """Read a captured SID log (JSONL, one frame per line)."""
    records = []
    for number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            frame, regs = row["frame"], row["regs"]
            if len(regs) != LOG_REGISTERS:
                raise ValueError(f"{len(regs)} registers, expected {LOG_REGISTERS}")
            records.append(FrameRecord(frame=int(frame), regs=tuple(int(r) for r in regs)))
        except (KeyError, TypeError, ValueError) as exc:
            # JSONDecodeError is a ValueError, so every malformed line — bad
            # JSON, missing key, wrong shape — is reported with its line number.
            raise ValueError(f"{path}: line {number} is not a frame record ({exc})") from exc
    return records


def freq_to_note(hz: float) -> tuple[str, float]:
    """Nearest equal-tempered note name (A4 = 440 Hz) and the cents off it.

    Cents are signed: positive is sharp of the named note.
    """
    if hz <= 0:
        raise ValueError(f"frequency must be positive, got {hz!r}")
    midi = _A4_MIDI + 12 * math.log2(hz / _A4_HZ)
    nearest = round(midi)
    return f"{_NOTE_NAMES[nearest % 12]}{nearest // 12 - 1}", (midi - nearest) * 100


def transcribe(records: Sequence[FrameRecord], clock_hz: float) -> list[NoteEvent]:
    """Note events for all three voices, ordered by voice then start frame.

    Every frame belongs to exactly one event, rests included, so the events of a
    voice tile the whole log.
    """
    return [event for voice in VOICES for event in _transcribe_voice(records, voice, clock_hz)]


def diff_score(events: Sequence[NoteEvent], ref: Mapping | str | Path) -> list[str]:
    """Compare transcribed events against a reference score; empty means pass.

    ``ref`` is either a parsed score or a path to the reference YAML. Only the
    voices the score lists are compared, and comparison is positional: event *n*
    of a voice against entry *n* of that voice's list. ``frames`` is optional per
    entry — omit it to check the note but not its duration. Each slot yields at
    most one diff: a wrong note is not also reported as a wrong duration.

    Silence past the end of a voice's list is not a diff — that is where the
    capture window ended, not a mistake — so an empty list means "this voice
    should be silent" and a score need not predict its own trailing rest. An
    extra *sounding* note past the end still is a diff.
    """
    voices = _load_score(ref).get("voices")
    if not isinstance(voices, Mapping):
        raise ValueError("reference score has no 'voices' mapping")

    diffs = []
    for key in sorted(voices, key=int):
        voice = int(key)
        expected = list(voices[key] or [])
        heard = [e for e in events if e.voice == voice]
        for index in range(max(len(expected), len(heard))):
            label = f"voice {voice} event {index + 1}"
            if index >= len(heard):
                want = _reference_note(expected[index], label)
                diffs.append(f"{label}: expected {want}, heard nothing (log ended)")
                continue
            got = heard[index]
            if index >= len(expected):
                if got.note != REST:
                    diffs.append(
                        f"{label}: unexpected {got.note} at frame {got.start_frame} "
                        f"(reference lists {len(expected)} events)"
                    )
                continue
            want = _reference_note(expected[index], label)
            want_frames = expected[index].get("frames")
            if want != got.note:
                diffs.append(
                    f"{label}: expected {want}, heard {got.note} at frame {got.start_frame}"
                )
            elif want_frames is not None and int(want_frames) != got.frames:
                diffs.append(
                    f"{label}: {got.note} expected {int(want_frames)} frames, "
                    f"heard {got.frames} (frame {got.start_frame})"
                )
    return diffs


def find_anomalies(
    events: Sequence[NoteEvent], records: Sequence[FrameRecord]
) -> list[str]:
    """Reference-free checks for things no working tune does.

    A voice that never sounds is not one of them — silence is a legal
    arrangement, and only a reference score can say a voice should have played.
    """
    found = [f for voice in VOICES for f in _stuck_gates(records, voice)]
    found += [f for f in map(_detuned, events) if f is not None]
    found.sort(key=lambda f: f[:2])
    return [message for _, _, message in found]


# --- internals ------------------------------------------------------------

def _voice_state(regs: Sequence[int], voice: int) -> tuple[int, int]:
    """``(reg16, control)`` for a voice, from one frame's registers."""
    base = 7 * (voice - 1)
    return regs[base] | (regs[base + 1] << 8), regs[base + 4]


class _Sounded(NamedTuple):
    """What one voice was doing in one frame."""

    note: str
    gated: bool
    waveform: int
    cents_off: float


def _sounded(regs: Sequence[int], voice: int, clock_hz: float) -> _Sounded:
    reg16, control = _voice_state(regs, voice)
    gated = bool(control & GATE_BIT)
    waveform = control & WAVEFORM_MASK
    if not gated or reg16 == 0:
        # A gate held over a zero frequency sounds nothing, so it transcribes as
        # a rest; ``gate_frames`` keeps the evidence and _stuck_gates flags it.
        return _Sounded(REST, gated, waveform, 0.0)
    name, cents = freq_to_note(reg16 * clock_hz / ACCUMULATOR_RANGE)
    return _Sounded(name, gated, waveform, cents)


def _transcribe_voice(
    records: Sequence[FrameRecord], voice: int, clock_hz: float
) -> list[NoteEvent]:
    frames = [_sounded(r.regs, voice, clock_hz) for r in records]
    events = []
    start = 0
    while start < len(frames):
        note = frames[start].note
        end = start
        while end < len(frames) and frames[end].note == note:
            end += 1
        run = frames[start:end]
        events.append(NoteEvent(
            voice=voice,
            note=note,
            start_frame=records[start].frame,
            frames=len(run),
            waveform=run[0].waveform,
            gate_frames=sum(1 for f in run if f.gated),
            cents_off=0.0 if note == REST else sum(f.cents_off for f in run) / len(run),
        ))
        start = end
    return events


def _load_score(ref: Mapping | str | Path) -> Mapping:
    if isinstance(ref, (str, Path)):
        loaded = yaml.safe_load(Path(ref).read_text())
        if not isinstance(loaded, Mapping):
            raise ValueError(f"{ref}: reference score is not a YAML mapping")
        return loaded
    return ref


def _reference_note(entry: Mapping, label: str) -> str:
    try:
        return str(entry["note"]).strip()
    except (KeyError, TypeError) as exc:
        raise ValueError(f"reference {label} has no 'note': {entry!r}") from exc


def _stuck_gates(
    records: Sequence[FrameRecord], voice: int
) -> list[tuple[int, int, str]]:
    """Runs of frames where the gate is held but the frequency is zero."""
    found = []
    run_start, held = 0, 0

    def close() -> None:
        if held > MAX_ZERO_FREQUENCY_FRAMES:
            found.append((voice, run_start, (
                f"voice {voice}: gate held over a zero frequency for {held} frames "
                f"from frame {run_start} (stuck gate / zero-frequency drone)"
            )))

    for record in records:
        reg16, control = _voice_state(record.regs, voice)
        if control & GATE_BIT and reg16 == 0:
            if held == 0:
                run_start = record.frame
            held += 1
        else:
            close()
            held = 0
    close()
    return found


def _detuned(event: NoteEvent) -> tuple[int, int, str] | None:
    if (event.note == REST
            or event.frames < MIN_DETUNE_FRAMES
            or abs(event.cents_off) <= MAX_CENTS_OFF):
        return None
    return (event.voice, event.start_frame, (
        f"voice {event.voice}: {event.note} at frame {event.start_frame} is detuned "
        f"{event.cents_off:+.1f} cents for {event.frames} frames"
    ))
