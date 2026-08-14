"""Pure-analysis tests: no VICE, no session, no daemon.

Register logs are built in-memory by ``_log`` from per-voice ``(reg16,
control)`` states, so every expectation below is traceable to the exact SID
register values a capture would have recorded. WAVs are synthesized the same
way by ``_write_wav``, so the expected metrics are arithmetic on the tone that
was written, not a restatement of the implementation.
"""

import json
import math
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from c64lib import sid_analysis
from c64lib.sid_analysis import (
    MAX_ROW_LABELS,
    MIN_ROW_HEIGHT,
    NOTE_RANGE_PADDING,
    ROLL_BACKGROUND,
    ROLL_GRID,
    ROLL_GRID_UNLABELLED,
    ROLL_GUTTER,
    ROLL_LEGEND_HEIGHT,
    ROLL_PAD,
    ROLL_TEXT,
    FrameRecord,
    NoteEvent,
    _midi_name,
    _midi_range,
    _note_to_midi,
    diff_score,
    dominant_partial_hz,
    find_anomalies,
    freq_to_note,
    nothing_played,
    parse_log,
    render_piano_roll,
    render_spectrogram,
    score_summary,
    transcribe,
    wav_metrics,
    write_report,
)

#: The pitch ``_midi_range`` centres an all-rest roll on. Derived, not spelled
#: "C4": the per-voice colour test scores each voice against an all-rest
#: baseline and needs both rolls to have the SAME geometry, which holds only
#: while the bars are drawn at this pitch. Pinning C4 by hand made that
#: dependency invisible, so moving the fallback would have failed the test
#: with "voice N painted another voice's channel" instead of naming geometry.
FALLBACK_NOTE = _midi_name(sum(_midi_range([])) // 2)

PAL_CLOCK = 985248
NTSC_CLOCK = 1022727
#: Frames per second of the machines above. Paired with the clock, never
#: mixed: a PAL log timed at 60 fps places every note 20% early against a WAV.
PAL_FPS = 50
NTSC_FPS = 60

#: reg16 values whose PAL pitches are pinned by the plan.
A4_REG = 7493        # 440.03 Hz, A4, +0.11 cents
C4_REG = 4455        # 261.62 Hz, C4, -0.03 cents
E4_REG = 5613        # 329.63 Hz, E4, -0.01 cents
GS4_REG = 7072       # 415.31 Hz, G#4, +0.00 cents — the enharmonic case
B3_REG = 4205        # 246.94 Hz, B3, -0.01 cents — one below C4
A4_SHARP30_REG = 7623   # 447.66 Hz, A4 +29.9 cents — audibly out of tune

#: Voice 3's frequency in the 8 s NTSC Space Invaders gameplay capture of
#: 2026-08-02, which is the log every noise test below is built from:
#: 6176 * 1022727 / 2**24 = 376.485 Hz, which is F#4 sharp by 30.1 cents.
#: The invader march's percussion — noise, so there is no pitch there at all.
INVADERS_NOISE_REG = 6176

TRIANGLE_ON = 0x11   # triangle waveform + gate
TRIANGLE_OFF = 0x10  # same waveform, gate released
PULSE_ON = 0x41      # pulse waveform + gate: pitched, so tuning applies
NOISE_ON = 0x81      # noise waveform + gate: no pitch to be in tune with
NOISE_OFF = 0x80     # same waveform, gate released
PULSE_NOISE_ON = 0xC1   # a combined waveform with noise in it


def _regs(voices):
    """25 register bytes from ``{voice: (reg16, control)}``."""
    regs = [0] * 25
    for voice, (reg16, control) in voices.items():
        base = 7 * (voice - 1)
        regs[base] = reg16 & 0xFF
        regs[base + 1] = (reg16 >> 8) & 0xFF
        regs[base + 4] = control
    return tuple(regs)


def _log(*segments):
    """Frame records from ``(frame_count, {voice: (reg16, control)})`` segments."""
    records = []
    for count, voices in segments:
        regs = _regs(voices)
        for _ in range(count):
            records.append(FrameRecord(frame=len(records), regs=regs))
    return records


def _voice(events, voice):
    return [e for e in events if e.voice == voice]


# --- freq_to_note ---------------------------------------------------------

def test_freq_to_note_concert_a():
    assert freq_to_note(440.0) == ("A4", 0.0)


def test_freq_to_note_pal_reg16_7493_is_a4():
    hz = A4_REG * PAL_CLOCK / 2**24
    assert hz == pytest.approx(440.06, abs=0.05)
    name, cents = freq_to_note(hz)
    assert name == "A4"
    assert abs(cents) < 2


def test_freq_to_note_pal_reg16_4455_is_c4():
    hz = C4_REG * PAL_CLOCK / 2**24
    assert hz == pytest.approx(261.6, abs=0.05)
    name, cents = freq_to_note(hz)
    assert name == "C4"
    assert abs(cents) < 3


def test_freq_to_note_octave_numbering():
    assert freq_to_note(220.0)[0] == "A3"
    assert freq_to_note(880.0)[0] == "A5"
    assert freq_to_note(261.63)[0] == "C4"
    assert freq_to_note(523.25)[0] == "C5"


def test_freq_to_note_reports_signed_cents():
    sharp = freq_to_note(A4_SHARP30_REG * PAL_CLOCK / 2**24)
    assert sharp[0] == "A4"
    assert sharp[1] == pytest.approx(29.9, abs=0.5)
    flat = freq_to_note(440.0 * 2 ** (-30 / 1200))
    assert flat == ("A4", pytest.approx(-30.0, abs=0.01))


def test_freq_to_note_rejects_non_positive():
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="positive"):
            freq_to_note(bad)


# --- parse_log ------------------------------------------------------------

def test_parse_log_round_trip(tmp_path):
    records = _log((2, {1: (A4_REG, TRIANGLE_ON)}), (1, {2: (C4_REG, TRIANGLE_ON)}))
    path = tmp_path / "sid-log.jsonl"
    path.write_text(
        "".join(json.dumps({"frame": r.frame, "regs": list(r.regs)}) + "\n"
                for r in records)
    )
    assert parse_log(path) == records


def test_parse_log_ignores_blank_lines(tmp_path):
    path = tmp_path / "sid-log.jsonl"
    row = json.dumps({"frame": 0, "regs": [0] * 25})
    path.write_text(f"\n{row}\n\n")
    assert parse_log(path) == [FrameRecord(frame=0, regs=tuple([0] * 25))]


def test_parse_log_rejects_wrong_register_count(tmp_path):
    path = tmp_path / "sid-log.jsonl"
    path.write_text(
        json.dumps({"frame": 0, "regs": [0] * 25}) + "\n"
        + json.dumps({"frame": 1, "regs": [0] * 24}) + "\n"
    )
    with pytest.raises(ValueError, match="line 2"):
        parse_log(path)


def test_parse_log_rejects_missing_keys(tmp_path):
    path = tmp_path / "sid-log.jsonl"
    path.write_text(json.dumps({"regs": [0] * 25}) + "\n")
    with pytest.raises(ValueError, match="line 1"):
        parse_log(path)


STAMP = {"machine": "c64", "clock_hz": 1022727, "fps": 60}


def _stamped(tmp_path, *rows) -> Path:
    path = tmp_path / "sid-log.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in (STAMP, *rows)))
    return path


def test_parse_log_skips_the_clock_stamp_on_line_one(tmp_path):
    """A log carries its machine so a re-score does not have to guess it.
    The stamp is not a frame record and must not be read as one."""
    path = _stamped(tmp_path, {"frame": 0, "regs": [0] * 25})
    assert parse_log(path) == [FrameRecord(frame=0, regs=tuple([0] * 25))]


def test_log_timing_reads_the_stamp_back(tmp_path):
    assert sid_analysis.log_timing(_stamped(tmp_path)) == STAMP


def test_log_timing_is_none_for_a_log_written_before_the_stamp(tmp_path):
    path = tmp_path / "sid-log.jsonl"
    path.write_text(json.dumps({"frame": 0, "regs": [0] * 25}) + "\n")
    assert sid_analysis.log_timing(path) is None


def test_parse_log_still_rejects_a_first_line_that_is_neither(tmp_path):
    """The stamp is a specific shape, not "any object without frames": a
    truncated or foreign first line is still the error it always was."""
    path = tmp_path / "sid-log.jsonl"
    path.write_text(json.dumps({"machine": "c64"}) + "\n")
    with pytest.raises(ValueError, match="line 1"):
        parse_log(path)


def test_log_stamp_accepts_a_future_extra_key(tmp_path):
    """The stamp is a minimum, not an exact shape. Stamping a fourth key one
    day must not make every parser already shipped reject line 1 of a new log
    — and reject it as a malformed frame record, an error naming the wrong
    thing entirely."""
    future = {**STAMP, "sid_model": "8580"}
    path = tmp_path / "sid-log.jsonl"
    path.write_text(json.dumps(future) + "\n"
                    + json.dumps({"frame": 0, "regs": [0] * 25}) + "\n")
    assert sid_analysis.log_timing(path) == future     # whole, extras and all
    assert parse_log(path) == [FrameRecord(frame=0, regs=tuple([0] * 25))]


def test_log_stamp_still_rejects_a_missing_key(tmp_path):
    """The other half of "minimum": a line short of a required key cannot
    answer what `log_timing` is asked, so it is not a header — it is the
    truncated or foreign line it always was."""
    path = tmp_path / "sid-log.jsonl"
    path.write_text(json.dumps({"machine": "c64", "fps": 60}) + "\n")
    assert sid_analysis.log_timing(path) is None
    with pytest.raises(ValueError, match="line 1"):
        parse_log(path)


def test_parse_log_rejects_a_stamp_that_is_not_on_line_one(tmp_path):
    """One header, at the top. A stamp mid-file would silently swallow a
    frame's worth of evidence."""
    path = tmp_path / "sid-log.jsonl"
    path.write_text(json.dumps({"frame": 0, "regs": [0] * 25}) + "\n"
                    + json.dumps(STAMP) + "\n")
    with pytest.raises(ValueError, match="line 2"):
        parse_log(path)


def _one_line_log(tmp_path, regs):
    path = tmp_path / "sid-log.jsonl"
    path.write_text(json.dumps({"frame": 0, "regs": list(regs)}) + "\n")
    return path


@pytest.mark.parametrize("bad", [5.0, 300, -1, "12", True, None])
def test_parse_log_rejects_a_register_that_is_not_a_byte(tmp_path, bad):
    """A bare ``int(r)`` took anything numeric: a float truncated silently and
    an out-of-range value went straight through. Both arrive as a plausible
    transcription rather than as an error, so the parse has to refuse them —
    the same footing the wrong register COUNT is already on."""
    regs = [0] * 25
    regs[3] = bad
    with pytest.raises(ValueError, match="line 1"):
        parse_log(_one_line_log(tmp_path, regs))


def test_parse_log_accepts_both_ends_of_the_byte_range(tmp_path):
    regs = [0, 255] + [0] * 23
    assert parse_log(_one_line_log(tmp_path, regs))[0].regs[:2] == (0, 255)


