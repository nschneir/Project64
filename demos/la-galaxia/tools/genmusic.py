#!/usr/bin/env python3
"""Compose the title theme and emit music.inc *and* its reference score.

Two things come out of one source, which is the point: the reference score
`c64 audio capture --ref` diffs the recording against is generated from the
same note data the C64 plays, so the score cannot drift away from the music.
A score written by hand next to the data is a second copy of the truth; a
score derived from a *transcription* cannot fail and so is not evidence.

    python3 tools/genmusic.py -o music.inc --score evidence/audio
    python3 tools/genmusic.py --check

The piece: 1960s sci-fi scoring played by a mariachi band on acid.  A 6/8
lilt with the bass dropping into 3/4 against it (the sesquialtera), a
guitarron walking in twos, an off-beat vihuela chop, a trumpet lead that
rips up into its held notes -- and, running through all of it, the era's
space-music vocabulary: whole-tone and chromatic slides, tritone turns, a
held low drone, and pulse widths that breathe until the trumpets sound
seasick.

Timing: one row is an eighth note and six frames long, so a 6/8 bar is six
rows and one second is ten rows.  A hundred bars is six hundred rows is
exactly sixty seconds at 60 Hz, which is the length floor the spec sets.

The seam is a compositional requirement, not a playback one, and --check
enforces the parts of it that can be checked mechanically: the last bar's
harmony has to be the dominant of the first bar's, no voice may be left
gated at the loop point, and the lead's last note has to be within a fourth
of its first so the line hands over instead of jumping.
"""

from __future__ import annotations

import argparse
import os
import sys

CLOCK = 1022727            # NTSC
ROWTICKS = 6
PATROWS = 24               # four 6/8 bars per pattern
FPS = 60

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_HOLD = "-"            # keep sounding
NOTE_OFF = "."             # release the gate
REST = None

# ---- instruments ---------------------------------------------------------
# waveform, attack/decay, sustain/release, pulse width, vibrato depth
INSTRUMENTS = [
    # 0 trumpet lead: bright pulse, hard attack, heavy vibrato
    dict(wave=0x40, ad=0x18, sr=0xB8, pw=0x0800, vib=6),
    # 1 guitarron: triangle, round and short
    dict(wave=0x10, ad=0x09, sr=0x40, pw=0x0000, vib=0),
    # 2 vihuela chop: sawtooth, clipped
    dict(wave=0x20, ad=0x06, sr=0x20, pw=0x0000, vib=0),
    # 3 theremin: triangle with ring modulation and a wide wobble
    dict(wave=0x14, ad=0x38, sr=0xC8, pw=0x0000, vib=14),
    # 4 the ominous drone: sawtooth, slow in, long tail
    dict(wave=0x20, ad=0x6A, sr=0xE8, pw=0x0000, vib=2),
    # 5 hard-synced trumpet: the grito rip
    dict(wave=0x22, ad=0x08, sr=0xA8, pw=0x0000, vib=9),
    # 6 seasick pulse: narrow, drifting
    dict(wave=0x40, ad=0x28, sr=0xC8, pw=0x0200, vib=11),
    # 7 noise: the rasp under the coda
    dict(wave=0x80, ad=0x18, sr=0x60, pw=0x0000, vib=0),
]

LEAD, BASS, CHOP, THEREMIN, DRONE, RIP, SEASICK, RASP = range(8)


FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def midi(name: str) -> int:
    """'A4' / 'Bb3' -> the index into the 96-note table (C1 = 0)."""
    i = 2 if name[1] in "#b" else 1
    head = FLATS.get(name[:i], name[:i])
    step = NAMES.index(head)
    octave = int(name[i:])
    n = (octave - 1) * 12 + step
    if not 0 <= n < 96:
        sys.exit(f"note out of range: {name}")
    return n


