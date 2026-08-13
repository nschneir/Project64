# 1812 — specification

What the demo is, what the hardware does, and what a stopped machine must
read back for the build to count as finished. Answers `PROMPT.md`. Hardware
facts are cited to `skills/c64-development/references/hardware.md` (VIC-II,
SID), `references/memory-maps.md`, `references/zero-page.md`, and
`docs/graphics-and-sprites.md` (policy).

Every acceptance criterion in §12 is written as an observation a *stopped*
machine can be read for. Nothing in this document is satisfied by reading
the source.

---

## 1. The picture in one paragraph

A black 160×200 multicolor bitmap fills up over 2 minutes 50 seconds with
rotated, dither-filled polygons — triangles, rectangles, pentagons,
hexagons, five- and four-pointed stars, crosses, circles, ovals and
ellipses. Each shape is spawned by a note onset in a three-voice SID
reduction of Tchaikovsky's *1812 Overture*, and the section of the
arrangement decides the shape vocabulary, the palette, the size range and
the spawn rate. Nothing is ever erased: the canvas only ever gets denser,
so the finished picture is a record of the whole piece. Sixteen cannon
shots flash the screen white and throw a burst of shapes. When the piece
ends the canvas holds; a key restarts it with a fresh seed.

---

## 2. Graphics mode and memory map

### 2.1 Mode

**Multicolor bitmap, 160×200, 4 colors per 4×8 cell.** Chosen over hi-res
because the prompt makes the color budget the interesting problem: hi-res
gives two colors per 8×8 cell out of screen RAM alone, which cannot express
a per-section three-color palette, and the dither masks that make shapes
read as translucent need more than one non-background ink.

The cost is horizontal resolution: a multicolor pixel is **two screen
pixels wide**. §5.3 corrects for that in the vertex transform so a circle
is round and a rotated square is a square, not a sheared rhombus.

| Register | Value written | Readback assertion | Why |
|---|---|---|---|
| `$D011` | `$3B` | `& $7F == $3B` | bitmap (bit 5), DEN (bit 4), RSEL 25 rows (bit 3), yscroll 3. Bit 7 is the raster MSB and is masked off. |
| `$D016` | `$18` | `& $1F == $18` | multicolor (bit 4), CSEL 40 columns (bit 3), xscroll 0. Bits 5-7 are unused and read as 1. |
| `$D018` | `$18` | `& $FE == $18` | screen base bits 7-4 = `%0001` → `$0400`; bitmap base bit 3 = 1 → `$2000`. Bit 0 is unused and reads as 1. |
| `$D020` | `$00` | `& $0F == 0` | black border. The register is 4 bits wide; a read returns `$F0`. |
| `$D021` | `$00` | `& $0F == 0` | black background = bit-pair `00`. Same 4-bit readback. |

VIC bank 0 (`$0000-$3FFF`) is left as the power-on default, so `$DD00` is
untouched and the screen stays at `$0400` — the toolset's screen reader
assumes that (`references/hardware.md`, "Video modes").

### 2.2 Memory

```
$0000-$00FF  zero page — 14 claimed bytes, §2.3
$0801-$080C  BASIC stub "10 SYS 2061"
$080D-$1FFF  CODE / RODATA / DATA / BSS      (6,131 bytes; hard ceiling $2000)
$0400-$07E7  screen RAM — bit-pair 01 = high nybble, 10 = low nybble
$2000-$3F3F  the 8,000-byte bitmap
$C000-$C3FF  quarter-square multiply tables, built at startup by `qsgen`
$C400-$C5FF  the rasterizer's working arrays
$D800-$DBE7  color RAM — bit-pair 11 (low nybble of each byte)
```

The program **must end below `$2000`** or it grows into its own canvas, and
the `$C400` block must fit its 512 bytes. Neither is checked by hand: both
are **linker assertions** in `vars.s`, so overrunning either is a build error
rather than a demo that quietly paints over its own canvas. (Both fired
during the build; that is why they are there.)

`$C000-$CFFF` is the 4 KB BASIC never touches. Nothing there is in the
`.prg` — with the bitmap at `$2000` the program has about 120 bytes of
headroom (`$2000 - (__BSS_LOAD__ + __BSS_SIZE__)`, re-derived from
`1812.lbl` rather than trusted from here, since it has moved every
iteration), and the tables and arrays are 1,536: the 1,024 and the 512 of
the two blocks above. The VIC-II cannot see `$C000`, which does not matter:
only the CPU reads them.

The VIC-II sees the character ROM image at `$1000-$1FFF` in bank 0, but
only for character and bitmap fetches; our bitmap is at `$2000` and our
code at `$1000-$1FFF` is never fetched by the VIC, so the shadow is
harmless.

