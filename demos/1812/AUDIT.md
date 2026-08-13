# 1812 — audit log

The improvement loop `PROMPT.md` asks for: evaluate every `SPEC.md` bullet
against the running machine, review the code, fix, re-verify. Every verdict
below comes from a stopped machine — a register, a state byte, a counted
`c64 mem read` dump or a `c64 profile` measurement. None comes from reading
the source.

Cycle counts are NTSC wall cycles from `c64 profile` (badline DMA included,
which is the frame-budget truth). One NTSC frame is 17,095 cycles.

---

## Iteration 0 — groundwork

Before any of the demo existed, two things the spec asserts had to be true.

| Claim | How it was checked | Verdict |
|---|---|---|
| `$02`, `$22-$2A` and `$FB-$FE` are free while the demo owns the machine | Wrote `$5A` into all fourteen, parked a probe in its own `jmp *` loop with the KERNAL IRQ chained, ran 600 interrupts (`until wedge --count 600`; the jiffy clock advanced 599, proving the chain was live), read them back | **PASS** — all fourteen still `$5A` |
| The generated tables are what the references say | `tools/gentables.py --check` re-derives every table; A4 = 7218, matching `references/hardware.md`'s note table exactly | **PASS** |

**Corrected by the machine.** `PLAN.md` claimed `rowaddr[199] = $3F3F`. It is
`$3E07` — `$3F3F` is the *last byte of the bitmap*, which is
`rowaddr[199] + 8·39`. The generator's self-test caught it; the plan was
amended rather than the code.

---

## Iteration 1 — the first full run

The demo played all 10,200 frames. Section boundaries landed exactly on
2400 / 3900 / 6000 / 7800 / 10200.

### Evaluate

| Criterion | Observation | Verdict |
|---|---|---|
| A1 mode | `$D011=$3B`, `$D016&$1F=$18`, `$D018&$FE=$18`, `$D020/$D021&$0F=0` | PASS |
| A2 black canvas | `litcount` = 0 at the first `drawshape` stop | PASS |
| A3 counter rises | 889 shapes, monotone across ten stops | PASS |
| A4 sections | boundaries exact to the frame | PASS |
| A5 rotation | a size-64 square at angle 32 transforms to (80,36) (111,100) (80,163) (48,100) — a true diamond | PASS |
| A6 accumulation | `litcount` non-decreasing; 24 of 24 sampled early addresses still lit late | PASS |
| A7 cannon | `cannons` = 16 | PASS |
| A8 sound | voice 3 control `$81` mid-cannon, `$15` mid-finale | PASS |
| A9 determinism | not yet tested | — |
| **A10 budget** | **`dropped` = 142** | **FAIL** |
| **A11 vocabulary** | `typeseen` = `$03FF`, **`patseen` = `$F3`** | **FAIL** |
| A13 cost measured | `spanfill` 3,279 · `xform` 26,674 · `drawshape` 511,980 (30 frames) | PASS |

### Review

Two findings, both real.

**Finding 1 — the dither patterns were not uniform, and two never appeared.**
`patseen = $F3` means patterns 2 and 3 were never drawn in 889 shapes. The
RNG was not at fault in isolation (`rndlt(8)` over 20,000 draws is flat).
The bias was *positional*: `rnd` advanced the LFSR one step per call, so
consecutive outputs differ by a single right shift and are not independent
samples. `rndlt` rejected until a value fell below its bound, which turned
that correlation into a hard bias — the first value below 8 is almost always
the one whose bit 3 has just shifted into bit 2. Simulated distribution
before the fix: `[107, 11, 22, 0, 750, 692, 810, 608]`.

**Finding 2 — 135 of the 142 drops were in the battle.** Measured per
section: hymn 0, Marseillaise 0, battle 135, cannon 7, finale 0. The battle
asks for ~612 shapes in 2,100 frames — one every 3.4 frames — against a
measured cost of about 3.5.

### Improve

1. **Quarter-square multiply.** `a*b = f(a+b) - f(a-b)` with
   `f(x) = floor(x²/4)`, built at startup by `qsgen` into `$C000-$C3FF`.
   Not in the `.prg`: the program has under 100 bytes of headroom below the
   bitmap, and 1 KB of table would not fit. `smul` **330 → 141 cycles**.
2. **Attribute stamp once per cell row.** A shape's scan visits a cell row
   for eight consecutive scanlines and never returns, so a per-cell-row
   "already claimed" flag turns eight stamps into one without ever stamping
   a cell the shape does not cover.
3. **Rasteriser working storage moved to `$C400`.** The BSS assertion
   (added this iteration) fired when the `stamped` array pushed the program
   past `$2000`. The ~370 bytes of edge arrays have no business competing
   with the bitmap for the low 8 KB.

### Re-verify — and a regression I caused

Fixing finding 1 by making `rnd` take eight LFSR steps per call worked for
distribution (`patseen = $FF`) and **made the budget worse**: `dropped`
saturated at 255. `rndlt` rejects `256/bound` times on average, so bounds of
3, 4 and 8 cost 85, 64 and 32 draws — about 200 `rnd` calls per shape, each
now 6.5× more expensive. `pickshape` had become ~25,000 cycles.

The fix was to stop rejecting. `rndlt` now **scales**: `v = (rnd·bound) >> 8`,
one draw and one multiply. Scaling reads the *top* bits of the draw, which are
the freshly shifted-in ones, so it is correlation-free as well as cheap.
Simulated distribution after: `[482 … 546]` against an ideal 500, and every
size in every range reachable. `pickshape` **~25,000 → 1,477 cycles**.

