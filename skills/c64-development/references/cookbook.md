# Cookbook — tested recipes to copy and adapt

Every program here is complete, runs on a C64, and is exercised by
`tests/test_docs_cookbook.py` (the assembly ones are built with real ca65;
the flagship ones run live on the emulator). Copy a recipe, rename things,
and build from there — they encode the conventions that trip people up
(lowercase BASIC, screen codes for pokes, color RAM, jiffy pacing, the SYS
stub).

## Contents

BASIC:
- [Game loop: non-blocking key read + jiffy pacing](#game-loop-non-blocking-key-read--jiffy-pacing)
- [Prompt loop: INPUT, validate, play again](#prompt-loop-input-validate-play-again)
- [Poke characters at a screen position](#poke-characters-at-a-screen-position)
- [Sound: a beep subroutine](#sound-a-beep-subroutine)
- [Switch character sets: uppercase/graphics vs lowercase](#switch-character-sets-uppercasegraphics-vs-lowercase)
- [Score HUD: poke a changing number to the screen](#score-hud-poke-a-changing-number-to-the-screen)
- [Show a sprite from BASIC](#show-a-sprite-from-basic)
- [Call a KERNAL routine from BASIC (SYS and 780-783)](#call-a-kernal-routine-from-basic-sys-and-780-783)

Assembly:
- [Game loop: poll GETIN, move a ball, pace with the jiffy clock](#game-loop-poll-getin-move-a-ball-pace-with-the-jiffy-clock)
- [Held-key input: steer with the current-key state at $CB](#held-key-input-steer-with-the-current-key-state-at-cb)
- [Sound: a beep from machine code](#sound-a-beep-from-machine-code)
- [Frame stepping: inspect a game loop one frame at a time](#frame-stepping-inspect-a-game-loop-one-frame-at-a-time)
- [Cheap pseudo-random byte (8-bit Galois LFSR)](#cheap-pseudo-random-byte-8-bit-galois-lfsr)
- [Point a pointer at screen row/column (plotaddr)](#point-a-pointer-at-screen-rowcolumn-plotaddr)
- [Static text without CHROUT (poke screen codes)](#static-text-without-chrout-poke-screen-codes)
- [Print a number as decimal digits](#print-a-number-as-decimal-digits)
- [IRQ wedge: run code 60×/second behind BASIC](#irq-wedge-run-code-60second-behind-basic)
- [Sprite setup and movement](#sprite-setup-and-movement)

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

### Prompt loop: INPUT, validate, play again

`INPUT` blocks until RETURN, prints its own `? ` after the prompt string,
and raises `?REDO FROM START` on non-numeric text typed to a numeric
variable (BASIC re-asks, so the loop survives it). `RND(1)` returns the
next value in 0..1 and `INT(RND(1)*N)+1` rolls 1..N — but the sequence is
identical after every reset, so seed it: `RND(-TI)` for a different game
each run, `RND(-1)` for a **fixed** sequence you can write a test against.

```basic
100 rem guess the number
110 poke 53280,0:poke 53281,11:poke 646,1
120 print "{clr}"
130 x=rnd(-ti)
140 print "    * guess the number *"
150 print
160 n=int(rnd(1)*100)+1:c=0
170 print "i am thinking of a number from 1 to 100"
180 print
190 input "your guess";g
200 c=c+1
210 if g>n then print "too high":goto 190
220 if g<n then print "too low":goto 190
230 print "you got it in";c;"guesses!"
240 print
250 input "play again (y/n)";a$
260 if a$="y" then 120
270 if a$="n" then print "bye":end
280 goto 250
```

Variable names are one or two characters on purpose: `guess` would tokenize
as fused keywords, and only the first two characters are significant
anyway. `print "you got it in";c;"guesses!"` needs no extra spaces —
BASIC prints a numeric value with a leading and trailing space of its own.

**Driving it from the CLI.** Screen output persists, so every prompt and
verdict repeats on screen; a bare `c64 wait --text "TOO HIGH"` matches the
copy from three turns ago and returns instantly. `wait --since` only counts
an occurrence landing *after the wait command starts* — but this loop
answers in far less than a CLI round-trip, so by the time `--since` takes
its baseline the fresh "TOO HIGH" is already on screen and already counted,
and the wait hangs waiting for a second one that never comes. `--since`
earns its keep on recipes with a real gap between the triggering key and
the result (an animation, a multi-second countdown); for an instant verdict
like this one, anchor to the screen cell instead — `wait --mem` polls the
byte directly, so there's no count to race:

```bash
c64 run guess.bas
c64 wait --text "YOUR GUESS?"
c64 key type "50\n"
c64 wait --mem "@6,0=20"                 # 20 = screen code 'T' (TOO HIGH/TOO LOW)
c64 screen --numbered                    # read off @row,col to confirm the verdict
```

In a YAML test, anchor each verdict to the row it lands on
(`assert: { mem: "@6,0", equals_text: "TOO HIGH" }`) as
`tests/programs/guess-the-number/` does — `since: true` has the identical
race in the step runner, since nothing separates a `key` step from the
`wait` step that follows it.

### Poke characters at a screen position

Screen RAM starts at 1024 ($0400); the cell at row R (0–24), column C
(0–39) is `1024 + 40*R + C`. POKE **screen codes**, not PETSCII or CHR$
values (42 below is the screen code for `*`; letters are 1–26). On the C64
every cell also has a color nybble at `55296 + 40*R + C` ($D800) — poke it
too, or the character can be invisible (same color as the background):

```basic
100 rem three stars on row 5, from column 10
110 for i=0 to 2
120 poke 1024 + 40*5 + 10 + i, 42
130 poke 55296 + 40*5 + 10 + i, 1 : rem color RAM: white
140 next i
150 print : print "done"
```

### Sound: a beep subroutine

The SID needs volume, an envelope, a frequency, and a gated waveform (see
the hardware reference). Keep the subroutine and call it wherever a game
needs a beep:

```basic
100 gosub 900
110 print "beeped" : end
900 rem --- beep for a quarter second ---
910 poke 54296,15 : poke 54277,9 : poke 54278,0
920 poke 54273,25 : poke 54272,30
930 poke 54276,17 : rem triangle + gate on
940 t=ti
950 if ti-t<15 goto 950
960 poke 54276,16 : rem gate off (release)
970 poke 54296,0
980 return
```

Vary 54273 (the pitch: higher = higher note) and the 15-jiffy duration.
The SID's voice and control registers are **write-only** — don't try to PEEK
them back. (The four read-only registers are $D419-$D41C: the paddles, the
oscillator-3 RNG at $D41B, and envelope 3 — see the hardware reference. For a
note-frequency table, see hardware.md's SID section.)

### Switch character sets: uppercase/graphics vs lowercase

The C64 has two character sets, selected by VIC-II memory setup bit 1:
`poke 53272,21` gives uppercase + graphics (the power-on set);
`poke 53272,23` gives lowercase + uppercase — in it, unshifted letters
render lowercase and shifted ones uppercase. Text adventures and anything
wordy want the lowercase set. `print chr$(14)` / `print chr$(142)` switch
the same thing from PETSCII. Note this changes the **glyphs drawn**, not
the screen codes in memory — so `c64 screen` text (which decodes screen
codes case-canonically — see petscii.md) looks identical either way; check
`c64 screen --png` to see the case change.

```basic
100 rem lowercase (business) character set
110 poke 53272,23
120 print "hello from business mode"
130 rem to switch back: poke 53272,21
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
140 poke 1024+30+i-2, asc(mid$(s$,i,1))
150 poke 55296+30+i-2, 1
160 next
170 poke 1024+30+len(s$)-1,32 : rem blank trailing cell
180 print "done"
```

### Show a sprite from BASIC

The minimum sprite: 63 data bytes in a free block, the pointer at 2040,
enable bit on, and a position. Block 13 = address 832 (the cassette
buffer — fine for a demo while tape is unused):

```basic
100 rem solid 24x21 sprite block in the cassette buffer
110 for i=0 to 62 : poke 832+i,255 : next
120 poke 2040,13      : rem sprite 0 data pointer: block 13 (832/64)
130 poke 53287,7      : rem sprite 0 color: yellow
140 poke 53248,160    : rem x
150 poke 53249,120    : rem y
160 poke 53269,1      : rem enable sprite 0
170 print "sprite on"
```

Sprites never appear in `c64 screen` text — inspect them with the purpose-built
commands (`c64 sprite status`, `c64 sprite show N`, `c64 sprite png N`), or
`c64 mem read '$D015' 1` (enable bits) and `c64 screen --png`. Policy and
testing rules: docs/superpowers/specs/graphics-and-sprites.md.

### Call a KERNAL routine from BASIC (SYS and 780-783)

`SYS` runs machine code, but KERNAL and BASIC ROM routines take their
arguments in the 6510 registers. Locations **780, 781, 782, 783** are copied
into A, X, Y, and the status register just before `SYS` jumps, and hold the
returned values afterward — so BASIC can drive the whole KERNAL jump table
(kernal-routines.md). This calls PLOT (`$FFF0` = 65520) to move the cursor to
row 10, column 5, then prints there; clearing carry with `POKE 783,0` tells
PLOT to *set* the position rather than read it:

```basic
100 rem move the cursor with kernal plot, then print there
110 poke 781,10 : poke 782,5 : poke 783,0 : rem x=row 10, y=col 5, p=carry clear
120 sys 65520 : rem plot ($fff0): set the cursor position
130 print "hi"
140 print : print "done"
```

`PEEK(781)` after `SYS 65517` (SCREEN, `$FFED`) likewise returns the column
count in X. Clearing carry (`POKE 783,0`) is safe; never *set* bit 2 of 783,
or you leave interrupts disabled and the keyboard goes dead.

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
JIFFLO = $A2                    ; low byte of the jiffy clock (60 Hz)
ROW12  = $0400 + 40*12          ; screen RAM, row 12
CROW12 = $D800 + 40*12          ; color RAM, row 12

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
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
        lda     #1              ; color RAM: white, so it's visible
        sta     CROW12,x
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
the current-key location `$CB` instead — the next recipe.

### Held-key input: steer with the current-key state at $CB

GETIN returns *buffered* keypresses — good for menus, wrong for action
controls, where a held key must move you every frame and releasing must
stop you. The IRQ keyboard scanner maintains the **matrix code** of the
key held right now at `$CB` (64 = none) — matrix codes, not PETSCII: A is
10, D is 18, space is 60 (see zero-page.md). A paddle on row 12 that
slides while A or D is held:

```asm
; keyhold.s — a paddle steered by HELD A/D keys read from $CB.
CHROUT  = $FFD2
JIFFLO  = $A2
KEYDOWN = $CB                   ; matrix code of the key down now (64 = none)
KEY_A   = 10
KEY_D   = 18
ROW12   = $0400 + 40*12
CROW12  = $D800 + 40*12

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$93
        jsr     CHROUT          ; clear the screen
mainloop:
        ldx     pos
        lda     KEYDOWN
        cmp     #KEY_A          ; held A: slide left...
        bne     notl
        cpx     #0
        beq     notl            ; ...unless at the wall
        lda     #$20
        sta     ROW12,x         ; erase, move
        dex
notl:   lda     KEYDOWN
        cmp     #KEY_D          ; held D: slide right
        bne     notr
        cpx     #39
        beq     notr
        lda     #$20
        sta     ROW12,x
        inx
notr:   stx     pos
        lda     #81             ; the paddle (screen code: filled circle)
        sta     ROW12,x
        lda     #1
        sta     CROW12,x        ; color RAM: white
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
`c64 key hold d --frames 5 --at mainloop` — the CLI re-pokes the matrix
code into `$CB` before each frame (the IRQ rewrites it every tick) and
frame-steps to your loop label; read `c64 mem read pos 1` between holds.
In a `c64 test run` YAML the same protocol is the `poke:` + `until:` step
pair.

### Sound: a beep from machine code

Same SID registers as the BASIC version, timed by the jiffy clock:

```asm
; beep.s — quarter-second beep, then OK.
CHROUT = $FFD2
JIFFLO = $A2

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #15
        sta     $D418           ; volume max
        lda     #9
        sta     $D405           ; attack/decay
        lda     #0
        sta     $D406           ; sustain/release
        lda     #25
        sta     $D401           ; frequency high
        lda     #30
        sta     $D400           ; frequency low
        lda     #17
        sta     $D404           ; triangle + gate on
        ldy     #15             ; ~1/4 second
bpace:  lda     JIFFLO
bw:     cmp     JIFFLO
        beq     bw
        dey
        bne     bpace
        lda     #16
        sta     $D404           ; gate off (release)
        lda     #0
        sta     $D418           ; volume off
        lda     #'O'
        jsr     CHROUT
        lda     #'K'
        jsr     CHROUT
        rts
```

SID registers are write-only — assert on the `OK` text (or your own state
bytes), never on SID readback.

### Frame stepping: inspect a game loop one frame at a time

Debugging an animated program by letting it free-run is guesswork. Instead,
run to the loop-top label with `c64 until` and use `--count` to advance an
exact number of frames, inspecting between steps. This program bumps
`FRAMES` once per pass and spins a character in the top-right corner:

```asm
; frame counter: the smallest "game loop", for frame-stepping practice.
JIFFLO = $A2
CHROUT = $FFD2
SCREEN = $0400
COLOR  = $D800

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
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
        lda     #1
        sta     COLOR+39        ; spinner cell: white
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

Games need randomness cheaper than calling into BASIC. A one-byte Galois
LFSR gives a 255-value pseudo-random sequence for three instructions of
work. **The state must never be zero** — 0 is the LFSR's fixed point and
locks the generator. Seed once at startup; in a real game seed from the
jiffy clock so each run differs:

    lda $a2        ; jiffy low byte — changes 60x/second
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
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
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

Everything that draws needs `screen address = $0400 + row*40 + col`.
`row*40 = row*32 + row*8` — three shifts and an add, no lookup table. The
pointer lives in zero page ($FB/$FC — see zero-page.md) so `(PTR),y`
indirection works. The same math with a `#$D8` base gives the color-RAM
cell.

```asm
; plot.s — plotaddr: point PTR ($FB/$FC) at screen row/column.
; In: A = row (0-24), Y = column (0-39). Demo puts a '*' at row 10, col 20.
PTR = $fb

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
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
        adc     #$04            ; + $0400 screen base (carry rides along)
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
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$93
        jsr     $ffd2           ; clear the screen
        lda     #<($0400 + 2*40 + 5)
        sta     PTR
        lda     #>($0400 + 2*40 + 5)
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
POS = $0400 + 0*40 + 30

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
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

The jiffy interrupt enters ROM at $FF48, pushes A/X/Y, then jumps through
the RAM vector CINV at `($0314)` — repoint it and your code runs every
frame while BASIC carries on. Rules: install with interrupts disabled
(`sei`/`cli`), save the old vector and **chain to it** (`jmp (oldvec)`,
default $EA31) so the clock and keyboard keep working, and keep the wedge
short (it steals time from every frame). One trap: `jmp (indirect)` has
the famous 6502 bug when its operand's low byte sits at `$xxFF`, so check
that `oldvec` doesn't land there — verify in the label file (`c64 build`
emits one) whenever you embed the wedge in a bigger program. The demo
counts 60 interrupts (~1 second), then unhooks itself and stores `$2A` at
`$03F1` as a done marker.

```asm
; wedge.s — hook CINV ($0314), count 60 jiffies behind BASIC, unhook, mark done.
CINV   = $0314
COUNT  = $03F0                  ; cassette-buffer scratch
DONE   = $03F1

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #0
        sta     COUNT
        sta     DONE
        sei                     ; no IRQ while the vector is half-written
        lda     CINV
        sta     oldvec
        lda     CINV+1
        sta     oldvec+1
        lda     #<wedge
        sta     CINV
        lda     #>wedge
        sta     CINV+1
        cli
        rts                     ; back to BASIC — the wedge runs underneath

wedge:  inc     COUNT           ; A/X/Y were already pushed by the ROM
        lda     COUNT
        cmp     #60
        bcc     chain
        lda     oldvec          ; one second: put the old vector back...
        sta     CINV
        lda     oldvec+1
        sta     CINV+1
        lda     #$2a
        sta     DONE            ; ...and leave the marker
chain:  jmp     (oldvec)        ; ALWAYS continue into the ROM handler

oldvec: .word   0
```

### Sprite setup and movement

The minimum hardware sprite from machine code: data in a free block,
pointer, color, position, enable — then move it by rewriting `$D000/$D001`.
Sprite data goes in its own segment-free block here (the cassette buffer,
block 13 = $0340); real programs put it in a dedicated `.byte` block (see
docs/superpowers/specs/graphics-and-sprites.md for the authoring rules). The demo
enables sprite 0 as a solid square, sweeps it right across the screen,
and writes a done marker at `$03F0`:

```asm
; sprite.s — enable sprite 0, sweep it right, leave $D015 on and a marker.
SPDATA = $0340                  ; block 13 (832 = 13*64); tape unused
JIFFLO = $A2

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  ldx     #62
fill:   lda     #$FF            ; solid 24x21 square
        sta     SPDATA,x
        dex
        bpl     fill
        lda     #13
        sta     $07F8           ; sprite 0 pointer: block 13
        lda     #7
        sta     $D027           ; sprite 0 color: yellow
        lda     #120
        sta     $D001           ; y
        lda     #1
        sta     $D015           ; enable sprite 0
        ldx     #30             ; x sweep: 30 -> 220
sweep:  stx     $D000
        ldy     #1              ; pace: 1 jiffy per step
space:  lda     JIFFLO
sw:     cmp     JIFFLO
        beq     sw
        dey
        bne     space
        inx
        cpx     #220
        bne     sweep
        lda     #$2a
        sta     $03F0           ; done marker
        rts                     ; sprite stays on screen (READY. behind it)
```

Sprites are drawn by the VIC-II, not stored in screen RAM — `c64 screen`
text never shows them. Verify with register reads (`$D015`, `$D000/$D001`)
and `c64 screen --png`; X > 255 additionally needs the MSB bit in `$D010`
(see hardware.md).

## Verifying a recipe-based program

Run it and assert on the screen, exactly like the tests here do:

```
c64 run mygame.s
c64 wait --text "expected output"
c64 screen
```

or wrap it in a YAML test (`c64 test run` — format in docs/cli.md).
