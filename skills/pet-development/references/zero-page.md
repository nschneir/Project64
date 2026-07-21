# Zero page and low memory (BASIC 4.0 / 2.0)

Locations below are for **BASIC 2.0 and 4.0** (they share this layout unless
noted). BASIC 1.0 (pet2001) uses a different layout — verify with
`c64 mem read` before relying on any of this there. Entries marked *(live)*
are asserted against a running x64sc by `tests/test_docs_memory.py`; the rest
are cross-checked against Programming the PET/CBM (West) — confirm with
`c64 mem read` before depending on them in anger.

## BASIC memory-management pointer chain *(live)*

All little-endian word pairs.

| Addr  | Name   | Meaning                                   |
|-------|--------|-------------------------------------------|
| 28/29 | TXTTAB | Start of BASIC text (= $0401)             |
| 2A/2B | VARTAB | End of program / start of variables       |
| 2C/2D | ARYTAB | Start of arrays                           |
| 2E/2F | STREND | End of arrays (start of free memory)      |
| 30/31 | FRETOP | Bottom of string storage (grows downward) |

Ordering invariant: TXTTAB <= VARTAB <= ARYTAB <= STREND <= FRETOP.

## Interpreter, clock, and interrupt

| Addr  | Meaning |
|-------|---------|
| 70-87 | CHRGET — BASIC's copied-to-RAM fetch-next-character routine (entry $76 = CHRGOT re-reads the current character) |
| 88-8C | RND seed / the previous random number |
| 8D-8F | TI jiffy clock, 3 bytes, **most-significant byte first**, +1 per 1/60 s *(live)* |
| (90)  | IRQ RAM vector — the 60 Hz interrupt jumps through here (BASIC 4: $E455) *(live)*; repoint it to hook the interrupt |
| (92)  | BRK RAM vector |
| (94)  | NMI RAM vector (BASIC 4) |
| 96    | Status byte ST (I/O status; source of BASIC's ST) |

## Keyboard and screen

| Addr  | Meaning |
|-------|---------|
| 97    | Key down right now: #$FF = none. **ROM-dependent value:** BASIC 4 (40-col) stores the key's *decoded PETSCII* (scanner `sta $97` at $E556, A loaded from the decode table at $E73E — 'A' reads as $41); BASIC 2 stores the *raw matrix index* (scanner at $E6C8; its table at $E6F7 feeds only the buffer). A program comparing $97 to PETSCII runs only on BASIC 4 — ship with `x64sc -model 4032` *(live)* |
| 98    | Shift key: 0 = no, 1 = yes |
| 9B    | Copy of $E812 used for the STOP-key test |
| 9E    | Number of characters in the keyboard buffer (write 0 to flush) |
| 9F    | Screen reverse flag (0 = normal) |
| A6    | Last keypress (used to suppress key repeat) |
| AF    | Current input device (0 = keyboard) |
| B0    | Current output device (3 = screen) |
| (C4)  | Pointer to screen RAM of the current line |
| C6    | Cursor column within the line |
| D8    | Cursor screen line |

## Free zero page for user ML pointers *(live)*

`(ptr),y` indirect addressing requires the pointer **in zero page** — the
cassette-buffer scratch areas below cannot serve. These bytes are safe for
user pointers on BASIC 2/4 (verified on live pet4032 AND pet8032 by
writing sentinels, then running FOR/RND/string-GC/float/GET BASIC plus
seconds of jiffy IRQs, and checking they survived —
`tests/test_docs_memory.py`):

| Addr    | Notes |
|---------|-------|
| FB-FE   | Free on 40- and 80-column machines; the conventional home for two user pointers ($FB/$FC and $FD/$FE). |

Tape I/O is the caveat for this whole region: cassette operations use
scratch through here on some ROMs, and disk-DOS zero-page use was not
exercised by the verification. If your program does tape or disk I/O,
re-verify with a sentinel test before trusting any of these.

## Low memory (outside zero page)

| Addr        | Meaning |
|-------------|---------|
| 0200-0250   | BASIC input buffer (81 bytes; a line maxes at 80 chars + null) |
| 026F-0278   | Keyboard type-ahead buffer (10 chars; count at $9E; max size configurable at $03EB on 40-col BASIC 4, $E3 on 80-col) |
| 027A-0339   | Cassette buffer #1 (a favorite home for small ML routines) |
| 033A-03F9   | Cassette buffer #2 / BASIC 4 DOS workspace (192 bytes at 826 decimal — the classic `SYS 826` home for user ML if tape and BASIC 4 disk commands are unused) |
| 03E9-03EE   | 40-col BASIC 4: key-repeat countdown/delay/flag ($03EE: 0 = repeat on, $40 = off) |

## BASIC 1.0 (pet2001) differences

BASIC 1 lays these out differently. The locations below are cross-validated
between two period references (West; Abacus ML guide) and the clock is
asserted live on a pet2001 by `tests/test_docs_memory.py`:

| Addr (B1)   | Meaning |
|-------------|---------|
| 0200-0202   | TI jiffy clock (MSB first) — *not* $8D-$8F *(live)* |
| 020D (525)  | Keyboard buffer count (POKE 525,0 flushes) |
| 020F-0218   | Keyboard buffer |

**Claiming zero page from your own ML:** everything above is owned by BASIC
or the kernal while BASIC runs. The safe scratch areas for user machine code
are the cassette buffers ($027A+) and, if you don't touch tape or BASIC 4
disk commands, unused slots there — not zero page. If you need zero-page
speed, save and restore what you use.