def test_parse_log_rejects_a_register_before_it_corrupts_the_frequency(tmp_path):
    """``regs[base + 1] << 8`` is where an out-of-range byte does its damage:
    300 in the frequency-high register would report a voice 44 * 256 units
    sharp, with nothing anywhere to say the log was malformed."""
    regs = [0] * 25
    regs[1] = 300
    with pytest.raises(ValueError, match="outside 0-255"):
        parse_log(_one_line_log(tmp_path, regs))


# --- transcribe -----------------------------------------------------------

def test_transcribe_note_then_rest():
    records = _log((25, {1: (A4_REG, TRIANGLE_ON)}), (25, {1: (A4_REG, TRIANGLE_OFF)}))
    note, rest = _voice(transcribe(records, PAL_CLOCK), 1)
    assert (note.voice, note.note, note.start_frame, note.frames, note.waveform,
            note.gate_frames) == (1, "A4", 0, 25, 0x10, 25)
    assert note.cents_off == pytest.approx(0.11, abs=0.05)
    assert rest == NoteEvent(voice=1, note="rest", start_frame=25, frames=25,
                             waveform=0x10, gate_frames=0, cents_off=0.0)


def test_transcribe_ends_note_at_the_gate_release_frame():
    records = _log((10, {1: (A4_REG, TRIANGLE_ON)}), (3, {1: (A4_REG, TRIANGLE_OFF)}))
    note, rest = _voice(transcribe(records, PAL_CLOCK), 1)
    assert (note.start_frame, note.frames) == (0, 10)
    assert (rest.note, rest.start_frame, rest.frames) == ("rest", 10, 3)


def test_transcribe_splits_on_pitch_change():
    records = _log(
        (4, {1: (A4_REG, TRIANGLE_ON)}),
        (6, {1: (C4_REG, TRIANGLE_ON)}),
    )
    events = _voice(transcribe(records, PAL_CLOCK), 1)
    assert [(e.note, e.start_frame, e.frames) for e in events] == [
        ("A4", 0, 4), ("C4", 4, 6),
    ]


def test_transcribe_merges_two_gatings_of_the_same_pitch():
    """The other half of ``test_transcribe_splits_on_pitch_change``: events are
    divided by the note NAME, so two gatings of the same pitch with no gate-low
    frame between them are one event, not two.

    The two segments below are the two gatings. A player that drops and
    re-raises the gate inside a single frame retriggers audibly, but the
    sampler reads the control register once per frame and never sees the dip —
    so the two 6-frame notes come back as one 12-frame note. That is what lets
    a player articulate every note and still score ``frames = ticks *
    frames_per_tick`` exactly. Spread the drop across a frame boundary instead
    and the rest becomes visible, which the second half asserts: the score then
    has to list a 1-frame rest per note."""
    merged = _log(
        (6, {1: (A4_REG, TRIANGLE_ON)}),   # first gating
        (6, {1: (A4_REG, TRIANGLE_ON)}),   # re-gated inside a frame: invisible
    )
    events = _voice(transcribe(merged, PAL_CLOCK), 1)
    assert [(e.note, e.start_frame, e.frames) for e in events] == [("A4", 0, 12)]
    assert events[0].gate_frames == 12

    split = _log(
        (6, {1: (A4_REG, TRIANGLE_ON)}),
        (1, {1: (A4_REG, TRIANGLE_OFF)}),   # one gate-low frame: now visible
        (5, {1: (A4_REG, TRIANGLE_ON)}),
    )
    assert [(e.note, e.start_frame, e.frames)
            for e in _voice(transcribe(split, PAL_CLOCK), 1)] == [
        ("A4", 0, 6), ("rest", 6, 1), ("A4", 7, 5),
    ]


def test_transcribe_records_the_waveform_bits():
    records = _log((3, {1: (A4_REG, 0x41)}))   # pulse + gate
    assert _voice(transcribe(records, PAL_CLOCK), 1)[0].waveform == 0x40


def test_transcribe_covers_every_voice():
    records = _log((5, {2: (C4_REG, TRIANGLE_ON)}))
    events = transcribe(records, PAL_CLOCK)
    assert [(e.voice, e.note) for e in events] == [
        (1, "rest"), (2, "C4"), (3, "rest"),
    ]


def test_transcribe_silent_voice_is_a_single_rest():
    records = _log((30, {1: (A4_REG, TRIANGLE_ON)}))
    rest = _voice(transcribe(records, PAL_CLOCK), 3)
    assert rest == [NoteEvent(voice=3, note="rest", start_frame=0, frames=30,
                              waveform=0, gate_frames=0, cents_off=0.0)]


def test_transcribe_gated_zero_frequency_is_a_rest_that_kept_the_gate():
    records = _log((8, {1: (0, TRIANGLE_ON)}))
    event = _voice(transcribe(records, PAL_CLOCK), 1)[0]
    assert (event.note, event.frames, event.gate_frames) == ("rest", 8, 8)


def test_transcribe_uses_the_supplied_clock():
    records = _log((5, {1: (A4_REG, TRIANGLE_ON)}))
    assert _voice(transcribe(records, PAL_CLOCK), 1)[0].note == "A4"
    ntsc = _voice(transcribe(records, NTSC_CLOCK), 1)[0]
    assert ntsc.note == "A#4"
    assert ntsc.cents_off == pytest.approx(-35.25, abs=0.1)


def test_transcribe_empty_log():
    assert transcribe([], PAL_CLOCK) == []


# --- diff_score -----------------------------------------------------------

def _one_note_log():
    return _log((25, {1: (A4_REG, TRIANGLE_ON)}), (25, {1: (A4_REG, TRIANGLE_OFF)}))


def test_diff_score_matching_reference_is_empty():
    events = transcribe(_one_note_log(), PAL_CLOCK)
    ref = {"voices": {1: [{"note": "A4", "frames": 25},
                          {"note": "rest", "frames": 25}]}}
    assert diff_score(events, ref) == []


def test_diff_score_reports_a_wrong_note():
    events = transcribe(_one_note_log(), PAL_CLOCK)
    ref = {"voices": {1: [{"note": "C4", "frames": 25},
                          {"note": "rest", "frames": 25}]}}
    diffs = diff_score(events, ref)
    assert len(diffs) == 1
    assert "voice 1" in diffs[0] and "C4" in diffs[0] and "A4" in diffs[0]


def test_diff_score_accepts_a_flat_spelling_of_the_note_it_heard():
    """A score written from music data spells `Ab4`; the transcription only
    ever emits sharps. Seven diffs of pure orthography is what comparing the
    STRINGS cost the first --ref run of a real demo."""
    records = _log((25, {1: (GS4_REG, TRIANGLE_ON)}))
    events = transcribe(records, PAL_CLOCK)
    assert _voice(events, 1)[0].note == "G#4"          # what it hears
    assert diff_score(events, {"voices": {1: [{"note": "Ab4", "frames": 25}]}}) == []


@pytest.mark.parametrize("spelling", ["Ab4", "A♭4", "G#4", "G♯4"])
def test_diff_score_reads_every_spelling_of_one_pitch(spelling):
    events = transcribe(_log((25, {1: (GS4_REG, TRIANGLE_ON)})), PAL_CLOCK)
    assert diff_score(events, {"voices": {1: [{"note": spelling}]}}) == []


@pytest.mark.parametrize("spelling, same_as", [("Cb4", "B3"), ("B#3", "C4")])
def test_diff_score_carries_an_octave_across_the_c_boundary(spelling, same_as):
    """`Cb4` is `B3`, an octave digit lower — a pitch-class-only comparison
    would call it a match against B4 and hide a real wrong-octave bug."""
    events = transcribe(_log((25, {1: (B3_REG, TRIANGLE_ON)})), PAL_CLOCK)
    heard = _voice(events, 1)[0].note
    expected_ok = heard == same_as
    assert (diff_score(events, {"voices": {1: [{"note": spelling}]}}) == []) is expected_ok


def test_diff_score_shows_both_spellings_when_a_flat_note_is_wrong():
    """The diff still has to be readable against the score as written, so it
    quotes the score's spelling and the one the transcription would use."""
    events = transcribe(_log((25, {1: (A4_REG, TRIANGLE_ON)})), PAL_CLOCK)
    diffs = diff_score(events, {"voices": {1: [{"note": "Ab4"}]}})
    assert len(diffs) == 1
    assert "Ab4 (= G#4)" in diffs[0] and "heard A4" in diffs[0]


def test_diff_score_reports_a_duration_mismatch():
    records = _log((15, {1: (E4_REG, TRIANGLE_ON)}), (4, {1: (E4_REG, TRIANGLE_OFF)}))
    ref = {"voices": {1: [{"note": "E4", "frames": 12},
                          {"note": "rest", "frames": 4}]}}
    diffs = diff_score(transcribe(records, PAL_CLOCK), ref)
    assert len(diffs) == 1
    assert "voice 1" in diffs[0] and "12" in diffs[0] and "15" in diffs[0]
    assert "frames" in diffs[0]


def test_diff_score_reports_one_diff_per_slot():
    """A wrong note is not also reported as a wrong duration."""
    records = _log((9, {1: (C4_REG, TRIANGLE_ON)}))
    ref = {"voices": {1: [{"note": "A4", "frames": 25}]}}
    assert len(diff_score(transcribe(records, PAL_CLOCK), ref)) == 1


def test_diff_score_reference_notes_on_a_silent_voice():
    events = transcribe(_one_note_log(), PAL_CLOCK)
    ref = {"voices": {3: [{"note": "C4", "frames": 10}]}}
    diffs = diff_score(events, ref)
    assert len(diffs) == 1
    assert "voice 3" in diffs[0] and "C4" in diffs[0]


def test_diff_score_reports_a_missing_event():
    events = transcribe(_one_note_log(), PAL_CLOCK)   # A4 then rest
    ref = {"voices": {1: [{"note": "A4", "frames": 25},
                          {"note": "rest", "frames": 25},
                          {"note": "C4", "frames": 8}]}}
    diffs = diff_score(events, ref)
    assert len(diffs) == 1 and "C4" in diffs[0] and "nothing" in diffs[0]


def test_diff_score_reports_an_extra_note():
    records = _log((25, {1: (A4_REG, TRIANGLE_ON)}), (8, {1: (C4_REG, TRIANGLE_ON)}))
    ref = {"voices": {1: [{"note": "A4", "frames": 25}]}}
    diffs = diff_score(transcribe(records, PAL_CLOCK), ref)
    assert len(diffs) == 1 and "C4" in diffs[0] and "unexpected" in diffs[0]


def test_diff_score_does_not_require_the_score_to_predict_trailing_silence():
    events = transcribe(_one_note_log(), PAL_CLOCK)   # A4 then rest
    assert diff_score(events, {"voices": {1: [{"note": "A4", "frames": 25}]}}) == []


def _late_start_log(*after):
    """5 frames of silence, then whatever the player does — the shape a
    free-running `sid_log` records when it opens before the first gate."""
    return _log((5, {1: (0, TRIANGLE_OFF)}), *after)


def test_diff_score_does_not_require_the_score_to_predict_a_leading_rest():
    """The mirror of the trailing-silence exemption, and the likelier of the
    two: a capture normally opens a few frames before the player's first
    gate."""
    events = transcribe(_late_start_log((25, {1: (A4_REG, TRIANGLE_ON)})), PAL_CLOCK)
    assert diff_score(events, {"voices": {1: [{"note": "A4", "frames": 25}]}}) == []


