# Fugue in C minor — audit

Four iterations. Each is evaluate → review → improve → re-verify, and every
PASS below was read off a running machine, never off the source.

Anchoring for everything here: `c64 break add tick` **before** `c64 run`, then
the first `wait --break` parks on frame 0, and `until tick --count N` is frame
N. Run-then-`until` does not work — measured on iteration 1, `c64 run` followed
by `c64 until tick --count 30` landed on frame **3,774**, because the machine
free-runs at warp in the gap between the two commands.

---

## Iteration 1 — the first build that scrolled

**Evaluate.** The picture came up on the first assembly: staves on rows 6-10
and 12-16, bar lines spanning both, heads and accidentals in the right cells,
the scroll running. Three criteria failed.

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | staves drawn before the music starts | **FAIL** | at `until tick --count 30` the score had advanced 7 columns and both clefs were off the left edge |
| 12 | `tickend` inside the badline deadline | **FAIL** | `shiftline` 236, `tickend` 252, against 195 |
| 11 | `tick` inside a frame | **FAIL** | `c64 profile tick --samples 32` → max **18,155**, more than the 17,095-cycle frame |
| 14 | glow behind the head | **FAIL** | `evidence/` PNG: every glow sat ~8 rasters above its note |

**Review.** The budget failure was not a tuning problem, and finding that out
was the iteration's real work. `c64 profile` broke it down: `shiftband` 13,368
cycles, `drawcol` 2,776, `glowtick` 613, `muswrite` 309, `musfetch` 59. At 15
rows a memmove needs at least `600 × 18 = 10,800` cycles of instructions
alone — `lda abs,x` + `sta abs,x`, twice per cell — so **no** amount of tuning
could fit the 215-raster window that arming in the top border leaves. That is
a proof, and it ruled out the whole class of fix the spec had planned for.

Optimising `drawcol` first was wasted effort worth recording: fetching and
decoding each note once instead of nine times took it from 2,776 to 2,697
cycles, because the cost was spread evenly across the background fill, the
blit and the decode rather than concentrated anywhere. Profiling the parts
(`dcbg` 643, `dcblit` 892, `dcscore` 1,182, `dcclef` 24) is what showed that,
and it should have come before the edit, not after.

**Improve.**

1. **Arm the raster IRQ at 204 instead of 251.** Once the VIC has latched a
   text row's matrix and colour on its badline, later writes to that row
   cannot affect the current frame — so the shift may start the moment the
   *last* band row has latched (`51 + 8×19 = 203`) and prepare the next frame
   across the bottom and top borders together: 263 raster lines instead of
   215.
2. **Move `drawcol` to the frame after the shift.** Screen column 39 is never
   visible in 38-column mode — the mode hides X 335-343, and column 39 spans
   336-343 at `xsc` 0 through 342-349 at `xsc` 6 — so it has a whole
   four-frame cycle of slack and no raster deadline at all.
3. **Chunk the move at page boundaries** (`$04C8`/`$0500`/`$0600`/`$0700`):
   22.3 → 21.4 cycles a cell.
4. **A static `HOLD` of 150 frames** before the scroll starts, so the clefs
   are on screen to be read and photographed. `sf = frame - HOLD` became the
   scroll clock; subtracting a constant leaves the one-clock property intact.
5. **`GLOWY0 = 42 + 8 * LADTOP`**, derived instead of the hardcoded 74 that
   was correct only for the band's original position.

**Re-verify.** `shiftline` 177, `tickend` 178 against 203 — 25 lines in hand.
`c64 profile tick --samples 32` max 15,625, min 864. `frame` reads exactly 900
after `until tick --count 900`, so no interrupt is being missed. `spry` =
122/150/182 for `vpos` = 10/17/25, and `$D000-$D005` = `50 7a 50 96 50 b6`.

**Two build failures, both ca65 traps the skill names.** `ldy nmidi,y` is an
illegal addressing mode — there is no `LDY abs,Y` — and one `bne` outgrew
±127 bytes, fixed mechanically by piping the build into
`skills/6502-assembly/references/fix-branch-range.py`.

---

## Iteration 2 — the arrangement, and what audio evidence actually proves

