---
name: cartridge-programming
description: Use when writing, building, or debugging a Commodore 64 cartridge — plain 8K/16K/Ultimax or bank-switched EasyFlash — with the c64 CLI or the c64-tools MCP server. Covers the two boot mechanisms (CBM80 vs the $FFFC reset vector), the memory modes, cart-native code in ROM, the EasyFlash banking discipline from cart.inc, and the failure modes that are silent on hardware.
---

# Cartridge programming

A cartridge is ROM the machine maps at power-on. Nothing loads it, so nothing
reports an error when it is wrong: a cartridge with a broken header simply does
not run, and the C64 boots to BASIC as if it were not there.

**Run `c64 cart verify game.crt` before every boot.** It catches exactly the
mistakes that are otherwise invisible, without an emulator round trip.

This skill assumes the `c64-development` skill's loop and the `6502-assembly`
skill's ca65 conventions. What changes for a cartridge is the *start*: there is
no `$0801` load address, no `10 SYS` stub, and no `READY.` prompt.

## The two boot mechanisms

**8K and 16K carts boot through CBM80.** The KERNAL reset routine scans `$8004`
for the five bytes `$C3 $C2 $CD $38 $30` and, if they are there, jumps through
the cold vector at `$8000`. If they are not, it carries on into BASIC.

| Address | Contents |
|---|---|
| `$8000-$8001` | cold start vector |
| `$8002-$8003` | warm start / NMI vector |
| `$8004-$8008` | `$C3 $C2 $CD $38 $30` — the signature |

**Ultimax and EasyFlash carts boot through `$FFFC`.** Both map ROM over the
KERNAL, so there is no reset routine left to scan for a signature — the CPU
takes its reset vector straight from `$FFFC`, which the cartridge supplies.
This was settled by experiment: an EasyFlash image with *both* entry points
armed ran only the `$FFFC` one. The CBM80 signature is never looked at on an
EasyFlash cart.

`c64 package prog.s --format crt --cart-type 8k` (or `16k`, or `ultimax`)
generates the right boot stub for the type you ask for. Export a `cart_main`
label and the stub jumps there:

```asm
CHROUT = $FFD2

        .export cart_main
        .segment "CODE"
cart_main:
        ldx     #0
loop:   lda     msg,x
        beq     done
        jsr     CHROUT
        inx
        bne     loop
done:   jmp     done                    ; a cartridge never returns anywhere
msg:    .byte   "CART HELLO", $0D, $00
```

Omitting `.export cart_main` is a link error that names the fix. Supplying your
own `.segment "STARTUP"` opts out entirely — the tool then generates nothing
and you own the CBM80 header or the reset vectors yourself. The opt-out is
detected by scanning your source *and everything ca65 reports it included*, so
boot code can live in a shared `.inc`.

## The three author models

| You have | Command | What happens |
|---|---|---|
| cart-native `.s` (owns the boot) | `c64 package prog.s --format crt` | assembled into the ROM window, boot stub injected |
| an existing `.bas` / `.prg` / `.s` program | `c64 package prog.bas -o prog.crt` | wrapped: a launcher copies the embedded image to its load address and starts it |
| many banks | `c64 cart build game.ef.yaml` | multi-bank EasyFlash image |

`--wrap` forces the launcher path for a `.s` that would otherwise be treated as
cart-native. `.bas` and `.prg` inputs are always wrapped.

**Wrapping has two hard limits, both from the memory map.** A wrapped program
that BASIC has to start — a tokenized `.bas`, or the `10 SYS 2061` stub the
standard `.s` layout emits — must be `8k`: a 16K cartridge maps ROM over
`$8000-$BFFF`, which covers the BASIC interpreter the launcher chains into, so
`--cart-type 16k` is *rejected* for it rather than being a way to fit more.
Only a machine-language wrap (one entered with a `JMP`) can use the 16K window.
Wrapping into `ultimax` is rejected outright for the same reason: the launcher
calls the KERNAL, and an Ultimax cartridge replaces it. The kind is decided by
sniffing the image's own bytes, never the file extension.

## Memory modes

The EXROM and GAME lines (0 = asserted) pick the mode:

| EXROM | GAME | Mode | ROM visible |
|---|---|---|---|
| 0 | 1 | 8k | `$8000-$9FFF` |
| 0 | 0 | 16k | `$8000-$BFFF` |
| 1 | 0 | ultimax | `$8000-$9FFF` and `$E000-$FFFF` |
| 1 | 1 | off | nothing |

**In Ultimax mode only `$0000-$0FFF` is RAM.** No BASIC, no KERNAL, no `$C000`
block — a `jmp $C000` there goes nowhere. Code that works in 8K mode can
silently do nothing in Ultimax because it touches memory that is not there.

## Writing cart-native code

ROM is not RAM. Three consequences:

