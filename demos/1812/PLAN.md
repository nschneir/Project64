# 1812 — implementation plan

> **For agentic workers:** execute task by task with
> `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax.

**2026-08-12 — this file is the pre-build record and stays one.** Its
checkboxes are the plan the demo was built from, and they are deliberately
left as they were written. What the demo has become since is in `AUDIT.md`;
for what changed most recently — the texture arc, the performance decisions
and the audio evidence — see `AUDIT.md`, iteration 3.

**Goal:** Build the demo `SPEC.md` describes — randomized rotated,
dither-filled polygons accumulating on a never-cleared multicolor bitmap,
spawned by note onsets in a three-voice SID reduction of the *1812
Overture*.

**Architecture:** A CINV wedge at 60 Hz runs the sequencer and the section
clock and pushes spawn requests onto a ring buffer; the main loop pops them
and rasterizes. The rasterizer is vertex transform → edge build → active
edge table → even-odd scanline fill → byte-wise masked span fill. Nothing
in the paint path calls ROM.

**Tech stack:** ca65/ld65 via `c64 build`; `c64 run`/`until`/`mem`/`profile`
for verification; Python 3 stdlib for the two `tools/` generators.

Per `AGENTS.md` §Plans this plan specifies **interfaces, not code bodies**:
exact label names, byte-level variable tables, memory allocations, and one
verification command per task.

## Global constraints

- The program must end **below `$2000`**; the bitmap starts there.
  `load_addr + len - 2 < $2000` is checked after every build.
- Bitmap `$2000`, screen `$0400`, color RAM `$D800`, VIC bank 0 untouched.
- Mode registers exactly `$D011=$3B`, `$D016=$18`, `$D018=$18`,
  `$D020=$D021=$00`.
- Claimed zero page: `$02`, `$22-$2A`, `$FB-$FE` — nothing else.
- Every SID write goes through `sidput`; nothing else touches `$D400-$D418`.
- No ROM call in the paint path or the sequencer.
- Every included `.s` opens with an explicit `.segment` directive.
- Machine is NTSC (`c64`); all sessions run `--warp --headless`.
- Session name for every verification command below: **`s1812`**.
- Binary is `.venv/bin/c64` from the repository root; commands stay in the
  plain one-command form `AGENTS.md` asks for.

---

## File structure

| File | Responsibility |
|---|---|
| `1812.s` | load address, BASIC stub, hardware equates, zero-page equates, `init`, `mainloop`, `.include` of the rest |
| `vars.s` | every mutable byte — the observable block, the shape parameter block, the edge arrays, the queue |
| `tables.inc` | **generated**: `sintab`, `rowaddrl/h`, `xoff8l/h`, `attrscrl/h`, `attrcoll/h`, `notefreql/h` |
| `shapes.s` | `shpvx`/`shpvy` unit vertex rows, `shpn` vertex counts, `shpoff` offsets, `dither`, `leftmask`, `rightmask`, `inkbits` |
| `raster.s` | `smul`, `xform`, `buildedges`, `scanfill`, `spanfill`, `drawshape` |
| `spawn.s` | `rnd`, `rndlt`, `qpush`, `qpop`, `pickshape` |
| `sections.s` | `secframes`, `secpal`, `secshapes`, `secsizelo/hi`, `secspawn`, `secinstr` |
| `music.s` | `sndinit`, `sidput`, `seqtick`, `voicetick`, `cannonfire`, the score streams |
| `tools/gentables.py` | writes `tables.inc` |
| `tools/litcount.py` | lit-pixel count + checksum from a `c64 mem read --json` dump |
| `tools/evidence.sh` | the deterministic proof protocol |
| `test.yaml` | the regression test |

---

## Variable map (`vars.s`)

Authoritative byte layout. Labels are what tests and `c64 until` name.

**Observable block** — contiguous, in `DATA` so it is initialized by the
`.prg` rather than left holding RAM garbage:

| Label | Bytes | Init | Meaning |
|---|---|---|---|
| `seed` | 2 | `$1812` | RNG seed, poked before RUN |
| `rng` | 2 | 0 | live LFSR state |
| `frames` | 2 | 0 | frames since the run started |
| `section` | 1 | 0 | 0-5 |
| `secframe` | 2 | 0 | frames into the section |
| `noteidx` | 1 | 0 | V1 events consumed this section |
| `shapes` | 2 | 0 | shapes completed |
| `dropped` | 1 | 0 | spawn requests dropped |
| `cannons` | 1 | 0 | cannon shots fired |
| `flash` | 1 | 0 | frames of flash left |
| `painting` | 1 | 0 | 1 inside the rasterizer |
| `qhead` | 1 | 0 | ring buffer write index |
| `qtail` | 1 | 0 | ring buffer read index |
| `lstype` | 1 | 0 | last shape type |
| `lssize` | 1 | 0 | last shape size |
| `lsx` | 1 | 0 | last shape centre x (mc pixels) |
| `lsy` | 1 | 0 | last shape centre y |
| `lsangle` | 1 | 0 | last shape angle |
| `lspat` | 1 | 0 | last shape dither pattern |
| `lsink` | 1 | 0 | last shape ink (1-3) |
| `lsbytes` | 2 | 0 | bitmap bytes the last shape wrote |
| `typeseen` | 2 | 0 | bitmask of types drawn |
| `patseen` | 1 | 0 | bitmask of patterns used |
| `sidshadow` | 25 | 0 | shadow of `$D400-$D418` |

**Shape parameter block** (`DATA`) — `drawshape`'s inputs:

`sh_type` `sh_size` `sh_cx` `sh_cy` `sh_angle` `sh_pat` `sh_ink`, 1 byte each.

**Rasterizer working storage** (`BSS`, all `.res`, all zeroed by `init`):

| Label | Bytes | Meaning |
|---|---|---|
| `vxl` `vxh` | 16 each | transformed vertex x, 16-bit signed |
| `vyl` `vyh` | 16 each | transformed vertex y, 16-bit signed |
| `nvert` | 1 | vertex count for this shape |
| `eytl` `eyth` | 16 each | edge ytop |
| `eybl` `eybh` | 16 each | edge ybot |
| `exl` `exh` | 16 each | edge current x |
| `edxl` `edxh` | 16 each | edge \|dx\| |
| `edyl` `edyh` | 16 each | edge dy (> 0) |
| `eerl` `eerh` | 16 each | edge DDA error |
| `esx` | 16 | edge x step, `$01` or `$FF` |
| `eord` | 16 | edge indices sorted by ytop |
| `nedge` | 1 | edge count |
| `aet` | 16 | active edge indices |
| `naet` | 1 | active count |
| `enext` | 1 | index into `eord` of the next edge to admit |
| `symin` `symax` | 2 each | shape y extent, 16-bit signed |
| `crossl` `crossh` | 8 each | scanline crossings, 16-bit signed |
| `ncross` | 1 | crossings this scanline |
| `spy` | 1 | span fill row 0-199 |
| `spxa` `spxb` | 1 each | span fill x range, `spxa < spxb <= 160` |
| `queue` | 16 | spawn ring buffer payloads |
| `vptr` | 6 | per-voice stream pointer (3 × 16-bit) |
| `vcnt` | 6 | per-voice frames left on the current event (3 × 16-bit) |
| `vnote` | 3 | per-voice current note |
| `cutoff` | 1 | cannon filter cutoff, swept down |
| `csweep` | 1 | cannon sweep frames left |
| `pwphase` | 1 | pulse-width LFO phase |

---

## Task 1: Zero page is actually free

`SPEC.md` §2.3 claims `$22-$2A` on the argument that BASIC never runs again.
Prove it before any code depends on it.

**Files:** Create `/tmp/zpprobe.s` (scratch, not committed).

**Interfaces:** Produces nothing. It is a gate: if it fails, the zero-page
allocation in `vars.s` changes before Task 3.

- [ ] **Step 1.** Write a probe: BASIC stub, `sei`, install a CINV wedge that
      only chains to `$EA31`, `cli`, then `idle: jmp idle`. Export `idle`.
- [ ] **Step 2.** Run it and let the KERNAL IRQ run 600 frames with sentinels
      in place.

      Verify: `.venv/bin/c64 session start --name s1812 --warp --headless`,
      `.venv/bin/c64 -s s1812 run /tmp/zpprobe.s`,
      `.venv/bin/c64 -s s1812 mem write '$22' 90 90 90 90 90 90 90 90 90`,
      `.venv/bin/c64 -s s1812 mem write '$02' 90`,
      `.venv/bin/c64 -s s1812 mem write '$fb' 90 90 90 90`, then
      `.venv/bin/c64 -s s1812 until idle --count 600`, then
      `.venv/bin/c64 -s s1812 mem read '$22' 9`.
      Expected: all fourteen bytes still `5a`.
- [ ] **Step 3.** Record the result in `AUDIT.md` under "Iteration 0 —
      groundwork". If any byte moved, narrow the claim to the bytes that
      survived and re-plan the allocation.

---

## Task 2: Generated tables

**Files:** Create `tools/gentables.py`, `tables.inc`.

**Interfaces produced** (all `RODATA`, all referenced by later tasks):

| Label | Entries | Contents |
|---|---|---|
| `sintab` | 256 | `round(127·sin(2πi/256))`, signed bytes |
| `rowaddrl` `rowaddrh` | 200 each | `$2000 + (y & 248)·40 + (y & 7)` |
| `xoff8l` `xoff8h` | 40 each | `8·c`, 0…312 |
| `attrscrl` `attrscrh` | 25 each | `$0400 + 40·r` |
| `attrcoll` `attrcolh` | 25 each | `$D800 + 40·r` |
| `notefreql` `notefreqh` | 72 each | note 1 = C1 … note 72 = B6, `round(f·16777216/1022730)` |

- [ ] **Step 1.** Write `tools/gentables.py` (stdlib only, runnable
      standalone, writes `tables.inc` next to itself). Every table gets a
      comment header naming its formula and its indexing.
- [ ] **Step 2.** Generate and eyeball the invariants.

      Verify: `python3 demos/1812/tools/gentables.py` then
      `grep -c '^ *\.byte' demos/1812/tables.inc`.
      Expected: file written; `sintab[0]=0`, `sintab[64]=127`,
      `sintab[128]=0`, `sintab[192]=-127`; `rowaddr[0]=$2000`,
      `rowaddr[1]=$2001`, `rowaddr[8]=$2140`, `rowaddr[199]=$3E07`
      (the *last* bitmap byte, `$3F3F`, is `rowaddr[199] + 8·39` — corrected
      from `$3F3F` by the generator's self-test);
      `notefreq[46]` (A4) = 7218 per `references/hardware.md`.
- [ ] **Step 3.** Add a `--check` mode that re-derives every table and
      compares it to the committed `tables.inc`, so drift is detectable.

      Verify: `python3 demos/1812/tools/gentables.py --check`.
      Expected: exit 0, "tables.inc matches".
- [ ] **Step 4.** Commit `tools/gentables.py` and `tables.inc`.

---

## Task 3: Bitmap mode and a black canvas

Something on screen before anything else. No shapes yet.

**Files:** Create `1812.s`, `vars.s`, `sections.s` (palette table only).

**Interfaces produced:**
- `init` — sets the mode registers, clears `$2000-$3F3F` to `$00`, stamps
  screen RAM and color RAM with section 0's palette, zeroes the whole BSS
  block and the observable block, sets `$CC` nonzero.
- `mainloop` — `jmp mainloop` for now; the spin loop the queue drains into.
- `setpal` — in: A = section index. Stamps all 1000 screen and color cells
  with that section's triple. Used by `init`; later also by the restart path.
- `secpal` in `sections.s` — 6 × 2 bytes: `(c01<<4)|c10`, then `c11`.

- [ ] **Step 1.** Write `1812.s` with the `$0801` stub, the equate block,
      `init`, and `mainloop`; `vars.s` with the full variable map above;
      `sections.s` with `secpal` only.
- [ ] **Step 2.** Build and check the size ceiling.

      Verify: `.venv/bin/c64 build demos/1812/1812.s --json`.
      Expected: succeeds; `$0801 + len - 2 < $2000`.
- [ ] **Step 3.** Run and read the mode registers back with the masks
      `SPEC.md` §2.1 gives.

      Verify: `.venv/bin/c64 -s s1812 run demos/1812/1812.s`, then
      `.venv/bin/c64 -s s1812 until mainloop`, then
      `.venv/bin/c64 -s s1812 mem read '$D011' 1`,
      `.venv/bin/c64 -s s1812 mem read '$D016' 1`,
      `.venv/bin/c64 -s s1812 mem read '$D018' 1`,
      `.venv/bin/c64 -s s1812 mem read '$D020' 2`.
      Expected: `$D011 & $7F = $3B`, `$D016 & $1F = $18`,
      `$D018 & $FE = $18`, `$D020 & $0F = 0`, `$D021 & $0F = 0`.
- [ ] **Step 4.** Prove the canvas is black, from the dump, not by eye.

      Verify: `.venv/bin/c64 -s s1812 mem read '$2000' 256` and
      `.venv/bin/c64 -s s1812 mem read '$3E40' 256`.
      Expected: all `00`. Also `mem read '$0400' 8` = the section 0 palette
      byte `$BC`, and `mem read '$D800' 8` masked to `$0F` = `$0F`.
- [ ] **Step 5.** Capture the first evidence frame.

      Verify: `.venv/bin/c64 -s s1812 screen --png demos/1812/evidence/blank.png --scale 2 --border`.
      Expected: an all-black 2× frame with a black border.
- [ ] **Step 6.** Commit.

---

## Task 4: `spanfill` — the byte-wise masked span

The innermost loop. Built and unit-tested **before** any geometry, with
`c64 call`, so a fill bug can never hide behind a transform bug.

**Files:** Create `shapes.s` (masks only), `raster.s` (`spanfill` only).

**Interfaces produced:**
- `dither` — 8 patterns × 8 rows × 2 bytes = 128 bytes, `RODATA`, commented
  binary rows.
- `leftmask` 4 bytes = `$FF,$3F,$0F,$03`; `rightmask` 4 bytes =
  `$C0,$F0,$FC,$FF`.
- `inkbits` 4 bytes = `$00,$55,$AA,$FF` indexed by ink 0-3.
- `spanfill` — in: `spy` (0-199), `spxa`, `spxb` (`spxa < spxb <= 160`),
  `sh_pat`, `sh_ink`, `section`. Paints the bitmap bytes and stamps screen
  and color RAM for exactly the cells the span covers. Adds the byte count to
  `lsbytes`. Clobbers A/X/Y and the claimed zero page. Ends in `RTS`.

- [ ] **Step 1.** Write `dither`, the edge masks and `inkbits` in `shapes.s`,
      each pattern preceded by an 8×8 ASCII picture of what it draws.
- [ ] **Step 2.** Write `spanfill` in `raster.s`: row address from
      `rowaddrl/h`, `BMPPTR` from `xoff8l/h`, first cell masked by
      `leftmask`, tight middle loop, last cell masked by `rightmask`,
      `spxa>>2 == (spxb-1)>>2` handled as its own case; then the attribute
      pass through `SCRPTR`/`COLPTR`.
- [ ] **Step 3.** Unit-test a solid full-width span with `c64 call`.

      Verify: `.venv/bin/c64 -s s1812 run demos/1812/1812.s`,
      `.venv/bin/c64 -s s1812 mem write sh_pat 0`,
      `.venv/bin/c64 -s s1812 mem write sh_ink 3`,
      `.venv/bin/c64 -s s1812 mem write spy 0`,
      `.venv/bin/c64 -s s1812 mem write spxa 0`,
      `.venv/bin/c64 -s s1812 mem write spxb 160`,
      `.venv/bin/c64 -s s1812 call spanfill`, then
      `.venv/bin/c64 -s s1812 mem read '$2000' 16`.
      Expected: bytes at `$2000`, `$2008`, `$2010` … all `$FF`; the bytes
      between them (`$2001`-`$2007`, subrows 1-7) still `00`.
- [ ] **Step 4.** Unit-test the partial-cell edges.

      Verify: same run, `spxa=1`, `spxb=7`, `spy=0`, then
      `.venv/bin/c64 -s s1812 mem read '$2000' 24`.
      Expected: `$2000 = $3F` (left mask, pixels 1-3), `$2008 = $FC`
      (right mask, pixels 4-6), `$2010 = $00`.
- [ ] **Step 5.** Unit-test a dither pattern and the ink.

      Verify: `sh_pat=1` (50% checker), `sh_ink=1`, `spxa=0`, `spxb=8`,
      `spy=0` then `spy=1`, reading `$2000` and `$2001` after each call.
      Expected: `$2000 = $44` and `$2001 = $11` — the checker's two row
      phases with ink `%01`, and the untouched pixels still `00`.
- [ ] **Step 6.** Verify the attribute stamp is exact.

      Verify: after the `spxa=1,spxb=7` call,
      `.venv/bin/c64 -s s1812 mem read '$0400' 4` and
      `.venv/bin/c64 -s s1812 mem read '$D800' 4`.
      Expected: cells 0 and 1 hold the section palette; cell 2 unchanged.
- [ ] **Step 7.** Price it.

      Verify: `.venv/bin/c64 -s s1812 profile spanfill`.
      Expected: a cycle count recorded in `AUDIT.md` for the full-width case.
- [ ] **Step 8.** Commit.

---

## Task 5: `smul` and `xform` — the rotating vertex transform

**Files:** Modify `raster.s`; create the vertex tables in `shapes.s`.

**Interfaces produced:**
- `smul` — in: `MULA`, `MULB` (signed bytes). Out: `MULR`/`MULR+1` (signed
  16-bit product). Unrolled shift-add on magnitudes, sign fixup. `RTS`.
- `shpvx`, `shpvy` — concatenated unit vertex bytes for all ten shapes,
  radius 64, isotropic screen-pixel space.
- `shpn` — 10 bytes, vertex count per type.
- `shpoff` — 10 bytes, index of each type's first vertex in `shpvx`/`shpvy`.
- `xform` — in: `sh_type`, `sh_size`, `sh_angle`, `sh_cx`, `sh_cy`. Out:
  `vxl/vxh`, `vyl/vyh`, `nvert`. Applies `SPEC.md` §5.3 including the `>>1`
  aspect correction on x. `RTS`.

- [ ] **Step 1.** Write `smul`.
- [ ] **Step 2.** Unit-test `smul` at the four sign quadrants and the
      extremes.

      Verify: for each of (100,100), (-100,100), (100,-100), (-100,-100),
      (127,127), (0,55), (-128,1):
      `.venv/bin/c64 -s s1812 mem write MULA <a>`,
      `.venv/bin/c64 -s s1812 mem write MULB <b>`,
      `.venv/bin/c64 -s s1812 call smul`,
      `.venv/bin/c64 -s s1812 mem read MULR 2`.
      Expected: 10000, −10000, −10000, 10000, 16129, 0, −128 as
      little-endian two's-complement words.
- [ ] **Step 3.** Write the ten vertex tables, each with a comment giving its
      construction (angles and radii) so the numbers are auditable.
- [ ] **Step 4.** Write `xform`.
- [ ] **Step 5.** Unit-test the identity case: a square at angle 0.

      Verify: `sh_type=1`, `sh_size=64`, `sh_angle=0`, `sh_cx=80`,
      `sh_cy=100`, `.venv/bin/c64 -s s1812 call xform`, then
      `.venv/bin/c64 -s s1812 mem read vxl 4` and `mem read vyl 4`.
      Expected: x values 80±22 (45·64/64 = 45 screen px → 22 mc px),
      y values 100±45.
- [ ] **Step 6.** Unit-test the rotation: the same square at angle 32 (45°).

      Verify: `sh_angle=32`, `call xform`, read `vxl`/`vyl`.
      Expected: the four corners now lie on the axes — one vertex at
      x ≈ 80, y ≈ 100−64, another at x ≈ 80+32, y ≈ 100 — i.e. a diamond,
      and no vertex magnitude exceeds `sh_size`.
- [ ] **Step 7.** Price it.

      Verify: `.venv/bin/c64 -s s1812 profile xform` for `sh_type=5`
      (circle, 16 vertices — the worst case).
      Expected: cycle count recorded in `AUDIT.md`.
- [ ] **Step 8.** Commit.

---

## Task 6: `buildedges`, `scanfill`, `drawshape` — a shape on screen

**Files:** Modify `raster.s`.

**Interfaces produced:**
- `buildedges` — in: `vxl/vxh`, `vyl/vyh`, `nvert`. Out: the edge arrays,
  `nedge`, `eord` (indices sorted by `ytop`), `symin`, `symax`. Edges with
  `vy0 == vy1` are dropped. No division: DDA fields only. `RTS`.
- `scanfill` — walks y from `symin` to `min(symax, 199)`, maintaining `aet`
  / `naet` / `enext`; collects up to 8 crossings into `crossl/h`,
  insertion-sorts them, and calls `spanfill` for each pair, clipped to
  x `[0,160]` and skipped entirely when y < 0. `RTS`.
- `drawshape` — in: the `sh_*` block. Sets `painting` = 1, zeroes `lsbytes`,
  runs `xform` → `buildedges` → `scanfill`, copies `sh_*` into the `ls*`
  bytes, ORs `typeseen`/`patseen`, increments `shapes`, clears `painting`.
  Exports `shapedone` as the label of its final `RTS` path. `RTS`.

- [ ] **Step 1.** Write `buildedges`.
- [ ] **Step 2.** Unit-test it on the angle-0 square.

      Verify: `call xform` as in Task 5 step 5, then
      `.venv/bin/c64 -s s1812 call buildedges`, then
      `.venv/bin/c64 -s s1812 mem read nedge 1` and `mem read eord 4`.
      Expected: `nedge = 2` (the two horizontal edges are dropped), and
      `eord` sorts them by `ytop`; `symin = 55`, `symax = 145`.
- [ ] **Step 3.** Write `scanfill` and `drawshape`.
- [ ] **Step 4.** Draw one square and look at it.

      Verify: `sh_type=1`, `sh_size=64`, `sh_angle=0`, `sh_cx=80`,
      `sh_cy=100`, `sh_pat=0`, `sh_ink=3`,
      `.venv/bin/c64 -s s1812 call drawshape`, then
      `.venv/bin/c64 -s s1812 screen --png /tmp/sq.png --scale 2`.
      Expected: a solid light-grey square, not a rhombus, roughly 45 screen
      pixels either side of centre; `shapes = 1`; `lsbytes` nonzero.
- [ ] **Step 5.** Draw the same square rotated and confirm it reads as a
      diamond.

      Verify: `sh_angle=32`, `call drawshape`, `screen --png /tmp/di.png`.
      Expected: a diamond whose points touch the square's edge midpoints.
- [ ] **Step 6.** Draw the concave star and confirm the fill is even-odd, not
      convex-hull.

      Verify: `sh_type=4`, `sh_size=80`, `sh_angle=0`, `call drawshape`,
      `screen --png /tmp/star.png`.
      Expected: five points with **black notches between them** — a filled
      pentagon means the crossing sort or the pairing is wrong.
- [ ] **Step 7.** Confirm clipping, not skipping.

      Verify: `sh_cx=0`, `sh_cy=0`, `sh_size=80`, `sh_type=5`,
      `call drawshape`, then `screen --png /tmp/clip.png` and
      `.venv/bin/c64 -s s1812 mem read '$2000' 8`.
      Expected: a quarter circle in the top-left corner; no wrapped pixels
      on the opposite edge; the machine did not hang.
- [ ] **Step 8.** Confirm the crossing ceiling holds.

      Verify: `sh_type=9` (cross), `sh_angle=20`, `sh_size=80`,
      `call drawshape`, `.venv/bin/c64 -s s1812 mem read ncross 1`.
      Expected: `ncross <= 8` at every stop; add a temporary high-water
      byte if needed to prove the maximum over a whole shape.
- [ ] **Step 9.** Price the worst case.

      Verify: `.venv/bin/c64 -s s1812 profile drawshape` with
      `sh_type=5`, `sh_size=90`, `sh_pat=0`.
      Expected: cycle count recorded in `AUDIT.md`, converted to frames at
      17,095 cycles/frame (NTSC).
- [ ] **Step 10.** Commit.

---

## Task 7: RNG, queue, and shape policy — a canvas that fills itself

Still no music: a frame counter spawns shapes so the whole rasterizer is
exercised under load before the sequencer exists.

**Files:** Create `spawn.s`; modify `1812.s`, `sections.s`.

**Interfaces produced:**
- `rnd` — out: A = next byte, `rng` advanced (Galois, taps `$B400`, zero
  forced to 1). `RTS`.
- `rndlt` — in: A = bound 1-255. Out: A in `0..bound-1`, reject-and-retry so
  it is unbiased. `RTS`.
- `qpush` — in: A = payload. Pushes onto `queue`; on full, increments
  `dropped` and returns without pushing. `RTS`.
- `qpop` — out: carry set and A = payload, or carry clear when empty. `RTS`.
- `pickshape` — in: A = payload. Fills `sh_type` `sh_size` `sh_cx` `sh_cy`
  `sh_angle` `sh_pat` `sh_ink` from `rnd` within the current section's
  policy. `RTS`.
- `sections.s` gains: `secframes` (6 × 2, frame budgets from `SPEC.md` §6.4),
  `secshapes` (6 × 2 — a 16-bit mask of allowed `sh_type` values),
  `secsizelo`/`secsizehi` (6 each), `secspawn` (6, voice mask).
- `mainloop` now: `qpop`; on carry, `pickshape` then `drawshape`.

- [ ] **Step 1.** Write `rnd` and `rndlt`; wire `init` to copy `seed` → `rng`
      and force a zero to 1.
- [ ] **Step 2.** Prove the LFSR's period and its reproducibility.

      Verify: `.venv/bin/c64 -s s1812 mem write rng '$12' '$18'`, then 8×
      `.venv/bin/c64 -s s1812 call rnd` with `mem read rng 2` between,
      recording the sequence; repeat from the same state.
      Expected: identical sequences; no state repeats within the 8; state
      never reaches `$0000`.
- [ ] **Step 3.** Write `qpush`/`qpop` and prove the overflow policy.

      Verify: 20× `call qpush` with `a` set, then
      `.venv/bin/c64 -s s1812 mem read dropped 1` and `mem read qhead 1`.
      Expected: `dropped = 5` (16-entry ring, one slot reserved to
      distinguish full from empty — state the chosen convention in the
      source comment and match it here), `qhead`/`qtail` in range.
- [ ] **Step 4.** Write `pickshape` and the four `sections.s` tables.
- [ ] **Step 5.** Add a temporary spawn timer to `mainloop`'s idle path (one
      `qpush` every 30 frames of `$A2` movement) and let it paint.

      Verify: `.venv/bin/c64 -s s1812 run demos/1812/1812.s`, wait, then
      `.venv/bin/c64 -s s1812 until shapedone --count 60`, then
      `.venv/bin/c64 -s s1812 mem read shapes 2` and
      `.venv/bin/c64 -s s1812 screen --png /tmp/fill.png --scale 2`.
      Expected: `shapes = 60`; a canvas of varied overlapping shapes; no
      hang; `dropped` still 0.
- [ ] **Step 6.** Prove accumulation from the dump.

      Verify: `.venv/bin/c64 -s s1812 mem read '$2000' 8000 --json` piped to
      `python3 demos/1812/tools/litcount.py` at 10 and at 60 shapes
      (write `tools/litcount.py` in this step).
      Expected: the later count is strictly greater, and every address in a
      sample of 64 lit at 10 shapes is still lit at 60.
- [ ] **Step 7.** Commit.

---

## Task 8: The 60 Hz wedge, the section clock, and the palettes

**Files:** Modify `1812.s`, `sections.s`; create `music.s` with the tick
skeleton only.

**Interfaces produced:**
- `irqinstall` — saves `$0314/$0315` into `oldvec`, points CINV at `wedge`,
  with `sei`/`cli` around it. Build-time check: `oldvec` low byte is not
  `$FF`.
- `wedge` — increments `frames` and `secframe`, calls `seqtick`, handles
  `flash`, then `jmp (oldvec)`.
- `seqtick` (`music.s`) — **the frame anchor**. For now: advance the section
  when `secframe` reaches `secframes[section]`, and on advance set
  `section`, zero `secframe`, `jsr setpal`, and pass through `secchange`.
- `secchange` — a label on the section-advance path, for `c64 until`.
- Temporary spawn timer moves from `mainloop` into `seqtick`.

- [ ] **Step 1.** Write `irqinstall`, `wedge`, and the `seqtick` skeleton.
- [ ] **Step 2.** Confirm the wedge is the frame anchor and the KERNAL still
      lives.

      Verify: `.venv/bin/c64 -s s1812 until seqtick --count 60`, then
      `.venv/bin/c64 -s s1812 mem read frames 2` and
      `.venv/bin/c64 -s s1812 mem read '$A2' 1` twice separated by another
      `until seqtick --count 60`.
      Expected: `frames` = 60 then 120; the jiffy byte advanced by ~60 as
      well, proving the chain to `$EA31` is intact.
- [ ] **Step 3.** Check the `jmp (oldvec)` page-boundary trap.

      Verify: `grep -i oldvec demos/1812/1812.lbl`.
      Expected: the address's low byte is not `$FF`.
- [ ] **Step 4.** Confirm the section clock and the repalette.

      Verify: `.venv/bin/c64 -s s1812 until secchange --count 1`, then
      `.venv/bin/c64 -s s1812 mem read section 1`,
      `.venv/bin/c64 -s s1812 mem read frames 2`,
      `.venv/bin/c64 -s s1812 mem read '$0400' 4`.
      Expected: `section = 1`, `frames = 2400`, screen bytes now section 1's
      `(6<<4)|2 = $62`.
- [ ] **Step 5.** Confirm the palette change re-tints what is already there.

      Verify: `screen --png /tmp/sec1.png --scale 2` right after the stop.
      Expected: shapes painted during section 0 that lie in cells section 1
      has since touched now show section 1's colors — the policy of
      `SPEC.md` §3, visible.
- [ ] **Step 6.** Commit.

---

## Task 9: The SID sequencer

**Files:** Modify `music.s`, `sections.s`.

**Interfaces produced:**
- `sndinit` — writes 0 through `sidput` to all 25 registers, then volume 15.
- `sidput` — in: X = offset `$00-$18`, A = value. `sta $D400,x` +
  `sta sidshadow,x`. The **only** writer of the SID. `RTS`.
- `voicetick` — in: X = voice 0-2. Decrements `vcnt`, fetches the next
  `(note,duration)` pair from `vptr` on expiry, gates, releases 3 frames
  early, handles `0` = rest, `$FD` = `cannonfire`, `$FF` = rewind. On a
  gate-on, if bit X of `secspawn[section]` is set, `qpush`. `RTS`.
- `secinstr` (`sections.s`) — 6 sections × 3 voices × 5 bytes: waveform,
  attack/decay, sustain/release, PW lo, PW hi.
- `seqtick` now calls `voicetick` for X = 0,1,2 and steps `pwphase`.
- Section 0's three streams in `music.s` (hymn only, for this task).

- [ ] **Step 1.** Write `sidput`, `sndinit`, `voicetick`; add section 0's
      streams and `secinstr`.
- [ ] **Step 2.** Prove every SID write is shadowed.

      Verify: `.venv/bin/c64 -s s1812 until seqtick --count 120`, then
      `.venv/bin/c64 -s s1812 mem read sidshadow 25`.
      Expected: nonzero frequency bytes on voices 1-3, ADSR bytes matching
      `secinstr` section 0, control bytes with gate bit 0 set on a sounding
      voice, and `sidshadow+$18` = `$0F`.
- [ ] **Step 3.** Prove the shadow matches the chip — search RAM for any
      second writer.

      Verify: `.venv/bin/c64 -s s1812 disasm drawshape 200` and
      `grep -n 'd4[0-9a-f][0-9a-f]' demos/1812/*.s`.
      Expected: `$D4xx` appears only inside `sidput`.
- [ ] **Step 4.** Prove note onsets drive spawns.

      Verify: `.venv/bin/c64 -s s1812 mem write shapes 0 0`, then
      `.venv/bin/c64 -s s1812 until seqtick --count 600`, then
      `.venv/bin/c64 -s s1812 mem read shapes 2` and
      `.venv/bin/c64 -s s1812 mem read noteidx 1`.
      Expected: `shapes` tracks `noteidx` for a section whose `secspawn`
      selects one voice; `dropped = 0`.
- [ ] **Step 5.** Remove the temporary spawn timer from `seqtick`.

      Verify: `grep -n 'spawn timer' demos/1812/*.s`.
      Expected: no hits.
- [ ] **Step 6.** Commit.

---

## Task 10: The arrangement

**Files:** Modify `music.s`, `sections.s`.

**Interfaces produced:** streams for sections 1-4 and the `secinstr` rows
for them; `notes.inc`-style equates (`N_C1` … `N_B6`) so the score reads as
music rather than as numbers.

- [ ] **Step 1.** Add note-name equates and write section 1 (Marseillaise),
      2 (battle), 3 (cannon), 4 (finale) streams — an original reduction,
      not a transcription of an existing arrangement.
- [ ] **Step 2.** Confirm the whole piece runs to its end and the sections
      land on their budgets.

      Verify: `.venv/bin/c64 -s s1812 until seqtick --count 10201`, then
      `.venv/bin/c64 -s s1812 mem read section 1`,
      `.venv/bin/c64 -s s1812 mem read frames 2`.
      Expected: `section = 5`, `frames = 10201`.
- [ ] **Step 3.** Listen to it — capture the shadow at four points and check
      the material is what the section says it is.

      Verify: `until secchange --count N` for N = 1..4, `mem read sidshadow 25`
      at each.
      Expected: section 1 pulse with a moving PW, section 2 sawtooth with
      the band-pass bits in `sidshadow+$17`/`+$18`, section 4 ring+triangle
      on voice 3.
- [ ] **Step 4.** Play it for real, once, and judge it as a listener.

      Verify: `.venv/bin/c64 session start --name listen`, then
      `.venv/bin/c64 -s listen run demos/1812/1812.s` on a non-warp session.
      Expected: the hymn, the Marseillaise fragment, the battle and the
      finale are recognizable as such. Findings go in `AUDIT.md`.
- [ ] **Step 5.** Commit.

---

## Task 11: The cannon and the flash

**Files:** Modify `music.s`, `1812.s`.

**Interfaces produced:**
- `cannonfire` — the `$FD` handler: noise + gate on voice 3, ADSR `$0A`/`$08`,
  `$D417` routing bit 2, `$D418` low-pass + volume 15, `cutoff` = `$FF`,
  `csweep` = 24, `flash` = 6, one large + six small `qpush`, `cannons`++.
- The `wedge`'s flash handling: `flash > 0` → `$D020` and `$D021` = 1;
  on expiry both back to 0.
- The `seqtick` cutoff sweep: while `csweep > 0`, `cutoff` -= 10 (floor
  `$10`), written to `$D416` through `sidput`.

- [ ] **Step 1.** Write `cannonfire`, the sweep and the flash.
- [ ] **Step 2.** Stop on a shot and read the flash registers.

      Verify: `.venv/bin/c64 -s s1812 until cannonfire --count 1`, then
      `.venv/bin/c64 -s s1812 mem read flash 1`,
      `.venv/bin/c64 -s s1812 until seqtick --count 1`, then
      `.venv/bin/c64 -s s1812 mem read '$D020' 2`.
      Expected: `flash = 6`; `$D020 & $0F = 1` and `$D021 & $0F = 1`.
- [ ] **Step 3.** Confirm it goes back to black.

      Verify: `.venv/bin/c64 -s s1812 until seqtick --count 8`, then
      `.venv/bin/c64 -s s1812 mem read '$D020' 2`.
      Expected: both `& $0F = 0`.
- [ ] **Step 4.** Confirm the count and the burst.

      Verify: `.venv/bin/c64 -s s1812 until secchange --count 4`, then
      `.venv/bin/c64 -s s1812 mem read cannons 1` and `mem read dropped 1`.
      Expected: `cannons = 16`, `dropped = 0`.
- [ ] **Step 5.** Capture the flash.

      Verify: `until cannonfire`, `until seqtick --count 1`, then
      `.venv/bin/c64 -s s1812 screen --png demos/1812/evidence/cannon.png --scale 2 --border`.
      Expected: a white field and a white border.
- [ ] **Step 6.** Commit.

---

## Task 12: The hold and the restart

**Files:** Modify `1812.s`, `music.s`.

**Interfaces produced:**
- Section 5 in `seqtick`: silence (`sidput` volume 0, all three gates off),
  stop spawning.
- `mainloop` reads `$CB` when `section == 5`; a code other than 64 calls
  `restart` — which mixes `$A2` into `seed`, reseeds `rng`, zeroes the
  observable counters, re-clears the bitmap, `setpal 0`, `section` = 0.

- [ ] **Step 1.** Write the hold and `restart`.
- [ ] **Step 2.** Prove the hold holds.

      Verify: `.venv/bin/c64 -s s1812 until seqtick --count 10201`,
      `.venv/bin/c64 -s s1812 mem read shapes 2`, then
      `.venv/bin/c64 -s s1812 until seqtick --count 120`, then
      `.venv/bin/c64 -s s1812 mem read shapes 2` and
      `.venv/bin/c64 -s s1812 mem read sidshadow+24 1`.
      Expected: `shapes` identical across the two reads; volume shadow
      `& $0F = 0`.
- [ ] **Step 3.** Prove the restart.

      Verify: `.venv/bin/c64 -s s1812 mem read rng 2` (record), then
      `.venv/bin/c64 -s s1812 mem write '$CB' 60`,
      `.venv/bin/c64 -s s1812 until seqtick --count 2`, then
      `.venv/bin/c64 -s s1812 mem read shapes 2`,
      `.venv/bin/c64 -s s1812 mem read rng 2`,
      `.venv/bin/c64 -s s1812 mem read '$2000' 64`.
      Expected: `shapes = 0`; `rng` differs from the recorded value; the
      sampled bitmap bytes are `00` again.
- [ ] **Step 4.** Commit.

---

## Task 13: The regression test

**Files:** Create `test.yaml`.

**Interfaces consumed:** every label in the variable map; `seqtick`,
`drawshape`, `secchange`, `cannonfire`.

- [ ] **Step 1.** Write `test.yaml` covering the ten bullets of `SPEC.md`
      §10. Use `autorun: false` + `poke: {addr: seed}` + `key: "run\n"` for
      the determinism check; `sample`/`greater_than` for `shapes`; masked
      compares for every VIC-II color register.
- [ ] **Step 2.** Run it.

      Verify: `.venv/bin/c64 test run demos/1812/test.yaml`.
      Expected: every step passes.
- [ ] **Step 3.** Break it on purpose once — change one expected value — and
      confirm it fails at that step, so the test is known to be load-bearing.

      Verify: same command with one assertion altered.
      Expected: exit 1, naming the altered step. Revert.
- [ ] **Step 4.** Commit.

---

## Task 14: Evidence and the disk

**Files:** Create `tools/evidence.sh`; produce `evidence/*.png`,
`1812.d64`, `1812.prg`.

- [ ] **Step 1.** Write `tools/evidence.sh` following
      `demos/invaders/tools/evidence.sh`: its own session, every capture
      taken **stopped** at a `c64 until` label, `--scale 2 --border`,
      re-runnable, and printing the state bytes beside each frame.
- [ ] **Step 2.** Run it.

      Verify: `sh demos/1812/tools/evidence.sh`.
      Expected: the full evidence set of `SPEC.md` §11 written, the
      `litcount` series monotone, the 64-address persistence check passing,
      and the SID shadow dumps in the log.
- [ ] **Step 3.** Package.

      Verify: `.venv/bin/c64 package demos/1812/1812.s -o demos/1812/1812.d64 --title "1812" --json`.
      Expected: image written, `run` reports `x64sc -ntsc …`.
- [ ] **Step 4.** Boot the packaged image the way a recipient would.

      Verify: `.venv/bin/c64 -s s1812 disk boot demos/1812/1812.d64`, then
      `.venv/bin/c64 -s s1812 until seqtick --count 300`, then
      `.venv/bin/c64 -s s1812 screen --png demos/1812/evidence/shipped-d64.png --scale 2 --border`.
      Expected: it runs from the image, not just from source.
- [ ] **Step 5.** Commit.

---

## Task 15: The improvement loop

Not a single-pass task — the numbered cycle `PROMPT.md` requires, logged in
`AUDIT.md`. Each iteration:

- [ ] **Evaluate.** Run the proof protocol and mark every `SPEC.md` §12
      criterion PASS or FAIL with the observation that decided it. No
      verdict may come from reading the source.
- [ ] **Review.** Cycle-count `spanfill`, `xform`, `scanfill` and a
      worst-case `drawshape` with `c64 profile`; scrutinize where the
      rasterizer and the sequencer contend for a frame; delete dead code;
      then judge it as a viewer and a listener would and write down whether
      the picture looks good and the arrangement sounds like the Overture.
- [ ] **Improve.** Fix every FAIL and act on every review finding.
- [ ] **Re-verify.** Prove each fix on the running machine before counting
      it done; re-run `test.yaml` and `tools/evidence.sh`.
- [ ] **Commit** the iteration and its `AUDIT.md` entry.

Stop when an iteration ends with every criterion PASS and a review with
nothing worth fixing. Check in with the maintainer if it passes four
iterations.

---

## Self-review

- **Spec coverage.** §2 → Task 3; §2.3 → Task 1; §3 → Tasks 3, 8; §4 →
  Task 5; §5.2 → Task 2; §5.3 → Task 5; §5.4 → Task 6; §5.5/§5.6 → Task 4;
  §6.1/§6.2 → Task 8; §6.3/§6.4/§6.5 → Tasks 9, 10; §6.6 → Task 11; §6.7 →
  Task 10; §7 → Task 7; §8 → Tasks 3, 6, 7; §9 → all; §10 → Task 13; §11 →
  Task 14; §12 → Task 15; §13 → nothing to build.
- **Name consistency.** `spanfill`/`xform`/`buildedges`/`scanfill`/
  `drawshape`/`shapedone`/`seqtick`/`secchange`/`cannonfire`/`rnd`/`rndlt`/
  `qpush`/`qpop`/`pickshape`/`sidput`/`sndinit`/`voicetick`/`setpal`/
  `irqinstall`/`restart` are used with the same spelling in every task and
  in `SPEC.md` §8.
- **No placeholders.** Every step names the file it touches and the exact
  command that decides it.
