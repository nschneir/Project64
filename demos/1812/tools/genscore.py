#!/usr/bin/env python3
"""Generate the reference scores for demos/1812's audio evidence.

`c64 audio capture --ref SCORE` diffs a recording against a YAML score.  This
writes those scores from the SAME data the C64 plays — the `.byte` streams in
`music.s` and the frequency table `tools/gentables.py` emits — so a score
cannot drift away from the arrangement, and a wrong note in the program still
fails the diff.  A score written from a transcription cannot fail, and a check
that cannot fail is not evidence.

    python3 tools/genscore.py --out evidence/audio     # write the five scores
    python3 tools/genscore.py --check                  # verify the committed ones
    python3 tools/genscore.py --pokes cannon           # the --at-frame reset spec

Stdlib only, runnable from anywhere.

--------------------------------------------------------------------------
THE MODEL.  `voicetick` (music.s) is walked one frame at a time, and the
score is the run-length encoding of what a once-per-frame sampler would read
off `$D400-$D418`.  Two facts about the player move the boundaries, and both
are invisible in the `.byte` data:

  * an event owns duration + 1 ticks — `voicetick` fetches on the frame
    `vcnt` reaches 0 and does not decrement it again that frame;
  * a note is RELEASED three frames before its event ends (`vcnt` < 4), so
    every event is `duration - 3` gated frames followed by four of rest.

So the naive "one entry per notated note, frames = duration" is wrong twice
over, and `references/audio-verification.md` says why: the score describes
the frame grid, not the sheet.

THE WINDOW.  Every capture resets the section's three streams to their heads
at log frame 0 with `c64 audio capture --at-frame 0` (see `--pokes`), which
is exactly what `loadstreams` does at a section change.  Log frame f is then
the state after section tick f + 1, deterministically, whatever the arming
took — so the same score passes on a re-capture instead of being fitted to
one run's lead-in.

WHY NO `frames`.  The sequencer is paced by the CINV wedge on the KERNAL's
CIA jiffy, which runs at 60.0016 Hz, while the sid log samples once per NTSC
video frame at 59.826 Hz.  The two separate by 60.0016 - 59.826 = 0.1756
counts a second, so a whole frame of drift takes 1 / 0.1756 = 5.69 s, which is
~341 log frames (~342 sequencer ticks).  Over a
900-frame window two or three ticks land between one pair of samples and the
events either side of them come back a frame short.  That is the drift
`references/audio-verification.md` names ("Durations drift, and omitting
`frames` is a legitimate score ... what to reach for when the passage is
long"), and pinning durations here would fail on it while proving nothing
about the music.  The modelled length is kept as a COMMENT on each entry —
information for a reader, not an assertion — and the note SEQUENCE, every
gate-down rest included, is what the score claims.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gentables import notefreq  # noqa: E402  (same directory, stdlib only)

DEMO = pathlib.Path(__file__).resolve().parent.parent

# The session's clock, which is NOT the one the table was built with: the
# table keeps 1022730 on purpose (see gentables.py), and the analysis resolves
# the machine's real 1022727 from the log's stamp.  The difference is 0.005
# cents — far inside a note name — but the score has to be spelled the way the
# TRANSCRIPTION will spell it, so the name is derived through the real clock.
CLOCK_HZ = 1022727
SID_ACC = 1 << 24
FPS = 60                      # the profile's nominal NTSC frame rate

REST_BYTE = 0
CANNON_BYTE = 0xFD
LOOPS_BYTE = 0xFF

#: `cannonfire` writes $D400/$D401 = $40/$04 for every shot — a low noise
#: pitch, not a note.  The transcription still names the oscillator (the
#: frequency register is real and sets how bright the noise is), so the score
#: has to name it too; its cents column reads `-` because noise has no pitch.
CANNON_REG16 = 0x0440

NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

#: Section index -> (stream-label prefix, human name).  Section 5 is the
#: hold: never ticked, nothing to score.
SECTIONS = {0: "hymn", 1: "marseillaise", 2: "battle", 3: "cannon", 4: "finale"}

#: The capture windows, in frames — nominally 15 s each at 60 fps.  Two of
#: them are not 15 s, and both departures are argued rather than convenient.
#:
#: THE HYMN IS 18 s AND THE REASON IS THE TEXTURE ARC.  Its left hand enters
#: on tick 849 — 14.1 s in — so a 15-second window shows 0.9 s of the two-hand
#: texture and the arc's first step ("one instrument, then two") is not
#: legible in the roll.  1089 frames spends three more seconds to show 241
#: frames of it.  Every other section's material is established well inside
#: 15 s: the Marseillaise's bass enters on tick 495 (8.2 s), and the battle,
#: the cannon and the finale have all three voices from tick 1.
#:
#: THE BATTLE IS 10 s AND THE REASON IS THE TAIL MARGIN.  The drift above is
#: one-sided — the machine is always AHEAD of the model, never behind — so a
#: window whose last modelled event ends within the drift of the edge picks up
#: an event the score does not list, and an extra sounding note is a diff by
#: design.  The margin has to cover the drift, and the battle's voice 1 caps
#: it: every event there is a 3-frame note and a 4-frame rest, so no window
#: length leaves more than 3 frames of it after the edge (checked over every
#: length from 480 to 920).  3 frames covers 599 frames of drift (1.7) and does
#: not cover 900 (2.6).
#:
#: THE MARGINS, per voice, as the model computes them: the frames from the
#: window's edge to that voice's next modelled TRANSITION, which is the first
#: thing the drift could pull in and the first thing that would show up as an
#: extra entry.  Recompute them by walking `per_frame` past the edge; they are
#: a property of the streams and the window and move whenever either does.
#:
#:      hymn          115 /  55 / never — s0v2 is the left hand, and s0v3
#:                                        never sounds at all (the solo piano)
#:      marseillaise   27 /  28 /  27
#:      battle          3 /  10 /   8  — the binding one, above
#:      cannon         55 /  55 / 108
#:      finale        131 /  26 /  26
WINDOWS = {"hymn": 1089, "marseillaise": 892, "battle": 599, "cannon": 905,
           "finale": 900}

# --- reading the arrangement ----------------------------------------------

_LABEL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")
_STREAM = re.compile(r"^s([0-4])v([1-3])$")

CONSTANTS = {
    "N_C": 1, "N_CS": 2, "N_D": 3, "N_DS": 4, "N_E": 5, "N_F": 6, "N_FS": 7,
    "N_G": 8, "N_GS": 9, "N_A": 10, "N_AS": 11, "N_B": 12,
    "OC1": 0, "OC2": 12, "OC3": 24, "OC4": 36, "OC5": 48, "OC6": 60,
    "REST": REST_BYTE, "CANNON": CANNON_BYTE, "LOOPS": LOOPS_BYTE,
}


def _value(token: str) -> int:
    """One `.byte` operand: a number, a constant, or a sum of constants."""
    total = 0
    for part in token.split("+"):
        part = part.strip()
        if part in CONSTANTS:
            total += CONSTANTS[part]
        elif part.startswith("$"):
            total += int(part[1:], 16)
        else:
            total += int(part, 10)
    return total


def read_streams(path: pathlib.Path | None = None) -> dict[str, list[int]]:
    """`{"s0v1": [bytes…], …}` straight out of music.s.

    Parsed rather than transcribed into this file, so the score and the
    program read one copy of the arrangement.  Comments are stripped first;
    a stream ends at the next label in column 1.
    """
    text = (path or DEMO / "music.s").read_text()
    streams: dict[str, list[int]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].rstrip()
        if not line:
            continue
        found = _LABEL.match(line)
        if found:
            name = found.group(1)
            current = name if _STREAM.match(name) else None
            line = line[found.end():]
            if current is not None:
                streams[current] = []
        if current is None:
            continue
        body = line.strip()
        if not body.startswith(".byte"):
            continue
        streams[current] += [_value(t) for t in body[5:].split(",") if t.strip()]
    missing = [f"s{s}v{v}" for s in SECTIONS for v in (1, 2, 3)
               if f"s{s}v{v}" not in streams]
    if missing:
        sys.exit(f"music.s: no stream data found for {', '.join(missing)}")
    return streams


def events_of(stream: list[int]) -> list[tuple[int, int]]:
    """A raw stream as (note, duration) pairs; the trailing LOOPS is dropped.

    A stream may never BEGIN with LOOPS — music.s says so beside `vtfetch`,
    because the rewind would spin — so that is checked here rather than
    modelled.
    """
    if not stream or stream[0] == LOOPS_BYTE:
        sys.exit("a stream begins with LOOPS: the rewind in vtfetch would spin")
    pairs = []
    i = 0
    while i < len(stream) and stream[i] != LOOPS_BYTE:
        pairs.append((stream[i], stream[i + 1]))
        i += 2
    return pairs


# --- naming a note the way the transcription will --------------------------

def note_name(reg16: int) -> str:
    """The equal-tempered name `sid_analysis.freq_to_note` gives this register."""
    import math
    hz = reg16 * CLOCK_HZ / SID_ACC
    midi = round(69 + 12 * math.log2(hz / 440.0))
    return f"{NAMES[midi % 12]}{midi // 12 - 1}"


def byte_name(note: int, freqs: list[int]) -> str:
    """The name for one note byte: 1..72 is C1..B6, $FD is the cannon."""
    if note == CANNON_BYTE:
        return note_name(CANNON_REG16)
    if not 1 <= note <= len(freqs):
        sys.exit(f"note byte {note} is outside 1..{len(freqs)}")
    return note_name(freqs[note - 1])


# --- the model -------------------------------------------------------------

def per_frame(pairs: list[tuple[int, int]], frames: int,
              freqs: list[int]) -> list[str]:
    """`voicetick`, one frame at a time — see this module's docstring.

    The voice starts as `loadstreams` leaves it (`vcnt` 0, pointer at the
    stream head), which is the state the capture's `--at-frame 0` writes
    impose, so entry `f` of the result is what the sampler reads on log
    frame `f`.
    """
    out: list[str] = []
    index = 0
    vcnt = 0
    vrel = 0
    gate = False
    current = "rest"
    for _ in range(frames):
        if vcnt:
            vcnt -= 1
            if vcnt < 4 and not vrel:
                vrel = 1
                gate = False            # gateoff: released three frames early
        else:
            if index >= len(pairs):     # the LOOPS rewind
                index = 0
            note, duration = pairs[index]
            index += 1
            vcnt, vrel = duration, 0
            if note == REST_BYTE:
                gate = False            # a rest event gates off at its fetch
            else:
                gate, current = True, byte_name(note, freqs)
        out.append(current if gate else "rest")
    return out


def encode(samples: list[str]) -> list[tuple[str, int]]:
    """Run-length encode the per-frame list — the transcriber's own rule."""
    out: list[tuple[str, int]] = []
    for note in samples:
        if out and out[-1][0] == note:
            out[-1] = (note, out[-1][1] + 1)
        else:
            out.append((note, 1))
    return out