def test_diff_score_a_leading_rest_does_not_cascade_onto_the_whole_voice():
    """THE regression: one unscored opening rest used to shift every later
    comparison by a slot, so a correct three-note phrase came back as three
    wrong notes plus a missing one."""
    records = _late_start_log(
        (10, {1: (A4_REG, TRIANGLE_ON)}),
        (10, {1: (C4_REG, TRIANGLE_ON)}),
        (10, {1: (E4_REG, TRIANGLE_ON)}),
    )
    ref = {"voices": {1: [{"note": "A4", "frames": 10},
                          {"note": "C4", "frames": 10},
                          {"note": "E4", "frames": 10}]}}
    assert diff_score(transcribe(records, PAL_CLOCK), ref) == []


def test_diff_score_compares_a_leading_rest_the_score_does_list():
    """Only an UNSCORED opening rest is skipped. Score one and it is checked
    like any other entry — otherwise the exemption would erase a claim."""
    events = transcribe(_late_start_log((25, {1: (A4_REG, TRIANGLE_ON)})), PAL_CLOCK)
    ref = {"voices": {1: [{"note": "rest", "frames": 7},
                          {"note": "A4", "frames": 25}]}}
    diffs = diff_score(events, ref)
    assert len(diffs) == 1
    assert "rest expected 7 frames, heard 5" in diffs[0]


def test_diff_score_still_reports_a_voice_that_only_ever_rests():
    """Dropping the leading rest must not hide a voice that never sounded:
    with nothing behind it, the score's first note has nothing to match."""
    events = transcribe(_log((30, {1: (0, TRIANGLE_OFF)})), PAL_CLOCK)
    diffs = diff_score(events, {"voices": {1: [{"note": "A4"}]}})
    assert len(diffs) == 1
    assert "heard nothing" in diffs[0]


@pytest.mark.parametrize("bad", [5, "A4", {"note": "A4"}])
def test_diff_score_rejects_a_voice_that_is_not_a_list(bad):
    """`1: 5` in hand-written YAML used to raise a bare TypeError from inside
    `list()`, while every other malformed shape names the offending entry."""
    with pytest.raises(ValueError, match="voice 1 is not a list of note entries"):
        diff_score([], {"voices": {1: bad}})


def test_diff_score_empty_voice_list_means_silent():
    events = transcribe(_log((10, {1: (C4_REG, TRIANGLE_ON)})), PAL_CLOCK)
    assert diff_score(events, {"voices": {2: [], 3: []}}) == []
    assert len(diff_score(events, {"voices": {1: []}})) == 1


@pytest.mark.parametrize("bad", [4, "4", 0, -1])
def test_diff_score_rejects_a_voice_number_the_sid_does_not_have(bad):
    """A typo'd `4:` used to be compared against a voice with no events, so
    every entry under it came back "heard nothing" — a wall of diffs blaming
    the program for a mistake in the reference."""
    events = transcribe(_log((10, {1: (C4_REG, TRIANGLE_ON)})), PAL_CLOCK)
    with pytest.raises(ValueError, match="voice"):
        diff_score(events, {"voices": {1: [{"note": "C4"}], bad: [{"note": "C4"}]}})


def test_diff_score_rejects_a_voice_key_that_is_not_a_number():
    """Named rather than left to `int()`'s bare "invalid literal", which is
    the one complaint in this module that does not say what it was reading."""
    with pytest.raises(ValueError, match="'lead' is not a voice number"):
        diff_score([], {"voices": {"lead": []}})


def test_load_score_accepts_what_diff_score_accepts(tmp_path):
    """The pre-parse `audio.capture` runs before it opens a capture window is
    the reader `diff_score` itself uses, so a score that survives one cannot
    fail the other on shape."""
    ref = tmp_path / "score.yaml"
    ref.write_text("voices:\n  1:\n    - {note: C4, frames: 5}\n  2: []\n")
    assert sid_analysis.load_score(ref) == [(1, [{"note": "C4", "frames": 5}]),
                                            (2, [])]
    ref.write_text("voices:\n  4: []\n")
    with pytest.raises(ValueError, match="voice 4"):
        sid_analysis.load_score(ref)


def test_diff_score_ignores_voices_the_reference_omits():
    events = transcribe(_log((10, {2: (C4_REG, TRIANGLE_ON)})), PAL_CLOCK)
    assert diff_score(events, {"voices": {}}) == []


def test_diff_score_checks_the_note_only_when_frames_are_omitted():
    events = transcribe(_one_note_log(), PAL_CLOCK)
    ref = {"voices": {1: [{"note": "A4"}, {"note": "rest"}]}}
    assert diff_score(events, ref) == []


def test_diff_score_reads_a_yaml_reference(tmp_path):
    path = tmp_path / "score.yaml"
    path.write_text(
        "tempo_frames_per_row: 6\n"
        "voices:\n"
        "  1:\n"
        "    - {note: A4, frames: 25}\n"
        "    - {note: rest, frames: 25}\n"
        "  2: []\n"
        "  3: []\n"
    )
    assert diff_score(transcribe(_one_note_log(), PAL_CLOCK), path) == []


def test_diff_score_rejects_a_reference_without_voices():
    with pytest.raises(ValueError, match="voices"):
        diff_score([], {"tempo_frames_per_row": 6})


def test_diff_score_rejects_a_yaml_reference_that_is_not_a_mapping(tmp_path):
    path = tmp_path / "score.yaml"
    path.write_text("- A4\n- C4\n")
    with pytest.raises(ValueError, match="not a YAML mapping"):
        diff_score([], path)


def test_diff_score_rejects_a_reference_entry_without_a_note():
    events = transcribe(_one_note_log(), PAL_CLOCK)
    with pytest.raises(ValueError, match="no 'note'"):
        diff_score(events, {"voices": {1: [{"frames": 25}]}})


# --- find_anomalies -------------------------------------------------------

def test_find_anomalies_clean_log_is_empty():
    records = _one_note_log()
    assert find_anomalies(transcribe(records, PAL_CLOCK), records) == []


def test_find_anomalies_silent_voice_is_legal():
    records = _log((200, {1: (A4_REG, TRIANGLE_ON)}))   # voices 2 and 3 all zeros
    assert find_anomalies(transcribe(records, PAL_CLOCK), records) == []


def test_find_anomalies_flags_a_gate_held_over_zero_frequency():
    records = _log((51, {1: (0, TRIANGLE_ON)}))
    findings = find_anomalies(transcribe(records, PAL_CLOCK), records)
    assert len(findings) == 1
    assert "voice 1" in findings[0] and "51" in findings[0]


def test_find_anomalies_measures_a_stuck_gate_in_frames_not_records():
    """The threshold is 50 FRAMES, so it has to be measured in frame numbers.
    Counting records instead let a log with gaps under-count against wall
    time — 51 elapsed frames sampled every 5th frame is 11 records, and the
    same drone would go unreported purely because the producer dropped
    frames."""
    regs = _regs({1: (0, TRIANGLE_ON)})
    sparse = [FrameRecord(frame=n, regs=regs) for n in range(0, 51, 5)]
    assert len(sparse) == 11
    findings = find_anomalies(transcribe(sparse, PAL_CLOCK), sparse)
    assert len(findings) == 1
    assert "for 51 frames" in findings[0] and "from frame 0" in findings[0]


def test_find_anomalies_tolerates_a_short_zero_frequency_gate():
    records = _log((50, {1: (0, TRIANGLE_ON)}))
    assert find_anomalies(transcribe(records, PAL_CLOCK), records) == []


def test_find_anomalies_zero_frequency_run_ends_when_the_gate_drops():
    records = _log(
        (40, {1: (0, TRIANGLE_ON)}),
        (1, {1: (0, TRIANGLE_OFF)}),
        (40, {1: (0, TRIANGLE_ON)}),
    )
    assert find_anomalies(transcribe(records, PAL_CLOCK), records) == []


def test_find_anomalies_flags_a_sustained_detuned_note():
    records = _log((25, {1: (A4_SHARP30_REG, TRIANGLE_ON)}))
    findings = find_anomalies(transcribe(records, PAL_CLOCK), records)
    assert len(findings) == 1
    assert "detun" in findings[0].lower()
    assert "voice 1" in findings[0] and "A4" in findings[0]


def test_find_anomalies_ignores_a_short_detuned_note():
    records = _log((24, {1: (A4_SHARP30_REG, TRIANGLE_ON)}))
    assert find_anomalies(transcribe(records, PAL_CLOCK), records) == []


def test_find_anomalies_ignores_a_slightly_detuned_note():
    records = _log((100, {1: (A4_REG, TRIANGLE_ON)}))   # +0.11 cents
    assert find_anomalies(transcribe(records, PAL_CLOCK), records) == []


def test_find_anomalies_reports_every_voice_in_order():
    records = _log(
        (60, {1: (0, TRIANGLE_ON), 2: (A4_SHARP30_REG, TRIANGLE_ON)}),
    )
    findings = find_anomalies(transcribe(records, PAL_CLOCK), records)
    assert len(findings) == 2
    assert "voice 1" in findings[0] and "voice 2" in findings[1]


# --- find_anomalies: noise has no tuning ----------------------------------

def _invaders_voice3():
    """Voice 3 of the 2026-08-02 NTSC Invaders gameplay capture: the march's
    noise percussion, 43 frames from frame 0 and 59 from frame 197."""
    return _log(
        (43, {3: (INVADERS_NOISE_REG, NOISE_ON)}),
        (154, {3: (INVADERS_NOISE_REG, NOISE_OFF)}),
        (59, {3: (INVADERS_NOISE_REG, NOISE_ON)}),
    )


def test_invaders_noise_percussion_transcribes_as_the_capture_did():
    """The fixture is the failing capture, not a convenient approximation.

    Asserted before the anomaly test uses it, because "no detune anomaly" is
    only evidence if this log is one that WOULD have produced one: two runs
    past `MIN_DETUNE_FRAMES`, each more than `MAX_CENTS_OFF` from a note."""
    sounding = [e for e in _voice(transcribe(_invaders_voice3(), NTSC_CLOCK), 3)
                if e.note != sid_analysis.REST]
    assert [(e.note, e.start_frame, e.frames) for e in sounding] \
        == [("F#4", 0, 43), ("F#4", 197, 59)]
    for event in sounding:
        assert event.cents_off == pytest.approx(30.1, abs=0.05)
        assert event.frames >= sid_analysis.MIN_DETUNE_FRAMES
        assert abs(event.cents_off) > sid_analysis.MAX_CENTS_OFF


def test_find_anomalies_does_not_call_noise_percussion_detuned():
    """The regression this fix exists for. Noise is an LFSR, not an
    oscillator: `$D400/$D401` sets its brightness, and calling that "F#4
    detuned +30.1 cents" failed a real capture whose transcription was
    independently confirmed correct."""
    records = _invaders_voice3()
    assert find_anomalies(transcribe(records, NTSC_CLOCK), records) == []