### 2.3 Zero page

`references/zero-page.md` documents only `$02` and `$FB-$FE` as safe *under
BASIC*. This demo never returns to BASIC — `SYS` never comes back — so the
only other consumer is the KERNAL IRQ we chain to. That makes BASIC's own
scratch reusable, but it is **proved, not assumed** (PLAN step 1): write
sentinels, park the machine in the demo's own idle loop with the KERNAL IRQ
live for 600 frames, read them back.

| Address | Label | Role |
|---|---|---|
| `$02` | `ORB1` | dither OR bits, odd cell |
| `$22/$23` | `COLPTR` | color-RAM row pointer |
| `$24` | `MULA` | signed multiply operand A |
| `$25` | `MULB` | signed multiply operand B |
| `$26/$27` | `MULR` | signed multiply result (16-bit) |
| `$28` | `ANDM0` | dither AND mask, even cell |
| `$29` | `ORB0` | dither OR bits, even cell |
| `$2A` | `ANDM1` | dither AND mask, odd cell |
| `$FB/$FC` | `BMPPTR` | bitmap byte pointer |
| `$FD/$FE` | `SCRPTR` | screen-RAM row pointer |

`$22-$2A` is BASIC's `INDEX` scratch and floating-point work area
(`zero-page.md`, "The label database"); nothing in the KERNAL IRQ path
touches it.

### 2.4 Cursor blink

The KERNAL IRQ blinks the cursor by writing a screen code into screen RAM
— which in this mode is a *color* cell. `BLNSW` (`$CC`) suppresses it; init
stores a nonzero value there so a stray blink can never recolor a cell.

---

## 3. Color: the palette and the clash policy

A multicolor bitmap cell has four inks
(`references/hardware.md`, "Bitmap and color-text modes"):

| bit-pair | source |
|---|---|
| `00` | `$D021` — global background, **always black** except during a cannon flash |
| `01` | high nybble of the cell's screen-RAM byte |
| `10` | low nybble of the cell's screen-RAM byte |
| `11` | low nybble of the cell's color-RAM byte |

**Policy: the section's palette owns the cell.** Each section fixes one
triple `(c01, c10, c11)`. Every cell a shape paints into is re-stamped with
the *current section's* triple, and each shape picks one of the three
bit-pairs as its ink.

Consequences, all deliberate:

- **Inside a section there is no clash at all.** Every cell carries the same
  three colors, so overlapping shapes composite cleanly and a dither mask
  really does read as translucency over what is underneath.
- **A section change re-tints.** When a battle shape crosses a cell the hymn
  painted, that cell's hymn pixels become battle colors. The picture ages
  toward the current section instead of staying a pile of stickers — this is
  the mechanism that makes the finished canvas read as one image.
- Cells no shape has touched are never stamped, so the re-tinting follows the
  shapes' actual geometry, not their bounding boxes. §5.6 pays for that
  exactness with a per-row attribute pass.

### 3.1 Section palettes

Colors are VIC-II indices (`references/hardware.md`, "Video modes").

| # | Section | `c01` | `c10` | `c11` | Reading |
|---|---|---|---|---|---|
| 0 | Hymn | 11 dark grey | 12 medium grey | 15 light grey | the luminance ladder on black — grave, unlit |
| 1 | Marseillaise | 6 blue | 2 red | 1 white | the tricolore |
| 2 | Battle | 2 red | 8 orange | 7 yellow | fire |
| 3 | Cannon | 9 brown | 8 orange | 1 white | smoke and muzzle flash |
| 4 | Finale | 7 yellow | 13 light green | 1 white | bright, ringing |

The palette does the mood; the dither masks (§5.5) mix apparent colors the
16-color palette does not contain — 50% red-on-orange reads as a third
tone, and sparse white over dark grey reads as a highlight.

---

## 4. Shapes

Ten types. Each is a closed polygon whose unit vertices lie within radius 64
of the origin in **isotropic screen-pixel space** (signed bytes, so radius
64 is `1.0` in Q6). Concave shapes are marked; the fill is even-odd, so
concavity is not a special case.

| id | name | verts | notes |
|---|---|---|---|
| 0 | triangle | 3 | equilateral, apex up at angle 0 |
| 1 | rectangle | 4 | square at angle 0; a rotated one reads as a diamond |
| 2 | pentagon | 5 | |
| 3 | hexagon | 6 | |
| 4 | star5 | 10 | **concave** — outer r 64, inner r 25 |
| 5 | circle | 16 | 16-gon, r 64 |
| 6 | oval | 12 | 12-gon, x 64 / y 48 |
| 7 | ellipse | 16 | 16-gon, x 64 / y 26 — a rotated one visibly tilts |
| 8 | star4 | 8 | **concave** — outer r 64, inner r 20 |
| 9 | cross | 12 | **concave** — a plus sign, arm half-width 22 |