`dropped` fell 142 → **59**, all in the battle (52) and cannon (7).

### The remaining gap — a policy decision, stated as one

Three rounds of optimisation had more than halved the shape cost and the
battle still dropped 52. The battle listened to all three voices, and voice 1
there is a running sixteenth-note figure of duration-6 events — 7 real ticks
each, so 300 onsets in 2,100 frames, one every seven. That is texture, not
accent. `secspawn[2]` changed from `%111` to `%110`, so the battle spawns on
the stabs and the bass hits.

This is a design choice about what a shape should mark, not a way of making
a number go away, and it is recorded here as such. `dropped` = **0**.

---

## Iteration 2 — evaluate again, and look at it

### Evaluate

Full protocol re-run (`tools/evidence.sh`). Every criterion PASS:

| Criterion | Observation |
|---|---|
| A1 | `$D011=59`, `$D016=216` (`&$1F=24`), `$D018=25` (`&$FE=24`), `$D020/$D021=240` (`&$0F=0`) |
| A2 | `lit=0 checksum=00000000` at the first `drawshape` |
| A3 | 732 shapes; `litcount` 3,913 → 20,853 → 27,991 → 28,309 → 29,845 → 29,980 — **superseded by iteration 3's arrangement**, which reads 746 and moves every rung but the first |
| A4 | 2400 / 3900 / 6000 / 7800 / 10200, exact |
| A5 | rectangle at angles 0/48/96 — three different vertex sets, three PNGs |
| A6 | **64 of 64** addresses lit at the end of the hymn still lit at frame 10,201 |
| A7 | `cannons=16`; `$D020/$D021 = 241` during the flash, `240` eight frames later |
| A8 | mid-cannon voice 3 control `129` (`$81` noise+gate), routing `244`, volume `31` (`$1F` low-pass); mid-finale control `21` (`$15` ring+triangle); volume `0` in the hold |
| A9 | see below |
| A10 | `dropped = 0`, reproduced across two independent full runs |
| A11 | `typeseen = $03FF`, `patseen = $FF` |
| A12 | `shapes` unchanged over 120 frames of hold; a key resets `shapes` to 0, clears the bitmap and mixes the jiffy clock into `seed` |
| A13 | `smul` **111–151** over 9 poked operand cases · `rnd` **29 or 38 blanked, nothing between** (96 arrivals over two runs, mean 33.0; `+43` per badline with the screen on) · `pickshape` 1,477 · `xform` 14,961 · `spanfill` 4,384 · worst-case `drawshape` 483,327 (28 frames) — see *A13's first two figures*, below |
| A14 | `1812.d64` built; `x64sc -ntsc demos/1812/1812.d64` |

**A9 needed its anchor corrected.** Two passes with seed `$9977` compared at
the same *frame* count disagreed: identical lit counts, different checksums.
They had not diverged — a frame boundary had fallen inside a half-painted
shape, so the two passes were being compared at different points of the same
sequence. Re-anchored on `until shapedone --count 400`, the two passes agree
on `rng`, all last-shape bytes, the lit count, the checksum **and** the frame
number. `SPEC.md` A9 was amended to name the shape boundary and say why.

**A13's first two figures were single numbers for routines that do not have
one.** `smul 141` and `rnd 72` were quoted bare, and a reader who re-measured
got something else and could not tell whether anything had regressed.
Re-measured on the tracked build with the screen blanked, so the counts are CPU
work with no badline steal:

```
c64 session start --headless --warp -s a13off ; c64 load 1812.prg --symbols 1812.lbl
c64 until drawshape --count 40        # qsgen's $C000-$C3FF tables are built by here
c64 mem write '$d011' '$2b'           # DEN clear; $D011 is written once, at 1812.s:127
c64 until drawshape --count 2         # so DEN is already 0 at the next raster $30
c64 profile rnd --samples 64 ; c64 profile rnd --samples 32
c64 mem write MULA '$fb' ; c64 mem write MULB '$07' ; c64 profile smul --samples 1
```

**`rnd` has exactly two paths and no third: 29 and 38 cycles.** It is a Galois
LFSR that advances `rng` itself (`spawn.s:19-27`), so it is the one routine here
that `--samples` sweeps honestly — N arrivals are N different states. Blanked:
min **29**, max **38**, **mean 33.0 over 96 arrivals** (64, then a further 32),
53 twenty-nines to 43 thirty-eights. The two values interleave irregularly, not
alternately — the longest run of one value across the 96 is seven.

**And the row's `72` is `29 + 43`: the 29-cycle path plus one badline.** With
the screen on, whether *any* arrival is inflated is governed by **where the
raster was parked when you stopped**, not by the screen being on. 96 arrivals of
a ~35-cycle routine span only about 54 raster lines, so the sampling window
either overlaps the badline range (`$30`–`$F7`) or it misses it entirely. Same
build, screen on throughout (`$D011` read back `$3B` in every run),
`c64 profile rnd --samples 96` at seven anchors:

