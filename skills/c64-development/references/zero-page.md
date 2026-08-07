# Zero page and low memory (C64 BASIC 2.0 / KERNAL)

Entries marked *(live)* are asserted against a running x64sc by
`tests/test_docs_memory.py`; the rest are cross-checked against Mapping the
Commodore 64 — confirm with `c64 mem read` before depending on them in
anger.

## The 6510 port — memory banking

| Addr | Meaning |
|------|---------|
| 00   | 6510 data-direction register (default $2F) |
| 01   | 6510 I/O port (default **$37**): bit 0 LORAM (BASIC ROM in), bit 1 HIRAM (KERNAL ROM in), bit 2 CHAREN (1 = I/O at $D000, 0 = char ROM), bit 3 cassette write, bit 4 cassette switch sense (the one **input** bit — which is why the DDR default is $2F, not $3F), bit 5 cassette motor. `LDA #$35 / STA $01` banks out BASIC+KERNAL for an all-RAM machine — with interrupts disabled or repointed first. |

## BASIC memory-management pointer chain *(live)*

All little-endian word pairs.

| Addr  | Name   | Meaning                                   |
|-------|--------|-------------------------------------------|
| 2B/2C | TXTTAB | Start of BASIC text (= $0801)             |
| 2D/2E | VARTAB | End of program / start of variables       |
| 2F/30 | ARYTAB | Start of arrays                           |
| 31/32 | STREND | End of arrays (start of free memory)      |
| 33/34 | FRETOP | Bottom of string storage (grows downward) |
| 37/38 | MEMSIZ | Top of BASIC memory (= $A000)             |

Ordering invariant: TXTTAB <= VARTAB <= ARYTAB <= STREND <= FRETOP.

## Interpreter, clock, and interrupt