Vertex data is commented `.byte` rows in `shapes.s`, per
`docs/graphics-and-sprites.md` §2 — no binary blobs.

Shapes may run off any edge. They are **clipped, never skipped**: the
scanline loop stops early below y 199 and suppresses fills above y 0, and
each span is clipped to x `[0,159]`.

---

## 5. The rasterizer

### 5.1 Per-shape inputs

Drawn from the RNG (§7) at paint time, all recorded in the observable
block (§8):

`type` 0-9 · `size` (on-screen radius in screen pixels, per-section range)
· `cx` 0-159 (multicolor pixels) · `cy` 0-199 · `angle` 0-255 ·
`pattern` 0-7 · `ink` 1-3 (which bit-pair).

### 5.2 Angle and the sin/cos tables

A **256-step angle**. `sintab` is 256 signed bytes,
`round(127 · sin(2πi/256))`, in `RODATA`; `cos(a) = sintab[(a + 64) & 255]`.
Generated by `tools/gentables.py` and committed as commented `.byte` rows.

### 5.3 Vertex transform

Two multiplies per shape, then four per vertex:

```
sc = (cos(angle) · size) >> 7        signed byte, |sc| <= size
ss = (sin(angle) · size) >> 7

per unit vertex (ux, uy):
    px = (ux·sc - uy·ss) >> 6        screen-pixel offset, |px| <= size
    py = (ux·ss + uy·sc) >> 6
    vx = cx + (px >> 1)              multicolor x  (>>1 is the 2:1 aspect)
    vy = cy +  py                    screen y
```

Fixed-point formats, stated exactly rather than called "8.8" everywhere:
unit vertices are **Q6** (64 = 1.0), the sin table is **Q7** (127 ≈ 1.0),
the products are 16-bit signed and shifted back to integers, and the edge
slopes of §5.4 are the only true **8.8** quantity. `size` is an integer
number of screen pixels.

The `>> 1` on x is what makes rotation *real*: vertices are rotated in
square-pixel space and only then projected onto the 160-wide grid, so a
rotated square is a square on screen and a rotated ellipse tilts about its
true axis.

`smul` is a signed 8×8 → 16 multiply built on **quarter squares**:
`a·b = f(a+b) − f(a−b)` with `f(x) = ⌊x²/4⌋`, which is exact for integers.
`qsgen` builds the two 512-entry tables at startup by accumulating `f`'s own
first difference, so there is no multiply in the generator either. Cost is
measured with `c64 profile`, not estimated (§12, A13) — the shift-add version
this replaced was measured at 330 cycles against a 16-vertex transform that
calls it 64 times.

### 5.4 Edges and the active-edge table

For each polygon edge with `vy0 != vy1`: `ytop`/`ybot` (16-bit signed),
`x` at `ytop` (16-bit signed), `|dx|`, `dy = ybot - ytop`, and a sign step
`sx` of ±1. There is **no division**: x advances by a Bresenham DDA —
`err += |dx|`, then `while err >= dy: err -= dy; x += sx` — whose total work
over an edge's life is `dy + |dx|` steps.

Edge indices are insertion-sorted by `ytop` into `eord`. The scanline loop
maintains an **active-edge table**: at each y, admit edges whose `ytop <= y`,
drop edges whose `ybot <= y`, and step only the survivors. Cost per row is
therefore proportional to the number of edges actually crossing that row —
2 for every convex shape, at most 4 for the concave ones — not to the vertex
count. This is the loop the audit cycle-counts.

Ceilings: 16 vertices, 16 edges, **8 crossings** per scanline. The
vocabulary's worst case is 4 (star5, star4, cross), so 8 is slack, and the
build asserts it rather than trusting it.

### 5.5 Dither patterns

Eight 8×8 masks, each 8 rows × 2 bytes, in `RODATA` as commented binary
rows. A byte is four multicolor pixels; a pixel's pair is `11` (paint) or
`00` (leave). The row mask for scanline y is
`pat[p] + (y & 7)·2`, and cell parity picks the byte — so the pattern is
8 pixels wide and 8 rows tall, and it is locked to the *screen*, not to the
shape, so overlapping shapes interleave instead of moiréing.

