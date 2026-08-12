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

## Iteration 3 — the performance candidates, decided in writing

**Scope of this section, and why it is here on its own.** This is the
*performance* half of iteration 3 and nothing else — the re-voiced hymn, the
texture arc and the band-pass belong to the same iteration and are not written
up here. It is landed separately because these seven decisions were produced
inside a plan workspace that is deleted when the plan closes, and a decision
that exists only in a deleted workspace is not a record. The fuller iteration-3
entry should **absorb this section**, not sit beside it.

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
shifted five tables `spanfill` indexes and took the one taken `→ sfnext` branch
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

---

## Closing state

- 136-step regression test passes; the demo runs the full 2:50 with
  `dropped = 0`, all ten shape types and all eight dither patterns used.
- The one ceiling worth watching: the program ends just below `$2000`, and the
  `$C400` block has its own size assertion. Both are **linker assertions**, so
  growing past either is a build error rather than a demo that quietly paints
  over its own canvas. The margin was **252** bytes at the close of iteration
  2 and is **120** after iteration 3 (see the performance section above). It
  has moved three times in one iteration, so read it out of `1812.lbl` rather
  than out of this line.
- Deliberately not optimised further: the per-scanline active-edge machinery
  is now comparable in cost to the fill itself for small shapes. With
  `dropped = 0` and a measured margin it is not worth the risk; the next
  person to want bigger or faster shapes should start there.
