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
| B849 | FADDH  | FAC1 = FAC1 + 0.5 |
| B850 | FSUB   | FAC1 = mem(A/Y) − FAC1 |
| B853 | FSUBT  | FAC1 = ARG − FAC1 |
| B867 | FADD   | FAC1 = mem(A/Y) + FAC1 |
| B86A | FADDT  | FAC1 = ARG + FAC1 |
| BA28 | FMULT  | FAC1 = mem(A/Y) × FAC1 |
| BA2B | FMULTT | FAC1 = ARG × FAC1 |
| BA8C | CONUPK | Unpack mem(A/Y) into ARG — the prologue FADD/FSUB/FMULT/FDIV JSR (FPWR instead loads via MOVFM) |
| BAE2 | MUL10  | FAC1 = FAC1 × 10 |
| BAFE | DIV10  | FAC1 = FAC1 ÷ 10 |
| BB0F | FDIV   | FAC1 = mem(A/Y) ÷ FAC1 |
| BB12 | FDIVT  | FAC1 = ARG ÷ FAC1 |
| BBA2 | MOVFM  | Load FAC1 from the 5-byte constant at A (low)/Y (high) |
| BBD4 | MOVMF  | Round FAC1 and store it as a packed 5-byte float at X (low)/Y (high) — the inverse of MOVFM |
| BBFC | MOVFA  | Copy ARG → FAC1 |
| BC0C | MOVAF  | Copy FAC1 → ARG |
| BC1B | ROUND  | Round FAC1 using the overflow byte FACOV (`$70`) |
| BC2B | SIGN   | Sign of FAC1 → A (−1 / 0 / +1) |
| BC58 | ABS    | FAC1 = |FAC1| (clears the sign bit) |
| BC5B | FCOMP  | Compare FAC1 with mem(A/Y): A = 1 / 0 / $FF |
| BC9B | QINT   | FAC1 → 32-bit signed integer in `$62-$65` |
| BCCC | INT    | FAC1 = INT(FAC1) |
| BCF3 | FIN    | ASCII number at TXTPTR → FAC1 (the interpreter's number parser) |
| BF78 | FPWR   | FAC1 = ARG ^ mem(A/Y) — loads the exponent from mem(A/Y) into FAC1 via MOVFM (not CONUPK), so the base must already be in ARG; falls into FPWRT |
| BF7B | FPWRT  | FAC1 = ARG ^ FAC1 |
| BFB4 | NEGOP  | FAC1 = −FAC1 |
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

## BASIC interpreter internals

Where a stopped or wedged BASIC program actually is. These are the names
`c64 disasm` and `c64 reg` print, so a PC of `$A7AE` reads as `NEWSTT` — the
statement loop — rather than a bare number. Every address was confirmed on a
live machine (`c64 disasm NAME 8`, plus the `$A00C` statement-vector table as
an oracle for FOR/NEXT); they are entry points to call or break on, not a
calling convention — check the code before depending on register use.

| Addr | Name     | What it is |
|------|----------|------------|
| A000 | COLD_VEC | BASIC's cold-start vector — the word here is $E394 |
| A002 | WARM_VEC | BASIC's warm-start vector — the word here is $E37B |
| A38A | FNDFOR   | Search the stack for a FOR/GOSUB frame (walks upward from TSX) |
| A3B8 | BLTU     | Open up space in the program/variable area (block move up) |
| A3FB | GETSTK   | Stack-depth check; falls into OMERR when there is no room |
| A408 | REASON   | Memory-space check against FRETOP ($33) — the `?OUT OF MEMORY` gate |
| A435 | OMERR    | Load error 16 and fall into ERROR: `?OUT OF MEMORY` |
| A437 | ERROR    | Error dispatch: `JMP ($0300)`, X = error number; repoint $0300 to trap errors |
| A469 | ERRFIN   | Print the message, then ` ERROR IN <line>` unless CURLIN hi is $FF |
| A474 | READY    | Print `READY.` and drop into direct mode |
| A480 | MAIN     | Direct-mode main loop: `JMP ($0302)` |
| A49C | MAIN1    | Store the typed line into the program (tokenize, relink) |
| A533 | LNKPRG   | Rebuild the line-link pointers after an edit |
| A560 | INLIN    | Read one line into the input buffer until RETURN |
| A579 | CRUNCH   | Tokenize the input buffer: `JMP ($0304)` |
| A613 | FNDLIN   | Search the program for a line number |
| A68E | STXTPT   | Point TXTPTR ($7A) at the start of the program minus one |
| A742 | FOR      | The FOR statement (verified against the $A00C statement vectors) |
| A7AE | NEWSTT   | Execute the next statement — the interpreter's per-statement loop |
| A7E1 | GONE     | Execute the current statement: `JMP ($0308)` |
| A7ED | GONE3    | Token dispatch proper: token−$80, range-checked against 35 statements |
| AD1E | NEXT     | The NEXT statement (verified against the $A00C statement vectors) |
| AD8A | FRMNUM   | Evaluate an expression and demand a numeric result |
| AD9E | FRMEVL   | Evaluate an expression at TXTPTR into FAC1 |
| AE83 | EVAL     | Evaluate one term: `JMP ($030A)` — the hook for new functions |
| AEF1 | PARCHK   | Expect `(`, evaluate, expect `)` |
| AEF7 | CHKCLS   | Demand `)` at TXTPTR |
| AEFA | CHKOPN   | Demand `(` at TXTPTR |
| AEFD | CHKCOM   | Demand `,` at TXTPTR |
| AEFF | SYNCHR   | Demand the character in A at TXTPTR, else SNERR |
| AF08 | SNERR    | Load error 11 and jump to ERROR: `?SYNTAX ERROR` |
| B79E | GETBYT   | Evaluate a 0-255 expression into X |
| B7EB | GETNUM   | GETADR then CHKCOM then GETBYT — the `POKE addr,byte` parameter pair |
| B7F7 | GETADR   | FAC1 → unsigned 16-bit into LINNUM ($14/$15) |

## BASIC token dispatch tables

How a token becomes code. GONE3 takes the statement token − $80 and pushes
the word at STMDSP + 2×index (stored as handler − 1, RTS-dispatched); EVAL
reaches function handlers through the words at FUNDSP (stored directly).
RESLST is the keyword list CRUNCH tokenizes against — the last character
of each keyword has bit 7 set, and a token's value is $80 + its position.
Every handler address below was read out of the live STMDSP/FUNDSP tables
themselves (`c64 mem read $A00C 70` / `$A052 46`), not copied from a
reference — the ROM's own tables are the oracle.

| Addr | Name   | What it is |
|------|--------|------------|
| A00C | STMDSP | Statement dispatch table: 35 words, each handler − 1 |
| A052 | FUNDSP | Function dispatch table: 23 words |
| A080 | OPTAB  | Operator priority/dispatch table (runs up to RESLST) |
| A09E | RESLST | The keyword list; bit 7 marks each keyword's last character |

### Statement handlers (via STMDSP)

Naming: `#` forms take an N suffix (PRINTN = PRINT#, INPUTN = INPUT#);
where the statement's name is already a KERNAL jump-table label the
handler takes a `_STMT` suffix (the same disambiguation precedent as
BASIN/BSOUT). FOR ($A742) and NEXT ($AD1E) are in the interpreter table
above.

| Token | Addr | Name |
|-------|------|------|
| 80 | A831 | END |
| 83 | A8F8 | DATA |
| 84 | ABA5 | INPUTN |
| 85 | ABBF | INPUT |
| 86 | B081 | DIM |
| 87 | AC06 | READ |
| 88 | A9A5 | LET |
| 89 | A8A0 | GOTO |
| 8A | A871 | RUN |
| 8B | A928 | IF |
| 8C | A81D | RESTORE |
| 8D | A883 | GOSUB |
| 8E | A8D2 | RETURN |
| 8F | A93B | REM |
| 90 | A82F | STOP_STMT |
| 91 | A94B | ON |
| 92 | B82D | WAIT |
| 93 | E168 | LOAD_STMT |
| 94 | E156 | SAVE_STMT |
| 95 | E165 | VERIFY |
| 96 | B3B3 | DEF |
| 97 | B824 | POKE |
| 98 | AA80 | PRINTN |
| 99 | AAA0 | PRINT |
| 9A | A857 | CONT |
| 9B | A69C | LIST |
| 9C | A65E | CLR |
| 9D | AA86 | CMD |
| 9E | E12A | SYS |
| 9F | E1BE | OPEN_STMT |
| A0 | E1C7 | CLOSE_STMT |
| A1 | AB7B | GET |
| A2 | A642 | NEW |

### Function handlers (via FUNDSP)

Naming: the `$`-suffix functions use the Commodore-source D-for-dollar
convention (STRD = STR$, CHRD = CHR$, LEFTD/RIGHTD/MIDD likewise). USR
dispatches through the RAM JMP at $0310 (see the USR vector note above);
everything else lands in ROM. Numeric results return in FAC1.

| Token | Addr | Name |
|-------|------|------|
| B4 | BC39 | SGN |
| B5 | BCCC | INT |
| B6 | BC58 | ABS |
| B7 | 0310 | USR |
| B8 | B37D | FRE |
| B9 | B39E | POS |
| BA | BF71 | SQR |
| BB | E097 | RND |
| BC | B9EA | LOG |
| BD | BFED | EXP |
| BE | E264 | COS |
| BF | E26B | SIN |
| C0 | E2B4 | TAN |
| C1 | E30E | ATN |
| C2 | B80D | PEEK |
| C3 | B77C | LEN |
| C4 | B465 | STRD |
| C5 | B7AD | VAL |
| C6 | B78B | ASC |
| C7 | B6EC | CHRD |
| C8 | B700 | LEFTD |
| C9 | B72C | RIGHTD |
| CA | B737 | MIDD |

## KERNAL internals

**Revision caveat:** unlike the jump table and the BASIC ROM, these live
inside the KERNAL, which has three revisions. Addresses below were verified
on the stock 901227-03 image (`$FF80` = $03); re-verify with `c64 disasm`
before depending on one under a different KERNAL.

| Addr | Name      | What it is |
|------|-----------|------------|
| E37B | BASWARM   | BASIC warm start — CLRCHN, reset the I/O channel, back to READY |
| E394 | BASCOLD   | BASIC cold start — init vectors, init RAM, print the banner |
| E3BF | INITBAS   | Initialize BASIC's RAM: CHRGET, the USR JMP at $0310, pointers |
| E453 | INITBVEC  | Copy the default BASIC vectors ($0300-$030B) out of ROM |
| E505 | SCRORG    | SCREEN's body: X = 40 columns, Y = 25 rows |
| E518 | CINT1     | Screen-editor init proper (CINT's body) |
| E544 | CLSR      | Clear the screen using HIBASE ($0288) |
| E566 | HOME      | Cursor to 0,0 (clears PNTR and TBLX), then falls into SCRPOS |
| E56C | SCRPOS    | Walk the line-link table ($D9) to place the cursor on its logical line |
| E5A0 | INITIO    | Set the default I/O devices (DFLTN 0 / DFLTO 3) and the VIC registers |
| E5B4 | LP2       | Pull one character out of the keyboard buffer ($0277) and shift it down |
| E5CD | INLOOP    | The direct-mode input loop: spins on NDX ($C6) waiting for a key. **This is what `c64 wait --idle` watches** (`ops.IDLE_PC_RANGE` = $E5CD-$E5D4) |
| E716 | SCROUT    | Put one character on the screen (the screen half of CHROUT) |
| EA31 | IRQMAIN   | The default IRQ service routine: UDTIM, cursor blink, keyboard scan |
| EA87 | KEYSCAN   | Keyboard matrix scan (SCNKEY's body); sets SFDX ($CB) and KEYTAB ($F5) |
| F13E | GETCH     | GETIN's body: buffered key from NDX, or the current input channel |
| F157 | BASIN     | CHRIN's body — the default $0324 target |
| F1CA | BSOUT     | CHROUT's body — the default $0326 target; screen when DFLTO = 3 |
| F6ED | STOPCHK   | STOP's body: compare STKEY ($91) with 127 |
| FCE2 | RESET     | Power-on/reset entry: SEI, stack to $FF, then the cartridge check |
| FD02 | CARTCHK   | Compare `$8004` against the `CBM80` signature to autostart a cartridge |
| FE43 | NMI       | ROM NMI entry: SEI then `JMP ($0318)` |
| FE47 | NMIHDLR   | The default NMI handler — the $0318 target (RESTORE key, RS-232) |
| FE66 | WARMRST   | Warm restart: restore vectors, re-init I/O and the editor, then BASIC |
| FF48 | IRQBRK    | The IRQ/BRK dispatcher: saves A/X/Y, then $0314 (IRQ) or $0316 (BRK) |

### Serial (IEC) and load/save internals

Each `$FFxx` serial call is one `JMP` from its body below — verified by
disassembling the jump-table entry and taking the target. N-prefixed
names mark the body of a same-named jump-table entry (the KERNAL
source's own convention for vectored bodies). The line-level helpers
drive CIA 2 at `$DD00` (bit 3 = ATN, bit 4 = clock out, bit 5 = data
out, all inverted on the bus — setting the bit pulls the line low).

`CLKLO`/`CLKHI` are swapped from the plan's original candidates: live
disassembly shows `$EE85` clearing bit 4 (release/HI) and `$EE8E`
setting it (pull-low/LO), the opposite of the candidate pairing, so
the names follow the code.

`NLOAD`/`NSAVE` are the `$FFD5`/`$FFD8` jump-table targets, confirmed
live the same way as the other entries here. Each stashes X/Y and then
jumps *indirectly* through its RAM vector (`JMP ($0330)` / `JMP
($0332)`); the live vector words read `$F4A5`/`$F5ED`, one level past
`NLOAD`/`NSAVE` themselves, not back at their own addresses — RESTOR's
"default" is that downstream continuation, not the fixed stub.

| Addr | Name   | What it is |
|------|--------|------------|
| ED09 | NTALK  | TALK's body: OR the device number with $40, send it under ATN |
| ED0C | NLISTN | LISTEN's body: OR the device number with $20, send it under ATN |
| EDB9 | SECND  | SECOND's body: send the secondary address after LISTEN |
| EDBE | SCATN  | Release ATN ($DD00 bit 3) |
| EDC7 | NTKSA  | TKSA's body: send the secondary address after TALK (bus turnaround) |
| EDDD | NCIOUT | CIOUT's body: buffer the byte in BSOUR ($95), transmit the previous one |
| EDEF | NUNTLK | UNTLK's body |
| EDFE | NUNLSN | UNLSN's body |
| EE13 | NACPTR | ACPTR's body: clock one byte in from the bus into A |
| EE85 | CLKHI  | Release the serial clock line (AND clears $DD00 bit 4) |
| EE8E | CLKLO  | Pull the serial clock line low (ORA sets $DD00 bit 4) |
| EE97 | DATAHI | Release the serial data line (AND clears $DD00 bit 5) |
| EEA0 | DATALO | Pull the serial data line low (ORA sets $DD00 bit 5) |
| EEA9 | DEBPIA | Debounced read of $DD00; serial data-in bit lands in carry via ASL |
| EEB3 | W1MS   | Busy-wait ~1 ms |
| F49E | NLOAD  | LOAD's body: stash X/Y, then jump indirect through ILOAD ($0330); the chain reached this way checks FA for device 1 = tape, else IEC |
| F5DD | NSAVE  | SAVE's body: stash X/Y, then jump indirect through ISAVE ($0332); same device-1-vs-IEC branch downstream |
