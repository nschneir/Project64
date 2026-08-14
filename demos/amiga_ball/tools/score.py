#!/usr/bin/env python3
"""score.py -- the reference scores for the two audio captures (SPEC.md 13.2).

The score is the CLAIM and the capture is the check, so this file is written
from the demo's own constants -- the frequency words `sndattack` writes, the
frame `tools/audio-evidence.sh` releases `freeze` on, and the `snd_timer == 20`
gate-off in `sound_step` -- and never from a transcription.  A score fitted to
what a capture reported cannot fail, and a check that cannot fail is not
evidence (`docs/cli.md`, `c64 audio report`).

Three decisions are worth stating, because each one is a claim about what
pitch analysis can settle:

  * **Voice 1 is scored** -- the pitched thump, one note per impact.  Its
    note name is DERIVED here from the 16-bit frequency word in `sound.s`
    through the SID's own formula (`hz = reg16 * clock / 2**24`), not typed
    in beside it, so a table built for the wrong clock fails this script
    rather than being written into the score and passing the capture.

  * **Voice 3 is `[]`** -- the positive claim "this voice sits out the
    window".  `sound_init` zeroes it and nothing writes it again, and an
    empty list is what makes the report check that, where omitting the voice
    would check nothing (SPEC.md 8, criterion 20).

  * **Voice 2 is OMITTED** -- it is noise.  The SID's noise generator is an
    LFSR clocked by the oscillator, so `$D407/$D408` sets how bright the hiss
    is and not what pitch it is; there is no pitch for a diff to be right or
    wrong about.  `skills/c64-development/references/audio-verification.md`
    makes the same point from the tool's side (the report's cents column
    reads `-` for noise).  Voice 2's evidence is the spectrogram, where the
    transient and the filter's downward sweep are visible and the piano roll
    cannot show them (criterion 22).

The model is `audio-verification.md`'s two-step recipe, the one
`demos/la-galaxia/tools/genmusic.py` follows: emit the note name a
once-per-frame sampler would read on each frame of the window, then
run-length encode that list.  It agrees with the transcriber by construction
because it is the same algorithm run from the other side -- and it still
fails on a program that gates the wrong voice or writes the wrong word,
because its input is `sound.s`'s constants rather than the log.

    python3 demos/amiga_ball/tools/score.py
    python3 demos/amiga_ball/tools/score.py --print floor
"""

import argparse
import math
import sys
from pathlib import Path

# --- the constants this scores against -------------------------------------

#: NTSC, and only NTSC.  `Fn = hz * 2**24 / CLOCK_HZ`; the demo is an NTSC
#: program (SPEC.md 8) and the same words on a PAL machine are 65 cents sharp.
CLOCK_HZ = 1022727
FPS = 60

#: The frame `audio-evidence.sh` clears `freeze` on, with `--at-frame`.
RELEASE_FRAME = 12

#: Samples between that write and the first sample showing the SID writes the
#: program made because of it.  ONE, and the reason is the sampler's phase
#: against this demo's raster interrupt rather than anything musical.
#:
#: `_sample_frames_client` in `src/c64lib/audio.py` is write / resume / read,
#: and every binary-monitor halt is at raster line 12 (`audio.py`'s module
#: docstring: 600 consecutive reads, all 12).  This demo's tick runs from the
#: raster interrupt at line 10, so at the halt the frame's `ball_step` has
#: already read `freeze` and its `sound_step` -- tens of lines further down --
#: has not yet written the SID.  So a scheduled write to a STATE byte is seen
#: by the next frame's tick, and the SID writes that tick makes land after
#: that frame's own sample point: `$4015=0` at frame N is heard at sample
#: N+1.  The tools' "frame N is the first logged frame whose registers show
#: them" is the other case -- a write straight to `$D4xx`, which needs no
#: frame of the program to take effect.
#:
#: Verified against the committed `sid-log.jsonl` of both captures: the first
#: sample holding `$D404 = $11` is 13 in each.
IRQ_LATENCY = 1

#: The sample the impact is first heard on.
IMPACT_SAMPLE = RELEASE_FRAME + IRQ_LATENCY

#: `sound_step`: the gate falls when `snd_timer` reaches 20, and `snd_timer`
#: is 0 on the frame of the strike -- so the gate is set on exactly 20 samples,
#: frames RELEASE_FRAME .. RELEASE_FRAME + 19.
GATE_FRAMES = 20

#: `sndattack`'s voice-1 frequency words, and the note each one is meant to
#: be.  The name is checked, not trusted: see `note_of`.
IMPACTS = {
    "floor": (0x070D, "A2"),   # 1805 -> 110.0 Hz, the heavier body
    "wall":  (0x0A90, "E3"),   # 2704 -> 164.8 Hz, the harder surface
}