| p | pattern |
|---|---|
| 0 | solid |
| 1 | 50% checker |
| 2 | vertical stripes, 2 px on / 2 off |
| 3 | horizontal stripes, 2 rows on / 2 off |
| 4 | diagonal, period 4 |
| 5 | sparse dots, 1 in 16 |
| 6 | cross-hatch |
| 7 | quarter tone, 1 in 4 |

Per scanline the mask is reduced to two AND/OR pairs in zero page:

```
ANDM = ~m        ORB = inkbits & m        inkbits = ink replicated ×4
                                          (1 → %01010101, 2 → %10101010,
                                           3 → %11111111)
byte := (old & ANDM) | ORB
```

### 5.6 Span fill

Bytes, not pixels. For scanline y and span `[xa, xb)`:

- `rowaddr[y]` (a 200-entry 16-bit table, `tables.inc`) gives the bitmap
  address of cell column 0 on that row — **no multiply**.
- `xoff8[c]` (40 entries, 16-bit) is `8·c`; `BMPPTR = rowaddr[y] + xoff8[ca]`
  once, then `+8` per cell.
- The first and last cells are masked with `leftmask[xa & 3]` /
  `rightmask[(xb-1) & 3]`; the cells between run in a tight loop with no
  edge test.
- A second pass over the same cells stamps the section palette:
  `screen[(y>>3)·40 + c] = (c01<<4) | c10` and `colram[...] = c11`, indexed by
  Y through `SCRPTR`/`COLPTR` from a 25-entry row table.

The attribute pass is per row, which stamps each cell up to 8 times. That is
the price of stamping *exactly* the cells the shape covers rather than its
bounding box (§3). Whether it is worth optimizing is a measurement, not a
guess: the audit profiles `spanfill` and decides.

No ROM call occurs anywhere in the rasterizer.

---

## 6. Music

### 6.1 Clock

A single **CINV wedge** at `$0314`, chaining to `$EA31`, so the sequencer
runs once per frame at 60 Hz and the KERNAL keeps the jiffy clock and the
keyboard scan — the demo needs `$CB` live for the restart key. This is the
cookbook's IRQ-wedge recipe. `oldvec` must not land on a `$xxFF` low byte
(the `jmp (indirect)` page bug); checked in the label file at build time.

Raster-chasing is out of scope (`docs/graphics-and-sprites.md` §1); this is
one interrupt per frame and nothing depends on hitting an exact scanline.

### 6.2 How music and painting coexist

**The IRQ keeps time; the main loop paints.** The sequencer never
rasterizes. When it gates a note on a voice selected by the section's
`spawnmask`, it pushes a request onto a 16-entry ring buffer; the main loop
pops and paints. A shape that takes twenty frames therefore cannot stretch a
note — it can only make the queue deeper.

**A full queue drops, and counts.** `dropped` increments instead of the
queue backing up, so shapes can never lag the music. `dropped == 0` across a
full run is an acceptance criterion (§12, A10): it is the measurement that
proves the shape budget fits the arrangement, which is exactly the "a shape
that takes longer than its note is a bug you find by measuring" rule.

### 6.3 Score format

Each section owns three voice streams. A stream is a sequence of
`(note, duration)` byte pairs:

| note byte | meaning |
|---|---|
| `0` | rest for `duration` frames |
| `1-72` | C1..B6 — gate on, hold, release 3 frames early |
| `$FD` | cannon shot (§6.6) |
| `$FF` | end of stream — rewind to the section's stream head (ostinato) |

`duration` is in frames. A section ends on its own frame budget, not on its
streams, so the three voices need no common length.

`notefreq` is a 72-entry 16-bit table of SID frequency values,
`round(f · 16777216 / 1022730)` for the NTSC clock
(`references/hardware.md`, "Sound"), generated by `tools/gentables.py`.

### 6.4 The arrangement

An original three-voice reduction, composed for this demo. The 1880 score is
public domain; the *Marseillaise* (1792) likewise. No existing SID, MIDI or
sheet arrangement is transcribed — the themes are reduced from their melodic
outlines.