| anchor | raster line at the stop | inflated | values seen |
|---|---:|---:|---|
| `until drawshape --count 40` | 251 | 0 / 96 | 29, 38 |
| `until drawshape --count 41` | 243 | 0 / 96 | 29, 38 |
| `until drawshape --count 42` | 13 | 2 / 96 | 29, 38, 72, 81 |
| `until drawshape --count 43` | 218 | 4 / 96 | 29, 38, 72, 81 |
| `until drawshape --count 45` | 192 | 7 / 96 | 29, 38, 72, 81 |
| `until drawshape --count 50` | 114 | 7 / 96 | 29, 38, 72, 81 |
| `until drawshape --count 55` | 149 | 6 / 96 | 29, 38, 72, 81 |

The inflated values are only ever **72** and **81** — `29 + 43` and `38 + 43`,
one badline's DMA on whichever path that arrival took. So the original `72` was
a real reading of a real event; what it never carried was the anchor that
produces it, and an anchor two shapes away produces none at all. Quote `rnd`
blanked, or quote it with the raster line beside it.

**`smul` is 111–151.** Three things move it: each negative operand costs a
magnitude fixup, `umul` costs 5 more when `|a−b|` needs a negate, and 2 more
when `a+b` carries into the table's upper half (`raster.s:287-296`). Nine poked
cases, one arrival each, blanked:

| MULA, MULB | cycles | | MULA, MULB | cycles |
|---|---:|---|---|---:|
| `+7, +5` | 111 | | `−7, −5` | 137 |
| `0, 0` | 111 | | `−128, −128` | 139 |
| `+127, +127` | 111 | | `−5, +7` | **141** |
| `+5, +7` | 116 | | `−5, −7` | 142 |
| | | | `+5, −7` | **151** |

`−7, −5` at 137 against `−128, −128` at 139 is that third term on its own: both
negative, neither needing the `|a−b|` negate, and only the second summing past
255. It is also the one row here the **program cannot produce** —
`raster.s:278-280` records that operand magnitudes are at most 127, so `a+b`
never exceeds 254 and that carry branch is dead in this program. It is in the
table as the boundary, not as a case.

So `141` *is* reproducible — but not under the condition previously recorded.
It is **A negative and B positive**; both-negative-with-the-smaller-magnitude-
first is 142. The two figures had been transposed onto the wrong case.

**And `--samples` must not be used on `smul` at all.** It overwrites `MULA` and
`MULB` with their magnitudes (`raster.s:330`, `:336`, `:341` — the source says
so in a comment), so every arrival after the first is handed a case nobody
asked for. From a poked `−5, −7`, `c64 profile smul --samples 4` returns
**`[142, 116, 116, 116]`**: one real measurement, then three of `+5, +7`. That
is a spread with a min, a max and a mean, and all of it after the first entry is
an artefact of the routine having eaten its own inputs.

### Review — as a viewer

The Marseillaise is the best-looking section: blue / red / white has real
luminance separation, so overlapping shapes stay legible and the dither masks
read as translucency rather than noise. The hymn works for the same reason —
it is the palette's own grey ladder.

The finale did not. Yellow / light green / white are all bright, so shapes
dissolved into each other and the section read as mush. Changed to
**6 blue / 7 yellow / 1 white** — the same kind of ladder that makes the
Marseillaise work, and still distinct from the battle's reds and the cannon's
browns, so the canvas keeps reading as strata.

### Review — the arrangement

**I cannot hear this.** No claim below is a claim about how it sounds; every
one is the SID shadow read back at a stopped machine and decoded from
frequency to pitch (`Fn · 1022730 / 2²⁴`). Whether the reduction is *good* is
a judgement a human with speakers has to make, and this audit does not make
it.

What the bytes do show is that each section is playing the material it was
written to play, on the instrument it was written for:

| Frame | Section | Voice 1 | Voice 2 | Voice 3 | Filter |
|---|---|---|---|---|---|
| 40 | hymn | E4 triangle | B3 triangle | E2 pulse | off, vol 15 |
| 2600 | Marseillaise | **D5** pulse | C4 sawtooth | D3 pulse | off, vol 15 |
| 4600 | battle | G4 sawtooth | B4 narrow pulse | D3 sawtooth | **`$F1` route v1, `$2F` band-pass** |
| 6200 | cannon | E4 triangle | B3 sawtooth | **C2 noise, gated** | **`$F4` route v3, `$1F` low-pass** |
| 8300 | finale | A5 pulse | B4 sawtooth | **E4 `$15` triangle + ring mod** | off, vol 15 |

The pitches are the scored ones — the hymn's opening E minor triad, the
Marseillaise's held D5, the finale's melody an octave up — and the three
effects the prompt names are all present in the register bytes: the battle's
band-passed sawtooth, the cannon's gated noise under a low-pass whose cutoff
is swept from `$FF` to `$10` over 24 frames, and the finale's
ring-modulated triangle bells with a decay-only envelope (`AD=$0A`,
`SR=$00`).

### Two things the test suite got wrong, not the program

Both were assertions that contradicted the design, caught by running them:

- `test.yaml` asserted the finale palette on screen cell `$0400`. A section
  change deliberately does **not** repaint cells — re-tinting follows the
  shapes' geometry (`SPEC.md` §3) — so cell (0,0) still held the cannon's
  palette. The assertion now reads `palscr`/`palcol`, which is the actual
  contract.
- The routine-level `call:` steps sat in the middle of the file. `c64 call`
  ends at a trap address and throws away the PC the demo was running at, so
  every timeline step after them failed with the machine back at `READY.`.
  They are now last, after everything that needs the demo still running.