# --- emission --------------------------------------------------------------

HEADER = """\
# 1812 — {title}
# GENERATED by tools/genscore.py from music.s's own note streams.  Do not
# edit: a score edited until it matches proves nothing, and the fix for a
# diff belongs in the program.  Re-run `python3 tools/genscore.py --check`.
#
# The window is section {section}'s ticks 1..{frames} ({seconds:.0f} s at {fps} Hz).
# The capture resets this section's three streams to their heads at log
# frame 0 (`--at-frame`, see tools/genscore.py --pokes), so log frame f is
# the state after tick f + 1 whatever the arming cost.
#
# `frames` is omitted on every entry ON PURPOSE — the sequencer runs on the
# 60.0016 Hz jiffy and the log samples at 59.826 fps, so durations drift by a
# frame every ~342 and pinning them would fail on the clock rather than on the
# music.  The number after each entry is the MODELLED length in frames: a
# comment, not a claim.
"""


def render(section: int, frames: int, title: str,
           streams: dict[str, list[int]], freqs: list[int]) -> str:
    lines = [HEADER.format(title=title, section=section, frames=frames,
                           seconds=frames / FPS, fps=FPS), "voices:"]
    for voice in (1, 2, 3):
        pairs = events_of(streams[f"s{section}v{voice}"])
        evs = encode(per_frame(pairs, frames, freqs))
        if len(evs) == 1 and evs[0][0] == "rest":
            # The positive claim "this voice sits out the captured passage",
            # which is what an empty list means to `diff_score`.
            lines.append(f"  {voice}: []")
            continue
        lines.append(f"  {voice}:")
        lines += [f"    - {{note: {note}}}    # {length}" for note, length in evs]
    return "\n".join(lines) + "\n"


