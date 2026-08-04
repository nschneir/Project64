"""Pure-analysis tests: no VICE, no session, no daemon.

Register logs are built in-memory by ``_log`` from per-voice ``(reg16,
control)`` states, so every expectation below is traceable to the exact SID
register values a capture would have recorded. WAVs are synthesized the same
way by ``_write_wav``, so the expected metrics are arithmetic on the tone that
was written, not a restatement of the implementation.
"""

import json
import wave

import numpy as np
import pytest
from PIL import Image

from c64lib.sid_analysis import (
    FrameRecord,
    NoteEvent,
    diff_score,
    find_anomalies,
    freq_to_note,
    parse_log,
    render_piano_roll,
    render_spectrogram,
    transcribe,
    wav_metrics,
    write_report,
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


# --- render_piano_roll ----------------------------------------------------

MIN_ROLL_SIZE = (640, 240)
PAL_FPS = 50


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


def test_render_piano_roll_colors_voice_1_red_2_green_3_blue(tmp_path):
    """The pinned voice->colour mapping, measured on bars rather than chrome.

    The legend paints all three voice colours on every render, so presence of a
    colour proves nothing. Each voice is rendered alone at the same pitch and
    frame span — which makes the image geometry, and therefore the legend,
    byte-identical to the all-rest baseline — and scored as the *increase* over
    that baseline. The `== baseline` assertions on the other two channels are
    what make swapping voice 2 and voice 3 fail.
    """
    span = 40
    baseline = _voice_colour_counts(tmp_path / "rest.png", [_note(1, "rest", 0, span)])
    assert all(count > 0 for count in baseline), "legend should paint all three colours"

    for voice, channel in ((1, 0), (2, 1), (3, 2)):
        counts = _voice_colour_counts(tmp_path / f"voice{voice}.png",
                                      [_note(voice, "C4", 0, span)])
        for other in range(3):
            if other == channel:
                assert counts[other] > baseline[other] * 10, (
                    f"voice {voice} should add a large bar in channel {channel}"
                )
            else:
                assert counts[other] == baseline[other], (
                    f"voice {voice} painted channel {other}, which belongs to another voice"
                )


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


def _report(tmp_path, events=(), diffs=(), anomalies=(), metrics=None):
    return write_report(tmp_path, list(events), list(diffs), list(anomalies), metrics)


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


def test_write_report_links_only_the_artifacts_that_exist(tmp_path):
    (tmp_path / "piano-roll.png").write_bytes(b"")
    text = _report(tmp_path, SOUNDING, metrics=_metrics()).read_text()
    assert "(piano-roll.png)" in text
    assert "spectrogram.png" not in text


def test_write_report_reports_the_wav_metrics(tmp_path):
    metrics = _metrics(duration_s=2.5, silence_windows=[(1.0, 1.5)])
    text = _report(tmp_path, SOUNDING, metrics=metrics).read_text()
    assert "2.5" in text
    assert "1.0" in text and "1.5" in text
