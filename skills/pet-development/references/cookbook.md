# Cookbook — tested recipes to copy and adapt

Every program here is complete, runs on a PET 4032, and is exercised by
`tests/test_docs_cookbook.py` (the assembly ones are built with real ca65;
the flagship ones run live on the emulator). Copy a recipe, rename things,
and build from there — they encode the conventions that trip people up
(lowercase BASIC, screen codes for pokes, jiffy pacing, the SYS stub).

## Contents

BASIC:
- [Game loop: non-blocking key read + jiffy pacing](#game-loop-non-blocking-key-read--jiffy-pacing)
- [Poke characters at a screen position](#poke-characters-at-a-screen-position)
- [Sound: a beep subroutine](#sound-a-beep-subroutine)
- [Switch character sets: uppercase/graphics vs lowercase](#switch-character-sets-uppercasegraphics-vs-lowercase)
- [Score HUD: poke a changing number to the screen](#score-hud-poke-a-changing-number-to-the-screen)

Assembly:
- [Game loop: poll GETIN, move a ball, pace with the jiffy clock](#game-loop-poll-getin-move-a-ball-pace-with-the-jiffy-clock)
- [Held-key input: steer with the key-down state at $97](#held-key-input-steer-with-the-key-down-state-at-97)
- [Sound: a beep from machine code](#sound-a-beep-from-machine-code)
- [Frame stepping: inspect a game loop one frame at a time](#frame-stepping-inspect-a-game-loop-one-frame-at-a-time)
- [Cheap pseudo-random byte (8-bit Galois LFSR)](#cheap-pseudo-random-byte-8-bit-galois-lfsr)
- [Point a pointer at screen row/column (plotaddr)](#point-a-pointer-at-screen-rowcolumn-plotaddr)
- [Static text without CHROUT (poke screen codes)](#static-text-without-chrout-poke-screen-codes)
- [Print a number as decimal digits](#print-a-number-as-decimal-digits)
- [IRQ wedge: run code 60×/second behind BASIC](#irq-wedge-run-code-60second-behind-basic)
- [Play a melody from a note table](#play-a-melody-from-a-note-table)

## BASIC recipes

### Game loop: non-blocking key read + jiffy pacing

`GET` returns immediately (empty string when no key), and the jiffy clock
`TI` ticks 60×/second — together they make a fixed-rate game loop. This one
prints a dot per frame at ~10 frames/second and quits on `Q`:

```basic
100 print "press q to quit"
110 t=ti
120 get k$
130 if k$="q" then print "bye" : end
140 rem --- update and draw the frame here ---
150 print ".";
160 if ti-t<6 goto 160
170 goto 110
```

Line 160 is the pacer: wait until 6 jiffies (1/10 s) have passed since the
frame started. Lower the 6 for a faster game.

### Poke characters at a screen position

Screen RAM starts at 32768 ($8000); the cell at row R (0–24), column C
(0–39) is `32768 + 40*R + C`. POKE **screen codes**, not PETSCII or CHR$
values (42 below is the screen code for `*`; letters are 1–26):

```basic
100 rem three stars on row 5, from column 10
110 for i=0 to 2
120 poke 32768 + 40*5 + 10 + i, 42
130 next i
140 print : print "done"
```

### Sound: a beep subroutine

Three pokes start a tone, two stop it (see the hardware reference for how
this works). Keep the subroutine and call it wherever a game needs a beep:

```basic
100 gosub 900
110 print "beeped" : end
900 rem --- beep for a quarter second ---
910 poke 59467,16 : poke 59466,15 : poke 59464,150
920 t=ti
930 if ti-t<15 goto 930
940 poke 59464,0 : poke 59467,0
950 return
```

Vary 59464 (the pitch: lower = higher note) and the 15-jiffy duration.

### Switch character sets: uppercase/graphics vs lowercase

The PET has two character sets, selected by the VIA peripheral control
register: `poke 59468,12` gives uppercase + graphics (the power-on set);
`poke 59468,14` gives lowercase + uppercase ("business" mode) — in it,
unshifted letters render lowercase and shifted ones uppercase. Text
adventures and anything wordy want mode 14. On the 12-inch-screen
machines (40xx/80xx, CRTC-based — including the default `pet4032`),
`print chr$(14)` / `print chr$(142)` switch the same thing from PETSCII
(and also adjust line spacing); the poke works on every model. Note this
changes the **glyphs the CRT draws**, not the screen codes in memory — so
`c64 screen` text (which decodes screen codes case-canonically — see
petscii.md's "How `c64 screen` decodes the screen" section) looks
identical either way; check `c64 screen --png` to see the case change.

```basic
100 rem lowercase (business) character set
110 poke 59468,14
120 print "hello from business mode"
130 rem to switch back: poke 59468,12
```

### Score HUD: poke a changing number to the screen

PRINT scrolls at the bottom and moves the cursor — wrong for a fixed
score display. Poke the digits instead: `STR$` gives the digits as
PETSCII, and for digits the PETSCII value IS the screen code (48–57), so
`ASC` of each character pokes directly. (`STR$` puts a sign blank first —
start at character 2.) A number that can *shrink* in width (100 → 99)
leaves its old last digit behind, so blank the cell after the digits too:

```basic
100 rem score digits at row 0, column 30
110 s=142
120 s$=str$(s)
130 for i=2 to len(s$)
140 poke 32768+30+i-2, asc(mid$(s$,i,1))
150 next
160 poke 32768+30+len(s$)-1,32 : rem blank trailing cell
170 print "done"
```

## Assembly recipes

### Game loop: poll GETIN, move a ball, pace with the jiffy clock

The complete shape of an action game: clear the screen, then loop —
read the keyboard without blocking (`GETIN` returns 0 in A when no key),
update, draw to screen RAM, and pace by watching the jiffy clock's low
byte. `Q` quits cleanly back to BASIC. A ball sweeps along row 12:

```asm
; ball.s — a moving ball paced at ~10 steps/second; Q quits.
CHROUT = $FFD2
GETIN  = $FFE4
JIFFLO = $8F                    ; low byte of the jiffy clock (60 Hz)
ROW12  = $8000 + 40*12          ; screen RAM, row 12

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$93
        jsr     CHROUT          ; clear the screen
main:   jsr     GETIN           ; key in A, or 0 if none
        cmp     #'Q'
        beq     done
        ldx     pos             ; erase the ball...
        lda     #$20            ; screen code for space
        sta     ROW12,x
        inx                     ; ...move right, wrapping at column 40...
        cpx     #40
        bne     nowrap
        ldx     #0
nowrap: stx     pos
        lda     #$2A            ; ...and redraw (screen code for *)
        sta     ROW12,x
        ldy     #6              ; pace: wait 6 jiffies (1/10 s)
pace:   lda     JIFFLO
w1:     cmp     JIFFLO
        beq     w1              ; spin until the clock ticks once
        dey
        bne     pace
        jmp     main
done:   rts                     ; back to BASIC (READY.)

pos:    .byte   0
```

To steer instead of auto-move, compare A against `#'A'`/`#'D'` after GETIN
and adjust `pos` accordingly; for keys *held down* (no repeat delay), read
the key-down location `$97` instead — the next recipe.

### Held-key input: steer with the key-down state at $97

GETIN returns *buffered* keypresses — good for menus, wrong for action
controls, where a held key must move you every frame and releasing must
stop you. The IRQ keyboard scanner maintains the key held right now at
`$97` (`$FF` = none). **On BASIC 4 machines the value is the key's
PETSCII** ('A' reads `$41`); on BASIC 2 it is a raw matrix index — so
target the 4032 and ship with `x64sc -model 4032` (see zero-page.md). A
paddle on row 12 that slides while A or D is held:

```asm
; keyhold.s — a paddle steered by HELD A/D keys read from $97.
CHROUT  = $FFD2
JIFFLO  = $8F
KEYDOWN = $97                   ; key down right now (BASIC 4: PETSCII)
ROW12   = $8000 + 40*12

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$93
        jsr     CHROUT          ; clear the screen
mainloop:
        ldx     pos
        lda     KEYDOWN
        cmp     #'A'            ; held A: slide left...
        bne     notl
        cpx     #0
        beq     notl            ; ...unless at the wall
        lda     #$20
        sta     ROW12,x         ; erase, move
        dex
notl:   lda     KEYDOWN
        cmp     #'D'            ; held D: slide right
        bne     notr
        cpx     #39
        beq     notr
        lda     #$20
        sta     ROW12,x
        inx
notr:   stx     pos
        lda     #81             ; the paddle (screen code: filled circle)
        sta     ROW12,x
        ldy     #3              ; pace: ~20 moves/second while held
pace:   lda     JIFFLO
pw:     cmp     JIFFLO
        beq     pw
        dey
        bne     pace
        jmp     mainloop

pos:    .byte   20
```

No key down, no motion; hold a key and it glides. Test it exactly like a
player holding the key: `c64 run keyhold.s`, then
`c64 key hold d --frames 5 --at mainloop` — the CLI re-pokes `$97` before
each frame (the IRQ rewrites it every tick) and frame-steps to your loop
label; read `c64 mem get pos` between holds. In a `c64 test run` YAML the
same protocol is the `poke:` + `until:` step pair.

### Sound: a beep from machine code

Same three VIA registers as the BASIC version, timed by the jiffy clock:

```asm
; beep.s — quarter-second beep, then OK.
CHROUT = $FFD2
JIFFLO = $8F

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$10
        sta     $E84B           ; shift register free-runs under timer 2
        lda     #$0F
        sta     $E84A           ; square-wave bit pattern
        lda     #150
        sta     $E848           ; pitch
        ldy     #15             ; ~1/4 second
bpace:  lda     JIFFLO
bw:     cmp     JIFFLO
        beq     bw
        dey
        bne     bpace
        lda     #0
        sta     $E848           ; silence...
        sta     $E84B           ; ...and release CB2
        lda     #'O'
        jsr     CHROUT
        lda     #'K'
        jsr     CHROUT
        rts
```

### Frame stepping: inspect a game loop one frame at a time

Debugging an animated program by letting it free-run is guesswork. Instead,
run to the loop-top label with `c64 until` and use `--count` to advance an
exact number of frames, inspecting between steps. This program bumps
`FRAMES` once per pass and spins a character in the top-right corner:

```asm
; frame counter: the smallest "game loop", for frame-stepping practice.
JIFFLO = $8F
CHROUT = $FFD2
SCREEN = $8000

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  ldx     #0
banner: lda     msg,x
        beq     init
        jsr     CHROUT
        inx
        bne     banner
init:   lda     #0
        sta     FRAMES
mainloop:
        inc     FRAMES          ; one more frame
        lda     FRAMES
        and     #3
        tax
        lda     spin,x
        sta     SCREEN+39       ; spinner, top-right corner
        ldy     #6              ; pace: 6 jiffies = 1/10 s per frame
pace:   lda     JIFFLO
pw:     cmp     JIFFLO
        beq     pw
        dey
        bne     pace
        jmp     mainloop

msg:    .byte   "FRAME COUNTER", $0D, $00
spin:   .byte   45, 78, 66, 77  ; screen codes: - / | \ (graphics slashes)

        .segment "BSS"
FRAMES: .res 1
```

The workflow, after `c64 run counter.s` (which registers the labels):

```
c64 until mainloop            # run to the top of the next frame, stay stopped
c64 mem read FRAMES 1         # symbols work here
c64 until mainloop --count 5  # advance exactly 5 frames, stay stopped
c64 mem read FRAMES 1         # the counter went up by exactly 5
c64 continue                  # back to real time
```

No in-program stepping scaffolding (gate flags, poke-to-advance loops) is
needed — the debugger provides deterministic stepping from outside.

Caveat: `c64 until` can only fire while the program still visits the label.
If play can branch away (death, menu, pause), the wait times out — and on
timeout the machine is left RUNNING with the checkpoint removed. For those
states, break at a code path that must still execute instead.

### Cheap pseudo-random byte (8-bit Galois LFSR)

Games need randomness; the PET has no hardware source. A one-byte Galois
LFSR gives a 255-value pseudo-random sequence for three instructions of
work. **The state must never be zero** — 0 is the LFSR's fixed point and
locks the generator. Seed once at startup; in a real game seed from the
jiffy clock so each run differs:

    lda $8f        ; jiffy low byte — changes 60x/second
    bne seeded
    lda #1         ; guard the zero lock
    seeded: sta seed

The demo below uses a fixed seed instead so its output is reproducible
(it stores the first three values at $03F0-$03F2 in the cassette-buffer
scratch area: 21, 178, 89).

```asm
; random.s — pseudo-random bytes from an 8-bit maximal Galois LFSR.
; Call `random`: a fresh pseudo-random byte comes back in A (and `seed`).

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$2a            ; fixed demo seed (must be nonzero)
        sta     seed
        jsr     random
        sta     $03f0
        jsr     random
        sta     $03f1
        jsr     random
        sta     $03f2
        rts                     ; back to BASIC (READY.)

random: lda     seed
        lsr                     ; shift right; old bit 0 -> carry
        bcc     nofb
        eor     #$b8            ; feedback taps -> maximal 255-byte cycle
nofb:   sta     seed
        rts

seed:   .byte   1
```

Range tricks, applied after `jsr random`: `and #$1f` for 0-31, or
reject-and-retry — `retry: jsr random / cmp #40 / bcs retry` — for an
unbiased 0-39. Branch back to the `jsr`, never into `random` itself:
entering the routine without a `jsr` means its `rts` pops *your* caller's
return address and control unwinds one level too far.

### Point a pointer at screen row/column (plotaddr)

Everything that draws needs `screen address = $8000 + row*width + col`.
On 40-column machines `row*40 = row*32 + row*8` — three shifts and an
add, no lookup table. The pointer lives in zero page ($FB/$FC — see
zero-page.md) so `(PTR),y` indirection works. On 80-column machines
(8032/8296) a row is 80 bytes: use `row*64 + row*16` (one more shift
pair) instead.

```asm
; plot.s — plotaddr: point PTR ($FB/$FC) at screen row/column.
; In: A = row (0-24), Y = column (0-39). Demo puts a '*' at row 10, col 20.
PTR = $fb

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$93
        jsr     $ffd2           ; clear the screen
        lda     #10             ; row 10
        ldy     #20             ; column 20
        jsr     plotaddr
        lda     #$2a            ; screen code for '*'
        ldy     #0
        sta     (PTR),y
        rts                     ; back to BASIC (READY.)

plotaddr:
        sty     PTR             ; park the column in PTR low
        asl                     ; row*2
        asl                     ; row*4
        asl                     ; row*8  (max 192 — still one byte)
        sta     row8
        lda     #0
        sta     PTR+1
        lda     row8
        asl                     ; row*16 ...
        rol     PTR+1
        asl                     ; row*32, high bits in PTR+1
        rol     PTR+1
        clc
        adc     row8            ; + row*8 = row*40 (low byte)
        bcc     nocarry
        inc     PTR+1
nocarry:
        clc
        adc     PTR             ; + column
        sta     PTR
        lda     PTR+1
        adc     #$80            ; + $8000 screen base (carry rides along)
        sta     PTR+1
        rts

row8:   .byte   0
```

### Static text without CHROUT (poke screen codes)

CHROUT ($FFD2) prints *at the cursor*: it moves the cursor and scrolls
the screen at the bottom row — wrong for a fixed HUD, score, or label.
Poke screen codes directly instead. ASCII source text folds to screen
codes with one compare: codes below $40 (digits, punctuation, space)
already ARE screen codes; letters $41-$5A fold down by $40
(`cmp #$40` leaves carry set exactly when the subtract is needed).

```asm
; hud.s — write a zero-terminated label by poking screen codes.
; Demo: "SCORE 000" at row 2, column 5. PTR = $FB/$FC (see zero-page.md).
PTR = $fb

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$93
        jsr     $ffd2           ; clear the screen
        lda     #<($8000 + 2*40 + 5)
        sta     PTR
        lda     #>($8000 + 2*40 + 5)
        sta     PTR+1           ; row 2, column 5
        ldy     #0
loop:   lda     msg,y
        beq     done
        cmp     #$40
        bcc     put             ; digit/punct/space: already a screen code
        sbc     #$40            ; letter: fold (carry set by the cmp)
put:    sta     (PTR),y
        iny
        bne     loop
done:   rts                     ; back to BASIC (READY.)

msg:    .byte   "SCORE 000", 0
```

The label reads back through `c64 screen` (letters and digits round-trip
through the decoder — see petscii.md), so `c64 wait --text "SCORE 000"`
works as a completion signal.

### Print a number as decimal digits

A HUD label is static; the score isn't. This converts a byte (0–255) to
three decimal digits by repeated subtraction and pokes them as screen
codes — digit `d` is screen code `48+d`, so `ora #48` converts directly.
Values below 100 show leading zeros (`007`); blank them by comparing the
digit to `#48` before storing if you care.

```asm
; digits.s — poke a byte as three decimal digits (demo: 142 at row 0, col 30).
POS = $8000 + 0*40 + 30

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$93
        jsr     $ffd2           ; clear the screen
        lda     #142
        jsr     putnum
        rts                     ; back to BASIC (READY.)

; A = value 0-255 -> three screen-code digits at POS
putnum: ldy     #0
hund:   cmp     #100
        bcc     hdone
        sbc     #100            ; carry is set by the cmp
        iny
        bne     hund
hdone:  pha                     ; remainder 0-99
        tya
        ora     #48             ; digit -> screen code '0'-'9'
        sta     POS
        pla
        ldy     #0
tens:   cmp     #10
        bcc     tdone
        sbc     #10
        iny
        bne     tens
tdone:  pha
        tya
        ora     #48
        sta     POS+1
        pla
        ora     #48
        sta     POS+2
        rts
```

### IRQ wedge: run code 60×/second behind BASIC

The jiffy interrupt enters ROM, pushes A/X/Y, then jumps through the RAM
vector at `($90)` — repoint it and your code runs every frame while BASIC
carries on. Rules: install with interrupts disabled (`sei`/`cli`), save
the old vector and **chain to it** (`jmp (oldvec)`) so the clock and
keyboard keep working, and keep the wedge short (it steals time from
every frame). One trap: `jmp (indirect)` has the famous 6502 bug when its
operand's low byte sits at `$xxFF`, so check that `oldvec` doesn't land
there — fine in this small demo (it assembles around `$0446`), but verify
in the label file (`c64 build` emits one) whenever you embed the wedge in
a bigger program. The demo counts 60 interrupts (~1 second), then
unhooks itself and stores `$2A` at `$03F1` as a done marker.

```asm
; wedge.s — hook ($90), count 60 jiffies behind BASIC, unhook, mark done.
IRQVEC = $90
COUNT  = $03F0                  ; cassette-buffer scratch
DONE   = $03F1

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #0
        sta     COUNT
        sta     DONE
        sei                     ; no IRQ while the vector is half-written
        lda     IRQVEC
        sta     oldvec
        lda     IRQVEC+1
        sta     oldvec+1
        lda     #<wedge
        sta     IRQVEC
        lda     #>wedge
        sta     IRQVEC+1
        cli
        rts                     ; back to BASIC — the wedge runs underneath

wedge:  inc     COUNT           ; A/X/Y were already pushed by the ROM
        lda     COUNT
        cmp     #60
        bcc     chain
        lda     oldvec          ; one second: put the old vector back...
        sta     IRQVEC
        lda     oldvec+1
        sta     IRQVEC+1
        lda     #$2a
        sta     DONE            ; ...and leave the marker
chain:  jmp     (oldvec)        ; ALWAYS continue into the ROM handler

oldvec: .word   0
```

### Play a melody from a note table

The beep recipes hold one tone; a tune is just a table of timer-2 periods
played in sequence. Periods come from the chromatic-scale table in the
hardware reference (hardware.md) — this demo uses `250, 198, 166, 125`,
and halving a period raises the note an octave. A zero terminates the
table. As always: zero `$E848` AND `$E84B` at the end or the last note
plays forever.

```asm
; tune.s — four-note rising jingle from a period table, then DONE.
CHROUT = $FFD2
JIFFLO = $8F

        .segment "LOADADDR"
        .word   $0401
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "1037", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$10
        sta     $E84B           ; sound on: SR free-runs under timer 2
        lda     #$0F
        sta     $E84A           ; square wave
        ldx     #0
note:   lda     tune,x
        beq     fin             ; 0 terminates the tune
        sta     $E848           ; period = pitch
        ldy     #12             ; ~1/5 s per note
npace:  lda     JIFFLO
nw:     cmp     JIFFLO
        beq     nw              ; spin until the jiffy clock ticks
        dey
        bne     npace
        inx
        bne     note
fin:    lda     #0
        sta     $E848           ; silence...
        sta     $E84B           ; ...and release CB2
        ldx     #0
msg:    lda     text,x
        beq     bye
        jsr     CHROUT
        inx
        bne     msg
bye:    rts

tune:   .byte   250, 198, 166, 125, 0
text:   .byte   "DONE", $0D, $00
```

Swap `tune` for your own periods from the table; double a value to drop
an octave. Durations: change the `ldy #12` per-note wait, or extend the
table format with a duration byte per note. The cleanup matters beyond
politeness: a free-running shift register interferes with cassette I/O
(the PET FAQ's classic warning), so silence it before any tape operation.

## Verifying a recipe-based program

Run it and assert on the screen, exactly like the tests here do:

```
c64 run mygame.s
c64 wait --text "expected output"
c64 screen
```

or wrap it in a YAML test (`c64 test run` — format in docs/cli.md).
