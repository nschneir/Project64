# Amiga Ball — fidelity audit

`PLAN.md` Task 10 asks for numbered iterations, each one evaluate → review →
improve → re-verify, scoring the build against every one of `SPEC.md` §14's 28
acceptance criteria. Every verdict below is read off the running machine — the
command and its output — and never off a reading of the source. Where a
criterion could not be settled it says so and says why; where the *criterion*
is wrong rather than the build, that is recorded as a SPEC.md defect with the
wording it should have had, and nothing is quietly relaxed to make a row green.

**How everything below was run.** One session, `ballaudit`, `--warp
--headless`, every command under `caffeinate -dimsu` (a headless VICE
idle-throttles on a Mac nobody is touching and presents as a *wedged*
emulator). Every observation is anchored on `c64 until tick` — `tick` is the
frame anchor and `mainloop` is not — and inspection never advances the machine.
The build line is the three areas, every time:

```sh
.venv/bin/c64 run demos/amiga_ball/amiga_ball.s -s ballaudit \
    --area 'CHARS=$2000:$0800' --area 'SPRITES=$2800:$1800' \
    --area 'VARS=$4000:$0100'
```

---

## Iteration 1 — the frame nobody had ever anchored on

### Evaluate

Twenty-four of the twenty-eight criteria passed on the first pass. Four failed,
all four at the same place and for the same reason, and it was a place no
earlier task had ever looked: **the first `tick` anchor after `run`**.

`c64 until tick` stops at tick **entry**. At `--count 1` that is the frame on
which `ball_init` has run and `ball_step` has *not*, and `ball_init` set the
physical state without ever deriving anything from it:

```
$ c64 run … && c64 until tick --count 1 -s ballaudit
$ c64 mem read $4000 32 -s ballaudit
4000: 00 28 00 00 c0 01 00 00 20 00 01 00 00 00 00 00
4010: 00 00 00 00 00 00 be 18 00 00 00 00 …
$ c64 mem read $07F8 8 -s ballaudit
07f8: 00 00 ff ff ff ff 00 00
$ c64 mem read $D000 17 -s ballaudit
d000: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
d010: 00
```

`ball_xi` = `$28` = 40 with `ball_x16` = 0 (criterion 10 wants 24 + 40 = 64).
`sptr` = 0 and `$07F8-$07FB` = `00 00 ff ff` where criterion 6 wants 160-163 —
the VIC was pointed at **block 255**, uninitialised RAM, for that frame.
`$D005` = 0 where criterion 7 wants `ball_yi + 42`. `$D002` = 0 where criterion
8 wants `ball_x16 + 48`.

Nothing was visible: `$D015` was already `$3F` but every sprite Y was 0, which
is above the display window, so six sprites pointed at garbage were drawn
nowhere. That is exactly why it survived nine tasks and a 156-step regression —
`test.yaml`'s first step was `until: { ref: tick, count: 30 }`, so the spec's
own regression started 29 frames after the only frame that could break it.

Criteria 6, 7, 8 and 10 are each written **"at every anchored frame"**. That
frame is an anchored frame. Four FAILs.

### Review

**The IRQ handler's cost.** `c64 profile tick --samples 200` from a clean run,
three times, byte-identical each time:

```
$087a (tick): 477.7 cycles mean over 200 arrivals (min 388, max 971;
              entry to rts, IRQs masked)
```

and priced frame by frame with the state staged, which is what says *where* the
cycles are:

| Frame | Cycles |
|---|---:|
| idle — no sound window open | 388 |
| sweep frame — one `$D416` write | 456 |
| floor impact — the gate-on frame, 30 register writes | 782 |
| wall impact — reversal, `spin_dir`, counters **and** gate-on | 842 |

Against `SPEC.md` §11's ceiling of 2,600 cycles that is 18% of budget at the
mean and 37% at the sampler's worst arrival. The program's own high-water mark
agrees:
`irq_hwm` = **14** raster lines after 600 ticks, i.e. 910 cycles including the
handler wrapper, against a declared ceiling of 40 and an operational form of
`10 + irq_hwm < 51` that reads 24 < 51 — the tick finishes 27 lines before the
display window opens, so there is no tearing to look for.

§11's estimate table adds up to "~840, worst frame". The most expensive frame
this audit could *stage* is the wall impact at **842** — the estimate is good
to two cycles for the frame it describes. The sampler's max of **971** is 129
cycles above that and no staged frame reproduces it; it is deterministic across
runs, it is 15 raster lines, and it is 37% of the ceiling, so it is recorded
rather than chased. Where §11 is genuinely under is its sound row, ~300 against
a measured 782 − 388 = **394** for the gate-on arm.

