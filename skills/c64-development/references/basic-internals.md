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

## How BASIC executes a statement (and why GOTO can be slow)

The interpreter's main loop runs each statement through the RAM vector
**IGONE at `$0308`** (default `$A7E4`, verified live). `$A7E4` calls CHRGET
(`$0073`) to fetch the first token, then dispatches: a command token
(`$80-$A2`) indexes the **command-address table at `$A00C`**, whose entries are
stored as *routine − 1* and pushed so CHRGET's `RTS` lands in the routine (e.g.
GOTO's slot holds `$A89F`, one before the routine at `$A8A0`).

**The GOTO/GOSUB gotcha:** finding the target line means walking the line-link
chain, and the search routine (`$A613`) always starts from `TXTTAB` (`$0801`).
GOTO compares the target to the *current* line (`$39/$3A`): a **backward** jump
(target ≤ current) rescans from the very start of the program every time; a
**forward** jump scans from the line after the current one. So in a large
program, a GOTO/GOSUB back to a low line number gets slower the bigger the
program is — keep hot-loop targets close, and put frequently-called subroutines
near the top so the scan is short.

**Extending BASIC** uses one of two classic hooks: repoint IGONE (`$0308`) to
intercept whole statements, or patch the RAM CHRGET routine — overwrite the
`CMP #$3A` at `$007C` (default `C9 3A`) with a `JMP` to your wedge and chain
back to the ROM master copy at `$E3AB`. This is how toolkits (RENUMBER, TRACE,
custom commands) attach to the interpreter.

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

## Keyword abbreviations (direct entry)

