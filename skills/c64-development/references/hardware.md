# C64 hardware overview

Base addresses of the I/O chips (all in the `$D000-$DFFF` window, visible
while `$01` bit 2 = 1). This is an orientation map plus the registers agents
actually use — for exhaustive bit meanings, consult the books, poke with
`c64 mem read`/`c64 mem write`, and read the ROM with `c64 rom disasm`.

| Base  | Chip     | Role                                                   |
|-------|----------|--------------------------------------------------------|
| D000  | VIC-II   | Video: text/bitmap modes, sprites, scrolling, raster.  |
| D400  | SID      | Sound: 3 voices, ADSR envelopes, filter.               |
| D800  | —        | Color RAM (1000 nybbles, one per screen cell).         |
| DC00  | CIA1     | Keyboard matrix + joystick ports, timer A/B, IRQ.      |
| DD00  | CIA2     | Serial (IEC) bus, user port, VIC bank select, NMI.     |

The 60 Hz (NTSC) system IRQ comes from CIA1 timer A; the handler (through
`($0314)`, default `$EA31`) scans the keyboard, updates TI, and blinks the
cursor.

## Keyboard and joysticks (CIA1)

The keyboard is an 8×8 matrix on CIA1: `$DC00` selects columns (out),
`$DC01` reads rows (in), **0 bit = pressed**. The IRQ scan decodes it and
leaves results where code can read them cheaply:

- `$CB` — matrix code of the key held right now (64 = none). This is the
  live key-down state — `c64 key hold` drives it deterministically for
  testing. Matrix codes: space 60, RETURN 1, W 9, A 10, S 13, D 18
  (full table: `MATRIX_CODES` in `src/c64lib/ops.py`).
- `$C6` — count of characters in the type-ahead buffer at `$0277`
  (write 0 to flush).
- `JSR $FFE4` (GETIN) — next buffered *decoded* character, 0 = none; the
  simple polling read for menus and INPUT-style interaction.

**Joysticks:** port 2 reads at `$DC00`, port 1 at `$DC01` — bits 0-3 =
up/down/left/right, bit 4 = fire, 0 = active. Reading `$DC01` collides
with the keyboard scan, which is why game docs say "use port 2"
(`JSR` nothing — just `LDA $DC00 / AND #$1F`). Prefer joystick port 2 or
`$CB` polling for game input.

## CIA 6526 timers, TOD, and interrupts

Both CIAs expose the same 16 registers, at an offset from `$DC00` (CIA1) or
`$DD00` (CIA2):

| Off | Name | Function |
|-----|------|----------|
| 0/1 | PRA/PRB | Ports A/B (CIA1: keyboard + joysticks; CIA2 PRA: VIC bank + serial bus, PRB: user port / RS-232) |
| 2/3 | DDRA/DDRB | Data direction, 1 = output (CIA1 defaults $FF / $00 — columns out, rows in) |
| 4/5 | TA LO/HI | Timer A: read = live count, write = latch (reload) value |
| 6/7 | TB LO/HI | Timer B, same read/write split |
| 8-11| TOD | Time-of-day clock, BCD: 10ths, sec, min, hr (bit 7 of hr = PM) |
| 12  | SDR | Serial shift register (user-port SP pin), MSB first |
| 13  | ICR | Interrupt control: read = pending flags (**and clears them**), write = enable mask |
| 14  | CRA | Control A: bit 0 start TA, bit 3 one-shot/continuous, bit 4 force-load, bit 5 count φ2/CNT, bit 7 TOD 60/50 Hz |
| 15  | CRB | Control B: same for TB; bit 7 = writes set the TOD **alarm** (1) or **clock** (0) |

- **Timers** are 16-bit down-counters loaded from a latch; on underflow they
  set an ICR flag and either stop (**one-shot**, CRA/CRB bit 3 = 1) or reload
  and repeat (**continuous**, bit 3 = 0). CIA1 timer A (continuous) drives the
  60 Hz system IRQ — don't stop it or rewrite CIA1's ICR mask casually or the
  keyboard scan and jiffy clock die.
- **ICR** (`$DC0D`/`$DD0D`) read flags: bit 0 timer A, 1 timer B, 2 TOD alarm,
  3 SDR, 4 FLAG pin (CIA1 = cassette read, CIA2 = RS-232 RXD), bit 7 = this
  chip raised its interrupt line — reading clears them. Writing sets the mask:
  bit 7 = 1 → set each 1-bit, bit 7 = 0 → clear each 1-bit. **CIA1's line is
  IRQ; CIA2's is NMI.**
- **CIA2 PRA `$DD00`** beyond the VIC bank (bits 0-1, inverted — see below):
  bit 2 RS-232 TXD, bit 3 serial ATN out, bits 4-5 CLK/DATA out, bits 6-7
  CLK/DATA in — the serial (IEC) bus disk drives and printers use.
