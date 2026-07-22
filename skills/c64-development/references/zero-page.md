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

## Low memory (outside zero page)

| Addr        | Meaning |
|-------------|---------|
| 0200-0258   | BASIC input buffer (89 bytes) |
| 0277-0280   | Keyboard type-ahead buffer (10 chars; count at $C6) |
| 0300-0312   | BASIC RAM vectors (error, main loop, tokenize, ...) |
| 0314-0333   | KERNAL RAM vectors (CINV, CBINV, NMINV, IOPEN at $031A, ...) — KERNAL jump-table I/O entries like OPEN $FFC0 = `JMP ($031A)` dispatch through these *(live)* |
| 033C-03FB   | Cassette buffer (192 bytes at 828 decimal — the classic `SYS 828` home for small user ML if tape is unused) |
| 07F8-07FF   | Sprite data pointers for the default screen (block = address/64) |

**Claiming memory from your own ML:** the cassette buffer ($033C+) fits tiny
routines; `$C000-$CFFF` gives 4 KB BASIC never touches — the standard home
for anything real. If you need zero-page speed beyond $FB-$FE/$02, save and
restore what you use.