The handler itself is clean and was checked against its contract on the
machine, not read: `$D019` is acked on entry (`lda #$01 / sta $D019`) before
anything else, `cld` runs because an interrupt does not clear D on the NMOS
6502, the cost subtract cannot straddle the 263 wrap because it starts at line
10 and costs 14, and the exit is `pla/tay/pla/tax/pla/rti` — nothing from ROM.
`$0314` is taken after the KERNAL's `$FF48` has pushed A/X/Y, so the three
pulls are the exact complement.

**The generators' math.** All five re-run byte-identical
(`python3 tools/generate.py && git status --short` clean), and the arithmetic
checks out against the machine:

| Claim | Checked how |
|---|---|
| wall verticals 32 px apart at columns 0,4,…,36 | pixel scan of a sprite-free capture: purple columns at screen x 0, 32, 64, 96, 128, 160, 192, 224, 256, 288 — ten, exactly |
| wall horizontals 24 px apart | purple rows at raster 51, 75, 99, 123, 147 |
| depth lines `y(d) = 171 + 79/d` | blue full-width rows at raster 171, 179, 181, 184, 187, 191, 197, 210, 250 — the generator's `[250, 210, 197, 191, 187, 184, 181, 179]` plus the horizon |
| five convergent lines, 80 px apart at the bottom | raster 249 carries blue only at screen x 1-2, 81, 160, 239, 318-319 |
| display window is rasters 51-250 | purple occupies PNG rows 31-150 and blue 151-230 in a 263-row canvas, i.e. 200 rows: PNG row = raster − 20 |
| sphere is 36 texel rows × 24 texels | `gen_sprites.py` now asserts it (below), and the machine measures the checker bbox at 88 × 68 px in seven separate captures |
| bounce table exact in 8.8 | `y(p)·256 = 40448 − 26·p·(64−p)`, integer for every p; symmetry assert is an equality |

Three problems came out of reading them against the machine rather than against
each other:

1. **`gen_sprites.py` printed the one number criterion 28 rests on instead of
   asserting it**, with the comment *"print it rather than assert a number the
   geometry might drift from"*. Drift in exactly that number is what makes
   criterion 28 fail — on the machine, days later, with nothing in the git diff
   to point at. Fixed (see Improve), and negative-tested.

2. **Two generator comments made checkable claims about `SPEC.md` that are no
   longer true.** `gen_bounce.py` says Section 6.1 "prints y(16) = 79.0 and
   y(24) = 57.5"; §6.1 now prints 80.0 and 60.5 and records the correction in
   its own parenthesis. `gen_sprites.py` says "SPEC.md Section 5.2 writes these
   as (11.5, 20.5)"; §5.2 now specifies (12.0, 21.0). Both claims propagate
   into the generated `.inc` headers. A comment carries the same evidence
   burden as a finding, and these two had gone stale under the spec they cite.

3. **`gen_sound.py`'s rationale for its 8 unused table entries is wrong.** It
   says entries 16-23 exist "so a table read outside the sweep window is still
   a defined byte" — but `sound.s` branches past the sweep with
   `cmp #16 / bcs stepgate` *before* it indexes, so no such read can occur. The
   entries are fine; the reason given for them is not.

**Dead code and slack.** One find: `tmp`, 8 bytes at `$4037`, is declared by
§9 and referenced by nothing — grepped across `*.s`, `*.inc` and `test.yaml`,
zero hits outside `vars.s`. It is real slack, not a bug (the whole per-frame
job runs out of A/X/Y), and it stays because §9 fixes every address after
`$4000` by arrangement; it is now annotated as unused rather than left to look
like an oversight. The other declared slack is intact and correct: 1,536 bytes
(24 blocks) unspent in `SPRITES`, and 16 unread bytes in the two sweep tables.
There is no dead code in `*.s` — every label is reached and every SID write
still goes through the single `sidput` (`grep -n 'sta *\$D4' *.s` returns three lines, two of
which are the comments that say so, and one instruction: `sidput`).

**One thing the review cleared rather than found.** `ball_step` handles the
wall reversal *before* it advances `bounce_phase`, so a frame carrying both a
wall hit and a floor hit would have the floor's `sound_impact` overwrite the
wall's and the wall boing would be swallowed. It cannot happen in the shipped
run: from the §12 initial state the floor impacts land on frames 32 + 64k and
the wall impacts on 105 + 128k, and 128k − 64m = −73 has no solution because
the left side is even. Left alone, deliberately.

### The viewer's judgement

Read off `room.png`, `apex.png`, `contact.png`, `rot00/05/10.png`,
`wall-left/right.png`, `shadow-1/2/3.png` and the four `ball-*.png`.

#### Does it actually look like the Boing Ball?

**Yes, and from across the room it is unmistakable.** What is right:

- **The room is the room.** A purple wire grid on black above a light-blue
  floor grid running to a vanishing point — and the floor is a genuine
  projection, not a wall lying down. In `room.png` the depth lines visibly pile
  up toward the horizon and spread toward the viewer, four bottom rows carry
  none, and three land inside a single character row. That is what perspective
  looks like and it is the single strongest "this is the Amiga demo" cue in the
  picture.
