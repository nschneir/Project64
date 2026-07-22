# Commodore BASIC 2.0 internals (C64)

## Program storage

BASIC text starts at `$0801` (the byte at `$0800` is `$00`). A program is a
chain of lines, each laid out as:

```
[next-line pointer: u16 LE][line number: u16 LE][tokens and text ...][$00]
```

The next-line pointer holds the absolute address of the following line's first
byte. The program ends with a next-line pointer of `$0000` — since it follows
the previous line's `$00` terminator, the end of a program is three
consecutive zero bytes. The zero-page
pointer TXTTAB (`$2B/$2C`) points at the start; VARTAB (`$2D/$2E`) marks the
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

For the full C64 BASIC 2.0 token list, run `petcat -k2`.

## Source convention (petcat)

When writing `.bas` source for the tools, keywords AND string text go in
**lowercase** — lowercase ASCII becomes unshifted PETSCII, which the C64
displays as uppercase in its default uppercase/graphics mode. Uppercase
source becomes shifted PETSCII (graphics characters). See petscii.md.

## Timing and randomness (for games and tests)

- `TI` is the jiffy clock: 60ths of a second since power-on, kept by the IRQ
  in three bytes at `$A0-$A2` (most-significant first). `TI$` is the same
  clock as `"HHMMSS"`. A BASIC delay: `t=ti+60 : if ti<t goto <same line>`.
- `RND(1)` returns the next pseudo-random value in 0..1;
  `INT(RND(1)*N)+1` rolls 1..N. `RND(-X)` reseeds deterministically (useful
  for reproducible tests); `RND(0)` derives a value from CIA timers.
  The seed/last value lives at `$8B-$8F`.

## Disk I/O from BASIC 2.0

BASIC 2.0 has no disk commands beyond LOAD/SAVE/OPEN — DOS commands and
status travel over channel 15 (there is no `DS`/`DS$`; you read the error
channel yourself). The sequential-file pattern:

```
10 open 15,8,15           : rem command/error channel
20 open 2,8,2,"names,s,w" : rem create+open sequential for write
30 print#2,"first record"
40 close 2
50 open 2,8,2,"names,s,r" : rem open for read
60 input#2,a$
70 close 2
80 input#15,e,e$,t,s      : rem read the error channel
90 if e>1 then print "disk error";e;e$
```

Reading the error channel (`INPUT#15,E,E$,T,S`) returns
`code, text, track, sector`; `0` and `1` mean success. Common codes
(CBM DOS 2):

| E     | Meaning |
|-------|---------|
| 00    | OK |
| 01    | FILES SCRATCHED (count in the track field) |
| 20-24, 27 | READ ERROR (header/sync/data/checksum variants) |
| 25    | WRITE ERROR (verify failed) |
| 26    | WRITE PROTECT ON |
| 29    | DISK ID MISMATCH |
| 30-34 | SYNTAX ERROR in the DOS command (bad/long/no filename) |
| 50-52 | RECORD errors (relative files) |
| 60    | WRITE FILE OPEN (unclosed file — VALIDATE the disk) |
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