**Evaluate.** With the real 31-bar arrangement in place the picture and the
regression test held: 99 steps PASS. The audio was a different matter.

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 8 | all four captures PASS | **FAIL** | entry2: 156 score differences |
| 7 | three entries audible in the roll | **FAIL** | the roll's window opened at bar 8 for a bass entry at bar 7 |
| 21 | filter sweep visible | **FAIL** | `cutoff` 112 → 26 and never returned |

**Review.** Three separate faults, and only one of them was in the program.

- **entry1 passed and entry2 failed for a reason worth keeping.** entry1's
  window opens in silence, and leading silence is exempt from the diff, so the
  window self-aligns and any lead-in error is absorbed. entry2's opens
  mid-phrase, where being a few frames out shifts every event against the
  score. A window that opens in silence is a much weaker test than it looks.
- **The park frame was being read while the machine ran.** A capture leaves
  the machine RUNNING, and at warp the gap before the next command is emulated
  seconds — so `frame` read after a capture is not where the next capture will
  start. Window 2 opened **215 frames** from where the script thought, ten
  sixteenths of music.
- **`PEDAL` is 0-based and `bar` counts from 1.** The filter would have swept
  a bar early and a bar short.
- **The sweep rate was wrong for the length of the pedal.** 96 steps at one
  every four frames is 384 frames, exactly the three-bar pedal, so it bottomed
  out as the last chord died and never came back.

**Improve.**

1. **A fresh run per capture window**, so the machine is stopped at an exact
   frame when the capture arms.
2. **Measure the window start instead of trusting it.** `lead_in_frames` is
   accurate to about a frame; a mid-phrase window needs better. The program
   sweeps voice 1's pulse width on a 256-frame triangle, and the log samples
   `$D402`/`$D403` every frame — so the log carries its own clock. Matching
   the first sample against the modelled sweep pins the true start. It uses no
   pitch information, so it cannot launder a wrong note into a passing score:
   it fixes *where* the window is, and the diff still decides *what* is in it.
3. **A 200-frame pre-roll** on each window, so the ~155 frames of arming do
   not push the window past the entry it is named for.
4. `pedal0`/`pedal1` converted to the program's 1-based bar numbering.
5. The sweep stepped every two frames instead of four.

**Re-verify.** All four windows PASS with `--strict`. Alignment corrections
came down to 4-6 frames once the machine was stopped at the park point (191,
476, 956, 3756 against estimates 186, 470, 950, 3750). `cutoff` measured
across the pedal: 112, 97, 72, 47, 22, 34, 59, 84 — down and back.

---

## Iteration 3 — reading the evidence rather than the verdict

**Evaluate.** Every criterion PASS. Two were only PASS because the previous
iteration had gone back and looked at the artifact rather than the exit code.

**Review as a viewer and a listener.**

- **The piano rolls read as three independent lines.** All three colours
  present in every window, the soprano above the alto above the bass, none
  dropping out. The countersubject's octave descent is visible as a staircase
  in whichever voice has just answered — the same gesture, four times, which
  is what it is in the score.
- **The spectrogram showed the filter sweep only weakly**, and the reason was
  a design one rather than a bug: only voice 3 is routed through the filter,
  and voice 3 is a triangle, which has almost no high harmonic content for a
  low-pass to remove. The prompt calls the pedal "the moment to spend it on",
  so through bars 29-31 `$D417` opens to `$A7` and all three voices go through
  the filter. The sweep is now unmistakable in `evidence/audio/pedal/`:
  the upper partials close down through the middle of the window and reopen.
  Ordinary routing (`$A4`, voice 3 only) is restored outside the pedal.
- **The score on screen reads as music.** Heads are 4 px in a 4 px space,
  which is the engraved proportion; accidentals are legible at 1× at six
  pixels tall; the bar lines join the staves as they do in keyboard music.
  The density is honest: with no key signature, roughly a third of heads carry
  a flat, which is cluttered and is the price of a scrolling score that cannot
  keep a key signature on screen.

**The cross-check.** `tools/crosscheck.py` takes what the sequencer says is
sounding and goes and looks at the cell the renderer drew for it, checking
four things per voice: that a head glyph is there at all, that its half bit
matches `vpos & 1`, that the cell's colour is `pcolor[vnote % 12]`, and that
`vnote` equals `posmidi[vpos]` adjusted by `vacc`. A disagreement localises
itself — the first two are renderer faults, the third a colour-table fault,
the fourth a decoder fault.

