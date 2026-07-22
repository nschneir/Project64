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
| FFB7 | READST | Read the I/O status word into A (bit 6 = EOF, bit 7 = device not present). |
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