- **The horizon is a colour change, not a line.** The wall's purple meets the
  floor's light blue at row 15 and the two planes separate without the ball
  ever having to cross an ambiguous edge — visible in `shadow-2.png`, where the
  ball straddles the horizon and still reads as being in front of the wall and
  above the floor.
- **The texture is the Boing Ball's texture.** Sixteen longitude segments by
  eight latitude bands, red and white, and it is genuinely mapped: in
  `contact.png` the checker columns compress toward the left and right limb and
  the rows compress toward the poles, so the checkers curve around the sphere
  instead of sitting on it. This is the thing that would have been easiest to
  fake and it is not faked.
- **It rotates, and you can see it rotate.** `rot00.png`, `rot05.png` and
  `rot10.png` are 14.06° apart and each one moves the checker boundaries a
  clear third of a cell across the face while the limb pattern changes with
  them. It reads as a turning ball, not as a flickering pattern.
- **The shadow is what sells the bounce.** In `apex.png` it is a small dark
  smudge far below a ball high on the wall; in `contact.png` it is a wide
  ellipse tucked under a ball sitting on the floor; in `shadow-2.png` it is
  mid-sized and the floor's grid lines run **over** it. That last detail is the
  whole trick — it puts the patch on the floor plane instead of floating above
  it, and it is why the ball reads as leaving the ground rather than sliding.
- **It is round.** Measured, not looked at: 96 × 72 raster pixels, 0.991 of a
  true circle at NTSC PAR (criterion 28).

What is not right:

- **The axis is not tilted.** The 1984 ball spins about an axis leaning roughly
  17° off vertical, and that lean is one of the two things people recognise it
  by. Here the poles sit dead top and dead bottom, so `rot05.png`'s upper cap
  is symmetric where the original's is off-centre and swings as the ball turns.
  §5.2 chose a vertical axis explicitly and the choice is defensible at 24 × 36
  texels — but §1's table of deliberate deviations lists three deviations and
  this is a fourth, unlisted. It is the largest remaining gap to the original.
- **It is not shaded.** §3.3 owns this: multicolour sprites carry three colours
  and the third went to the rim. The ball reads as a flat checkered disc lit
  head-on, which is what the Amiga's also looks like in the frames where the
  light is behind the camera, and unlike it everywhere else.
- **The rim does not do what §3.3 says it does.** `$D025` is black and `$D021`
  is black, so against the background the rim is *indistinguishable from
  transparency* — it buys no silhouette there, it just removes a texel. Where
  it does earn its place is over the grid: it guarantees that no purple or blue
  grid pixel ever touches a checker, which gives the ball a one-texel dark halo
  that pushes it in front of the wall. Visible in `room.png`, where the grid
  lines stop cleanly short of the checkers. The third colour is well spent; the
  reason §3.3 gives for spending it is the wrong one.
- **The ball never deforms.** It arrives at 6.5 px/frame and stops dead. §5.3
  names a wall-impact squash as deliberately unspent slack, and that is the
  right call for the brief, but the absence is visible at contact.
- **The red is a brick red.** `$02` measures (174, 71, 93) against the Amiga's
  saturated red. Nothing to be done — the C64 has one red.

#### Does the impact actually sound like a ball hitting something?

**It sounds like a struck body, and it is convincingly two different bodies.
It does not quite sound like the Amiga's rubber ball**, and the measurements
say exactly where the gap is.

What is in `evidence/audio/floor/` and `wall/`, measured off `capture.wav`
(2048-point Hann STFT at 48 kHz, 10 ms hop, with the first 60 ms dropped — see
the toolchain note below):

| | floor | wall |
|---|---|---|
| onset level | −25.4 dBFS | −23.7 dBFS |
| spectral centroid at onset | 4,204 Hz | 4,484 Hz |
| centroid at +50 ms | 2,129 Hz | 3,466 Hz |
| centroid at +100 ms | **1,128 Hz** | **1,881 Hz** |
| level at +100 ms | −36.3 dBFS | −40.5 dBFS |
| transcribed voice 1 | A2, +0.5 cents, 20 frames from 13 | E3, +0.2 cents, 20 frames from 13 |
| report's silence window opens at | 0.70 s | 0.60 s |

The **spectrogram** shows the gesture the piano roll cannot. Both are black for
the first fifth of the frame, then a single bright vertical column spanning the
full height from DC to Nyquist — the noise transient, arriving in one frame —
and then a wedge that collapses downward: after the column, energy is confined
to the lower part of the frame and narrows further as it moves right, with a
banded texture from the triangle's harmonics riding under it. The wall's wedge
sits visibly higher and reaches further to the right than the floor's, which is
§8's "the wall stays brighter throughout" as a picture. The **piano roll**
shows a single 20-frame A2 (floor) / E3 (wall) on voice 1, the noise voice
alongside it, and voice 3 an empty lane for all 90 frames.

