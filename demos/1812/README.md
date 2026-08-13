# 1812

Randomised shapes painted to Tchaikovsky's *1812 Overture*, in pure 6502
assembly — a multicolour bitmap that is never cleared, a real rotating
polygon rasteriser with an even-odd scanline fill, eight 8×8 dither masks,
a per-section palette spent on purpose, an original three-voice SID reduction
that opens as a solo piano and gains instruments as it builds, and an explicit
audit-and-improve loop that ran until every spec bullet passed — the last time
round against captured audio.

`PROMPT.md` was drafted with Claude's help from detailed human direction, and
a human edited the result. Every other file here — the spec, the plan they
were built from, the sources, the audit, the regression test, the evidence
frames and the audio captures, and the packaged disk — was written by Claude
Opus 5 in answer to that prompt.

![the canvas at the end of the Marseillaise](evidence/sec1.png)
![the finished canvas](evidence/final.png)

## Watch it

`1812.d64` sits beside the sources, so stock VICE is all you need:

```sh
x64sc -ntsc demos/1812/1812.d64
```

The `-ntsc` flag matters more here than in most demos: the note table is
computed for the NTSC clock (1,022,730 Hz) and the whole arrangement is
timed in 60 Hz frames, so the PAL machine stock VICE boots by default would
play it flat and slow. To rebuild the image (and the `.prg` beside it) from
source:

```sh
c64 package demos/1812/1812.s -o demos/1812/1812.d64 --title "1812"
```

**Controls.** None while it plays — it runs for 2 minutes 50 seconds and then
holds the finished canvas. Any key restarts it with a fresh seed, read as the
live matrix code at `$CB` rather than through a ROM call.

## What is here

| File | |
|---|---|
| `PROMPT.md` | the human-directed, Claude-assisted prompt everything else answers |
| `SPEC.md` | the design: memory map, shape vocabulary, colour policy, the arrangement, and every acceptance criterion as an observation |
| `PLAN.md` | the implementation plan written before any code |
| `AUDIT.md` | the audit log — every spec bullet with the measurement that decided it, and what each iteration fixed |
| `1812.s` | load address, BASIC stub, equates, init, main loop, the IRQ wedge, includes |
| `vars.s` | every mutable byte, the observable block, and the two linker assertions that guard the memory map |
| `raster.s` | the rasteriser: quarter-square multiply, vertex transform, edge build, active-edge table, scanline fill, span fill |
| `spawn.s` | the LFSR, the spawn ring buffer, and the per-section shape policy |
| `music.s` | the sequencer, the SID shadow, and the score |
| `sections.s` | one row per section: frame budget, palette, shape mask, size range, spawn mask, and the instrument rows that spell the texture arc |
| `shapes.s` | the ten unit vertex tables and the eight dither masks, as commented `.byte` rows |
| `tables.inc` | generated: sine, bitmap row addresses, cell offsets, SID note frequencies |
| `test.yaml` | 170-step regression test: `c64 test run demos/1812/test.yaml` |
| `tools/gentables.py` | writes `tables.inc`; `--check` fails if the committed file has drifted |
| `tools/litcount.py` | counts lit pixels and checksums the canvas from a `c64 mem read` dump |
| `tools/evidence.sh` | re-runs the deterministic proof protocol and rewrites `evidence/` |
| `tools/genscore.py` | writes the five reference scores from `music.s`'s own note streams; `--check` fails if a committed score has drifted from the arrangement |
| `tools/audio-evidence.sh` | the audio half of the protocol: one capture per section, off warp, into `evidence/audio/` |
| `evidence/` | the screenshots the visual protocol captures, one per claim, and `audio/` — five section captures, each with its reference score, piano roll, spectrogram and report |
| `1812.d64` | the packaged disk image, autostartable in stock VICE |
| `1812.prg` | the assembled program `c64 package` writes beside the image |

## What a passing run shows

A black 160×200 multicolour bitmap that fills up over 2:50 with rotated,
dither-filled polygons — triangles, rectangles, pentagons, hexagons, four-
and five-pointed stars, crosses, circles, ovals and ellipses — every one of
them spawned by a note onset in the SID reduction of the Overture, and none
of them ever erased. The section of the arrangement decides the vocabulary,
the palette, the size range and the spawn rate, so the picture changes
character as the piece moves from hymn to Marseillaise to battle to cannon to
finale; sixteen cannon shots flash the whole screen white, border included,
and throw a burst of shapes. Then the canvas holds.

The arrangement moves with it. The piece opens as a **solo piano** — two hands
over a byte-identical instrument row, the third voice silent — and gains
instruments as it builds: a sawtooth reed arrives over the piano's chords and
bass hand for the Marseillaise, the battle runs all three voices, the cannon
plays two under the artillery, and the finale is three again, the
ring-modulated bells among them. The full texture is arrived at rather
than merely present, and then the hold takes every voice away again.

Everything about it is settled from registers and state bytes: 746 shapes
drawn and none dropped, all ten shape types and all eight dither patterns
used, the section boundaries exact to the frame, both of the hymn's piano
hands reading sustain 0 while voice 3's frequency shadow is still zero 900
ticks in, sixteen cannon shots, the SID shadow showing gated noise under a
swept low-pass during the artillery and a ring-modulated triangle during the
bells, and — the proof that nothing is ever cleared — 64 bitmap addresses lit
at the end of the hymn still lit at frame 10,201, with the lit-pixel count
counted off an 8,000-byte dump rather than judged by eye.

The sound has evidence of its own, which this demo did not have until its
third audit iteration: five captures under `evidence/audio/`, one per section,
each diffed against a score `tools/genscore.py` generates from `music.s`'s own
note streams rather than from a listen. All five report PASS — no diffs, no
anomalies, no clipped samples — and the hymn's piano roll shows one voice
alone for two thirds of its window, the left hand entering at frame 846 and
the third voice never appearing at all, which is the arc's first step drawn.
What the scores do not claim is tempo: the sequencer runs off the KERNAL's
60.0016 Hz jiffy while `sid_log` samples at the NTSC frame's 59.826 Hz, so the
two separate by a whole frame every 5.69 seconds. And on 2026-08-12 the
maintainer played the five captures and answered *"it all sounds very good"* —
a judgement about how the piece sounds, and about nothing else.

## The bits worth reading

**`sections.s`.** The entire coupling between the music and the picture is
one table. A section index selects a frame budget, three colours, a bitmask
of allowed shapes, a size range, an instrument row for each of the three
voices, and a mask of which voices' note onsets spawn a shape. Nothing else
in the demo knows what section it is in.

**The colour policy, in `raster.s`'s `spanfill`.** A multicolour cell has
three inks plus the background, and they are shared by everything in that
cell — so when a battle shape crosses a cell the hymn painted, the hymn's
pixels there become battle colours. That is the design, not a bug: the
picture ages toward the current section instead of staying a pile of
stickers. It works because a section change updates only the two palette
bytes and repaints *nothing*; a cell takes the new colours when, and only
when, a shape of the new section actually covers it.

**`AUDIT.md`, iteration 1.** The most interesting bug in the demo was not in
the rasteriser. `rndlt` drew random values by reject-and-retry, which is the
textbook answer and is wrong on a shift register: consecutive LFSR outputs
differ by a single shift, so rejecting until a value falls below 8 stops
almost always on the same bit pattern. Two of the eight dither patterns never
appeared in an 889-shape run. The measurement that caught it was a state
byte — `patseen`, a bitmask OR'd once per shape — and the fix made the demo
seventeen times faster at drawing its parameters as a side effect.