The test was then broken on purpose (`cannons` 16 → 15) to confirm it fails
at that step, and reverted. 136 steps, exit 0.

---

## Iteration 3 — the arrangement, heard

Three things happened in this iteration: the piece was re-voiced into a
**texture arc** (`f57b904`), seven performance candidates were profiled and one
of them landed (`52b2ed3`), and the demo was **captured as audio and scored**
for the first time. Iteration 2's arrangement review had to open *"I cannot
hear this."* This one does not.

Three protocols produced everything below, and each is re-runnable:

- `tools/evidence.sh` — one detached run under `caffeinate -dimsu`, exit 0, six
  `--warp --headless` sessions, the piece played three times; twelve PNGs and
  the state bytes quoted here. `shipped-d64.png` is the thirteenth, taken by
  hand from the packaged image afterwards.
- `tools/audio-evidence.sh` — five real-time captures, one per section, into
  `evidence/audio/`; five `capture.wav` + `sid-log.jsonl` + `piano-roll.png` +
  `spectrogram.png` + `report.md`.
- `c64 test run demos/1812/test.yaml --json` — **170 steps, `passed: true`,
  40.87 s**; the step indices cited below are that run's.

### Evaluate

| Criterion | Observation | Verdict |
|---|---|---|
| A1 mode | `$D011=59`, `$D016=216` (`&$1F=24`), `$D018=25` (`&$FE=24`), `$D020/$D021=240 240` (`&$0F=0`); re-read with their masks at test steps 2-6 | PASS |
| A2 canvas starts black | `lit=0 checksum=00000000` at the entry to the first `drawshape` | PASS |
| A3 counter only rises | **746** shapes at the end — 33 / 121 / 435 / 555 / 746 at the five section ends, and 435 → 480 across two `seqtick` stops in the test (steps 55, 57) | PASS |
| A4 sections progress | `frames` = 2400 / 3900 / 6000 / 7800 / 10200 at the five `secchange` stops, exact; test steps 32 and 37 read `$0960` and `$0F3C` at the first two | PASS |
| A5 rotation is real | one rectangle at `lsangle` 0 / 48 / 96 → vertices `x=12 67 67 12` / `55 76 24 3` / `79 39 0 40`; three different vertex sets, three different bitmaps | PASS — but see the instrument note under *Re-verify* |
| A6 nothing is ever cleared | `litcount` **3,913 → 24,946 → 28,807 → 28,973 → 29,804 → 29,947**, non-decreasing; **64 of 64** addresses lit at the end of the hymn still lit at frame 10,201 | PASS |
| A7 the cannon | `cannons` = `$10` = **16** at the end of section 3 (test step 75); `$D020/$D021 = 241 241` during a flash and `240 240` eight frames later | PASS — the number comes from `test.yaml`, for the reason below |
| A8 sound happened | mid-cannon voice 3 control `129` (`$81`, noise + gate), routing `244` (bit 2), `$D418` `31` (`$1F`, low-pass, volume 15); mid-finale control `21` (`$15`, triangle + ring mod + gate); volume `0` in the hold | PASS |
| A9 determinism | at `shapedone --count 400`: `$1812` twice → frames 5,770, `rng $08EB`, `lit 28,967`, checksum `c8b13257`; `$9977` twice → frames 5,772, `rng $1A9C`, `lit 28,412`, `503d64b0`. Same seed identical in every column; different seeds differ in every column | PASS |
| A10 the budget fits | `dropped = 0` at all five section ends and at frame 10,202; test steps 58, 91 and 110 read it 0 as well | PASS |
| A11 vocabulary | `typeseen = $03FF`, `patseen = $FF` (test steps 89, 90) | PASS |
| A12 hold and restart | `shapes = 746` 120 frames into the hold, byte-for-byte unchanged (steps 98, 102); after the keypress `shapes = 1`, `section = 0`, `cannons = 0`, `rng`/`seed` move from `$27F1`/`$1812` to `$3D22`/`$E91B`, and the first 32 bitmap bytes are zero | PASS |
| A13 cost is measured | `smul` **111–151** over nine poked cases · `rnd` **29 or 38** blanked · `spanfill` 2,985.4 mean on a poked 160-pixel span · worst-case `drawshape` **480,131 → 467,500.5** (see *Improve*) | PASS |
| A14 it ships | `c64 package` → `1812.d64`; booted from the image with `disk boot` and stopped at `seqtick` ×300 with `shapes = 5` (`shipped-d64.png`); the program ends at `$1F88`, **120** bytes below `$2000` | PASS |
| **A15 the arrangement is heard** *(new)* | five captures, five `report.md` **PASS** — 0 diffs, 0 anomalies, `nothing_played` false, 0 clipped samples, each WAV of real duration (18.44 / 15.14 / 10.25 / 15.36 / 15.28 s) | PASS on the machine half; **the maintainer's listen is outstanding** |
| **A16 the piano envelope** *(new)* | at `seqtick` ×900, `sidshadow+6 & $F0 = 0` and `sidshadow+13 & $F0 = 0` — both piano hands hold sustain 0 (steps 26, 27) — while `sidshadow+14` still reads `0000`, so voice 3 has not sounded at all (step 29) | PASS |

A15 and A16 did not exist before this iteration; they were added to `SPEC.md`
§12 in it, which is why the first table entry for each is here.

