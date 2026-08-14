"""Pure analysis of captured SID register logs and audio: transcription, diff,
anomalies, piano roll, WAV metrics, spectrogram, report.

A capture writes one JSONL line per video frame holding the whole SID register
block (``$D400-$D418``), plus a WAV of the same window. This module turns those
into something an agent can check without ears: note events per voice, a diff
against a reference score, a list of anomalies, two PNGs to look at, and a
markdown report with an overall verdict.

Nothing here talks to VICE — no session, monitor, or daemon imports — so every
function is testable from synthetic register logs and synthesized WAVs.

Voice ``v`` (1-3) lives at ``$D400 + 7*(v-1)``: ``+0/+1`` frequency lo/hi,
``+4`` control (bit 0 = gate, bits 4-7 = waveform). The oscillator frequency is
``reg16 * clock_hz / 2**24``; the clock is always passed in, never assumed,
because it differs between PAL and NTSC machines.
"""

from __future__ import annotations

import json
import math
import statistics
import wave
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

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

#: Waveform bits (control register bits 4-7), for report tables.
WAVEFORM_NAMES = {0x10: "triangle", 0x20: "sawtooth", 0x40: "pulse", 0x80: "noise"}
#: The noise bit. Noise is an LFSR clocked by the oscillator, so the frequency
#: register sets how BRIGHT the broadband output is and not what pitch it is —
#: there is no pitch to be out of tune with. Everything downstream that talks
#: about tuning (the detune check, the report's cents column) therefore has to
#: exclude it, and the bit is tested rather than the whole waveform compared:
#: a combined waveform with noise in it is not a clean tone either.
NOISE_WAVEFORM = 0x80

#: A gated note the recording says was inaudible for longer than this is
#: over-reported: the gate stayed on, but a sustain-zero envelope had already
#: decayed to nothing, so the piano roll draws a bar over silence.
#:
#: One second, which is four times ``MIN_SILENCE_S`` (a stretch shorter than
#: that is not even called silence) and ten times the ``RMS_WINDOW_S`` the
#: measurement is quantized to. It is deliberately far above any decay tail
#: worth calling normal: a silence window only exists when the whole MIX is
#: under ``SILENCE_DB``, so a plucked voice under a sounding arrangement can
#: never reach it, and a plucked voice alone would have to be inaudible for a
#: full second while still gated to be flagged. Against the capture this was
#: written for — the 8 s NTSC Invaders gameplay capture of 2026-08-02, whose
#: voice 1 transcribed a 290-frame (4.83 s at 60 fps) G2 while the WAV's
#: silence window ran 4.00 s to 8.11 s — the overlap is 4.11 s measured and
#: 3.91 s after the alignment slack below, nearly four times this threshold.
MIN_INAUDIBLE_S = 1.0
#: How far the WAV's zero and the log's frame 0 may disagree. The recorder and
#: the sampling loop share a time base but are started one after the other, so
#: the two agree on RATE exactly and on OFFSET only to about a frame. Silence
#: windows are shrunk by this at both ends before they are measured against a
#: note, which spends the uncertainty on not crying wolf.
SILENCE_ALIGNMENT_S = 0.1

# --- rendering -----------------------------------------------------------

#: One fixed colour per voice — pinned, so a piano roll from one demo can be
#: read against another's without checking a per-report legend mapping.
VOICE_COLORS = {1: (255, 64, 64), 2: (64, 220, 64), 3: (80, 120, 255)}
#: Neutral greys, so nothing but a voice bar is ever channel-dominant.
ROLL_BACKGROUND = (18, 18, 22)
ROLL_GRID = (52, 52, 58)
#: The rows `MAX_ROW_LABELS` leaves unnamed, ruled a step dimmer than the
#: labelled ones — see `render_piano_roll`.
ROLL_GRID_UNLABELLED = (32, 32, 37)
ROLL_TEXT = (208, 208, 212)

#: Pinned minimum size for both rendered PNGs.
MIN_IMAGE_WIDTH = 640
MIN_IMAGE_HEIGHT = 240
#: A long capture shares columns rather than producing a mile-wide PNG; bars
#: are still drawn at least one pixel wide, so no note vanishes.
MAX_ROLL_WIDTH = 4096
#: Semitones of headroom drawn above and below the notes actually present.
NOTE_RANGE_PADDING = 2
#: Below this a bar is too thin to see.
MIN_ROW_HEIGHT = 4
#: Roll chrome: note-name gutter, right/top padding, legend strip.
ROLL_GUTTER, ROLL_PAD, ROLL_LEGEND_HEIGHT = 48, 8, 36
#: Y labels are thinned to at most this many, so a wide range stays readable.
#: Every row is still ruled — the ones this cap skips in `ROLL_GRID_UNLABELLED`.
MAX_ROW_LABELS = 12

# --- audio ---------------------------------------------------------------

#: A sample at or above this fraction of the format's positive full scale is
#: clipped. Measured against the FORMAT's rail, not against 1.0, because PCM's
#: rails are not symmetric: signed formats have one more negative code than
#: positive (16-bit runs -32768 to +32767), and 8-bit unsigned maps 0-255 onto
#: -1.0 to +127/128 the same way. At 8 bits the positive rail is 0.9922, so a
#: flat 0.999 could never see positive full-scale clipping at all — the width
#: `SAMPLE_DTYPES` advertises but the live path (VICE records 16-bit) never
#: produces. Scaling 8-bit by 127.5 instead would centre the rails at the cost
#: of turning the format's own silence (the code 128) into a -48 dBFS DC
#: offset, which is the worse trade.
CLIP_THRESHOLD = 0.999
#: Resolution of the RMS profile, and therefore of silence detection.
RMS_WINDOW_S = 0.1
#: A window quieter than this counts as silence.
SILENCE_DB = -60.0
#: Silence shorter than this is a musical gap, not a dropout.
MIN_SILENCE_S = 0.25
#: How far the decoded samples may fall short of what the RIFF header claims
#: before `wav_metrics` calls the file truncated. One RMS window, because that
#: is the resolution silence is measured at: a shortfall under it cannot move a
#: window boundary, and the partial frame `_read_wav` drops is orders of
#: magnitude smaller again. Nothing the verdict computes rests on this
#: tolerance — `duration_s` is the DECODED length whether or not the flag fires.
TRUNCATION_TOLERANCE_S = RMS_WINDOW_S
#: Digital silence is -inf dBFS; floored so the profile stays JSON-serializable
#: (an MCP tool returns this dict, and `Infinity` is not valid JSON).
MIN_DB = -120.0
#: WAV sample widths in bytes -> numpy type. 8-bit WAV is unsigned by format.
SAMPLE_DTYPES = {1: "u1", 2: "<i2", 4: "<i4"}