Sampled at five attack frames across the whole piece:

```
=== machine frame 262, bar 1 slot 3 ===
  voice 2: B4   midi  71  p= 9 -> row 9 half 1 col 10  glyph  39 colour 13
=== machine frame 1398, bar 10 slot 1 ===
  voice 1: F5   midi  77  p= 5 -> row 7 half 1 col  8  glyph  39 colour  4
  voice 2: Ab4  midi  68  p=10 -> row 10 half 0 col  8  glyph  40 colour  8
  voice 3: Bb3  midi  58  p=16 -> row 13 half 0 col 10  glyph  38 colour 10
=== machine frame 2038, bar 15 slot 1 ===
  voice 1: C6   midi  84  p= 1 -> row 5 half 1 col  8  glyph  39 colour  2
  voice 2: G3   midi  55  p=18 -> row 14 half 0 col  8  glyph  38 colour  3
  voice 3: Eb3  midi  51  p=20 -> row 15 half 0 col  8  glyph  38 colour  7
=== machine frame 3110, bar 23 slot 7 ===
  voice 1: F4   midi  65  p=12 -> row 11 half 0 col  8  glyph  38 colour  4
  voice 2: D4   midi  62  p=14 -> row 12 half 0 col  8  glyph  34 colour  5
  voice 3: F2   midi  41  p=26 -> row 18 half 0 col 10  glyph  34 colour  4
=== machine frame 4126, bar 31 slot 6 ===
  voice 1: G4   midi  67  p=11 -> row 10 half 1 col 10  glyph  39 colour  3
  voice 3: sounding but held (age 240), head has scrolled past the now column

OK: every sounding note is drawn at the position, in the half, and in the
colour its own pitch demands
```

The one voice it declines to check is the honest part. The closing tonic pedal
is held from bar 29 to the end, and a held note's head travels on at two
pixels a frame like everything else — by bar 31 it is at column 0 and its glow
has been off for 200 frames. There is nothing at the now column to compare
against, so the check says so instead of passing it silently.

**Improve.** The filter routing above; the cross-check scoped to heads still
on the now column.

**Re-verify.** All four captures PASS. `c64 test run demos/fugue/test.yaml`:
**128 steps, PASS.** The cross-check: OK at all five frames.

---

## Iteration 4 — the two shots that were blank

**Evaluate.** Every criterion still PASS, and two committed evidence PNGs were
**an empty staff**: `accidental.png` and `fine.png`. Nothing in the pipeline
had complained. The evidence script exited 0, the test passed 128 steps, and
all four captures passed.

**Review.** Two unrelated faults, both of the same shape — something that
reports success without having looked.

- **The shot list was not sorted.** `genscore.py --shots` emitted the three
  entries, then the pedal at frame 3822, then `crossing` at 1046 and
  `accidental` at 1470. The script walks forward only — `until` cannot
  rewind — and its `goto` skips travel when the delta is negative, so both
  late shots were captured wherever the pedal shot had left the machine.
- **The scroll halted eight sixteenths too late.** The spec said it stops
  "when the final chord's head reaches the now column"; the code stopped when
  the *sequencer* ran out. The closing C major chord attacks at bar 31 slot 8
  (sixteenth 488) and is held to the end, so between its attack at frame 4142
  and the sequencer finishing at 4206 the score scrolled 16 more columns and
  carried the whole chord off the left edge. Read off the machine at frame
  4300: `shifts` 1013, and every one of the 40 columns in all eleven staff
  rows held nothing but background.

**Improve.**

1. `genscore.py --shots` sorts by frame.
2. `genmusic.py` emits `stopshift` = `22 + 2 * last_attack` = **998**, and
   `tick` halts the shift and the render there instead of on `state`.
3. `glowtick` freezes `sprage` while the scroll is halted. The age is what
   drives the glow's x, so freezing it keeps the glow on the head that has
   also stopped moving — otherwise the final chord would age out of its own
   backlight while standing still. The chord attacks on the very frame the
   scroll halts, so its age is 0 and its glow sits exactly on the now column.