def sharp(name: str) -> str:
    """'Ab4' -> 'G#4'.  The transcription names every black key with a sharp,
    so a score that spells one flat is a diff about orthography and nothing
    else -- and a diff about orthography buries the diffs that matter."""
    if name == "rest":
        return name
    i = 2 if name[1] in "#b" else 1
    return FLATS.get(name[:i], name[:i]) + name[i:]


def freq(n: int) -> int:
    hz = 32.703195 * (2 ** (n / 12.0))
    return min(0xFFFF, round(hz * (1 << 24) / CLOCK))


def bar(*rows: str) -> list[str]:
    if len(rows) != 6:
        sys.exit(f"a 6/8 bar is six rows, got {len(rows)}: {rows}")
    return list(rows)


# ==========================================================================
# The piece.  Each voice is a list of bars; a bar is six row entries.
# ==========================================================================
H, O = NOTE_HOLD, NOTE_OFF

# ---- intro: the held low drone and a theremin rising out of it ----------
intro_lead = [
    bar(O, O, O, O, "A4", H),
    bar("D5", H, H, "Ab4", H, H),
    bar("A4", H, "D5", H, "F5", H),
    bar("E5", H, H, H, H, O),
    bar(O, O, "A3", H, "D4", H),
    bar("F4", H, "A4", H, "D5", H),
    bar("Ab5", H, H, H, "G5", H),
    bar("F5", H, "E5", H, "D5", H),
]
intro_bass = [
    bar("D2", H, H, H, H, H),
    bar(H, H, H, H, H, H),
    bar("D2", H, H, "Ab2", H, H),
    bar("A2", H, H, H, H, H),
    bar("D2", H, "A2", H, H, H),
    bar("D2", H, "A2", H, H, H),
    bar("Ab2", H, "Eb3", H, H, H),
    bar("A2", H, "A2", H, "E3", H),
]
intro_chop = [
    bar(O, O, O, O, O, O),
    bar(O, O, O, O, O, O),
    bar(O, O, O, O, O, O),
    bar(O, O, O, O, O, O),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "Eb5", "Ab5", O, "Eb5", "Ab5"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
]