**A7's number does not come from the evidence run, and could not.**
`tools/evidence.sh` stops at the *first* `cannonfire` and prints `cannons=1`;
it never samples a final count. The audio protocol cannot supply it either —
`tools/audio-evidence.sh` rewinds section 3's streams at log frame 0, which
re-fires shot 1, so `cannons` over-counts during that run **by construction**,
and the script's own header says so. The sixteen is `test.yaml`'s: it reads
`cannons` at the end of section 3 and separately compares section 3's V3 stream
against sixteen `$FD`/`112` pairs, which pins the count and the spacing as
data. That is a gap in the *visual* protocol, not in the demo, and it is in the
friction log rather than left here as a shrug.

### Review — as a listener

**This is the first iteration that could listen, and the machine did the
listening.** Five windows, one per section, each opening on its section's first
tick; the reference scores were modelled from `voicetick` one frame at a time
by `tools/genscore.py` and never edited to fit a capture. All five passed on
the first run.

| section | window | frames | verdict |
|---|---|---|---|
| hymn | 18.1 s | 1089 | PASS |
| Marseillaise | 14.9 s | 892 | PASS |
| battle | 10.0 s | 599 | PASS |
| cannon | 15.1 s | 905 | PASS |
| finale | 15.0 s | 900 | PASS |

The arc is legible in the images, which is the point of having them:

- **`hymn/piano-roll.png`** — red alone for the first two thirds, the
  troparion's rising fourth and stepwise descent intact; green enters at
  **frame 846** low in the range and climbs a broken triad; **blue never
  appears at all** across 1089 frames. One instrument, then two, and the third
  provably absent.
- **`marseillaise/piano-roll.png`** — red and green from frame 0, blue's first
  bar at **frame 493**, root-and-fifth on the beat from there. Two becoming
  three, where `s1v3`'s rests put it.
- **`battle/piano-roll.png`** — all three from frame 0; red a chromatic zigzag
  of 3-frame bars, green sparse off-beat stabs, blue the octave bass. Nothing
  off the grid.
- **`cannon/piano-roll.png`** — red and green converge on E4 as the data says,
  and blue is **eight 109-frame bars at C2 spaced 112–113 frames apart**: the
  noise oscillator naming its own register rather than a pitch.
- **`cannon/spectrogram.png`** — each shot is a broadband vertical smear
  filling the gaps between the sustained voices' harmonics. Measured off the
  WAV: over 1.5–4 kHz the first 0.30 s after a shot averages **3.4 dB** above
  the level between shots, the onsets recur at **1.8833 s** (113 ticks at
  60.0016 Hz), and the band is back to the floor **0.35–0.40 s** later — the
  24-frame cutoff sweep, expiring on time.
- **`finale/piano-roll.png`** — three dense colours, the hymn an octave up and
  arched, green and blue interleaving rather than doubling.

**What this evidence does not claim.** No score asserts a duration. The
sequencer runs off a CINV wedge on the KERNAL's CIA jiffy — **60.0016 Hz** —
while `sid_log` samples once per NTSC video frame — **59.826 Hz** — so the log
runs ahead of the model by about one frame per 300, one-sidedly: the hymn's
left hand is modelled on tick 849 and heard at frame 846, the Marseillaise's
bass on tick 495 and heard at 493, and the cannon's intervals come back
`112 113 113 113 112 113 113 112` against a modelled 113. The scores therefore
claim the **event sequence for every voice, every gate-down rest included**,
and each window was cut so the last modelled event clears its edge. Prose that
wants to say the tempo is exact has the transcription tables to quote, not
these verdicts.

**And the listen itself has not happened.** Everything above is a machine's
account of the arrangement; whether the reduction *sounds* like the Overture is
a judgement a human with speakers makes. Iteration 2 stated that limit and
stopped there. This iteration states it as a standing acceptance criterion —
`SPEC.md` §12 A15 — with the five WAVs named, so the gate is a thing that can
be met rather than an intention.

### Improve — the texture arc

**The piece now opens on one instrument and gains them:** 1 → 2 → 3 →
2 + artillery → 3 → 0 (`f57b904`). Section 0 is a **solo piano** — voices 1
and 2 are two hands over a byte-identical `secinstr` row, and voice 3 is
silent; section 1 gains a sawtooth reed over the piano's chords and bass hand.
Sections 2, 3 and 4 were not touched. The defect it answers is an envelope
one, and it is measurable rather than aesthetic: the old hymn rows held
sustain nybbles 10, 9 and 10, and a non-zero sustain level is what makes a
struck instrument read as a sustained organ. Both hands now read sustain 0 on
the machine (A16 above).

**What it cost the picture: nothing that needed tuning.** `shapes` reads 33 at
the end of the hymn — the largest shapes in the piece, against the 19 onsets
the old stream fired (`f57b904`) — and `dropped` is still **0**. No
spawn mask, size range or frame budget was touched to absorb it: `secspawn` is
still `%001, %011, %110, %001, %111, %000`, byte for byte what iteration 1's
policy decision left, so `sections.s`' rationale beside that table still
describes the masks it sits above.

### Improve — the seven performance candidates, decided in writing

**Anchors here are labels, not line numbers.** The first version of this section
cited `raster.s:809-814` for `sfloop`; a comment edit twelve lines above it, in
the same wave, moved that block to 821-826 and the citation went stale before
the branch even closed. Routine and label names are what survive — the same
convention `docs/todo.md`'s preamble states, for the same reason.

