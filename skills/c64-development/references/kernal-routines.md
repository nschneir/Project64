# C64 KERNAL routine catalog

The KERNAL jump table at `$FF81-$FFF3` is the C64's stable public API —
call the `$FFxx` address and it JMPs into the ROM proper. Register
conventions below are cross-checked against the Commodore 64 Programmer's
Reference Guide. Disassemble any entry yourself with `c64 rom disasm NAME`.

## KERNAL jump table

| Addr | Name   | Contract |
|------|--------|----------|
| FF81 | CINT   | Initialize the screen editor and VIC-II. |
| FF84 | IOINIT | Initialize CIA I/O devices; start the IRQ timer. |
| FF87 | RAMTAS | RAM test/init; sets memory pointers, screen to $0400. |
| FF8A | RESTOR | Restore the default RAM vectors ($0314-$0333). |
| FF8D | VECTOR | Read (carry set) or set (carry clear) the RAM vectors; X/Y = table pointer. |
| FF90 | SETMSG | A = control/error message flags (bit 7 KERNAL, bit 6 control). |
| FF93 | SECOND | Send secondary address in A after LISTEN. |
| FF96 | TKSA   | Send secondary address in A after TALK. |
| FF99 | MEMTOP | Read (carry set, into X/Y) or set top of RAM. |
| FF9C | MEMBOT | Read (carry set, into X/Y) or set bottom of RAM. |
| FF9F | SCNKEY | Scan the keyboard matrix; updates $C5/$CB and the buffer. Normally called by the IRQ. |
| FFA2 | SETTMO | Set serial bus timeout flag (A). |
| FFA5 | ACPTR  | Input one byte from the serial bus into A. |
| FFA8 | CIOUT  | Output the byte in A to the serial bus. |
| FFAB | UNTLK  | Send UNTALK to the serial bus. |
| FFAE | UNLSN  | Send UNLISTEN to the serial bus. |
| FFB1 | LISTEN | Command device A to listen. |
| FFB4 | TALK   | Command device A to talk. |
| FFB7 | READST | Read the I/O status word ST into A (full bit table below). |
| FFBA | SETLFS | Set file parameters: A = logical file, X = device, Y = secondary address. |
| FFBD | SETNAM | Set filename: A = length, X/Y = pointer to the name. |
| FFC0 | OPEN   | Open the logical file set up by SETLFS/SETNAM. |
| FFC3 | CLOSE  | Close logical file A. |
| FFC6 | CHKIN  | Set input channel: `LDX #lfn / JSR $FFC6`. |
| FFC9 | CHKOUT | Set output channel: `LDX #lfn / JSR $FFC9`. |
| FFCC | CLRCHN | Restore default I/O (keyboard in, screen out). |
| FFCF | CHRIN  | Input one character into A (screen input shows a cursor). |
| FFD2 | CHROUT | Output the PETSCII byte in A to the current device. **Preserves A, X, Y.** `LDA #$93 / JSR $FFD2` clears the screen. |
| FFD5 | LOAD   | As BASIC LOAD: A = 0 load / 1 verify, X/Y = address (with secondary 0). |
| FFD8 | SAVE   | As BASIC SAVE: A = zero-page pointer to start address, X/Y = end. |
| FFDB | SETTIM | Set the jiffy clock from A/X/Y. |
| FFDE | RDTIM  | Read the jiffy clock into A/X/Y. |
| FFE1 | STOP   | Test the STOP key (`JSR $FFE1`; Z set if pressed). |
| FFE4 | GETIN  | Get one buffered keypress into A; **A = 0 (Z set) when none** — poll it like BASIC's `GET`. |
| FFE7 | CLALL  | Close all files, restore default channels. |
| FFEA | UDTIM  | Update the jiffy clock; normally called by the IRQ. |
| FFED | SCREEN | Return screen size: X = columns (40), Y = rows (25). |
| FFF0 | PLOT   | Read (carry set: X = row, Y = column) or set (carry clear) the cursor position. |
| FFF3 | IOBASE | Return the CIA base address ($DC00) in X/Y. |

## The I/O status word (ST)

READST returns the status byte at `$90`. What each bit means depends on the
device being used:

| Bit | Val | Cassette read | Serial bus | Tape verify / LOAD |
|-----|-----|---------------|------------|--------------------|
| 0 | 1 | — | write timeout | — |
| 1 | 2 | — | read timeout | — |
| 2 | 4 | short block | — | short block |
| 3 | 8 | long block | — | long block |
| 4 | 16 | unrecoverable read error | — | verify mismatch |
| 5 | 32 | checksum error | — | checksum error |
| 6 | 64 | end of file | EOI (end of data) | — |
| 7 | 128 | end of tape | device not present | end of tape |

