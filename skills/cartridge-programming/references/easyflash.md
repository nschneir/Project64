# EasyFlash at register level

Everything here was measured on VICE 3.10 with cc65 and VICE's `cartconv`, or
read off the shipped runtime (`src/c64lib/data/cart/cart.inc`) and the shipped
container code (`src/c64lib/cartridge.py`). Nothing is recalled from a
datasheet — if a bit is not listed below, this toolchain has not measured it,
so do not write it.

## Geometry

64 banks × 16 KB = 1,048,576 bytes. Each bank is two 8192-byte windows:

| Window | Address while mapped | Manifest key |
|---|---|---|
| LOROM | `$8000-$9FFF` | `lo` |
| HIROM | `$A000-$BFFF` (and `$E000-$FFFF` in Ultimax mode) | `hi` |

Both windows of a bank are mapped at once, and **both switch together** on a
single write to `$DE00`. A cross-bank `JSR` is therefore impossible; a call
from a bank's LOROM into the *same* bank's HIROM is an ordinary `JSR`.

## `$DE00` — bank register

Bits 0–5 select the bank, 0–63. `cart.inc` calls it `EF_BANK` and writes it
with a plain `sta EF_BANK`.

Write-only on real hardware. Under VICE it reads back — measured `$DE00: 02`
after the cart selected bank 2. With **no** EasyFlash cartridge mapped the
address is open bus and reads `$FF`, which is why `c64 cart bank` reports mode
`unknown` on a machine with no such cart. `c64 cart bank` uses that read-back,
which is why the command is a debugging aid and not something a cartridge may
imitate: track the current bank in RAM, the way `cart.inc`'s `ef_cur_bank` does.

## `$DE02` — control register

`cart.inc` calls it `EF_CONTROL`. One value is measured end to end:

| Value | Meaning |
|---|---|
| `$87` | leave Ultimax for **16K** cart mode, LED on — `EF_MODE_16K` |

The shipped decoder in `c64 cart bank` maps three values and treats bit 7 as
the LED:

| `$DE02` | reported mode |
|---|---|
| `$87` | `16k` |
| `$86` | `8k` |
| `$84` | `ultimax` |
| anything else | `unknown` |

Also write-only on hardware, also readable under VICE (measured `$DE02: 87`
after the cart wrote it).

## The boot sequence, step by step

Measured end to end: the cart wrote `"AaCc*"` to `$0502`, proving bank 1
(`$8000`=`A`, `$A000`=`a`) and bank 2 (`$8000`=`C`, `$A000`=`c`) each switched
*both* windows on one `$DE00` write, and that the sequence ran to completion.

1. The cart powers up in **Ultimax mode** (EXROM=1, GAME=0). The CPU takes
   RESET from `$FFFC` — which is offset `$1FFC` of **bank 0's HIROM window**,
   assembled for `$E000`. The CBM80 signature is never scanned.
2. `SEI / CLD / LDX #$FF / TXS` — `ef_boot` in `cart.inc`.
3. Copy the resident block from ROM at `$E0xx` down to RAM at `$0900`. This
   must happen *before* the mode switch: `$E000` stops being cart ROM the
   instant the cart leaves Ultimax mode.
4. `JMP` into the copy — everything after this runs from RAM.
5. `LDA #$87 / STA $DE02` — leaves Ultimax for 16K cart mode, so KERNAL and
   BASIC exist again.
6. `JSR $FDA3` (IOINIT), `JSR $FD50` (RAMTAS), `JSR $FD15` (RESTOR),
   `JSR $FF5B` (CINT). RAMTAS' memory-size probe writes `$0900` and restores
   it, so the resident block survives its own initialisation.
7. `CLI`, then `LDA #$00 / STA ef_cur_bank / STA $DE00` and
   `JMP $9F00` — bank 0's LOROM jump table, entry 0. That entry is your cold
   start.

From here every bank switch is a `STA $DE00`, and every cross-bank call is
`jsr bankcall` (which the `ef_call` macro sets up).

### Why `$0900`

Found by failing twice, not by choosing:

| Address | Result |
|---|---|
| `$0334` (cassette buffer) | crashed after the mode switch — `RAMTAS` clears `$0002-$0101` **and `$0200-$03FF`** |
| `$C000` | never reached — in Ultimax mode only `$0000-$0FFF` is RAM |
| `$0900` | works |

So the usable resident window is `$0800-$0FFF`: above the `$0400-$07FF` screen
that `CINT` clears, above everything `RAMTAS` wipes, and inside the only RAM
Ultimax mode provides.

The block is assembled absolute with `.org EF_RESIDENT` inside the ordinary
`CODE` segment — there is no `RAMCODE` segment and no `__RAMCODE_LOAD__` /
`__RAMCODE_RUN__` / `__RAMCODE_SIZE__` import scheme. Every bank includes
`cart.inc`, but only the boot window's linker config could host a
RAM-resident segment, so a segment-based scheme is a hard `ld65` error
("Missing memory area assignment") in every other window. The block must
therefore stay **under 256 bytes** — the bound comes from the copy loop's
8-bit counter, asserted at assembly time, not from a linker memory area.

## `cart.inc` surface

| Name | Value / form | What it is |
|---|---|---|
| `EF_BANK` | `$DE00` | bank register |
| `EF_CONTROL` | `$DE02` | mode/LED register |
| `EF_MODE_16K` | `$87` | the `$DE02` value the boot sequence writes |
| `EF_JUMPTABLE` | `$9F00` | each code bank's entry table (LOROM) |
| `EF_RESIDENT` | `$0900` | where the trampoline runs |
| `EF_MAX_ENTRY` | `84` | last legal jump-table index (3 bytes × 85 = one page) |
| `ef_entry target` | macro | emits `jmp target`; declaration order is the index |
| `ef_call bank, index` | macro | `lda #bank / ldx #(index*3) / jsr bankcall` |
| `bankcall` | routine | A = bank, X = index × 3; switches, calls, switches back |
| `ef_setbank` | routine | A = bank; switches without calling, caller switches back |
| `ef_boot` | routine | cold entry; the boot window's reset vectors point here |

