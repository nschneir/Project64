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

## Sprites (VIC-II)

8 hardware sprites, 24×21 pixels each, 63 bytes of data per shape.
Policy for demos: docs/specs/graphics-and-sprites.md.

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

## Sound (SID)

3 voices, 7 registers each from `$D400` (voice 2 at `$D407`, voice 3 at
`$D40E`); global volume at `$D418` (0-15, low nybble). Per voice:

| Offset | Role |
|--------|------|
| +0/+1  | Frequency low/high |
| +2/+3  | Pulse width low/high (pulse waveform only) |
| +4     | Control: waveform (bit 4 triangle, 5 sawtooth, 6 pulse, 7 noise) + gate (bit 0: 1 starts the envelope, 0 releases) |
| +5     | Attack/decay nybbles |
| +6     | Sustain/release nybbles |

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