TITLES = {
    "hymn": "the hymn, solo piano, and the left hand entering on tick 849",
    "marseillaise": "the anthem on the reed, with the piano's bass hand "
                    "entering on tick 495",
    "battle": "running sixteenths, off-beat stabs and the octave bass",
    "cannon": "eight of the sixteen shots, over the hymn's sustained chords",
    "finale": "the hymn in E major over the ring-modulated bells",
}


def scores(streams: dict[str, list[int]], freqs: list[int]) -> dict[str, str]:
    out = {}
    for section, name in SECTIONS.items():
        out[f"{name}.score.yaml"] = render(section, WINDOWS[name],
                                           TITLES[name], streams, freqs)
    return out


# --- the capture's --at-frame reset ----------------------------------------

#: The sequencer state `loadstreams` writes, as label -> (count, what).
#: Reproducing it at log frame 0 is what makes the window deterministic.
RESET_LABELS = ("vptrl", "vptrh", "vbasel", "vbaseh", "vcnt", "vnote", "vrel")


def labels(path: pathlib.Path | None = None) -> dict[str, int]:
    """Addresses out of the VICE label file `c64 build` writes beside the .prg."""
    out = {}
    for line in (path or DEMO / "1812.lbl").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "al":
            out[parts[2].lstrip(".")] = int(parts[1], 16)
    return out