4. `fine` is shot in the gap between the halt (frame 4143) and the release
   (4206), where the picture is stopped and the chord is still sounding.

**Re-verify.** At frame 4300: `shifts` 998 = `stopshift`, `scrollon` 0,
`state` 3, and the closing chord on screen at column 10 — glyph 41 at row 11
(hollow lower head: **E4**, the Picardy third) and glyph 40 at row 14 (hollow
upper head: **G3**). `evidence/fine.png` shows both, backlit, with the scroll
stopped. `evidence/accidental.png` now shows flats beside the heads they
modify across both staves. 128 test steps still PASS.

**One thing this iteration did not fix, on purpose.** The tonic pedal C3 is
attacked at bar 29 and tied to the end, so at the close its head is 54 columns
to the left and off screen: the final sonority reads on the staff as G3 and E4
with the bass implied. That is what a tied note looks like in notation — the
head is at the attack, not at the release — and moving it would be drawing a
note Bach did not write. The glow going out at the release is the same
honesty: the backlight tracks *sounding*, and once the gate is released
nothing is.

## Criteria, final

| # | Criterion | Evidence |
|---|---|---|
| 1 | staves, clefs, bar line before the music | `evidence/staves.png`; codes 33 across rows 7-11 and 13-17, 64-73 and 74-79 in columns 1-2 |
| 2 | mode registers | `$D011` `$1B`, `$D018` `$19`, `$D01B` `$07`, `$D016` bit 3 clear, border/background 0 |
| 3 | `xsc` walks 6,4,2,0; `shifts` +1 once per four | test steps, one frame at a time |
| 4 | `state` 0/1/2 at frames 0/150/238 | test |
| 5 | `sixteenth = (frame - 238) / 8` | test at frames 238, 400, 510, 1022 |
| 6 | the three entries, one voice at a time | frame 254 alto alone (`v2idx` 1, C5); 510 soprano (G5); 1022 bass (C4) |
| 7 | three lines in the roll, none missing | `evidence/audio/*/piano-roll.png` |
| 8 | four reports PASS, none `nothing_played` | `--strict` on both capture and report |
| 9 | WAVs non-empty, no clipping | `duration_s` 12.27 s, `clipped_samples` 0 |
| 10 | SID shadow holds waveform + gate | test |
| 11 | `tick` inside a frame | max 15,625 of 17,095 |
| 12 | `tickend` before the last row's badline | 178 of 203 |
| 13 | no dropped frames | `frame` = 900 after 900 ticks; = 4,422 after 4,422 |
| 14 | glow behind the head | `evidence/backlight.png` |
| 15 | sprite registers match published bytes | test, `unchanged` against a sample |
| 16 | `collide` = the predicted count | **3**, and `genmusic.py` predicts 3 (bars 20, 27, 29) |
| 17 | `rendk - sixteenth` = 15 | test at frame 400 |
| 18 | accidental beside its head | `evidence/accidental.png` |
| 19 | two voices crossing, both legible | `evidence/crossing.png` |
| 20 | PWM visible | `evidence/audio/entry1/spectrogram.png`; `pwmval` sampled moving |
| 21 | filter sweep | `evidence/audio/pedal/spectrogram.png`; `cutoff` 112→22→84 |
| 22 | it ends | scroll halts at `shifts` = `stopshift` = 998 (frame 4,143), chord rings at the now column, `state` 3 at 4,206; `shifts` unchanged over 120 more frames |
| 23 | `test.yaml` | 128 steps PASS |
| 24 | packaged, `-ntsc` pinned | see README |
| 25 | roll and screen agree | `tools/crosscheck.py`, five frames |

## What is still open

- **Two bars of the transcription are marked `# UNSURE:`** in
  `tools/bwv847.py` — bar 18's last eighth (the voice assignment of a low G3
  against an eighth rest) and bar 29 slots 0-9 (the two upper parts run in the
  same low octave and meet on a unison C4). Both are documented at the bar
  with the reasoning; neither affects the subject or any entry.
- **The maintainer's listen is the final gate.** Everything above is
  mechanical: registers, transcription diffs, cell contents. Whether it sounds
  like the C minor fugue is not a thing this audit can settle.
