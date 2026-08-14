# Fugue in C Minor — implementation plan

> **For agentic workers:** use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to work this task by task. Steps are
> checkboxes.

**Goal:** a C64 demo that plays BWV 847 on three SID voices while its notated
score scrolls right-to-left in time with the music, in pure 6502 assembly.

**Architecture:** one raster IRQ at line 204 drives everything from a single
frame counter. The scroll offset *is* the sixteenth-note subdivision counter,
so picture and music cannot drift. One 1,488-byte array of note bytes is read
twice — once by the renderer 15 sixteenths ahead, once by the sequencer — so
the two evidence streams have one source.

**Tech Stack:** ca65 via `c64 build --area`; `c64 charset encode` and
`c64 sprite encode` for graphic data; stdlib-only Python in `tools/` for the
arrangement and its derived tables; `c64 test run` and `c64 audio capture`
for verification.

**Spec:** `demos/fugue/SPEC.md` — read it first; every task argues from it.

## Global constraints

- Machine **NTSC** (`c64`). 17,095 cycles/frame, 60 fps, clock 1,022,727 Hz.
- Screen stays at `$0400`. VIC bank 0, untouched (`$DD00` is never written).
- Charset `$2000`, sprites `$2800`; `$1000`/`$1800` are illegal charset bases.
- Build: `c64 build --area 'CHARS=$2000:$0800' --area 'SPRITES=$2800:$0100'`.
  The same two strings go in `test.yaml`'s `areas:`.
- Screen codes used: **32-79 only.** Never 96, never 224, never 128-154.
- Every mutable byte lives in `vars.s` in the **`DATA`** segment, not `BSS`:
  BSS is not part of the `.prg`, so a `.res` there loads as whatever was in
  RAM, while DATA ships real initialisers and a fresh LOAD starts from a
  known state. This is `demos/invaders/vars.s`'s convention and its stated
  reason. No `.export` is needed — ld65's `-Ln` emits every label
  (`demos/invaders` has 357 labels in its `.lbl` and zero `.export`
  directives) — but an *equate* never reaches the file, so anything a test
  names must be storage.
- The position ladder is **absolute**: `row = LADTOP + (p >> 1)`,
  `sprite Y = 42 + 8*LADTOP + 4*p`, for `p` = 0 (D6) to 29 (C2). `LADTOP` = 5.
  Both formulas are *derived in the source* from `LADTOP`, never written down
  as a number — Task 10 shipped a hardcoded 74 and it silently stopped
  matching when the band moved.
- Every SID write goes through `sidwr`, which mirrors it into `sidshadow`.
- Colour-RAM and `$D020`/`$D021` assertions are masked `and: "$0f"`.
- Start every included `.s` file with an explicit `.segment` directive —
  segment state carries across `.include` (asm/SKILL.md).
- A branch that fails to assemble with "Range error" is fixed mechanically:
  `c64 build demos/fugue/fugue.s 2>&1 | python3
  skills/6502-assembly/references/fix-branch-range.py`.
- Session for all live work: `c64 session start --name fug --warp --headless`,
  and every unattended live command runs under `caffeinate -dimsu`.
- Demo `tools/` scripts are outside the repo's ruff and pyright gates; they
  are stdlib-only Python 3 and are tested by the demo.

---

## File structure

| File | Responsibility |
|---|---|
| `fugue.s` | load address, BASIC stub, equates, `init`, `irq`, `tick`, includes |
| `vars.s` | every mutable byte, with the labels tests read |
| `staff.s` | `drawscreen`, `drawcol`, row-base and glyph tables |
| `scroll.s` | `shiftband`, the `$D016` write |
| `music.s` | `musinit`, `musfetch`, `muswrite`, `sidwr`, sweeps |
| `glow.s` | `glowtick` |
| `chars.inc` `sprites.inc` `notes.inc` | generated data, committed |
| `tools/*.py` `tools/*.txt` `tools/*.sh` | generators and the evidence protocol |
| `test.yaml` | the regression test |

### Zero page

`$FB-$FE` only — the four bytes documented free in `zero-page.md`.
`ptr` = `$FB/$FC` (screen), `cptr` = `$FD/$FE` (colour RAM). Nothing else in
zero page is touched; BASIC is still resident.

### Glyph code map (fixed here, consumed by Tasks 3, 6)

