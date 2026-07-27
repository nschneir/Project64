---
name: disk-io-programming
description: Use when a Commodore 64 program has to touch a disk while it runs — loading levels, music or graphics on demand, saving a high-score file, or streaming a data file byte by byte. Covers the KERNAL LOAD/SAVE and channel calls, device and secondary-address conventions, reading the DOS error channel, and the build-boot-inspect loop for finding out what actually landed on the image.
---

# Disk I/O programming

The `c64 disk` commands build and inspect an image from the host. This skill is
about the other half: a program that uses the disk *while it runs* — a boot
loader that pulls in levels, music and graphics on demand, and a save file that
survives a power cycle.

Everything below was measured on this toolchain against a real emulated 1541.
The reference program is `tests/programs/disk-loader/`; it boots from a disk,
loads a second file off the same disk at runtime and prints it, and it runs as
part of the regression suite (`c64 test programs`).

## Loading a file

Three KERNAL calls, in this order:

```asm
        lda #1              ; logical file number (any non-zero value)
        ldx #8              ; device 8 — the first disk drive
        ldy #1              ; secondary address (see below)
        jsr $FFBA           ; SETLFS
        lda #namelen
        ldx #<name
        ldy #>name
        jsr $FFBD           ; SETNAM
        lda #0              ; 0 = load, 1 = verify
        jsr $FFD5           ; LOAD
        bcs failed          ; carry set = error, A = the KERNAL error code
        ; X/Y now hold the end address + 1
name:   .byte "DATA"
namelen = * - name
```

**The secondary address decides where the file lands, and it is the single most
common mistake:**

| SA | Behaviour |
|---|---|
| `1` | Load at the address in the file's own 2-byte PRG header. X/Y are ignored. |
| `0` | Ignore the header and load at the address passed in X/Y to `LOAD`. |

Measured both ways with the reference program: with SA=1 the payload appears at
`$C000`, the address in the data file's header and nowhere else in the source;
switch to SA=0 with `X/Y = $C800` and the same file lands at `$C800` while
`$C000` is left untouched.

A PRG's first two bytes are its load address, **not** data — they are consumed
either way. So if you write a level file with `c64 disk put level1.bin level1`
and load it with SA=1, the first two bytes of `level1.bin` are eaten as an
address and the rest lands wherever they pointed. Either give the data file a
real 2-byte header aimed at your buffer (see
`tests/programs/disk-loader/data.s`, which is a header plus a payload and
nothing else), or load it with SA=0 and name the address yourself.

**Filenames are PETSCII, and asm sources get that for free.** `c64 disk put`
takes a lowercase host name and CBM DOS stores it uppercase: dumping the
directory sector of the reference image with
`c64 disk block read game.d64 18 1` shows `data` on disk as `44 41 54 41`,
padded with `$A0`. That is exactly what ca65 emits for `.byte "DATA"`, so
**write the name in uppercase in assembly** and it matches. (In BASIC sources
the petcat rule is the opposite — lowercase there.)

**A runtime LOAD is silent — but only because BASIC made it so.** The KERNAL
prints `SEARCHING FOR` / `LOADING` when bit 7 of **MSGFLG (`$9D`)** is set,
and `RUN` clears it, so a loader reached through `RUN` says nothing while the
same loader `SYS`ed from the `READY.` prompt announces itself. Measured all
three ways on the reference program: `$9D` reads `$80` at the prompt; `SYS
2061` there prints `SEARCHING FOR DATA` / `LOADING`; and `POKE 157,0 : SYS
2061` prints nothing but the program's own output. Do not use the absence of
those messages as evidence a load happened — check the carry.

## Saving a file