# ---- A: the tune proper, trumpet over a walking guitarron ---------------
a_lead = [
    bar("D5", "E5", "F5", "A5", H, "G5"),
    bar("F5", H, "E5", "D5", H, "C#5"),
    bar("D5", "F5", "A5", "D6", H, "C6"),
    bar("A5", H, "G5", "F5", "E5", "D5"),
    bar("A4", "C#5", "E5", "G5", H, "F5"),
    bar("E5", H, "D5", "C#5", H, "A4"),
    bar("Bb4", "D5", "F5", "Bb5", H, "A5"),
    bar("G5", "F5", "E5", "D5", H, O),
    bar("D5", "E5", "F5", "A5", H, "G5"),
    bar("F5", H, "E5", "D5", H, "C#5"),
    bar("D5", "F5", "Ab5", "D6", H, "B5"),
    bar("Ab5", H, "G5", "F5", "E5", "D5"),
    bar("E5", "G5", "Bb5", "D6", H, "C6"),
    bar("Bb5", H, "A5", "G5", H, "F5"),
    bar("E5", "F5", "G5", "A5", "Bb5", "C#6"),
    bar("D6", H, H, H, H, O),
]
a_bass = [
    bar("D2", H, H, "A2", H, H),
    bar("D2", H, H, "A2", H, H),
    bar("D2", H, H, "F2", H, H),
    bar("A2", H, H, "A2", H, H),
    bar("A2", H, H, "E3", H, H),
    bar("A2", H, H, "E3", H, H),
    bar("Bb2", H, H, "F3", H, H),
    bar("A2", H, H, "A2", H, H),
    bar("D2", H, H, "A2", H, H),
    bar("D2", H, H, "A2", H, H),
    bar("D2", H, H, "Ab2", H, H),
    bar("D2", H, H, "D2", H, H),
    bar("C3", H, H, "G2", H, H),
    bar("Bb2", H, H, "F2", H, H),
    bar("A2", H, H, "A2", H, H),
    bar("D2", H, H, "A2", H, H),
]
a_chop = [
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "D5", O, "A4", "C#5"),
    bar(O, "A4", "D5", O, "A4", "C5"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
    bar(O, "A4", "C#5", O, "B4", "E5"),
    bar(O, "A4", "C#5", O, "B4", "E5"),
    bar(O, "Bb4", "D5", O, "C5", "F5"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "D5", O, "A4", "C#5"),
    bar(O, "A4", "D5", O, "B4", "Eb5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "G4", "C5", O, "G4", "B4"),
    bar(O, "F4", "Bb4", O, "F4", "A4"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
]

# ---- B: the whole-tone drift.  The band wanders into a key nobody asked
# ---- for and finds its way back.
b_lead = [
    bar("D5", "E5", "F#5", "Ab5", "Bb5", "C6"),
    bar("D6", H, H, "C6", "Bb5", "Ab5"),
    bar("F#5", "E5", "D5", "C5", "Bb4", "Ab4"),
    bar("F#4", H, H, H, H, O),
    bar("Eb5", "F5", "G5", "A5", "B5", "C#6"),
    bar("Eb6", H, H, "C#6", "B5", "A5"),
    bar("G5", "F5", "Eb5", "C#5", "B4", "A4"),
    bar("G4", H, H, H, H, O),
    bar("A4", "B4", "C#5", "Eb5", "F5", "G5"),
    bar("A5", H, "G5", H, "F5", H),
    bar("Eb5", H, "C#5", H, "B4", H),
    bar("A4", H, H, "Ab4", H, H),
    bar("D5", "F5", "Ab5", "B5", H, "Ab5"),
    bar("F5", "D5", "B4", "Ab4", H, "F4"),
    bar("A4", "C#5", "E5", "G5", H, "E5"),
    bar("A5", H, H, H, H, O),
]
b_bass = [
    bar("D2", H, H, "F#2", H, H),
    bar("Ab2", H, H, "Bb2", H, H),
    bar("C3", H, H, "Ab2", H, H),
    bar("F#2", H, H, "F#2", H, H),
    bar("Eb2", H, H, "G2", H, H),
    bar("A2", H, H, "B2", H, H),
    bar("C#3", H, H, "A2", H, H),
    bar("G2", H, H, "G2", H, H),
    bar("A2", H, H, "C#3", H, H),
    bar("A2", H, H, "C#3", H, H),
    bar("Eb2", H, H, "Ab2", H, H),
    bar("A2", H, H, "Ab2", H, H),
    bar("D2", H, H, "Ab2", H, H),
    bar("D2", H, H, "Ab2", H, H),
    bar("A2", H, H, "E3", H, H),
    bar("A2", H, H, "A2", H, H),
]
b_chop = [
    bar(O, "F#4", "Bb4", O, "F#4", "Bb4"),
    bar(O, "Ab4", "C5", O, "Ab4", "C5"),
    bar(O, "C5", "E5", O, "Ab4", "C5"),
    bar(O, "F#4", "Bb4", O, "F#4", "Bb4"),
    bar(O, "G4", "B4", O, "G4", "B4"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
    bar(O, "C#5", "F5", O, "A4", "C#5"),
    bar(O, "G4", "B4", O, "G4", "B4"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
    bar(O, "Ab4", "C5", O, "Ab4", "C5"),
    bar(O, "A4", "C#5", O, "Ab4", "C5"),
    bar(O, "Ab4", "B4", O, "Ab4", "B4"),
    bar(O, "Ab4", "B4", O, "Ab4", "B4"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
]

# ---- C: sesquialtera.  The lead keeps 6/8; the bass plays 3/4 across it,
# ---- so the bar is felt two ways at once.
c_lead = [
    bar("D5", "E5", "F5", "G5", "A5", "Bb5"),
    bar("A5", H, "G5", "F5", "E5", "D5"),
    bar("F5", "G5", "A5", "Bb5", "C6", "D6"),
    bar("C6", H, "Bb5", "A5", "G5", "F5"),
    bar("A5", H, "F5", H, "D5", H),
    bar("E5", "F5", "G5", "A5", H, "G5"),
    bar("F5", "E5", "D5", "C#5", H, "A4"),
    bar("D5", H, H, H, H, O),
    bar("A4", "D5", "F5", "A5", "F5", "D5"),
    bar("Ab4", "D5", "F5", "Ab5", "F5", "D5"),
    bar("A4", "C#5", "E5", "A5", "E5", "C#5"),
    bar("Bb4", "D5", "F5", "Bb5", H, "A5"),
    bar("G5", "F5", "E5", "F5", "G5", "A5"),
    bar("Bb5", H, "A5", H, "G5", H),
    bar("F5", "E5", "D5", "E5", "F5", "G5"),
    bar("A5", H, H, H, H, O),
]
c_bass = [
    bar("D2", H, "F2", H, "A2", H),
    bar("D2", H, "F2", H, "A2", H),
    bar("Bb2", H, "D3", H, "F3", H),
    bar("Bb2", H, "D3", H, "F3", H),
    bar("D2", H, "F2", H, "A2", H),
    bar("A2", H, "C#3", H, "E3", H),
    bar("A2", H, "C#3", H, "E3", H),
    bar("D2", H, "A2", H, "D3", H),
    bar("D2", H, "A2", H, "D3", H),
    bar("Ab2", H, "D3", H, "Ab3", H),
    bar("A2", H, "C#3", H, "E3", H),
    bar("Bb2", H, "D3", H, "F3", H),
    bar("C3", H, "E3", H, "G3", H),
    bar("Bb2", H, "D3", H, "F3", H),
    bar("A2", H, "C#3", H, "E3", H),
    bar("A2", H, "E3", H, "A3", H),
]
c_chop = [
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "Bb4", "F5", O, "Bb4", "F5"),
    bar(O, "Bb4", "F5", O, "Bb4", "F5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "Ab4", "D5", O, "Ab4", "D5"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
    bar(O, "Bb4", "D5", O, "Bb4", "F5"),
    bar(O, "C5", "E5", O, "C5", "G5"),
    bar(O, "Bb4", "D5", O, "Bb4", "F5"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
]

# ---- coda: twelve bars that walk the harmony back onto the intro's D
# ---- pedal and hand the lead its own opening A4.
coda_lead = [
    bar("D6", H, "C6", H, "Bb5", H),
    bar("A5", H, "G5", "F5", "E5", "D5"),
    bar("Ab5", H, "G5", H, "F5", H),
    bar("E5", H, "D5", "C#5", H, "A4"),
    bar("D5", "F5", "A5", H, "F5", "D5"),
    bar("Ab4", "B4", "D5", H, "B4", "Ab4"),
    bar("A4", "C#5", "E5", H, "C#5", "A4"),
    bar("D5", H, H, H, H, O),
    bar(O, O, "A4", H, "D5", H),
    bar("F5", H, "E5", H, "D5", H),
    bar("C#5", H, H, "A4", H, H),
    bar("A4", H, H, H, H, O),
]
coda_bass = [
    bar("D3", H, H, "Bb2", H, H),
    bar("A2", H, H, "A2", H, H),
    bar("Ab2", H, H, "Eb3", H, H),
    bar("A2", H, H, "A2", H, H),
    bar("D2", H, H, "F2", H, H),
    bar("Ab2", H, H, "B2", H, H),
    bar("A2", H, H, "C#3", H, H),
    bar("D2", H, H, "D2", H, H),
    bar("D2", H, H, "A2", H, H),
    bar("D2", H, H, "A2", H, H),
    bar("A2", H, H, "A2", H, H),
    bar("E3", H, H, "A2", H, O),
]
coda_chop = [
    bar(O, "Bb4", "D5", O, "Bb4", "F5"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
    bar(O, "Ab4", "B4", O, "Eb5", "Ab5"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
    bar(O, "A4", "D5", O, "A4", "F5"),
    bar(O, "Ab4", "B4", O, "Ab4", "D5"),
    bar(O, "A4", "C#5", O, "A4", "E5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "D5", O, "A4", "D5"),
    bar(O, "A4", "C#5", O, "A4", "C#5"),
    bar(O, "A4", "C#5", O, "E5", O),
]

SECTIONS = [
    ("intro", intro_lead, intro_bass, intro_chop, (THEREMIN, DRONE, CHOP)),
    ("A", a_lead, a_bass, a_chop, (LEAD, BASS, CHOP)),
    ("A'", a_lead, a_bass, a_chop, (RIP, BASS, CHOP)),
    ("B", b_lead, b_bass, b_chop, (SEASICK, BASS, CHOP)),
    ("C", c_lead, c_bass, c_chop, (LEAD, BASS, CHOP)),
    ("A''", a_lead, a_bass, a_chop, (RIP, BASS, CHOP)),
    ("coda", coda_lead, coda_bass, coda_chop, (THEREMIN, DRONE, CHOP)),
]


def flatten() -> tuple[list[list[str]], list[list[int]], int]:
    """-> (per-voice row lists, per-voice instrument-per-row lists, bars)."""
    voices: list[list[str]] = [[], [], []]
    insts: list[list[int]] = [[], [], []]
    bars = 0
    for name, lead, bass, chop, instr in SECTIONS:
        for v, part in enumerate((lead, bass, chop)):
            for b in part:
                voices[v].extend(b)
                insts[v].extend([instr[v]] * 6)
        n = len(lead)
        if len(bass) != n or len(chop) != n:
            sys.exit(f"section {name}: voices are {n}/{len(bass)}/{len(chop)} bars")
        bars += n
    return voices, insts, bars


def check(voices: list[list[str]], bars: int) -> None:
    rows = len(voices[0])
    seconds = rows * ROWTICKS / FPS
    problems = []
    if seconds < 60.0:
        problems.append(f"the theme is {seconds:.1f} s, under the one-minute floor")
    if rows % PATROWS:
        problems.append(f"{rows} rows does not divide into {PATROWS}-row patterns")
    for v, part in enumerate(voices):
        if len(part) != rows:
            problems.append(f"voice {v + 1} is {len(part)} rows, not {rows}")
        if part[-1] == NOTE_HOLD:
            problems.append(
                f"voice {v + 1} is still gated at the seam -- a note left "
                "sounding announces the loop point as loudly as a gap"
            )
    # the seam has to resolve: the coda's last bass note must be the
    # dominant of the intro's first
    last_bass = [n for n in voices[1] if n not in (NOTE_HOLD, NOTE_OFF)][-1]
    first_bass = [n for n in voices[1] if n not in (NOTE_HOLD, NOTE_OFF)][0]
    if midi(last_bass) % 12 != (midi(first_bass) + 7) % 12:
        problems.append(
            f"the seam does not resolve: coda ends on {last_bass}, which is "
            f"not the dominant of the opening {first_bass}"
        )
    lead = [n for n in voices[0] if n not in (NOTE_HOLD, NOTE_OFF)]
    if abs(midi(lead[-1]) - midi(lead[0])) > 5:
        problems.append(
            f"the lead jumps at the seam: {lead[-1]} into {lead[0]}"
        )
    if problems:
        for p in problems:
            print("FAIL " + p, file=sys.stderr)
        sys.exit(1)
    print(
        f"ok {bars} bars, {rows} rows, {rows * ROWTICKS} frames, "
        f"{seconds:.1f} s at {FPS} Hz"
    )
    print(f"ok the seam resolves: {last_bass} -> {first_bass}, "
          f"lead {lead[-1]} -> {lead[0]}")


def state_at(part: list[str], row: int) -> tuple[str | None, bool]:
    """(the note musvoice is holding, is it gated) on entry to `row`."""
    cur: str | None = None
    gate = False
    for entry in part[:row]:
        if entry == NOTE_HOLD:
            continue
        if entry == NOTE_OFF:
            gate = False
        else:
            cur, gate = entry, True
    return cur, gate


# fx_laser's sweep, straight out of sound.s: the frequency high byte, with
# the low byte held at zero.  Five sampled frames, not six: on the sixth tick
# sfxtick drops the gate and clears vprio, and musictick -- which runs after
# it in the same soundtick -- writes the music back over the voice before the
# frame ends.  The handover costs no frame at all.
LASERTAB = [0x40, 0x34, 0x28, 0x1C, 0x10]


def reg_name(reg16: int) -> str:
    """The note name a raw 16-bit frequency register works out to."""
    import math
    hz = reg16 * CLOCK / (1 << 24)
    n = round(12 * math.log2(hz / 440.0)) + 9 + 4 * 12   # A4 = index 57
    return NAMES[n % 12] + str(n // 12)


LASER = [reg_name(hi << 8) for hi in LASERTAB]


def per_frame(part: list[str], state: tuple[str | None, bool],
              overlay: dict[int, str] | None = None) -> list[str]:
    """Rows -> what the once-per-frame sampler sees, one entry per frame.

    This is a model of `musvoice`, not of the sheet music, and the difference
    is the whole reason the score can be generated at all.  Two things in the
    player move the boundaries:

    * a new note spends its first frame with the gate DOWN -- that is the
      retrigger -- so a notated 12-frame note is sampled as one frame of rest
      and eleven of the note;
    * a row that only holds adds its six frames to whatever is sounding.

    Run-length encoding this gives exactly the events `sid_analysis`
    transcribes, because it transcribes the same once-per-frame samples.
    """
    cur, gate = state
    trig = False
    out: list[str] = []
    frame = 0
    for entry in part:
        if entry == NOTE_OFF:
            gate = False
        elif entry != NOTE_HOLD:
            cur, gate, trig = entry, True, True
        for _ in range(ROWTICKS):
            if overlay and frame in overlay:
                # An effect owns the voice: musvoice computes the state and
                # skips only the write, so `trig` is NOT consumed here.  That
                # is what makes the music resume at the position it would
                # have reached instead of restarting the note it was on.
                out.append(overlay[frame])
            elif cur is None or not gate:
                out.append("rest")
            elif trig:
                trig = False
                out.append("rest")
            else:
                out.append(cur)
            frame += 1
    return out


def events(part: list[str],
           state: tuple[str | None, bool] = (None, False),
           overlay: dict[int, str] | None = None) -> list[tuple[str, int]]:
    """Rows -> (note or 'rest', frames) events, run-length encoded per frame."""
    out: list[tuple[str, int]] = []
    for note in per_frame(part, state, overlay):
        if out and out[-1][0] == note:
            out[-1] = (note, out[-1][1] + 1)
        else:
            out.append((note, 1))
    return out


def emit_asm(voices: list[list[str]], insts: list[list[int]]) -> str:
    rows = len(voices[0])
    npat = rows // PATROWS
    out = [
        "; music.inc -- GENERATED by tools/genmusic.py.  Do not edit.",
        f"; {rows} rows, {ROWTICKS} frames each = {rows * ROWTICKS / FPS:.1f} s.",
        "",
        '        .segment "ENGINE"',
        "",
        f"MUS_ROWTICKS = {ROWTICKS}",
        f"MUS_PATROWS  = {PATROWS}",
        "",
        "; ---- the 96-note frequency table, NTSC ----",
    ]
    out.append("notelo:")
    out.append("        .byte   $00, $00")     # entries 0 (hold) and 1 (off)
    for n in range(96):
        if n % 8 == 0:
            out.append("        .byte   " + ", ".join(
                f"${freq(m) & 0xFF:02x}" for m in range(n, min(n + 8, 96))))
    out.append("notehi:")
    out.append("        .byte   $00, $00")
    for n in range(96):
        if n % 8 == 0:
            out.append("        .byte   " + ", ".join(
                f"${freq(m) >> 8:02x}" for m in range(n, min(n + 8, 96))))
    out.append("")

    out.append("; ---- instruments ----")
    for field, key, fmt in (
        ("i_wave", "wave", "${:02x}"),
        ("i_ad", "ad", "${:02x}"),
        ("i_sr", "sr", "${:02x}"),
        ("i_vib", "vib", "{}"),
    ):
        out.append(f"{field}:")
        out.append("        .byte   " + ", ".join(
            fmt.format(i[key]) for i in INSTRUMENTS))
    out.append("i_pwlo:")
    out.append("        .byte   " + ", ".join(
        f"${i['pw'] & 0xFF:02x}" for i in INSTRUMENTS))
    out.append("i_pwhi:")
    out.append("        .byte   " + ", ".join(
        f"${(i['pw'] >> 8) & 0x0F:02x}" for i in INSTRUMENTS))
    out.append("")

    out.append("; ---- the order list, $FF = the loop seam ----")
    out.append("musorder:")
    out.append("        .byte   " + ", ".join(str(p) for p in range(npat)))
    out.append("        .byte   $FF")
    out.append("patlo:")
    out.append("        .byte   " + ", ".join(f"<pat{p}" for p in range(npat)))
    out.append("pathi:")
    out.append("        .byte   " + ", ".join(f">pat{p}" for p in range(npat)))
    out.append("")

    for p in range(npat):
        out.append(f"pat{p}:")
        for r in range(PATROWS):
            row = p * PATROWS + r
            cells = []
            for v in range(3):
                n = voices[v][row]
                if n == NOTE_HOLD:
                    cells.append("$00, $00")
                elif n == NOTE_OFF:
                    cells.append("$01, $00")
                else:
                    cells.append(f"{midi(n) + 2:>3}, {insts[v][row]:>3}")
            out.append("        .byte   " + ", ".join(cells))
        out.append("")
    return "\n".join(out) + "\n"


def emit_score(voices: list[list[str]], path: str, rows: list[int],
               title: str, lasers: list[int] | None = None) -> str:
    """The score for the window `rows`, both edges landing in silence.

    `muslead` opens the window before the first row and `muslimit` closes the
    player after the last, so neither edge cuts a note in half and every entry
    can carry its exact frame count.  The leading and trailing rests are left
    out on purpose: they are however long arming happened to take, they are
    exempt from the diff either way, and listing them would put the one
    non-deterministic number in the piece into the evidence.
    """
    lines = [
        f"# {title}",
        "# GENERATED by tools/genmusic.py from the same note data music.inc",
        "# carries -- a reference score written from a transcription cannot",
        "# fail, and a check that cannot fail is not evidence.",
        f"# rows {rows[0]}..{rows[-1]} ({len(rows)} rows, "
        f"{len(rows) * ROWTICKS} frames)",
        f"tempo_frames_per_row: {ROWTICKS}",
        "voices:",
    ]
    overlay = {}
    for start in lasers or []:
        for i, note in enumerate(LASER):
            overlay[start + i] = note
    for v in range(3):
        part = [voices[v][i] for i in rows]
        evs = events(part, state_at(voices[v], rows[0])[:2],
                     overlay if v == 0 else None)
        while evs and evs[0][0] == "rest":
            evs.pop(0)
        while evs and evs[-1][0] == "rest":
            evs.pop()
        lines.append(f"  {v + 1}:" if evs else f"  {v + 1}: []")
        for note, frames in evs:
            lines.append(f"    - {{note: {sharp(note)}, frames: {frames}}}")
    text = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


OPEN_ROWS = 40                 # 4.0 s of the opening
SEAM_BEFORE = 20               # rows either side of the loop point
SEAM_AFTER = 20
PRIO_ROWS = 44                 # the priority window: rows 0..43
# Where the lasers land in it.  muslead and sfxdelay are both counted down
# once per tick by the same soundtick, so the gap between them is fixed:
# with muslead = 140 the sequencer's frame 0 is tick 141, and a laser cued
# with sfxdelay = 200 fires at tick 201 -- music frame 60 -- however long
# arming took.  sfxevery = 59 repeats it every 60 frames.
PRIO_LASERS = [60, 120, 180, 240]


def windows(rows: int) -> dict[str, list[int]]:
    """The two title-theme capture windows, as row indices."""
    return {
        "title-open": list(range(OPEN_ROWS)),
        "title-seam": (list(range(rows - SEAM_BEFORE, rows))
                       + list(range(SEAM_AFTER))),
    }


def emit_state(voices, insts, row: int) -> None:
    """What to poke so the sequencer starts a window mid-piece cleanly.

    Aiming a capture at the seam means setting mus_ord/mus_row -- but a voice
    whose window opens on a HOLD row is continuing a note the poke skipped
    over, so the note, its instrument and the gate have to be staged too or
    the passage starts silent.  Walking the data to `row` is the only thing
    that knows them.
    """
    notes, gates, ins = [], [], []
    for v in range(3):
        cur, gate = state_at(voices[v], row)
        notes.append(0 if cur is None else midi(cur) + 2)
        gates.append(1 if gate else 0)
        last = [i for i, e in enumerate(voices[v][:row])
                if e not in (NOTE_HOLD, NOTE_OFF)]
        ins.append(insts[v][last[-1]] if last else 0)
    print(f"row {row}: mus_ord {row // PATROWS} mus_row {row % PATROWS}")
    print("mus_note " + " ".join(str(n) for n in notes))
    print("mus_inst " + " ".join(str(i) for i in ins))
    print("mus_gate " + " ".join(str(g) for g in gates))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out")
    ap.add_argument("--score", help="directory for the reference scores")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--state", type=int, metavar="ROW",
                    help="print the sequencer state to poke to start at ROW")
    args = ap.parse_args()

    voices, insts, bars = flatten()
    check(voices, bars)
    rows = len(voices[0])
    if args.state is not None:
        emit_state(voices, insts, args.state)
        return
    if args.check:
        return
    if args.out:
        text = emit_asm(voices, insts)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.out}: {len(text.splitlines())} lines")
    if args.score:
        os.makedirs(args.score, exist_ok=True)
        titles = {
            "title-open": "La Galaxia -- the title theme's opening",
            "title-seam": "La Galaxia -- the loop seam, scored across it",
        }
        for name, window in windows(rows).items():
            emit_score(voices, os.path.join(args.score, f"{name}.score.yaml"),
                       window, titles[name])
        emit_score(
            voices, os.path.join(args.score, "title-priority.score.yaml"),
            list(range(PRIO_ROWS)),
            "La Galaxia -- four lasers taking voice 1 off the theme, and "
            "giving it back\n"
            "# The laser (priority 2) seizes voice 1 from the sequencer at "
            "music frames\n"
            "# " + ", ".join(str(f) for f in PRIO_LASERS) + ", holds it for "
            "five frames of sweep and one of\n"
            "# gate-off, then hands it back.  The sequencer never stopped: "
            "every note\n"
            "# after a seizure is the one it would have been playing had the "
            "laser never\n"
            "# fired, at the frame it would have been playing it -- which is "
            "the whole\n"
            "# of the resume half of the priority rule, and is what this "
            "score checks.\n"
            "# Voices 2 and 3 carry on untouched, which is the other half: a "
            "seizure\n"
            "# takes one voice, not the player",
            lasers=PRIO_LASERS)
        print(f"wrote scores into {args.score}")
        print(f"the seam window starts at row {rows - SEAM_BEFORE} of {rows} "
              f"(mus_ord {(rows - SEAM_BEFORE) // PATROWS}, "
              f"mus_row {(rows - SEAM_BEFORE) % PATROWS})")


if __name__ == "__main__":
    main()