| Codes | Meaning | Index |
|---|---|---|
| 32 | blank | — |
| 33 | staff line / ledger line | — |
| 34-41 | single head | `HEADONE + (online<<2) + (hollow<<1) + half` |
| 42-49 | both halves | `HEADTWO + (online<<2) + (lowerhollow<<1) + upperhollow` |
| 50-57 | accidental | `ACCID + (online<<2) + (half<<1) + flat` |
| 58-59 | bar line | `BARLINE + online` |
| 60-63 | unused, blank (padding to keep the sheet contiguous) | — |
| 64-73 | treble clef, 2 cols × 5 rows, column-major | `CLEFT + col*5 + (row-6)` |
| 74-79 | bass clef, 2 cols × 3 rows, column-major | `CLEFB + col*3 + (row-12)` |

`half`: 0 = upper (pixel rows 0-3), 1 = lower (pixel rows 4-7).
`online`: 1 when the cell's screen row carries a staff or ledger line.

### Position ladder (fixed here, consumed by Tasks 2, 6, 8, 10)

`p` = 0 at the top. `row = LADTOP + (p >> 1)`, `half = p & 1`,
`sprite Y = 42 + 8*LADTOP + 4*p`. The pitch of position `p` is `posmidi[p]`;
the full table is SPEC §3. `LADTOP = BANDTOP = 5` and `BANDROWS = 15`, put
there by Task 7's raster budget rather than by the range.

---

## Task 1: the arrangement

**Files:** create `demos/fugue/tools/bwv847.py`.

**Produces:** `BARS` (31 bars × 3 voices of `(pitch, sixteenths)` events,
each voice summing to 16 per bar; `"rest"` and `"tie"` are the two
non-pitch tokens), `SUBJECT_ENTRIES`, `PEDAL`, and a `main()` that
self-checks and prints the pitch-class histogram and per-voice range.

- [ ] Write the reduction from the public-domain score as original work —
      not from anyone's SID, MIDI or published arrangement.
- [ ] Self-checks: 31 bars; every voice sums to 16 per bar; no `tie` after a
      `rest`; every pitch parses and lies in C2-C6; the exposition's three
      subject entries agree as interval sequences except where a commented
      exemption names the tonal-answer adjustment; attacks-per-pitch-class
      histogram; total = 496 sixteenths.
- [ ] **Verify:** `python3 demos/fugue/tools/bwv847.py` prints `OK` and exits 0.

## Task 2: derived tables and the colour assignment

**Files:** create `demos/fugue/tools/genmusic.py`; generate
`demos/fugue/notes.inc`.

**Consumes:** `bwv847.BARS`, `SUBJECT_ENTRIES`.
**Produces:** `notes.inc` holding `notes1`/`notes2`/`notes3` (496 bytes
each, encoding per SPEC §10), `posmidi` (30 bytes), and four frequency
tables `ntsclo`/`ntschi`/`pallo`/`palhi` (56 bytes each, MIDI 33-88, from
`round(hz * 2**24 / clock)` at 1,022,727 and 985,248 Hz). Also prints, to
stdout, the measured pitch range per voice, the pitch-class histogram, the
**colour assignment table**, the predicted `collide` count, and the
`BANDTOP`/`BANDROWS` the measured range needs.

- [ ] Map each spelled pitch to `(p, accidental)` — the spelling decides the
      staff position, so `Eb4` and `D#4` are different positions.