Put together, what you hear is: a bright crack about 2 ms long; under it a low
pitched thump, A2 for the floor and a fourth-and-a-bit above it for the wall;
and over the first tenth of a second the crack darkens fast — the centroid
drops by a factor of 3.7 — as a resonant low-pass closes over it. That is a
struck body: transient, pitched body, decay. The two impacts are unmistakably
different objects, and the floor is convincingly the heavier one.

**Where it falls short of a boing.** Two things, both measured:

1. **Two-thirds of the "oing" is inaudible.** §8's whole thesis is the
   descending resonant cutoff over the noise burst, swept over 16 frames
   (267 ms). But voice 2's decay is `$D40C` = `$04` = 114 ms, so the burst the
   filter is sweeping is 30 dB down by frame 7. The centroid confirms it: it
   falls cleanly for ~100 ms and then *rises* again from +110 ms onward, which
   is not the filter reopening — it is the signal having decayed into the noise
   floor and the measurement following the residue. Frames 7-15 of the sweep
   write `$D416` over a voice nobody can hear.
2. **The body has no pitch envelope.** The Amiga's sample has an audible glide
   — the rubbery "oi" — where voice 1 here holds one fixed frequency for its
   whole 20-frame gate. The entire "oing" is delegated to the filter, and per
   (1) most of that is spent.

Neither is a coding defect: both are `SPEC.md` §8's stated instrument,
implemented exactly. They are the reason iteration 2 is needed — see
"Is a second iteration needed?" below.

**A toolchain note that matters for reading these numbers.** Every
`c64 audio capture` WAV in this repository opens with a step to about
−9,600 LSB followed by a ~45 ms exponential decay to zero — the emulator's
audio output being switched on, not anything the program plays. Measured across
all seventeen committed captures in the four demos that have them (`1812` 10,617-14,480, `la-galaxia`
12,807-15,882, `ms-muncher` 15,192-15,660, `amiga_ball` 9,637), it is present
in every one and is *louder* than this demo's actual impact. Every measurement
above drops the first 60 ms for that reason. Nothing here is wrong; a reader who
does not know this will conclude the demo clicks.

### Improve

Seven changes, all inside `demos/amiga_ball/`.

| Where | What |
|---|---|
| `ball.s` `ball_init` | **The four FAILs.** Ends `jmp ballderive` instead of `rts`, so init derives `ball_x16`, `ball_yi`, `shadow_x16`, `shadow_size` and writes all six sprite X/Y registers, `$D010` and all six pointers before it returns. `ballderive` ends in the `rts` init needs, so the `jmp` *is* the return — no extra byte of code and no extra cycle in any frame. |
| `test.yaml` | Ten new assertions at `until tick --count 1`, ahead of the existing `count: 30` warm-up (now 29, so the total frame count is unchanged). They pin §12's initial state at the exact anchor that was broken: `ball_x16` 64, `ball_yi` 54, `$D000-$D007`, `$D010` 0, `$07F8-$07FD` = 160-163 + 230-231, `sptr`, `shadow_x16`, `shadow_size` 3. |
| `tools/gen_sprites.py` | The sphere's extent is now **asserted**, per frame, not printed: rows 3-38 exactly, widest row 24 texels, and the checker bbox 22 × 34 texels — which is criterion 28's 88 × 68 px at 4 × 2 px per texel. |
| `tools/gen_sprites.py` | The `(11.5, 20.5)` note rewritten as history; §5.2 now specifies `(12.0, 21.0)` itself. |
| `tools/gen_bounce.py` | The `y(16) = 79.0` note rewritten as history; §6.1 now prints 80.0 and 60.5 itself. |
| `tools/gen_sound.py` | The 16 held table entries are documented for the reason they actually have — keeping the table's index domain equal to `snd_timer`'s — with the fact that `sound.s` makes them unreachable stated outright. |
| `ball.s`, `tools/gen_shadow.py` | The **off-by-one raster arithmetic**, below. |
| `vars.s` | `tmp` annotated as unused, with why nothing has ever needed it. |

**The off-by-one, because it is a finding and not a typo.** `SPEC.md` §6.1 says
the sphere's bottom raster at contact is `sprite_y + 77` = 235, and §7 says the
shadow's ellipse centre is raster 235. Measured, both are **236**, and they are
one fact, not two:

```
$ # a 21-row hires sprite, block 232, poked to Y = 100, everything else off
$ c64 mem write $D00D 100 -s ballaudit ; c64 mem write $D015 $40 -s ballaudit
$ c64 screen --png spry2.png --scale 1 --border -s ballaudit
      white PNG rows 81-101  →  raster 101-121
```

A sprite whose Y register is V has its first row on raster **V + 1**: the VIC
starts the sprite's DMA on the line where `$D012` equals Y and displays the
fetched data on the next one. The room in the same capture puts display row 0
at raster 51 (purple occupies PNG rows 31-150), which is what the raster axis
is calibrated against, so the +1 is the sprite's and not the canvas's.

