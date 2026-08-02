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
there is a running sixteenth-note figure: 350 onsets in 2,100 frames, one
every six. That is texture, not accent. `secspawn[2]` changed from `%111` to
`%110`, so the battle spawns on the stabs and the bass hits.

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
| A3 | 732 shapes; `litcount` 3,913 → 20,853 → 27,991 → 28,309 → 29,845 → 29,980 |
| A4 | 2400 / 3900 / 6000 / 7800 / 10200, exact |
| A5 | rectangle at angles 0/48/96 — three different vertex sets, three PNGs |
| A6 | **64 of 64** addresses lit at the end of the hymn still lit at frame 10,201 |
| A7 | `cannons=16`; `$D020/$D021 = 241` during the flash, `240` eight frames later |
| A8 | mid-cannon voice 3 control `129` (`$81` noise+gate), routing `244`, volume `31` (`$1F` low-pass); mid-finale control `21` (`$15` ring+triangle); volume `0` in the hold |
| A9 | see below |
| A10 | `dropped = 0`, reproduced across two independent full runs |
| A11 | `typeseen = $03FF`, `patseen = $FF` |
| A12 | `shapes` unchanged over 120 frames of hold; a key resets `shapes` to 0, clears the bitmap and mixes the jiffy clock into `seed` |
| A13 | `smul` 141 · `rnd` 72 · `pickshape` 1,477 · `xform` 14,961 · `spanfill` 4,384 · worst-case `drawshape` 483,327 (28 frames) |
| A14 | `1812.d64` built; `x64sc -ntsc demos/1812/1812.d64` |

**A9 needed its anchor corrected.** Two passes with seed `$9977` compared at
the same *frame* count disagreed: identical lit counts, different checksums.
They had not diverged — a frame boundary had fallen inside a half-painted
shape, so the two passes were being compared at different points of the same
sequence. Re-anchored on `until shapedone --count 400`, the two passes agree
on `rng`, all last-shape bytes, the lit count, the checksum **and** the frame
number. `SPEC.md` A9 was amended to name the shape boundary and say why.

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

## Closing state

- 136-step regression test passes; the demo runs the full 2:50 with
  `dropped = 0`, all ten shape types and all eight dither patterns used.
- The one ceiling worth watching: the program ends a few hundred bytes below
  `$2000`, and the `$C400` block has its own size assertion. Both are
  **linker assertions**, so growing past either is a build error rather than
  a demo that quietly paints over its own canvas.
- Deliberately not optimised further: the per-scanline active-edge machinery
  is now comparable in cost to the fill itself for small shapes. With
  `dropped = 0` and a measured margin it is not worth the risk; the next
  person to want bigger or faster shapes should start there.