- [ ] Encode: `$00` rest, `$FF` hold, else `bits0-4 = p+1`,
      `bits5-6 = accidental` (0 none, 1 sharp, 2 flat), `bit7 = hollow`
      (set when the note's written duration is 4 sixteenths or more).
- [ ] Assign colours: the nine strong colours (2, 3, 4, 5, 7, 8, 10, 13, 14)
      to the nine most frequent pitch classes, the three weak ones
      (9 brown, 12 medium gray, 15 light gray) to the three rarest, ties
      broken by pitch-class order. Emit the table as a 12-byte
      `pcolor` array in `notes.inc` **and** as a markdown table for SPEC §7.
- [ ] Predict `collide`: count sixteenths where two voices land in the same
      `(row, half)`, and separately the same `row` with different halves
      (those are the both-halves glyph, not a collision).
- [ ] **Verify:** `python3 demos/fugue/tools/genmusic.py --check` re-derives
      `notes.inc` in memory, compares it byte-for-byte with the committed
      file, and exits non-zero on any difference.

## Task 3: the charset

**Files:** create `demos/fugue/tools/charset.txt`; generate
`demos/fugue/chars.inc`.

**Produces:** 48 hires glyphs for codes 32-79, in the map above, under label
`glyphs`.

- [ ] Author the sheet as 48 named 8-row hires blocks of `.#`, in code order,
      with the blank at 32 and the staff line (`%11111111` at pixel row 5) at 33.
- [ ] Heads are 6 px wide, pixel bits 1-6, 4 px tall in their half. On a line
      row the filled head's pixel row 5 is `%11111111`; the hollow head's is
      `%11000011`, so the line ends show and the head reads as open.
- [ ] Accidentals are 6 px tall, upper-aligned (pixel rows 0-5) or
      lower-aligned (rows 2-7), 4 px wide in bits 2-5, with the staff line
      ORed in on line rows.
- [ ] **Verify:** `.venv/bin/c64 charset encode demos/fugue/tools/charset.txt
      --hires --first-code 32 --label glyphs -o demos/fugue/chars.inc --json`
      reports exactly 48 glyphs.

## Task 4: the glow sprite

**Files:** create `demos/fugue/tools/glow.txt`; generate
`demos/fugue/sprites.inc`.

**Produces:** one 24×21 hires sprite, `sprite0`, whose lit band is sprite
rows 7-13 — that is what makes `sprite Y = 74 + 4*p` centre it on the note.

- [ ] **Verify:** `.venv/bin/c64 sprite encode demos/fugue/tools/glow.txt
      --hires -o demos/fugue/sprites.inc --json` reports one sprite, and
      rows 0-6 and 14-20 are all zero.

> **Execution notes.** Tasks 1-13 below are the plan as written before any
> code existed. Where the running machine corrected it, the correction is
> recorded inline under the task, because "a step is done when the
> observation the plan named for it is read back off the running machine".

## Task 5: skeleton, charset install, static staff

**Files:** create `fugue.s`, `vars.s`, `staff.s`.

**Consumes:** `chars.inc`, `notes.inc` (for `pcolor`, `posmidi`).
**Produces:** `init`, `tick` (an `rts`-terminated stub), `irq`, every label
in SPEC §9, `drawscreen`, `drawcol`, `rowlo`/`rowhi`/`crowlo`/`crowhi`,
`bgcode`, and the `BANDTOP`/`BANDROWS` equates set from Task 2's output.

- [ ] `$0801` load address, `EXEHDR` stub, code at `$080D` — the skeleton in
      asm/SKILL.md, unmodified except for the code it wraps.
- [ ] `CHARS` segment = `.res 32*8` then `.include "chars.inc"`, so glyph 32
      lands at `$2100`. The ROM charset is **not** copied: every code outside
      32-79 is deliberately blank, which is why there is no `CHAREN` dance
      and no `sei` around a copy. Say so in a comment at the segment.
- [ ] `.assert (__BSS_LOAD__ + __BSS_SIZE__) <= $2000, error, "BSS ran into
      the charset"`.
- [ ] `init`: `$D020`/`$D021` = 0; fill all 1000 screen cells with 32 and
      colour with 1; `$D011` = `$1B`; `xsc` = 6 → `$D016`; `$D018` = `$18`;
      zero every var (BSS is not in the `.prg` — `.res` bytes load as
      whatever was in RAM); `drawscreen`; install the IRQ.
- [ ] `irq`: `lda #$01 / sta $D019` first, `cld`, `jsr tick`, `sta $D019`
      again, `jmp $EA31`. Install with `sei`, `$DC0D` ← `$7F`, read `$DC0D`
      to clear, save and repoint `($0314)`, `$D011` bit 7 clear, `$D012` ←
      251, `$D01A` ← `$01`, `$D019` ← `$01`, `cli`.
- [ ] `drawcol` takes `dcol` (16-bit score column) and `dscr` (0-39) and
      writes `BANDROWS` screen cells and their colour cells. At this task it
      draws only the background and the clefs.
- [x] **Verify:** `c64 run demos/fugue/fugue.s`, `c64 until tick --count 30`,
      then `c64 screen --codes` shows 33 across every staff-line row and 32
      across rows 0-3 and 19-24, and `c64 mem read '$D018' 1` reads `$19`.

**Corrected by the machine.**

- **The band is rows 5-19, `LADTOP = BANDTOP = 5`**, not 4. Every row further
  down raises the last band row's badline deadline by 8 rasters, and Task 7
  needed them. Rows 5-19 is also dead centre of the 25-row screen.
- **Variables live in `DATA`, not `BSS`** — `demos/invaders/vars.s`'s
  convention and its reason: BSS is not in the `.prg`, so `.res` there loads
  as whatever was in RAM.
- **The verification above does not anchor where it says it does.** Run first
  and `until` afterwards and the machine free-runs at warp in the gap: this
  read `frame = 3774`, not 30. Arm `c64 break add tick` **before** `c64 run`,
  take the first `wait --break` to reach frame 0, and only then step. Inside
  `c64 test run` the runner arms before the program gets going, so its first
  `until tick` does land on frame 0.
- **A static `HOLD` of 150 frames had to be added.** The clefs are drawn at
  the head of the score and the score scrolls; at frame 30 they were already
  off the left edge. `sf = frame - HOLD` became the scroll clock.

## Task 6: the score grid in `drawcol`

**Files:** modify `staff.s`.

**Consumes:** `notes1/2/3`, `posmidi`, `pcolor`, the glyph map.
**Produces:** a `drawcol` that renders any score column, and `rendk`.

- [ ] `SC0 = 69`, `NOW = 10`. `offset = dcol - SC0`; `k = offset >> 1`; even
      offset is the accidental/bar-line slot, odd is the head slot.
- [ ] Bar line on `k mod 16 == 0`, filling screen rows 6-16; an accidental in
      the same column overwrites its own cell only.
- [ ] Head cells: pick the glyph by `(half, hollow, online)`; if the cell
      already holds a head this column, replace it with the both-halves glyph
      and increment `collide` only when the two are in the *same* half.
- [ ] Colour: white for staff, line, bar and clef cells; `pcolor[pitchclass]`
      for a head and for the accidental that modifies it. Lower-numbered
      voice wins a shared cell.
- [ ] Ledger positions get code 33 instead of 32 when occupied.
- [ ] **Verify:** with the program stopped at `tick`, `c64 mem write dcol …`
      then `c64 call drawcol` for the score column of a known bar line, and
      `c64 screen --codes` shows 58/59 down rows 6-16 of column `dscr`.
      (A `call` ends the run — reload with `c64 run` afterwards.)

## Task 7: the scroll

**Files:** create `scroll.s`; modify `fugue.s`.

**Produces:** `shiftband`, and `tick`'s frame order (SPEC §5): `$D016`,
`musfetch`, `glowtick`, `muswrite`, `shiftband` + `drawcol`. At this task
`musfetch`/`glowtick`/`muswrite` are `rts` stubs.

- [ ] `xsc = 6 - 2*(frame & 3)`, written straight to `$D016` (bits 3 and 4
      clear = 38 columns, no multicolour).
- [ ] `shiftband`: one linear move, `BANDROWS*40` screen bytes interleaved
      with the same count of colour bytes, unrolled by 8, top-down. Column 39
      is left wrong on purpose; `drawcol` overwrites it.
- [ ] On `(frame & 3) == 0` and `frame > 0`: shift, `inc shifts`, then
      `drawcol` with `dcol = shifts + 39`, `dscr = 39`. Record `shiftline`
      and `tickend` high-water marks on these frames only.
- [x] **Verify:** four consecutive `c64 until tick --count 1` stops read
      `xsc` = 6, 4, 2, 0 and `shifts` rising by exactly 1 across the 0→6
      wrap; then after `--count 600`, `c64 mem get tickend 1` is below 195.
      If it is not, apply SPEC §5's remedy ladder in order and re-measure.

**It was not, and the remedy ladder was the wrong ladder.** First measurement:
`shiftband` 13,368 cycles, `drawcol` 2,776, `tick` max **18,155 — more than a
whole 17,095-cycle frame** — and `tickend` 252 against a 195 deadline.

Neither listed remedy was needed, and one arithmetic fact ruled out the whole
class the plan was reasoning inside: at 15 rows the memmove needs at least
`600 x 18 = 10,800` cycles of instructions alone, so *no* tuning could fit the
215-raster window an arm-in-the-top-border design leaves. What fixed it:

1. **Arm at raster 204, not 251.** Once the VIC has latched a row at its
   badline, later writes cannot affect the current frame — so the shift may
   start the moment the *last* band row has latched (`51 + 8*19 = 203`) and
   use the bottom and top borders together: 263 lines instead of 215.
2. **Move `drawcol` to the frame after the shift.** Column 39 is never
   visible in 38-column mode — it lies inside the hidden right 9 pixels at
   every `xsc` the demo uses — so it has four frames of slack and no raster
   deadline at all.
3. **Chunk the move at page boundaries** (22.3 → 21.4 cycles a cell).

Measured after: `tickend` **178**, `shiftline` **177**, deadline 203 — and
`frame` reads exactly 900 after `until tick --count 900`, so no frame is
dropped. `c64 profile tick --samples 32`: max 15,625, min 864.

Two build failures worth recording, both ca65 traps the skill names:
`ldy nmidi,y` is an illegal addressing mode (**there is no `LDY abs,Y`** —
route through A), and one `bne` outgrew ±127 bytes, fixed mechanically by
`c64 build … 2>&1 | python3 skills/6502-assembly/references/fix-branch-range.py`.

## Task 8: the sequencer

**Files:** create `music.s`; modify `fugue.s`.

**Produces:** `musinit`, `musfetch`, `muswrite`, `sidwr` (X = register offset
0-24, A = value; writes `$D400,x` and `sidshadow,x`), and the `state`,
`sixteenth`, `bar`, `beat`, `slot`, `vNnote`, `vNpos`, `vNidx` bytes.

- [ ] `musinit`: zero all 25 SID registers first (hardware.md: a left-over
      gate bit blocks a new note), then ADSR and waveform per SPEC §10,
      `$D417` = `$A4`, `$D418` = `$1F`, `$D416` = `$70`; read `$02A6` and
      copy the NTSC or PAL frequency table into the `freqlo`/`freqhi` RAM
      arrays.
- [ ] `musfetch`, on frames where `frame >= 240` and `(frame & 7) == 0`:
      advance `sixteenth`, derive `bar`/`beat`/`slot`, and for each voice read
      `notesN[sixteenth]` — `$00` release, `$FF` hold, else decode `p` and the
      accidental, set `vNpos`, `vNnote = posmidi[p] ± 1`, bump `vNidx`.
- [ ] `muswrite`: for each voice that attacked this frame, write frequency
      lo/hi, then **gate off and gate on within the same call** — the
      once-per-frame sampler must never see the gate low (SPEC §10).
- [ ] `state`: 1 while `frame < 240`, 2 during play, 3 once `sixteenth`
      reaches 495 and the final chord has released; shifting stops at state 3.
- [ ] **Verify:** `c64 until tick --count 250`, then `c64 mem get sidshadow 25`
      shows non-zero frequency bytes and `$41`/`$21`/`$11` control bytes for
      the voices the arrangement says are sounding at sixteenth 1.

## Task 9: PWM and the filter sweep

**Files:** modify `music.s`.

**Produces:** `pwmval`, `cutoff`, both written every frame.

- [ ] `pwmval` a 128-frame triangle over `$0400`-`$0C00`, step 16, to
      `$D402`/`$D403` through `sidwr`.
- [ ] `cutoff` held at `$70` except across `PEDAL`'s bars, where it descends
      to `$10` over two bars and returns over two, to `$D415`/`$D416`.
- [ ] **Verify:** sample `pwmval` with `width: 2` at two `until tick` stops 20
      frames apart and confirm it moved; `c64 mem get cutoff 2` inside and
      outside the pedal bars differs.

## Task 10: the sprite backlight

**Files:** create `glow.s`; modify `fugue.s`, `init`.

**Produces:** `glowtick`, `sprx0..2`, `spry0..2`, `sprage0..2`, `sprcol0..2`.

- [ ] `init`: sprite pointers `$07F8`-`$07FA` ← `$A0`; `$D027`-`$D029` ← 6,
      11, 9; `$D01B` ← `$07`; `$D010` ← 0.
- [ ] `glowtick`: per voice, `x = 102 - 2*sprage`, `y = 74 + 4*vNpos`,
      enable in `$D015` while `vNnote != 0` and `sprage <= 39`, disable
      otherwise. `sprcol` = `NOW` less 1 while `(frame & 7) >= 4`.
- [x] **Verify:** at one `until tick` stop, `c64 sprite status` X/Y for each
      enabled sprite equal `sprx*`/`spry*`, and `spry* == 82 + 4*vpos`.

**Corrected by an evidence PNG, not by an assertion.** `GLOWY0` was a
hardcoded 74 — right for `LADTOP = 4`. When Task 7 moved the band down a row
the constant did not follow, and every glow sat 8 rasters above its note
head. Nothing then written would have caught it; the screenshot did. It is
now `GLOWY0 = 42 + 8 * LADTOP`, derived. Verified after: `spry` = 122/150/182
for `vpos` = 10/17/25, and `$D000-$D005` = `50 7a 50 96 50 b6`, matching.

## Task 11: the regression test

**Files:** create `demos/fugue/test.yaml`.

- [ ] Every criterion in SPEC §12 that a stopped machine can settle: the mode
      registers, `$D018` = `$19`, staff codes, the `xsc`/`shifts` walk,
      a head cell's colour masked `and: "$0f"`, `$D000`-`$D005` against the
      published sprite bytes, `rendk - sixteenth == 15`, `tickend` < 195,
      `collide` at Task 2's predicted value, and the SID shadow control bytes.
- [ ] 16-bit counters are sampled with `width: 2`; climbing counters use
      `at_least`, never `equals`; no `wait:` step ever follows an `until:`.
- [ ] `areas:` carries the two `--area` strings.
- [x] **Verify:** `.venv/bin/c64 test run demos/fugue/test.yaml` passes every
      step. **99 steps, PASS in 19 s.**

Two things the format made possible that are worth copying: a register is
compared against the byte the program published for it with
`sample: {mem: sprx+0} / assert: {mem: "$D000", unchanged: x0}` — `unchanged`
is equality against a sample, so it compares two *locations*, which no
literal comparator can do. And `symbol+offset` addresses one element of a
three-byte per-voice array.

## Task 12: screenshot evidence

**Files:** create `demos/fugue/tools/evidence.sh`; populate
`demos/fugue/evidence/`.

- [ ] One `run`, then `until tick --count N` before every capture, and **one
      extra tick immediately before each `screen --png`** — the capture
      returns the emulator's rolling scanline buffer, not a re-render.
- [ ] The nine PNGs of SPEC §11, `--scale 2 --border`.
- [ ] **Verify:** `bash demos/fugue/tools/evidence.sh` writes all nine and
      exits 0; run it twice and confirm the `until`-anchored shots are
      byte-identical.

## Task 13: audio evidence

**Files:** create `demos/fugue/tools/genscore.py`,
`demos/fugue/tools/audio-evidence.sh`; populate `evidence/audio/`.

- [ ] `genscore.py` models the player **one frame at a time** — the note a
      once-per-frame sampler would read on each frame, including gate-down
      frames — then run-length encodes. Never write a score from a
      transcription.
- [ ] Four windows: the three exposition entries and the pedal point, 10-15
      emulated seconds each. Park at `target - lead_in`, capture with
      `--strict` and `--ref`, and if `lead_in_frames` moved, re-score the
      existing log with `c64 audio report` rather than re-capturing.
- [ ] **Verify:** all four `report.md` files carry verdict PASS, none reports
      `nothing_played`, and `bash demos/fugue/tools/audio-evidence.sh` exits 0.

## Task 14: the improvement loop

**Files:** create `demos/fugue/AUDIT.md`.

- [ ] Iterate: evaluate every SPEC §12 criterion PASS/FAIL from the running
      machine (never from reading source); review the build (cycle-count the
      shift against the sequencer, audit the charset at 1× scale, remove dead
      code); then judge it as a viewer and a listener — does the score read as
      music, does it sound like the C minor fugue; fix every FAIL; re-verify
      each fix on the machine.
- [ ] Read each piano roll against the screen at the same frames and record
      the cross-check per capture, not as a summary.
- [ ] **Verify:** the last iteration in `AUDIT.md` ends with every criterion
      PASS and a review finding nothing worth fixing.

## Task 15: ship it

- [ ] `.venv/bin/c64 package demos/fugue/fugue.s -o demos/fugue/fugue.d64
      --title "FUGUE IN C MINOR" --area 'CHARS=$2000:$0800'
      --area 'SPRITES=$2800:$0100'`.
- [ ] **Verify:** the reported `run` command names `-ntsc`, and
      `c64 test run demos/fugue/test.yaml` still passes afterwards (packaging
      rewrites `fugue.lbl`).
