# PET hardware overview

Base addresses of the I/O chips (all in the `$E800-$EFFF` window). This is an
orientation map, not a register-level reference — for exact bit meanings, poke
with `c64 mem read`/`c64 mem write` and read the ROM with `c64 rom disasm`.

| Base  | Chip  | Role                                                        |
|-------|-------|-------------------------------------------------------------|
| E810  | PIA1  | Keyboard matrix scan (row select out, columns in); screen blank and cassette lines. |
| E820  | PIA2  | IEEE-488 data lines.                                        |
| E840  | VIA   | IEEE-488 control, user port, CB2 sound, timers.            |
| E880  | CRTC  | Video timing — register select `$E880`, data `$E881`. **CRTC models only** (4032/8032/8296). |

Notes:

- The keyboard is scanned from the IRQ handler on the ~60 Hz jiffy interrupt
  (the same interrupt updates the TI clock and flashes the cursor; it runs
  through the RAM vector at `($90)` on BASIC 2/4). For automation, feed the
  keyboard through `c64 basic type` (or the keyboard-feed path) rather than
  poking the PIA1 matrix directly.
- **IEEE-488** is the PET's peripheral bus — disk drives and printers live here
  as devices 8 and up. c64-tools drives disks through disk images and `c64 disk`
  / VICE, so you rarely touch the bus registers directly.

## The keyboard matrix

The keyboard is a matrix of 10 rows × 8 columns. Bits 0–3 of PIA1 port A
(`$E810`) select a row; reading PIA1 port B (`$E812`) returns that row's
columns — **a 0 bit means the key is pressed** (no key = `$FF`). The IRQ
handler scans all rows each tick and decodes presses through an 80-entry
table in ROM, leaving results where machine code can read them cheaply:

- `$97` — which key is down right now (`#$FF` = none). The stored value is
  **ROM-dependent**: the BASIC 4 40-column editor stores the decoded
  PETSCII ('A' held reads $41), the BASIC 2 editor stores the raw matrix
  index. Games comparing $97 against PETSCII therefore only work on
  BASIC 4 machines — pin the model when shipping (`x64sc -model 4032
  game.d64`; `c64 package` emits exactly that hint). `c64 key hold` drives
  this byte deterministically for testing.
- `$98` — shift flag (`0`/`1`).
- `$9E` — count of characters in the keyboard buffer at `$026F` (write 0 to
  flush type-ahead).

After a scan, `$E810` is left selecting the row that contains STOP (also
space, `<`, `=`, `[`, reverse on 40-column graphics keyboards), which is why
`LDA $E812` works as a quick STOP-key test — but from machine code prefer
`JSR $FFE1` (TEST STOP KEY) or `JSR $FFE4` (GETIN). For a game loop, GETIN
in a polling loop is the simple path; scanning `$97` gives key-down state
without waiting for the repeat mechanism.

Key repeat (BASIC 4, 40-column) is controlled from `$03EE` (`0` = repeat on,
`$40` = off) with countdown/delay at `$03E9`/`$03EA`; the 80-column machines
keep the equivalent flags in zero page (`$E4`/`$E5`).

## Sound (VIA CB2)

Sound is a square wave from the VIA's shift register on the CB2 line — no
dedicated sound chip (a speaker must be wired to CB2/pin M of the user port;
VICE emulates it). Three registers do everything:

| Register | Addr (dec) | Role |
|----------|------------|------|
| ACR (aux control)  | `$E84B` (59467) | `$10` = shift register free-runs under timer 2; `0` = sound off |
| Shift register     | `$E84A` (59466) | The bit pattern that is shifted out — waveform/timbre (`$0F`/`15` = square; other patterns change the octave/character) |
| Timer 2 low        | `$E848` (59464) | Shift period — the pitch (`0` = silent) |

From BASIC:

```
100 poke 59467,16 : poke 59466,15   : rem sound on, square wave
110 poke 59464,125                  : rem play a note
120 for j=0 to 400 : next j
130 poke 59464,0 : poke 59467,0     : rem sound off
```

Beyond sound, T2 is an ordinary VIA down-counter: `$E848` decrements once
per microsecond (with `$E849` as the high byte), so reading it gives
sub-jiffy timing when the shift register isn't in use.

The timer decrements at 1 MHz, and a full wave is 16 shifts for a
single-pulse pattern, so frequency ≈ 1,000,000 / (16 × T) Hz — e.g. T=125
→ ~500 Hz; each doubling of T drops the pitch an octave. A descending
chromatic scale of T values (from Programming the PET/CBM):
250, 236, 223, 210, 198, 187, 176, 166, 157, 148, 139, 132, then halve for
the next octave. **Always zero both `$E848` and `$E84B` when done** or the
tone continues forever.
