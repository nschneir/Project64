# PET ROM routine catalog

The kernal jump table at `$FFC0-$FFEA` is stable across all PET BASICs —
call the `$FFxx` address and it JMPs into the version-specific ROM. Register
conventions below are cross-checked against Programming the PET/CBM (West);
the jump targets marked *(live)* are asserted against a running BASIC 4 x64sc
by `tests/test_docs_memory.py`. Disassemble anything yourself with
`c64 rom disasm NAME`.

## Kernal jump table

Jump targets per ROM family shown as B1 / B2 / B4.

| Addr | Name   | Contract | Jumps to |
|------|--------|----------|----------|
| FFC0 | OPEN   | Open a logical file (parameters from the file tables). | F52A / F521 / F560 *(live)* |
| FFC3 | CLOSE  | Close a logical file (A = logical file number). | F2C8 / F2A9 / F2DD |
| FFC6 | CHKIN  | Set input device: `LDX #lfn / JSR $FFC6`. Preserves A,X,Y. | F78B / F770 / F7AF |
| FFC9 | CHKOUT | Set output device: `LDX #lfn / JSR $FFC9`. Preserves A,X,Y. | F7DC / F7BC / F7FE |
| FFCC | CLRCHN | Restore default I/O (input 0 = keyboard at $AF, output 3 = screen at $B0). | F27D / F272 / F2A6 |
| FFCF | CHRIN  | Input one character into A (screen input shows a cursor). X,Y preserved. | F1DF / F1E1 / F215 |
| FFD2 | CHROUT | Output the PETSCII byte in A to the current device. **Preserves A, X, Y.** `LDA #$93 / JSR $FFD2` clears the screen. | F230 / F232 / F266 *(live)* |
| FFD5 | LOAD   | As BASIC LOAD. | F346 / F3C2 / F401 |
| FFD8 | SAVE   | As BASIC SAVE. | F69E / F69E / F6DD |
| FFDB | VERIFY | As BASIC VERIFY. | F4BB / F4B7 / F4F6 |
| FFDE | SYS    | As BASIC SYS. | F695 / F684 / F6C3 |
| FFE1 | STOP   | Test the STOP key (`JSR $FFE1` — aborts I/O and exits to READY if pressed; defeat by forcing $9B to #$FF). | F339 / F30F / F343 |
| FFE4 | GETIN  | Get one buffered keypress into A; **A = 0 (Z set) when none** — poll it like BASIC's `GET`. | F1CC / F1D1 / F205 |
| FFE7 | CLALL  | Close all files, restore default channels. | F2A4 / F26E / F2A2 |
| FFEA | UDTIM  | Update the jiffy clock / store scanned key (called by the IRQ). | F736 / F729 / F768 |

## BASIC 4 disk kernal ($FF93-$FFBD, BASIC 4 only)

Entry points for the BASIC 4 disk commands, one per command:

| Addr | Command | Addr | Command |
|------|---------|------|---------|
| FF93 | CONCAT  | FFAB | APPEND  |
| FF96 | DOPEN   | FFAE | DSAVE   |
| FF99 | DCLOSE  | FFB1 | DLOAD   |
| FF9C | RECORD  | FFB4 | CATALOG/DIRECTORY |
| FF9F | HEADER  | FFB7 | RENAME  |
| FFA2 | COLLECT | FFBA | SCRATCH |
| FFA5 | BACKUP  | FFBD | DS$ (disk status) |

## Hardware vectors

| Addr | Name      | Points to (B1 / B2 / B4) |
|------|-----------|--------------------------|
| FFFA | NMI_VEC   | CA60 / FCFE / FD49 |
| FFFC | RESET_VEC | FD38 / FCD1 / FD16 *(live)* |
| FFFE | IRQ_VEC   | E66B / E61B / E442 *(live)* |

The 60 Hz IRQ enters ROM at the IRQ_VEC target, then jumps through the RAM
vector at `($90)` (BASIC 4: $E455 *(live)*) — repoint `($90)` to hook the
interrupt (keyboard scan, clock, and cursor keep working if you chain to
the original address).

## BASIC zero-page pointers (cross-reference)

| Addr | Name   | Meaning                          |
|------|--------|----------------------------------|
| 0028 | TXTTAB | Start of BASIC text (= $0401).   |
| 002A | VARTAB | End of program / start of vars.  |

Full zero-page map: zero-page.md.