Seven optimisation candidates were profiled. **Six are dropped, each with the
number that dropped it; one is implemented.** None of it was required: `dropped`
was already **0** at frame 10,200 with a ~42% margin, so the measurement *is*
the deliverable, and the one change that landed did so because it is 2.6% of a
worst-case shape for 47 bytes and provably cannot move a pixel.

Figures are NTSC wall cycles from `c64 profile`, taken on the worst-case shape
(`sh_type 5 / sh_size 90 / sh_cx 80 / sh_cy 100 / sh_angle 0`) unless a row says
otherwise. The denominator throughout is a worst-case `drawshape` of **480,131**
(mean of 2, 480,127–480,135). Rows marked *apportioned* are derived from a
measured per-cell cost rather than profiled directly: a worst-case shape writes
**3,161** bitmap cells (`lsbytes` read back) at a measured **52 cycles** each —
(2,600 − 623) / 38 middle cells — which is the hand count of 34 (the middle-cell
loop) plus 18 (the `sfa1` per-cell `stamped` scan). An apportionment is enough
to **drop** a candidate and is never used as a before number for anything
implemented.

| # | candidate | before | share | verdict |
|---|---|---|---|---|
| 1 | offscreen rows run the crossing sort for nothing | **6,032 ±90** | 1.3% | dropped — conditional, and now mostly gone |
| 2 | the per-cell-row `stamped` clear and per-cell test | **≈67,000** *apportioned* | 14% | dropped — **the mechanism is unsound here** |
| 3 | `xform` transforms every vertex | **15,607.9** (8 samples, 15,600–15,648) | 3.25% | dropped — the ceiling is too low |
| 4 | per-span dither/ink/AND-OR recompute | **≈22,000** *apportioned* | 4.6% | dropped — only half is realisable |
| 5 | the crossing bubble sort runs a full pass for 2 crossings | **21,409** worst, **6,949** typical | 4.5% | **implemented** — 9,419 / 4,221 |
| 6 | the middle-cell fill loop | **≈92,000** *apportioned* | **19%** | dropped — **byte-blocked, not effort-blocked** |
| 7 | `buildedges`' bubble sort of up to 16 edges | **14,492.9** (8 samples, 14,369–14,628) | 3.0% | dropped — the number |

**1 — offscreen rows run the crossing sort for nothing. Dropped.**
6,032 ±90 measured as a patched L1−L2 differential at `sh_cy 0`, `sh_size 90`
with `symax` forced to `$FFFF`; ≈6,320 including the `jmp cssort` trampoline.
Three things compound. It is **zero on a shape entirely on screen** — at
`sh_cy 100` the same shape measures `symin 11 / symax 189`, no offscreen rows to
skip. `sfloop`'s own screen-bottom test already exits at the bottom of the
screen, so only *top*-clipped shapes could gain at all. And the scanline cost
is set by
admission order rather than geometry, so 6,032 is one shape at one angle, not a
per-shape saving. Candidate 5 has since cut the sort this would skip by 56%,
leaving ≈2,700 on that same configuration — an inference from the measured 56%,
not a fresh measurement.

**2 — the per-cell-row `stamped` clear and per-cell test. Dropped on
soundness, not on size.** ≈67,000 apportioned (3,161 cell-visits × 18, plus ~24
cell rows × ~406 for the 40-byte clear). The proposed mechanism is a stamped
interval `[lo,hi)` per cell row, justified by "a convex shape's spans in one cell
row are contiguous". **Three of this demo's ten types are not convex.**
`shapes.s` carries star5 (type 4), star4 (8) and cross (9), and `maxcross`
reaches **4** — which is exactly two disjoint spans on one row. An interval over
two disjoint spans claims the gap between them; those gap cells are then never
palette-stamped, and a later scanline in the same cell row whose span *does*
cover them is skipped as "already stamped", leaving the previous shape's colour
under the new shape's pixels. That breaks the contract in `sfattr`'s header
— *"without ever stamping a cell the shape does not cover"* — and `test.yaml`
asserts `typeseen == $03FF`, so all ten types really do run. A correct variant
must keep the byte array as a fallback and add a per-cell-row contiguity flag,
which is a materially larger change than the mechanism as stated, in the hottest
routine in the demo. **Recorded here so it is not picked up later as written and
shipped as a bug: this is not an unprofitable optimisation, it is an incorrect
one for this shape set.**

**3 — `xform` transforms every vertex. Dropped.** 15,607.9 mean over 8 samples
(`c64 profile xform --samples 8`), 3.25% of a shape. The mechanism is central
symmetry — `v[k+n/2] == -v[k]`, true for 7 of the 10 types — so reflect instead
of transforming. A *perfect* halving of the whole routine buys ~1.6% of a shape
and applies to 7 types of 10, so the realised figure is lower again. The ceiling
is the number.

**4 — per-span dither/ink/AND-OR recompute. Dropped.** The recompute
(the dither/ink block at the head of `spanfill`, down to the `ORB1` store) is
~100 instruction cycles of the 623-cycle minimum measured on a short span
(`c64 profile spanfill` at `spy 100 / spxa 0 / spxb 8`: 696.2
mean, 623 min, 1,123 max over 8); over ~222 calls that is ≈22,000 = 4.6%. It
depends only on `(sh_pat, sh_ink, spy&7)`, so a per-shape table indexed by
`spy&7` would replace it — but the table still costs ~52 cycles per call to
read, so only ~48 of the ~100 survive: ≈10,600 = **2.2% of a worst-case shape**,
for 48 bytes of table in `RWORK` plus ~60 bytes of `.prg` and a new per-shape
initialisation step in `drawshape`. Dropped on the number.