Nothing on screen is wrong: the ball's bottom and the shadow's centre move
together and still coincide exactly at contact. What was wrong is every number
written down for it. `ball.s`'s `Y_FLOOR` and `SHADOW_Y` comments and
`gen_shadow.py`'s `CENTRE_ROW` comment now state 236 and the mechanism.
`SPEC.md` §6.1 and §7 are **not** edited — see the defect list.

### Re-verify

Everything below is from the fixed build.

**The frame that failed, at the same anchor:**

```
$ c64 run … && c64 until tick --count 1 -s ballaudit
$ c64 mem read $4000 32 -s ballaudit
4000: 00 28 40 00 c0 01 00 36 20 00 01 00 00 00 00 00
4010: 00 00 40 00 03 00 a0 a1 a2 a3 7b 18 00 00 00 00
$ c64 mem read $07F8 8 -s ballaudit
07f8: a0 a1 a2 a3 e6 e7 00 00
$ c64 mem read $D000 17 -s ballaudit
d000: 40 36 70 36 40 60 70 60 40 e1 70 e1 00 00 00 00
d010: 00
```

`ball_xi` 40 → `ball_x16` `$40` = 64 = 24 + 40 (10 ✓). `sptr` and `$07F8-$07FB`
both `a0 a1 a2 a3` = 160-163 for `rot_frame` 0, `$07FC/$07FD` = `e6 e7` =
230/231 for `shadow_size` 3 (6 ✓). `$D001` = `$D003` = `$36` = 54 = `ball_yi`,
`$D005` = `$D007` = `$60` = 96 = 54 + 42 (7 ✓). `$D000` = `$D004` = `$40`,
`$D002` = `$D006` = `$70` = 64 + 48 (8 ✓). `frame_count` is still 0: no physics
has run, which is the point.

**The generator assert bites** — a guard that cannot fail is not a guard:

```
$ python3 -c "…; m.CY = 20.5; m.main()"      # the draft's index centre
assert fired as intended: frame 0: sphere occupies rows 3-37 (35 rows),
    expected 3-38 = 36 (SPEC.md Section 3.2)
$ git status --short demos/amiga_ball/sprites.inc
                                              # empty: the failing run wrote nothing
```

**The gate, in full:**

```
$ python3 demos/amiga_ball/tools/generate.py && git status --short demos/amiga_ball/
--- 5 generators, all clean
    (bounce.inc and shadow.inc differ in comment text only —
     `git diff | grep -c '\.byte'` is 0 for both; sprites.inc, chars.inc,
     screen.inc and sound.inc are byte-identical)
$ .venv/bin/c64 test run demos/amiga_ball/test.yaml
PASS  amiga-ball  (c64, 24.86s)          # 167 steps, was 156
$ .venv/bin/c64 package … -o demos/amiga_ball/amiga_ball.d64 --title "AMIGA BALL"
packaged 'AMIGA BALL' -> demos/amiga_ball/amiga_ball.d64
run it with: x64sc -ntsc demos/amiga_ball/amiga_ball.d64
$ .venv/bin/python -m pytest tests/test_docs_demos.py -q -m "not vice"
21 passed in 1.61s
$ sh demos/amiga_ball/tools/evidence.sh
done -- 15 frames, 12 state files       # every PNG and .txt byte-identical to the
                                        # committed ones: the fix changed no pixel
$ sh demos/amiga_ball/tools/audio-evidence.sh
PASS: …/evidence/audio/floor/report.md
PASS: …/evidence/audio/wall/report.md
```

That the fifteen frames came back byte-identical is itself the re-verification
that the fix is invisible: it moves nothing the display was ever showing, it
only makes the frame before the first `ball_step` describe the same state as
the frame after it.

---

## The criteria

All twenty-eight, scored against the fixed build. Every row is a command run on
`ballaudit` at a `tick` anchor.

### Mode and memory

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | `$D011&$7F`=`$1B`, `$D016&$1F`=`$08`, `$D018`=`$19`, `$D020&$0F`=0, `$D021&$0F`=0 | **PASS** | `d011: 1b` · `d016: c8` (`&$1F`=`$08`) · `d018: 19` · `d020: f0 f0` (`&$0F`=0,0) |
| 2 | colour RAM row 0 col 0 = `$04`, row 20 col 0 = `$0E` | **PASS** | `d800: 04` · `db20: 0e` |
| 3 | `$0400-$07E7` non-zero, with a wall row and a floor row | **PASS** | row 0 `0400: 01 02 02 02 01 02 02 02`; row 20 `0720: … 2c 2d 00 00 00 00 2e 00` |

