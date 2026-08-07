---
name: 6502-assembly
description: Use when writing or debugging 6502 assembly for the Commodore 64 with ca65/ld65 via c64 build or c64 run. Covers the C64 program skeleton, the BASIC SYS stub, calling ROM routines, and 6502 gotchas.
---

# 6502 assembly for the C64

Assemble with ca65/ld65 through `c64 build FILE.s` (produces a `.prg` plus a
VICE label file) or run in one step with `c64 run FILE.s` (assembles, loads,
and RUNs, registering the labels on the session for symbolic debugging). The
machine-level reference for addresses and ROM routines is the `c64-development`
skill's reference files (memory map, ROM routines, zero page, PETSCII).

## The program skeleton

A C64 program loads at `$0801` and needs a tiny BASIC stub so that `RUN`
transfers control to your machine code. (A cartridge is the exception: it is
ROM the machine maps at power-on, so it has no load address and no stub —
see the `cartridge-programming` skill.) This skeleton assembles as-is (it is
the project’s `tests/programs/hello-asm` example):

```asm
; print a message via the ROM CHROUT routine, then return to BASIC.
; Layout: 2-byte load address ($0801), then a BASIC stub "10 SYS 2061",
; then code at $080D (= 2061).

CHROUT = $FFD2

        .segment "LOADADDR"
        .word   $0801

        .segment "EXEHDR"
        .word   nextln          ; pointer to next BASIC line
        .word   10              ; line number 10
        .byte   $9E, "2061", $00 ; SYS 2061
nextln: .word   $0000           ; end of BASIC program

        .segment "CODE"
start:  ldx     #0
loop:   lda     msg,x
        beq     done
        jsr     CHROUT
        inx
        bne     loop
done:   rts

msg:    .byte   "HELLO FROM ASM", $0D, $00
```

### Why SYS 2061

The load address `$0801` is emitted by the `LOADADDR` segment (not loaded into
RAM as data — it is the PRG header). Starting at `$0801` the `EXEHDR` segment
lays down a single BASIC line — next-line pointer, line number 10, the `SYS`
token `$9E`, the digits `"2061"`, and a `$00` terminator — followed by the
`$0000` end-of-program marker. That stub occupies 12 bytes (`$0801`–`$080C`),
so your `CODE` segment begins at `$080D`, which is decimal **2061**. Hence
`SYS 2061` jumps to `start`. Change the message and the code, not the stub.

Segments available in the linker config: `CODE`, `RODATA`, `DATA`, `BSS`
(and `ZEROPAGE`). Put executable code and mutable data in `CODE`/`DATA`,
constants in `RODATA`, and uninitialized storage in `BSS`.

## Calling ROM

Define the entry point and `jsr` it. CHROUT (`$FFD2`) prints the PETSCII byte
in `A` to the current output channel; return to BASIC with `rts`. The full
kernal jump table (CHRIN, GETIN, STOP, OPEN/CLOSE, …) and register conventions
are in the `c64-development` skill's ROM-routines reference. CHROUT expects
**PETSCII**, not a screen code — see that skill's PETSCII reference.

**Quoted text in a `.byte` goes in UPPERCASE — the opposite of a `.bas`
file.** This is about the characters inside the quotes only; mnemonics,
labels and directives are case-insensitive to ca65, and lowercase (`lda`,
`jsr`) is this project's house style. The reason is that ca65 does no
character translation at all: `.byte "..."` emits raw ASCII, and ASCII
`A`-`Z` (`$41`-`$5A`) happens to coincide with the PETSCII codes for
letters, so `"HELLO"` prints HELLO. Lowercase ASCII `a`-`z` (`$61`-`$7A`)
is a *different* PETSCII range, which the power-on uppercase/graphics
charset draws as graphics glyphs — `.byte "hello"` prints `└┌○──`. A `.bas`
file behaves the other way round because petcat *does* translate on the way
in, which is why lowercase is the rule there. (Switch to the lowercase
charset and the mapping shifts again — see the cookbook's character-set
recipe.)

Printing a number is a ROM call too: **LINPRT (`$BDCD`)** prints the
unsigned 16-bit value in A (high) / X (low) as decimal, with no padding.
The cookbook's "Time a routine and print the jiffies" recipe uses it.

## 6502 gotchas

- The NMOS 6502 has **no** `BRA` (unconditional branch) and none of the 65C02
  additions — use `jmp` or a always-true conditional branch.
- Branches (`beq`, `bne`, …) reach only **±127 bytes**; use `jmp` for longer
  jumps.
- **Growing code breaks short branches.** Inserting instructions into a
  dispatch chain or handler pushes existing branches past ±127 bytes and
  ca65 fails with "Range error". In any block you expect to grow, prefer a
  `jmp` trampoline from the start — invert the branch over it:
  `beq :+ / jmp far_target / :` — and expect to convert several
  `bne`/`bcc` this way once a routine passes ~120 bytes (the Ms. Muncher
  dogfood hit this three separate times while adding features).
- Zero page is scarce and shared with BASIC/kernal — see the
  `c64-development` skill's zero-page reference before claiming zero-page
  locations.