#: STFT geometry.
FFT_WINDOW = 1024
FFT_HOP = 512
#: Column cap for the spectrogram, the piano roll's ``MAX_ROLL_WIDTH`` applied
#: to the other PNG. Past it the hop widens instead, so both the image and the
#: arrays behind it stay bounded whatever the capture's length.
#:
#: Arithmetic, at the 48 kHz mono VICE records. Uncapped a 60 s capture is
#: 2880000 samples, so (2880000 - 1024) // 512 + 1 = 5624 columns: a
#: 5624-pixel-wide PNG behind a 5624 x 1024 float64 block (46 MB) and its
#: 5624 x 513 complex128 rFFT (46 MB). At the cap those are 4096 x 1024
#: (33.6 MB) and 4096 x 513 (33.6 MB), and no capture can exceed them. The
#: widening starts once the uncapped count would pass 4096, which is
#: 4095 * 512 + 1024 = 2097664 samples — about 44 s at 48 kHz.
MAX_SPECTROGRAM_WIDTH = 4096
#: The SID's musical content lives well under this; higher bins are noise.
SPECTROGRAM_MAX_HZ = 8000.0
#: dB below the loudest bin that maps to the bottom of the ramp.
SPECTROGRAM_RANGE_DB = 80.0
#: Floor under the loudest bin that normalization is measured against, in the
#: STFT's own magnitude dB (not dBFS). Silence has no loudest bin worth scaling
#: to: without this, a recording of digital silence would normalize against
#: itself and fill the image with the *top* ramp stop, so the one failure this
#: tool exists to catch — a warped capture writing a silent WAV — would render
#: as the signature of loud broadband noise. A 16-bit signal at one LSB still
#: peaks near -42 dB here, so only degenerate silence ever reaches this floor.
SPECTROGRAM_FLOOR_DB = -60.0
#: Fixed ramp stops, so two spectrograms are comparable by eye: black at the
#: floor, through violet/magenta/orange, to near-white at the peak.
SPECTROGRAM_RAMP = (
    (0.00, (0, 0, 0)),
    (0.25, (40, 20, 110)),
    (0.50, (160, 40, 120)),
    (0.75, (240, 120, 40)),
    (1.00, (255, 250, 220)),
)

# --- report --------------------------------------------------------------

#: Report filename, and the capture artifacts it links when they are present.
REPORT_NAME = "report.md"
ARTIFACT_NAMES = ("capture.wav", "sid-log.jsonl", "piano-roll.png", "spectrogram.png")
#: Fraction of the recording that must be silent to call it silent overall.
ALL_SILENT_COVERAGE = 0.99


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

    ``note`` and ``cents_off`` describe the OSCILLATOR, which is only a pitch
    when the waveform is one. A noise event still carries both — the frequency
    register is real, it sets how bright the noise is, and the piano roll and
    the score diff are positioned by the name — but nothing may read its
    ``cents_off`` as tuning: see ``NOISE_WAVEFORM``.
    """

    voice: int
    note: str
    start_frame: int
    frames: int
    waveform: int
    gate_frames: int
    cents_off: float


def _register_byte(value) -> int:
    """One logged register: a whole number in 0-255, or a ValueError.

    A bare ``int(value)`` accepted anything numeric, and both ways it was
    wrong: a float truncated silently, and an out-of-range value corrupted
    the 16-bit frequency through ``regs[base + 1] << 8`` with no complaint
    anywhere downstream — a producer bug arriving as a plausible
    transcription. The wrong register COUNT is already a named parse error;
    this puts the register's VALUE on the same footing. ``bool`` is an
    ``int`` subclass, so it is excluded by name.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"register {value!r} is not an integer")
    if not 0 <= value <= 255:
        raise ValueError(f"register {value} is outside 0-255")
    return value


#: The keys a log's clock stamp carries, and the MINIMUM test for one: a first
#: line holding at least these is the header `c64lib.audio.sid_log_detail`
#: writes, extra keys and all. The test was equality once, and that made the
#: format unextendable — the day a fourth key is stamped, every parser already
#: shipped rejects line 1 of a new log, and rejects it as a malformed frame
#: record, a hard error naming the wrong thing. Missing keys still fail, so a
#: truncated or foreign line cannot pass as a header.
LOG_STAMP_KEYS = ("machine", "clock_hz", "fps")


def _log_stamp(line: str) -> dict | None:
    """The clock stamp in a log's first line, or None if it is not one.

    The one predicate both readers use: `log_timing` returns what this returns
    and `parse_log` skips the line this accepts, so stamp-ness cannot mean two
    things. What a superset costs is a line carrying all three stamp keys AND a
    frame record's own: no writer in this tree emits such a hybrid, and until
    one turns up, an "and not a frame record" clause here would be a guard
    against nothing.
    """
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict) or not set(LOG_STAMP_KEYS) <= set(row):
        return None
    return row


def log_timing(path: str | Path) -> dict | None:
    """The clock stamp a log was captured with — line 1 whole, extras and all —
    or None.

    A register log does not carry its clock in its records — the same
    `$D400/$D401` pair is A4 on the NTSC machine and G#4 +35 cents on PAL —
    so a capture stamps the machine it came from on line 1 and a re-score
    reads it back here instead of assuming PAL. None is what every log
    written before the stamp existed answers; `c64lib.audio.report_timing_from`
    is where that falls back.
    """
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        return _log_stamp(line)
    return None


def parse_log(path: str | Path) -> list[FrameRecord]:
    """Read a captured SID log (JSONL, one frame per line).

    A clock stamp on line 1 is skipped, not returned — `log_timing` is what
    reads it. Everywhere else the rule is unchanged: a line that is not a
    25-register frame record is an error naming its line number, which is
    what keeps a stray warning or a half-written log from being analysed.
    """
    records = []
    first = True
    for number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        stamp, first = (first and _log_stamp(line) is not None), False
        if stamp:
            # The FIRST content line only: a log has one header and it is at
            # the top. A stamp anywhere else falls through to the frame-record
            # parse and is reported there, rather than silently swallowing a
            # frame's worth of evidence.
            continue
        try:
            row = json.loads(line)
            frame, regs = row["frame"], row["regs"]
            if len(regs) != LOG_REGISTERS:
                raise ValueError(f"{len(regs)} registers, expected {LOG_REGISTERS}")
            records.append(FrameRecord(frame=int(frame),
                                       regs=tuple(_register_byte(r) for r in regs)))
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


def load_score(ref: Mapping | str | Path) -> list[tuple[int, list]]:
    """A reference score's voices as ``(voice, entries)`` pairs, in voice order.

    Everything `diff_score` checks about a score's *shape*, split out so it can
    be paid for before a capture rather than after one: `audio.capture` calls
    this before it opens its real-time window, where a typo would otherwise
    cost the whole window before the diff ever read the file. It is the same
    reader, not a second one, so nothing can pass here and fail there.

    Raises ValueError for a score that is not a mapping, one with no ``voices``
    mapping, a voice that is not a list of entries, or a voice key the SID does
    not have. That last one is why unknown keys are rejected rather than
    ignored: `diff_score` compares only the voices a score lists, so a typo'd
    ``4:`` would be compared against a voice with no events and report every
    entry under it as "heard nothing" — a wall of diffs blaming the program
    for a mistake in the reference. Entry contents are NOT checked here; a
    missing ``note`` is still `diff_score`'s to raise.
    """
    voices = _load_score(ref).get("voices")
    if not isinstance(voices, Mapping):
        raise ValueError("reference score has no 'voices' mapping")
    known = ", ".join(str(v) for v in VOICES)
    out = []
    for key, entries in voices.items():
        try:
            voice = int(key)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"reference score voice key {key!r} is not a voice number: "
                f"the SID's voices are {known}") from exc
        if voice not in VOICES:
            raise ValueError(
                f"reference score lists voice {voice}: the SID's voices are "
                f"{known}")
        out.append((voice, _voice_entries(entries, voice)))
    return sorted(out, key=lambda pair: pair[0])