def test_find_anomalies_still_flags_the_same_detuning_on_a_pitched_waveform():
    """Same registers, same durations, pulse instead of noise — so the
    exemption is the WAVEFORM and not a threshold quietly widened past the
    numbers the Invaders capture happened to hold."""
    records = _log((43, {3: (INVADERS_NOISE_REG, PULSE_ON)}))
    findings = find_anomalies(transcribe(records, NTSC_CLOCK), records)
    assert len(findings) == 1
    assert "voice 3" in findings[0] and "F#4" in findings[0]
    assert "detuned +30.1 cents for 43 frames" in findings[0]


def test_find_anomalies_exempts_a_combined_waveform_holding_noise():
    """The bit is tested, not the whole register: pulse+noise is not a clean
    tone either, so there is still no tuning to be wrong about."""
    records = _log((43, {3: (INVADERS_NOISE_REG, PULSE_NOISE_ON)}))
    assert find_anomalies(transcribe(records, NTSC_CLOCK), records) == []


def test_find_anomalies_still_flags_a_stuck_gate_on_a_noise_voice():
    """Only tuning is exempt. A noise voice gated over a zero frequency is as
    stuck as any other, and that check reads the registers, not the pitch."""
    records = _log((51, {3: (0, NOISE_ON)}))
    findings = find_anomalies(transcribe(records, NTSC_CLOCK), records)
    assert len(findings) == 1 and "stuck gate" in findings[0]


# --- find_anomalies: gated but inaudible ----------------------------------

def _wav(duration_s, silence_windows=()):
    """The `wav_metrics` fields the anomaly checks read, and only those."""
    return {"duration_s": duration_s,
            "silence_windows": [tuple(w) for w in silence_windows]}


def _decayed_note_log():
    """2.0 s of an audible note, then a 290-frame note held to the end.

    The shape of the capture this check was written for: voice 1's last event
    transcribed as 290 frames while the WAV under it went quiet part way
    through. At `PAL_FPS` the second note runs 2.00 s to 7.80 s.
    """
    return _log((100, {1: (A4_REG, TRIANGLE_ON)}),
                (290, {1: (C4_REG, TRIANGLE_ON)}))


def test_find_anomalies_flags_a_note_gated_across_recorded_silence():
    """A gate is not audibility: a sustain-zero envelope decays to nothing
    with the gate still held, so the transcription reports 5.8 s of C4 while
    the recording says the last 3.6 s of it never sounded."""
    records = _decayed_note_log()
    findings = find_anomalies(transcribe(records, PAL_CLOCK), records,
                              fps=PAL_FPS, metrics=_wav(7.8, [(4.0, 7.8)]))
    assert len(findings) == 1
    assert "voice 1: C4 at frame 100" in findings[0]
    assert "gated for 290 frames" in findings[0]
    assert "silent from 4.00 s to 7.80 s" in findings[0]
    assert "3.6 s of the note never sounded" in findings[0]


def test_find_anomalies_cannot_see_an_inaudible_note_without_the_recording():
    """The same log alone is clean — every register in it is doing what it
    was told. Which is why the assertion above is evidence about the WAV and
    not about the transcription, and why a register-only run keeps passing."""
    records = _decayed_note_log()
    assert find_anomalies(transcribe(records, PAL_CLOCK), records) == []


def test_find_anomalies_tolerates_silence_shorter_than_the_threshold():
    """1.15 s of measured silence inside the note, less 0.1 s of alignment
    slack at each end, is 0.95 s — under `MIN_INAUDIBLE_S`, which is where a
    decay tail and a gap between phrases live."""
    records = _decayed_note_log()
    assert find_anomalies(transcribe(records, PAL_CLOCK), records,
                          fps=PAL_FPS, metrics=_wav(7.8, [(4.0, 5.15)])) == []


def test_find_anomalies_flags_silence_just_past_the_threshold():
    """The other side of the same 0.1 s: a 1.25 s window is 1.05 s after the
    slack, which is over — and reported to one decimal as 1.1 s. The pair pins
    the threshold AND the slack: without the slack the 1.15 s window above
    would be over it too, and 0.1 s of window separates the two cases."""
    records = _decayed_note_log()
    findings = find_anomalies(transcribe(records, PAL_CLOCK), records,
                              fps=PAL_FPS, metrics=_wav(7.8, [(4.0, 5.25)]))
    assert len(findings) == 1 and "1.1 s of the note never sounded" in findings[0]


def test_find_anomalies_ignores_silence_outside_the_note():
    """An overlap, not "a long silence exists somewhere". The note ends at
    5.80 s and the recording goes quiet after it — which is the gate being
    released, the most ordinary thing in the log."""
    records = _log((290, {1: (A4_REG, TRIANGLE_ON)}),
                   (100, {1: (A4_REG, TRIANGLE_OFF)}))
    assert find_anomalies(transcribe(records, PAL_CLOCK), records,
                          fps=PAL_FPS, metrics=_wav(7.8, [(5.9, 7.8)])) == []


def test_find_anomalies_times_the_recording_from_the_first_logged_frame():
    """Frame numbers are the session's, seconds are the recording's. A log
    that opens at frame 3000 is 60 s into the machine and 0 s into the WAV;
    measured from frame 0 the note would land at 62-78 s, past the end of a
    7.8 s recording, and nothing would ever be flagged."""
    records = [FrameRecord(frame=r.frame + 3000, regs=r.regs)
               for r in _decayed_note_log()]
    findings = find_anomalies(transcribe(records, PAL_CLOCK), records,
                              fps=PAL_FPS, metrics=_wav(7.8, [(4.0, 7.8)]))
    assert len(findings) == 1 and "C4 at frame 3100" in findings[0]


def test_find_anomalies_leaves_a_wholly_silent_recording_to_the_verdict():
    """A capture that recorded nothing at all is one failure with a named
    cause — `write_report`'s silence rule — not one anomaly per note burying
    it under the symptom."""
    records = _decayed_note_log()
    assert find_anomalies(transcribe(records, PAL_CLOCK), records,
                          fps=PAL_FPS, metrics=_wav(7.8, [(0.0, 7.8)])) == []


def test_find_anomalies_refuses_a_frame_rate_it_cannot_divide_by():
    """Raised rather than skipped: a bad fps is a caller bug, and swallowing
    it would delete the check silently — which is how this defect shipped."""
    records = _decayed_note_log()
    with pytest.raises(ValueError, match="fps must be positive"):
        find_anomalies(transcribe(records, PAL_CLOCK), records,
                       fps=0, metrics=_wav(7.8, [(4.0, 7.8)]))


def test_find_anomalies_ignores_a_rest_over_recorded_silence():
    """Silence under a released gate is the system working."""
    records = _log((100, {1: (A4_REG, TRIANGLE_ON)}),
                   (290, {1: (A4_REG, TRIANGLE_OFF)}))
    assert find_anomalies(transcribe(records, PAL_CLOCK), records,
                          fps=PAL_FPS, metrics=_wav(7.8, [(2.0, 7.8)])) == []


# --- render_piano_roll ----------------------------------------------------

MIN_ROLL_SIZE = (640, 240)


def _note(voice, note, start_frame, frames, waveform=0x10, gate_frames=None):
    return NoteEvent(voice=voice, note=note, start_frame=start_frame, frames=frames,
                     waveform=waveform,
                     gate_frames=frames if gate_frames is None else gate_frames,
                     cents_off=0.0)


def _colors(path):
    """``{(r, g, b): pixel_count}`` for a rendered PNG."""
    with Image.open(path) as img:
        counted = img.convert("RGB").getcolors(1 << 20)
    assert counted is not None, "image has more colours than the counting cap"
    return {color: count for count, color in counted}


def _dominant(colors, channel):
    """Pixels whose colour is clearly led by one channel.

    Grid lines, background and label text are all neutral greys, so they never
    qualify; this isolates "how much of the image is voice N's colour" without
    the test having to know the exact pinned RGB triples.

    NB this counts the legend swatches too — the legend paints all three voice
    colours on every render, so a bare "is there red?" assertion would pass
    with no bars drawn at all. Callers must measure against the all-rest
    baseline from ``_voice_colour_counts``, never against zero.
    """
    return sum(count for color, count in colors.items()
               if color[channel] > 128
               and all(color[channel] - color[other] > 64
                       for other in range(3) if other != channel))


def _voice_colour_counts(png, events):
    """``(red, green, blue)`` pixel counts for a roll drawn from ``events``."""
    render_piano_roll(events, png, PAL_FPS)
    colors = _colors(png)
    return tuple(_dominant(colors, channel) for channel in range(3))


def test_render_piano_roll_writes_a_png_of_at_least_the_minimum_size(tmp_path):
    png = tmp_path / "piano-roll.png"
    render_piano_roll([_note(1, "A4", 0, 20), _note(2, "C4", 0, 20)], png, PAL_FPS)
    assert png.exists()
    with Image.open(png) as img:
        assert img.size >= MIN_ROLL_SIZE
        assert img.format == "PNG"


def _plot_rows(path, channel):
    """Image rows where `channel` leads, excluding the legend strip.

    The legend paints all three voice colours on every render, so anything
    measuring bars has to cut it off first.
    """
    with Image.open(path) as img:
        pixels = np.asarray(img.convert("RGB"), dtype=int)
        # height = ROLL_PAD + plot_height + ROLL_LEGEND_HEIGHT, so the plot
        # ends exactly one legend strip above the bottom.
        plot_bottom = img.height - ROLL_LEGEND_HEIGHT
    leads = pixels[:, :, channel] > 128
    for other in range(3):
        if other != channel:
            leads &= pixels[:, :, channel] - pixels[:, :, other] > 64
    return {int(row) for row in np.flatnonzero(leads.any(axis=1))
            if row < plot_bottom}


def test_render_piano_roll_colors_voice_1_red_2_green_3_blue(tmp_path):
    """The pinned voice->colour mapping, measured on bars rather than chrome.

    The legend paints all three voice colours on every render, so presence of a
    colour proves nothing. Each voice is rendered alone at the same pitch and
    frame span — which makes the image geometry, and therefore the legend,
    byte-identical to the all-rest baseline — and scored as the *increase* over
    that baseline. The `== baseline` assertions on the other two channels are
    what make swapping voice 2 and voice 3 fail.

    The bars are drawn at ``FALLBACK_NOTE``, which is derived from
    ``_midi_range``'s own empty-list fallback rather than written out as C4:
    the baseline is an all-rest roll, so only a bar at that exact pitch gives
    the two rolls the same geometry. The size assertion below states that
    dependency out loud, so moving the fallback fails as a geometry mismatch
    instead of as "voice N painted another voice's channel".
    """
    span = 40
    rest_png = tmp_path / "rest.png"
    baseline = _voice_colour_counts(rest_png, [_note(1, "rest", 0, span)])
    assert all(count > 0 for count in baseline), "legend should paint all three colours"
    with Image.open(rest_png) as img:
        baseline_size = img.size

    for voice, channel in ((1, 0), (2, 1), (3, 2)):
        png = tmp_path / f"voice{voice}.png"
        counts = _voice_colour_counts(png, [_note(voice, FALLBACK_NOTE, 0, span)])
        with Image.open(png) as img:
            assert img.size == baseline_size, (
                f"a {FALLBACK_NOTE} roll no longer has the same geometry as the "
                f"all-rest baseline, so the counts below are not comparable — "
                f"_midi_range's empty-range fallback has moved"
            )
        for other in range(3):
            if other == channel:
                assert counts[other] > baseline[other] * 10, (
                    f"voice {voice} should add a large bar in channel {channel}"
                )
            else:
                assert counts[other] == baseline[other], (
                    f"voice {voice} painted channel {other}, which belongs to another voice"
                )


