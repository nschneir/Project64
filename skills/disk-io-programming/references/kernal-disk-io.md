# KERNAL disk I/O reference

The subset of the KERNAL jump table a program uses to talk to a drive, with the
register contract for each call. These are the same entry points listed in
`skills/c64-development/references/kernal-routines.md` — that file is the
authority for the whole table (and for the routines that have nothing to do
with disks); this one adds the disk-side detail and is checked against it by
`tests/test_docs_skills.py`, so the two cannot drift on an address.

The jump table is the *stable* interface: call `$FFD5`, never the ROM routine
it dispatches to.

## Setting a file up

| Addr | Name | In | Out | Notes |
|------|------|----|-----|-------|
| FFBA | SETLFS | A = logical file number, X = device, Y = secondary address | — | No I/O happens yet. A is any non-zero value you then use for CHKIN/CLOSE. Device 8 is the first drive. |
| FFBD | SETNAM | A = name length, X/Y = pointer to the name (lo/hi) | — | A = 0 means "no name" — required when opening the command channel. The name is PETSCII. |

Secondary address, for a drive:

| SA | Meaning |
|----|---------|
| 0 | LOAD: ignore the file's header, load at the address in X/Y. SAVE uses 0. |
| 1 | LOAD: load at the address in the file's own 2-byte PRG header. |
| 2-14 | A data channel opened with OPEN, for byte-by-byte reads and writes. |
| 15 | The command/error channel. |

## Whole-file transfers

| Addr | Name | In | Out | Notes |
|------|------|----|-----|-------|
| FFD5 | LOAD | A = 0 load / 1 verify; X/Y = load address, used only when SA = 0 | Carry clear on success, X/Y = end address + 1; carry set on failure with the error code in A | Call SETLFS and SETNAM first. Prints nothing when a running program calls it (measured). |
| FFD8 | SAVE | A = the **zero-page address** of a two-byte pointer to the start; X/Y = end address + 1 | Carry set on failure, error code in A | A is a pointer to a pointer, not the start address. The end is exclusive. Overwriting needs the `@0:` name prefix. |

## Channels

| Addr | Name | In | Out | Notes |
|------|------|----|-----|-------|
| FFC0 | OPEN | the SETLFS/SETNAM setup | Carry set on failure, error code in A | Opens the logical file. |
| FFC3 | CLOSE | A = logical file number | — | Close every file you open; an unclosed write channel leaves a splat file and DOS error 60 behind. |
| FFC6 | CHKIN | X = logical file number | Carry set on failure | The file must already be OPEN. Redirects CHRIN/GETIN to it. |
| FFC9 | CHKOUT | X = logical file number | Carry set on failure | The output twin of CHKIN; redirects CHROUT to the file. |
| FFCC | CLRCHN | — | — | Restore the default channels (keyboard in, screen out). Call it before CLOSE, and before printing anything again. |
| FFCF | CHRIN | — | A = one byte | Reads from the current input channel. Check READST after every call. |
| FFD2 | CHROUT | A = one PETSCII byte | — | Writes to the current output channel — the screen by default, the file after CHKOUT. Preserves A, X and Y. |
| FFE4 | GETIN | — | A = one byte, 0 (Z set) when there is none | Non-blocking. On a file channel it behaves like CHRIN; on the keyboard it is BASIC's `GET`. |
| FFB7 | READST | — | A = the ST status byte | The only way to see end-of-file and bus errors. Non-destructive; call it as often as you like. |

## The ST status byte

`READST` returns the byte at `$90`. On the serial bus (a disk drive) two bits
matter; the full three-column table, including the cassette meanings, is in
`skills/c64-development/references/kernal-routines.md`.

| Bit | Value | Serial bus |
|-----|-------|------------|
| 0 | 1 | write timeout |
| 1 | 2 | read timeout |
| 6 | 64 | EOI — the last byte has been read |
| 7 | 128 | device not present |

`bit 6 set` after a CHRIN means that byte was the last one; a drive that is
switched off answers with bit 7 and no data at all.

## KERNAL error codes (carry set from LOAD/SAVE/OPEN)

| A | Meaning |
|---|---------|
| 1 | too many files |
| 2 | file already open |
| 3 | file not open |
| 4 | file not found |
| 5 | device not present |
| 6 | file is not an input file |
| 7 | file is not an output file |
| 8 | filename missing |
| 9 | illegal device number |

Codes 4 and 5 are measured against a real emulated 1541 by
`tests/programs/disk-loader/` (loading an absent name, and pointing the loader
at device 9); the rest are the documented KERNAL set and are not exercised
here.

## DOS error codes (the drive's own answer, on channel 15)

The KERNAL code says only that something failed. The drive's reply — read
through secondary address 15 as `code,text,track,sector` — says what:

| Code | Meaning |
|------|---------|
| 00 | OK |
| 01 | FILES SCRATCHED (the count is in the track field) |
| 62 | FILE NOT FOUND |
| 63 | FILE EXISTS |
| 72 | DISK FULL |

The complete CBM DOS 2 table (read/write errors, syntax errors, relative-file
errors) is in `skills/c64-development/references/basic-internals.md`, together
with the BASIC form of the same read. Note that `01` is a *success* line: a
scratch that matched nothing answers with it too, and only the count field
tells the two apart — which is why `c64 disk rm` reports the count rather than
just an exit status.

The same status line is what the host-side tooling parses, so a failure looks
identical from inside the program and from `c64 disk ls` / `c64 disk validate`
on the host.

## Minimal call sequences

Load a file at the address in its own header:

```asm
        lda #1
        ldx #8
        ldy #1
        jsr $FFBA           ; SETLFS
        lda #4
        ldx #<name
        ldy #>name
        jsr $FFBD           ; SETNAM
        lda #0
        jsr $FFD5           ; LOAD
        bcs failed
name:   .byte "DATA"
```

Read the error channel:

```asm
        lda #15
        ldx #8
        ldy #15
        jsr $FFBA           ; SETLFS
        lda #0
        jsr $FFBD           ; SETNAM — no name
        jsr $FFC0           ; OPEN
        ldx #15
        jsr $FFC6           ; CHKIN
        jsr $FFCF           ; CHRIN, repeatedly, until READST says EOI
        jsr $FFCC           ; CLRCHN
        lda #15
        jsr $FFC3           ; CLOSE
```