| # | Section | Frames | Time | Material | V1 | V2 | V3 |
|---|---|---|---|---|---|---|---|
| 0 | Hymn — *O Lord, Save Thy People* | 2400 | 40 s | E minor, ~50 bpm; struck quarters, the held tonic rolled | piano — pulse PW $0800, **sustain 0** — the chant, right hand | the *same* instrument row — the left hand, entering on tick 849 | silent; the opening is one instrument |
| 1 | Marseillaise | 1500 | 25 s | G major, ~112 bpm, dotted march | **sawtooth reed** — the anthem's rising fourth and dotted anacrusis | the piano — chords | the piano — marching bass on the beat, entering on tick 495 |
| 2 | Battle | 2100 | 35 s | chromatic, ~150 bpm, sixteenths | sawtooth through the band-pass — running figures | pulse, narrow PW — stabs against the beat | sawtooth — driving octave bass |
| 3 | Cannon | 1800 | 30 s | the hymn fragment over artillery | triangle — the hymn returning, wide-spaced | sawtooth — sustained chords | **noise through the low-pass**, 16 shots |
| 4 | Finale | 2400 | 40 s | E major, ~120 bpm, the hymn in triumph | pulse, swept PW — the hymn, doubled up an octave | sawtooth — countermelody | **ring-modulated triangle** — bells |
| 5 | Hold | ∞ | — | silence; volume 0 | — | — | — |

Total 10,200 frames = **170 s = 2 min 50 s**.

**The texture arc is the design, not a side effect of the voice count.** The
piece opens on one instrument and gains them — 1 → 2 → 3 → 2 + artillery →
3 → 0 — so the finale's full texture is *arrived at* rather than merely
present. Section 0 is a solo piano whose two hands share a byte-identical
instrument row (only `secpw` parts them); section 1's reed is a second
instrument over that piano, not a re-voicing of it. The two late entries are
exact and load-bearing: the left hand enters on section 0's tick 849, the tick
the right hand begins its second phrase, and the bass hand on section 1's tick
495, the tick the anthem repeats. A piano row has **sustain 0**, so a note
stops sounding when its decay completes whatever its duration byte says — that
nybble is what separates a struck instrument from an organ, and it is asserted
(§12 A16). Both entries were read off the captures as well as the shadow:
`AUDIT.md` iteration 3.

Per-voice instruments are a table of `(waveform, attack/decay,
sustain/release, PW lo, PW hi)` indexed by section and voice — the ADSR
nybbles are the ones in `references/hardware.md`'s envelope-rate and
instrument tables, not invented.

### 6.5 Every SID write is shadowed

The SID is write-only, so a single `sidput` routine (X = register offset
`$00-$18`, A = value) does `sta $D400,x` **and** `sta sidshadow,x`. Nothing
else writes the SID. `sidshadow` is 25 bytes at a labeled address and is the
only testable evidence that sound happened.

### 6.6 The cannon

A `$FD` event in section 3's V3 stream, sixteen of them, each carrying a
duration byte of 112. **112 is the duration, not the interval**: an event owns
duration + 1 ticks, so the shots arrive **113 ticks apart**, on section-3 ticks
1 + 113(k−1) (`music.s:717-727`). Sixteen of them ask for 1,808 ticks against
the section's 1,800, so shot 16 is truncated by 8 and its gate-off falls to
section 4's `loadinstr`; `cannons` still reads 16 either way, because it
increments at the fetch. Each shot does:

1. V3 control ← noise + gate (`$81`), ADSR attack 0 / decay `$A`,
   sustain 0 / release `$8`.
2. `$D417` routes voice 3 into the filter (bit 2); `$D418` selects low-pass
   (bit 4) with volume 15.
3. `cutoff` is set to `$FF` and swept **down** to `$10` over 24 frames by the
   sequencer, one step per frame, written to `$D416`.
4. `flash` ← 6. While `flash > 0`, `$D020` and `$D021` are white (1) —
   border included — and both return to 0 when it expires. Because `00` is
   the unpainted ink, the whole screen flashes.
5. One large shape (size 70-90) and six small ones (size 8-20) are pushed
   onto the spawn queue.
6. `cannons` increments. It must read exactly 16 at the end of the section.

### 6.7 The bells

Section 4's V3 is triangle + ring-mod (control `$15`), which
ring-modulates against voice 2's oscillator
(`references/hardware.md`, "SID technique"). Envelope is attack 0 /
decay `$A`, sustain 0 / release `$0` — bright, fast decays, no sustain.

---

## 7. Randomness

A **16-bit Galois LFSR** in software. `$D41B` is not used: reading it means
giving voice 3 over to noise for the whole run, and voice 3 is never spare —
it carries an instrument in sections 1, 2 and 4, and the artillery in section
3. (It *is* silent in the hymn, where the arc opens on one instrument, but a
voice that is silent for one section cannot be traded away for all five.)

```
rng >>= 1 ; if the shifted-out bit was 1: rng ^= $B400      (period 65535)
```