```asm
        lda #1
        ldx #8
        ldy #0              ; SA 0 for SAVE
        jsr $FFBA           ; SETLFS
        lda #namelen
        ldx #<name
        ldy #>name
        jsr $FFBD           ; SETNAM
        lda #<start         ; set up a zero-page pointer to the start address
        sta $FB
        lda #>start
        sta $FC
        lda #$FB            ; A = the ZERO-PAGE ADDRESS of that pointer
        ldx #<end           ; X/Y = end address + 1
        ldy #>end
        jsr $FFD8           ; SAVE
        bcs failed
```

`SAVE` takes A as a *pointer to a pointer* — the zero-page location holding the
start address, not the address itself. The end is passed directly in X/Y and is
exclusive.

CBM DOS refuses to overwrite an existing file (`63 FILE EXISTS` in the error
table in `skills/c64-development/references/basic-internals.md`); the
save-and-replace form is the `@0:` prefix — `@0:SCORES` — or scratch the old
one first. The host side behaves the same way: writing a name that is already
on the image fails rather than replacing it (measured — `c64 disk put` on a
duplicate name exits 1 with "cannot open `SCORES' for writing on image").

## Streaming a file byte by byte

`LOAD` is all-or-nothing and needs somewhere to put the whole file. To read a
file incrementally — a level description, a text adventure's room data — open
a channel instead:

```asm
        jsr $FFC0           ; OPEN  (after SETLFS/SETNAM)
        ldx #1              ; logical file number
        jsr $FFC6           ; CHKIN — make it the input channel
loop:   jsr $FFCF           ; CHRIN — one byte in A
        ; ... consume A ...
        jsr $FFB7           ; READST — status; bit 6 set = end of file
        beq loop
        jsr $FFCC           ; CLRCHN — back to keyboard/screen
        lda #1
        jsr $FFC3           ; CLOSE
```

The name handed to SETNAM here carries the file's type and mode, not just its
name — `SCORES,S,R` to read the sequential file back, `SCORES,S,W` to create
it. See "PRG vs SEQ" below; leaving the type off does not do what you expect.

Check `READST` (`$FFB7`) after **every** read: bit 6 (64) is end of file and bit
7 (128) is device not present. The full bit table is in
`skills/c64-development/references/kernal-routines.md`.

Always `CLRCHN` before `CLOSE`, and close every file you open — an unclosed
write channel is what leaves a splat file behind and produces `60 WRITE FILE
OPEN` on the next access.

## Error handling

`LOAD`/`SAVE` return with the carry set and a KERNAL error code in A. Two
measured with the reference program:

| A | Meaning | How it was produced |
|---|---|---|
| 4 | FILE NOT FOUND | LOAD a name that is not on the image |
| 5 | DEVICE NOT PRESENT | `ldx #9` with only drive 8 attached |

The rest of the KERNAL's set (1 too many files, 2 file open, 3 file not open,
6 not input file, 7 not output file, 8 missing filename, 9 illegal device) is
the documented table and is not exercised here.

The KERNAL code is coarse. For the drive's own answer, read the command
channel — secondary address 15:

```asm
        lda #15
        ldx #8
        ldy #15
        jsr $FFBA           ; SETLFS
        lda #0
        jsr $FFBD           ; SETNAM — no name = just open the channel
        jsr $FFC0           ; OPEN
        ldx #15
        jsr $FFC6           ; CHKIN
        ; CHRIN now returns "62,FILE NOT FOUND,00,00"
```

From BASIC that is `open 15,8,15 : input#15,e,e$,t,s` (illegal in direct mode —
it has to be in a program). Codes `0` and `1` mean success; the error table is
in `skills/c64-development/references/basic-internals.md`. The string is the
same DOS status the host-side `c64 disk` commands parse, so a failure reads
identically from either end.

## Conventions worth internalising