- **TOD** is a BCD clock that sits **stopped at 0 from power-on** (verified: it
  reads 0 and doesn't advance until set). Set it by writing hr, min, sec, then
  **10ths last, which starts it**. Reading the hour latches the whole time until
  you read 10ths, so read hr→…→10ths (or read 10ths last). The alarm register
  overlays the same four addresses (CRB bit 7 selects it) and is write-only.

## Sprites (VIC-II)

8 hardware sprites, 24×21 pixels each, 63 bytes of data per shape.
Policy for demos: docs/superpowers/specs/graphics-and-sprites.md.

| Register | Role |
|----------|------|
| D000/D001 | Sprite 0 X/Y (pairs continue through D00E/D00F for sprites 1-7) |
| D010 | X-coordinate bit 8 (one bit per sprite — X > 255 needs it) |
| D015 | Sprite enable bits |
| D017 / D01D | Double height / double width bits |
| D01B | Sprite-behind-text priority bits |
| D01C | Multicolor mode bits (per sprite) |
| D01E / D01F | Sprite-sprite / sprite-background collision latches (**reading clears them**) |
| D025 / D026 | Multicolor shared colors 0/1 |
| D027-D02E | Sprite 0-7 individual colors |

Data pointers live at screen+`$3F8` (`$07F8-$07FF` for the default screen);
pointer value = data address / 64. Visible X range starts at 24, Y at 50
(a sprite at X<24 is partly off the left edge).

A multicolor sprite (`$D01C` bit set) trades horizontal resolution for color:
pixels are 2 bits wide (12×21) and each pair picks a color — `00` transparent,
`01` shared color 0 (`$D025`), `10` the sprite's own color (`$D027-$D02E`),
`11` shared color 1 (`$D026`).

## Video modes (VIC-II)

- `$D011` — mode bits (bitmap enable bit 5, extended color bit 6, screen
  blank bit 4, vertical scroll bits 0-2, raster bit 8 in bit 7).
- `$D016` — multicolor bit 4, 38/40-column bit 3, horizontal scroll 0-2.
- `$D018` — memory setup: screen and charset/bitmap base within the VIC
  bank. Power-on `$15`: screen `$0400`, uppercase charset. **Leave the
  screen at `$0400`** — the toolset's screen reader assumes it.
- `$D012` — raster line (read current / write compare for raster IRQ).
- `$D020` / `$D021` — border / background color (0-15).

Colors: 0 black, 1 white, 2 red, 3 cyan, 4 purple, 5 green, 6 blue,
7 yellow, 8 orange, 9 brown, 10 light red, 11 dark gray, 12 medium gray,
13 light green, 14 light blue, 15 light gray. A character cell's color is
its nybble in color RAM `$D800+offset`.

## Bitmap and color-text modes (VIC-II)

Beyond standard text the VIC-II has bitmap and multicolor modes. Set enable
bits read-modify-write so you don't clobber the rest of the register:

- **Hi-res bitmap** (320×200, 1 bit/pixel): `$D011` bit 5. The 8000-byte
  bitmap sits at an 8 KB boundary chosen by `$D018` bit 3. Color comes from
  **screen memory**, not color RAM — each 8×8 cell's screen byte gives the
  "1" color in the high nybble, the "0" color in the low nybble. The byte for
  pixel (x,y) is `base + (y AND 248)*40 + (x AND 504) + (y AND 7)`; set the
  dot with bit `7-(x AND 7)`. Memory is 8-byte cells, not linear scanlines.
- **Multicolor bitmap** (160×200, 2 bits/pixel): bitmap bit 5 of `$D011` AND
  multicolor bit 4 of `$D016`. Pixel pairs select 00 = background `$D021`,
  01 = screen-mem high nybble, 10 = screen-mem low nybble, 11 = color RAM.
- **Extended-background text** (`$D011` bit 6): the top 2 bits of each screen
  code pick the cell background from `$D021`-`$D024`; only the first 64
  characters remain usable. Do not combine with multicolor.
- **Multicolor text** (`$D016` bit 4, enabled per cell by bit 3 of the color
  nybble): pixel pairs select 00 = `$D021`, 01 = `$D022`, 10 = `$D023`,
  11 = the low 3 bits of the cell's color nybble.

Background color registers: `$D021` bg 0, `$D022` bg 1, `$D023` bg 2,
`$D024` bg 3. A hi-res bitmap at `$2000` overlaps BASIC's variable area —
lower the top of BASIC or move the bitmap first.

## VIC bank and interrupts

- **VIC 16 KB bank** — the VIC-II only sees 16 KB at a time, chosen by the
  *inverted* low 2 bits of CIA#2 `$DD00` (make them outputs in `$DD02`
  first): `11`→bank 0 `$0000` (power-on), `10`→bank 1 `$4000`, `01`→bank 2
  `$8000`, `00`→bank 3 `$C000`. The character ROM image is visible to the VIC
  only in banks 0 and 2 (at `$1000`/`$9000`). The toolset assumes the screen
  stays at `$0400`, so treat bank switching as reference knowledge.
- **`$D018` bit-fields** — bits 7-4 = screen base in 1 KB steps, bits 3-1 =
  character/bitmap base in 2 KB steps, bit 0 ignored. When moving the screen,
  also point the editor at it: `POKE 648,page` (page = address/256).