- **`DATA` is read-only.** The cart linker config links `DATA` as `type = ro`
  into the ROM window. Mutable state goes in `BSS`, which every single-region
  config maps to a RAM area starting at `$0800` — `$0800-$7FFF` for 8K/16K, and
  only `$0800-$0FFF` for Ultimax, because that is all the RAM there is.
- **No self-modifying code in a ROM segment.** Copy the routine to RAM first.
- **Nothing below `$0800` is yours.** The generated 8K/16K stub calls `IOINIT`
  (`$FDA3`), `RAMTAS` (`$FD50`), `RESTOR` (`$FD15`) and `CINT` (`$FF5B`) before
  your code, so the machine is in the state a normal program finds — but that
  means `$0002-$0101` and `$0200-$03FF` are cleared by `RAMTAS` and
  `$0400-$07FF` by `CINT`.

An Ultimax cart has no KERNAL to call: the generated stub only does
`SEI / CLD / LDX #$FF / TXS` and jumps, and `cart_main` owns every piece of
hardware setup from there.

The build always reports `bytes` used and `free` left in the window — watch
`free` as the program grows rather than discovering the overflow at link time.

## EasyFlash

64 banks × 16 KB. Each bank has a LOROM window at `$8000-$9FFF` and a HIROM
window at `$A000-$BFFF`, and **both switch together** on a write to `$DE00`.

Boot state is Ultimax, so bank 0's HIROM window is what the CPU sees at
`$E000-$FFFF` and it carries the reset vectors. `c64 cart build` generates that
boot window for you; the manifest just has to give bank 0 a `hi:` entry, and
`c64 cart verify` fails an image that lacks one.

```yaml
name: BANKED
banks:
  0: {lo: main.s, hi: boot.s}
  1: {lo: far.s}
```

Every `.s` is linked independently against its own window's config; anything
else (a `.bin`, a data blob) is included verbatim. Banks may be sparse — empty
windows are dropped from the finished `.crt`, so gaps are normal, not
corruption. `boot.s` can be a single line, `.include "cart.inc"`: the generated
stub supplies the vectors.

Register-level detail — `$DE00`, `$DE02`, the boot sequence, the CHIP packet
layout — is in references/easyflash.md.

### The banking discipline

Because both windows switch together, **no ROM bank is ever resident** and one
bank can never `JSR` directly into another. Within *one* bank, LOROM and HIROM
are mapped at the same time, so a plain `JSR` from `$8000`-side code into
`$A000`-side code is fine. Everything else goes through the trampoline.

1. **Cross-bank calls go through the RAM-resident trampoline.** `cart.inc`
   provides `bankcall`, which saves the caller's bank, switches, calls, and
   switches back. Use the `ef_call` macro:

   ```asm
   ef_call 5, 2          ; call bank 5's jump-table entry 2
   ```

2. **Every code bank publishes a jump table at `$9F00`.** Banks are linked
   independently, so a fixed address is the only stable thing a caller can
   name. Declare entries in order with `ef_entry`; the index is the position,
   and the LOROM config reserves the whole `$9F00` page for them (the author's
   part of a LOROM window is `$8000-$9EFF`).

   ```asm
   .segment "JUMPTAB"
           ef_entry update      ; entry 0
           ef_entry draw        ; entry 1
   ```

   Three bytes per entry, one page: the last usable index is
   **`EF_MAX_ENTRY` = 84**. `ef_call` with a larger index is an assembly-time
   `.error`, not a runtime surprise.

The jump table lives in the LOROM window, so `ef_call` always enters the target
bank's `$8000` side. Bank 0's HIROM window is the boot window and is linked for
`$E000`, not `$A000` — do not put `$A000` code there.

`ef_setbank` (A = bank) switches without calling, for streaming data out of a
bank; the caller switches back.

**Register discipline.** `ef_call` loads A with the bank and X with
`index * 3`, so **arguments arrive only in Y or in RAM**. `bankcall` returns
with A holding the caller's bank and the flags set from that pull — there is no
return value in A or in the flags. X and Y come back exactly as the callee left
them, so results go in X, Y, or RAM. Nested `ef_call`s are safe: the caller's
bank rides the stack, and the self-modified `JSR` has already executed by the
time a nested call rewrites it.

**Interrupts.** The runtime is not re-entrant from an interrupt. An IRQ handler
must not issue `ef_call` and must not read `$8000-$BFFF` expecting a particular
bank — an interrupt landing inside `bankcall`, between the operand write and
the `JSR`, corrupts the call in flight. Keep handlers in RAM or in code that is
in every bank.

### Where the resident block lives, and why

The trampoline runs at `$0900`. That address is not arbitrary — it was found by
failing twice:

| trampoline at | result |
|---|---|
| `$0334` (the cassette buffer) | crashed: `RAMTAS` clears `$0200-$03FF` |
| `$C000` | never reached: in Ultimax mode only `$0000-$0FFF` is RAM |
| **`$0900`** | works: inside the Ultimax RAM, above the `CINT` screen, below nothing that clears it |

