# Amiga Ball — specification

The 1984 Amiga **Boing Ball**, on a Commodore 64: a red-and-white checkered
sphere bouncing in a wire-grid room, spinning about its vertical axis, with a
contact shadow on the floor and a synthesised "boing" on every impact.

This document states *what* is built and *why* each number is that number. It
is the list `AUDIT.md` scores the build against; §14 is that list. Every
hardware fact is cited to the reference that carries it.

---

## 1. What the Amiga did, and what this does instead

The Amiga drew the sphere into a bitmap every frame: a texture-mapped,
Lambert-shaded ball, double-buffered, redrawn by the blitter and the CPU
together. The C64 has neither a blitter nor the bandwidth. A 96×72 region is
6,912 pixels; at multicolor bitmap resolution that is 1,728 bytes to write per
frame, and the whole NTSC frame is 17,095 cycles. A store is 4-5 cycles even
before the pixel is computed. It cannot be done, and a demo that tries drops
frames and looks worse than one that does not.

So three deliberate deviations from the original, each of which is *the better
C64 demo*:

| Amiga | Here | Why |
|---|---|---|
| Sphere rasterised into a bitmap each frame | Four **hardware sprites** carrying pre-generated art | The VIC-II draws sprites for free. Moving the ball costs 6 register writes, not 1,728 stores. |
| Rotation computed per frame from geometry | **16 pre-generated rotation frames**, switched by the four sprite pointers | Switching a frame costs 4 stores. The texture mapping still happens — once, in `tools/generate.py`, at full float precision, instead of 60 times a second in 8-bit integers. |
| Shaded sphere (a continuous light term) | Two checker colors plus a **one-texel dark rim** | Multicolor sprites carry exactly three colors plus transparent. The rim buys the silhouette, which is what shading was mostly doing at this size. |
| Grid drawn as vector lines into the bitmap | Grid drawn with a **custom character set** | A static backdrop has no business spending 8 KB and a per-frame budget. The charset is 2 KB and costs zero frame time. |

The one thing that is *not* a deviation: the ball really is texture-mapped.
`tools/generate.py` casts a ray per sprite texel, intersects the unit sphere,
converts the hit point to latitude/longitude, and applies the frame's rotation
offset before deciding checker parity (§5). The result is committed as
`.byte` rows, per `docs/graphics-and-sprites.md` §2.

---

## 2. Memory map

The VIC-II sees only bank 0, `$0000-$3FFF`, and the toolset requires the screen
at `$0400` (`references/memory-maps.md`; `references/hardware.md`, "VIC bank and
interrupts"). Everything the chip reads — charset, sprite blocks — must live
there.

| Range | Bytes | Contents |
|---|---:|---|
| `$0000-$00FF` | 256 | Zero page. This program uses `$FB-$FE` (the two free user pointers, `references/zero-page.md`) during init only; the IRQ uses none. |
| `$0400-$07E7` | 1000 | Screen matrix — the room. |
| `$07F8-$07FF` | 8 | Sprite data pointers. |
| `$0801-$080C` | 12 | BASIC stub, `10 SYS 2061` (§12). |
| `$080D-$1FFF` | 6,131 | `CODE` + `RODATA` + `DATA` — the program, the screen-matrix source, the bounce table, the sound tables. `ld65` caps `MAIN` here, so an overflow is a **link error**, not a wrong-pixels mystery. |
| `$1000-$1FFF` | — | *(overlapped by the above, and that is fine: this is a CPU-side range.)* The character ROM's 4 KB image is what the **VIC** sees here, which is why the charset is not at `$1000` or `$1800` — see the note below. |
| `$2000-$27FF` | 2,048 | `CHARS` area — the RAM character set, 256 glyphs. |
| `$2800-$37FF` | 4,096 | `SPRITES` area, part 1 — 16 rotation frames × 4 blocks × 64 bytes. Blocks **160-223**. |
| `$3800-$39FF` | 512 | `SPRITES` area, part 2 — 4 shadow sizes × 2 blocks × 64 bytes. Blocks **224-231**. |
| `$3A00-$3FFF` | 1,536 | Free (blocks 232-255). Declared but unused; see §5 for what it would buy. |
| `$4000-$403E` | 63 | `VARS` area — every observable byte (§9). Outside bank 0 on purpose: the VIC never reads it. `.res` inside an area ships as zeros (the segment is linked `type = ro`), so every counter starts at 0 with no init loop. |

**The charset base trap.** Bank 0 offers eight 2 KB charset bases, and the
character ROM's image is **4 KB** (`$1000-$1FFF`), which covers *two* of them:
`$1000` and `$1800` are both unusable, and `$1800` fails silently by drawing the
ROM's lowercase glyphs (`references/memory-maps.md`; `references/hardware.md`,
"VIC bank and interrupts"). That leaves `$2000`, `$2800`, `$3000`, `$3800`. This
demo takes `$2000` and gives the remaining 6 KB to sprite blocks in one run.

**`$D018` = `$18`.** Bits 7-4 are the screen base in 1 KB steps: `$0400/$0400`
= 1 → `$10`. Bits 3-1 are the character base in 2 KB steps: `$2000/$0800` = 4,
shifted left one → `$08`. Together `$18`. **It reads back as `$19`** — bit 0 is
unused and reads as 1 (cookbook, "Custom character set"), so the test compares
against `$19` or masks with `$FE`.

**Build line.** Three areas, contiguous and ascending, per `c64 build --area`:

```sh
c64 build demos/amiga_ball/amiga_ball.s \
    --area 'CHARS=$2000:$0800' \
    --area 'SPRITES=$2800:$1800' \
    --area 'VARS=$4000:$0100'
```