- `jsr` pushes the return address **minus one**; `rts` compensates. This
  matters if you manipulate the stack directly.
- **Carry discipline:** `adc`/`sbc` always include the carry — `clc` before
  the first add and `sec` before the first subtract of each multi-byte chain.
- **Decimal-mode trap:** `sed` switches `adc`/`sbc` to BCD, and on the NMOS
  6502 an interrupt does *not* clear the D flag. `cld` once at program start
  (and in any interrupt handler that does arithmetic) keeps you in binary.
- **Compare sets carry as an *unsigned* test.** After `cmp`/`cpx`/`cpy`:
  `bcs` = register **≥** operand, `bcc` = register **<** operand, `beq` =
  equal. A compare touches only N/Z/C (never V), so `bmi`/`bpl` after a
  compare is *not* a valid magnitude test — reaching for it on unsigned
  bytes (screen coords, counters) is a classic wrong-branch bug.
- **`bit` loads N and V straight from the operand's top bits.** `bit addr`
  sets N to **bit 7** and V to **bit 6** of the memory byte (Z comes from
  `A AND M`; A is unchanged). So to poll a hardware status bit you need no
  mask for bits 6–7: `bit $d011 / bmi ...` branches on the raster MSB, `bvs`
  on bit 6. A mask in A is only needed to test bits 0–5.
- **Index-register asymmetry.** Zero-page indexed addressing uses **X only**
  (except `ldx`/`stx`, which take `zp,Y`); `Y` indexes absolute addresses
  but never zero page for general ops. And the read-modify-write ops
  (`asl`/`lsr`/`rol`/`ror`/`inc`/`dec`) accept **no `,Y` form at all**. ca65
  rejects the illegal encodings — a surprise when mechanically swapping an
  `,X` loop to `,Y`.
- **Segment state carries across `.include`.** ca65 does not reset the
  active segment at file boundaries: if one included file ends in
  `.segment "BSS"`, the next include's code assembles into BSS — address
  space that is *not in the .prg* — and the program crashes at runtime
  (typically a `?SYNTAX ERROR` or garbage when execution reaches the
  unloaded region). Start every included source file with an explicit
  `.segment "CODE"` (or the segment it really wants).
  `.include` resolves relative to the including file, so a multi-file
  program needs no `-I`: `c64 build main.s` finds `.include
  "nested/tables.s"` from `main.s`'s own directory, whatever directory
  the build runs from.
- **BSS is not in the .prg.** `.res` storage is just reserved address space
  — at load it holds whatever was in RAM (often `$AA`s), and a flag or
  timer that "should be zero" silently isn't. Initialize every mutable
  variable at startup; the tidy idiom is one contiguous block zeroed by a
  loop bounded by start/end labels.

For complete, tested game-loop and sound programs to copy from, see
`skills/c64-development/references/cookbook.md` (its assembly recipes are the
fastest starting point for an action game).

## Reading the keyboard and timing (game loops)

- **Buffered keys:** `jsr GETIN` (`GETIN = $FFE4`) returns the next buffered
  keypress in A, or **0 with the Z flag set when none** — poll it without
  blocking. Flush type-ahead by storing 0 to `$C6` (the buffer count).
- **Held-key state:** the IRQ's keyboard scan leaves the current key's
  **matrix code** at `$CB` (64 = no key; A=10, D=18, space=60) — read it
  for continuous movement instead of waiting for key repeat. Details and
  the joystick registers: the `c64-development` skill's hardware and
  zero-page references.
- **Timing:** the jiffy clock at `$A0-$A2` (MSB first) increments 60×/second
  in the IRQ — compare its low byte (`$A2`) for frame pacing, or hook the
  interrupt through the CINV RAM vector at `($0314)`.
- **An interrupt saves only PC and the status byte — not A/X/Y.** A handler
  that touches any register must preserve it, and only `A` and `P` push
  directly, so X and Y route through A:
  `pha / txa / pha / tya / pha` on entry, `pla / tay / pla / tax / pla / rti`
  on exit. Skip this and you corrupt whatever the IRQ interrupted. (Hooking
  CINV *after* the KERNAL's own save is gentler — it has already stacked the
  registers — but a raw `$0314`/`$FFFE` handler owns the whole job.)
- **Screen writes:** screen RAM starts at `$0400`; the byte for column X of
  row Y is at `$0400 + 40*Y + X`, with its color nybble at `$D800` + the
  same offset. Store **screen codes**, not PETSCII. `lda #$93 / jsr CHROUT`
  clears the screen.
- **Sound:** the SID at `$D400` — volume `$D418`, per-voice frequency,
  ADSR, and gated waveform; see the hardware reference and the cookbook's
  beep recipe. SID registers are write-only.

## Sprite invisible? Check in order

Work down this list before reaching for the emulator — most "invisible
sprite" bugs are exactly one of these, and checking in order finds the
actual cause fastest. Register meanings and priority/collision details:
the `c64-development` skill's hardware reference, "Sprites" section.