- **VIC interrupts** — `$D019` is the flag register (bit 0 raster compare,
  1 sprite-background collision, 2 sprite-sprite collision, 3 light pen;
  clear a latch by writing a 1 to its bit), `$D01A` the enable mask (1 = that
  source raises an IRQ). This is what a raster or collision IRQ needs beyond
  reading `$D012`.

## Sound (SID)

3 voices, 7 registers each from `$D400` (voice 2 at `$D407`, voice 3 at
`$D40E`). Per voice:

| Offset | Role |
|--------|------|
| +0/+1  | Frequency low/high |
| +2/+3  | Pulse width low/high (12-bit; pulse waveform only; `$800` = square) |
| +4     | Control: waveform (bit 4 triangle, 5 sawtooth, 6 pulse, 7 noise) + gate (bit 0: 1 starts attack/decay/sustain, 0 releases). Bit 1 **sync** (hard-sync to the previous voice), bit 2 **ring mod** (ring-modulate the triangle with the previous voice — bells/gongs), bit 3 **test** (reset/hold the oscillator at 0) |
| +5     | Attack (high nybble) / decay (low nybble) |
| +6     | Sustain *level* (high nybble) / release rate (low nybble) |

Selecting two waveforms at once ANDs them; noise combined with another
waveform can "lock up" until you toggle the test bit. Sustain is a level
(0-15), not a time; decay and release share the rate column below.

**Global and filter registers:**

| Reg | Role |
|-----|------|
| D415 | Filter cutoff low (bits 0-2 only; 11-bit total with D416) |
| D416 | Filter cutoff high (main 8 bits); cutoff ≈ 30 Hz–12 kHz |
| D417 | Resonance (bits 4-7) + filter-routing (bit 0 voice1, 1 voice2, 2 voice3, 3 ext through the filter) |
| D418 | Volume (bits 0-3, 0-15) + filter mode (bit 4 low-pass, 5 band-pass, 6 high-pass — additive, LP+HP = notch) + bit 7 disconnects voice 3 from the output (so it can drive modulation silently) |

**Read-only registers** — the voice/control registers are write-only, but
these four read back:

| Reg | Role |
|-----|------|
| D419 / D41A | Paddle X / Y position (0-255) |
| D41B | Oscillator 3 output — with noise on voice 3 this is a free hardware RNG; sawtooth gives a ramp for modulation |
| D41C | Envelope 3 output — voice-3 envelope level, for modulation |

**Envelope rates** (nybble value → time, at ~1 MHz; NTSC runs ~2% faster).
Decay and release share the right column:

| Val | Attack | Dec/Rel | Val | Attack | Dec/Rel |
|-----|--------|---------|-----|--------|---------|
| 0 | 2 ms | 6 ms | 8 | 100 ms | 300 ms |
| 1 | 8 ms | 24 ms | 9 | 250 ms | 750 ms |
| 2 | 16 ms | 48 ms | A | 500 ms | 1.5 s |
| 3 | 24 ms | 72 ms | B | 800 ms | 2.4 s |
| 4 | 38 ms | 114 ms | C | 1 s | 3 s |
| 5 | 56 ms | 168 ms | D | 3 s | 9 s |
| 6 | 68 ms | 204 ms | E | 5 s | 15 s |
| 7 | 80 ms | 240 ms | F | 8 s | 24 s |

So the beep's `poke 54277,9` (attack/decay `$09`) is attack 250 ms, decay
750 ms; `poke 54278,0` is sustain level 0, release 6 ms.

The classic beep from BASIC:

```
100 poke 54296,15          : rem volume max
110 poke 54277,9 : poke 54278,0   : rem attack/decay, sustain/release
120 poke 54273,25 : poke 54272,30 : rem frequency
130 poke 54276,17          : rem triangle + gate on
140 for j=0 to 300 : next j
150 poke 54276,16          : rem gate off (release)
160 poke 54296,0           : rem volume off when done
```

Frequency: Fout = value × clock / 16777216 Hz (NTSC clock ≈ 1022730), so
value ≈ Fout × 16.4. Always gate off and zero the volume when done, or the
tone continues forever.

**Playing named notes.** Fn = round(freq × 16777216 / clock); split it with
Fhi = INT(Fn/256), Flo = Fn AND 255, then poke Fhi→`$D401`, Flo→`$D400`. One
octave at concert pitch (NTSC; values match the PRG note table within ±1 from
clock rounding):

| Note | Fn | Fhi | Flo | Note | Fn | Fhi | Flo |
|------|------|-----|-----|------|------|-----|-----|
| C4  | 4292 | 16 | 196 | F#4 | 6070 | 23 | 182 |
| C#4 | 4547 | 17 | 195 | G4  | 6430 | 25 | 30  |
| D4  | 4817 | 18 | 209 | G#4 | 6813 | 26 | 157 |
| D#4 | 5104 | 19 | 240 | A4  | 7218 | 28 | 50  |
| E4  | 5407 | 21 | 31  | A#4 | 7647 | 29 | 223 |
| F4  | 5729 | 22 | 97  | B4  | 8102 | 31 | 166 |

An octave up doubles Fn; an octave down halves it.