**Values are drawn by scaling, not by rejection.** `rndlt(bound)` returns
`(rnd · bound) >> 8`. Reject-and-retry is the textbook answer and it is wrong
on a shift register: consecutive outputs differ by one shift, so rejecting
until a value falls below a small bound stops almost always on the same
bit pattern — measured, two of the eight dither patterns never appeared in a
whole 889-shape run. It is also slow, at `256/bound` draws. Scaling reads the
freshly shifted-in high bits, in one draw. See `AUDIT.md`, iteration 1.

`seed` is a 16-bit value in `DATA` at a labeled address, default `$1812`.
Init copies it into `rng`; a zero seed is forced to 1.

**Reproducibility you can set.** A test writes `seed` *before* the program
runs: `autorun: false` loads without running, `poke: {addr: seed, ...}` sets
it, then `key: "run\n"` starts it. Same seed → same canvas, byte for byte
(§12, A9).

The restart key mixes the jiffy clock at `$A2` into `seed`, so a restart is
a genuinely different picture.

---

## 8. Observable state

All at labeled addresses, exported in `1812.lbl` by `c64 build`, so tests
and `c64 until` name the signal instead of hard-coding an address.

| Label | Size | Meaning |
|---|---|---|
| `seed` | 2 | RNG seed — **written before RUN** to pin a run |
| `rng` | 2 | live LFSR state |
| `frames` | 2 | frames since the run started |
| `section` | 1 | 0-5, the current section |
| `secframe` | 2 | frames elapsed inside the current section |
| `noteidx` | 1 | events consumed from V1's stream this section |
| `shapes` | 2 | shapes completed — monotonic, never reset except on restart |
| `dropped` | 1 | spawn requests dropped because the queue was full |
| `cannons` | 1 | cannon shots fired |
| `flash` | 1 | frames of screen flash remaining |
| `painting` | 1 | 1 while the rasterizer is inside a shape |
| `qhead` `qtail` | 1 each | spawn ring buffer indices |
| `lstype` | 1 | last shape: type 0-9 |
| `lssize` | 1 | last shape: size (screen-pixel radius) |
| `lsx` `lsy` | 1 each | last shape: center, multicolor x / screen y |
| `lsangle` | 1 | last shape: angle 0-255 |
| `lspat` | 1 | last shape: dither pattern 0-7 |
| `lsink` | 1 | last shape: ink bit-pair 1-3 |
| `lsbytes` | 2 | bitmap bytes the last shape wrote — the cost proxy |
| `typeseen` | 2 | bitmask of shape types drawn so far; `$03FF` = all ten |
| `patseen` | 1 | bitmask of dither patterns used; `$FF` = all eight |
| `sidshadow` | 25 | shadow of `$D400-$D418` |

Code anchors, exported as labels for `c64 until`:

| Label | Fires |
|---|---|
| `seqtick` | top of the sequencer — **once per frame**, the frame anchor |
| `drawshape` | entry to the rasterizer, parameters already chosen |
| `shapedone` | a shape has finished painting |
| `cannonfire` | a `$FD` event is being executed |
| `secchange` | the section index has just advanced |

`mainloop` is *not* a frame anchor — it spins while the queue is empty.
Anchor frame counts on `seqtick`.

---

## 9. File layout

| File | Contents |
|---|---|
| `1812.s` | load address, BASIC stub, equates, init, main loop, includes |
| `vars.s` | every mutable byte, including the observable block of §8 |
| `tables.inc` | generated: sin table, row-address table, x-offset table, note table |
| `shapes.s` | unit vertex tables, dither masks, edge masks |
| `raster.s` | multiply, vertex transform, edge build, AET, scanline fill, span fill |
| `spawn.s` | LFSR, spawn queue, per-section shape policy |
| `music.s` | sequencer, `sidput`, instrument tables, the score |
| `sections.s` | section table: lengths, palettes, shape sets, size ranges, spawn masks |
| `tools/gentables.py` | emits `tables.inc` (stdlib only, runnable standalone) |
| `tools/litcount.py` | lit-pixel count and checksum from a `c64 mem read --json` dump |
| `tools/evidence.sh` | the deterministic proof protocol of §11 |
| `tools/genscore.py` | emits the reference scores of §11.1 from `music.s`'s own streams |
| `tools/audio-evidence.sh` | the audio protocol of §11.1 |
| `test.yaml` | the regression test of §10 |

Every included file opens with an explicit `.segment` directive — ca65 does
not reset the active segment across `.include` (`6502-assembly` skill,
gotchas).

---

## 10. Regression test (`test.yaml`)

Asserts memory, registers and state bytes — **never PNG pixels**
(`docs/graphics-and-sprites.md` §4):

- the five mode registers of §2.1, with the 4-bit and unused-bit masks;
- `$2000` reads all zero at the first `drawshape` stop (the canvas starts
  black);