1. `$D015` — is the sprite's enable bit set?
2. The data pointer at `screen+$3F8` (`$07F8-$07FF` for the default screen)
   holds `data_address / 64`, not the data address itself.
3. The sprite data is aligned to a 64-byte boundary — a pointer can only
   select multiples of 64, so data starting anywhere else displays the
   wrong 63 bytes.
4. X is in the visible range **24-343** (X > 255 needs its bit set in
   `$D010`, one bit per sprite).
5. Y is in the visible range **50-249**. To align with text, sprite Y for
   text row R is `51 + 8*R` — the 25-row window spans rasters 51-250, so
   Y=50 is one raster line *above* row 0 (see the hardware reference's
   Sprites section).
6. Nothing has overwritten the sprite's own 63 bytes of data — a program
   that grew into its data region is a common cause (below).

## Where runtime data lives (and how it actually loads)

Sprite shapes, charsets, and other data your program writes at runtime
need RAM outside `CODE`/`DATA`/`BSS` — and outside anything the running
program itself touches (the sprite-overwrite case above).

**Picking a safe address.** Stay clear of the `$0801+` program area — your
code, then BASIC's variables/arrays/strings growing upward from the end of
it. `$3000-$3FFF` is a convenient hole below most BASIC-stub programs;
`$C000-$CFFF` is the 4 KB BASIC never touches at all if you need more
headroom or an address independent of program size (see the
`c64-development` skill's memory map). Either way, the trap is a `.prg`
that grows into its own data region as you add code: check that the end
address (`load_addr + len - 2`) still lands below wherever you placed the
data, every time the code grows.

**BSS consumes address space even though it ships no bytes.** `.res`
storage is allocated right after DATA, so the "check the end address"
rule above must count BSS too: a program with a bitmap at `$2000` or a
charset at `$3000` can grow until BSS silently overlaps it — the program
paints over its own variables with no build error and no crash, just
wrong pixels. Make the linker enforce the ceiling with a deferred
assertion next to the BSS variables:

    .import __BSS_LOAD__, __BSS_SIZE__
    .assert (__BSS_LOAD__ + __BSS_SIZE__) <= $2000, error, "BSS ran into the bitmap"

(`__BSS_LOAD__`/`__BSS_SIZE__` exist because the linker config declares
BSS with `define = yes`.) The assertion is evaluated at link time, when
the addresses are real; it fired twice during the 1812 demo's build and
is the reason that demo works.

**Getting a linked-in segment there.** A `.prg` is a *flat* binary — file
bytes map straight onto consecutive addresses starting at the load
address. That's no trouble for a hand-picked address you poke into
directly (like `$3000` above), but a segment you want the *linker* to place
at a high address needs the gap between it and `CODE` to ship as real zero
bytes in the file, or everything after the gap loads at the wrong address.
`c64 build --area` declares the area and writes that padding for you:

```sh
c64 build game.s --area 'HIGH=$4000:$2000'
```

```asm
        .segment "HIGH"
glyphs: .incbin "chars.bin"        ; assembles at $4000, wherever CODE ended
```

The flag caps `MAIN` at `$4000 - $0801` and adds `fill = yes` to it, which
pads `$0801-$3FFF` with zeros so the `HIGH` segment lands at `$4000` in the
finished file instead of collapsing to right after `MAIN`'s last real byte.
Areas are declared `define = yes`, so `__HIGH_LOAD__`/`__HIGH_SIZE__` are
available for the same kind of `.assert` as `__BSS_*` above. Repeat the flag
for more areas; they must be contiguous, since a hole between two of them
would shift the upper one.

The cost is file size: that padding is real bytes, so `--area 'HIGH=$4000:…'`
makes every build at least 14 KB. **For data the VIC never reads** — sprite
source art, charset source glyphs, level tables, anything only the CPU
touches — the cheaper move is to link it normally, last, and copy it above
`$4000` in the first instructions of your start routine. It then costs no
low RAM and no file size at all, which is what `demos/ms-muncher` does with
2,545 bytes of art. Reach for `--area` when the data has to be *at* a fixed
address (a charset on its 2 KB boundary, sprite blocks on their 64-byte
ones) rather than merely out of the way.

## Debugging

`c64 run FILE.s` registers the labels, so you can `c64 break add start`, then
`c64 wait --break`, `c64 reg`, `c64 step`, and `c64 mem read` your data by
symbol.

**Equates are not labels and never reach the label file.** `MULA = $24`
exists only inside the assembler: `ld65 -Ln` writes labels, so
`c64 mem write MULA 5` fails with "unknown symbol" while every `label:`
in the same file resolves. Export what a test or debug session needs to
name — `.exportzp MULA` for a zero-page equate, `.export` otherwise — and
it appears in the `.lbl` like any label. This bites every hardware equate
and every zero-page alias a test wants to poke.

Disassemble live memory (with your labels and ROM labels) via
`c64 rom disasm start 32`. Test one routine in isolation with
`c64 call ROUTINE` (fake JSR; stops at its RTS). For symptom-driven
procedures — corruption hunts, clobber audits, deterministic
reproduction — use the `6502-debugging` skill's playbook.