### Sprites

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 4 | `$D015`=`$3F`, `$D01C`=`$0F`, `$D017`=`$0F`, `$D01D`=`$3F`, `$D01B`=`$30` | **PASS** | `d015: 3f` · `d017: 0f` · `d01b: 30 0f 3f` (`$D01B/$D01C/$D01D`) |
| 5 | `$D025`=0, `$D026`=1, `$D027-$D02A`=2, `$D02B`=`$D02C`=`$0B`, masked | **PASS** | `d025: f0 f1 f2 f2 f2 f2 fb fb` → `0 1 2 2 2 2 b b` |
| 6 | `$07F8-$07FB` = 160+4·`rot_frame`+n = `sptr`; `$07FC/$07FD` = 224+2·`shadow_size`+n | **PASS** | at `rot_frame` 13 / `shadow_size` 0: `07f8: d4 d5 d6 d7 e0 e1` and `sptr` `d4 d5 d6 d7` (212-215 = 160+52; 224/225). Also at the **first** anchor: `a0 a1 a2 a3 e6 e7`, `sptr` `a0 a1 a2 a3` — the frame that failed in Evaluate |

### Geometry that must hold as the ball moves

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 7 | `$D001`=`$D003`=`ball_yi`; `$D005`=`$D007`=`ball_yi`+42 | **PASS** | `ball_yi`=`$8b`: `d000: 72 8b a2 8b 72 b5 a2 b5` — `$8b`,`$8b`,`$b5`,`$b5` = 139,139,181,181 |
| 8 | `$D000`=`$D004`=`ball_x16` lo; `$D002`=`$D006`=(`ball_x16`+48)&$FF | **PASS** | same read: `$72`,`$72` = 114 = `ball_x16`; `$a2`,`$a2` = 162 = 114+48 |
| 9 | `$D010` = `$00` below `ball_xi` 184, `$2A` at and above | **PASS** | staged with `freeze`: `ball_xi=183 -> D010=0`; `ball_xi=184 -> D010=42`; `ball_xi=223 -> D010=42` with `d000: f7 3c 27 3c f7 66 27 66 f7 e1 27 e1` |
| 10 | `ball_x16` = 24 + `ball_xi` at every anchored frame | **PASS** *(was FAIL)* | `ball_xi` 90 → `ball_x16` `$72` = 114; `ball_xi` 223 → 247; and at the first anchor 40 → 64, which is the frame that failed |

### Motion

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 11 | `ball_x16` differs 20 ticks apart | **PASS** | `t0: ball_x16=114 0` → `t20: ball_x16=149 0` (35 px = 20 × 1.75) |
| 12 | `ball_yi` reaches ≤ 60 and returns to 158 | **PASS** | polled every tick for 66 ticks: `ball_yi min=54 max=158` |
| 13 | `bounce_count` climbs over 200 ticks, `wall_count` over 300 | **PASS** | `bounce_count` 2 → 5 over 200; over the next 300, `bounce_count` 5 → 10 and `wall_count` 2 → 4 |
| 14 | `rot_frame` differs 20 ticks apart and is always ≤ 15 | **PASS** | 13 → 1 across 20 ticks; polled every tick for 64 ticks, `max rot_frame = 15` |
| 15 | `spin_dir` is `$01`/`$FF` either side of a wall hit; `last_impact` 2 or 3 | **PASS** | right wall: `spin_dir 1 → 255`, `last_impact 3`, `ball_vx $01C0 → $FE40`. left wall: `spin_dir 255 → 1`, `last_impact 2`, `ball_vx → $01C0`. Both produced by the program's own reversal, `freeze` released for exactly one tick |
| 16 | `shadow_x16` = `ball_x16` at three anchors; `shadow_size` takes ≥ 2 values | **PASS** | 247/247, 227/227, 194/194 at three separate anchors; `shadow_size` polled every tick for 64 ticks reads `33333333322222211111000000000111112222223333…` — all four values |

### Sound

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 17 | on a floor impact `sid+4`=`$11`, `sid+11`=`$81`, `sid+0/1`=`$0D`/`$07` | **PASS** | `401d: 0d 07 00 00 11 08 00 00 10 00 00 81 04 …` — staged by the program's own `bounce_phase` 63 → 0 wrap |
| 18 | +8 frames the cutoff is lower; +24 frames `sid+4`=`$10` | **PASS** | `sid+22` 220 (`$dc`) at impact → **119** at +8; at +24, `sid+4=16`, `sid+11=128` — both gates released |
| 19 | on a wall impact `sid+0/1`=`$90`/`$0A`, higher than the floor's | **PASS** | `401d: 90 0a 00 00 11 08 00 00 18 …` — 2704 vs the floor's 1805, and the noise clock `$18` vs `$10` |
| 20 | `sid+14`…`sid+20` (voice 3) are 0 at every anchored frame | **PASS** | `402b: 00 00 00 00 00 00 00` at the impact frame, at +8, at +24, and in the steady-state read |
| 21 | both audio reports read `verdict: PASS` against a generated score | **PASS** | `audio-evidence.sh` re-run against this build: `PASS: …/floor/report.md`, `PASS: …/wall/report.md`, `--ref` + `--strict`, score written from the impact schedule *before* the capture. Voice 1 transcribes A2 +0.5 ¢ / E3 +0.2 ¢, 20 frames from frame 13; voice 3 an empty lane |
| 22 | the spectrogram shows a broadband transient whose centroid falls over ~250 ms | **PASS on substance, criterion defective** | Transient: a full-height column in both spectrograms at the impact frame. Fall: centroid **4,204 → 1,128 Hz** (floor) and **4,484 → 1,881 Hz** (wall) over the first 100 ms. It does **not** fall over 250 ms — from +110 ms the signal is >30 dB down and the centroid rises with the noise floor. Corrected wording proposed below; the build is doing what §8 designed, the criterion asks for a duration §8's own `$D40C` = `$04` cannot deliver |