- `section` progresses 0 → 1 → 2 → 3 → 4 → 5 at the frame boundaries;
- `shapes` is strictly increasing across `until seqtick` stops
  (`greater_than` against a `sample`, never an equality);
- `dropped` is 0 at the end;
- `cannons` is 16 after section 3;
- `typeseen == $03FF` and `patseen == $FF` by the finale;
- the seed is poked before RUN and the same seed reproduces the same `rng`,
  `shapes` and last-shape bytes at the same frame count;
- `sidshadow` shows a gated noise waveform on voice 3 during a cannon and a
  ring-modulated triangle during the finale;
- the texture arc, section by section: inside the hymn voice 1 is gated while
  voices 2 and 3 are not, both piano hands hold a sustain nybble of 0, and
  voice 3's frequency registers still read `0000` late in the section — while
  in the battle all three voices are shown to have sounded.

---

## 11. The deterministic proof protocol

`tools/evidence.sh`, re-runnable, starts and stops its own
`--warp --headless` session. Every capture is taken while the machine is
**stopped** at a `c64 until` label, per `docs/graphics-and-sprites.md` §5;
screenshots are `--scale 2 --border` PNGs under `demos/1812/evidence/`.

| Evidence | Stop | Artifact |
|---|---|---|
| black canvas before the first shape | `until drawshape` | `blank.png` + `litcount == 0` |
| one shape and the bytes that made it | `until shapedone` | `first-shape.png` + `lstype/lssize/lsx/lsy/lsangle/lspat/lsink` |
| the same type at three rotations | forced `lsangle` at three spawns | `rot-a.png` `rot-b.png` `rot-c.png` |
| the canvas at the end of each section | `until secchange` | `sec0.png` … `sec4.png` |
| a cannon flash | `until cannonfire`, `flash > 0` | `cannon.png` + `$D020`/`$D021` |
| the finished canvas | `until seqtick` at frame 10,200 | `final.png` |
| SID mid-cannon and mid-finale | the same stops | `sidshadow` dumps in the run log |
| nothing is ever cleared | 6 samples across the run | monotone `litcount`, and 64 addresses lit in section 0 still lit at the end |

Lit-pixel counting is done by `tools/litcount.py` over a
`c64 mem read --json '$2000' 8000` dump — counted off the dump, not by eye.

### 11.1 The audio protocol

The picture's protocol cannot say anything about the sound, so there is a
second one: `tools/audio-evidence.sh`, also re-runnable, also owning its own
`--warp --headless` session — but **each capture window takes the machine off
warp**, because a capture is a recording and a warped window writes a
zero-frame WAV. The five windows are therefore real time, and the run is long
by construction. One window per section, each opening on that section's first
tick, into
`demos/1812/evidence/audio/SECTION/`:

| Artifact | What it is |
|---|---|
| `capture.wav` | the audio itself, for a human to listen to |
| `sid-log.jsonl` | the per-frame SID log the verdict is computed from |
| `report.md` | `c64 audio report` against the section's reference score |
| `piano-roll.png` | voices 1/2/3 as red/green/blue — reads the entries and contours |
| `spectrogram.png` | the frequency picture — where the cannon's broadband burst and its downward cutoff sweep can be seen at all |

The five reference scores (`evidence/audio/*.score.yaml`) are **generated from
the note streams by `tools/genscore.py`, not transcribed from a capture** —
`--check` re-derives them and fails if they have drifted from `music.s`. A
score that was fitted to a recording proves nothing about the arrangement, and
this one is deliberately built the other way round.

---

## 12. Acceptance criteria

Each is an observation on a stopped machine — **except A15**, which is the one
criterion that cannot be one, and says why.

- **A1 — mode.** At any stop after init: `$D011 & $7F == $3B`,
  `$D016 & $1F == $18`, `$D018 & $FE == $18`, `$D020 & $0F == 0`, and
  `$D021 & $0F == 0` whenever `flash == 0`.
- **A2 — the canvas starts black.** At the first `drawshape` stop, all 8,000
  bytes of `$2000-$3F3F` are `$00` (`litcount == 0`).
- **A3 — the counter only rises.** `shapes` sampled at ten `seqtick` stops
  spread across the run is non-decreasing, and ends above 300.
- **A4 — sections progress.** `section` reads 0, 1, 2, 3, 4, 5 at
  `seqtick` counts 1, 2401, 3901, 6001, 7801, 10201 (±1 frame).
- **A5 — rotation is real.** Three shapes of the same `lstype` at
  `lsangle` values 0, 48 and 96 produce three different bitmaps; a rotated
  rectangle reads as a diamond and a rotated ellipse tilts. Evidenced by
  three PNGs plus the three state-byte sets.