`cart.inc` assembles the block **absolute** with `.org EF_RESIDENT` inside the
normal `CODE` segment. There is no `RAMCODE` segment and no `__RAMCODE_*`
import scheme: every bank includes `cart.inc` (every bank needs `ef_call` and
the address of `bankcall`), but only the boot window's config has anywhere to
put a RAM-resident segment, so a segment-based scheme would be a hard `ld65`
error in every other window. Assembling absolute also makes bank 5's
`jsr bankcall` and bank 0's resolve to the same byte of RAM by construction.

Two consequences to remember:

- The block is capped at **256 bytes** by the copy loop's 8-bit counter, not by
  a linker memory area. `cart.inc` asserts it at assembly time.
- Each window carries its own ~70-byte copy of the block in ROM; only the boot
  window's copy is ever executed. That is the price of the scheme, and it is
  paid in ROM you were not using.

EasyFlash window configs have **no `BSS` segment** — put mutable state at fixed
absolute addresses instead, and remember that until the cart leaves Ultimax
mode only `$0000-$0FFF` exists.

## Pitfalls

- **A missing CBM80 signature is silent.** The machine boots to BASIC and says
  nothing. The tell is the free-bytes count in the banner:
  `30719 BASIC BYTES FREE` instead of `38911`, because the ROM still occupies
  `$8000-$9FFF`. Run `c64 cart verify`.
- **The cassette buffer is not safe.** `RAMTAS` clears `$0200-$03FF`, so
  resident code at `$0334` is destroyed the moment the KERNAL initialises.
  This is the classic wrong answer for "where do I put the trampoline".
- **`$C000` does not exist during boot.** In Ultimax mode there is no RAM above
  `$0FFF` at all.
- **Bank overflow is a hard error, and should stay one.** Every window is
  exactly 8192 bytes; `c64 cart build` names the bank, the window and the
  overflow amount and always prints the per-bank fill table. Read the table
  and move code to another bank — never trim blindly to make it fit.
- **Calling into a swapped-out bank returns garbage, not an error.** If a
  routine is not in the currently mapped bank it does not exist. Use `ef_call`.
- **`$DE00` and `$DE02` are write-only on real hardware.** VICE lets you read
  them back and `c64 cart bank` does — fine for debugging, but never have the
  cartridge read its own bank register. Track the current bank in RAM, the way
  `cart.inc` does.
- **A `.crt` cannot be loaded into a running machine.** `c64 run game.crt`
  stops the session and boots a fresh one with the cartridge attached; there is
  no `READY.` to wait for, because the cart is already running.
- **Merged bank symbols are unique by name but not by address.** See below.

## Debugging a running cartridge

```
c64 run game.crt              # boots a fresh session with the cart attached
c64 cart bank                 # current bank, $DE00/$DE02, decoded mode
c64 watch add '$DE00' --store # break on every bank switch
c64 mem read '$8000' 32       # reads through the currently mapped bank
c64 rom disasm '$8000' 20     # same: live memory, currently mapped bank
c64 cart dump game.crt --bank 3 --window hi -o bank3hi.bin   # offline, any bank
```

Everything the monitor reads from `$8000-$BFFF` is the **currently mapped**
bank. There is no way to enumerate the unmapped ones from a running machine —
that is why `c64 cart bank` reports the registers instead of deriving the bank
from memory, and why `c64 cart dump` exists for looking at a bank you are not
in.

Symbols from a multi-bank build are bank-tagged: `b01lo_update` is `update` in
bank 1's LOROM window, and the prefix is what tells apart five banks that all
put code at `$8000`. The names are unique; **the addresses are not**. A
breakpoint is an address, so one set on `b01lo_update` also fires when a
different bank executes that same address, and a report that annotates an
address with the nearest symbol may name an arbitrary bank's copy. Confirm with
`c64 cart bank` after the break rather than trusting the label.

## The loop

1. Write the cart-native `.s` (or the bank sources plus the `.ef.yaml`).
2. Build: `c64 package prog.s --format crt` or `c64 cart build game.ef.yaml` —
   read the reported `free`, or the fill table.
3. `c64 cart verify game.crt` — before every boot, every time.
4. `c64 run game.crt`, then `c64 screen`, `c64 cart bank`, `c64 mem read` to
   observe. Use `c64 wait --text` for output and `c64 wait --break` for
   breakpoints, exactly as for a `.prg`.
5. Pin it down with a YAML test: a spec's `cart:` key takes a `.crt`, a `.s`
   (with `cart_type:`), or an `.ef.yaml` manifest, builds it, and powers on a
   machine with it attached — `c64 test run game.yaml`. A cart spec sets
   `cart:` *or* `program:`, never both, and the runner skips the `READY.` gate
   because a cartridge never shows one.

## References

- references/easyflash.md — `$DE00`/`$DE02` at register level, the measured
  boot sequence step by step, the `.crt` CHIP-packet layout for EasyFlash, and
  what `cartconv` demands of a raw image.
- Full command reference: `docs/cli.md` (the `Cartridges` section).