A keyword can be typed as its first letter(s) plus the **next letter held with
SHIFT**; `?` is the special case for PRINT. It tokenizes to the same single
byte (abbreviations save no memory) and LISTs back fully spelled. The one
catch: an abbreviation can pack a line past the 80-column logical-line limit,
and once such a line LISTs at full width it can no longer be edited in place.
Common ones (SHIFTed letter shown uppercase): `?`=PRINT, `pO`=POKE, `pE`=PEEK,
`gO`=GOTO, `goS`=GOSUB, `nE`=NEXT, `dA`=DATA, `sY`=SYS, `rE`=READ, `reT`=RETURN,
`reS`=RESTORE, `cH`=CHR$, `lE`=LEFT$, `mI`=MID$, `rI`=RIGHT$, `vA`=VAL. The
reserved variables have short forms too: `ST`, `TI`, `TI$`. (Full list:
Appendix A of the Programmer's Reference Guide.)

## Variables and numbers

- **Integers** (`A%`) store their *value* in 2 bytes, range -32768..32767.
  **Floats** (the default) store in **5 bytes**, computed to ~10 significant
  digits and printed to 9; magnitudes below 0.01 or above 999999999 print in
  scientific notation. Largest float ≈ **1.70141183E+38** (overflow →
  `?OVERFLOW`); smallest ≈ 2.93873588E-39 (underflow silently yields 0).
  But every *simple* variable's table entry is **7 bytes regardless of type**
  (2 name + 5 value slot — verified live), so `A%` as a scalar saves nothing;
  integers only save space as **arrays** (2 bytes/element vs 5).
- **Names**: only the **first two characters are significant** (`SCORE` and
  `SCORING` are the same variable); a name must start with a letter and must
  not contain a reserved keyword. Trailing `%` = integer, `$` = string, none =
  float.
- **Array memory**: 5 bytes of header + 2 bytes per dimension + per element
  2 (int) / 5 (float) / 3+length (string) bytes. An undimensioned array
  auto-DIMs to 11 elements (0-10) on first reference — a later explicit `DIM`
  of it then raises `?REDIM'D ARRAY`.

## BASIC runtime error messages

Distinct from the disk error channel above — these are interpreter errors,
printed as `?<MESSAGE> ERROR`:

> BAD DATA · BAD SUBSCRIPT · CAN'T CONTINUE · DEVICE NOT PRESENT · DIVISION BY
> ZERO · EXTRA IGNORED · FILE NOT FOUND · FILE NOT OPEN · FILE OPEN · FORMULA
> TOO COMPLEX · ILLEGAL DIRECT · ILLEGAL QUANTITY · LOAD · NEXT WITHOUT FOR ·
> NOT INPUT FILE · NOT OUTPUT FILE · OUT OF DATA · OUT OF MEMORY · OVERFLOW ·
> REDIM'D ARRAY · REDO FROM START · RETURN WITHOUT GOSUB · STRING TOO LONG ·
> SYNTAX ERROR · TYPE MISMATCH · UNDEF'D FUNCTION · UNDEF'D STATEMENT · VERIFY

The ones whose cause isn't obvious from the name:

- **REDO FROM START** — non-numeric text typed to a numeric `INPUT`; BASIC
  re-prompts on its own, so it is not fatal.
- **ILLEGAL DIRECT** — `INPUT` (or `GET`) used in direct mode instead of a
  running program (see the disk-I/O note above).
- **ILLEGAL QUANTITY** — a function argument out of range (`SQR` of a negative,
  `POKE` value > 255, bad array subscript in some paths).
- **STRING TOO LONG** — a string grew past 255 characters.
- **FORMULA TOO COMPLEX** — too many nested string expressions in one term.

## Math functions BASIC lacks — derive them

BASIC 2.0 provides only ABS, ATN, COS, EXP, INT, LOG, RND, SGN, SIN, SQR, TAN.
The rest are built from those (every line verified on a real C64; use
`ATN(1)*2` for π/2):

```
SEC(X)     = 1/COS(X)
CSC(X)     = 1/SIN(X)
COT(X)     = 1/TAN(X)
ARCSIN(X)  = ATN(X/SQR(-X*X+1))
ARCCOS(X)  = -ATN(X/SQR(-X*X+1)) + π/2
ARCSEC(X)  = ARCCOS(1/X)
ARCCSC(X)  = ARCSIN(1/X)
ARCCOT(X)  = -ATN(X) + π/2
SINH(X)    = (EXP(X)-EXP(-X))/2
COSH(X)    = (EXP(X)+EXP(-X))/2
TANH(X)    = (EXP(X)-EXP(-X))/(EXP(X)+EXP(-X))
ARCSINH(X) = LOG(X+SQR(X*X+1))
ARCCOSH(X) = LOG(X+SQR(X*X-1))
ARCTANH(X) = LOG((1+X)/(1-X))/2
```

Adapted from the PRG's "Deriving Mathematical Functions" appendix, whose
ARCSEC/ARCCSC/ARCCOT entries are given here in corrected form (the book's
printed versions have sign/argument errors).

## Strings, FRE, and garbage collection

- **`FRE(0)` is signed** — with more than 32767 bytes free it returns a
  *negative* number (verified: a fresh C64 prints a negative value). Real free
  bytes: `FRE(0) - (FRE(0)<0)*65536`. So `IF FRE(0)<100` misfires; always
  correct the wrap first.
- **String garbage collection is O(N²) in the *number* of live strings** (not
  their lengths) — roughly `0.75 ms × N²` on the C64 (≈1 s at 100 strings, ≈7 s
  at 300). It fires automatically when string space runs out, and the machine
  **hangs with the keyboard dead** during it (RUN/STOP can't interrupt). You
  mostly hit it with large **string arrays**; a few dozen scalar strings is a
  sub-second blip. Mitigate by keeping the string *count* down (packing two
  strings into one roughly quarters the pause, since halving N quarters N²), and
  by calling **`FRE(0)` at an idle moment** to force the unavoidable collection
  when it won't be noticed — `FRE(0)` always triggers a full GC.

## Robust text input

Plain `INPUT A$` chokes on commas and colons (`?EXTRA IGNORED`, the string is
truncated at the separator). Two fixes:

- **Read through a file**, which suppresses both the `?` prompt and the
  separator problem: `OPEN 3,3 : INPUT#3,A$ : CLOSE 3` reads the current screen
  line; `OPEN 5,0 : INPUT#5,A$` reads the keyboard with no prompt (verified: no
  `?` appears).
- **Quote-before-INPUT** — queue a leading `"` into the keyboard buffer so the
  whole line is taken literally: `POKE 631,34 : POKE 198,1 : INPUT A$` (631 =
  buffer start, 198 = character count; see zero-page.md).

## Reserving RAM from BASIC

To protect a block at the top of memory (charset, sprite data, ML) from BASIC,
lower MEMSIZ (`$37/$38` = 55/56) and `CLR`:

```
poke 56,peek(56)-8 : clr    : rem reserve 2 KB (8 pages) above BASIC
```

`CLR` resyncs the string pointers but **loses variables**, so do this before
defining any. To keep variables, set FRETOP (`$33/$34`), FRESPC (`$35/$36`) and
MEMSIZ (`$37/$38`) together to the same top and skip `CLR`. (For ML, `$C000`
gives 4 KB BASIC never touches — see zero-page.md.)