def pokes(section: int, sym: dict[str, int], streams: dict[str, list[int]]) -> str:
    """The `--at-frame 0` spec that rewinds this section's streams.

    Exactly what `loadstreams` writes — the three stream pointers, their
    rewind bases, and `vcnt`/`vnote`/`vrel` — plus `noteidx`, which `nextsec`
    zeroes at a section change.  Nothing else is touched: the instruments,
    the palette and `secframe` are the section's own and stay as the program
    set them.
    """
    heads = [sym[f"s{section}v{v}"] for v in (1, 2, 3)]
    writes = []
    for i, head in enumerate(heads):
        writes.append((sym["vptrl"] + i, head & 0xFF))
        writes.append((sym["vptrh"] + i, head >> 8))
        writes.append((sym["vbasel"] + i, head & 0xFF))
        writes.append((sym["vbaseh"] + i, head >> 8))
    for label in ("vcnt", "vnote", "vrel"):
        writes += [(sym[label] + i, 0) for i in range(3)]
    writes.append((sym["noteidx"], 0))
    return ",".join(f"${addr:04x}=${value:02x}" for addr, value in writes)


# --- main ------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="directory for the five .score.yaml files")
    ap.add_argument("--check", action="store_true",
                    help="verify the committed scores match this generator")
    ap.add_argument("--pokes", metavar="SECTION",
                    help="print the --at-frame 0 reset spec for a section "
                         "(name or index) and exit")
    args = ap.parse_args(argv)

    streams = read_streams()
    freqs = notefreq()

    if args.pokes is not None:
        names = {name: index for index, name in SECTIONS.items()}
        try:
            section = names[args.pokes] if args.pokes in names else int(args.pokes)
        except ValueError:
            return _fail(f"unknown section {args.pokes!r}: "
                         f"{', '.join(sorted(names))}")
        if section not in SECTIONS:
            return _fail(f"section {section} has no score: {sorted(SECTIONS)}")
        print(pokes(section, labels(), streams))
        return 0

    out = scores(streams, freqs)
    target = pathlib.Path(args.out) if args.out else DEMO / "evidence" / "audio"
    if args.check:
        bad = []
        for name, text in out.items():
            path = target / name
            if not path.exists():
                bad.append(f"{path} is missing")
            elif path.read_text() != text:
                bad.append(f"{path} differs from the generator output")
        if bad:
            return _fail("\n".join(bad))
        print(f"the {len(out)} scores under {target} match the generator")
        return 0

    target.mkdir(parents=True, exist_ok=True)
    for name, text in out.items():
        (target / name).write_text(text)
        entries = sum(1 for line in text.splitlines() if line.lstrip().startswith("-"))
        print(f"wrote {target / name} ({entries} events)")
    return 0


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
