# Fugue No. 2 in C Minor — specification

J. S. Bach's Fugue No. 2 in C minor, BWV 847, played on the SID's three
voices while its notated score scrolls right-to-left across a custom-charset
grand staff, in time with the music.

Everything below is a decision plus the fact it rests on. Hardware facts are
cited to `skills/c64-development/references/hardware.md` (`hardware.md`),
`references/memory-maps.md` (`memory-maps.md`),
`references/audio-verification.md` (`audio-verification.md`),
`references/cookbook.md` (`cookbook.md`), `skills/6502-assembly/SKILL.md`
(`asm/SKILL.md`) and `docs/cli.md`.

Machine: **NTSC** (`c64`, the toolset default). 60 fps, 17,095 cycles per
frame, 263 raster lines, clock 1,022,727 Hz (hardware.md, "Frame budget";
audio-verification.md, "Clocks and frame rates").

---

## 1. The one clock

Everything in this demo is a function of one 16-bit frame counter, `frame`,
incremented once per raster IRQ. Nothing else keeps time.

The demo opens with a **static hold** of `HOLD = 150` frames during which
nothing moves; `sf = frame - HOLD` is the scroll clock, and every derivation
below reads `sf`, never `frame`. Subtracting a constant leaves the one-clock
property intact.

| Quantity | Derivation |
|---|---|
| Fine scroll `$D016` bits 0-2 | `6 - 2*(sf & 3)` → 6, 4, 2, 0 |
| Column shift | on frames where `(sf & 3) == 0`, `sf > 0` |
| Entering column rendered | on frames where `(sf & 3) == 1` |
| Sixteenth-note index | `(sf - 88) / 8`, once `sf >= 88` |
| Note attack | on frames where `(sf & 7) == 0`, `sf >= 88` |

So the screen advances 2 pixels per frame, 8 pixels (one character column)
every 4 frames, and 16 pixels (two columns) every 8 frames — and 8 frames is
one sixteenth note. **The scroll offset counter *is* the sixteenth-note
subdivision counter.** Scroll/sequencer drift is not something this design
avoids by care; it is unrepresentable, because there is one counter and both
consumers read it. Criterion 3 measures that rather than assuming it.

Quarter note = 32 frames = 0.533 s = **112.5 BPM**. 31 bars × 16 sixteenths ×
8 frames = 3,968 frames = **66.1 s** of music, after `HOLD + LEADIN` = 150 +
88 = **238 frames (4.0 s)** of silence.

