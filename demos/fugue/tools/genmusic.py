#!/usr/bin/env python3
"""bwv847.py -> notes.inc, plus the numbers the spec has to quote.

The arrangement is authored once, as note names, in bwv847.py.  This turns it
into the tables the 6502 reads and prints the measurements SPEC.md cites: the
pitch range each voice actually uses, the pitch-class histogram that decides
the colour assignment, the predicted `collide` count, and the band geometry
the range needs.

One byte per voice per sixteenth (SPEC.md section 10):

    $00   rest -- release the gate
    $FF   hold -- the previous note continues, gate untouched
    else  bits 0-4 = p + 1 (ladder position 1..30)
          bits 5-6 = accidental, 0 none / 1 sharp / 2 flat
          bit 7    = hollow head (a quarter note or longer)

The sounding pitch is posmidi[p] adjusted by the accidental, so the picture
and the sound are the same byte read two ways.  There is no separate pitch
stream that could disagree with the drawn one -- which is what makes the
piano-roll-versus-screen cross-check in SPEC.md section 11 meaningful rather
than circular.

    python3 genmusic.py            # regenerate notes.inc and print the report
    python3 genmusic.py --check    # re-derive and diff against the committed
                                   #   file; exit 1 on any difference
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bwv847  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "notes.inc"

NSIX = 496
CLOCK_NTSC = 1022727
CLOCK_PAL = 985248
MIDI_LO, MIDI_HI = 33, 88

# The ladder, top to bottom: p = 0 is D6, p = 29 is C2.  See SPEC.md section 3.
LETTERS = "CDEFGAB"
SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def build_ladder() -> list[tuple[str, int]]:
    """(letter, octave) for p = 0..29, descending diatonically from D6."""
    out = []
    letter, octave = "D", 6
    for _ in range(30):
        out.append((letter, octave))
        i = LETTERS.index(letter) - 1
        if i < 0:
            i = 6
            octave -= 1
        letter = LETTERS[i]
    return out


LADDER = build_ladder()
POS_OF = {lo: p for p, lo in enumerate(LADDER)}
POSMIDI = [(octave + 1) * 12 + SEMITONE[letter] for letter, octave in LADDER]

# Colour tiers (SPEC.md section 7).  White is spent on the staves, and only
# nine of the remaining fifteen read unambiguously against black.
STRONG = [2, 3, 4, 5, 7, 8, 10, 13, 14]  # red cyan purple green yellow
#                                          orange lt-red lt-green lt-blue
WEAK = [9, 12, 15]  # brown, medium gray, light gray
COLOUR_NAME = {
    2: "red", 3: "cyan", 4: "purple", 5: "green", 7: "yellow", 8: "orange",
    9: "brown", 10: "light red", 12: "medium gray", 13: "light green",
    14: "light blue", 15: "light gray",
}
PC_NAME = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def parse_pitch(s: str) -> tuple[int, int]:
    """'Eb4' -> (ladder position, accidental code)."""
    letter = s[0].upper()
    rest = s[1:]
    acc = 0
    if rest and rest[0] in "#b":
        acc = 1 if rest[0] == "#" else 2
        rest = rest[1:]
    octave = int(rest)
    key = (letter, octave)
    if key not in POS_OF:
        raise ValueError(f"{s!r} is outside the C2-D6 ladder")
    return POS_OF[key], acc


def expand() -> list[list[int]]:
    """BARS -> three streams of NSIX note bytes."""
    streams: list[list[int]] = [[], [], []]
    for bn, bar in enumerate(bwv847.BARS):
        for v in (1, 2, 3):
            stream = streams[v - 1]
            before = len(stream)
            for pitch, dur in bar[v]:
                if pitch == "rest":
                    stream.extend([0x00] * dur)
                elif pitch == "tie":
                    stream.extend([0xFF] * dur)
                else:
                    p, acc = parse_pitch(pitch)
                    hollow = 1 if dur >= 4 else 0
                    stream.append((p + 1) | (acc << 5) | (hollow << 7))
                    stream.extend([0xFF] * (dur - 1))
            if len(stream) - before != 16:
                raise ValueError(
                    f"bar {bn + 1} voice {v}: {len(stream) - before} sixteenths, not 16"
                )
    for v, s in enumerate(streams, 1):
        if len(s) != NSIX:
            raise ValueError(f"voice {v}: {len(s)} sixteenths, not {NSIX}")
    return streams


def note_midi(byte: int) -> int:
    p = (byte & 31) - 1
    acc = (byte >> 5) & 3
    return POSMIDI[p] + (1 if acc == 1 else -1 if acc == 2 else 0)


def histogram(streams: list[list[int]]) -> list[int]:
    counts = [0] * 12
    for s in streams:
        for b in s:
            if b not in (0x00, 0xFF):
                counts[note_midi(b) % 12] += 1
    return counts


def assign_colours(counts: list[int]) -> list[int]:
    """Strong colours to the commonest pitch classes, weak to the rarest.

    Frequency is the least bad rule available: it minimises the number of
    note heads a viewer has to work to read, and it is reproducible, so the
    table in SPEC.md is derived rather than tasteful.  Ties break by
    pitch-class order so the assignment is stable across runs.
    """
    order = sorted(range(12), key=lambda pc: (-counts[pc], pc))
    palette = STRONG + WEAK
    colours = [0] * 12
    for rank, pc in enumerate(order):
        colours[pc] = palette[rank]
    return colours


def predict_collide(streams: list[list[int]]) -> tuple[int, list[str]]:
    """How many cells two voices will fight over, and where.

    Two voices a diatonic step apart share a character cell and get the
    both-halves glyph -- that is not a collision.  A collision is two voices
    in the SAME half of the same cell (a unison, or an octave-plus-unison
    spelling landing on one position), or two accidentals in the same row,
    which is what the renderer counts.
    """
    total = 0
    where: list[str] = []
    for k in range(NSIX):
        heads: dict[tuple[int, int], int] = {}
        accs: dict[int, int] = {}
        for v in range(3):
            b = streams[v][k]
            if b in (0x00, 0xFF):
                continue
            p = (b & 31) - 1
            row, half = p >> 1, p & 1
            if (row, half) in heads:
                total += 1
                where.append(f"bar {k // 16 + 1} slot {k % 16}: head, voices "
                             f"{heads[(row, half)] + 1} and {v + 1} at p={p}")
            else:
                heads[(row, half)] = v
            if (b >> 5) & 3:
                if row in accs:
                    total += 1
                    where.append(f"bar {k // 16 + 1} slot {k % 16}: accidental, "
                                 f"voices {accs[row] + 1} and {v + 1} in row {row}")
                else:
                    accs[row] = v
    return total, where


def freq_table(clock: int) -> list[int]:
    out = []
    for m in range(MIDI_LO, MIDI_HI + 1):
        hz = 440.0 * 2.0 ** ((m - 69) / 12.0)
        out.append(min(0xFFFF, round(hz * (2 ** 24) / clock)))
    return out


def bytes_row(values: list[int], per: int = 16) -> list[str]:
    return [
        "        .byte " + ",".join(str(v) for v in values[i:i + per])
        for i in range(0, len(values), per)
    ]


def render(streams: list[list[int]], colours: list[int]) -> str:
    lines: list[str] = []
    a = lines.append
    a("; notes.inc -- GENERATED by tools/genmusic.py from tools/bwv847.py.")
    a("; Do not edit: run `python3 demos/fugue/tools/genmusic.py` instead, and")
    a("; `--check` proves the committed file still matches the arrangement.")
    a("")
    a("; The three voices as one contiguous block, so the renderer's voice")
    a("; stride is a constant add on a pointer built once.")
    a(f"; voice 1 at +0, voice 2 at +{NSIX}, voice 3 at +{2 * NSIX}.")
    a("notes:")
    for v, s in enumerate(streams, 1):
        a(f"; ---- voice {v} ----")
        lines.extend(bytes_row(s))
    a("")
    a("; The natural MIDI number of each ladder position, p = 0 (D6) to 29 (C2).")
    a("posmidi:")
    lines.extend(bytes_row(POSMIDI, 10))
    a("")
    a("; Pitch class -> colour nybble, by measured frequency in this arrangement.")
    a("pcolor:")
    lines.extend(bytes_row(colours, 12))
    a("")
    a(f"; MIDI {MIDI_LO}..{MIDI_HI} -> colour, so the renderer needs no modulo.")
    a("midicol:")
    lines.extend(bytes_row([colours[m % 12] for m in range(MIDI_LO, MIDI_HI + 1)]))
    a("")
    a("; Oscillator frequency for MIDI 33..88 on both machines, from")
    a(";     reg = round(hz * 2**24 / clock)")
    a("; An NTSC-tuned table played on a PAL machine is 65 cents flat on every")
    a("; note, so both ship and init picks one from $02A6.")
    for name, clock in (("ntsc", CLOCK_NTSC), ("pal", CLOCK_PAL)):
        tab = freq_table(clock)
        a(f"{name}lo:")
        lines.extend(bytes_row([v & 0xFF for v in tab]))
        a(f"{name}hi:")
        lines.extend(bytes_row([v >> 8 for v in tab]))
    a("")
    last = max(k for k in range(NSIX) for v in range(3)
               if streams[v][k] not in (0x00, 0xFF))
    a("; Where the scroll stops.  The last ATTACK is at sixteenth "
      f"{last} (bar {last // 16 + 1} slot {last % 16}), and its head reaches")
    a("; the now column at shifts = 22 + 2*k.  Halting on the sequencer's last")
    a("; sixteenth instead would be 8 sixteenths too late: the final chord is")
    a("; held to the end, so its head would have scrolled 16 columns past the")
    a("; now column and off the left edge, leaving an empty staff.")
    a(f"stopshift: .word {22 + 2 * last}")
    a("")
    a("; The closing pedal point, for the filter sweep.  bwv847.PEDAL is a pair")
    a("; of 0-BASED bar indices; the program's `bar` byte counts from 1, so")
    a("; these are converted.  Getting that wrong sweeps the filter a bar early")
    a("; and a bar short, which the spectrogram would show and nothing else")
    a("; would.")
    a(f"pedal0:  .byte {bwv847.PEDAL[0] + 1}")
    a(f"pedal1:  .byte {bwv847.PEDAL[1] + 1}")
    return "\n".join(lines) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    streams = expand()
    counts = histogram(streams)
    colours = assign_colours(counts)
    text = render(streams, colours)

    if check:
        if not OUT.exists():
            print(f"FAIL: {OUT} does not exist")
            return 1
        if OUT.read_text() != text:
            print(f"FAIL: {OUT} does not match the arrangement -- rerun genmusic.py")
            return 1
        print(f"OK: {OUT} matches tools/bwv847.py")
        return 0

    OUT.write_text(text)

    # ---- the report the spec quotes -------------------------------------
    print(f"wrote {OUT}")
    print()
    used_p = [
        (b & 31) - 1 for s in streams for b in s if b not in (0x00, 0xFF)
    ]
    print("range, as ladder positions (0 = D6 at the top, 29 = C2):")
    for v, s in enumerate(streams, 1):
        ps = [(b & 31) - 1 for b in s if b not in (0x00, 0xFF)]
        if not ps:
            print(f"  voice {v}: silent")
            continue
        hi, lo = min(ps), max(ps)
        print(f"  voice {v}: p {hi}..{lo}  = "
              f"{LADDER[hi][0]}{LADDER[hi][1]} down to {LADDER[lo][0]}{LADDER[lo][1]}"
              f"   ({len(ps)} attacks)")
    pmin, pmax = min(used_p), max(used_p)
    rows = (pmax >> 1) - (pmin >> 1) + 1
    print(f"  overall: p {pmin}..{pmax} -> ladder rows {pmin >> 1}..{pmax >> 1}"
          f" = {rows} rows needed")
    print(f"  band must cover ladder rows {pmin >> 1}..{pmax >> 1};"
          f" BANDROWS >= {rows}")
    print()
    print("pitch-class histogram (attacks, all voices):")
    order = sorted(range(12), key=lambda pc: (-counts[pc], pc))
    for pc in order:
        print(f"  {PC_NAME[pc]:>2}  {counts[pc]:5d}   colour {colours[pc]:2d} "
              f"{COLOUR_NAME[colours[pc]]}")
    print()
    print("| Pitch class | Colour | | Pitch class | Colour |")
    print("|---|---|---|---|---|")
    half = 6
    for i in range(half):
        a_pc, b_pc = order[i], order[i + half]
        print(f"| {PC_NAME[a_pc]} | {colours[a_pc]} {COLOUR_NAME[colours[a_pc]]} | "
              f"| {PC_NAME[b_pc]} | {colours[b_pc]} {COLOUR_NAME[colours[b_pc]]} |")
    print()
    total, where = predict_collide(streams)
    print(f"predicted collide = {total}")
    for w in where[:12]:
        print(f"  {w}")
    if len(where) > 12:
        print(f"  ... and {len(where) - 12} more")
    print()
    print(f"total sixteenths {NSIX}, "
          f"{NSIX * 8} frames = {NSIX * 8 / 60.0:.1f} s at 8 frames a sixteenth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
