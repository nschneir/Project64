# Commodore BASIC internals

## Program storage

BASIC text starts at `$0401` (the byte at `$0400` is `$00`). A program is a
chain of lines, each laid out as:

```
[next-line pointer: u16 LE][line number: u16 LE][tokens and text ...][$00]
```

The next-line pointer holds the absolute address of the following line's first
byte. The program ends with a next-line pointer of `$0000` — since it follows
the previous line's `$00` terminator, the end of a program is three
consecutive zero bytes. The zero-page
pointer TXTTAB (`$28/$29`) points at the start; VARTAB (`$2A/$2B`) marks the
end of the program and the start of variables (see zero-page.md).

Because the link chain and VARTAB must be consistent, you cannot simply poke a
tokenized program into memory and RUN it — the pointers would be wrong. This is
why c64-tools loads programs via VICE autostart (which performs a real LOAD),
not by raw memory injection.

## Tokens

Keywords are stored as single bytes with bit 7 set. Common tokens (verified
against `petcat` — see tests/test_docs_rom_basic.py):

| Token | Byte |
|-------|------|
| END   | $80  |
| FOR   | $81  |
| NEXT  | $82  |
| DATA  | $83  |
| GOTO  | $89  |
| GOSUB | $8D  |
| REM   | $8F  |
| PRINT | $99  |
| SYS   | $9E  |

For the full token list of any BASIC version, run `petcat -k40` (BASIC 4.0),
`-k2` (BASIC 2.0), or `-k1p` (BASIC 1.0).

## Source convention (petcat)

When writing `.bas` source for the tools, keywords AND string text go in
**lowercase** — lowercase ASCII becomes unshifted PETSCII, which the PET
displays as uppercase. Uppercase source becomes shifted PETSCII (graphics
characters). See petscii.md.

## Timing and randomness (for games and tests)

- `TI` is the jiffy clock: 60ths of a second since power-on, kept by the IRQ
  in three bytes at `$8D-$8F` (most-significant first). `TI$` is the same
  clock as `"HHMMSS"`. A BASIC delay: `t=ti+60 : if ti<t goto <same line>`.
- `RND(1)` returns the next pseudo-random value in 0..1;
  `INT(RND(1)*N)+1` rolls 1..N. `RND(-X)` reseeds deterministically (useful
  for reproducible tests); `RND(0)` derives a value from the jiffy clock.
  The seed/last value lives at `$88-$8C`.

## Disk I/O from BASIC 4

BASIC 4 has native disk commands (their kernal entry points are in
rom-routines.md). The sequential-file pattern:

```
10 dopen#1,"names",w      : rem create+open for write (drive 0)
20 print#1,"first record"
30 dclose#1
40 dopen#2,"names"        : rem open for read
50 input#2,a$
60 dclose#2
```

After every disk operation check the status: `DS` is the numeric error code
and `DS$` the full message (`code, text, track, sector`). `0` and `1` mean
success. Common codes (CBM DOS 2):

| DS    | Meaning |
|-------|---------|
| 00    | OK |
| 01    | FILES SCRATCHED (count in the track field) |
| 20-24, 27 | READ ERROR (header/sync/data/checksum variants) |
| 25    | WRITE ERROR (verify failed) |
| 26    | WRITE PROTECT ON |
| 29    | DISK ID MISMATCH |
| 30-34 | SYNTAX ERROR in the DOS command (bad/long/no filename) |
| 50-52 | RECORD errors (relative files) |
| 60    | WRITE FILE OPEN (unclosed file — COLLECT the disk) |
| 61    | FILE NOT OPEN |
| 62    | FILE NOT FOUND *(live)* |
| 63    | FILE EXISTS |
| 64    | FILE TYPE MISMATCH |
| 70    | NO CHANNEL |
| 72    | DISK FULL |
| 73    | DOS MISMATCH |
| 74    | DRIVE NOT READY |

The 62 row is asserted live against a real drive image by
`tests/test_integration_disk.py`; the rest follow the standard CBM DOS 2
table (cross-checked against two period references).