Two different things need that silence and they need it in different forms.
Arming an audio capture costs emulated frames before log frame 0
(audio-verification.md, "Give the program a silent lead-in": "arming still
consumed about **84 frames (1.4 s)**"), and any silence covers that. The
clefs need the *static* half specifically: they are drawn at the head of the
score and the score scrolls, so on the first build they were gone twelve
frames in — measured, at frame 30 the picture had already advanced seven
columns and both clefs were off the left edge. `HOLD` is what puts the
staves, the clefs and the first bar line in front of the reader before
anything moves, and it is what criterion 1 photographs.

The demo never loops, so neither part of the lead-in can reappear mid-piece.

---

## 2. Screen mode and memory map

Text mode, custom character set, screen and border black.

| Register | Value written | Reads back as | Why |
|---|---|---|---|
| `$D011` | `$1B` | `$1B` | Standard text, 25 rows, DEN on. Bit 7 is the raster MSB, which would normally make the readback vary — but VICE picks up a monitor command at the next vsync, so a stopped machine is always near the top of the frame and bit 7 always reads 0 (audio-verification.md, "Known facts": "`$D012` reads 12 at every halt, forever"). Measured `$1b` on this session. |
| `$D016` | `xsc` (0-6, even) | `$C0 \| xsc` | 38-column mode (**bit 3 clear**) + fine scroll. Bits 5-7 are unused and read as 1 — assert masked with `and: "$0f"`. |
| `$D018` | `$18` | `$19` | Screen `$0400` (high nybble 1) + charset `$2000` (`$2000/$0800 = 4`, shifted left one = `$08`). Bit 0 is unused and reads as 1 (cookbook.md, "Custom character set": "**It does not read back as `$1C`**"). Measured `$19` live. |
| `$D01B` | `$07` | `$07` | Sprites 0-2 **behind** character data. |
| `$D015` | per frame | — | Bit v set while voice v+1 is sounding and its head is on screen. |
| `$D020` | `0` | `$F0` | Border black; 4-bit register (hardware.md). |
| `$D021` | `0` | `$F0` | Background black. |
| `$D01A` | `$01` | — | Raster interrupt source enabled. |
| `$DC0D` | `$7F` | — | CIA1 timer IRQ off — one interrupt source, or the raster high-water mark is fiction (cookbook.md, "Per-frame raster budget"). |

**38-column mode is the load-bearing bit and it is a *cleared* bit.** With
`$D016` bit 3 clear the VIC blanks the leftmost 7 and rightmost 9 pixels of
the display window, which is what hides the character column entering at the
right edge. `demos/la-galaxia/AUDIT.md:40` records the failure mode from the
other direction — an uninitialised `$D016` shadow wrote 0 every frame and put
a band into 38-column mode unintentionally — so `xsc` is initialised in
`init` before the first IRQ, and criterion 2 reads it back.

### Memory map

| Range | Contents | Constraint |
|---|---|---|
| `$0801-$080C` | BASIC stub, `10 SYS 2061` | asm/SKILL.md, "Why SYS 2061" |
| `$080D-$1FFF` | `CODE` + `RODATA` + `DATA` + `BSS` | must end below `$2000`; enforced by `.assert` |
| `$0400-$07E7` | Screen RAM | left at `$0400`, but not for the reason the cookbook gives — see below |
| `$07F8-$07FF` | Sprite data pointers | screen + `$3F8` (memory-maps.md) |
| `$2000-$27FF` | Custom charset (2 KB) | `--area 'CHARS=$2000:$0800'` |
| `$2800-$28FF` | Sprite blocks (4 × 64) | `--area 'SPRITES=$2800:$0100'`; glow = block `$A0` (`$2800/64 = 160`) |
| `$D800-$DBE7` | Color RAM | never moves (memory-maps.md) |

`$2000` and `$2800` are legal charset/sprite homes in VIC bank 0; `$1000`
and `$1800` are not, because the character ROM's **4 KB** image covers both
of those 2 KB bases and `$1800` fails silently by drawing the ROM's lowercase
glyphs (memory-maps.md; cookbook.md, "Custom character set"). Bank 0 is left
at its power-on setting, so `$DD00` is never touched.

The screen stays at `$0400` because this demo has no reason to move it — not
because the toolset requires it. Two references say it does: cookbook.md:2523
("the toolset's screen reader assumes `$0400`") and hardware.md:214 (the same
sentence). **Both are wrong, measured on this session:** with `$D018` set to
`$78` and marker bytes at `$0400` and `$1C00`, `c64 mem read '@0,0'` returned
`1c00: 05` and `c64 screen --codes` read the relocated screen. That agrees
with `docs/graphics-and-sprites.md` §3 and `SKILL.md`:209, which both say
reads follow `$DD00`/`$D018`. Filed in `docs/todo.md`; noted here because the
double-buffer fallback in §5 would have depended on it.

The link is `c64 build --area 'CHARS=$2000:$0800' --area 'SPRITES=$2800:$0100'`.
Every area below the last one is filled to its declared size, so the `.prg`
spans `$0801-$28FF` — about 8.4 KB — whatever the code actually holds
(docs/cli.md, `c64 build`). The build carries the cookbook's ceiling check:

```asm
.import __BSS_LOAD__, __BSS_SIZE__
.assert (__BSS_LOAD__ + __BSS_SIZE__) <= $2000, error, "BSS ran into the charset"
```

---

## 3. Staff layout

**One grand staff**, because BWV 847 is keyboard music and the grand staff is
how it is printed. Voices 1 and 2 (soprano and alto) read on the treble
staff, voice 3 (bass) on the bass staff. Three separate per-voice staves were
rejected: they would never let two voices collide, but they cost 19-21 rows
to shift (over the frame budget, §5) and they hide the vertical harmony,
which in a fugue is half of what a reader is looking at.

**A diatonic step is 4 pixels — half a character cell — and a staff line is
every 8 pixels, one per character row.** Within a cell, the **upper half**
(pixel rows 0-3) is a space position and the **lower half** (pixel rows 4-7)
is a line position, with the staff line itself drawn at pixel row 5.

This is what makes the layout fit. It also makes note heads 4 px tall, which
is roughly one staff space — the correct proportion for engraved notation.

### The position ladder

Positions are numbered `p = 0` at the top, increasing downward, and anchored
on `LADTOP` — the screen row of positions 0 and 1:

```
row = LADTOP + (p >> 1)     half = p & 1        (0 = upper, 1 = lower)
```

`LADTOP = 5`, so the ladder occupies screen rows 5-19: the treble staff on
rows 7-11, middle C's ledger on row 12, the bass staff on rows 13-17, and one
ledger row above and below each staff. That is dead centre of the 25-row
screen, and it is also the cheapest place to put it — every row further down
raises the last band row's badline deadline by 8 rasters, which §5 spends.

| p | row.half | pitch | | p | row.half | pitch |
|--:|---|---|---|--:|---|---|
| 0 | 5.u | D6 | | 15 | 12.l | **C4** (ledger) |
| 1 | 5.l | C6 (ledger) | | 16 | 13.u | B3 |
| 2 | 6.u | B5 | | 17 | 13.l | **A3** (bass line 5) |
| 3 | 6.l | A5 (ledger) | | 18 | 14.u | G3 |
| 4 | 7.u | G5 | | 19 | 14.l | **F3** (line 4) |
| 5 | 7.l | **F5** (treble line 5) | | 20 | 15.u | E3 |
| 6 | 8.u | E5 | | 21 | 15.l | **D3** (line 3) |
| 7 | 8.l | **D5** (line 4) | | 22 | 16.u | C3 |
| 8 | 9.u | C5 | | 23 | 16.l | **B2** (line 2) |
| 9 | 9.l | **B4** (line 3) | | 24 | 17.u | A2 |
| 10 | 10.u | A4 | | 25 | 17.l | **G2** (bass line 1) |
| 11 | 10.l | **G4** (line 2) | | 26 | 18.u | F2 |
| 12 | 11.u | F4 | | 27 | 18.l | E2 (ledger) |
| 13 | 11.l | **E4** (treble line 1) | | 28 | 19.u | D2 |
| 14 | 12.u | D4 | | 29 | 19.l | C2 (ledger) |

Rows **6-10** carry the treble staff, rows **12-16** the bass staff, and the
ladder runs unbroken through row 11 — where the lower half is middle C on its
own ledger line, exactly as printed. The scrolled band is **rows 4-18, 15
rows**; rows 4-5 and 17-18 exist to carry the ledger positions above the
treble and below the bass. Rows 0-3 and 19-24 are never touched and stay
black.

`posmidi[p]`, the natural MIDI number of each position, is a 30-byte table:
D6=86 down to C2=36 in diatonic steps. The sounding pitch is
`posmidi[p] + accidental_offset`.

### Y coordinate identity

A sprite whose Y register is `V` shows its first row on raster `V+1`, and
text row R's first raster is `51 + 8*R` (hardware.md, "Sprites" — measured,
and the invaders demo's off-by-one is recorded there). Centring a glow whose
lit band sits at sprite rows 7-13 on position `p` gives

```
sprite Y = 42 + 8*LADTOP + 4*p          = 82 + 4*p at LADTOP = 5
```

which is why the ladder is numbered this way: `8*(p>>1) + 4*(p&1) == 4*p`.
Y ranges 82 (D6) to 198 (C2), inside the legal 50-249. **It is derived in the
source, not written down**: the first build hardcoded the `LADTOP = 4` value
74, the band later moved down one row to buy raster budget, the constant did
not follow, and every glow sat 8 rasters above its note head — caught in an
evidence PNG, invisible to every assertion written at that point.

---

## 4. Charset design

44 glyphs, hires, authored as an ASCII sheet in `tools/charset.txt` and
converted with `c64 charset encode --hires` (docs/cli.md). Head columns are
pixel bits 1-6; the staff line is all 8 bits of pixel row 5, so lines join
across columns.

| Codes | Glyphs |
|---|---|
| 32 | blank (all zero) — the empty cell, and still a space to `c64 screen` |
| 33 | staff line / ledger line |
| 34-49 | note heads: {upper, lower, both} × {filled, hollow} × {on a line, not} (16) |
| 50-57 | accidentals: {sharp, flat} × {upper-aligned, lower-aligned} × {on a line, not} (8) |
| 58-59 | bar line, {on a line, not} (2) |
| 64-79 | treble clef (2 cols × 5 rows) and bass clef (2 cols × 3 rows) (16) |

Every code is below 96 and outside 128-154. That is deliberate: codes **32,
96 and 224 decode to a blank** in `c64 screen`, and **129-154 are reverse
A-Z**, so a charset patching 128+ turns every reverse-video line into game
glyphs (cookbook.md, "Custom character set"; SKILL.md, "Common pitfalls").
Only code 32 is used from that set, and it *is* our blank, so nothing is
hidden. Tests assert with `c64 screen --codes` and `mem read`, never on
decoded text.

**A hollow head interrupts the staff line; a filled head does not.** On a
line row the filled lower head's pixel row 5 is `%11111111` (head plus the
line's outer two bits), while the hollow head's is `%11000011` — outline and
line-ends only, so the head reads as white-centred the way engraving draws
it.

**Deliberate omissions: no stems, no beams, no flags, no key signature.**

- Stems and beams are omitted on legibility grounds: a head is 4 px tall, a
  stem would be a 1-px column over one to three cells, and beams span
  columns, which would end the renderer's per-column independence (§6) for a
  mark that adds nothing a reader of this display needs. Duration is carried
  instead by **head shape**: filled for an eighth or shorter, hollow for a
  quarter or longer.
- **There is no key signature, and every altered note carries its own
  accidental, every time it occurs.** This is a departure from engraving
  convention, where an accidental persists to the end of the bar and the key
  signature covers E♭/A♭/B♭ silently. It is chosen because the display
  scrolls: a key signature is printed once at the head of a system, and this
  score has no systems — it would scroll off after four seconds and the
  reader would be left inferring flats from a symbol that is no longer on
  screen. Spelling every alteration satisfies the prompt's criterion
  literally ("if a note sounds a semitone away from the staff position it
  occupies, the symbol saying so must be on screen") with no bar-scoped
  state in the renderer. The cost is visual density: in C minor roughly a
  third of all note heads will carry a flat.
- Natural signs are therefore never drawn — with no key signature, an
  unmarked head *is* the natural.

Clefs are drawn from custom characters, as required, at the head of the
score. They occupy score columns 1-2 and scroll away with the music once it
starts, the way a printed clef leaves your field of view as your eye moves
along the system. They are on screen for the whole 4-second lead-in, which is
what criterion 1 photographs.

---

## 5. The scroll mechanism

### Mechanism

`$D016` bits 0-2 hold a 0-7 pixel fine scroll; the display shifts right as
the value rises. The demo counts it **down** — 6, 4, 2, 0 — moving the
picture 2 px left per frame, and on the frame after 0 it shifts screen and
color RAM one character column left and resets `xsc` to 6. Continuity check:
a cell at screen column `c` with `xsc = 0` has its left edge at
`24 + 8c`; after the shift it is column `c-1` with `xsc = 6`, left edge
`24 + 8(c-1) + 6 = 24 + 8c - 2` — exactly 2 px further left.

The shift moves columns 0-38 ← 1-39 for both screen RAM and color RAM across
**rows 4-18 only**; rows 0-3 and 19-24 are black and never move. Column 39 is
then written fresh by the column renderer (§6).

### Budget, measured

`c64 profile shiftband --samples 4` reads **12,856 cycles** — 600 cells at
21.4 cycles each, against an 18-cycle instruction floor (`lda abs,x` +
`sta abs,x`, twice) plus 1.4 of loop overhead and about 1,075 of badline DMA
that `profile` counts as wall cycles. `c64 profile tick --samples 32` reads
**15,625 max** over 864 min: bimodal, exactly as the shift/no-shift split
predicts, and inside the 17,095-cycle frame.

Three things got it there, and the first two were forced by measurement
rather than chosen:

1. **The interrupt is armed at raster 204, not in the top border.** Once the
   VIC has latched a text row's matrix and colour on its badline, later
   writes to that row cannot affect the current frame — so the shift may
   begin the moment the *last* band row has latched, at `51 + 8*19 = 203`,
   and prepare the next frame across the bottom border and the top border
   together. That is 263 raster lines of room instead of the 215 an
   arm-in-the-top-border design gets. The first build armed at 251 and read
   `tickend = 227` against a 203 deadline; moving the arm to 204 was the
   single change that fixed it.
2. **`drawcol` runs on the frame *after* the shift, and that is free.**
   Screen column 39 is never visible in 38-column mode: the mode hides the
   rightmost 9 pixels (X 335-343), and column 39 spans X 336-343 at `xsc` 0
   through 342-349 at `xsc` 6 — entirely inside that strip at every value the
   demo uses. The column reaches the eye only after the next shift moves it
   to column 38, so it has a whole four-frame cycle of slack, and its ~2,700
   cycles leave the shift frame's critical path.
3. **The move is chunked at page boundaries.** `lda base+1+i,x` costs an
   extra cycle whenever the address crosses a page; one 256-cell block based
   at `$04C9` crosses on most reads. Splitting at `$0500`/`$0600`/`$0700`
   took 22.3 cycles a cell down to 21.4.

The program publishes the outcome rather than trusting the arithmetic:
`shiftline` is `$D012` the instant `shiftband` returns and `tickend` is
`$D012` at `tick`'s exit, both high-water marks kept over shift frames only.
Measured after 900 frames: **`shiftline` 177, `tickend` 178, against a
deadline of 203** — 25 raster lines in hand. `frame` read exactly 900 after
`until tick --count 900`, so no frame is being dropped.

**Why one frame and not spread across four.** Spreading the shift would put
rows one character out of step with each other for part of every cycle, and
vertical alignment between rows is precisely what this display asserts: notes
in the same column sound on the same sixteenth. A skew of one column between
the treble and bass staff would be the demo showing a lie. So the shift is
atomic within a frame, and the frame budget is what has to give.

**What was ruled out, and why it is recorded.** At 15 rows a single-buffer
memmove needs at least `600 x 18 = 10,800` cycles of instructions alone, so no
amount of tuning could have met the 215-raster window the original raster-251
design left. That is a proof, not a guess, and it is what sent the design to
the raster-204 arm rather than to either fallback. Two fallbacks were costed
and are not built:

- **A display list** — keep the marks (heads, accidentals, bar lines, clefs)
  and erase/redraw each at its new column instead of moving the whole band.
  Costed at ~70 cycles a mark: about 4,300 cycles in the typical case but
  **9,900 in the worst** (three voices attacking with accidentals across all
  twenty visible head columns), which is barely better than the memmove for
  substantially more machinery and a data-dependent budget. Rejected on the
  worst case.
- **Double-buffering the screen** at `$1C00`, spreading the screen half over
  four frames and flipping `$D018` at the wrap; colour RAM cannot be
  double-buffered, so its half stays atomic. Costed at ~10,600 cycles on the
  wrap frame. Not needed once the arm moved.

### The interrupt

A raster IRQ through `($0314)`, following cookbook.md's **"Raster event
chain"** recipe (live-tested as `asm-raster_chain`) rather than its jiffy
"IRQ wedge", because this demo needs a known scanline. One event per frame,
armed at raster **204** (§5). With a single event there is no next line to
arm, so the recipe's "compare the line you just armed against the live
raster" loop does not apply — `$D012` is re-armed to the same 204 every
frame, and 204 < 256 keeps `$D011` bit 7 clear as the recipe requires.

- Entry acknowledges with `lda #$01 / sta $D019` — "ack first: an unacked
  raster IRQ re-fires the instant the RTI runs" (cookbook.md).
- `cld` on entry: "an IRQ does not clear D on the NMOS 6502" (cookbook.md).
- CIA1 timer IRQ is off (`$DC0D` ← `$7F`), so there is exactly one interrupt
  source.
- **Exit is through `$EA31`, not `$EA81`.** The chain recipe exits `$EA81`
  and says so plainly: "While the chain owns the IRQ the jiffy clock and the
  keyboard scan are dead". This demo wants the jiffy alive, because
  `lead_in_frames` "is measured from the KERNAL jiffy at `$A0-$A2` … a player
  that takes the IRQ over freezes it, and null then means 'not measured'"
  (audio-verification.md). Since there is one event per frame there is no
  following event for the keyboard scan's ~15 lines of jitter to disturb.
- The handler is a **thin wrapper around a `tick` subroutine ending in
  `rts`**, so `c64 profile tick` can price it: "A fake JSR needs a callable
  entry ending in `RTS`; a raster handler entered through `$0314` has neither
  … put the whole per-frame job in a subroutine ending in `rts`"
  (docs/cli.md, `c64 profile`). `tick` is bimodal — shift frames and
  ordinary frames — so it is profiled with `--samples 32`, not once.

**The cookbook has no smooth-scrolling recipe.** Verified: `$D016` occurs
twice in `cookbook.md`, both inside "Multicolor bitmap" turning on bit 4, and
there is no heading mentioning scrolling. The register description is one
line in hardware.md ("`$D016` — multicolor bit 4, 38/40-column bit 3,
horizontal scroll 0-2"). Everything in this section is new material; the
in-repo precedent for a banded `$D016` shadow is `demos/la-galaxia/vars.s`.

---

## 6. The score grid and the column renderer

### Grid

**Two character columns per sixteenth note.** The first is the
accidental/bar-line slot, the second the note-head slot. Two columns is what
buys accidentals a cell of their own "beside the note heads they modify" —
at one column per sixteenth an accidental could only sit in the previous
sixteenth's head cell, which collides exactly when accidentals are most
likely (a repeated letter name, C then C♯).

Score column `C` maps to musical content as:

| C | content |
|---|---|
| 0, 3-30 | blank staff |
| 1-2 | treble and bass clefs |
| `31 + 2k` | accidental / bar-line slot of sixteenth `k` |
| `32 + 2k` | note-head slot of sixteenth `k` |

`SC0 = 31` is fixed by the scrolling half of the lead-in: the head of
sixteenth 0 is at score column 32 and must reach the "now" column when the
music starts, so `shifts = 32 - NOW = 22`, and 22 shifts × 4 frames = the
88-frame `LEADIN`. `SC0 = LEADIN/4 + NOW - 1`.

`NOW = 10`. Screen column 10 is where a head is at the instant it sounds,
which leaves 29 columns (≈14 sixteenths, nearly one bar) of music visible
*before* it sounds and 10 columns of music already played — so the score
reads as arriving. During the static `HOLD` the screen shows score columns
0-39, which is the clefs, the first bar line and the opening four sixteenths
standing still.

**Bar lines and accidentals share a column, and the accidental wins the
cell.** A bar line fills its column across rows 6-16 (treble top line to bass
bottom line); where a voice needs an accidental in that same column, the
accidental glyph is written into that one cell instead of the bar-line
segment. The result is a bar line with a notch in it, which is legible and is
close to what engraving does anyway (the accidental sits just after the
bar line).

### Renderer

`drawcol` writes score column `C` into screen column 39 and its color RAM,
once per column shift. It is per-column independent — no state carries
between columns — which is what makes the whole display a pure function of
`shifts`.

1. Fill all 15 band rows with the row's background glyph: code 33 (staff
   line) for rows 6-10 and 12-16, code 32 (blank) otherwise; color white.
2. Clefs if `C` is 1 or 2.
3. If `C >= SC0`: `k = (C - SC0) >> 1`.
   - Even offset (accidental slot): if `k` is a bar downbeat (`k mod 16 == 0`)
     write bar-line glyphs into rows 6-16. Then for each voice with an
     accidental at `k`, write its accidental glyph at that voice's row and
     half, in that note's pitch-class color.
   - Odd offset (head slot): for each voice with an attack at `k`, write the
     head glyph — the variant selected by (half, filled/hollow, on-a-line) —
     and set the cell's color to the note's pitch class.
4. Ledger positions (p = 1, 3, 15, 27, 29) get code 33 rather than 32 when a
   head or accidental occupies them.

**Two voices in one cell.** Two voices a diatonic step apart share a
character cell (one in each half) and the renderer writes a combined
both-halves glyph — but color RAM is one nybble per cell, so only one pitch
class can be shown. Policy: **the lower-numbered voice's color wins** (voice
1 over 2 over 3 — the subject is never the one that loses its color), and the
program increments a 16-bit `collide` counter. This is the honest limit of
one-color-per-cell, it is counted rather than hidden, and criterion 15 reads
the counter.

### The renderer and the sequencer read one array

When sixteenth `k` sounds, `shifts = 22 + 2k`, and the column being rendered
at the right edge is `shifts + 39`, whose offset is `30 + 2k`, whose
sixteenth is `15 + k`. The render frame is one frame later, at
`shifts = 23 + 2k`, whose offset is `31 + 2k` — odd, the head slot — and
`(31 + 2k) >> 1` is `15 + k` again. **The renderer is exactly 15 sixteenths
ahead of the sequencer on both of a sixteenth's two render frames, from the
same three arrays.** Criterion 16 reads both indices at one stop and checks
the difference is 15.

---

## 7. Note-to-color mapping

Color RAM is one nybble per character cell, so a note head's color is a
whole cell's worth of color and each of the twelve pitch classes gets one of
the C64's sixteen (hardware.md, "Video modes", colors 0-15).

**Be honest about the constraint.** Black (0) is the background. White (1) is
spent on the staves, clefs and bar lines, where it has to be — that is the
prompt's requirement and it is also the only color that reads as "not a
note". That leaves fourteen for twelve pitch classes, and the fourteen are
not equally legible against black:

| Tier | Colors | Judgement |
|---|---|---|
| **Strong** (9) | 2 red, 3 cyan, 4 purple, 5 green, 7 yellow, 8 orange, 10 light red, 13 light green, 14 light blue | Unambiguous against black at 1× and distinguishable from each other. |
| **Weak** (3, used) | 9 brown, 12 medium gray, 15 light gray | Legible but compromised: brown is dim and muddy against black, medium gray is dim, and light gray is close enough to the white staff lines that a head on a line is momentarily hard to pick out. |
| **Rejected** (2) | 6 blue, 11 dark gray | Too dark on black to read as a note head at all. |

Twelve classes need nine strong plus three weak. **The three weak colors go
to the three pitch classes that occur least often in this arrangement**, and
which those are is measured, not guessed: `tools/bwv847.py` counts attacks
per pitch class over all three voices and `tools/genmusic.py` reads that
histogram. Assigning by frequency is the least bad rule available — it
minimises the number of note heads a viewer has to work to read — and it is
reproducible, so the table below is derived rather than tasteful.

The two rejected colors are not wasted: they are the sprite backlight colors
(§8), where dimness is the point.

<!-- COLORTABLE -->

---

## 8. The sprite backlight

**Three sprites, one per voice** — sprite 0 for voice 1, 1 for voice 2, 2 for
voice 3. Three of eight is cheap, and it makes the tracking claim provable
three times at one stop instead of once.

All three use the same 24×21 hires shape at `$2800` (pointer block `$A0` =
`$2800/64`), a soft glow whose lit band occupies sprite rows 7-13, and they
differ only in color: voice 1 blue (6), voice 2 dark gray (11), voice 3 brown
(9) — dim by design, and the two rejected note colors put to use.

`$D01B` bits 0-2 are set, which is the choice that makes it read as backlit
rather than pasted on. The bit "only sets sprite-vs-*character-data*
priority (each sprite's bit: 0 = sprite in front of data, 1 = data in front);
sprites always beat the background *color*" (hardware.md, "Sprites"). So the
glow is hidden wherever the note head's own pixels are lit and shows
everywhere the cell is background — a halo around a white-on-black head,
which is exactly backlighting. Criterion 13 is the screenshot that has to
show it that way.

### Tracking

The glow follows the head of the note actually sounding, and moves with it as
it scrolls:

```
x = 102 - 2*age            age = frames since this voice last attacked
y = 82 + 4*p               p = the position index of the sounding note
```

`x` derives from the head's own pixel position — head left edge is
`24 + 8*NOW + xsc` at age 0 and falls 2 px per frame, and the glow is
centred on it by subtracting 8. At `age = 0` that is 102; the sprite is
disabled once `age > 39`, where `x` would fall below 24 and leave the visible
range (hardware.md: "Visible X range starts at 24"). A note longer than five
sixteenths therefore loses its glow before the head scrolls out of the "now"
region — documented, and `sprage` publishes the age that caused it.

Everything in those two formulas is published as a state byte (§9), so
criterion 14 compares `$D000`-`$D005` against them and against the
sequencer's own idea of what is sounding, at one stop.

---

## 9. Observable state

Every byte below is a label exported into the `.lbl` file, so `c64 until`,
`c64 mem get` and `test.yaml` name the signal instead of an address that
drifts on the next build. Equates do not reach the label file — "Equates are
not labels and never reach the label file … Export what a test or debug
session needs to name" (asm/SKILL.md) — so these are all real storage in
`vars.s`.

| Label | Bytes | Meaning |
|---|--:|---|
| `frame` | 2 | frames since `init`; the one clock |
| `sf` | 2 | the scroll clock, `frame - HOLD`; every scroll and sequencer derivation reads this |
| `state` | 1 | 0 HOLD (static), 1 LEAD (scrolling, silent), 2 PLAY, 3 FINE |
| `xsc` | 1 | the `$D016` fine-scroll value written this frame (0-6, even) |
| `shifts` | 2 | column shifts performed since `init` |
| `sixteenth` | 2 | index of the sounding sixteenth, 0-495 (PLAY only) |
| `rendk` | 2 | the sixteenth index `drawcol` last drew |
| `bar` `beat` `slot` | 1 each | 1-31, 1-4, 0-15 |
| `vnote` | 3 | MIDI number sounding per voice, 0 = silent |
| `vpos` | 3 | staff position `p` per voice, `$FF` = none |
| `vacc` | 3 | 0 none, 1 sharp, 2 flat |
| `vatk` | 3 | 1 on the frame that voice attacked |
| `v1idx` `v2idx` `v3idx` | 2 each | attacks played on that voice so far (contiguous words) |
| `sprx` `spry` | 3 each | the sprite X/Y this frame wrote |
| `sprage` | 3 | frames since that voice's last attack |
| `sprcol` | 3 | screen column of the head being backlit |
| `sprena` | 1 | the `$D015` value written this frame |
| `collide` | 2 | cells where two voices wanted the same half, or the same accidental row |
| `pwmval` | 2 | voice 1 pulse width, as written |
| `cutoff` | 2 | filter cutoff, as written |
| `videostd` | 1 | 0 NTSC, 1 PAL, latched from `$02A6` |
| `shiftline` | 1 | high-water `$D012` immediately after `shiftband`, shift frames only |
| `tickend` | 1 | high-water `$D012` at `tick`'s exit, shift frames only |
| `sidshadow` | 25 | every SID write mirrored, `$D400`-`$D418` in order |

The per-voice signals are three-byte arrays rather than nine separate labels,
because the tick walks them in a loop. A test names one with `symbol+offset`,
which `c64 test run` resolves: `vnote+1` is voice 2's sounding pitch.

`sidshadow` exists because "on real hardware `$D400–$D418` is write-only …
That is why demos still mirror every SID write into a RAM shadow block — the
shadow is the program's own evidence and holds on a real C64, the register
log is the emulator's. Keep both; they fail in different directions"
(audio-verification.md, "Known facts"). It is not the audio evidence; §11 is.

---

## 10. The arrangement

Three voices, no parts dropped, merged or compromised — BWV 847 is a
three-voice fugue and the SID has three voices. The reduction is original
work for this demo, written from the public-domain score, and lives as
readable note names in `tools/bwv847.py`; `tools/genmusic.py` turns it into
`notes.inc`.

### Encoding

One byte per voice per sixteenth, 3 × 496 = **1,488 bytes**:

| Byte | Meaning |
|---|---|
| `$00` | rest — release the gate |
| `$FF` | hold — the previous note continues, gate untouched |
| other | bits 0-4 = `p + 1` (staff position 1-30); bits 5-6 = accidental (0 none, 1 sharp, 2 flat); bit 7 = hollow head (quarter or longer) |

The sounding pitch is `posmidi[p] + (+1 sharp / -1 flat / 0 none)`, so the
picture and the sound are the same byte read two ways — which is what makes
the cross-check in §11 meaningful rather than circular. There is no separate
pitch stream that could disagree with the drawn one.

### Voice assignment and timbre

| Voice | Role | Waveform | A | D | S | R | Registers |
|---|---|---|--:|--:|--:|--:|---|
| 1 | subject / soprano | pulse, PW swept | 0 | 8 | 10 | 6 | `$D400-$D406`, ctrl `$41`/`$40` |
| 2 | countersubject / alto | sawtooth | 1 | 7 | 9 | 5 | `$D407-$D40D`, ctrl `$21`/`$20` |
| 3 | bass / pedal | triangle, through the filter | 0 | 9 | 11 | 7 | `$D40E-$D414`, ctrl `$11`/`$10` |

Attack 0 is 2 ms and decay 8 is 300 ms (hardware.md, "Envelope rates"), which
is the crisp attack the fugue's perpetual sixteenths reward at 133 ms a note.
Voice 3's sustain is the highest of the three deliberately: "Low (bass) notes
sound **weaker** than high notes of the same amplitude; raise the sustain
level of low notes to compensate" (hardware.md, "6581 caveats").

Globals: `$D418` = `$1F` (volume 15, low-pass), `$D417` = `$A4` (resonance
10, voice 3 routed through the filter). Bit 7 of `$D418` is **not** set — it
would disconnect voice 3 from the output.

**Pulse-width modulation, voice 1.** `pwmval` sweeps `$0400` ↔ `$0C00` in
steps of 16 per frame, a 128-frame triangle, written to `$D402/$D403`.
`$800` is a square wave (hardware.md), so the sweep passes through it and out
both sides: a chorusing, phasing lead. The spectrogram is the evidence
(audio-verification.md: the spectrogram "is where everything the note
transcription cannot describe shows up").

**Filter sweep, voice 3.** Base cutoff `$D416` = `$70`, high enough that the
bass is present rather than swallowed. Through the closing pedal point the
cutoff descends to `$10` over two bars and returns over two, published in
`cutoff`. On the spectrogram this is a moving edge; that is the claim
criterion 20 reads.

**Gate policy: drop and re-raise the gate inside one frame.** Both writes
happen in the same `tick`, so the once-per-frame sampler never sees the gate
low, every note is articulated, and every scored duration stays a whole
multiple of 8 frames — "This is the option to reach for when you want the
arithmetic to be predictable" (audio-verification.md). Its consequence is
that two consecutive equal pitches merge into one transcribed event, and the
score generator models exactly that (§11).

**Note frequencies are a table generated for both machines.** `hz = reg16 *
clock / 2**24` inverted, for MIDI 33-88, at 1,022,727 Hz and 985,248 Hz;
`init` reads `$02A6` (0 = NTSC, 1 = PAL — zero-page.md) and picks one. This
costs 224 bytes and removes the classic bug wholesale: "an NTSC-tuned table
played on a PAL machine sounds **65 cents flat** on every note"
(audio-verification.md). The *tempo* still follows the frame rate, so a PAL
machine plays this at 93.75 BPM — which is why `c64 package` pins `-ntsc`.

**Ending.** The demo plays once and stops, in two steps that are eight
sixteenths apart and must not be confused — the first build confused them and
ended on an empty staff.

1. **The scroll halts** when the last *attack*'s head reaches the now column,
   at `shifts = stopshift = 22 + 2*488 = 998`, frame 4,143. `stopshift` is
   emitted by `genmusic.py` from the arrangement, not written down. Halting
   on the sequencer's last sixteenth instead is too late: the closing chord is
   held to the end, so the score would scroll 16 further columns and carry it
   off the left edge.
2. **The gates release** when the sequencer runs out at frame 4,206, and
   `state` becomes 3.

Between the two the chord rings at the now column, backlit — `glowtick`
freezes `sprage` while the scroll is halted, because the age is what drives
the glow's x and a stationary head must have a stationary glow. At the release
the glow goes out with the sound: the backlight tracks *sounding*, and nothing
is. The heads stay on screen.

**Two things must stop, and the second is easy to miss.** Halting the column
shift is not halting the scroll: the `$D016` fine scroll is a separate write,
and leaving it running walks `xsc` through 6, 4, 2, 0 for ever, jittering the
finished picture six pixels back and forth at 15 Hz. Both are gated on
`scrollon`. And from the frame after `state` becomes 3, `tick` returns
immediately: the transition frame has already released the gates, put the
sprites out and written the release, so every frame after it has nothing to do
and does nothing. `frame` goes on counting so `c64 until tick` is still an
anchor — there is simply nothing left that could move for it to anchor on.
Criterion 22 samples `shifts`, `xsc` and `$D016` and asserts all three
unchanged across 120 further frames.

The closing sonority is C3-G3-E4, and only G3 and E4 are on the staff at the
end: the tonic pedal C3 was attacked at bar 29 and tied through, so its head
is 54 columns to the left. That is where a tied note's head belongs. No loop,
no fade.

---

## 11. Verification

### Deterministic protocol

Everything runs `--warp --headless`; every observation is anchored on a
`c64 until tick --count N` stop and read while the machine is stopped.
`tools/evidence.sh` regenerates the lot in one command and follows the five
rules in `docs/graphics-and-sprites.md` §5 — one `run`, `until` before every
capture, never a `wait` after an `until`, staged states poked rather than
played to, and **one extra tick immediately before every capture**, because
`c64 screen --png` returns the emulator's rolling scanline buffer.

`frame` and `until tick --count N` are the same quantity, which is what makes
every screenshot below reproducible to the frame.

### Screenshots (`evidence/`, `--scale 2 --border`)

| File | Stop | Shows |
|---|---|---|
| `staves.png` | tick 30 | the grand staff, both clefs, black screen — drawn before a note sounds |
| `entry1.png` | first attack of the subject | the first entry, with the state bytes beside it |
| `entry2.png` | first attack of the answer | second voice in |
| `entry3.png` | first attack of the bass | third voice in |
| `crossing.png` | a frame where two voices cross | the layout still legible where the lines meet |
| `accidental.png` | a bar with a flat on a repeated letter | an accidental beside the head it modifies |
| `pedal.png` | the pedal point | the closing section under the filter sweep |
| `backlight.png` | any attack | the glow reading as behind the head, not over it |
| `fine.png` | `state = 3` | the final chord, scroll halted |

### `test.yaml`

`c64 test run demos/fugue/test.yaml`, with
`areas: [CHARS=$2000:$0800, SPRITES=$2800:$0100]`. It asserts, never on PNG
pixels: the mode registers of §2 (masked where they are 4-bit); `$D018` = `$19`;
staff glyph codes at their expected cells on both staves; the clefs present
during the lead-in; `xsc` walking 6→4→2→0 across four `until tick` stops and
`shifts` incrementing exactly once across the wrap; a head cell's color RAM
matching the §7 table for that pitch class, masked `and: "$0f"`; `$D000`-`$D005`
equal to `sprx*`/`spry*`; `spry_v == 74 + 4*p_v`; `rendk - sixteenth == 15`;
`shiftline < 195`; `collide` at its expected value; and the SID shadow
matching the control/ADSR bytes for each voice.

Motion is sampled, not fixed: `sample: { mem: shifts, as: s0, width: 2 }`,
`until`, `assert: { mem: shifts, greater_than: s0 }` — **`width: 2`**, because
a byte-wide sample of a 16-bit counter "is a number that falls every 256
counts" (docs/cli.md, `c64 test run`).

### Audio evidence (`evidence/audio/`)

Four captures, each the five artifacts `c64 audio capture` writes
(`capture.wav`, `sid-log.jsonl`, `piano-roll.png`, `spectrogram.png`,
`report.md`), one per structural moment: the three exposition entries and the
pedal point with its filter sweep. Ten to fifteen emulated seconds each —
captures run in real time and cost two to three times that in wall clock
(audio-verification.md), so the whole set is four minutes, not an hour.

**Scores are generated from the arrangement, never from the
transcription.** `tools/genscore.py` implements the two-step rule
audio-verification.md gives: model the player one frame at a time — emitting
what a once-per-frame sampler would read on each frame, including the frames
the gate is down — then run-length encode that list. Pasting a transcription
back in "produces a diff that passes by construction — with your bug baked in
as the specification."

**Durations are pinned, and that is a claim this demo can make where a
jiffy-paced one cannot.** The documented drift — "a jiffy-paced player and
the sid log are two clocks, and they separate by one frame every ~341 log
frames" — is between the KERNAL's 60.0016 Hz CIA tick and the log's 59.826 Hz
video frame. This player is paced by a raster IRQ, one per video frame, and
the log "samples once per resume" with the machine halting at vsync — the
same clock. So a 900-frame window can carry `frames` on every entry. If a
capture disagrees, that is a finding about the pacing, not a reason to drop
the durations, and the audit records which.

Window placement accounts for the arm: park at `target - lead_in`, capture,
read `lead_in_frames` from the payload, and if it moved, re-score the
**existing log** with `c64 audio report` rather than re-capturing — it is
"analysis only, no machine".

### The cross-check

The piano roll and the scrolling staff are two renderings of one array
(§10) — same bytes, read once for pitch and once for position. They are put
side by side and read for the same pitches in the same order with the same
rhythm. Because there is only one array, a disagreement is a bug in one of
the two *paths*, and finding out which is the point. The audit records the
comparison per capture, not as a summary.

---

## 12. Acceptance criteria

Each is an observation a stopped machine can be read for. Anchoring: arm
`c64 break add tick` **before** `c64 run`, take the first `wait --break` to
reach `frame = 0` deterministically, then `until tick --count N` puts you on
frame N exactly. (Running first and `until`-ing afterwards does not: measured
on the first build, `until tick --count 30` straight after `run` landed on
frame 3,774, because the machine free-ran at warp between the two commands.)

1. At `until tick --count 30`, `c64 screen --codes` shows code 33 across all
   40 columns of rows 7-11 and 13-17, code 32 across rows 0-4 and 20-24, and
   the clef codes 64-73 and 74-79 in columns 1-2 of rows 7-11 and 13-15.
2. At the same stop: `$D011` = `$1B` exactly (a stopped machine is at the top
   of the frame, so the raster MSB is 0 — measured); `$D016 and $0F` = 6, 4,
   2 or 0 with bit 3 **clear**; `$D018` = `$19`; `$D01B` = `$07`;
   `$D020 and $0F` = 0; `$D021 and $0F` = 0.
3. Across four consecutive `until tick` stops during PLAY, `xsc` reads 6, 4,
   2, 0 in that cyclic order, and `shifts` increases by exactly 1 across the
   0→6 transition and by 0 across the others.
4. `state` reads 0 while `frame < 150`, 1 from 150 to 237, and 2 at frame
   238 — the first frame of PLAY is `HOLD + LEADIN`.
5. `sixteenth` = `(frame - 238) / 8` at every PLAY stop, exactly.
6. At the stop where `v1idx`, `v2idx` or `v3idx` first becomes 1 for each
   voice in turn, `bar` and `slot` equal the bar and slot the arrangement's
   `SUBJECT_ENTRIES` records for that entry.
7. The three exposition entries are audible as three separate entries in
   `piano-roll.png`: three colours, each starting at a different frame, none
   missing (audio-verification.md: "A color missing entirely" is a
   voice-allocation bug).
8. Every one of the four `report.md` files carries verdict **PASS** with an
   empty score diff and no anomalies, and none reports `nothing_played`.
9. `capture.wav` in each of the four is non-empty, `duration_s` within 5% of
   the requested seconds, `clipped_samples` = 0.
10. At a stop during PLAY, `sidshadow+4`, `+11` and `+18` hold `$41`, `$21`
    and `$11` (waveform + gate) for a voice that is sounding, and `$40`,
    `$20`, `$10` for one that is not.
11. `c64 profile tick --samples 32` reports both modes, and its maximum is
    below 17,095 cycles. **Measured: 15,625 max, 864 min.**
12. After at least 600 frames, `tickend` <= 203 — the last band row's column
    is final before the VIC latches that row — and `shiftline` <= `tickend`.
    Both marks are kept only on shift frames; a non-shift frame exits in the
    border and would poison a high-water that included it. **Measured after
    900 frames: `shiftline` 177, `tickend` 178.**
13. `frame` reads exactly N after `until tick --count N` for N = 900, so the
    tick never overruns a frame and no interrupt is missed.
14. `backlight.png` shows the glow only in the cell's background pixels
    around the head, with the head's own white pixels unobscured.
15. At one stop, for each voice `v` that is sounding: `$D000 + 2v` =
    `sprx+v`, `$D001 + 2v` = `spry+v`, `spry+v` = `82 + 4*(vpos+v)`, the bit
    for `v` is set in `$D015`, and `vnote+v` = `posmidi[vpos+v]` adjusted by
    that note's accidental.
16. `collide` is stable across the run and equals the count
    `tools/genmusic.py` predicts from the arrangement; where it is non-zero,
    `crossing.png` shows one of those cells and the audit names the bar.
17. `rendk - sixteenth` = 15 at every PLAY stop.
18. `accidental.png` shows a flat or sharp in the column immediately left of
    the head it modifies, and the SID shadow at that stop holds a frequency
    one semitone from `posmidi[p]` for that voice.
19. `crossing.png` is taken at a bar the arrangement says has voice 1 below
    voice 2, and both heads are separately visible.
20. `spectrogram.png` for the voice-1 entry capture shows harmonic content
    moving with `pwmval` — the PWM is visible as changing partials, not a
    static comb.
21. `spectrogram.png` for the pedal capture shows a moving cutoff edge, and
    `cutoff` read at stops through that section descends and returns.
22. At the last stop, `state` = 3, `shifts` has stopped increasing across a
    further 120 frames, the final heads are still on screen, and all three
    gates read released in `sidshadow`.
23. `c64 test run demos/fugue/test.yaml` passes every step.
24. `c64 package` produces `fugue.d64` and `fugue.prg`, and the reported run
    command names `-ntsc`.
25. The piano roll from each capture and the score on screen at the same
    frames agree on pitch, order and rhythm — recorded in `AUDIT.md` per
    capture, with any disagreement traced to one of the two paths.

---

## 13. Files

| File | |
|---|---|
| `fugue.s` | load address, BASIC stub, equates, `init`, the IRQ wrapper, includes |
| `vars.s` | every mutable byte of §9, with the labels tests read |
| `staff.s` | `drawscreen`, `drawcol`, the row/background tables |
| `scroll.s` | the column shift and `$D016` |
| `music.s` | the sequencer, SID writes, the shadow, PWM and filter sweeps |
| `glow.s` | sprite tracking |
| `chars.inc` | generated charset (`c64 charset encode`) |
| `sprites.inc` | generated glow shape (`c64 sprite encode`) |
| `notes.inc` | generated note data, `posmidi`, the two frequency tables |
| `tools/bwv847.py` | the arrangement, as note names, with self-checks |
| `tools/genmusic.py` | `bwv847.py` → `notes.inc`, and the pitch-class histogram |
| `tools/genscore.py` | `bwv847.py` → reference scores, per capture window |
| `tools/charset.txt` | the ASCII glyph sheet |
| `tools/glow.txt` | the ASCII sprite sheet |
| `tools/evidence.sh` | regenerates every screenshot |
| `tools/audio-evidence.sh` | regenerates the four captures (`--strict`) |
| `test.yaml` | the regression test |