### Budget

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 23 | `irq_hwm` ≤ 40 after 600 ticks and `10 + irq_hwm < 51` | **PASS** | `irq_hwm=14`, `irq_last=7` after 600 ticks from a clean run, and again `$0e` after 712. 10 + 14 = **24** < 51 |
| 24 | `c64 profile tick` mean under 2,600 cycles | **PASS** | `477.7 cycles mean over 200 arrivals (min 388, max 971)`, identical across three clean runs; staged single arrivals price 388 idle, 456 sweep, 782 floor gate-on, 842 wall reversal + gate-on |
| 25 | `alive` differs 20 ticks apart | **PASS** | `alive=178` → `alive=188` |

### Shipping

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 26 | `c64 package` produces the `.d64` and `.prg`, run command `x64sc -ntsc amiga_ball.d64` | **PASS** | `packaged 'AMIGA BALL' -> demos/amiga_ball/amiga_ball.d64` / `run it with: x64sc -ntsc demos/amiga_ball/amiga_ball.d64` |
| 27 | `c64 test run demos/amiga_ball/test.yaml` passes | **PASS** | `PASS  amiga-ball  (c64, 24.86s)`, 167 steps |

### Shape

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 28 | the sphere's bbox measures 96 × 72 raster px | **PASS** | Red+white checker bbox measured in **seven** captures — three fresh `--scale 1` grabs at `rot_frame` 0/5/10 and the four committed evidence PNGs at `--scale 2` — all read **88 × 68** raster px, so 88+4+4 = **96** by 68+2+2 = **72**, and 96 × 0.7435 / 72 = **0.991**. Never judged by eye: §13.1 B is why |

**Tally: 28 PASS, 0 FAIL, 0 INCONCLUSIVE** — after four FAILs (6, 7, 8, 10)
were fixed and re-verified in this iteration. Criterion 22 passes on what it
substantively asserts and carries a defect in its quantitative clause, recorded
below rather than absorbed.

---

## SPEC.md defects found in this iteration

None of these is edited by this audit. They are reported for a ruling, because
editing the document a build is scored against is how a criterion gets
weakened.

1. **§6.1 — the contact geometry is one raster low.** It says "sphere bottom
   raster = `sprite_y` + 77" and "contact: `sprite_y` = 158 → sphere spans
   164-235"; measured, it is `sprite_y` + 78 and 165-236. Likewise "apex:
   `sprite_y` = 54 → sphere spans 60-131" is 61-132. **Proposed wording:**
   `sphere top raster = sprite_y + 7` / `sphere bottom raster = sprite_y + 78`,
   with `contact: sprite_y = 158 -> sphere spans 165-236` and
   `apex: sprite_y = 54 -> sphere spans 61-132`, plus the mechanism: *the VIC
   starts a sprite's DMA on the line where `$D012` equals its Y and displays
   that data on the next line, so a sprite whose Y register is V has its first
   row on raster V+1.*

2. **§7 — the shadow's contact line is one raster low.** "Ellipse centre row 10
   of 21 → raster 235, the contact line" is raster **236**, for the same
   reason. **Proposed wording:** `Ellipse centre row 10 of 21 -> raster 236
   (225 + 1 + 10), the contact line` — which is the same raster the ball's own
   bottom reaches, and that coincidence is the thing worth stating.

3. **§14 criterion 22 — "~250 ms" is not achievable with §8's own instrument.**
   The filter sweeps for 16 frames (267 ms) but `$D40C` = `$04` decays voice 2
   in 114 ms, so the centroid falls for ~100 ms and then the burst is gone.
   **Proposed wording:** *"The spectrogram of each capture shows a broadband
   transient at the impact frame whose energy centroid falls by at least a
   factor of three over the following ~100 ms — the filter sweep, which the
   piano roll cannot show — and the wall's centroid is higher than the floor's
   at every point in that window."* The last clause is free: it is already true
   (4,484 vs 4,204 Hz at onset, 1,881 vs 1,128 Hz at +100 ms) and it makes the
   criterion test §8's two-surfaces claim instead of only its one-gesture claim.

