# C64 memory map

All addresses hex. The CPU is the **6510** — a 6502 core with an on-chip
I/O port at `$00/$01` that banks the ROMs and I/O in and out of the address
space (see zero-page.md). I/O region details: references/hardware.md.
Generate annotated ROM listings with `c64 rom disasm`.

| Range       | What                                                     |
|-------------|----------------------------------------------------------|
| 0000-00FF   | Zero page; $00/$01 = 6510 banking port (see zero-page.md)|
| 0100-01FF   | 6510 stack                                               |
| 0200-03FF   | OS variables: input buffer $0200, keyboard buffer $0277, RAM vectors $0314-$0333, cassette buffer $033C-$03FB |
| 0400-07E7   | Screen RAM (1000 bytes, power-on default)                |
| 07F8-07FF   | Sprite data pointers (for the default screen)            |
| 0801-9FFF   | BASIC program text, then variables/arrays/strings        |
| A000-BFFF   | BASIC ROM (RAM underneath — banked by $01)               |
| C000-CFFF   | 4 KB free RAM (never touched by BASIC — prime ML home)   |
| D000-DFFF   | I/O: VIC-II D000, SID D400, color RAM D800, CIA1 DC00, CIA2 DD00 (char ROM underneath) |
| E000-FFFF   | KERNAL ROM (RAM underneath); vectors NMI FFFA (→FE43), RESET FFFC (→FCE2), IRQ FFFE (→FF48) |

Notes:
- 64 KB RAM exists under all the ROMs; the `$01` port bits (LORAM, HIRAM,
  CHAREN) select what the CPU sees. Default value `$37`: BASIC + KERNAL +
  I/O all visible, 38911 BASIC bytes free ($0801-$9FFF).
- The VIC-II always reads through its own 16 KB bank (bank 0, $0000-$3FFF
  by default, selected via CIA2 $DD00) — it sees the char ROM at $1000
  even though the CPU doesn't. That image is **4 KB** ($1000-$1FFF:
  uppercase set, then lowercase), which covers **two** of the eight 2 KB
  charset bases — a RAM charset in bank 0 must avoid both $1000 and $1800,
  and $1800 fails silently by drawing the ROM's lowercase glyphs.
- The screen can be relocated by the VIC-II ($D018, plus the VIC bank in
  $DD00); `c64 screen` and `@row,col` follow both, so a relocated screen
  still reads back correctly. Color RAM never moves — it stays at $D800.
- `c64` (NTSC, 60 Hz) and `c64pal` (PAL, 50 Hz) share this entire map;
  only frame timing and CPU clock differ. A running program can tell them
  apart with `PEEK(678)` (0 = NTSC, 1 = PAL) — see zero-page.md.