- **Device 8** is the first drive. `c64 disk boot` and a plain `x64sc image.d64`
  autostart with `LOAD"*",8,1`, and on a drive that has not touched a file yet
  — which is the state at power-on, and the only state autostart cares about —
  `*` is the first directory entry. That is why `c64 disk build` writes a
  manifest's files in listed order and why the loader has to be first. **`*` is
  not a synonym for "first file" after that:** the drive remembers the last
  name it accessed and `*` matches that instead. Measured — `LOAD"DATA",8,1`
  followed by `LOAD"*",8,1` loads DATA a second time, leaving the first entry
  untouched. Name the file you mean.
- **PRG vs SEQ**: `c64 disk put` and `c64 disk build` write PRG files. A PRG
  carries a load address; a SEQ is a plain byte stream you read through a
  channel. The type lives in the *name* you hand to OPEN, after the filename:
  `open 2,8,2,"scores,s,w"` creates a sequential file for writing and
  `"scores,s,r"` reopens it for reading. Measured: leaving the type field out
  (`"scores,w"`) does not fall back to PRG — the drive created a SEQ either
  way, so spell the type out. Give a data file a deliberate PRG header and
  LOAD it instead, and life is simpler.
- **Names are PETSCII, max 16 characters**, and `"` `:` `,` `=` are DOS
  metacharacters that silently retarget an operation — `c64 disk` rejects them
  for you. `*` and `?` are wildcards, legal in a lookup (`c64 disk rm game.d64
  "lvl*"`) and not in a name.
- **Nothing is written back to your source tree unless you write it.** The
  emulator does write through to the attached host image, so a program that
  SAVEs modifies the `.d64` in your working copy.

## The dev loop

Serial loading runs at the drive's real speed, and it dominates the loop.
Measured with the reference program's runtime LOAD, one 16-block (4 KB) file:
**14.3 s unwarped, 2.2 s in warp.** Run the emulator in warp while developing
(`c64 session start --warp`; the test runner already does).

After a run, check what actually landed:

```
c64 disk ls game.d64                   # names, sizes, blocks free
c64 disk block read game.d64 18 0      # the BAM
c64 disk block read game.d64 18 1      # the first directory sector
c64 disk validate game.d64             # allocation check + repair
```

`c64 disk build game.disk.yaml` rebuilds the whole image reproducibly from a
manifest, so the loop is: edit → build → boot → observe. A YAML test can name
the manifest directly (`disk: game.disk.yaml`); the runner builds it, attaches
it at power-on and autostarts it, which is how `tests/programs/disk-loader/`
is regression-covered.

## Pitfalls

- **The load-address header is the recurring bug.** See the SA table: a data
  file loaded with SA=1 goes wherever its first two bytes say, which for a raw
  `.bin` is wherever the first two bytes of your data happen to point.
- **A full disk corrupts silently.** Writing past capacity leaves a truncated
  file and a wrong BAM behind. `c64 disk build` refuses such a manifest before
  formatting anything; with `c64 disk put` directly, check blocks free after.
- **`LOAD` clobbers memory you did not intend** when the header points
  somewhere unexpected. Verify with `c64 mem read` after the load rather than
  trusting the screen — a load into `$0400` looks like garbage, a load over
  your own code looks like a crash later.
- **Loading over BASIC's workspace.** `$C000-$CFFF` is the free 4 KB block and
  the natural target for runtime data; anything below `$A000` is competing with
  the program and its variables.
- **Do not SAVE to the disk a test boots from** without expecting the image on
  disk to change — the next run starts from the modified image.
- **A missing file is a carry bit, not a message.** Nothing is printed. If a
  program silently does nothing after a load, branch on carry and print A.

## References

- `references/kernal-disk-io.md` — every KERNAL disk entry point with its
  register contract, the ST status bits, and the DOS error codes.
- `skills/c64-development/references/kernal-routines.md` — the full KERNAL jump
  table these are drawn from.
- `skills/c64-development/references/basic-internals.md` — disk I/O from BASIC
  2.0 and the complete CBM DOS error table.
- `tests/programs/disk-loader/` — the working reference program: manifest,
  loader, and a data file that is nothing but a header and a payload.