`CHARS` and `SPRITES` are filled to their declared sizes because they are not
the last area; `VARS` is last, so only its real content ships. The `.prg` is
therefore 14,337 bytes of padded low memory (the figure `docs/cli.md` measures
for La Galaxia's three areas: "the 2-byte load header plus every address from
`$0801` to `$3FFF`") plus `VARS`' 71 bytes ≈ 14.4 KB. That padding is the price
of putting the charset on its 2 KB boundary and the sprite blocks on their
64-byte ones, which is exactly the case `skills/6502-assembly/SKILL.md` says to
reach for `--area` for.

---

## 3. The ball: geometry, and why it is round

### 3.1 Pixel aspect ratio

320×200 pixels are not square. On the NTSC machine:

- Dot clock 8.181816 MHz; an NTSC line's active picture is 52.6 µs, so the 4:3
  raster is 52.6 × 8.181816 ≈ **430 dots** wide.
- Of 262.5 lines per field, ≈ **240** are active picture.

So one C64 pixel is `(4/3)/430` wide and `1/240` tall in picture units:

```
PAR = pixel_width / pixel_height = ((4/3)/430) / (1/240) = 0.7435
```

A pixel is about three-quarters as wide as it is tall. **A circle therefore
needs `width = height / 0.7435 = 1.345 × height` in pixels.** (This is the
familiar "NTSC C64 PAR ≈ 0.75". The PAL machine's is ≈ 0.94; the bounce table
and this arithmetic are both written for NTSC, which is why the run command
pins `-ntsc`.)

### 3.2 The sprite block

Four sprites in a 2×2 grid, **all four multicolor** (`$D01C`) and **all four
expanded in both axes** (`$D017` and `$D01D`).

| | Value | Note |
|---|---|---|
| Sprite grid | 2 wide × 2 tall | sprites 0=TL, 1=TR, 2=BL, 3=BR |
| Texels across | 24 | multicolor halves horizontal resolution to 12 pixel-pairs per sprite (`references/hardware.md`, "Sprites") |
| Texel rows | 42 | 2 × 21 |
| Texel size on screen | 4 px wide × 2 px tall | X- and Y-expansion double each axis |
| Block on screen | 96 × 84 px | 24×4 by 42×2 |

The sphere does **not** fill all 42 rows. It occupies texel rows **3-38**
(36 rows) and all 24 columns:

```
sphere on screen = 24 texels x 4 px = 96 px wide
                 = 36 rows   x 2 px = 72 px tall
roundness        = 96 / (72 x 1.345) = 0.991     <- 0.9% off a true circle
```

Three blank texel rows above and three below are what make it round. Had the
sphere filled the block, it would be 96×84 — 11% too tall, a visible egg.

**Why expanded.** Expansion changes no data: the texel grid is 24×36 either
way, and the unexpanded ball would be 48×36 with the identical roundness.
Expansion buys size for free — the ball becomes 30% of the screen width,
which is the scale the Amiga original reads at — at the cost of 4×2 px texels.
The checkers are 4-5 texels across at the sphere's centre (§5), so the
chunkiness lands on the color boundaries, not inside them.

### 3.3 Colors

Multicolor bit-pair → color (`references/hardware.md`, "Sprites"):

| Pair | Register | Value | What it is |
|---|---|---|---|
| `00` | — | transparent | outside the sphere |
| `01` | `$D025` (shared MC 0) | `$00` black | **the rim** — a one-texel dark outline at the limb |
| `10` | `$D027-$D02A` (per sprite) | `$02` red | red checker |
| `11` | `$D026` (shared MC 1) | `$01` white | white checker |

`$D025`/`$D026` are shared by every multicolor sprite, so red must be the
*per-sprite* color; all four ball sprites get `$02`.

**What the third color bought.** A dark rim, not a shading tone. At 4×2 px
texels the sphere's limb is where the eye reads "sphere"; against a purple grid
line a red or white checker at the limb loses its edge. The rim is one texel
wide, always present, and independent of where the ball is — a guarantee a
Lambert term cannot make. The cost is that the ball is not shaded: it reads as
a *flat* checkered disc lit head-on, which is what the Amiga ball also looks
like in the frames where the light is behind the camera.

---

## 4. The room

25 text rows, divided:

| Rows | Rasters | Plane | Color RAM |
|---|---|---|---|
| 0-14 | 51-170 | back wall | `$04` purple |
| 15 | 171-178 | wall foot / horizon | `$0E` light blue |
| 16-24 | 179-250 | floor | `$0E` light blue |

Background `$D021` = `$00` black, border `$D020` = `$00` black. Standard text
mode: `$D011` = `$1B`, `$D016` = `$08` (reads back `$C8` — bits 6-7 are unused
and read as 1).

**Palette justification.** The Amiga's grid was magenta/violet on black. The
C64 has exactly one purple, `$04`, and it is dark. Keeping it for the *wall*
holds the reference; giving the *floor* light blue `$0E` makes the color change
itself the horizon, so the two planes separate without the ball ever having to
cross an ambiguous line — and it keeps the floor legible under the shadow,
which is the one place low contrast would cost something.

### 4.1 The wall grid

Vertical lines at columns 0, 4, 8, …, 36 (10 lines, 32 px apart).
Horizontal lines at rows 0, 3, 6, 9, 12 (5 lines, 24 px apart), closed at the
bottom by the horizon at row 15.

```
wall cell = 32 px wide x 24 px tall
          = 32 x 0.7435 = 23.8 picture units wide
          =              24.0 picture units tall
```

Square to within 1%. That is why the spacing is 4 columns by 3 rows and not
something rounder-looking in cells.

### 4.2 The floor

A floor whose grid spacing does not change with distance is a wall lying down,
so the floor is a real perspective projection with its vanishing point on the
horizon at screen (x=160, y=171).

**Depth lines** (lines of constant distance) sit at

```
y(d) = 171 + K/d ,  K = 79 ,  d = 1,2,3,4,5,6,8,10
```

| d | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | ∞ |
|---|---|---|---|---|---|---|---|---|---|
| raster | 250 | 210 | 197 | 191 | 187 | 184 | 181 | 179 | 171 |
| row.offset | 24.7 | 19.7 | 18.2 | 17.4 | 17.0 | 16.5 | 16.2 | 16.0 | 15.0 |

The lines pile up toward the horizon and spread toward the viewer — three of
them land inside row 16 and four rows near the bottom carry none, which is what
perspective looks like and what a uniform grid cannot produce. The 8-pixel-tall
character cell is what makes this expressible: a horizontal rule can sit on any
of the cell's 8 scanlines, so the generator places each line at its exact
raster.

**Convergent lines** run to the vanishing point. Five of them, spaced 80 px
apart where they meet the bottom of the screen:

```
x(y) = 160 + j * (80/79) * (y - 171) ,  j = -2,-1,0,1,2
```

At y=250 that is x = 0, 80, 160, 240, 320 — the whole visible width. The
generator rasterises each line into the 8×8 cells it crosses, so the
convergence is drawn at pixel granularity, not stair-stepped per row.

**The grid is square on the ground.** With the depth constant K = 79 px and a
bottom spacing of 80 px, and correcting the horizontal for PAR:

```
physical column spacing at d=1 = 80 x 0.7435 = 59.5 units = C
camera height H = K / C = 79 / 59.5 = 1.33 ground cells
```

so the ground cells are 1×1 and the eye sits 1.33 cell-widths above the floor —
a consistent projection, not a set of lines that merely lean.

### 4.3 The charset

All 256 glyphs are **generated**; nothing is copied from the character ROM, so
there is no `$01` banking dance and no interrupt window to protect. Glyph 0 is
blank, which means a screen matrix of zeros is an empty room. `tools/generate.py`
rasterises every wall and floor cell, deduplicates the resulting 8-byte
patterns, assigns codes in first-use order, and **fails if the count exceeds
256**. The screen matrix it emits (1000 bytes, `screen.inc`) is copied to
`$0400` at init; color RAM is filled by row range, no table.

---

## 5. Rotation: the generator, the frame count, and the pointer trick

### 5.1 The texture

16 longitude segments (22.5° each) × 8 latitude bands (22.5° each); checker
parity is `(lon_index + lat_index) & 1`. This is the Boing Ball's own
checkerboard.

### 5.2 The ray cast

For texel (column `c` in 0-23, row `r` in 0-41), with the sphere centred at
**(12.0, 21.0)** with radii 12 texels and 18 rows:

```
nx = (c + 0.5 - 12.0) / 12
ny = (r + 0.5 - 21.0) / 18
if nx^2 + ny^2 > 1 :  transparent
nz  = sqrt(1 - nx^2 - ny^2)          # the near hit of the ray, z toward viewer
lat = asin(ny)                       # spin axis is vertical, poles top/bottom
lon = atan2(nx, nz) + rot            # rot = this frame's rotation offset
lat_index = floor((lat + pi/2) / (pi/8))    mod 8
lon_index = floor((lon + 2pi) / (pi/8))     mod 16
color = red if (lat_index + lon_index) & 1 else white
```

A texel is **rim** (`01`, black) instead of a checker if it is inside the
sphere but one of its four neighbours is outside. The rim is applied after the
checker so it always wins at the limb.

**The centre is the block's continuous centre, not its index centre**, and the
difference is not cosmetic. Texel `c` is sampled at `c + 0.5`, so the 24-column
grid spans 0.0-24.0 and its centre is 12.0; the sphere's 36 rows span 3.0-39.0,
so their centre is 21.0. This draft first wrote (11.5, 20.5) — the *index*
centre — and the C64 says what that costs: `nx` runs -0.9167 to +1.0000 instead
of ±0.9583, so the disc's left limb falls at column -1, off the block, and the
equator flattens into a vertical edge about 11 texel rows tall; the sphere also
comes out 37 rows instead of the 36 that §3.2's roundness of 0.991 is computed
from. Caught by the Task 1 implementer against the running machine.

### 5.3 Why 16 frames, and what a frame costs

Rotating a checkerboard by one longitude segment (22.5°) maps every segment
onto its neighbour, whose parity is opposite — so the image is *colour-inverted*.
Rotating by **two** segments (45°) returns the identical image. **The rotation
period of this texture is 45°, not 360°**, so generating a full turn would ship
eight identical copies of everything.

16 frames spanning 45° gives **2.8125° per frame**. At one frame advance per
video frame (`ROT_STEP = 1`):

```
45 deg per 16 frames  ->  360 deg per 128 frames  ->  2.13 s per revolution
```

Storage:

```
1 frame  = 4 sprite blocks = 4 x 64 = 256 bytes
16 frames                            4,096 bytes  (blocks 160-223, $2800-$37FF)
4 shadow sizes x 2 blocks              512 bytes  (blocks 224-231, $3800-$39FF)
                                     -----------
used of the 6,144-byte SPRITES area  4,608 bytes
left over                            1,536 bytes  = 24 blocks
```

The 24 spare blocks are real slack, deliberately unspent: six more rotation
frames would take the step to 2.05° and change nothing a viewer can see at
4-px texels, and the alternative — a second shadow set or a wall-impact
squash — is not in this brief.

### 5.4 Switching a frame costs four pointer writes

Sprite pointers live at `screen+$3F8` = `$07F8-$07FF`, and hold
`block = address / 64` (`references/hardware.md`). Frame `f` uses blocks

```
TL = 160 + 4f    TR = 161 + 4f    BL = 162 + 4f    BR = 163 + 4f
```

so switching frames is four `sta $07F8+n`. The alternative — copying 4×63 =
252 bytes into a fixed block every frame — costs ~1,300 cycles (a `lda`/`sta`
pair per byte plus loop overhead), which is 7.6% of the NTSC frame, to achieve
precisely the same picture. The pointers are the reason all 16 frames can be
resident at once, and the reason the frame budget in §11 is what it is.

---

## 6. Physics

### 6.1 Vertical: a parabolic bounce table

`P = 64` frames per bounce (1.067 s at 60 Hz). Sprite-0 Y at phase `p`:

```
y(p) = Y_FLOOR - A * 4 * p * (P - p) / P^2
     = 158 - 104 * p * (64 - p) / 1024
```

| p | 0 | 8 | 16 | 24 | 32 | 40 | 48 | 56 | 63 |
|---|---|---|---|---|---|---|---|---|---|
| y | 158.0 | 112.5 | 79.0 | 57.5 | 54.0 | 57.5 | 79.0 | 112.5 | 151.6 |

Stored as **8.8 fixed point**, 64 entries × 2 bytes = 128 bytes (`bounce.inc`),
generated by `tools/generate.py`. Impact is the wrap from `p = 63` to `p = 0`.

**Parabolic, not sinusoidal.** `d²y/dp² = 8A/P² = 0.203 px/frame²` — a constant,
which is what free fall is. A sinusoid's acceleration is largest at the apex and
zero at the floor: exactly backwards. The two curves differ most where the eye
spends the most time, because a real ball spends most of a bounce near the top,
and a sinusoid rounds that dwell away. Speed at contact is `dy/dp|₀ = 6.5
px/frame`, so the impact frame is visibly fast, which is the other half of the
same tell.

The constant works out to 731 px/s²; at 72 px per ball diameter that is about
0.62 g for a 60 cm ball. The ball is slightly floaty on purpose — so is the
Amiga's, and a full-g bounce at this height would be over in 0.85 s.

**Geometry of the two ends.**

```
sphere top raster    = sprite_y + 6      (3 blank texel rows x 2 px)
sphere bottom raster = sprite_y + 77     (36 rows x 2 px, minus one)
contact:  sprite_y = 158  ->  sphere spans 164-235   (floor, row 23)
apex:     sprite_y =  54  ->  sphere spans  60-131   (wall, above the horizon)
```

Both ends are inside the sprite Y window 50-249 (`skills/6502-assembly/SKILL.md`,
"Sprite invisible?"). The bottom sprite pair sits at `sprite_y + 42` because
Y-expansion makes each sprite 42 rasters tall.

### 6.2 Horizontal: 8.8 constant velocity

`ball_x` is **8.8 fixed point measured from `X_BASE = 24`**, so its integer part
is 0-223 and fits a byte. Sprite X derives:

```
spr0_x = spr2_x = 24 + int(ball_x)          range  24 - 247
spr1_x = spr3_x = spr0_x + 48               range  72 - 295
```

48, not 24, because X-expansion doubles the sprite's width.

Velocity `VX = $01C0` = 1.75 px/frame. A full crossing is `223 / 1.75 = 127.4`
frames = 2.12 s — which is, to within a frame, the ball's own rotation period.
That is a coincidence of two independently chosen constants and it is left in
because it reads well.

The ball stays **fully on screen**: it reverses when its integer part reaches 0
or 223, so no part of it ever leaves the 24-343 visible X window. On reversal:
`VX = -VX`, `spin_dir = -spin_dir`, `wall_count++`.

### 6.3 The X-MSB

`$D010` carries X bit 8, one bit per sprite. Here:

```
spr0_x <= 247  ->  bit 0 always clear, and bit 2 (spr2) with it
spr1_x >= 256  <->  spr0_x >= 208  <->  int(ball_x) >= 184
```

so `$D010` takes exactly two values: `$00`, or `$2A` (bits 1, 3, 5 — sprites 1,
3 and the right shadow half) once the ball's left edge passes 208. The IRQ
rebuilds the whole byte from the comparison every frame rather than
read-modify-writing it; a stale MSB is a ball that teleports 256 pixels, and
rebuilding is 6 cycles cheaper than being careful.

---

## 7. The shadow

Sprites **4 and 5**, side by side, **hires** (not in `$D01C`), **X-expanded**
only. Two 24-px hires sprites at 2× is a 96-px-wide, 21-raster-tall pair —
exactly the ball's width — at 48 horizontal texels, so the ellipse's edge is
finer than the ball's.

- **Position.** `spr4_x = spr0_x`, `spr5_x = spr0_x + 48` — the shadow tracks
  the ball's X exactly, with no lag, because it is derived from the same byte in
  the same frame. `spr4_y = spr5_y = 225`, fixed: the shadow lives on the floor
  plane, not under the ball. Ellipse centre row 10 of 21 → raster 235, the
  contact line.
- **It shrinks.** Four shapes, selected by the ball's height above contact
  `h = 158 - int(ball_y)` (0-104):

  | h | 0-25 | 26-51 | 52-77 | 78+ |
  |---|---|---|---|---|
  | `shadow_size` | 0 | 1 | 2 | 3 |
  | ellipse | 96×14 | 80×12 | 64×10 | 48×8 |

  Blocks `224 + 2*size + half`. A contact shadow is the ball's *contact*, not
  its silhouette: a shadow that stayed the ball's size would say the light is at
  infinity directly overhead, and then the ball would appear to slide rather than
  to leave the ground. Contracting toward the contact point is the cue that
  reads as height without needing a second light or a gradient the C64 cannot
  draw.
- **Color `$0B` dark gray**, and this is a deliberate inversion worth stating:
  the floor's background is black, so nothing can be *darker* than the floor.
  What the sprite provides is a gray contact patch where the black would
  otherwise be — the only way a shadow can exist against black. It reads as
  shadow because of the next point.
- **`$D01B` bits 4 and 5 set.** Character data is drawn *in front of* the
  shadow, so the floor's grid lines run **over** it. That is what puts the patch
  on the floor plane instead of floating above it. The ball's sprites 0-3 keep
  `$D01B` clear, so the ball passes in front of the grid. Sprite-vs-sprite order
  is fixed and not programmable — 0 is always in front, 7 always behind
  (`references/hardware.md`) — which is why the ball is 0-3 and the shadow 4-5
  and not the other way round.

The four sprite-configuration registers, stated exactly:

| Register | Value | Reading |
|---|---|---|
| `$D015` enable | `$3F` | sprites 0-5 on, 6-7 off |
| `$D01C` multicolor | `$0F` | ball multicolor, shadow hires |
| `$D017` double height | `$0F` | ball only |
| `$D01D` double width | `$3F` | ball **and** shadow — the shadow is 96 px wide because of this bit |
| `$D01B` behind data | `$30` | shadow behind the grid, ball in front |

---

## 8. The sound

A struck body is three things at once: a fast bright inharmonic transient, a
pitched thump under it, and a decay. Two SID voices and the filter, one gesture
each.

**Voice 1 — the thump (the body).** Triangle, one pitch per impact, held 20
frames and released. It is the ball's mass. Floor is lower than wall because
the floor is the heavier body:

| | note | Hz | `Fn = round(Hz × 16.40483)` | `$D401`/`$D400` |
|---|---|---|---|---|
| floor | A2 | 110.00 | 1805 | `$07` / `$0D` |
| wall | E3 | 164.81 | 2704 | `$0A` / `$90` |

(`Fn = Hz × 16777216 / 1022727` at the NTSC clock — `references/hardware.md`,
"Sound".) `$D405` = `$08`: attack nybble 0 = 2 ms, decay nybble 8 = 300 ms.
`$D406` = `$00`: sustain level 0, release 6 ms. So the envelope is a pure
decay — the note is over before the gate falls, which is what a struck body
does and why sustain is 0 rather than a level.

**Voice 2 — the transient (the strike).** Noise, gated with voice 1, `$D40C` =
`$04` (attack 2 ms, decay 114 ms), `$D40D` = `$00`. Noise frequency `$1000`
(floor) / `$1800` (wall) — the noise generator's clock, which sets how bright
the hiss is before the filter touches it.

**The filter — the "oing".** Voice 2 is routed through the filter (`$D417` =
`$F2`: resonance 15, routing bit 1 = voice 2), the filter is **low-pass**
(`$D418` = `$1F`: mode bit 4 set, volume 15), and the cutoff sweeps **downward**
over 16 frames. That descending, resonant cutoff on a noise burst is the whole
"boing": it imitates a struck elastic surface whose brightness collapses as the
strike energy leaves it, which is exactly what the Amiga's digitised sample
sounds like and is a gesture the SID can synthesise where it cannot sample.

| | `$D416` start | `$D416` end |
|---|---|---|
| floor | 220 | 30 |
| wall | 250 | 70 |

The wall stays brighter throughout: a wall is a harder, smaller surface.
`cut_floor[24]` and `cut_wall[24]` are generated by `tools/generate.py` as a
linear ramp, and are read one entry per frame.

**Voice 3 is silent.** Its registers are written zero at init and never again,
so the SID shadow's bytes 14-20 read 0 for the life of the run — an assertion,
not an omission.

**Every SID write is shadowed.** The SID is write-only
(`references/hardware.md`), so a stopped machine can say nothing about sound
except through RAM. One routine does every write:

```
sidput:  sta $D400,x
         sta sid_shadow,x
         rts
```

`sid_shadow` is 25 bytes mirroring `$D400-$D418` (§9). The shadow proves the
writes happened. It **cannot** prove the result sounds like an impact — that is
what §13's WAV, spectrogram and piano roll are for, and why this spec has audio
acceptance criteria that a stopped machine cannot settle.

**Schedule.** An impact sets `snd_timer = 0` and `snd_kind`. Each frame while
`snd_timer < 24`: at 0, write both envelopes, both frequencies, `$D417`,
`$D418`, and gate on (`$D404` = `$11` triangle+gate, `$D40B` = `$81`
noise+gate); at 0-15, write `$D416` from the sweep table; at 20, gate off
(`$10`, `$80`); at 24, idle. A new impact inside the window restarts it.

---

## 9. Observable state

Every byte below is in the `VARS` area at a fixed address **and** exported as a
label, so `c64 until`, `c64 mem read`, `test.yaml` and `--at-frame` can each use
whichever form they accept. Addresses are fixed by the `--area` placement, not
by where the code happened to end.

| Addr | Label | Size | Meaning |
|---|---|---:|---|
| `$4000` | `ball_xf` | 1 | X fraction (8.8 low byte) |
| `$4001` | `ball_xi` | 1 | X integer, 0-223, offset from `X_BASE` = 24 |
| `$4002` | `ball_x16` | 2 | absolute sprite-0 X, lo/hi (24-247) |
| `$4004` | `ball_vx` | 2 | X velocity, signed 8.8, lo/hi (`$01C0` / `$FE40`) |
| `$4006` | `ball_yf` | 1 | Y fraction |
| `$4007` | `ball_yi` | 1 | Y integer = the sprite-0 Y register value (54-158) |
| `$4008` | `bounce_phase` | 1 | 0-63, index into the bounce table |
| `$4009` | `rot_frame` | 1 | 0-15 |
| `$400A` | `spin_dir` | 1 | `$01` or `$FF` |
| `$400B` | `bounce_count` | 1 | floor impacts, wraps at 256 |
| `$400C` | `wall_count` | 1 | wall impacts, wraps at 256 |
| `$400D` | `last_impact` | 1 | 0 none, 1 floor, 2 wall-left, 3 wall-right |
| `$400E` | `frame_count` | 2 | 16-bit, lo/hi |
| `$4010` | `irq_hwm` | 1 | **high-water mark**: most raster lines any tick has consumed |
| `$4011` | `irq_last` | 1 | raster lines the last tick consumed |
| `$4012` | `shadow_x16` | 2 | sprite-4 X, lo/hi |
| `$4014` | `shadow_size` | 1 | 0-3 |
| `$4015` | `freeze` | 1 | non-zero freezes physics; the staging hook (§13) |
| `$4016` | `sptr` | 4 | the four ball sprite pointers as written this frame |
| `$401A` | `alive` | 1 | incremented by the main loop |
| `$401B` | `snd_timer` | 1 | 0-24, 24 = idle |
| `$401C` | `snd_kind` | 1 | 1 = floor, 2 = wall |
| `$401D` | `sid_shadow` | 25 | mirror of `$D400-$D418` |
| `$4036` | `rasterin` | 1 | scratch: `$D012` at tick entry |
| `$4037` | `tmp` | 8 | scratch |

**`irq_hwm` is a mark the program keeps, not a sample.** Per-frame cost spikes
only on the frames that do the expensive thing, so a sampler steps over them and
reports a comfortable number that means nothing —
`docs/graphics-and-sprites.md` §4 has the worked case (La Galaxia's sampler read
4 against a mark of 88). The mark is monotone and saturating, so a test reads it
with `at_most`; it is zeroed by poking it, so a claim can be scoped to a window.

---

## 10. Structure

`amiga_ball.s` holds the load address, the BASIC stub, the equates and the
init/IRQ/main-loop skeleton, and `.include`s the rest. Every included file
opens with an explicit `.segment` directive, because ca65 does not reset the
active segment at file boundaries (`skills/6502-assembly/SKILL.md`).

| File | |
|---|---|
| `amiga_ball.s` | load address, stub, equates, init, IRQ, main loop |
| `vars.s` | the `VARS` area — §9, byte for byte, in order |
| `room.s` | charset install, screen-matrix copy, color RAM fill |
| `chars.inc` | *generated* — 2,048 bytes, `CHARS` segment |
| `screen.inc` | *generated* — the 1,000-byte screen matrix, `RODATA` |
| `ball.s` | physics, sprite registers, pointers, shadow selection |
| `sprites.inc` | *generated* — 16 rotation frames, `SPRITES` segment |
| `shadow.inc` | *generated* — 4 shadow sizes, `SPRITES` segment |
| `bounce.inc` | *generated* — the 8.8 bounce table, `RODATA` |
| `sound.s` | the impact synth and `sidput` |
| `sound.inc` | *generated* — the two cutoff sweep tables, `RODATA` |
| `test.yaml` | the regression spec |
| `tools/generate.py` | emits every `.inc` above |
| `tools/score.py` | emits the reference score YAML from the impact schedule |
| `tools/evidence.sh` | regenerates `evidence/` in one command |

### 10.1 The BASIC stub

The standard 12-byte skeleton from `skills/6502-assembly/SKILL.md`: `LOADADDR`
holds `$0801`; `EXEHDR` lays down next-line pointer, line number 10, the `SYS`
token `$9E`, the digits `"2061"`, `$00`, and the `$0000` end marker. That is
`$0801-$080C`, so `CODE` begins at **`$080D` = 2061**, which is the address the
stub names. `start:` is the first byte of `CODE`.

### 10.2 The interrupt

One raster interrupt per frame, armed at **raster line 10**, through the
`$0314`/`$0315` vector:

```
sei
lda #$7F / sta $DC0D / lda $DC0D     ; CIA1 timer IRQ off, ack what it had
$0314/$0315  <- irq
lda $D011 / and #$7F / sta $D011     ; compare line is < 256
lda #10 / sta $D012
lda #$01 / sta $D01A / sta $D019     ; raster source on, no stale latch
cli
```

The handler acknowledges by writing 1 to `$D019` bit 0 on entry — without it the
interrupt re-fires immediately (`references/hardware.md`, "Raster-interrupt
technique"). It then reads `$D012`, calls `tick`, reads `$D012` again, updates
`irq_last`/`irq_hwm`, and exits by **pulling the registers itself**:

```
pla / tay / pla / tax / pla / rti
```

not through `$EA31` or `$EA81`. Nothing from ROM runs inside the interrupt. The
KERNAL's `$FF48` entry has already pushed A/X/Y before `jmp ($0314)`, so the
three pulls are the exact complement.

**Why line 10.** Two reasons, and both are arithmetic. First, `$D012` wraps at
263, so a tick that straddles the wrap would compute a negative cost; starting
at 10 and costing under 40 lines cannot reach 263. Second, the display window
starts at raster 51, and the VIC fetches a sprite's pointer and data when the
raster reaches that sprite's Y — the highest the ball ever goes is Y=54. A tick
that starts at line 10 and finishes before line 51 has written every sprite
register **before the VIC draws a single pixel of the frame**, so there is no
tearing to look for. §11 is the measurement that this holds.

`tick` is a subroutine ending in `rts`, which is what makes `c64 profile tick`
possible: `c64 profile` masks interrupts, so it can price a routine but not a
handler in situ. The handler is a wrapper; the job is the routine.

**The main loop** does nothing but `inc alive` and `jmp` — a liveness signal and
no more. It is *not* the frame anchor: it free-runs, so `until mainloop --count
N` would be a loop count rather than a frame count
(`skills/c64-development/SKILL.md`, "Testing motion"). **`tick` is the anchor.**

---

## 11. The frame budget

The per-frame job is a fixed cost: no allocation, no search, no loop whose trip
count depends on the ball's position. The sound routine is the only branch, and
its expensive arm is 30 register writes.

| Work | Approx. cycles |
|---|---:|
| physics (2 adds, 2 compares, table index) | ~90 |
| bounce table lookup + shadow band select | ~60 |
| 6 sprite X, 6 sprite Y, `$D010`, 6 pointers | ~330 |
| sound (worst frame: gate-on) | ~300 |
| cost measurement + counters | ~60 |
| **total, worst frame** | **~840** |

840 cycles is 12.9 raster lines (65 cycles/line) and 4.9% of the 17,095-cycle
NTSC frame. Lines 10-50 are top border — no badlines — so the DMA scale-back
`docs/cli.md` measures (×1.067) does not apply here.

**The declared ceiling is `irq_hwm ≤ 40` raster lines**, which is 2,600 cycles
and 15% of the frame. **The margin is therefore at least 223 of the frame's 263
lines (85%)**, and the operational form of it is the one that matters:
`10 + irq_hwm < 51` — the tick finishes in the top border. Both are asserted in
`test.yaml`, and `c64 profile tick` is the independent instrument.

---

## 12. Determinism and staging

Everything runs under `--warp --headless`, every observation is anchored on a
`c64 until tick` stop, and inspection never advances the machine
(`skills/c64-development/SKILL.md`, "The stopped-state rule").

`freeze` (§9) is the staging hook. With `freeze` non-zero, `tick` skips
*advancing* the physics but still derives Y from `bounce_phase`, writes every
sprite register, selects the shadow, and services sound. So poking
`bounce_phase` = 32 and stepping one tick shows the apex exactly; poking
`ball_xi` = 223 shows the right wall. This is `docs/graphics-and-sprites.md`
§5's third rule — stage unreachable states by poking the program's own state
bytes — and it is the same set of bytes `test.yaml` asserts on, so the evidence
and the regression test agree by construction.

Initial state: `ball_xi` = 40, `ball_vx` = `$01C0`, `bounce_phase` = 32 (the
apex), `rot_frame` = 0, `spin_dir` = `$01`. The first floor impact therefore
lands on frame 32 and every 64 frames after; the first wall impact on frame
≈105.

---

## 13. Evidence

### 13.1 Frames

`tools/evidence.sh` regenerates all of it in one command, following the five
rules in `docs/graphics-and-sprites.md` §5 — plus two this demo had to establish
for itself, both stated here because a reviewer will otherwise draw a wrong
conclusion from a correct picture.

**A. Flush the scanline buffer.** `c64 screen --png` returns the emulator's
rolling raster, not a re-render of video RAM: lines the beam has swept show the
current partial frame and lines below it show the previous one, arbitrarily
stale after a warped phase. Step exactly one more `until tick` immediately
before every capture. This is not in the policy's five rules;
`demos/la-galaxia/tools/evidence.sh` states it as its own rule 2, having shipped
a capture with boot-screen blue below the beam.

**B. The PNG has square pixels; the C64 does not.** `c64 screen --png` writes
the raw NTSC raster with no aspect correction — measured, 1 PNG pixel per raster
pixel at `--scale 1`. Since the machine's PAR is 0.7435 (§3.1), **a ball that is
genuinely round on a television necessarily reads as a 4:3-wide ellipse in these
PNGs, and one that looks round in the PNG would be a 29%-too-tall egg on the
machine.** So roundness is never judged by eye off `evidence/*.png`. It is
judged by the bounding box: the sphere must measure **96 × 72** raster pixels,
which is criterion 28. `apex.png` and `contact.png` are evidence of *position*,
not of shape.

Each PNG is captured while the machine is **stopped** at a `c64 until tick`
anchor, at `--scale 2 --border`, and each is accompanied by a `.txt` holding the
state bytes that put it there.

| File | The claim |
|---|---|
| `room.png` | the room before the ball moves |
| `apex.png` + `.txt` | the ball at the apex, with `bounce_phase`/`ball_yi` |
| `contact.png` + `.txt` | the ball at floor contact, same bytes |
| `rot00.png` `rot05.png` `rot10.png` + `.txt` | three rotation frames, each with `rot_frame` and the four sprite pointers |
| `wall-left.png` `wall-right.png` + `.txt` | both side walls, with `spin_dir` before and after |
| `shadow-1/2/3.png` + `.txt` | the shadow's X against the ball's X at three positions |
| `ball-tl/tr/bl/br.png` | `c64 sprite png` of the four blocks at one rotation frame — the shape the VIC actually reads, independent of where the ball is |
| `sid-impact.txt` | the SID shadow on the frame of a floor impact and again 8 frames later |

### 13.2 Audio

Two captures under `evidence/audio/`, one per impact kind, each with all five
artifacts (`capture.wav`, `sid-log.jsonl`, `piano-roll.png`, `spectrogram.png`,
`report.md`):

| Dir | Window |
|---|---|
| `evidence/audio/floor/` | a floor impact plus its decay |
| `evidence/audio/wall/` | a wall impact plus its decay |

Captures run with **warp off, in real time** — `c64 audio capture` pins the
speed, and a warped capture writes a 0-frame WAV (`docs/cli.md`). Budget wall
clock: ~42 ms per frame plus ~1.1 s fixed, so a 90-frame window is about 5 s of
real time.

Each capture is staged the same way the frames are, and released *inside* the
window with `--at-frame`, which is the only way to trigger something once the
capture owns the session:

```sh
c64 audio capture 1.5 evidence/audio/floor --at-frame 12 '$4015=0' --ref floor.score.yaml
```

(`$4015` is `freeze`; the address is fixed by §9, which is why `VARS` is an
area.) The impact therefore lands on a **known frame of the window**, computed
from the bounce table, not observed after the fact.

**The reference score is generated, not fitted.** `tools/score.py` reads the
same constants as the demo — the impact frame, the 20-frame gate, the two
pitches — and writes the score YAML. It scores **voice 1** (the pitched thump)
and claims **voice 3 silent** (`3: []`). Voice 2 is noise; the report's own
checks never call noise detuned, and a pitch diff on a noise voice would be
asserting something pitch analysis cannot settle, so voice 2 is **omitted** from
the score and its evidence is the spectrogram — where the noise transient and
the filter's downward sweep are visible and the piano roll cannot show them.
Both reports must read `verdict: PASS`.

The maintainer's listen of `capture.wav` is the final gate on whether it sounds
like a boing.

---

## 14. Acceptance criteria

Each is an observation a stopped machine (or a named capture) can be read for.
`AUDIT.md` scores every one of these PASS/FAIL with evidence from the running
machine, never from reading the source.

**Mode and memory**

1. `$D011 & $7F` = `$1B`; `$D016 & $1F` = `$08`; `$D018` = `$19`;
   `$D020 & $0F` = 0; `$D021 & $0F` = 0.
2. Color RAM row 0 col 0 masked = `$04`; row 20 col 0 masked = `$0E`.
3. `$0400`-`$07E7` differs from all-zero, and at least one wall row and one
   floor row hold a non-zero glyph code.

**Sprites**

4. `$D015` = `$3F`; `$D01C` = `$0F`; `$D017` = `$0F`; `$D01D` = `$3F`;
   `$D01B` = `$30`.
5. `$D025` = `$00`, `$D026` = `$01`, `$D027`-`$D02A` = `$02`,
   `$D02B` = `$D02C` = `$0B` (all masked to 4 bits).
6. `$07F8`-`$07FB` equal `160 + 4*rot_frame + n`, and equal `sptr` (§9).
   `$07FC`/`$07FD` equal `224 + 2*shadow_size + n`.

**Geometry that must hold as the ball moves**

7. At any anchored frame: `$D001` = `$D003` = `ball_yi`, and `$D005` = `$D007`
   = `ball_yi + 42`.
8. At any anchored frame: `$D000` = `$D004` = `ball_x16` low byte, and
   `$D002` = `$D006` = `(ball_x16 + 48) & $FF`.
9. `$D010` equals `$00` when `ball_xi < 184` and `$2A` when `ball_xi >= 184`.
10. `ball_x16` = `24 + ball_xi` at every anchored frame.

**Motion**

11. Sampled at a `tick` anchor and again 20 ticks later, `ball_x16` differs.
12. `ball_yi` sampled across a full bounce reaches ≤ 60 (near apex) and returns
    to 158 (contact).
13. `bounce_count` climbs across 200 ticks; `wall_count` climbs across 300.
14. `rot_frame` cycles: sampled 20 ticks apart it differs, and it is always
    ≤ 15.
15. `spin_dir` before and after a wall hit are `$01` and `$FF` (in either
    order); `last_impact` is 2 or 3 on the wall-hit frame.
16. `shadow_x16` = `ball_x16` at three separate anchored frames, and
    `shadow_size` takes at least two distinct values across a bounce.

**Sound**

17. On a floor-impact frame, `sid_shadow+4` (`$D404`) = `$11` and
    `sid_shadow+11` (`$D40B`) = `$81`; `sid_shadow+0/1` = `$0D`/`$07`.
18. 8 frames later the cutoff `sid_shadow+22` (`$D416`) is **lower** than on
    the impact frame; 24 frames later `sid_shadow+4` = `$10` (released).
19. On a wall-impact frame `sid_shadow+0/1` = `$90`/`$0A` — a higher pitch than
    the floor's.
20. `sid_shadow+14` through `sid_shadow+20` (voice 3) are 0 at every anchored
    frame.
21. `evidence/audio/floor/report.md` and `evidence/audio/wall/report.md` both
    read `verdict: PASS` against a score written from the impact schedule.
22. The spectrogram of each capture shows a broadband transient at the impact
    frame whose energy centroid falls over the following ~250 ms — the filter
    sweep, which the piano roll cannot show.

**Budget**

23. `irq_hwm ≤ 40` raster lines after 600 ticks, and `10 + irq_hwm < 51`.
24. `c64 profile tick` reports a mean under 2,600 cycles.
25. `alive` differs when sampled 20 ticks apart — the main loop is still running
    under the interrupt.

**Shipping**

26. `c64 package` produces `amiga_ball.d64` and `amiga_ball.prg`, and the
    reported run command is `x64sc -ntsc amiga_ball.d64`.
27. `c64 test run demos/amiga_ball/test.yaml` passes.

**Shape**

28. The sphere's bounding box, measured off a capture rather than judged by
    eye, is **96 × 72 raster pixels** — `96 × 0.7435 / 72 = 0.991`. Measured as
    the red-checker bbox plus one rim texel on each side: 88 × 68 red, +4 px
    left/right and +2 px top/bottom. §13.1 B is why this is a measurement and
    not a look.
