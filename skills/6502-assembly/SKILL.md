---
name: 6502-assembly
description: Use when writing or debugging 6502 assembly for the Commodore PET with ca65/ld65 via c64 build or c64 run. Covers the PET program skeleton, the BASIC SYS stub, calling ROM routines, and 6502 gotchas.
---

# 6502 assembly for the PET

Assemble with ca65/ld65 through `c64 build FILE.s` (produces a `.prg` plus a
VICE label file) or run in one step with `c64 run FILE.s` (assembles, loads,
and RUNs, registering the labels on the session for symbolic debugging). The
machine-level reference for addresses and ROM routines is the `c64-development`
skill's reference files (memory map, ROM routines, zero page, PETSCII).

## The program skeleton

A PET program loads at `$0401` and needs a tiny BASIC stub so that `RUN`
transfers control to your machine code. This skeleton assembles as-is (it is
the project’s `tests/programs/hello-asm` example):

```asm
; print a message via the ROM CHROUT routine, then return to BASIC.
; Layout: 2-byte load address ($0401), then a BASIC stub "10 SYS 1037",
; then code at $040D (= 1037).

CHROUT = $FFD2

        .segment "LOADADDR"
        .word   $0401

        .segment "EXEHDR"
        .word   nextln          ; pointer to next BASIC line
        .word   10              ; line number 10
        .byte   $9E, "1037", $00 ; SYS 1037
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

### Why SYS 1037

The load address `$0401` is emitted by the `LOADADDR` segment (not loaded into
RAM as data — it is the PRG header). Starting at `$0401` the `EXEHDR` segment
lays down a single BASIC line — next-line pointer, line number 10, the `SYS`
token `$9E`, the digits `"1037"`, and a `$00` terminator — followed by the
`$0000` end-of-program marker. That stub occupies 12 bytes (`$0401`–`$040C`),
so your `CODE` segment begins at `$040D`, which is decimal **1037**. Hence
`SYS 1037` jumps to `start`. Change the message and the code, not the stub.

Segments available in the linker config: `CODE`, `RODATA`, `DATA`, `BSS`
(and `ZEROPAGE`). Put executable code and mutable data in `CODE`/`DATA`,
constants in `RODATA`, and uninitialized storage in `BSS`.

## Calling ROM

Define the entry point and `jsr` it. CHROUT (`$FFD2`) prints the PETSCII byte
in `A` to the current output channel; return to BASIC with `rts`. The full
kernal jump table (CHRIN, GETIN, STOP, OPEN/CLOSE, …) and register conventions
are in the `c64-development` skill's ROM-routines reference. CHROUT expects
**PETSCII**, not a screen code — see that skill's PETSCII reference.

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
- **Segment state carries across `.include`.** ca65 does not reset the
  active segment at file boundaries: if one included file ends in
  `.segment "BSS"`, the next include's code assembles into BSS — address
  space that is *not in the .prg* — and the program crashes at runtime
  (typically a `?SYNTAX ERROR` or garbage when execution reaches the
  unloaded region). Start every included source file with an explicit
  `.segment "CODE"` (or the segment it really wants).
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
  blocking. Flush type-ahead by storing 0 to `$9E` (the buffer count).
- **Key-down state:** the IRQ's keyboard scan leaves the current key at `$97`
  (`#$FF` = no key) and the shift flag at `$98` — read these for continuous
  movement instead of waiting for key repeat. Details and the repeat-control
  locations: the `c64-development` skill's hardware and zero-page references.
- **Timing:** the jiffy clock at `$8D-$8F` (MSB first) increments 60×/second
  in the IRQ — compare its low byte for frame pacing, or hook the interrupt
  through the RAM vector at `($90)`.
- **Screen writes:** screen RAM starts at `$8000`; the byte for column X of
  row Y is at `$8000 + 40*Y + X` (80-column models: 80*Y). Store **screen
  codes**, not PETSCII. `lda #$93 / jsr CHROUT` clears the screen.
- **Sound:** three VIA registers (`$E84B`=`$10` on, `$E84A`=pattern,
  `$E848`=pitch; zero `$E848`/`$E84B` to stop) — see the hardware reference.

## Debugging

`c64 run FILE.s` registers the labels, so you can `c64 break add start`, then
`c64 wait --break`, `c64 reg`, `c64 step`, and `c64 mem read` your data by
symbol. Disassemble live memory (with your labels and ROM labels) via
`c64 rom disasm start 32`. Test one routine in isolation with
`c64 call ROUTINE` (fake JSR; stops at its RTS). For symptom-driven
procedures — corruption hunts, clobber audits, deterministic
reproduction — use the `6502-debugging` skill's playbook.