4. **§3.3 — the rim's stated benefit is not the benefit it has.** "The rim buys
   the silhouette" is false against the background: `$D025` and `$D021` are
   both black, so the rim and transparency are the same pixel. Its real and
   visible benefit is over the grid — no wall or floor line pixel ever touches
   a checker. **Proposed wording:** *"The rim is one texel of black at the limb.
   Against the black background it is invisible by construction — it is the
   background — and that is not what it is for: it guarantees that no purple
   wall line and no blue floor line ever touches a checker, so the ball keeps a
   clean dark edge wherever it crosses the grid, which is everywhere it
   matters. A Lambert term cannot make that guarantee and a red or white
   checker at the limb loses its edge against a purple line."*

5. **§1 — the deviations table is missing one.** The Amiga ball spins about an
   axis tilted ~17° from vertical; §5.2's ray cast uses a vertical axis and the
   table of three deliberate deviations does not mention it. **Proposed
   wording:** a fourth row — *"Spin axis tilted ~17° from vertical | **Vertical
   spin axis** | A tilt would move the poles off the block's centre column and
   cost texels at the limb, where 24 columns is already the whole budget; at
   4 × 2 px texels the lean reads as noise rather than as a lean. It is the
   most recognisable thing the ball gives up, and it is given up on purpose."*

6. **§11 — the sound row is a third under the measurement.** The table prices
   "sound (worst frame: gate-on)" at ~300; measured, the gate-on arm costs
   782 − 388 = **394** cycles. The total of ~840 is nonetheless right for the
   frame it describes — the wall impact stages at 842 — so only one row is
   wrong. **Proposed wording:** raise the sound row to ~390, keep the total at
   ~840, and append *"measured: `c64 profile tick --samples 200` reads 477.7
   mean, 388 min, 971 max; the wall-impact frame staged on its own prices 842
   and the floor-impact frame 782."*

## A defect outside `demos/amiga_ball/`, reported not edited

`skills/c64-development/references/hardware.md`, under sprite positioning, says
*"Sprite Y for **text row R is `51 + 8*R`**"* and *"a sprite at Y=50 sits one
raster line above row 0"*. Both are one high, by the measurement in Improve
above: a sprite at Y = 100 occupies rasters 101-121, so the Y that aligns a
sprite's top with text row R is **`50 + 8*R`**, and a sprite at Y = 50 sits
exactly *on* row 0's first line rather than above it. The paragraph goes on to
warn that "off by one raster line is invisible until a sprite lands next to
text; the invaders dogfood shipped its UFO a line high through a whole audit
iteration this way" — which is the same defect the rule of thumb would cause.
This is outside the scope of this task and is not touched.

---

## Is a second iteration needed?

**Yes, for one thing, and it needs a maintainer ruling rather than a commit.**

Everything scored can be scored again and comes back green; the four FAILs are
fixed and guarded by ten new regression assertions. What is left is the sound,
and it is not a bug:

> §8 designs the boing as a resonant low-pass collapsing over a noise burst,
> swept over 16 frames. Voice 2's decay is 114 ms and the sweep is 267 ms, so
> frames 7-15 of the gesture — nine of the sixteen — write `$D416` over a voice
> that is already 30 dB down. The centroid measurement shows the fall stopping
> at ~100 ms and the level reaching the noise floor at ~250 ms.

There are two one-constant fixes and they point in opposite directions, which
is exactly why this is a ruling and not a patch:

- **`$D40C` `$04` → `$06`** (decay 114 ms → 250 ms). The sweep becomes audible
  for its whole length and the impact gets wetter and longer — closer to a
  boing, further from §8's own "the transient is shorter than the thump it sits
  on".
- **`RAMP` 16 → 7** in `gen_sound.py`. The sweep ends where the burst does,
  the same sound comes out, and nine frames of dead register writes leave the
  IRQ. Honest, cheaper, and it concedes that the gesture is 117 ms rather than
  267 ms.

Either way the final gate is §13.2's: *the maintainer's listen of
`capture.wav`*. Neither change should be made on a spectral centroid alone, and
this audit did not make one.

The other open item for a second iteration is smaller and also a ruling: the six
`SPEC.md` defects above are proposed wording, not edits, and the
`hardware.md` sprite-Y rule is outside this task's scope.

## Watch item

`irq_hwm` is 14 raster lines against a ceiling of 40 and a hard operational
limit of 40 (`10 + irq_hwm < 51`). That is 26 lines of headroom, and the tick's
cost is genuinely fixed — no allocation, no search, no loop whose trip count
depends on the ball's position — so it should stay 14 unless something is
added. The one thing that would move it is a per-frame gesture on the sprite
data rather than the pointers; the 1,536 bytes of unspent `SPRITES` slack exist
precisely so that any such gesture can stay a pointer switch.