**5 — the crossing bubble sort runs a full pass for 2 crossings. Implemented**
(`52b2ed3`, `perf(1812): straight-line the two-crossing case out of the scanline
sort`; the comment block above `cssort` in `raster.s` is its account in
source). `ncross == 2`
now takes one signed compare and at most one swap.

| leg | before | after | move |
|---|---|---|---|
| sort only (patched L1−L2), worst case, 179 rows | **21,409** | **9,419** | −11,990, −56.0% |
| sort only (patched L1−L2), typical (`sh_type 8` @ 27, 49 rows) | **6,949** | **4,221** | −2,728, −39.3% |
| `c64 profile scanfill --samples 1`, worst case | 443,724 | 430,997 | −12,727, −2.87% |
| `c64 profile scanfill --samples 1`, typical | 78,686 | 75,996 | −2,690, −3.42% |
| `c64 profile drawshape --samples 2`, worst case | 480,131 | 467,500.5 | −12,630, −2.63% |

Each patched leg is a single arrival at ~±45, so each differential carries ~±90.
**The differential rows and the whole-routine rows are not two readings of one
number, and the 737 between −11,990 and −12,727 is not error.** The 47 bytes
shifted the four tables behind the five absolute-indexed reads whose
page-crossing status it changed — `dither` (read twice, at `dither` and
`dither+1`), `rowaddrl`, `rowaddrh`, `attrcoll`, which is where the −480 is
counted; `spanfill`'s other absolute-indexed reads moved too and contributed
nothing, their crossing status being the same either side — and took the one
taken `→ sfnext` branch
per row off the `$1100` boundary, which makes the *untouched* row body 656
cycles cheaper — real work, collected by `scanfill` and `drawshape`, and
cancelled by construction in the differential, whose two legs both delete that
body. −11,990 is the sort; −12,727 is the sort plus the relocation. (Measured
by re-profiling both builds with the screen blanked; the method note is in
`docs/cli.md` under `c64 profile`.)
The typical shape gains 39% and not 56% because `sh_type 8` is star4, one of the
three concave types: some of its rows carry four crossings and still take the
bubble sort. It went in because it cannot change a painted byte *by
construction* — for two elements the fast path performs the identical signed
comparison and the identical swap, so the permutation is the same one — and
because the identity check that exercises the changed path already existed.
Identity across every region the rasteriser writes, 400 shapes off the pinned
`$1812` seed: bitmap `$2000-$3F3F` `lit=28967 checksum=96e4e3b7`, screen RAM
`$0400` `fde5f0de`, colour-RAM `$D800` low nybble `e75d260e` — all three
unchanged. Cost **47 bytes**: `.prg` 5,888 → 5,935, free below `$2000` 167 → 120.

**6 — the middle-cell fill loop. Dropped because it does not fit — and this is
the largest single line item in the demo.** ≈92,000 = **19% of a worst-case
shape**, apportioned from the 34 of 52 cycles each of the 3,161 cells costs; the
measured anchor is `c64 profile spanfill` at `spy 100 / spxa 0 / spxb 160`,
2,985.4 mean, 2,600 min, 4,389 max over 8. The X-stride form does not reach:
8 × 38 middle cells = 304, past an 8-bit index. The form that pays is a **4-cell
unrolled chain** (`ldy #0/8/16/24` with a `+32` re-base), 34 → ~23.5 cycles per
cell ≈ 6% of a shape — but it needs two parity entry points (`ANDM0/ORB0` against
`ANDM1/ORB1`) plus a remainder path, **≈130 bytes against the 120 now free below
`$2000`**, and the BSS-overrun `.assert` at the end of `vars.s` turns an
overrun into a build error. **The byte figure is the binding one, and 120 is
the number to watch**: anything that frees space below `$2000` re-opens this
candidate and anything that consumes space closes it further.

The cheap variant — stepping `Y` by 8 instead of adding 8 to `BMPPTR`, ~25 bytes
— saves 5 of 34 cycles per cell, ≈14,000 per worst-case shape = **2.9%**, and is
the first thing a future pass should pick up. It is *not* covered by the
400-shape checksum, and the reason is worth knowing: it needs a re-base past 32
middle cells whose correctness interacts with the even/odd dither parity, and on
the current tables **the demo cannot produce a span that wide at all** —
`secsizehi`'s largest entry is 90, the largest vertex radius in `shapes.s` is
the cross's (64, 22) → r = 67.7, and `xform` shifts right twice for x, so the
half-width ceiling is 67.7 × 90 × 127 / 16384 ≈ 47 multicolour pixels, so a span
is at most 95 pixels wide and touches at most **25** cells — `floor((o+94)/4) −
floor(o/4) + 1` at the worst alignment `o` — leaving **≤ 23 middle cells**. (The
task report said 24 cells and 22 middle cells, which is what a span aligned to a
cell boundary touches; one straddling a boundary reaches 25 and therefore 23.
The margin against 32 is what the claim rests on, and it is unaffected either
way: 23 < 32.) That margin is a property of the size tables, not of the loop:
raise `secsizehi`, add a shape with a larger vertex radius, or change
either shift in `xform`, and it moves. The proof that would clear the variant is
a targeted span identity — poke `spy` / `spxa 0` / `spxb 160` at both `spca`
parities on both builds, `c64 mem read` the affected bitmap rows and compare byte
for byte — *then* the 400-shape checksum.