#: How far off equal temperament a frequency word may be before this script
#: refuses to write a score around it.  The report's own detune anomaly fires
#: at 15 cents; a demo whose table is rounded to the nearest SID word should
#: be an order of magnitude inside that, and both of these are ~0.3 cents.
CENTS_TOLERANCE = 5.0

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
REST = "rest"


def note_of(reg16: int) -> tuple[str, float]:
    """`(note name, cents off)` for a SID frequency word on this machine.

    The transcriber's `freq_to_note` from the other side, spelled with sharps
    for the same reason: a frequency carries no key signature to choose a
    spelling from.
    """
    if reg16 <= 0:
        raise ValueError(f"frequency word must be positive, got {reg16}")
    hz = reg16 * CLOCK_HZ / 2 ** 24
    midi = 69 + 12 * math.log2(hz / 440.0)
    nearest = round(midi)
    return f"{NOTE_NAMES[nearest % 12]}{nearest // 12 - 1}", (midi - nearest) * 100


def per_frame(note: str) -> list[str]:
    """One entry per frame of the window, up to the gate-off.

    Frames past the note are not modelled: trailing silence is exempt from
    the diff, and a score that pinned it would depend on the capture landing
    exactly the number of frames it asked for.  The note's own duration is
    what asserts the release -- 20 frames and then something else.
    """
    return [REST] * IMPACT_SAMPLE + [note] * GATE_FRAMES


def events(frames: list[str]) -> list[tuple[str, int]]:
    """Run-length encode the per-frame model into `(note, frames)` entries."""
    out: list[tuple[str, int]] = []
    for name in frames:
        if out and out[-1][0] == name:
            out[-1] = (name, out[-1][1] + 1)
        else:
            out.append((name, 1))
    return out


def score_yaml(kind: str) -> str:
    """The score for one impact kind, as YAML text.

    Hand-emitted rather than dumped, so this stays stdlib-only like every
    other generator in `tools/` (PLAN.md, Global Constraints).
    """
    reg16, intended = IMPACTS[kind]
    heard, cents = note_of(reg16)
    if heard != intended:
        raise SystemExit(
            f"{kind}: ${reg16:04X} is {heard} at {CLOCK_HZ} Hz, not the {intended} "
            f"SPEC.md 8 says it is -- fix the table in sound.s, not this file")
    if abs(cents) > CENTS_TOLERANCE:
        raise SystemExit(
            f"{kind}: ${reg16:04X} is {cents:+.1f} cents off {intended}, past the "
            f"{CENTS_TOLERANCE:.0f}-cent bar -- wrong clock, or a mistyped word")

    lines = [
        "# Generated by demos/amiga_ball/tools/score.py -- do not hand-edit.",
        "#",
        f"# The {kind} impact, staged by tools/audio-evidence.sh: freeze is cleared",
        f"# at frame {RELEASE_FRAME} of the window and set again at frame {RELEASE_FRAME + 1}, so the",
        "# window holds exactly ONE frame of physics and exactly one impact -- the",
        "# other one cannot fire behind it and the schedule cannot repeat.",
        "#",
        f"# voice 1: {intended} = ${reg16:04X} = {reg16 * CLOCK_HZ / 2 ** 24:.2f} Hz",
        f"#          ({cents:+.2f} cents at the NTSC clock), gated {GATE_FRAMES} frames from",
        f"#          sample {IMPACT_SAMPLE} = frame {RELEASE_FRAME} + {IRQ_LATENCY} (see IRQ_LATENCY in score.py).",
        "# voice 2: omitted -- noise has no pitch to diff.  Its evidence is",
        "#          spectrogram.png (SPEC.md criterion 22).",
        "# voice 3: [] -- silent for the life of the run (SPEC.md criterion 20).",
        "voices:",
        "  1:",
    ]
    for name, frames in events(per_frame(intended)):
        lines.append(f"    - {{note: {name}, frames: {frames}}}")
    lines += ["  3: []", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", type=Path, default=here.parent / "evidence",
                    help="where the score YAMLs go (default: ../evidence)")
    ap.add_argument("--print", dest="show", choices=sorted(IMPACTS),
                    help="print one score to stdout and write nothing")
    args = ap.parse_args(argv)

    if args.show:
        sys.stdout.write(score_yaml(args.show))
        return 0

    args.outdir.mkdir(parents=True, exist_ok=True)
    for kind in sorted(IMPACTS):
        path = args.outdir / f"{kind}.score.yaml"
        text = score_yaml(kind)
        path.write_text(text)
        entries = len(events(per_frame(IMPACTS[kind][1])))
        print(f"{path}: voice 1 = {entries} entries over "
              f"{IMPACT_SAMPLE + GATE_FRAMES} frames, voice 3 silent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