The BASIC reserved variable `ST` reads this same byte; on the serial bus,
`ST = -128` (bit 7) means the device didn't answer, `ST = 64` (bit 6) is the
normal end-of-file after the last byte.

## BASIC-ROM entry points (below the jump table)

Unlike the KERNAL (three revisions with shifting internals), the BASIC ROM
`$A000-$BFFF` is a *single* unchanging revision, so these internal entry
points are about as stable as the jump table — handy from asm when you need
floating-point math or number/string output. Every address below was verified
with `c64 rom disasm` (and `$BDCD` run live); confirm any you depend on the
same way. Floating point flows through **FAC1** (`$61-$66`), with the second
operand in **ARG/FAC2** (`$69-$6E`); the result returns in FAC1.

| Addr | Name | Contract |
|------|------|----------|
| B391 | GIVAYF | Signed 16-bit int (A = high, Y = low) → FAC1; sets VALTYP (`$0D`) to 0 = numeric |
| B1AA | AYINT  | FAC1 → signed 16-bit int in `$64/$65` (verified round-trip) |
| BBA2 | MOVFM  | Load FAC1 from the 5-byte constant at A (low)/Y (high) |
| BBD4 | MOVMF  | Round FAC1 and store it as a packed 5-byte float at X (low)/Y (high) — the inverse of MOVFM |
| B86A | FADDT  | FAC1 = ARG + FAC1 |
| B853 | FSUBT  | FAC1 = ARG − FAC1 |
| BA2B | FMULTT | FAC1 = ARG × FAC1 |
| BB12 | FDIVT  | FAC1 = ARG ÷ FAC1 |
| BF7B | FPWRT  | FAC1 = ARG ^ FAC1 |
| BC2B | SIGN   | Sign of FAC1 → A (−1 / 0 / +1) |
| BC58 | ABS    | FAC1 = |FAC1| (clears the sign bit) |
| BCCC | INT    | FAC1 = INT(FAC1) |
| BDDD | FOUT   | FAC1 → ASCII digits at `$0100`; pointer returned in A (low)/Y (high) |
| AB1E | STROUT | Print the `$00`/quote-terminated string at A (low)/Y (high) |
| BDCD | LINPRT | Print the unsigned 16-bit int in A (high)/X (low) as decimal |

Quick "print a number": load A/X and `JSR $BDCD`. Signed or floating value:
`GIVAYF` → `FOUT` → `STROUT`. (LINPRT verified live: A = `$30`, X = `$39`
prints `12345`.)

**Detect the KERNAL revision** before trusting any *internal* KERNAL address:
`$FF80` (65408) holds the revision number — `$00` = original (901227-01/02),
`$03` = the common 901227-03 (verified: `$03` on the stock image). The
`$FFxx` jump table and the BASIC-ROM entries above are stable across revisions;
internal KERNAL routines are not.

**The USR vector** is the other BASIC→ML hook besides `SYS` (the cookbook's
"Call a KERNAL routine from BASIC" recipe covers the `SYS` side). `USR(x)`
evaluates `x` into FAC1, then `JMP $0310`. `$0310` holds a `JMP` opcode, so
point it at your routine by writing the address to `$0311/$0312` (785/786); the
routine reads the argument from FAC1 and leaves the result there before `RTS`.
Or overwrite the `JMP` itself: `POKE 784,96` (an `RTS` at `$0310`) makes
`USR(x)=x` (verified: `USR(6)` returns 6).

## Hardware vectors

| Addr | Name      | Points to (stock KERNAL 901227-03) |
|------|-----------|-------------------------------------|
| FFFA | NMI_VEC   | FE43 |
| FFFC | RESET_VEC | FCE2 |
| FFFE | IRQ_VEC   | FF48 |

The 60 Hz IRQ enters ROM at the IRQ_VEC target, then jumps through the RAM
vector CINV at `$0314` (default $EA31 — keyboard scan, jiffy clock, cursor).
Repoint `($0314)` to hook the interrupt; chain to the original address to
keep the system services running.

## BASIC zero-page pointers (cross-reference)

| Addr | Name   | Meaning                          |
|------|--------|----------------------------------|
| 002B | TXTTAB | Start of BASIC text (= $0801).   |
| 002D | VARTAB | End of program / start of vars.  |

Full zero-page map: zero-page.md.