| Addr  | Meaning |
|-------|---------|
| 73-8A | CHRGET — BASIC's copied-to-RAM fetch-next-character routine (entry $73; CHRGOT $79 re-reads the current character; TXTPTR $7A/7B) |
| 41-42 | DATPTR — text address READ is pulling DATA from; RESTORE resets it to TXTTAB ($2B). Save/restore this pair to READ DATA out of order |
| 61-66 | FAC1, the primary floating-point accumulator ($61 exponent, bias 129; $62-65 mantissa; $66 sign); ARG/FAC2 at 69-6E. A USR/ML routine hands its result back to BASIC through FAC1 |
| 8B-8F | RND seed / the previous random number |
| 90    | Status byte ST (I/O status; source of BASIC's ST) |
| A0-A2 | TI jiffy clock, 3 bytes, **most-significant byte first**, +1 per 1/60 s *(live)* |
| (0314)| CINV — IRQ RAM vector, default $EA31 *(live)*; the 60 Hz interrupt jumps through here — repoint it to hook the interrupt (keyboard scan, clock, and cursor keep working if you chain to $EA31) |
| (0316)| CBINV — BRK RAM vector (default $FE66) |
| (0318)| NMINV — NMI RAM vector (default $FE47) |

## Keyboard and screen

| Addr  | Meaning |
|-------|---------|
| C5    | Matrix code of the key pressed at the last IRQ scan (64 = none) |
| C6    | Number of characters in the keyboard buffer (write 0 to flush) |
| CB    | Matrix code of the key held **right now** (SFDX; 64 = none) — what `c64 key hold` re-pokes *(live)* |
| C7    | Reverse-video flag (0 = normal) |
| 91    | Last-row keyboard scan (STKEY): 127 = STOP held, 255 = none (same row: 239 = SPACE, 223 = Commodore key) — poll STOP without the KERNAL *(live: 255 idle)* |
| CC    | Cursor-blink enable (BLNSW): 0 = cursor flashes, nonzero = suppressed (the OS suppresses it while a program runs); `POKE 204,0` shows a blinking cursor during a GET loop |
| D4    | Quote-mode flag (QTSW): nonzero = editor is in quote mode (cursor-control chars echo as reversed glyphs instead of acting); `POKE 212,0` force-exits it *(live: 0 idle)* |
| D1/D2 | Pointer to screen RAM of the current line |
| D3    | Cursor column within the line |
| D6    | Cursor screen line |
| F3/F4 | Pointer to color RAM of the current line |

Note the C64 stores **matrix codes**, not PETSCII, in $C5/$CB — the decoded
character only exists in the keyboard buffer ($0277). Matrix-code table:
`MATRIX_CODES` in `src/c64lib/ops.py` (space = 60, RETURN = 1).

## Free zero page for user ML pointers *(live)*

`(ptr),y` indirect addressing requires the pointer **in zero page**. These
bytes are safe for user pointers under BASIC (verified on live c64 and
c64pal by writing sentinels, then running FOR/RND/string-GC/float/GET BASIC
plus seconds of jiffy IRQs, and checking they survived —
`tests/test_docs_memory.py`):

| Addr    | Notes |
|---------|-------|
| FB-FE   | The conventional home for two user pointers ($FB/$FC and $FD/$FE). |

`$02` is also unused by BASIC/KERNAL, good for one scratch byte. Tape I/O
is the caveat: cassette operations use zero-page scratch; if your program
does tape I/O, re-verify with a sentinel test first.

## Free zero page once your program owns the machine *(live)*

Six bytes is not much when `(ptr),y` is the only indirect mode there is, and
the table above is deliberately conservative: it answers "free **while BASIC
is running**". A game that has taken the machine over — SYS'd in and never
coming back, no interpreter running, no ROM routine called — is in a
different situation. Almost everything BASIC owns is idle, and the only
thing still writing zero page is the KERNAL's own interrupt handler.

Measured the same way as the table above, on live `c64` and `c64pal`: a
program that owns the machine, uses no zero page itself, and paces on the
jiffy for 600 frames with interrupts **enabled** (so the jiffy update,
`SCNKEY` and the cursor blink all run, with real keystrokes fed partway
through). Every one of these 75 bytes came back holding its sentinel:

| Addr    | Bytes | Normally |
|---------|-------|----------|
| 02      | 1     | Unused by BASIC and the KERNAL — free under BASIC too. |
| 22-2A   | 9     | BASIC's INDEX1/INDEX2 scratch pointers ($22-$25) and its multiply work area ($26-$2A). |
| 4E-53   | 6     | BASIC numeric work area; $53 is the garbage collector's step size. |
| 57-60   | 10    | BASIC's floating-point temporaries (TEMPF1-TEMPF3). |
| 62-6E   | 13    | The working bytes of FAC1 and FAC2, BASIC's two floating-point accumulators. |
| 70-8F   | 32    | BASIC scratch, the CHRGET routine copied into RAM at $73-$8A, and the RND seed (RNDX) at $8B-$8F. |
| FB-FE   | 4     | The conventional user pointers — free under BASIC as well. |

**The caveats are the point.** These bytes are free *because* nothing that
uses them is running, so:

- **One ROM call takes them back.** A single `jsr CHROUT`, `jsr GETIN` or
  any other KERNAL/BASIC entry may use its own zero-page scratch, and
  returning to `READY.` puts all of it back in play at once. If your program
  prints through the ROM, treat only `$FB-$FE`/`$02` as yours.
- **$73-$8A is code, not scratch.** CHRGET is a subroutine living in RAM;
  overwrite it and BASIC cannot tokenize or execute another line until the
  machine is reset. That is fine for a game that never returns — and fatal
  for one that does.
- **The KERNAL IRQ still runs**, so everything it maintains stays off this
  table and is never free: `$A0-$A2` (jiffy clock), `$C5`/`$CB` (last and
  current key), `$C6` (buffer count), `$CC-$CF` (cursor blink state). Mask
  interrupts and you may have those too — but then you have also stopped the
  clock and the keyboard, which is usually not what you wanted.
- **Tape I/O reclaims low scratch**, exactly as in the under-BASIC table.

The standing advice below — save and restore, or move to `$C000` — still
applies to anything you are unsure of. What this table buys is the handful
of *fast* pointer pairs a game actually needs: `demos/ms-muncher` keeps its
screen and colour-RAM pointers in `$FB-$FE` and its tile-map and two blit
pointers in `$22-$27` on this basis — three pairs it could not otherwise
have had.

## Low memory (outside zero page)

| Addr        | Meaning |
|-------------|---------|
| 0200-0258   | BASIC input buffer (89 bytes) |
| 0277-0280   | Keyboard type-ahead buffer (10 chars; count at $C6) |
| 0300-030B   | BASIC RAM vectors: error $0300, main loop $0302, tokenize $0304, LIST $0306, execute-statement IGONE $0308 (→ $A7E4), eval $030A — repoint to extend BASIC (see basic-internals.md) |
| 030C-0312   | SYS register store $030C-$030F (A/X/Y/P = 780-783), then the USR JMP vector $0310-$0312 |
| 0314-0333   | KERNAL RAM vectors (CINV, CBINV, NMINV, IOPEN at $031A, ...) — KERNAL jump-table I/O entries like OPEN $FFC0 = `JMP ($031A)` dispatch through these *(live)* |
| 033C-03FB   | Cassette buffer (192 bytes at 828 decimal — the classic `SYS 828` home for small user ML if tape is unused) |
| 07F8-07FF   | Sprite data pointers for the default screen (block = address/64) |

**Claiming memory from your own ML:** the cassette buffer ($033C+) fits tiny
routines; `$C000-$CFFF` gives 4 KB BASIC never touches — the standard home
for anything real. If you need zero-page speed beyond $FB-$FE/$02, save and
restore what you use.

## Current I/O state

| Addr  | Meaning |
|-------|---------|
| 99/9A | Default input (DFLTN, 0 = keyboard) / output (DFLTO, 3 = screen) device, set by CHKIN/CHKOUT *(live: $9A = 3)* |
| BA    | FA — current device number (0 keyboard, 1 tape, 2 RS-232, 3 screen, 4-5 printer, 8-11 disk) |

## Handy control locations (pages 2-3)

*Mapping the Commodore 64*'s flag bytes worth knowing — mostly one-POKE
behavior switches (verified on a live machine unless noted):

| Addr (dec / $) | Effect |
|----------------|--------|
| 646 / $0286 | Current text color the OS writes into color RAM on every PRINT (0-15). `POKE 646,2` → red text *(verified)* |
| 648 / $0288 | Screen memory page (HIBASE); screen start = value×256. If you relocate the screen via $D018, POKE this too or the editor keeps writing to the old address |
| 650 / $028A | Key repeat: 128 = all keys repeat, 64 = none, 0 = default (cursor/space/INST-DEL only) *(verified)* |
| 653 / $028D | Live modifier flags: bit 0 SHIFT, bit 1 Commodore, bit 2 CTRL (values add). The only way to read a bare modifier — $C5/$CB don't show it |
| 657 / $0291 | 128 = lock the current character set (disable the SHIFT+Commodore case flip); 0 = allow it *(verified)* |
| 678 / $02A6 | Region flag set at power-on: 0 = NTSC (`c64`), 1 = PAL (`c64pal`) — a program can self-detect and adjust timing *(verified: 0 on NTSC)* |
| 780-783 | A / X / Y / status passed to (and returned from) the next `SYS` — how BASIC drives the KERNAL jump table (see cookbook.md) *(verified via PLOT)* |
| 808 / $0328 | STOP-key vector low byte: `POKE 808,239` disables RUN/STOP (STOP/RESTORE still works), `234` disables both but breaks LIST, `237` restores |

## The label database

The names `c64 disasm` and `c64 reg` annotate these bytes with, shipped in
`src/c64lib/data/rom_labels/basic2.lbl` — so `lda $c6` prints as
`lda $c6 (NDX)`. (`c64 mem read` does *not* see them: it resolves only the
session's own label file, and its hex dump carries no label gloss.)
Sections above are the *explanation*; this is the index.
Each address was checked on a live machine while the tranche was authored
(a memory read at a known state, or the ROM code that touches it — e.g.
`$45/$46` read `XY` after `10 XY=7`), but only the entries marked *(live)*
elsewhere in this file are re-asserted by the test suite.

| Addr | Name   | Byte(s) |
|------|--------|---------|
| 0000 | D6510  | 6510 data-direction register (default $2F) |
| 0001 | R6510  | 6510 I/O port — memory banking (default $37) |
| 0003 | ADRAY1 | Vector: FAC1 → signed integer (holds $B1AA) |
| 0005 | ADRAY2 | Vector: signed integer → FAC1 (holds $B391) |
| 0007 | CHARAC | String-scan terminator character |
| 0008 | ENDCHR | Second string-scan terminator |
| 000B | COUNT  | Input-buffer index / subscript count |
| 000C | DIMFLG | DIM in progress |
| 000D | VALTYP | Expression type: 0 = numeric, $FF = string |
| 000E | INTFLG | Integer-variable flag |
| 000F | GARBFL | String garbage-collection flag |
| 0010 | SUBFLG | Subscript / FN name allowed |
| 0011 | INPFLG | Which of INPUT / GET / READ is running |
| 0013 | CHANNL | Current I/O channel for PRINT |
| 0014 | LINNUM | 16-bit line-number scratch; where GETADR leaves its result |
| 0022 | INDEX  | Four bytes of pointer scratch ($22-$25) |
| 002B | TXTTAB | Start of BASIC text (= $0801) |
| 002D | VARTAB | End of program / start of variables |
| 002F | ARYTAB | Start of arrays |
| 0031 | STREND | End of arrays (start of free memory) |
| 0033 | FRETOP | Bottom of string storage |
| 0035 | FRESPC | String-work pointer |
| 0037 | MEMSIZ | Top of BASIC memory (= $A000) |
| 0039 | CURLIN | Line being executed; $FF in the high byte = direct mode |
| 003B | OLDLIN | Line CONT resumes at (set by STOP/END) |
| 003D | OLDTXT | Text pointer CONT resumes at |
| 003F | DATLIN | Line the last READ took DATA from |
| 0041 | DATPTR | Text address READ is pulling DATA from |
| 0043 | INPPTR | Source pointer for INPUT/READ |
| 0045 | VARNAM | Name (2 chars) of the variable being looked up |
| 0047 | VARPNT | Pointer to that variable's value |
| 0049 | FORPNT | Pointer to the current FOR loop's variable |
| 0061 | FACEXP | FAC1 exponent (bias 129) |
| 0062 | FACHO  | FAC1 mantissa ($62-$65) |
| 0066 | FACSGN | FAC1 sign |
| 0069 | ARGEXP | FAC2/ARG exponent |
| 006A | ARGHO  | FAC2/ARG mantissa ($6A-$6D) |
| 006E | ARGSGN | FAC2/ARG sign |
| 0070 | FACOV  | FAC1 rounding byte |
| 0073 | CHRGET | Fetch the next BASIC character (routine copied into RAM) |
| 0079 | CHRGOT | Re-read the current character (the `LDA` inside CHRGET) |
| 007A | TXTPTR | The address CHRGOT reads — BASIC's program counter |
| 008B | RNDX   | RND seed / previous random number (5-byte float) |
| 0090 | STATUS | I/O status byte ST |
| 0091 | STKEY  | Last-row keyboard scan; 127 = STOP held |
| 0093 | VERCK  | 0 = LOAD, 1 = VERIFY |
| 0098 | LDTND  | Number of open files |
| 0099 | DFLTN  | Default input device (0 = keyboard) |
| 009A | DFLTO  | Default output device (3 = screen) |
| 009D | MSGFLG | KERNAL message control (SETMSG's byte) |
| 00A0 | TIME   | Jiffy clock, 3 bytes, most-significant first |
| 00B7 | FNLEN  | Length of the current filename |
| 00B8 | LA     | Current logical file number |
| 00B9 | SA     | Current secondary address |
| 00BA | FA     | Current device number |
| 00BB | FNADR  | Pointer to the current filename |
| 00C1 | STAL   | Start address for LOAD/SAVE |
| 00C5 | LSTX   | Matrix code of the key pressed at the last IRQ scan (64 = none) |
| 00C6 | NDX    | Characters waiting in the keyboard buffer |
| 00C7 | RVS    | Reverse-video flag |
| 00C8 | LNEND  | End-of-line pointer for screen input |
| 00C9 | LXSP   | Cursor row/column where the current input started |
| 00CB | SFDX   | Matrix code of the key held right now (64 = none) |
| 00CC | BLNSW  | Cursor-blink enable (0 = blinking) |
| 00CD | BLNCT  | Cursor-blink countdown |
| 00CE | GDBLN  | Character under the cursor |
| 00CF | BLNON  | Cursor-blink phase |
| 00D0 | CRSW   | Input source: keyboard or screen line |
| 00D1 | PNT    | Pointer to screen RAM of the cursor's line |
| 00D3 | PNTR   | Cursor column within the line |
| 00D4 | QTSW   | Quote-mode flag |
| 00D5 | LNMX   | Logical line length (39 or 79) |
| 00D6 | TBLX   | Cursor screen line |
| 00D8 | INSRT  | Outstanding insert count |
| 00D9 | LDTB1  | Screen line-link table (25+1 bytes; bit 7 starts a logical line) |
| 00F3 | USER   | Pointer to color RAM of the cursor's line |
| 00F5 | KEYTAB | Pointer to the keyboard decode table in use |
| 00FB | FREEZP | Free for user pointers ($FB-$FE) |