def test_render_piano_roll_draws_three_simultaneous_voices_without_overdraw(tmp_path):
    """Nothing else renders more than two voices at once, so an overdraw that
    only shows up with all three had nowhere to be caught. C4 < E4 < G4 and Y
    runs high pitch at the top, so each voice owns its own band of rows: a
    dropped voice empties one set, a colour swap reorders them, and a bar that
    paints past its row makes two of them intersect."""
    png = tmp_path / "trio.png"
    render_piano_roll([_note(1, "C4", 0, 40), _note(2, "E4", 0, 40),
                       _note(3, "G4", 0, 40)], png, PAL_FPS)
    red, green, blue = (_plot_rows(png, channel) for channel in range(3))
    assert red and green and blue, "a voice went missing from a three-voice roll"
    assert not red & green and not green & blue and not red & blue, \
        "two voices share plot rows: bars are overdrawing each other"
    assert max(blue) < min(green) < max(green) < min(red), \
        "the three bands are not in pitch order G4 (top) / E4 / C4 (bottom)"


def test_render_piano_roll_draws_at_least_two_colors_for_two_voices(tmp_path):
    """The brief's smoke check: a two-voice roll is not monochrome."""
    png = tmp_path / "piano-roll.png"
    render_piano_roll([_note(1, "A4", 0, 40), _note(2, "C4", 0, 40)], png, PAL_FPS)
    colors = _colors(png)
    background, _ = max(colors.items(), key=lambda item: item[1])
    assert len(set(colors) - {background}) >= 2


def test_render_piano_roll_draws_gates_as_bars_and_leaves_rests_empty(tmp_path):
    """More gated frames means more of voice 1's colour on the page."""
    long_note = tmp_path / "long.png"
    short_note = tmp_path / "short.png"
    all_rest = tmp_path / "rest.png"
    render_piano_roll([_note(1, "A4", 0, 40)], long_note, PAL_FPS)
    render_piano_roll([_note(1, "A4", 0, 4), _note(1, "rest", 4, 36)], short_note, PAL_FPS)
    render_piano_roll([_note(1, "rest", 0, 40)], all_rest, PAL_FPS)

    reds = [_dominant(_colors(p), 0) for p in (long_note, short_note, all_rest)]
    assert reds[0] > reds[1] > reds[2]


def test_render_piano_roll_pads_the_note_range(tmp_path):
    """One note in a +/-2 semitone pad is one row of five, not the whole plot.

    Measured as the tallest unbroken band of voice-1 colour: without the
    padding the single note would fill the plot top to bottom.
    """
    png = tmp_path / "piano-roll.png"
    render_piano_roll([_note(1, "A4", 0, 40)], png, PAL_FPS)
    with Image.open(png) as img:
        height = img.height
        pixels = np.asarray(img.convert("RGB"), dtype=int)
    red_rows = ((pixels[:, :, 0] > 128) & (pixels[:, :, 0] - pixels[:, :, 1] > 64)).any(axis=1)

    tallest, run = 0, 0
    for is_red in red_rows:
        run = run + 1 if is_red else 0
        tallest = max(tallest, run)
    assert 0 < tallest < height * 0.4


def test_render_piano_roll_handles_an_empty_event_list(tmp_path):
    png = tmp_path / "piano-roll.png"
    render_piano_roll([], png, PAL_FPS)
    with Image.open(png) as img:
        assert img.size >= MIN_ROLL_SIZE


def test_render_piano_roll_rejects_a_non_positive_fps(tmp_path):
    for bad in (0, -50):
        with pytest.raises(ValueError, match="fps"):
            render_piano_roll([_note(1, "A4", 0, 4)], tmp_path / "roll.png", bad)


# --- render_piano_roll: reading the pitch axis off the image ---------------
#
# The tests below read a rendered roll the way a reviewer does — grid lines and
# printed labels, no access to the event list that drew them — because that is
# the property in question: whether a bar between two labels can be named from
# the image alone.

#: A 33-semitone passage (D2 to A#4, the 1812 hymn's range), with the bar under
#: test at F3: 53 - 36 = 17 rows above the bottom of the padded range, which is
#: not a multiple of the label stride, so F3 is never one of the printed names.
WIDE_PASSAGE = (_note(1, "D2", 0, 60), _note(2, "A#4", 0, 60), _note(3, "F3", 20, 20))
UNLABELLED_BAR = "F3"

#: Tall enough for one whole note-name glyph box and short enough that the next
#: label down cannot reach into the crop.
GLYPH_HEIGHT = ImageFont.load_default().getbbox("A#-1")[3]


def _midi(name):
    """`_note_to_midi` for a name that is not a rest."""
    midi = _note_to_midi(name)
    assert midi is not None, f"{name} is a rest, not a pitch"
    return midi


def _pixels(path):
    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"), dtype=int), img.size


def _ruled_rows(pixels, width):
    """``{y: colour}`` for every row ruled clean across the plot area.

    A whole-row match, so a bar or a label can only remove a row from this map,
    never invent one.
    """
    plot = pixels[:, ROLL_GUTTER:width - ROLL_PAD]
    found = {}
    for tone in (ROLL_GRID, ROLL_GRID_UNLABELLED):
        for y in np.flatnonzero((plot == np.array(tone)).all(axis=2).all(axis=1)):
            found[int(y)] = tone
    return found


def _label_mask(name, height):
    """The pixels a note name leaves in the gutter, rendered as the roll does."""
    image = Image.new("RGB", (ROLL_GUTTER, height), ROLL_BACKGROUND)
    ImageDraw.Draw(image).text((4, 0), name, fill=ROLL_TEXT,
                               font=ImageFont.load_default())
    return (np.asarray(image, dtype=int) != np.array(ROLL_BACKGROUND)).any(axis=2)


def _read_label(pixels, top):
    """The note name printed with its top edge at row ``top``, or None.

    Grid lines start at ``ROLL_GUTTER``, so a crop left of it holds nothing but
    the label's own glyphs and can be matched against a rendering of each
    candidate name.
    """
    crop = pixels[top:top + GLYPH_HEIGHT, :ROLL_GUTTER]
    mask = (crop != np.array(ROLL_BACKGROUND)).any(axis=2)
    for midi in range(128):
        if np.array_equal(mask, _label_mask(_midi_name(midi), GLYPH_HEIGHT)):
            return _midi_name(midi)
    return None


def test_render_piano_roll_rules_every_semitone_and_still_caps_the_labels(tmp_path):
    """A 33-semitone passage gets 37 ruled rows and at most MAX_ROW_LABELS
    names — the cap stays, the rows the cap skips get the second tone."""
    png = tmp_path / "wide.png"
    render_piano_roll(list(WIDE_PASSAGE), png, PAL_FPS)
    pixels, (width, _) = _pixels(png)
    rows = _midi("A#4") - _midi("D2") + 1 + 2 * NOTE_RANGE_PADDING

    ruled = _ruled_rows(pixels, width)
    assert len(ruled) == rows, "not every semitone row is ruled"
    labelled = sorted(y for y, tone in ruled.items() if tone == ROLL_GRID)
    assert 0 < len(labelled) <= MAX_ROW_LABELS
    assert len(ruled) > len(labelled), "the unlabelled rows are not drawn"

    spacing = {b - a for a, b in zip(sorted(ruled), sorted(ruled)[1:], strict=False)}
    assert spacing == {max(spacing)} and max(spacing) >= MIN_ROW_HEIGHT, \
        "the ruled rows are not evenly spaced, so counting them means nothing"


def test_render_piano_roll_lets_an_unlabelled_bar_be_named_by_counting_rows(tmp_path):
    """The todo item's own test, run on pixels: take the bar the roll never
    labels, count ruled rows up to the nearest printed name, read that name out
    of the gutter, and arrive at F3 without the event list."""
    png = tmp_path / "wide.png"
    render_piano_roll(list(WIDE_PASSAGE), png, PAL_FPS)
    pixels, (width, _) = _pixels(png)
    ruled = _ruled_rows(pixels, width)
    step = min(b - a for a, b in zip(sorted(ruled), sorted(ruled)[1:], strict=False))

    blue = sorted(_plot_rows(png, 2))
    assert blue, "voice 3's bar is missing"
    # The bar sits in the row that ends at the next ruled line below it.
    bar_row = min(y for y in ruled if y > max(blue))
    assert ruled[bar_row] == ROLL_GRID_UNLABELLED, \
        "the bar under test is on a labelled row, so this proves nothing"

    label_row = max(y for y, tone in ruled.items()
                    if tone == ROLL_GRID and y < bar_row)
    name = _read_label(pixels, label_row - step + 1)
    assert name is not None, "no note name is printed beside that ruled row"
    counted = (bar_row - label_row) // step
    assert _midi_name(_midi(name) - counted) == UNLABELLED_BAR


# --- wav_metrics ----------------------------------------------------------

RATE = 44100


def _write_wav(path, samples, rate=RATE, channels=1, width=2):
    """A PCM WAV from full-scale floats in [-1, 1] (interleaved if stereo)."""
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(np.round(np.asarray(samples) * 32767).astype("<i2").tobytes())
    return path


def _write_codes(path, codes, rate=RATE, width=2):
    """A PCM WAV from raw sample CODES rather than floats, so a test can sit
    on one exact quantization step of a threshold."""
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(np.asarray(codes, dtype="u1" if width == 1 else "<i2").tobytes())
    return path