def score_summary(ref: Mapping | str | Path) -> dict:
    """What a reference score claims, without a capture to check it against.

    A capture costs several times its emulated length in wall clock, so the
    arithmetic in a hand-written score — did I really list every event in the
    window? do the durations add up to the passage I meant? — should be
    checkable before spending one. This reads the score through `load_score`,
    the same and only reader, so nothing can summarise here and fail there.

    Returns ``{"voices": {"<voice>": {"entries", "frames", "first", "last"}},
    "entries", "frames"}``. Only the voices the score LISTS appear: an empty
    list is the positive claim "this voice sits out", and comes back with zero
    entries and ``None`` for its first and last note, while a voice the score
    omits claims nothing and is absent entirely — the same asymmetry
    `diff_score` compares by.

    ``frames`` is the sum of the durations actually present. An entry that
    omits ``frames`` — which is how the window's first and last notes are
    normally scored — counts toward ``entries`` and contributes nothing to
    ``frames``, so the two numbers disagreeing is information, not an error.

    Raises ValueError for everything `load_score` rejects, plus the two
    entry-level slips it deliberately leaves to `diff_score`: an entry with no
    ``note``, and a ``frames`` that is not a number. Catching those here is
    most of the point — after a capture they cost the window.
    """
    voices: dict[str, dict] = {}
    for voice, entries in load_score(ref):
        names: list[str] = []
        frames = 0
        for index, entry in enumerate(entries, 1):
            label = f"voice {voice} event {index}"
            names.append(_reference_note(entry, label))
            value = entry.get("frames")
            if value is None:
                continue
            try:
                frames += int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"reference {label} has a non-numeric 'frames': {value!r}"
                ) from exc
        voices[str(voice)] = {
            "entries": len(names),
            "frames": frames,
            "first": names[0] if names else None,
            "last": names[-1] if names else None,
        }
    return {
        "voices": voices,
        "entries": sum(v["entries"] for v in voices.values()),
        "frames": sum(v["frames"] for v in voices.values()),
    }


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

    Silence BEFORE the start of a voice's list is exempt the same way, and for
    the same reason: a free-running `sid_log` normally opens a few frames
    before the player's first gate, which is where the capture window began
    and not a mistake either. A leading rest is dropped before the positional
    comparison unless the score lists one, so the common case costs one
    skipped event instead of cascading a wrong-note diff onto every entry in
    the voice. Score a leading rest explicitly when its length is part of the
    claim — then it is compared like any other entry.

    The score is read through `load_score`, which is where every complaint
    about its shape — including a voice key the SID does not have — comes
    from.
    """
    diffs = []
    for voice, expected in load_score(ref):
        heard = _drop_unscored_leading_rest(
            [e for e in events if e.voice == voice], expected, voice)
        for index in range(max(len(expected), len(heard))):
            label = f"voice {voice} event {index + 1}"
            if index >= len(heard):
                shown = _expected_note(expected[index], label)[1]
                diffs.append(f"{label}: expected {shown}, heard nothing (log ended)")
                continue
            got = heard[index]
            if index >= len(expected):
                if got.note != REST:
                    diffs.append(
                        f"{label}: unexpected {got.note} at frame {got.start_frame} "
                        f"(reference lists {len(expected)} events)"
                    )
                continue
            want, shown = _expected_note(expected[index], label)
            want_frames = expected[index].get("frames")
            if want != got.note:
                diffs.append(
                    f"{label}: expected {shown}, heard {got.note} at frame {got.start_frame}"
                )
            elif want_frames is not None and int(want_frames) != got.frames:
                diffs.append(
                    f"{label}: {got.note} expected {int(want_frames)} frames, "
                    f"heard {got.frames} (frame {got.start_frame})"
                )
    return diffs


def find_anomalies(
    events: Sequence[NoteEvent],
    records: Sequence[FrameRecord],
    *,
    fps: float | None = None,
    metrics: Mapping | None = None,
) -> list[str]:
    """Reference-free checks for things no working tune does.

    A voice that never sounds is not one of them — silence is a legal
    arrangement, and only a reference score can say a voice should have played.

    ``fps`` and ``metrics`` are what a run with audio adds: given both, a note
    the register log says is sounding is checked against the levels the
    recording actually reached, which is the only way to catch a note that is
    gated but inaudible. Without them (a register-only run — `c64 audio
    sidlog` produces one) that check is skipped and every other one still
    applies; there is no WAV to contradict the log.
    """
    found = [f for voice in VOICES for f in _stuck_gates(records, voice)]
    found += [f for f in map(_detuned, events) if f is not None]
    if fps is not None and metrics is not None:
        found += _inaudible_notes(events, fps, metrics)
    found.sort(key=lambda f: f[:2])
    return [message for _, _, message in found]


def nothing_played(events: Sequence[NoteEvent], metrics: Mapping | None = None) -> bool:
    """Whether this capture caught no sound at all.

    True when no transcribed event sounds and — when there is a recording —
    the recording is silent too. This is not a failure: proving a program is
    quiet when it should be quiet is a real thing to want, and a reference
    score listing three empty voices is how you claim it. It is reported
    prominently anyway, because the same result is what a capture window that
    opened on the wrong screen, or on a program that never started, produces,
    and those must not read as "everything checks out".

    The recording has to agree before the notice fires. A log with no gated
    voice over a WAV with audio in it is not "nothing played" — that is
    sample playback driven through ``$D418``, which this transcription cannot
    see and must not deny.
    """
    if any(event.note != REST for event in events):
        return False
    return metrics is None or _all_silent(metrics)


def render_piano_roll(events: Sequence[NoteEvent], png_path: str | Path, fps: float) -> None:
    """Draw the transcription as a piano roll PNG.

    X is capture frames, Y is the MIDI note numbers present padded by
    ``NOTE_RANGE_PADDING`` semitones each way, and each gated note is a filled
    bar in its voice's pinned colour. Rests are left as background, so what the
    eye picks out is exactly what sounded. ``fps`` only labels the legend with
    the capture's duration in seconds — the drawing itself is in frames.

    Every semitone row is ruled, but only ``MAX_ROW_LABELS`` of them are named:
    over a wide range the names thin out to every second or third semitone, and
    the dim lines between them are how a bar the labels skip is still named —
    count rows from the nearest name. Without them a 33-semitone passage could
    only be read against the transcription table in ``report.md``.

    An empty (or all-rest) event list still renders: a labelled, empty grid is
    a truthful answer to "what played?", and downstream report links must not
    dangle.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps!r}")
    events = list(events)

    first_frame, last_frame = _frame_span(events)
    span = max(1, last_frame - first_frame)
    low_midi, high_midi = _midi_range(events)
    rows = high_midi - low_midi + 1

    row_height = max(MIN_ROW_HEIGHT,
                     math.ceil((MIN_IMAGE_HEIGHT - ROLL_PAD - ROLL_LEGEND_HEIGHT) / rows))
    plot_height = rows * row_height
    plot_width = min(MAX_ROLL_WIDTH - ROLL_GUTTER - ROLL_PAD,
                     max(MIN_IMAGE_WIDTH - ROLL_GUTTER - ROLL_PAD, span))
    width = plot_width + ROLL_GUTTER + ROLL_PAD
    height = plot_height + ROLL_PAD + ROLL_LEGEND_HEIGHT

    image = Image.new("RGB", (width, height), ROLL_BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    def x_of(frame: int) -> int:
        return ROLL_GUTTER + round((frame - first_frame) * plot_width / span)

    def y_of(midi: int) -> int:
        return ROLL_PAD + (high_midi - midi) * row_height

    # Every semitone gets a line; only every `label_stride`-th gets a name and
    # the brighter tone. The dim lines are what make the cap survivable: a bar
    # the labels skip is still countable off the nearest name, which is the
    # whole reading a reviewer does when the range is wider than twelve rows.
    label_stride = max(1, math.ceil(rows / MAX_ROW_LABELS))
    for midi in range(low_midi, high_midi + 1):
        labelled = (midi - low_midi) % label_stride == 0
        y = y_of(midi) + row_height - 1
        draw.line([(ROLL_GUTTER, y), (width - ROLL_PAD, y)],
                  fill=ROLL_GRID if labelled else ROLL_GRID_UNLABELLED)
        if labelled:
            draw.text((4, y - row_height + 1), _midi_name(midi), fill=ROLL_TEXT, font=font)

    for event in events:
        midi = _note_to_midi(event.note)
        if midi is None:   # a rest: leave the background showing
            continue
        left = x_of(event.start_frame)
        # At least one pixel wide: a long capture shares columns, and a short
        # note must still be visible rather than rounding away to nothing.
        right = max(left + 1, x_of(event.start_frame + event.frames)) - 1
        top = y_of(midi)
        draw.rectangle([left, top, right, top + row_height - 2],
                       fill=VOICE_COLORS[event.voice])

    legend_y = ROLL_PAD + plot_height + 10
    x = ROLL_GUTTER
    for voice in VOICES:
        draw.rectangle([x, legend_y, x + 9, legend_y + 9], fill=VOICE_COLORS[voice])
        draw.text((x + 14, legend_y), f"voice {voice}", fill=VOICE_COLORS[voice], font=font)
        x += 92
    draw.text((x, legend_y),
              f"frames {first_frame}-{last_frame} ({span / fps:.1f} s @ {fps:g} fps)",
              fill=ROLL_TEXT, font=font)

    image.save(png_path)


def wav_metrics(wav_path: str | Path) -> dict:
    """Level metrics for a captured WAV: clipping, silence, and an RMS profile.

    Returns ``duration_s``, ``header_duration_s``, ``truncated``,
    ``clipped_samples`` (samples at or above ``CLIP_THRESHOLD`` of the FORMAT's
    positive full scale — see that constant — counted across every channel
    before the mixdown, because clipping is a per-channel event),
    ``silence_windows`` (``(start_s, end_s)`` pairs) and ``rms_db_profile``
    (dBFS per ``RMS_WINDOW_S``).

    **``duration_s`` is the length of the samples this decoded, not the length
    the RIFF header claims**, and every other number here covers exactly that
    span. The two are the same for a finished recording and differ for one
    whose header outruns its data — which is not a corner case: VICE leaves
    both size fields at the placeholder ``llll`` until the recorder's close is
    serviced, `audio._await_finalized` waits that out on the capture path, and
    the re-score paths (`c64 audio report --wav`, MCP `c64_sid_report`) read
    whatever is on disk. Measuring coverage against the claim while measuring
    silence against the samples is what let 1 s of dead audio under a 30 s
    header clear ``ALL_SILENT_COVERAGE`` and report PASS.

    The claim is kept rather than discarded: ``header_duration_s`` is what the
    header says, and ``truncated`` is true when it exceeds the decoded length
    by more than ``TRUNCATION_TOLERANCE_S``. That disagreement is a finding in
    its own right — the artifact set is a partial recording of a run — so
    :func:`write_report` fails on it and names both figures.

    Silence is found on the RMS profile rather than on a separate sweep, so its
    resolution is the profile's: a run must cover enough whole windows to reach
    ``MIN_SILENCE_S``. Channels are averaged to mono first — a dropout in one
    channel of a stereo recording is a mix problem, not the SID's.
    """
    audio = _read_wav(wav_path)
    clipped = int(np.count_nonzero(
        np.abs(audio.samples) >= CLIP_THRESHOLD * audio.positive_full_scale))
    window = max(1, round(RMS_WINDOW_S * audio.rate))
    profile = [_rms_db(audio.mono[start:start + window])
               for start in range(0, len(audio.mono), window)]
    decoded_s = len(audio.mono) / audio.rate
    header_s = audio.frames / audio.rate
    return {
        "duration_s": decoded_s,
        "header_duration_s": header_s,
        "truncated": header_s - decoded_s > TRUNCATION_TOLERANCE_S,
        "clipped_samples": clipped,
        "silence_windows": _silence_windows(profile, window, len(audio.mono), audio.rate),
        "rms_db_profile": profile,
    }


def dominant_partial_hz(wav_path: str | Path) -> dict:
    """The loudest frequency in a recording, and how precise that answer is.

    Returns ``{"peak_hz", "bin_hz", "bin", "resolution_cents", "seconds"}``.
    One rFFT over the whole mono mixdown, no windowing and no averaging, so
    ``bin_hz`` is ``rate / samples`` and the answer is the centre of the bin
    that holds the partial — never a sub-bin estimate. ``resolution_cents`` is
    what half a bin is worth at that pitch, which is the tightest agreement
    this measurement can honestly claim.

    This exists because the branch's central alignment evidence — that VICE's
    WAV writer paces on emulated time, checked against the recording's PITCH
    and not only its length — was produced by an ad-hoc probe script that was
    deleted with its scratch WAV. ``wav_metrics`` reports levels and cannot
    produce a frequency, so nothing shipped could re-derive the number that
    argument rests on. Now `c64 audio report --peak-hz` can.

    DC is excluded: a recording with a level offset has no musical partial at
    0 Hz, and an offset is often the largest bin. Digital silence has no
    partial at all and answers ``peak_hz`` 0.0 with ``resolution_cents``
    ``None``.
    """
    audio = _read_wav(wav_path)
    if audio.frames < 1:
        raise ValueError(f"{wav_path}: no samples to measure")
    magnitude = np.abs(np.fft.rfft(audio.mono))
    magnitude[0] = 0.0
    index = int(np.argmax(magnitude)) if len(magnitude) > 1 else 0
    bin_hz = audio.rate / len(audio.mono)
    peak = index * bin_hz
    return {
        "peak_hz": peak,
        "bin_hz": bin_hz,
        "bin": index,
        "resolution_cents": (1200 * math.log2((peak + bin_hz / 2) / peak)
                             if peak > 0 else None),
        "seconds": len(audio.mono) / audio.rate,
    }


def render_spectrogram(wav_path: str | Path, png_path: str | Path) -> None:
    """Draw a log-magnitude STFT of a captured WAV as a PNG.

    ``FFT_WINDOW``-sample Hann windows at ``FFT_HOP``, X is time and Y is
    frequency from 0 Hz at the bottom to ``SPECTROGRAM_MAX_HZ`` at the top (or
    Nyquist, if the recording is sampled too low to reach it). Magnitudes are
    normalized against the loudest bin in this recording over
    ``SPECTROGRAM_RANGE_DB``, which makes a quiet capture readable at the cost
    of absolute levels — read those off ``wav_metrics`` instead.

    That relative scaling stops at ``SPECTROGRAM_FLOOR_DB``, so a silent
    recording renders black rather than normalizing its own noise floor up into
    a solid bright field. An agent reading this PNG has to be able to tell
    silence from noise, and silence is the failure most worth catching.

    A recording shorter than one window is zero-padded to one rather than
    refused: a single column is still a truthful picture of what was captured.

    A long one widens the hop instead of growing without limit: past
    ``MAX_SPECTROGRAM_WIDTH`` columns the windows are spaced further apart, so
    the time axis still spans the whole recording and neither the PNG nor the
    arrays behind it scale with its length. Windows never overlap less than
    they abut, so no audio is skipped.
    """
    audio = _read_wav(wav_path)
    mono = audio.mono
    if len(mono) < FFT_WINDOW:
        mono = np.pad(mono, (0, FFT_WINDOW - len(mono)))

    span = len(mono) - FFT_WINDOW
    hop = max(FFT_HOP, math.ceil(span / (MAX_SPECTROGRAM_WIDTH - 1)))
    starts = range(0, span + 1, hop)
    windowed = np.stack([mono[s:s + FFT_WINDOW] for s in starts]) * np.hanning(FFT_WINDOW)
    # +1e-12 keeps digital silence at a finite floor instead of -inf.
    decibels = 20 * np.log10(np.abs(np.fft.rfft(windowed, axis=1)) + 1e-12)

    top_bin = min(decibels.shape[1],
                  math.ceil(SPECTROGRAM_MAX_HZ * FFT_WINDOW / audio.rate) + 1)
    decibels = decibels[:, :top_bin]
    peak = max(float(decibels.max()), SPECTROGRAM_FLOOR_DB)
    normalized = np.clip((decibels - (peak - SPECTROGRAM_RANGE_DB)) / SPECTROGRAM_RANGE_DB, 0, 1)

    # Transpose to (frequency, time), then flip so low frequencies sit at the
    # bottom the way a spectrogram is conventionally read.
    image = Image.fromarray(_apply_ramp(normalized.T[::-1]), "RGB")
    if image.width < MIN_IMAGE_WIDTH or image.height < MIN_IMAGE_HEIGHT:
        # Nearest-neighbour: an interpolated resample would invent bins.
        image = image.resize((max(image.width, MIN_IMAGE_WIDTH),
                              max(image.height, MIN_IMAGE_HEIGHT)),
                             Image.Resampling.NEAREST)
    image.save(png_path)


def write_report(
    outdir: str | Path,
    events: Sequence[NoteEvent],
    diffs: Sequence[str],
    anomalies: Sequence[str],
    metrics: Mapping | None,
    *,
    ref: Mapping | str | Path | None = None,
) -> Path:
    """Write ``report.md`` into ``outdir`` and return its path.

    The verdict is PASS only when there are no score diffs, no anomalies, and —
    when a WAV was measured — the recording is whole (see ``truncated`` in
    :func:`wav_metrics`), unclipped, and not unexpectedly silent. ``metrics``
    of ``None`` is a render-only run (no audio captured), which is a legitimate
    outcome and not a failure; likewise an empty ``diffs`` list, which is what a
    run with no reference score produces.

    ``ref`` is the reference score those ``diffs`` came from — the path (or the
    parsed score) a caller handed :func:`diff_score`, and ``None`` for a run
    that was never scored. It is what the Score-diff section stands on: with it
    the section names the file and quotes what that score claims, and without
    it the section says outright that nothing was checked. Passing the diffs
    alone cannot express the difference, which is the bug — a committed report
    of an unscored run read exactly like a clean one.

    A capture in which nothing sounded at all passes on the same rule — there
    is nothing for a check to disagree with — but says so, under the verdict
    and again above the transcription. See :func:`nothing_played`.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    failures = _verdict_failures(events, diffs, anomalies, metrics)

    lines = ["# SID audio verification", ""]
    lines += _transcription_section(events)
    lines += _score_diff_section(diffs, ref)
    lines += _list_section("Anomalies", anomalies, "None found.")
    lines += _metrics_section(metrics)
    lines += _artifacts_section(outdir)
    lines += ["## Verdict", "", f"**{'FAIL' if failures else 'PASS'}**", ""]
    lines += _nothing_played_notice(events, metrics)
    lines += [f"- {reason}" for reason in failures] + ([""] if failures else [])

    path = outdir / REPORT_NAME
    path.write_text("\n".join(lines).rstrip() + "\n")
    return path


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


def _voice_entries(entries, voice: int) -> list:
    """One voice's reference list, or a ValueError naming what was there.

    `list(entries or [])` alone turns the commonest hand-editing slip — a
    scalar where a list belongs, `1: 5` — into a bare `TypeError`, while
    every other malformed shape in this module raises a descriptive
    `ValueError`. A string is rejected for the same reason: iterating it
    would silently yield one entry per character.
    """
    if entries is None:
        return []
    if isinstance(entries, (str, bytes, Mapping)) or not isinstance(entries, Sequence):
        raise ValueError(
            f"reference voice {voice} is not a list of note entries: {entries!r}")
    return list(entries)


def _drop_unscored_leading_rest(
    heard: list[NoteEvent], expected: Sequence, voice: int
) -> list[NoteEvent]:
    """Drop a leading rest the score does not claim — see `diff_score`.

    The score keeps its rest when it lists one: only an UNSCORED leading rest
    is the capture window opening early, and only that one is skipped.
    """
    if not heard or heard[0].note != REST:
        return heard
    if expected and _reference_note(expected[0], f"voice {voice} event 1") == REST:
        return heard
    return heard[1:]


def _reference_note(entry: Mapping, label: str) -> str:
    try:
        return str(entry["note"]).strip()
    except (KeyError, TypeError) as exc:
        raise ValueError(f"reference {label} has no 'note': {entry!r}") from exc


def _expected_note(entry: Mapping, label: str) -> tuple[str, str]:
    """`(pitch, how to show it)` for one reference entry.

    The pitch is respelled the way the transcription writes it, so `Ab4`
    matches the `G#4` it heard. The display keeps the score's own spelling
    and appends the transcription's when they differ — `Ab4 (= G#4)` — so a
    diff is still readable against the file the reader wrote, and the
    respelling is visible rather than something the reader has to know
    happened.
    """
    written = _reference_note(entry, label)
    pitch = spell_as_transcribed(written)
    return pitch, written if pitch == written else f"{written} (= {pitch})"


def _stuck_gates(
    records: Sequence[FrameRecord], voice: int
) -> list[tuple[int, int, str]]:
    """Runs of frames where the gate is held but the frequency is zero.

    Measured in ``record.frame`` deltas, not in records: a producer that drops
    frames would otherwise under-count a run against wall time, and
    ``MAX_ZERO_FREQUENCY_FRAMES`` would quietly mean something different for
    every log. On a gapless log the two are identical, which is the case the
    threshold was chosen against.
    """
    found = []
    run_start: int | None = None
    run_end = 0

    def close() -> None:
        if run_start is None:
            return
        held = run_end - run_start + 1
        if held > MAX_ZERO_FREQUENCY_FRAMES:
            found.append((voice, run_start, (
                f"voice {voice}: gate held over a zero frequency for {held} frames "
                f"from frame {run_start} (stuck gate / zero-frequency drone)"
            )))

    for record in records:
        reg16, control = _voice_state(record.regs, voice)
        if control & GATE_BIT and reg16 == 0:
            if run_start is None:
                run_start = record.frame
            run_end = record.frame
        else:
            close()
            run_start = None
    close()
    return found


def _is_noise(waveform: int) -> bool:
    """Whether a waveform has the noise bit in it — see ``NOISE_WAVEFORM``."""
    return bool(waveform & NOISE_WAVEFORM)


def _detuned(event: NoteEvent) -> tuple[int, int, str] | None:
    # Noise first, and on its own line, because it is exempt for a different
    # reason than the thresholds are: not "too small to matter" but "not a
    # pitch at all". While it fired, the commonest drum track there is failed
    # a capture for being "detuned +30.1 cents" — the register that sets the
    # LFSR's brightness read as a badly tuned F#4. See NOISE_WAVEFORM.
    if _is_noise(event.waveform):
        return None
    if (event.note == REST
            or event.frames < MIN_DETUNE_FRAMES
            or abs(event.cents_off) <= MAX_CENTS_OFF):
        return None
    return (event.voice, event.start_frame, (
        f"voice {event.voice}: {event.note} at frame {event.start_frame} is detuned "
        f"{event.cents_off:+.1f} cents for {event.frames} frames"
    ))


def _silent_overlap_s(start_s: float, end_s: float, window: Sequence[float]) -> float:
    """Seconds of ``start_s``-``end_s`` inside a silence window, less slack.

    The window is shrunk by ``SILENCE_ALIGNMENT_S`` at each end before the
    intersection, so an offset error between the WAV and the log can only ever
    shorten the overlap this reports, never invent one.
    """
    window_start, window_end = window
    return (min(end_s, window_end - SILENCE_ALIGNMENT_S)
            - max(start_s, window_start + SILENCE_ALIGNMENT_S))


def _inaudible_notes(
    events: Sequence[NoteEvent], fps: float, metrics: Mapping
) -> list[tuple[int, int, str]]:
    """Notes the log says are sounding while the recording says nothing is.

    The transcriber reads the gate, and a gate is not audibility: a
    sustain-zero ADSR envelope decays to nothing with the gate still held, so
    a voice can transcribe as one long note while the WAV under it is silent.
    That is a real over-report — the piano roll draws the bar to the edge —
    and neither the transcription nor ``_stuck_gates`` can see it, because
    every register involved is doing exactly what it was told.

    Frames become seconds against the FIRST frame in the events, not against
    frame 0: a log that opens at frame 3000 is 50 s into a session, not 50 s
    into this recording, and the WAV starts where the capture did.

    A recording that is silent END TO END is left alone. That is the warped
    or dead capture, ``_silence_failure`` already reports it once with the
    sentence that names the real cause, and turning it into one anomaly per
    note would bury that sentence under the symptom.
    """
    if fps <= 0:
        # Raised, not skipped. A frame rate this cannot divide by is a caller
        # bug, and swallowing it would delete a check silently — which is the
        # exact failure mode this check was added to close.
        raise ValueError(f"fps must be positive, got {fps!r}")
    windows = [tuple(window) for window in metrics.get("silence_windows") or []]
    if not windows or _all_silent(metrics):
        return []
    sounding = [event for event in events if event.note != REST]
    if not sounding:
        return []

    origin = min(event.start_frame for event in events)
    found = []
    for event in sounding:
        start_s = (event.start_frame - origin) / fps
        end_s = (event.start_frame + event.frames - origin) / fps
        seconds, window = max(
            ((_silent_overlap_s(start_s, end_s, w), w) for w in windows),
            key=lambda pair: pair[0])
        if seconds < MIN_INAUDIBLE_S:
            continue
        found.append((event.voice, event.start_frame, (
            f"voice {event.voice}: {event.note} at frame {event.start_frame} is "
            f"gated for {event.frames} frames ({start_s:.2f}-{end_s:.2f} s) but "
            f"the recording is silent from {window[0]:.2f} s to {window[1]:.2f} s "
            f"— at least {seconds:.1f} s of the note never sounded (gate held "
            f"over a decayed envelope?)"
        )))
    return found


def _midi_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


#: What one of each accidental is worth in semitones. `♯`/`♭` are here
#: because a score is hand-written by a human with a keyboard layout, and a
#: typographic accidental is a spelling of the same pitch, not a typo.
_ACCIDENTALS = {"#": 1, "♯": 1, "b": -1, "♭": -1}


def _note_to_midi(note: str) -> int | None:
    """MIDI number for a name from :func:`freq_to_note`; ``None`` for a rest."""
    if note == REST:
        return None
    body = note.strip()
    letter, body = body[:1].upper(), body[1:]
    shift = 0
    while body and body[0] in _ACCIDENTALS:
        shift += _ACCIDENTALS[body[0]]
        body = body[1:]
    try:
        return (int(body) + 1) * 12 + _NOTE_NAMES.index(letter) + shift
    except ValueError as exc:
        raise ValueError(f"{note!r} is not a note name") from exc


def spell_as_transcribed(note: str) -> str:
    """A reference note respelled the way the transcription writes it.

    `freq_to_note` names every black key with a sharp, because a frequency
    carries no key signature to choose a spelling from. A score written from
    music data does carry one, and `Ab4` is the same pitch as `G#4` — so
    comparing the STRINGS reports orthography as a wrong note. (Measured: the
    first `--ref` run of one demo came back as seven diffs, every one of them
    a flat against its sharp.)

    Round-tripping through MIDI is what makes this a PITCH comparison without
    losing the octave: `Cb4` is `B3`, an octave digit lower, so a bare
    pitch-class match would call it B4 and hide a real wrong-octave bug.

    Anything that is not a note name — a rest, a typo — comes back unchanged,
    for `diff_score` to report against as it always did.
    """
    if note == REST:
        return REST
    try:
        midi = _note_to_midi(note)
    except (ValueError, IndexError):
        return note
    return note if midi is None else _midi_name(midi)


def _frame_span(events: Sequence[NoteEvent]) -> tuple[int, int]:
    """``(first, last)`` frame covered by the events; at least one frame wide."""
    if not events:
        return 0, 1
    first = min(event.start_frame for event in events)
    last = max(event.start_frame + event.frames for event in events)
    return first, max(last, first + 1)


def _midi_range(events: Sequence[NoteEvent]) -> tuple[int, int]:
    pitched = [midi for midi in (_note_to_midi(e.note) for e in events) if midi is not None]
    if not pitched:
        # Nothing sounded, but the axis still has to mean something: centre the
        # empty grid on middle C rather than drawing a zero-height plot.
        pitched = [60]
    return min(pitched) - NOTE_RANGE_PADDING, max(pitched) + NOTE_RANGE_PADDING


class _Audio(NamedTuple):
    """A decoded WAV: full-scale floats, plus the mono mixdown analysis uses.

    ``positive_full_scale`` is the largest value this format can actually
    encode — 127/128 at 8 bits, 32767/32768 at 16 — which is what clipping is
    measured against. See ``CLIP_THRESHOLD``.

    ``frames`` is the frame count the RIFF header CLAIMS, which is not always
    the number of frames that were read: ``len(mono)`` is the decoded length,
    and `wav_metrics` reports both. See its docstring for why the header is
    not trusted for the length.
    """

    samples: np.ndarray
    mono: np.ndarray
    rate: int
    frames: int
    positive_full_scale: float


def _read_wav(path: str | Path) -> _Audio:
    path = Path(path)
    with wave.open(str(path), "rb") as source:
        channels, width = source.getnchannels(), source.getsampwidth()
        rate, frames = source.getframerate(), source.getnframes()
        raw = source.readframes(frames)
    dtype = SAMPLE_DTYPES.get(width)
    if dtype is None:
        supported = ", ".join(str(8 * w) for w in sorted(SAMPLE_DTYPES))
        raise ValueError(f"{path}: {8 * width}-bit samples are not supported "
                         f"(need {supported}-bit PCM)")
    if rate <= 0:
        raise ValueError(f"{path}: sample rate is {rate}, expected a positive rate")
    # `readframes` returns what is THERE, which for a file whose header outruns
    # its data is short and can end inside a frame — mid-sample even. Neither
    # `frombuffer` (a buffer that is not a whole number of samples) nor the
    # stereo reshape below accepts a partial frame, so both would come out of a
    # re-score as a traceback; the partial frame is dropped and `wav_metrics`
    # reports the shortfall against the header instead.
    raw = raw[:len(raw) // (width * channels) * (width * channels)]
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    # 8-bit WAV is unsigned with a 128 midpoint; every wider format is signed.
    # Either way the divisor is the NEGATIVE rail, so the code for silence maps
    # to exactly 0.0 and the positive rail lands one step short of 1.0.
    scale = 128.0 if width == 1 else 2.0 ** (8 * width - 1)
    samples = samples / 128.0 - 1.0 if width == 1 else samples / scale
    if channels > 1:
        mono = samples[:frames * channels].reshape(-1, channels).mean(axis=1)
    else:
        mono = samples
    return _Audio(samples=samples, mono=mono, rate=rate, frames=frames,
                  positive_full_scale=(scale - 1.0) / scale)


def _rms_db(chunk: np.ndarray) -> float:
    if not len(chunk):
        return MIN_DB
    rms = float(np.sqrt(np.mean(np.square(chunk))))
    return max(MIN_DB, 20 * math.log10(rms)) if rms > 0 else MIN_DB


def _silence_windows(
    profile: Sequence[float], window: int, samples: int, rate: int
) -> list[tuple[float, float]]:
    """Maximal runs of sub-``SILENCE_DB`` profile windows lasting ``MIN_SILENCE_S``."""
    found: list[tuple[float, float]] = []
    start = None
    for index in range(len(profile) + 1):   # one past the end closes a trailing run
        if index < len(profile) and profile[index] < SILENCE_DB:
            start = index if start is None else start
        elif start is not None:
            # The last profile window may be short, so clamp to the real length.
            begin, end = start * window / rate, min(index * window, samples) / rate
            if end - begin >= MIN_SILENCE_S:
                found.append((begin, end))
            start = None
    return found


def _apply_ramp(normalized: np.ndarray) -> np.ndarray:
    """Map values in [0, 1] through ``SPECTROGRAM_RAMP`` to RGB."""
    stops = [position for position, _ in SPECTROGRAM_RAMP]
    channels = [np.interp(normalized, stops, [color[c] for _, color in SPECTROGRAM_RAMP])
                for c in range(3)]
    return np.stack(channels, axis=-1).astype(np.uint8)


def _waveform_name(bits: int) -> str:
    names = [name for bit, name in sorted(WAVEFORM_NAMES.items()) if bits & bit]
    return "+".join(names) if names else "none"


def _count(number: int, noun: str, plural: str | None = None) -> str:
    return f"{number} {noun if number == 1 else plural or noun + 's'}"


def _transcription_section(events: Sequence[NoteEvent]) -> list[str]:
    lines = ["## Transcription", ""]
    if not events:
        return lines + ["No note events — the register log was empty.", ""]
    if not any(event.note != REST for event in events):
        # Said before the tables, not left to be inferred from three columns
        # of "rest": this is the shape of a capture that missed its window.
        lines += ["**No voice sounded.** Every frame of all three voices "
                  "transcribed as a rest.", ""]
    for voice in VOICES:
        heard = [event for event in events if event.voice == voice]
        if not heard:
            continue
        lines += [
            f"### Voice {voice}", "",
            "| Start frame | Frames | Note | Cents off | Waveform | Gated frames |",
            "|---|---|---|---|---|---|",
        ]
        for event in heard:
            # `+ 0.0` folds the negative zero a tiny flat deviation rounds to,
            # so a dead-in-tune note reads "+0.0" rather than "-0.0".
            #
            # Noise gets the rest's dash rather than a number. The note NAME
            # stays — it is a faithful reading of the oscillator, it is what
            # sets the noise's brightness, and the piano roll and the score
            # diff are both built on it — but a cents figure next to it is a
            # claim about tuning, and noise has no pitch to be in tune with.
            # Printing "+30.1" there is what made a drum track's FAIL read as
            # credible. The `Waveform` column two cells along says "noise".
            cents = ("-" if event.note == REST or _is_noise(event.waveform)
                     else f"{round(event.cents_off, 1) + 0.0:+.1f}")
            lines.append(
                f"| {event.start_frame} | {event.frames} | {event.note} | {cents} | "
                f"{_waveform_name(event.waveform)} | {event.gate_frames} |"
            )
        lines.append("")
    return lines


def _score_diff_section(diffs: Sequence[str], ref: Mapping | str | Path | None) -> list[str]:
    """The Score-diff section: what was checked, then what it found.

    "What was checked" first and unconditionally, because the section's own
    findings are ambiguous without it — no diffs is what a matching score
    produces AND what no score at all produces, and a committed report that
    could not tell a reviewer which is what this section exists to fix.
    """
    lines = ["## Score diff", ""]
    if ref is None:
        lines += [
            "**No reference score supplied.** Nothing below was checked against one, so "
            "this section is not evidence about which notes played — only the "
            "reference-free checks under *Anomalies* ran. Re-run with `--ref SCORE.yaml` "
            "to diff this log against a written score.",
            "",
        ]
    else:
        named = ("a score supplied inline (not a file)" if isinstance(ref, Mapping)
                 else f"`{ref}`")
        lines += _reference_claim(named, ref)
    if diffs:
        # Printed even under "no reference supplied" — a combination
        # `audio.sid_report` cannot produce (it skips the diff outright when
        # there is no score), so this is for a library caller that diffed
        # against something it did not name. Its findings are real; dropping
        # them here would be a worse failure than an odd-reading section.
        return lines + [f"- {diff}" for diff in diffs] + [""]
    if ref is None:
        return lines
    return lines + ["No differences: every entry above was compared against this capture.",
                    ""]


def _reference_claim(named: str, ref: Mapping | str | Path) -> list[str]:
    """What the reference score claims, read through `score_summary`.

    The same function `c64 audio score` prints, so the report and that command
    cannot disagree about a score's counts.
    """
    try:
        summary = score_summary(ref)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        # A score that reached this point has already been read by
        # `diff_score` — with one gap: that comparison only reaches an entry's
        # `frames` when the NOTE matched, so a wrong note over a non-numeric
        # duration diffs cleanly and summarises not at all. Say so rather than
        # losing a finished report, and its capture, at the last line.
        return [f"Checked against {named}, which could not be summarised: {exc}.", ""]
    voices = summary["voices"]
    lines = [
        f"Checked against {named} — {_count(len(voices), 'voice')}, "
        f"{_count(summary['entries'], 'entry', 'entries')}, "
        f"{_count(summary['frames'], 'frame')}.",
        "",
        "| Voice | Entries | Frames | First | Last |",
        "|---|---|---|---|---|",
    ]
    for voice, claim in sorted(voices.items(), key=lambda item: int(item[0])):
        # A voice the score lists as empty claims silence, and has no first or
        # last note to print; the dash is that claim, not a missing value.
        lines.append(f"| {voice} | {claim['entries']} | {claim['frames']} | "
                     f"{claim['first'] or '-'} | {claim['last'] or '-'} |")
    return lines + [""]


def _list_section(title: str, items: Sequence[str], when_empty: str) -> list[str]:
    lines = [f"## {title}", ""]
    lines += [f"- {item}" for item in items] if items else [when_empty]
    return lines + [""]


def _metrics_section(metrics: Mapping | None) -> list[str]:
    lines = ["## WAV metrics", ""]
    if metrics is None:
        return lines + ["No audio was recorded for this run (register log only).", ""]
    windows = list(metrics.get("silence_windows") or [])
    profile = list(metrics.get("rms_db_profile") or [])
    silence = (", ".join(f"{start:.2f}-{end:.2f} s" for start, end in windows)
               if windows else "none")
    # The full profile is hundreds of numbers — callers that want it read the
    # dict; the report carries the shape of it.
    rms = (f"{min(profile):.1f} / {statistics.median(profile):.1f} / {max(profile):.1f} dBFS "
           f"over {_count(len(profile), 'window')} of {RMS_WINDOW_S:g} s"
           if profile else "no samples")
    duration = float(metrics.get("duration_s") or 0.0)
    lines += [
        "| Metric | Value |",
        "|---|---|",
        f"| Duration | {duration:.2f} s |",
    ]
    # Only when the two disagree. A finished capture's header says exactly what
    # its samples do, and a row repeating the duration on every report would
    # train a reader to skip the one place this row means something.
    if metrics.get("truncated"):
        claimed = float(metrics.get("header_duration_s") or 0.0)
        lines.append(f"| Header duration | {claimed:.2f} s — "
                     f"{claimed - duration:.2f} s of it is not in the file |")
    return lines + [
        f"| Clipped samples | {int(metrics.get('clipped_samples') or 0)} |",
        f"| Silence windows | {silence} |",
        f"| RMS min / median / max | {rms} |",
        "",
    ]


def _artifacts_section(outdir: Path) -> list[str]:
    lines = ["## Artifacts", ""]
    present = [name for name in ARTIFACT_NAMES if (outdir / name).exists()]
    lines += ([f"- [{name}]({name})" for name in present] if present
              else ["None were written next to this report."])
    return lines + [""]


def _all_silent(metrics: Mapping) -> bool:
    """Whether a measured recording carries no audible sound at all.

    ``ALL_SILENT_COVERAGE`` of its duration under ``SILENCE_DB`` — or no
    duration to cover, which is the WAV with a header and no frames.

    ``duration_s`` being the DECODED length is what makes the coverage
    fraction mean anything: measured against a header's claim, a file holding
    a second of silence out of the thirty it advertises covers 3% and passes
    for audible. See :func:`wav_metrics`.
    """
    duration = float(metrics.get("duration_s") or 0.0)
    if duration <= 0.0:
        return True
    silent = sum(end - start for start, end in metrics.get("silence_windows") or [])
    return silent >= duration * ALL_SILENT_COVERAGE


def _truncation_failure(metrics: Mapping) -> str | None:
    """Why a recording's header outrunning its samples fails the verdict.

    Unconditional — unlike the silence failures below, this one does not wait
    for the log to claim something sounded. What is wrong is the ARTIFACT: the
    file holds part of a run, so every metric beside it, the spectrogram and
    the score diff all describe a fragment, and a PASS over that says the run
    was verified when only its beginning was. `wav_metrics` measures whatever
    landed rather than refusing — a partial recording is still evidence — but
    it is evidence about a partial recording.
    """
    if not metrics.get("truncated"):
        return None
    return (f"the recording is truncated: its header claims "
            f"{float(metrics.get('header_duration_s') or 0.0):.2f} s but only "
            f"{float(metrics.get('duration_s') or 0.0):.2f} s of samples are in the "
            f"file — VICE patches the header when the recorder's close is serviced, "
            f"so this WAV was either measured before the capture was finalized or "
            f"lost its tail; every level metric in this report covers only the part "
            f"that landed, so re-capture, or re-score once the file has settled, "
            f"before reading them as a result")


def _silence_failure(events: Sequence[NoteEvent], metrics: Mapping) -> str | None:
    """Why a recording's silence fails the verdict, or ``None``.

    Silence is only a failure when the log says something sounded. Two
    different faults reach that point and they need different sentences: a
    recording that ran and came back quiet, and a recording that never
    happened. The second is the warp signature — VICE writes a header and no
    frames — and telling its owner "the recording is silent" sends them
    looking at ``$D418`` instead of at the speed pin.
    """
    if not any(event.note != REST for event in events):
        return None
    if float(metrics.get("duration_s") or 0.0) <= 0.0:
        return ("the recording has no samples at all, though the register log has "
                "sounding notes — a WAV with a header and no frames is what a "
                "capture window that was not at real time produces")
    if _all_silent(metrics):
        return "the recording is silent, but the register log has sounding notes"
    return None


def _nothing_played_notice(
    events: Sequence[NoteEvent], metrics: Mapping | None
) -> list[str]:
    """The block quote that sits under the verdict when nothing sounded.

    A notice and not a failure, for the reason `nothing_played` gives: a
    silent capture can be exactly what was asked for. But a bare **PASS** over
    an empty capture tells an agent that mis-timed its window, or whose
    program never started, that everything checks out — so the pass says out
    loud what it is passing on. A block quote rather than a ``- `` bullet
    because those bullets are the verdict's REASONS, which a front end reads
    back out of this file.
    """
    if not nothing_played(events, metrics):
        return []
    heard = ("no voice was ever gated over a frequency" if events
             else "the register log was empty")
    recording = ("" if metrics is None
                 else " and the recording is silent from end to end")
    return [
        f"> **Nothing played.** In this capture {heard}{recording}, so there was "
        f"nothing for the checks above to disagree with. That is a legitimate "
        f"result when the claim was that the program is quiet — and it is also "
        f"what a capture window that opened on the wrong moment, or on a "
        f"program that never started, produces. Confirm which before reading "
        f"this as evidence that the audio works.",
        "",
    ]


def _verdict_failures(
    events: Sequence[NoteEvent],
    diffs: Sequence[str],
    anomalies: Sequence[str],
    metrics: Mapping | None,
) -> list[str]:
    failures = []
    if diffs:
        failures.append(f"{_count(len(diffs), 'difference')} from the reference score")
    if anomalies:
        failures.append(f"{_count(len(anomalies), 'anomaly', 'anomalies')} in the register log")
    if metrics is not None:
        # First of the recording's reasons: it is the one that says the others
        # only cover part of the run.
        truncated = _truncation_failure(metrics)
        if truncated is not None:
            failures.append(truncated)
        clipped = int(metrics.get("clipped_samples") or 0)
        if clipped:
            failures.append(f"{_count(clipped, 'clipped sample')} in the recording")
        silence = _silence_failure(events, metrics)
        if silence is not None:
            failures.append(silence)
    return failures