- **A6 — nothing is ever cleared.** `litcount` is non-decreasing across six
  samples spanning the run, and a fixed set of 64 bitmap addresses that are
  lit at the end of section 0 are still lit at frame 10,200.
- **A7 — the cannon.** `cannons == 16` at the end of section 3; at a stop
  with `flash > 0`, `$D020 & $0F == 1` and `$D021 & $0F == 1`; both are 0
  again within 8 frames.
- **A8 — sound happened.** Mid-cannon, `sidshadow+$12` (voice 3 control)
  has bit 7 (noise) and bit 0 (gate) set and `sidshadow+$17` routes voice 3
  through the filter with `sidshadow+$18` in low-pass; mid-finale,
  `sidshadow+$12` has bit 4 (triangle) and bit 2 (ring mod) set. Volume
  (`sidshadow+$18 & $0F`) is 15 while playing and 0 in section 5.
- **A9 — determinism.** Two runs with `seed` poked to the same value before
  RUN reach identical `rng`, all seven last-shape bytes, an identical
  lit-pixel count and an identical bitmap checksum **at the same `shapedone`
  count**. Two runs with different seeds differ in all of them.
  The anchor is a *shape* boundary, not a frame boundary: a frame boundary
  can fall inside a half-painted shape, and the two passes would then be
  compared at different points of the same sequence rather than at the same
  point — measured, and it is the reason this criterion names `shapedone`.
- **A10 — the budget fits.** `dropped == 0` at frame 10,200.
- **A11 — the vocabulary is used.** `typeseen == $03FF` and
  `patseen == $FF` by the end of the finale.
- **A12 — the hold and the restart.** At frame 10,201: `section == 5`,
  `sidshadow+$18 & $0F == 0`, and `shapes` unchanged 120 frames later.
  Poking `$CB` with a matrix code then resets `shapes` to 0, clears the
  bitmap and yields an `rng` different from the previous run's.
- **A13 — cost is measured, not guessed.** `c64 profile` reports cycle
  counts for `smul`, `spanfill` and a worst-case `drawshape`, and those
  numbers appear in `AUDIT.md`. A single shape must not exceed the queue's
  ability to keep `dropped` at 0 (A10 is the binding test).
- **A14 — it ships.** `c64 package` produces `demos/1812/1812.d64`, which
  autostarts in stock VICE with `x64sc -ntsc demos/1812/1812.d64`, and the
  program ends below `$2000`.
- **A15 — the arrangement is heard, and by both halves.** The SID shadow (A8)
  proves a register was written; it cannot prove the piece plays. So:
  **(a) the machine's half** — `tools/audio-evidence.sh` produces the five
  captures of §11.1, one per section (hymn, Marseillaise, battle, cannon,
  finale), and every `report.md` reads **PASS** against that section's
  generated reference score with `nothing_played` false, no diffs and no
  anomalies, over a `capture.wav` of real duration with no clipped samples.
  **(b) the human's half** — a maintainer with speakers listens to those five
  WAVs, in order, and says whether the reduction reads as the *1812 Overture*.
  **Neither half substitutes for the other**, and the listen's verdict is
  recorded in `AUDIT.md` like any other. A score claims each voice's **event
  sequence**, rests included, and not its durations: the sequencer's jiffy
  clock (60.0016 Hz) and the log's frame clock (59.826 Hz) differ by 0.3%, so
  timing claims are made as measurements in `AUDIT.md`, not as score entries.
- **A16 — the piano is struck, not held.** At a stop inside section 0, the
  sustain nybble of both piano voices' SR bytes in the SID shadow reads 0 —
  `sidshadow+6 & $F0 == 0` and `sidshadow+13 & $F0 == 0`, voice *n*'s registers
  being at offset `7n` — and voice 3's frequency registers (`sidshadow+14`)
  still read `0000`, so the opening really is one instrument. A non-zero
  sustain *level* is the single thing that makes a SID voice read as an organ
  rather than as a struck string, so this is the texture arc's testable core.

---

## 13. Out of scope

- Raster splits and any effect needing an exact scanline
  (`docs/graphics-and-sprites.md` §1).
- Golden-image pixel diffs — ruled out repo-wide (§6 of the same file);
  every claim here is registers, state bytes or a counted dump.
- Joystick input: the emulator cannot inject it, so the restart key is
  `$CB` only.
- PAL. The demo is built and tested on the NTSC machine, and the note table
  is computed for the NTSC clock; the run command pins `-ntsc`.
