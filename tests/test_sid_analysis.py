"""Pure-analysis tests: no VICE, no session, no daemon.

Register logs are built in-memory by ``_log`` from per-voice ``(reg16,
control)`` states, so every expectation below is traceable to the exact SID
register values a capture would have recorded.
"""

import json

import pytest

from c64lib.sid_analysis import (
    FrameRecord,
    NoteEvent,
    diff_score,
    find_anomalies,
    freq_to_note,
    parse_log,
    transcribe,
)

PAL_CLOCK = 985248
NTSC_CLOCK = 1022727

#: reg16 values whose PAL pitches are pinned by the plan.
A4_REG = 7493        # 440.03 Hz, A4, +0.11 cents
C4_REG = 4455        # 261.62 Hz, C4, -0.03 cents
E4_REG = 5613        # 329.63 Hz, E4, -0.01 cents
A4_SHARP30_REG = 7623   # 447.66 Hz, A4 +29.9 cents — audibly out of tune

TRIANGLE_ON = 0x11   # triangle waveform + gate
TRIANGLE_OFF = 0x10  # same waveform, gate released


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


def test_diff_score_empty_voice_list_means_silent():
    events = transcribe(_log((10, {1: (C4_REG, TRIANGLE_ON)})), PAL_CLOCK)
    assert diff_score(events, {"voices": {2: [], 3: []}}) == []
    assert len(diff_score(events, {"voices": {1: []}})) == 1


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