def _tone(seconds, hz=440.0, amplitude=0.5, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    return amplitude * np.sin(2 * np.pi * hz * t)


def test_wav_metrics_tone_has_no_clipping_and_no_silence(tmp_path):
    """A half-amplitude sine sits at 20*log10(0.5/sqrt(2)) = -9.03 dBFS."""
    metrics = wav_metrics(_write_wav(tmp_path / "tone.wav", _tone(1.0)))
    assert metrics["duration_s"] == pytest.approx(1.0)
    assert metrics["clipped_samples"] == 0
    assert metrics["silence_windows"] == []
    assert len(metrics["rms_db_profile"]) == 10
    for db in metrics["rms_db_profile"]:
        assert db == pytest.approx(-9.03, abs=0.05)


def test_wav_metrics_full_scale_tone_is_three_db_louder(tmp_path):
    """Doubling amplitude adds 6.02 dB: -9.03 -> -3.01 dBFS."""
    metrics = wav_metrics(_write_wav(tmp_path / "tone.wav", _tone(0.5, amplitude=1.0)))
    for db in metrics["rms_db_profile"]:
        assert db == pytest.approx(-3.01, abs=0.05)


def test_wav_metrics_silence_is_one_full_length_window(tmp_path):
    metrics = wav_metrics(_write_wav(tmp_path / "silence.wav", np.zeros(RATE)))
    assert metrics["silence_windows"] == [pytest.approx((0.0, 1.0))]
    assert metrics["clipped_samples"] == 0
    assert all(db < -60 for db in metrics["rms_db_profile"])


def test_wav_metrics_counts_clipped_samples(tmp_path):
    """A full-scale square wave sits at every sample on the rails."""
    square = np.sign(np.sin(2 * np.pi * 440.0 * np.arange(RATE) / RATE))
    metrics = wav_metrics(_write_wav(tmp_path / "clipped.wav", square))
    assert metrics["clipped_samples"] > 0
    assert metrics["clipped_samples"] == RATE - np.count_nonzero(square == 0)


def test_wav_metrics_finds_an_interior_silence(tmp_path):
    samples = np.concatenate([_tone(0.5), np.zeros(RATE // 2), _tone(0.5)])
    metrics = wav_metrics(_write_wav(tmp_path / "gap.wav", samples))
    assert metrics["silence_windows"] == [pytest.approx((0.5, 1.0))]


def test_wav_metrics_ignores_a_silence_shorter_than_the_minimum(tmp_path):
    """0.2 s of nothing is a musical gap, not a dropout."""
    samples = np.concatenate([_tone(0.5), np.zeros(int(0.2 * RATE)), _tone(0.5)])
    assert wav_metrics(_write_wav(tmp_path / "gap.wav", samples))["silence_windows"] == []


def test_wav_metrics_reports_a_silence_of_exactly_the_minimum(tmp_path):
    """MIN_SILENCE_S is 0.25 s and the comparison is inclusive.

    Exactly 0.25 s is only reachable at the END of a file — the profile's
    resolution is 0.1 s, so an interior run is always a multiple of that, and
    only the last window is clamped to the real sample count. 22050 tone
    samples then 11025 silent ones is 0.5 s to 0.75 s exactly.
    """
    samples = np.concatenate([_tone(0.5), np.zeros(int(0.25 * RATE))])
    metrics = wav_metrics(_write_wav(tmp_path / "tail.wav", samples))
    assert metrics["silence_windows"] == [pytest.approx((0.5, 0.75))]


def test_wav_metrics_ignores_a_trailing_silence_just_under_the_minimum(tmp_path):
    """0.24 s: one hundredth short, on the same clamped-tail path."""
    samples = np.concatenate([_tone(0.5), np.zeros(int(0.24 * RATE))])
    assert wav_metrics(_write_wav(tmp_path / "tail.wav", samples))["silence_windows"] == []


def test_wav_metrics_silence_level_boundary_sits_between_two_16_bit_codes(tmp_path):
    """SILENCE_DB is -60.0 dBFS, tested strictly (`<`), and the silence
    fixtures elsewhere all sit at -120 — so the LEVEL half of the threshold
    was never exercised at all.

    Exactly -60.000 dBFS is not representable: it needs a mean square of
    1073.741824 in 16-bit codes. The tightest the boundary can be pinned is
    the adjacent pair that straddles it — code 32 is 20*log10(32/32768) =
    -60.21 dBFS and silent, code 33 is -59.94 dBFS and is not.
    """
    quiet = _write_codes(tmp_path / "quiet.wav", [32] * RATE)
    loud = _write_codes(tmp_path / "loud.wav", [33] * RATE)
    assert wav_metrics(quiet)["rms_db_profile"][0] == pytest.approx(-60.21, abs=0.01)
    assert wav_metrics(loud)["rms_db_profile"][0] == pytest.approx(-59.94, abs=0.01)
    assert wav_metrics(quiet)["silence_windows"] == [pytest.approx((0.0, 1.0))]
    assert wav_metrics(loud)["silence_windows"] == []


def test_wav_metrics_detects_clipping_at_8_bit_positive_full_scale(tmp_path):
    """8-bit unsigned tops out at code 255 = +127/128 = 0.9922 of full scale,
    which a flat 0.999 threshold could never reach: positive clipping in the
    one width `SAMPLE_DTYPES` advertises besides 16-bit was undetectable, and
    only the negative rail (code 0) ever counted."""
    metrics = wav_metrics(_write_codes(tmp_path / "hot.wav", [255, 0] * 500, width=1))
    assert metrics["clipped_samples"] == 1000


def test_wav_metrics_does_not_call_a_loud_8_bit_sample_clipped(tmp_path):
    """Threshold, not "anything above the midpoint": +-0.5625 is not clipping."""
    metrics = wav_metrics(_write_codes(tmp_path / "warm.wav", [200, 56] * 500, width=1))
    assert metrics["clipped_samples"] == 0


def test_wav_metrics_keeps_8_bit_silence_silent(tmp_path):
    """Code 128 is the format's zero, and it has to stay there. Re-centring
    the rails on 127.5 to make them symmetric — the other way of fixing the
    clipping asymmetry above — would give 8-bit silence a -48 dBFS DC offset
    and stop it registering as silence at all."""
    metrics = wav_metrics(_write_codes(tmp_path / "quiet8.wav", [128] * RATE, width=1))
    assert metrics["rms_db_profile"][0] == -120.0
    assert metrics["silence_windows"] == [pytest.approx((0.0, 1.0))]
    assert metrics["clipped_samples"] == 0


def test_wav_metrics_mixes_stereo_channels_to_mono(tmp_path):
    """One silent channel halves the amplitude: -9.03 dBFS becomes -15.05."""
    mono = _tone(1.0)
    stereo = np.stack([mono, np.zeros_like(mono)], axis=1).reshape(-1)
    metrics = wav_metrics(_write_wav(tmp_path / "stereo.wav", stereo, channels=2))
    assert metrics["duration_s"] == pytest.approx(1.0)
    for db in metrics["rms_db_profile"]:
        assert db == pytest.approx(-15.05, abs=0.05)


def test_wav_metrics_handles_a_wav_with_no_frames(tmp_path):
    metrics = wav_metrics(_write_wav(tmp_path / "empty.wav", np.zeros(0)))
    assert metrics["duration_s"] == 0.0
    assert metrics["clipped_samples"] == 0
    assert metrics["rms_db_profile"] == []
    assert metrics["silence_windows"] == []


def test_wav_metrics_rejects_an_unsupported_sample_width(tmp_path):
    path = tmp_path / "24bit.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(3)
        out.setframerate(RATE)
        out.writeframes(b"\x00\x00\x00" * 100)
    with pytest.raises(ValueError, match="24-bit"):
        wav_metrics(path)


# --- wav_metrics: a header that outruns the samples ------------------------

def _claim_frames(path, frames, width=2, channels=1):
    """Rewrite a finished WAV's RIFF and data sizes to claim `frames` frames.

    What VICE leaves on disk until the recorder's close is serviced: both size
    fields are placeholders, so `wave` reports a frame count the file does not
    hold (`audio._wav_finalized` is the check that spots it). The capture path
    waits it out; `c64 audio report --wav` and MCP `c64_sid_report` read the
    file exactly as it is. Canonical 44-byte PCM header — what the `wave`
    writer these fixtures use emits, and what VICE writes.
    """
    raw = bytearray(Path(path).read_bytes())
    data = frames * width * channels
    raw[4:8] = (data + 36).to_bytes(4, "little")
    raw[40:44] = data.to_bytes(4, "little")
    Path(path).write_bytes(bytes(raw))
    return path


def _truncated_metrics(tmp_path, seconds=1.0, claimed_s=30.0):
    """`wav_metrics` of `seconds` of digital silence under a header claiming
    `claimed_s` — the 1.0.0 review's reproduction, measured end to end."""
    path = _write_wav(tmp_path / "cut.wav", np.zeros(int(seconds * RATE)))
    return wav_metrics(_claim_frames(path, int(claimed_s * RATE)))


def test_wav_metrics_measures_the_samples_not_the_header_claim(tmp_path):
    """1 s of samples under a header claiming 30 s. `duration_s` is the
    DECODED length because every verdict divides by it; the header's claim is
    kept beside it, since the two disagreeing is itself the finding."""
    metrics = _truncated_metrics(tmp_path)
    assert metrics["duration_s"] == pytest.approx(1.0)
    assert metrics["header_duration_s"] == pytest.approx(30.0)
    assert metrics["truncated"] is True


def test_wav_metrics_calls_a_finalized_capture_untruncated(tmp_path):
    """The regression half: a normal capture's two durations agree exactly,
    and nothing about it is flagged."""
    metrics = wav_metrics(_write_wav(tmp_path / "tone.wav", _tone(1.0)))
    assert metrics["truncated"] is False
    assert metrics["header_duration_s"] == metrics["duration_s"] == pytest.approx(1.0)


def test_wav_metrics_silence_covers_a_truncated_file_end_to_end(tmp_path):
    """Silence was always measured on the samples while `duration_s` came off
    the header, so 1 s of silence under a 30 s claim covered 3% of the
    "duration" and could never reach `ALL_SILENT_COVERAGE`."""
    metrics = _truncated_metrics(tmp_path)
    assert metrics["silence_windows"] == [pytest.approx((0.0, 1.0))]
    covered = sum(end - start for start, end in metrics["silence_windows"])
    assert covered >= metrics["duration_s"] * sid_analysis.ALL_SILENT_COVERAGE


def test_wav_metrics_reads_a_wav_cut_mid_frame(tmp_path):
    """A file that lost its tail can end inside a sample: `frombuffer` refuses
    a buffer that is not a whole number of samples, so a re-score of one used
    to come out as a traceback. The partial frame is dropped instead — and
    three lost bytes are not a truncated capture."""
    path = _write_wav(tmp_path / "cut.wav", np.zeros(RATE))
    raw = path.read_bytes()
    path.write_bytes(raw[:-3])
    metrics = wav_metrics(path)
    assert metrics["duration_s"] == pytest.approx(44098 / RATE)
    assert metrics["truncated"] is False


# --- dominant_partial_hz --------------------------------------------------

def test_dominant_partial_hz_finds_a_synthesized_tone(tmp_path):
    """One second at 44100 gives 1 Hz bins, so a 440 Hz tone is bin 440."""
    out = dominant_partial_hz(_write_wav(tmp_path / "tone.wav", _tone(1.0, hz=440.0)))
    assert out["bin"] == 440
    assert out["bin_hz"] == pytest.approx(1.0)
    assert out["peak_hz"] == pytest.approx(440.0)
    assert out["seconds"] == pytest.approx(1.0)
    assert out["resolution_cents"] == pytest.approx(
        1200 * math.log2(440.5 / 440.0), rel=1e-9)


def test_dominant_partial_hz_ignores_a_dc_offset(tmp_path):
    """A level offset is not a partial, and it is often the largest bin: 0.7
    of DC over a second is 30870 in bin 0 against the tone's 4410."""
    samples = _tone(1.0, hz=1000.0, amplitude=0.2) + 0.7
    assert dominant_partial_hz(_write_wav(tmp_path / "dc.wav", samples))["bin"] == 1000


def test_dominant_partial_hz_reports_silence_as_no_partial(tmp_path):
    out = dominant_partial_hz(_write_wav(tmp_path / "silence.wav", np.zeros(RATE)))
    assert out["peak_hz"] == 0.0
    assert out["resolution_cents"] is None


def test_dominant_partial_hz_refuses_a_wav_with_no_samples(tmp_path):
    with pytest.raises(ValueError, match="no samples"):
        dominant_partial_hz(_write_wav(tmp_path / "empty.wav", np.zeros(0)))


def test_dominant_partial_hz_reproduces_the_alignment_gates_measurement(tmp_path):
    """The branch's central evidence, re-derivable from the repo at last.

    `audio.py`'s module docstring rests on a live capture whose registers
    predicted 440.0041 Hz and whose WAV's dominant partial fell in the bin
    holding that prediction. The probe that measured it was a scratch script,
    deleted with its WAV — so the numbers it quotes (0.4788 Hz bins over
    100256 samples of 48 kHz, bin 919, +-0.94 cents) could not be checked
    against anything. Same geometry, synthesized: same bin, same resolution.
    """
    rate, frames = 48000, 100256
    tone = 0.5 * np.sin(2 * np.pi * 440.0041 * np.arange(frames) / rate)
    out = dominant_partial_hz(_write_wav(tmp_path / "a4.wav", tone, rate=rate))
    assert out["bin"] == 919
    assert out["bin_hz"] == pytest.approx(0.4788, abs=0.0001)
    assert out["peak_hz"] == pytest.approx(439.9937, abs=0.0005)
    assert out["resolution_cents"] == pytest.approx(0.94, abs=0.005)


# --- render_spectrogram ---------------------------------------------------

def _brightest_row_fraction(path):
    """Where the loudest horizontal band sits, 0.0 = top of the image."""
    with Image.open(path) as img:
        rows = np.asarray(img.convert("L"), dtype=float).sum(axis=1)
    return int(np.argmax(rows)) / len(rows)


def test_render_spectrogram_writes_a_png(tmp_path):
    png = tmp_path / "spectrogram.png"
    render_spectrogram(_write_wav(tmp_path / "tone.wav", _tone(1.0)), png)
    assert png.exists() and png.stat().st_size > 0
    with Image.open(png) as img:
        assert img.size >= MIN_ROLL_SIZE
        assert img.format == "PNG"


def test_render_spectrogram_places_a_tone_at_its_frequency(tmp_path):
    """The Y axis runs 0-8 kHz bottom to top, so 1 kHz sits low and 6 kHz high."""
    low = tmp_path / "low.png"
    high = tmp_path / "high.png"
    render_spectrogram(_write_wav(tmp_path / "low.wav", _tone(1.0, hz=1000.0)), low)
    render_spectrogram(_write_wav(tmp_path / "high.wav", _tone(1.0, hz=6000.0)), high)

    assert _brightest_row_fraction(low) == pytest.approx(1 - 1000 / 8000, abs=0.05)
    assert _brightest_row_fraction(high) == pytest.approx(1 - 6000 / 8000, abs=0.05)


def test_render_spectrogram_renders_a_silent_recording_dark(tmp_path):
    """Silence must not normalize against itself into a solid bright field.

    A warped capture writes a silent (or zero-frame) WAV — the one failure this
    tooling exists to catch. Rendering it as the visual signature of loud
    broadband noise would tell an agent the exact opposite of the truth.
    """
    for name, samples in (("silence", np.zeros(RATE)), ("zero-frame", np.zeros(0))):
        png = tmp_path / f"{name}.png"
        render_spectrogram(_write_wav(tmp_path / f"{name}.wav", samples), png)
        with Image.open(png) as img:
            luminance = np.asarray(img.convert("L"), dtype=float)
        assert luminance.max() < 32, f"{name} rendered bright (max {luminance.max():.0f})"


def test_render_spectrogram_still_normalizes_a_quiet_recording(tmp_path):
    """The silence floor must not flatten a real but quiet signal.

    One LSB of 16-bit headroom is still a signal; only degenerate silence may
    reach the floor.
    """
    quiet = tmp_path / "quiet.png"
    render_spectrogram(
        _write_wav(tmp_path / "quiet.wav", _tone(1.0, hz=1000.0, amplitude=2 / 32768)),
        quiet,
    )
    assert _brightest_row_fraction(quiet) == pytest.approx(1 - 1000 / 8000, abs=0.05)
    with Image.open(quiet) as img:
        assert np.asarray(img.convert("L"), dtype=float).max() > 200


def test_render_spectrogram_widens_its_hop_instead_of_growing_without_limit(
        tmp_path, monkeypatch):
    """Columns used to scale with the recording, and so did the arrays behind
    them: a 60 s capture at the 48 kHz VICE records asked for 5624 columns and
    about 46 MB each of windowed samples and rFFT output. Past
    MAX_SPECTROGRAM_WIDTH the hop widens instead, the way the roll's
    MAX_ROLL_WIDTH shares columns.

    Exercised at a lowered cap: the shipped 4096 does not engage until about
    44 s of 48 kHz audio, and synthesizing that per test run is not worth it.
    """
    wav = _write_wav(tmp_path / "long.wav", _tone(25.0, hz=1000.0))
    png = tmp_path / "long.png"

    render_spectrogram(wav, png)
    with Image.open(png) as img:
        # 25 s at 44100 is 1102500 samples: (1102500 - 1024) // 512 + 1 = 2152.
        assert img.width == 2152, "the shipped cap must not touch a real capture"

    monkeypatch.setattr(sid_analysis, "MAX_SPECTROGRAM_WIDTH", 700)
    render_spectrogram(wav, png)
    with Image.open(png) as img:
        assert MIN_ROLL_SIZE[0] <= img.width <= 700
    # The time axis still spans the whole recording, so the tone is still at
    # its own frequency rather than smeared or truncated.
    assert _brightest_row_fraction(png) == pytest.approx(1 - 1000 / 8000, abs=0.05)


def test_render_spectrogram_handles_a_wav_shorter_than_one_window(tmp_path):
    png = tmp_path / "spectrogram.png"
    render_spectrogram(_write_wav(tmp_path / "short.wav", _tone(1.0)[:100]), png)
    with Image.open(png) as img:
        assert img.size >= MIN_ROLL_SIZE


# --- write_report ---------------------------------------------------------

def _metrics(duration_s=1.0, clipped_samples=0, silence_windows=(), profile=(-9.0,) * 10):
    return {"duration_s": duration_s, "clipped_samples": clipped_samples,
            "silence_windows": [tuple(w) for w in silence_windows],
            "rms_db_profile": list(profile)}


def _report(tmp_path, events=(), diffs=(), anomalies=(), metrics=None, ref=None):
    return write_report(tmp_path, list(events), list(diffs), list(anomalies), metrics,
                        ref=ref)


SOUNDING = (_note(1, "A4", 0, 25), _note(1, "rest", 25, 25))


def test_write_report_writes_report_md_and_returns_its_path(tmp_path):
    path = _report(tmp_path, SOUNDING, metrics=_metrics())
    assert path == tmp_path / "report.md"
    assert path.exists()


def test_write_report_creates_a_missing_output_directory(tmp_path):
    path = _report(tmp_path / "run" / "nested", SOUNDING, metrics=_metrics())
    assert path.exists()


def test_write_report_has_every_section(tmp_path):
    text = _report(tmp_path, SOUNDING, metrics=_metrics()).read_text()
    for heading in ("## Transcription", "## Score diff", "## Anomalies",
                    "## WAV metrics", "## Artifacts", "## Verdict"):
        assert heading in text
    assert text.index("## Transcription") < text.index("## Score diff") \
        < text.index("## Anomalies") < text.index("## WAV metrics") \
        < text.index("## Artifacts") < text.index("## Verdict")


def test_write_report_passes_on_empty_inputs(tmp_path):
    assert "**PASS**" in _report(tmp_path, SOUNDING, metrics=_metrics()).read_text()


def test_write_report_fails_on_a_score_diff(tmp_path):
    text = _report(tmp_path, SOUNDING, diffs=["voice 1 event 1: expected C4, heard A4"],
                   metrics=_metrics()).read_text()
    assert "**FAIL**" in text
    assert "expected C4, heard A4" in text


def test_write_report_fails_on_an_anomaly(tmp_path):
    text = _report(tmp_path, SOUNDING, anomalies=["voice 1: stuck gate"],
                   metrics=_metrics()).read_text()
    assert "**FAIL**" in text
    assert "stuck gate" in text


def test_write_report_fails_on_clipping(tmp_path):
    text = _report(tmp_path, SOUNDING, metrics=_metrics(clipped_samples=12)).read_text()
    assert "**FAIL**" in text
    assert "12" in text


def test_write_report_fails_when_a_sounding_log_recorded_silence(tmp_path):
    metrics = _metrics(silence_windows=[(0.0, 1.0)], profile=(-120.0,) * 10)
    assert "**FAIL**" in _report(tmp_path, SOUNDING, metrics=metrics).read_text()


def test_write_report_passes_when_an_all_rest_log_recorded_silence(tmp_path):
    """Silence is only a failure when the register log says something sounded."""
    metrics = _metrics(silence_windows=[(0.0, 1.0)], profile=(-120.0,) * 10)
    events = [_note(v, "rest", 0, 50, waveform=0, gate_frames=0) for v in (1, 2, 3)]
    assert "**PASS**" in _report(tmp_path, events, metrics=metrics).read_text()


def test_write_report_without_metrics_is_a_render_only_run(tmp_path):
    """No reference and no WAV is a legitimate run, not a failure."""
    text = _report(tmp_path, SOUNDING).read_text()
    assert "**PASS**" in text
    assert "## WAV metrics" in text


def test_write_report_tabulates_the_notes_of_each_voice(tmp_path):
    events = [_note(1, "A4", 0, 25), _note(2, "C4", 3, 9, waveform=0x40)]
    text = _report(tmp_path, events, metrics=_metrics()).read_text()
    assert "Voice 1" in text and "Voice 2" in text
    assert "A4" in text and "C4" in text
    assert "pulse" in text


def test_write_report_prints_no_cents_for_a_noise_event(tmp_path):
    """The cents column is a tuning claim, and noise has no pitch to be in
    tune with — the note name stays (it is what the oscillator holds, and
    what the roll and the diff are positioned by), the number goes."""
    events = [NoteEvent(voice=3, note="F#4", start_frame=0, frames=43,
                        waveform=0x80, gate_frames=43, cents_off=30.1)]
    row = [line for line in _report(tmp_path, events, metrics=_metrics()
                                    ).read_text().splitlines()
           if line.startswith("| 0 |")]
    assert row == ["| 0 | 43 | F#4 | - | noise | 43 |"]


def test_write_report_still_prints_cents_for_a_pitched_event(tmp_path):
    """The same event on a pulse waveform keeps its number, so the dash above
    is about the waveform and not about the column having been emptied."""
    events = [NoteEvent(voice=3, note="F#4", start_frame=0, frames=43,
                        waveform=0x40, gate_frames=43, cents_off=30.1)]
    row = [line for line in _report(tmp_path, events, metrics=_metrics()
                                    ).read_text().splitlines()
           if line.startswith("| 0 |")]
    assert row == ["| 0 | 43 | F#4 | +30.1 | pulse | 43 |"]


ALL_REST = tuple(_note(v, "rest", 0, 50, waveform=0, gate_frames=0) for v in (1, 2, 3))


def test_write_report_says_so_when_nothing_played(tmp_path):
    """The attract-screen capture: no voice gated, the WAV silent throughout.
    Still a PASS — nothing sounded, so no check had anything to disagree with
    — but a bare PASS there tells an agent whose program never started that
    everything is fine, so the pass says what it is passing on."""
    metrics = _metrics(silence_windows=[(0.0, 1.0)], profile=(-120.0,) * 10)
    text = _report(tmp_path, ALL_REST, metrics=metrics).read_text()
    assert "**PASS**" in text
    assert "**Nothing played.**" in text          # under the verdict
    assert "**No voice sounded.**" in text        # and above the transcription
    assert "the recording is silent from end to end" in text


def test_write_report_does_not_say_nothing_played_when_a_voice_sounded(tmp_path):
    text = _report(tmp_path, SOUNDING, metrics=_metrics()).read_text()
    assert "Nothing played" not in text and "No voice sounded" not in text


def test_write_report_does_not_call_a_silent_log_over_an_audible_wav_silent(tmp_path):
    """No gated voice over a WAV with audio in it is `$D418` sample playback,
    which this transcription cannot see. The transcription reports what it
    read; the verdict does not claim nothing played when the recording
    disagrees."""
    text = _report(tmp_path, ALL_REST, metrics=_metrics()).read_text()
    assert "**No voice sounded.**" in text
    assert "Nothing played" not in text


def test_write_report_says_nothing_played_on_a_register_only_run(tmp_path):
    """No WAV to corroborate, so the notice makes the claim it can: the log
    is what says nothing played, and the sentence does not invent a silent
    recording that was never measured."""
    text = _report(tmp_path, ALL_REST).read_text()
    assert "**Nothing played.**" in text
    assert "the recording is silent" not in text


def test_write_report_says_nothing_played_for_an_empty_log(tmp_path):
    text = _report(tmp_path).read_text()
    assert "the register log was empty" in text
    assert "**Nothing played.**" in text


def test_write_report_nothing_played_notice_is_not_a_verdict_reason(tmp_path):
    """The reasons under a verdict are `- ` bullets that a front end reads
    back out of this file. The notice is a block quote so that a PASS with a
    notice still has no reasons — and so a FAIL's reasons stay countable."""
    metrics = _metrics(silence_windows=[(0.0, 1.0)], profile=(-120.0,) * 10)
    verdict = _report(tmp_path, ALL_REST, metrics=metrics).read_text()
    body = verdict[verdict.index("## Verdict"):]
    assert "**Nothing played.**" in body
    assert [line for line in body.splitlines() if line.startswith("- ")] == []


def test_write_report_links_only_the_artifacts_that_exist(tmp_path):
    (tmp_path / "piano-roll.png").write_bytes(b"")
    text = _report(tmp_path, SOUNDING, metrics=_metrics()).read_text()
    assert "(piano-roll.png)" in text
    assert "spectrogram.png" not in text


def test_write_report_reports_the_wav_metrics(tmp_path):
    """Asserted as whole rendered table cells. A bare `"2.5" in text` matches
    any 2.5 anywhere in the report — a cents offset, a frame count, a piece of
    the RMS line — so it could pass with the metrics table empty."""
    metrics = _metrics(duration_s=2.5, clipped_samples=7,
                       silence_windows=[(1.0, 1.5)], profile=(-9.0, -12.0, -3.0))
    text = _report(tmp_path, SOUNDING, metrics=metrics).read_text()
    assert "| Duration | 2.50 s |" in text
    assert "| Clipped samples | 7 |" in text
    assert "| Silence windows | 1.00-1.50 s |" in text
    assert "| RMS min / median / max | -12.0 / -9.0 / -3.0 dBFS over 3 windows of 0.1 s |" \
        in text


def test_write_report_names_a_recording_that_never_happened(tmp_path):
    """Right verdict, wrong sentence: a WAV with a header and no frames is
    the warp signature, and "the recording is silent" sends its owner looking
    at $D418 and the filter instead of at the speed pin."""
    metrics = _metrics(duration_s=0.0, profile=(), silence_windows=())
    text = _report(tmp_path, SOUNDING, metrics=metrics).read_text()
    assert "**FAIL**" in text
    assert "no samples at all" in text
    assert "the recording is silent" not in text


def test_write_report_still_says_silent_when_the_recording_really_ran(tmp_path):
    """The other half of the same branch, so the two sentences stay distinct."""
    metrics = _metrics(duration_s=1.0, silence_windows=[(0.0, 1.0)],
                       profile=(-120.0,) * 10)
    text = _report(tmp_path, SOUNDING, metrics=metrics).read_text()
    assert "the recording is silent" in text
    assert "no samples at all" not in text


# --- write_report: a WAV whose header outruns its samples ------------------

def test_nothing_played_is_not_defeated_by_a_lying_header(tmp_path):
    """Silence coverage is measured against the samples that exist, so a dead
    capture reads as dead however long its header says it is."""
    assert nothing_played(ALL_REST, _truncated_metrics(tmp_path)) is True


def test_write_report_fails_dead_audio_under_a_lying_header(tmp_path):
    """The 1.0.0 review's reproduction: a header claiming 30 s over 1 s of
    silent samples. Coverage was measured against the header's 30 s, so 1 s of
    silence cleared the 99% test, `nothing_played` came back false, and a
    capture with no audio in it at all was reported **PASS** with no notice."""
    text = _report(tmp_path, ALL_REST, metrics=_truncated_metrics(tmp_path)).read_text()
    assert "**FAIL**" in text
    assert "- the recording is truncated" in text
    assert "**Nothing played.**" in text


def test_write_report_names_both_durations_for_a_truncated_capture(tmp_path):
    """Asserted as whole rendered cells: the measured length is the one the
    other metrics cover, and the header's claim is shown beside it rather than
    quietly replaced."""
    text = _report(tmp_path, ALL_REST, metrics=_truncated_metrics(tmp_path)).read_text()
    assert "| Duration | 1.00 s |" in text
    assert "| Header duration | 30.00 s — 29.00 s of it is not in the file |" in text


def test_write_report_metrics_table_omits_the_header_duration_when_finished(tmp_path):
    """A finalized capture's table and verdict are untouched by any of this."""
    metrics = wav_metrics(_write_wav(tmp_path / "tone.wav", _tone(1.0)))
    text = _report(tmp_path, SOUNDING, metrics=metrics).read_text()
    assert "| Duration | 1.00 s |" in text
    assert "Header duration" not in text
    assert "truncated" not in text
    assert "**PASS**" in text


def test_write_report_names_a_header_only_wav_read_through_the_rescore_path(tmp_path):
    """The warp signature — a placeholder header over zero frames — reaching
    `wav_metrics` with nobody having waited for VICE to finalize. Measured off
    the header it was 30 s of audio nobody had examined and produced no
    failure at all; measured off the samples it is the recording that never
    happened, which is the sentence that names the speed pin."""
    text = _report(tmp_path, SOUNDING,
                   metrics=_truncated_metrics(tmp_path, seconds=0.0)).read_text()
    assert "**FAIL**" in text
    assert "no samples at all" in text
    assert "- the recording is truncated" in text


# --- write_report: what the Score-diff section says it checked -------------

#: One sounding entry, one rest, and a voice claiming silence: enough shape for
#: the summary table to have something to say about each column.
REF_YAML = """\
voices:
  1:
    - {note: A4, frames: 25}
    - {note: rest}
  2: []
"""


def _ref(tmp_path, text=REF_YAML, name="score.yaml"):
    path = tmp_path / name
    path.write_text(text)
    return path


def _score_diff_section(text):
    """The report's Score-diff section, up to the next heading."""
    assert "## Score diff\n" in text
    return text.split("## Score diff\n", 1)[1].split("\n## ", 1)[0]


def test_write_report_names_the_reference_score_it_diffed_against(tmp_path):
    ref = _ref(tmp_path)
    section = _score_diff_section(
        _report(tmp_path, SOUNDING, metrics=_metrics(), ref=ref).read_text())
    assert str(ref) in section


def test_write_report_quotes_the_reference_scores_own_counts(tmp_path):
    """Asserted against `score_summary`'s output, not against literals: the
    report has to be quoting that function rather than counting the file a
    second time, which is the way the two could ever disagree."""
    ref = _ref(tmp_path)
    summary = score_summary(ref)
    section = _score_diff_section(
        _report(tmp_path, SOUNDING, metrics=_metrics(), ref=ref).read_text())
    for voice, claim in summary["voices"].items():
        assert (f"| {voice} | {claim['entries']} | {claim['frames']} |") in section
    assert f"{summary['entries']} entries" in section
    assert f"{summary['frames']} frames" in section


def test_write_report_says_when_no_reference_score_was_supplied(tmp_path):
    """The finding itself: an unscored run must not read as a clean check."""
    section = _score_diff_section(
        _report(tmp_path, SOUNDING, metrics=_metrics()).read_text())
    assert "No reference score supplied" in section
    assert "No differences" not in section


def test_write_report_score_section_differs_with_and_without_a_reference(tmp_path):
    """The todo item's verification at unit scale: same events, two reports,
    and the Score-diff sections must not read the same."""
    ref = _ref(tmp_path)
    scored = _score_diff_section(
        _report(tmp_path / "scored", SOUNDING, metrics=_metrics(), ref=ref).read_text())
    unscored = _score_diff_section(
        _report(tmp_path / "plain", SOUNDING, metrics=_metrics()).read_text())
    assert scored != unscored
    assert str(ref) in scored and str(ref) not in unscored


def test_write_report_does_not_hedge_a_clean_diff_that_had_a_reference(tmp_path):
    """The sentence this replaces — "an empty diff list is also what a run with
    no reference score produces" — was the whole finding: it made the strongest
    audio evidence a demo can commit unreadable as evidence."""
    section = _score_diff_section(
        _report(tmp_path, SOUNDING, metrics=_metrics(), ref=_ref(tmp_path)).read_text())
    assert "with no reference score" not in section
    assert "No differences" in section


def test_write_report_lists_the_diffs_under_the_reference_it_names(tmp_path):
    ref = _ref(tmp_path)
    text = _report(tmp_path, SOUNDING, diffs=["voice 1 event 1: expected C4, heard A4"],
                   metrics=_metrics(), ref=ref).read_text()
    section = _score_diff_section(text)
    assert str(ref) in section
    assert "- voice 1 event 1: expected C4, heard A4" in section
    assert "**FAIL**" in text


def test_write_report_does_not_call_an_inline_score_a_file(tmp_path):
    """A library caller can hand the writer a parsed score; printing a path
    there would be a citation to a file that does not exist."""
    section = _score_diff_section(
        _report(tmp_path, SOUNDING, metrics=_metrics(),
                ref={"voices": {1: [{"note": "A4", "frames": 25}]}}).read_text())
    assert "not a file" in section
    assert "| 1 | 1 | 25 | A4 | A4 |" in section


def test_write_report_survives_a_reference_it_cannot_summarise(tmp_path):
    """`diff_score` only reads an entry's `frames` when its NOTE matched, so a
    wrong note with a non-numeric duration diffs fine and summarises not at
    all. Losing the finished report at its last line over that would throw the
    capture away; the section says what happened instead."""
    ref = _ref(tmp_path, "voices:\n  1:\n    - {note: C4, frames: soon}\n", "bad.yaml")
    text = _report(tmp_path, SOUNDING, diffs=["voice 1 event 1: expected C4, heard A4"],
                   metrics=_metrics(), ref=ref).read_text()
    assert "could not be summarised" in _score_diff_section(text)
    assert str(ref) in text
    assert "**FAIL**" in text