`ef_call` with `index > EF_MAX_ENTRY` is an assembly-time `.error`.

Registers across `bankcall`: A is loaded with the bank going in and holds the
*caller's* bank coming out (the flags are set by that pull), so nothing useful
returns in A or the flags. X carries the entry offset going in and whatever the
callee left coming out; Y is untouched throughout. Arguments therefore travel
in Y or in RAM; results in X, Y, or RAM.

Nesting is safe — the caller's bank rides the stack and the self-modified `JSR`
operand has already been consumed before a nested call rewrites it. An
*interrupt* landing between the operand write and the `JSR` is not safe, so
interrupt handlers must not use `ef_call`.

## `.crt` container, EasyFlash flavour

Header (64 bytes), then CHIP packets back to back:

| Offset | Size | Field |
|---|---|---|
| `$00` | 16 | magic `C64 CARTRIDGE   ` — the trailing spaces are part of it |
| `$10` | 4 | header length, big-endian — `$00000040` |
| `$14` | 2 | version — `$0100` |
| `$16` | 2 | hardware type, big-endian — **32** for EasyFlash |
| `$18` | 1 | EXROM line, 0 = asserted — **1** |
| `$19` | 1 | GAME line, 0 = asserted — **0** |
| `$1A` | 6 | reserved |
| `$20` | 32 | cartridge name, NUL/space-padded (32 bytes, not 16) |

CHIP packet:

| Offset | Size | Field |
|---|---|---|
| `+0` | 4 | magic `CHIP` |
| `+4` | 4 | **total** packet length (16 + data), big-endian |
| `+8` | 2 | chip type — `0` = ROM, `2` = FLASH |
| `+10` | 2 | bank number |
| `+12` | 2 | load address |
| `+14` | 2 | data size |
| `+16` | *size* | data |

An EasyFlash image emits **two packets per bank** — `($8000, $2000)` and
`($A000, $2000)` — both with chip type FLASH. `c64 cart info` prints them as
`flash`, one row per packet, with the window derived from the load address.

For contrast, a generic cart is one packet: 8K is `($8000, $2000)`, and **16K
is a single `($8000, $4000)` packet**, not two 8K ones. Ultimax is
`($E000, $2000)`.

## What `cartconv` demands

`cartconv` is only used to *write* an image; reading is done in Python, because
`cartconv -c` printed `Error: this file seems broken.` on a deliberately
truncated `.crt` and still exited 0. It cannot be a gate.

- The type name is **`easy`** — `-t easyflash` is rejected. (`ultimax` is
  likewise `ulti`; 8K and 16K are both `normal`.)
- The raw input must be **exactly 1,048,576 bytes**. Every other size is
  refused:

  ```
  banks=2  size=32768   -> Error: Input file size (32768) doesn't match EasyFlash requirements
  banks=3  size=49152   -> Error: Illegal file size of t.bin
  banks=32 size=524288  -> Error: Input file size (524288) doesn't match EasyFlash requirements
  banks=64 size=1048576 -> Conversion from binary format to C64 EasyFlash .crt successful.
  ```

- By default it **optimizes**: all-`$FF` windows are dropped and the remaining
  bank numbers stay correct. A 1 MB image holding only bank 0 HI, bank 1 and
  bank 2 produced a 41,104-byte `.crt` with 5 packets.

So `c64 cart build` always pads to 1 MB and lets `cartconv` shrink it — a
sparse manifest costs nothing in the finished image, and gaps in the bank
numbering of a built `.crt` are normal output rather than corruption.
`c64 cart build` keeps that padded 1 MB image beside the `.crt` as `.bin`,
which is what a flasher or a raw-ROM mode wants.

## What `c64 cart verify` checks on an EasyFlash image

Each rule maps to a failure that is silent on hardware:

- the image declares Ultimax (EXROM=1, GAME=0) — anything else never boots;
- **bank 0 has a HIROM packet** — that is where `$FFFC` lives, and without it
  the cart never executes an instruction;
- the reset vector at offset `$1FFC` of that packet points inside
  `$E000-$FFFF`;
- every window is exactly 8192 bytes and loads at `$8000` or `$A000`;
- no `(bank, window)` pair appears twice;
- every bank number is inside 0–63.

Gaps between bank numbers are *not* flagged: `cartconv` drops empty banks on
purpose.

## Debugging notes

VICE's binary monitor exposes banks `default`/`cpu` (0), `ram` (1), `rom` (2),
`io` (3) and `cart` (4). Reading `$8000` from `cpu` or `cart` returns the
**currently mapped** EasyFlash bank's bytes; there is no way to enumerate an
unmapped bank from a running machine. Hence:

- `c64 cart bank` reports the registers rather than deriving the bank from
  memory;
- `c64 mem read '$8000' 32` always shows the bank that is mapped *now*;
- to look at a bank you are not in, go offline: `c64 cart dump game.crt
  --bank 3 --window hi -o bank3hi.bin`.

Merged label files tag every symbol with its bank and window (`b01lo_update`),
which keeps the names unique. The *addresses* still collide across banks — five
banks all place code at `$8000` — so an address-to-symbol lookup may name an
arbitrary bank's copy, and a breakpoint set on one bank's routine fires for any
bank executing that address. Confirm the bank with `c64 cart bank` after the
break.
