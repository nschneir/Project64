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

# --- rendering -----------------------------------------------------------

#: One fixed colour per voice — pinned, so a piano roll from one demo can be
#: read against another's without checking a per-report legend mapping.
VOICE_COLORS = {1: (255, 64, 64), 2: (64, 220, 64), 3: (80, 120, 255)}
#: Neutral greys, so nothing but a voice bar is ever channel-dominant.
ROLL_BACKGROUND = (18, 18, 22)
ROLL_GRID = (52, 52, 58)
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
MAX_ROW_LABELS = 12

# --- audio ---------------------------------------------------------------

#: A sample at or above this fraction of full scale is clipped.
CLIP_THRESHOLD = 0.999
#: Resolution of the RMS profile, and therefore of silence detection.
RMS_WINDOW_S = 0.1
#: A window quieter than this counts as silence.
SILENCE_DB = -60.0
#: Silence shorter than this is a musical gap, not a dropout.
MIN_SILENCE_S = 0.25
#: Digital silence is -inf dBFS; floored so the profile stays JSON-serializable
#: (an MCP tool returns this dict, and `Infinity` is not valid JSON).
MIN_DB = -120.0
#: WAV sample widths in bytes -> numpy type. 8-bit WAV is unsigned by format.
SAMPLE_DTYPES = {1: "u1", 2: "<i2", 4: "<i4"}

#: STFT geometry.
FFT_WINDOW = 1024
FFT_HOP = 512
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


def render_piano_roll(events: Sequence[NoteEvent], png_path: str | Path, fps: float) -> None:
    """Draw the transcription as a piano roll PNG.

    X is capture frames, Y is the MIDI note numbers present padded by
    ``NOTE_RANGE_PADDING`` semitones each way, and each gated note is a filled
    bar in its voice's pinned colour. Rests are left as background, so what the
    eye picks out is exactly what sounded. ``fps`` only labels the legend with
    the capture's duration in seconds — the drawing itself is in frames.

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

    label_stride = max(1, math.ceil(rows / MAX_ROW_LABELS))
    for midi in range(low_midi, high_midi + 1, label_stride):
        y = y_of(midi) + row_height - 1
        draw.line([(ROLL_GUTTER, y), (width - ROLL_PAD, y)], fill=ROLL_GRID)
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

    Returns ``duration_s``, ``clipped_samples`` (samples at or above
    ``CLIP_THRESHOLD`` of full scale, counted across every channel before the
    mixdown, because clipping is a per-channel event), ``silence_windows``
    (``(start_s, end_s)`` pairs) and ``rms_db_profile`` (dBFS per
    ``RMS_WINDOW_S``).

    Silence is found on the RMS profile rather than on a separate sweep, so its
    resolution is the profile's: a run must cover enough whole windows to reach
    ``MIN_SILENCE_S``. Channels are averaged to mono first — a dropout in one
    channel of a stereo recording is a mix problem, not the SID's.
    """
    audio = _read_wav(wav_path)
    clipped = int(np.count_nonzero(np.abs(audio.samples) >= CLIP_THRESHOLD))
    window = max(1, round(RMS_WINDOW_S * audio.rate))
    profile = [_rms_db(audio.mono[start:start + window])
               for start in range(0, len(audio.mono), window)]
    return {
        "duration_s": audio.frames / audio.rate,
        "clipped_samples": clipped,
        "silence_windows": _silence_windows(profile, window, len(audio.mono), audio.rate),
        "rms_db_profile": profile,
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
    """
    audio = _read_wav(wav_path)
    mono = audio.mono
    if len(mono) < FFT_WINDOW:
        mono = np.pad(mono, (0, FFT_WINDOW - len(mono)))

    starts = range(0, len(mono) - FFT_WINDOW + 1, FFT_HOP)
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
) -> Path:
    """Write ``report.md`` into ``outdir`` and return its path.

    The verdict is PASS only when there are no score diffs, no anomalies, and —
    when a WAV was measured — no clipping and no unexpected silence. ``metrics``
    of ``None`` is a render-only run (no audio captured), which is a legitimate
    outcome and not a failure; likewise an empty ``diffs`` list, which is what a
    run with no reference score produces.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    failures = _verdict_failures(events, diffs, anomalies, metrics)

    lines = ["# SID audio verification", ""]
    lines += _transcription_section(events)
    lines += _list_section("Score diff", diffs,
                           "No differences against the reference score — an empty diff "
                           "list is also what a run with no reference score produces.")
    lines += _list_section("Anomalies", anomalies, "None found.")
    lines += _metrics_section(metrics)
    lines += _artifacts_section(outdir)
    lines += ["## Verdict", "", f"**{'FAIL' if failures else 'PASS'}**", ""]
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


def _midi_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def _note_to_midi(note: str) -> int | None:
    """MIDI number for a name from :func:`freq_to_note`; ``None`` for a rest."""
    if note == REST:
        return None
    accidental = 2 if len(note) > 1 and note[1] == "#" else 1
    name, octave = note[:accidental], note[accidental:]
    try:
        return (int(octave) + 1) * 12 + _NOTE_NAMES.index(name)
    except ValueError as exc:
        raise ValueError(f"{note!r} is not a note name") from exc


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
    """A decoded WAV: full-scale floats, plus the mono mixdown analysis uses."""

    samples: np.ndarray
    mono: np.ndarray
    rate: int
    frames: int


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
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    # 8-bit WAV is unsigned with a 128 midpoint; every wider format is signed.
    samples = samples / 128.0 - 1.0 if width == 1 else samples / 2 ** (8 * width - 1)
    if channels > 1:
        mono = samples[:frames * channels].reshape(-1, channels).mean(axis=1)
    else:
        mono = samples
    return _Audio(samples=samples, mono=mono, rate=rate, frames=frames)


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
            cents = "-" if event.note == REST else f"{round(event.cents_off, 1) + 0.0:+.1f}"
            lines.append(
                f"| {event.start_frame} | {event.frames} | {event.note} | {cents} | "
                f"{_waveform_name(event.waveform)} | {event.gate_frames} |"
            )
        lines.append("")
    return lines


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
    return lines + [
        "| Metric | Value |",
        "|---|---|",
        f"| Duration | {float(metrics.get('duration_s') or 0.0):.2f} s |",
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


def _unexpected_silence(events: Sequence[NoteEvent], metrics: Mapping) -> bool:
    """A silent recording is only a failure when the log says something sounded."""
    if not any(event.note != REST for event in events):
        return False
    duration = float(metrics.get("duration_s") or 0.0)
    silent = sum(end - start for start, end in metrics.get("silence_windows") or [])
    return silent >= duration * ALL_SILENT_COVERAGE


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
        clipped = int(metrics.get("clipped_samples") or 0)
        if clipped:
            failures.append(f"{_count(clipped, 'clipped sample')} in the recording")
        if _unexpected_silence(events, metrics):
            failures.append("the recording is silent, but the register log has sounding notes")
    return failures