**7 — `buildedges`' bubble sort of up to 16 edges. Dropped on the number.**
14,492.9 mean over 8 samples at angle 0 (14,369–14,628), worst angle found is
192 at 16,359 mean / **16,381** max; the natural mid-run 8-edge shape is 3,444.
Anchor: `c64 profile $0eb9 --samples 8` after `call xform`, `$0EB9` being the
`ldx #0` that precedes `beid` — the block falls through to `besorted`, which *is*
`buildedges`' `rts`, and the index init makes it idempotent, so `--samples` is
honest here. It is 3.0–3.4% of a shape and 70% of `buildedges`, which is itself
4.3%; an insertion sort on 16 near-sorted keys might halve it, i.e. 1.5% of a
shape.

**What the apportionment says that no candidate captures.** 19% + 14% + 4.6% =
**38% of a worst-case shape sits inside `spanfill`'s per-cell and per-call
overheads**, and the three mechanisms for reaching it are respectively too big
for the byte budget (6), unsound for the concave types (2) and half-realisable
(4). If a later iteration ever *needs* the cycles, the honest starting point is
not any of the three as stated — it is that a shape writes 3,161 cells and pays
52 cycles for each, of which 34 are the fill itself and 18 are a bookkeeping
scan a correct interval-plus-fallback could mostly remove.

**One instrument note, because it cost this pass a false alarm.** `c64 mem read`
of `$D800-$DBFF` returns `(phi1 & $F0) | storage` — colour RAM is four bits
wide and the high nybble is open bus, uniform across the dump but varying with
where the machine stopped. A raw comparison of two dumps of the *same* build can
therefore differ in all 1000 bytes. **Only a masked comparison is a valid
instrument there**, which is why `test.yaml`'s one colour-RAM assertion masks
with `$0f`.

### Re-verify

**The whole proof protocol was re-run against the new arrangement**, not
patched. Eleven of the thirteen PNGs changed; `blank.png` and
`first-shape.png` came back **byte-identical**, because the first note onset
still draws the same shape from the same untouched RNG state —
`lstype=3 lssize=79 lsx=56 lsy=135 lsangle=226 lspat=3 lsink=3`, `lit=3913`,
which is the first ladder rung iteration 2 recorded. Every later rung moved:
the new curve climbs harder early (24,946 against 20,853 at the end of the
hymn, which is where the hymn's 33 shapes — the largest in the piece — land)
and finishes slightly lower (29,947 against 29,980). **The count never falls**, so A6's persistence proof
is untouched by the re-take. `sec4.png` and `final.png` are still byte-identical
to each other (`348b8296…`, 8,620 bytes each) — the hold paints nothing.

The rebuild is byte-identical to the committed binaries (`1812.prg`
`cd80da09…`, `1812.d64` `d6d7e589…`), so the evidence PNGs were the only stale
artifact this iteration had to retake.

`c64 test run demos/1812/test.yaml --json`: **170 steps, all `ok`, exit 0**,
40.87 s. The margin below `$2000` is **120** bytes
(`__BSS_LOAD__ $1F2E` + `__BSS_SIZE__ $5A` out of `1812.lbl`).

**One instrument note, and it invalidates three of the thirteen PNGs as
evidence.** `rot-a/b/c.png` changed on this run, and the geometry did not move:
re-staging section 9 three times from scratch gives a byte-identical bitmap
every pass (`lit=6105 checksum=1c454f03`, vertices `y=44 44 155 155`) and three
*different* PNGs, whose every differing pixel sits in one horizontal band at
the shape's lower edge. `evidence.sh` screenshots straight after
`call drawshape` with no `until` in between, so the frame is caught wherever
the beam was — which is the race the script's own header warns about, in the
one place it does not honour it. **A5 is unaffected** (it rests on the vertex
sets and on three bitmaps differing, not on three file hashes), but any claim
that `evidence/` is byte-reproducible is false for those three files until a
`c64 until` goes between the call and the capture. In the friction log.

---

## Closing state

- 170-step regression test passes; the demo runs the full 2:50 with
  **746 shapes**, `dropped = 0`, all ten shape types and all eight dither
  patterns used.
- **The arrangement has been heard by the machine and not yet by a human.**
  Five captures under `evidence/audio/`, five PASS reports, and `SPEC.md` §12
  A15 now states both halves of that criterion. The maintainer's listen is the
  one acceptance criterion this demo has never satisfied, and it is the open
  item at the close of iteration 3.
- The one ceiling worth watching: the program ends just below `$2000`, and the
  `$C400` block has its own size assertion. Both are **linker assertions**, so
  growing past either is a build error rather than a demo that quietly paints
  over its own canvas. The margin was **252** bytes at the close of iteration
  2 and is **120** after iteration 3 (see *Improve*, above). It
  has moved three times in one iteration, so read it out of `1812.lbl` rather
  than out of this line.
- Deliberately not optimised further: the per-scanline active-edge machinery
  is now comparable in cost to the fill itself for small shapes. With
  `dropped = 0` and a measured margin it is not worth the risk; the next
  person to want bigger or faster shapes should start there.
