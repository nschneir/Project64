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
- [Time a section of code with TI](#time-a-section-of-code-with-ti)
- [Pace a BASIC loop to the frame](#pace-a-basic-loop-to-the-frame)
- [Switch character sets: uppercase/graphics vs lowercase](#switch-character-sets-uppercasegraphics-vs-lowercase)
- [Score HUD: poke a changing number to the screen](#score-hud-poke-a-changing-number-to-the-screen)
- [Poke a letter string to the screen (PETSCII → screen codes)](#poke-a-letter-string-to-the-screen-petscii--screen-codes)
- [Show a sprite from BASIC](#show-a-sprite-from-basic)
- [Multicolor sprite from BASIC (ASCII art → DATA)](#multicolor-sprite-from-basic-ascii-art--data)
- [Call a KERNAL routine from BASIC (SYS and 780-783)](#call-a-kernal-routine-from-basic-sys-and-780-783)

Assembly:
- [Game loop: poll GETIN, move a ball, pace with the jiffy clock](#game-loop-poll-getin-move-a-ball-pace-with-the-jiffy-clock)
- [Held-key input: steer with the current-key state at $CB](#held-key-input-steer-with-the-current-key-state-at-cb)
- [Sound: a beep from machine code](#sound-a-beep-from-machine-code)
- [Frame stepping: inspect a game loop one frame at a time](#frame-stepping-inspect-a-game-loop-one-frame-at-a-time)
- [Cheap pseudo-random byte (8-bit Galois LFSR)](#cheap-pseudo-random-byte-8-bit-galois-lfsr)
- [Signed multiply: quarter squares, tables built at startup](#signed-multiply-quarter-squares-tables-built-at-startup)
- [Point a pointer at screen row/column (plotaddr)](#point-a-pointer-at-screen-rowcolumn-plotaddr)
- [Static text without CHROUT (poke screen codes)](#static-text-without-chrout-poke-screen-codes)
- [Print a number as decimal digits](#print-a-number-as-decimal-digits)
- [Time a routine and print the jiffies (LINPRT)](#time-a-routine-and-print-the-jiffies-linprt)
- [IRQ wedge: run code 60×/second behind BASIC](#irq-wedge-run-code-60second-behind-basic)
- [Sprite setup and movement](#sprite-setup-and-movement)
- [Sprite multiplexer: more objects than sprites](#sprite-multiplexer-more-objects-than-sprites)
- [Raster event chain: one sorted interrupt list per frame](#raster-event-chain-one-sorted-interrupt-list-per-frame)
- [Custom character set: copy the ROM charset to RAM and redefine glyphs](#custom-character-set-copy-the-rom-charset-to-ram-and-redefine-glyphs)
- [Multicolor bitmap: mode, clear, and one masked span](#multicolor-bitmap-mode-clear-and-one-masked-span)
- [Read the screen code you are moving into (collision by glyph)](#read-the-screen-code-you-are-moving-into-collision-by-glyph)

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
byte directly, so there's no count to race, provided you anchor the row the
verdict you are waiting for *will* land on: each turn prints two rows
further down (6, 8, 10, …), so re-using `@6,0` for the second guess matches
the first verdict instantly, the same stale-match trap `--text` has:

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

### Time a section of code with TI

`TI` is the jiffy clock — 60ths of a second, kept by the IRQ in `$A0-$A2`.
Reset it with `TI$="000000"` immediately before the part you care about and
read `TI` immediately after; assigning it to a variable first (`t=ti`) stops
the clock advancing while you format the report:

```basic
10 print "{clr}summing 1 to 2000..."
20 s=0
30 ti$="000000"
40 for i=1 to 2000
50 s=s+i
60 next i
70 t=ti
80 print "sum";s
90 print "took";t;"jiffies"
```

Prints `TOOK 458 JIFFIES` — 7.6 seconds. Two things to know before you
report a number from this:

- **`PRINT` puts a space in front of a positive number** (the slot where a
  minus sign would go), which is why `print "took";t` reads `TOOK 458` with
  no space in the source. The assembly equivalent, `LINPRT`, does *not* —
  see the LINPRT recipe below.
- **The clock's resolution is one jiffy**, so anything under a second is
  mostly quantization error: 9 jiffies means 9±1, a 22% band. To time
  something fast, repeat it N times inside the measurement and divide.
  That matters most when comparing BASIC against machine code, where the
  asm side often lands in single digits.
- **`TI` is the wrong clock for anything the frame counts.** The jiffy IRQ
  runs at exactly 60.00 Hz; an NTSC frame is 59.826 Hz. Over 2184 frames
  that is 2190 jiffies — six frames of drift, and it grows without bound.
  Use `TI` to *measure* a span, never to *pace* one that a sid log, a raster
  effect or a screenshot will be compared against. See
  [Pace a BASIC loop to the frame](#pace-a-basic-loop-to-the-frame).

### Pace a BASIC loop to the frame

When something outside your program counts frames — the SID register log
behind `c64 audio capture`, a raster effect, a screenshot at a known moment —
the loop that drives it has to advance exactly one frame per iteration. `TI`
cannot do that (see the bullet above). `WAIT` on the raster can:

```basic
10 rem --- pace a loop to the frame ---
20 d=53265 : mk=128 : n=300
30 print "{clr}pacing";n;"frames..."
40 t=ti
50 for k=1 to n
60 wait d,mk
70 next k
80 t=ti-t
90 w=int(n*60/59.826+.5)
100 if abs(t-w)<=2 then print "paced";t;"jiffies, want";w : end
110 print "slipped";t;"jiffies, want";w
```

Prints `PACED 301 JIFFIES, WANT 301`. `$D011` bit 7 is the raster line's 9th
bit, set only for lines 256–262, so a `WAIT` on it returns once per frame.

**One `WAIT`, never two.** The obvious-looking `wait d,128 : wait d,128,128`
— wait for the bit, then wait for it to clear — does *not* give you a frame
boundary. Those seven raster lines last 0.44 ms and the second `WAIT`'s own
statement setup costs about 3 ms, so it overshoots the window and returns
somewhere in the middle of the frame (measured: raster line 120–190), leaving
under 8 ms of budget. A *single* `WAIT` self-clears, because whatever runs
next always carries the raster past line 262 before the next `WAIT` polls.

**Budget the work per slice, not per tick.** Between two single-`WAIT` syncs
you have about **15 ms**. Overrun it by a hair and the next `WAIT` misses its
window and costs you a whole extra frame — the failure is quantized, so a
slice that is 5% too heavy runs 100% too slow. Split a tick's work across as
many synced slices as it takes to fit; a music player writing ten SID
registers per tick wants five slices of two, not one slice of ten.

What fits in 15 ms, measured on an NTSC machine (500 repetitions timed
against `TI`, empty-loop baseline subtracted):

| Statement | Cost |
|---|---|
| `poke <var>,<var>` | 3.0 ms |
| `poke <var>,<int array>(<var>)` | 5.0 ms |
| `poke <5-digit literal>,<var>` | 7.7 ms |
| `poke <5-digit literal>,<int array>(<var>)` | 9.6 ms |
| empty `for`/`next` iteration | 1.6 ms |

**A literal address costs +4.7 ms** — more than the poke itself. That is why
every address above is in a variable assigned before the loop, and it is the
single cheapest speedup available to a BASIC inner loop: five array-pokes fit
in a frame, but only three of them do if you spell the addresses out.

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

### Poke a letter string to the screen (PETSCII → screen codes)

Digits are the easy case. For *letters* the PETSCII value `ASC` returns
(65–90 for `A`–`Z`) is **not** the screen code (1–26), so poking it
straight through — as the Score HUD recipe above legitimately does for
digits — puts the wrong glyph on screen. Fold the letters down by 64:

```basic
10 rem poke a word
20 a$="hello there": b=1024+40*10+14
30 for i=1 to len(a$)
40 c=asc(mid$(a$,i,1)): if c>63 then c=c-64
50 poke b+i-1,c: next
60 print chr$(19): print "done"
```

Line 40's `if c>63` guard is what makes this general over any string.
Space (32) and punctuation are *already* their own screen codes, so a
bare `c=c-64` would corrupt them — a space would become 32-64 = -32 and
`POKE` would raise `?ILLEGAL QUANTITY ERROR`. The string above contains
a space precisely so a live run proves the guard: at `1024+40*10+14`
($059E) the eleven cells read back as 8, 5, 12, 12, 15, 32, 20, 8, 5,
18, 5 — the space passed through untouched while every letter folded.
Digits (48–57) are below 64 too and likewise pass through, which is
exactly why the Score HUD recipe needs no conversion at all.

Two details worth copying: `PRINT CHR$(19)` on line 60 is HOME, not CLR
— it parks the cursor at the top-left so printing the `done` marker
cannot scroll the poked row away. And this recipe leaves color RAM
alone, so the text inherits whatever color the cells already had; on a
screen you cleared to the background color, poke `55296+` alongside as
the Score HUD recipe does.

This is the BASIC twin of the assembly
[Static text without CHROUT](#static-text-without-chrout-poke-screen-codes)
recipe, where the same fold is `cmp #$40` / `sbc #$40` — one compare,
branch below for "already a screen code", subtract otherwise.

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
`c64 mem read '$D015' 1` (enable bits) and `c64 screen --png`. What a test
may assert about a sprite — registers and state bytes, never PNG pixels —
is under *Verifying a change* in SKILL.md.

### Multicolor sprite from BASIC (ASCII art → DATA)

A multicolor sprite trades half its horizontal resolution for color: each
*pair* of data bits is one double-wide pixel (so the shape is 12×21, drawn
24 pixels wide) and the pair picks the color — `00` transparent, `01` the
shared color at `$D025`, `10` the sprite's **own** color at `$D027`+n, `11`
the shared color at `$D026`. Two of the three are shared by every multicolor
sprite; only `10` is per-sprite.

Don't work out the bit pairs by hand. Draw the shape as 21 rows of 12
characters using the `c64 sprite encode` legend — `' '` transparent, `'.'`
→ `$D025`, `'#'` → the sprite's own color, `'+'` → `$D026` — and let the
tool encode it. A beach ball, `ball.txt` (every row is exactly 12 columns
wide, trailing spaces included — or pass `--background .` and draw the
transparent pixels as dots, so the width is countable and no editor can
strip it):

```
    ++++    
   +..##+   
  +...###+  
  ....####  
 +....####+ 
 #....####. 
+##...###..+
+##...###..+
+###..##...+
+####.#....+
+#####.....+
+####.#....+
+###..##...+
+##...###..+
+##...###..+
 #....####. 
 +....####+ 
  ....####  
  +...###+  
   +..##+   
    ++++    
```

`c64 sprite encode ball.txt --format basic --start-line 1000` emits the 21
numbered `data` lines below, ready to paste. (Without `--start-line` the
rows come out unnumbered and will not store; the keyword is lowercase
because an uppercase `DATA` is shifted PETSCII and tokenizes to junk.)

```basic
100 rem multicolor beach ball, shape from c64 sprite encode
110 print "{clr}"
120 for i=0 to 62 : read a : poke 832+i,a : next : rem block 13 = 832/64
130 poke 2040,13   : rem $07f8: sprite 0 data pointer
140 poke 53276,1   : rem $d01c: sprite 0 multicolor on (bit 0)
150 poke 53285,1   : rem $d025: bit-pair 01 -> white
160 poke 53287,2   : rem $d027: bit-pair 10 -> sprite 0's own color, red
170 poke 53286,0   : rem $d026: bit-pair 11 -> black (the rim)
180 poke 53248,160 : poke 53249,120 : rem $d000/$d001: x,y
190 poke 53269,1   : rem $d015: enable sprite 0
200 print "ball on"
210 goto 210
1000 data 0,255,0
1010 data 3,90,192
1020 data 13,90,176
1030 data 5,90,160
1040 data 53,90,172
1050 data 37,90,164
1060 data 233,90,151
1070 data 233,90,151
1080 data 234,90,87
1090 data 234,153,87
1100 data 234,165,87
1110 data 234,153,87
1120 data 234,90,87
1130 data 233,90,151
1140 data 233,90,151
1150 data 37,90,164
1160 data 53,90,172
1170 data 5,90,160
1180 data 13,90,176
1190 data 3,90,192
1200 data 0,255,0
```

Verify the shape actually landed before believing anything: `c64 sprite show
0` renders the loaded block back as ASCII art (it is the inverse of
`encode`, so it should look like `ball.txt` again, double-wide), and
`c64 sprite png 0 -o check.png` renders it with the live colors. Registers
are the ground truth for the setup: `$D015` = 1, `$D01C` = 1, `$07F8` = 13.
Note that `$D025`/`$D026`/`$D027` are 4-bit registers — they read back with
the high nybble set (`$F1`, not `$01`), so mask with `and $0f` before
comparing.

To *move* it, poke `$D000`/`$D001`; past x=255 set the sprite's bit in
`$D010` as well (`poke 53264,-(x>255)` — a true comparison is -1 in BASIC).
`tests/programs/bouncing-ball/` is this sprite bounced around a bordered
playfield, with the state bytes that make it testable.

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
frame-steps to your loop label; read `c64 mem read pos 1` between holds. The
hold pokes 64 back after the last frame — the re-poke above assumes the
KERNAL scan is alive to clear `$CB`, and a game that owns the interrupt has
none, so without that the key would stay down for ever. Pass `--no-release`
to keep it held.
In a `c64 test run` YAML the same protocol is the `poke:` + `until:` step
pair.

**Read `$CB` at the top of the loop.** `key hold` pokes the matrix code
while the machine sits at the anchor, and the IRQ keyboard scan puts 64
back within a jiffy. If the read is the first thing after the anchor label
it always wins; if it happens after a pacing delay, the poke is long gone
and steering silently does nothing. (Sampling `$CB` again *during* the
pacing loop is fine and makes a human-held key just as responsive — ignore
64 there rather than latching it.)

**With a play-loop anchor, the move that ends the game cannot be driven by
`key hold`.** When the anchor label executes only while playing, the fatal
move leaves it for good: the hold's wait times out and (per its documented
timeout behavior) leaves the machine running with the checkpoint pulled —
past the crash you wanted to inspect. Two shapes avoid that:

**Prefer a shared tick.** Anchor on a label that runs every frame in every
state — title, play, game over. Then `key hold d --at mainloop --frames 1`
drives the fatal move too and comes back stopped with the game-over screen
already drawn: every state is drivable from one anchor and one `until`.
(Snake's `mainloop` is this shape.)

**With a play-loop anchor, break on the death path** and supply that one
key yourself:

```bash
c64 break add died         # the label the collision check jumps to
c64 mem write '$CB' 9      # W's matrix code, by hand (space 60, A 10, D 18)
c64 wait --break           # resumes, stops the instant the snake dies
c64 mem read nrow 2        # the cell that killed it
```

The full matrix-code table is `MATRIX_CODES` in `src/c64lib/ops.py`; the
common ones are in the hardware reference.

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

Three caveats, all about `until` firing at the wrong time or not at all:

- **`c64 until` can only fire while the program still visits the label.**
  If play can branch away (death, menu, pause), the wait times out — and on
  timeout the machine is left RUNNING with the checkpoint removed. For those
  states, break at a code path that must still execute instead.
- **On a running machine, `until` is a race, not a rewind.** It sets its
  checkpoint when it runs, so `c64 key type " "` (dismiss the title) followed
  by `c64 until mainloop` does not stop at move 1 — at warp the wall-clock
  gap between the two commands is emulated seconds and the game has already
  played on. Nothing errors; you just get an arbitrary later frame. When the
  frame you want is the *first* one after a trigger, set a breakpoint
  **before** the trigger — a checkpoint halts the machine on arrival with no
  gap to race:

  ```bash
  c64 break add mainloop     # BEFORE the key that starts play
  c64 key type " "           # runs, hits mainloop, stops there by itself
  c64 mem read FRAMES 1      # frame 1, deterministically
  ```
- **`--count N` is a frame count only because this loop is frame-paced.**
  The pace loop waits on the jiffy clock, so `mainloop` runs at a fixed
  rate (this one paces 6 jiffies per pass). A main loop that free-runs
  — draining a work queue, spinning on a flag — arrives at its label as
  fast as it loops, and `--count 600` returns in emulated microseconds
  having measured nothing. Anchor on something executed exactly once per
  frame; if the main loop spins, anchor on the IRQ handler instead.

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
scratch area: 21, 178, 89). It then **proves** the property rather than
claiming it: 1024 draws are tallied into a 256-byte page and the number of
distinct values printed. A maximal 8-bit LFSR visits 255 of the 256; a dead
one visits 1, which is the whole point of the two failure modes below.

```asm
; random.s — pseudo-random bytes from an 8-bit maximal Galois LFSR.
; Call `random`: a fresh pseudo-random byte comes back in A (and `seed`).

CHROUT  = $FFD2
LINPRT  = $BDCD                 ; print A/X as an unsigned 16-bit decimal
TALLY   = $C000                 ; 256 bytes BASIC never touches

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

        lda     #0              ; clear the tally page
        tax
clr:    sta     TALLY,x
        inx
        bne     clr

        lda     #4              ; 4 x 256 = 1024 draws
        sta     rounds
outer:  ldy     #0
inner:  jsr     random
        tax                     ; the draw IS the tally index
        inc     TALLY,x
        iny
        bne     inner
        dec     rounds
        bne     outer

        ldx     #0              ; how many of the 256 came up at all?
        ldy     #0
cnt:    lda     TALLY,x
        beq     skip
        iny
skip:   inx
        bne     cnt
        sty     distinct

        ldx     #0
msgl:   lda     msg,x
        beq     msgd
        jsr     CHROUT
        inx
        bne     msgl
msgd:   lda     #0              ; LINPRT wants the high byte in A, low in X
        ldx     distinct
        jsr     LINPRT
        lda     #$0d
        jsr     CHROUT
        rts                     ; back to BASIC (READY.)

random: lda     seed
        lsr                     ; shift right; old bit 0 -> carry
        bcc     nofb
        eor     #$b8            ; feedback taps -> maximal 255-byte cycle
nofb:   sta     seed
        rts

msg:    .byte   "DISTINCT ", $00
seed:   .byte   1
rounds: .byte   0
distinct: .byte 0
```

**Two ways this stops being random, both silent.**

**A state of zero is absorbing** — every shift of zero is zero — so a
generator seeded by the same loop that clears your variables returns a
constant from the first frame. Seed it with a non-zero literal at startup,
*after* the clear, and never from `BSS`.

**An LFSR you also write from outside is not an LFSR.** Stirring entropy into
the state every frame overwrites what the last shift produced; if the
stirred-in value is constant — a keyboard byte reading "no key", say — the
output collapses to a constant too. Stir *only* when there is real entropy,
on the frame a key actually arrives, and let the register own its state the
rest of the time.

Neither failure looks like a failure. The program runs, the values are
plausible, nothing on screen is wrong: the Ms. Muncher dogfood shipped both
at once and spent two full audit iterations believing its ghosts opened
differently every game when every board was identical. Test it the way you
would test any other claim — count distinct values as above, or run the same
scenario twice with different input timing and diff the result.

Range tricks, applied after `jsr random`: `and #$1f` masks to 0-31
(powers of two only). Reject-and-retry — `retry: jsr random / cmp #40 /
bcs retry` — returns **1-39, not 0-39**: the LFSR's state is never zero
(zero is the fixed point the seeding guards against) and `random` returns
the state, so 0 is unreachable — a game picking a column with it never
uses column 0. For small bounds it is also positionally biased and slow:
consecutive outputs of a right-shifting LFSR differ by one shift, so they
are not independent draws — rejecting until one falls under a small bound
almost always stops on the same freshly-shifted bit pattern (in the 1812
demo, two of eight dither patterns never appeared across an 889-shape
run) — and it costs 255/(bound-1) draws on average (only bound-1 of the
255 states accept, since 0 never lands): ~128 for a bound of 3, half
again worse than the naive 256/bound estimate suggests. Prefer
**scaling**: `v = (rnd * bound) >> 8` — one draw, reading the freshly
shifted-in high bits, uniform to within one part in floor(256/bound).
The product's high byte IS the value; the multiply is the quarter-squares
recipe below — its **unsigned** `umul` half, no sign fixup — and
`demos/1812/spawn.s`'s `rndlt` is the worked version: past loading the
operands, the scaling step proper is just `jsr umul / lda MULR+1`. Branch
back to the `jsr`, never into `random` itself: entering the routine
without a `jsr` means its `rts` pops *your* caller's return address and
control unwinds one level too far.

### Signed multiply: quarter squares, tables built at startup

Geometry, physics, scaling — anything beyond shifts needs a signed
8×8→16 multiply, and the 6502 has none. The classic shift-add loop costs
~330 cycles; quarter squares does it in ~141 (both measured with
`c64 profile` in the 1812 demo, which calls this four times per vertex):
`a*b = f(a+b) - f(a-b)` where `f(x) = floor(x*x/4)` — exactly, for
integers — so a multiply becomes two table lookups and a 16-bit subtract.

The 512-entry tables are **generated at startup, into RAM the program
never ships**: `f` is accumulated from its own first difference
(`f(x+1) - f(x) = floor((x+1)/2)`, which steps up on every odd index), so
the generator needs no multiply either, and building into `$C000-$C3FF` —
the 4 KB BASIC never touches — costs the `.prg` nothing. Accumulating `f`
directly keeps everything in 16 bits (`x*x` would overflow at `x = 256`;
`f(511) = 65280` does not).

```asm
; qsmul.s — signed 8x8 -> 16 multiply by quarter squares.
; Builds f(x) = floor(x*x/4) for x = 0..511 at startup, then computes
; 12 * 12 = 144 and -3 * 100 = -300 into $03F0-$03F3 as proof.
QSL = $C000             ; 512 low bytes of f
QSH = $C200             ; 512 high bytes of f

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  jsr     qsgen           ; build the tables once
        lda     #12
        sta     MULA
        sta     MULB
        jsr     smul            ; 12 * 12
        lda     MULR
        sta     $03f0           ; 144
        lda     MULR+1
        sta     $03f1           ; 0
        lda     #<-3
        sta     MULA
        lda     #100
        sta     MULB
        jsr     smul            ; -3 * 100 = -300 = $FED4
        lda     MULR
        sta     $03f2           ; $D4
        lda     MULR+1
        sta     $03f3           ; $FE — stored last: the done marker
        rts

; umul — UNSIGNED 8x8 -> 16.  in: MULA, MULB.  out: MULR/MULR+1.
; a+b reaches 510 for two full-range bytes, so the tables carry 512
; entries and the sum's carry selects the upper half; |a-b| never
; exceeds 255, so the subtrahend always comes from the lower half.
umul:   lda     MULA
        clc
        adc     MULB
        tax
        bcc     umlo
        lda     QSL+256,x
        sta     MULR
        lda     QSH+256,x
        sta     MULR+1
        jmp     umd
umlo:   lda     QSL,x
        sta     MULR
        lda     QSH,x
        sta     MULR+1
umd:    lda     MULA            ; minus f(|a - b|); f is even
        sec
        sbc     MULB
        bcs     :+
        eor     #$ff
        clc
        adc     #1
:       tax
        lda     MULR
        sec
        sbc     QSL,x
        sta     MULR
        lda     MULR+1
        sbc     QSH,x
        sta     MULR+1
        rts

; smul — SIGNED, by magnitudes through umul plus one sign fixup.
smul:   lda     MULA
        bpl     smpa
        eor     #$ff
        clc
        adc     #1
        ldx     #1
        stx     smsgn
        jmp     sma2
smpa:   ldx     #0
        stx     smsgn
sma2:   sta     MULA
        lda     MULB
        bpl     smpb
        eor     #$ff
        clc
        adc     #1
        sta     MULB
        lda     smsgn
        eor     #1
        sta     smsgn
        jmp     smgo
smpb:   sta     MULB
smgo:   jsr     umul
        lda     smsgn
        beq     smdone
        lda     #0              ; negate the 16-bit product
        sec
        sbc     MULR
        sta     MULR
        lda     #0
        sbc     MULR+1
        sta     MULR+1
smdone: rts

; qsgen — build both 512-entry tables by first difference: no multiply.
qsgen:  lda     #0
        sta     flo
        sta     fhi
        sta     dlt
        sta     qspg
        lda     #<QSL
        sta     qs1+1
        lda     #>QSL
        sta     qs1+2
        lda     #<QSH
        sta     qs2+1
        lda     #>QSH
        sta     qs2+2
        ldx     #0
qsl:    lda     flo
qs1:    sta     $ffff,x         ; self-modified: QSL, then QSL+256
        lda     fhi
qs2:    sta     $ffff,x         ; self-modified: QSH, then QSH+256
        txa                     ; index parity == X parity (256 is even)
        and     #1
        beq     qsev
        inc     dlt
qsev:   lda     flo
        clc
        adc     dlt
        sta     flo
        bcc     :+
        inc     fhi
:       inx
        bne     qsl
        inc     qs1+2
        inc     qs2+2
        inc     qspg
        lda     qspg
        cmp     #2
        bne     qsl
        rts

        .segment "BSS"
MULA:   .res 1
MULB:   .res 1
MULR:   .res 2
smsgn:  .res 1
flo:    .res 1
fhi:    .res 1
dlt:    .res 1
qspg:   .res 1
```

The full signed range works, `-128 * -128` included: magnitudes reach 128,
so `a+b` peaks at 256 and the carry path indexes the upper table half.
`smul` leaves `MULA`/`MULB` holding their magnitudes — reload them per
call. The worked production version (zero-page operands, `c64 profile`
numbers in the comments) is `demos/1812/raster.s`.

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

### Time a routine and print the jiffies (LINPRT)

The recipe above is a byte-to-three-digits converter; for anything wider,
don't write one. The BASIC ROM's **LINPRT (`$BDCD`) prints the unsigned
16-bit value in A (high) / X (low)** as decimal, which covers 0-65535 in
three instructions. Here it reports how long a routine took, measured off
the jiffy clock at `$A0-$A2`:

```asm
; jtime.s — time a routine with the jiffy clock, print the count with LINPRT.
REPS   = 4                      ; measure several runs: see the note below

CHROUT = $FFD2
LINPRT = $BDCD                  ; print A(hi)/X(lo) as unsigned decimal

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #$93
        jsr     CHROUT
        lda     #0              ; restart the clock: $A0-$A2, MSB first
        sta     $A0
        sta     $A1
        sta     $A2

        ldx     #REPS           ; work must leave X alone (or save it here)
tloop:  jsr     work
        dex
        bne     tloop

        lda     $A2             ; snapshot before printing, so the print
        sta     tlo             ; itself is outside the measurement
        lda     $A1
        sta     thi

        lda     thi             ; A = high byte, X = low byte
        ldx     tlo
        jsr     LINPRT
        ldx     #0
p1:     lda     msg,x
        beq     done
        jsr     CHROUT
        inx
        bne     p1
done:   rts

; the routine under test — here, 65536 increments (about half a second)
work:   lda     #0
        sta     ctr
        sta     ctr+1
w1:     inc     ctr
        bne     w1
        inc     ctr+1
        bne     w1
        rts

ctr:    .word   0
tlo:    .byte   0
thi:    .byte   0
msg:    .byte   " JIFFIES FOR 4 RUNS", $0D, $00
```

Prints `150 JIFFIES FOR 4 RUNS`. Three things this encodes:

- **LINPRT emits no padding** — no leading space, no leading zeros. BASIC's
  `PRINT` *does* prefix positive numbers with a space, so a message ported
  from BASIC comes out as `LARGEST997` until you put the space in the
  string yourself (note the leading space in `msg`).
- **Snapshot the clock into your own bytes before printing.** `$A0-$A2`
  keeps ticking through CHROUT, so reading it twice during the report
  yields two different times.
- **`REPS` exists because one jiffy is the resolution.** A routine that
  takes 9 jiffies is 9±1 — repeat it and divide, or the speedup you report
  is mostly noise. (The three-byte clock is read MSB-first: `$A0` is the
  high byte. Anything under ~18 minutes fits in `$A1`/`$A2` alone.)

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
block 13 = $0340); real programs put it in a dedicated, commented `.byte`
block at a fixed address (say `$2000`, pointer `$80`) — see the
sprite-authoring section of SKILL.md. The demo
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

### Sprite multiplexer: more objects than sprites

Eight hardware sprites is the ceiling *per scanline*, not per screen. Reuse
a register down the screen and a shooter flies twenty objects: sort the
objects by Y once a frame, hand each one the first register that has come
free by the time the beam reaches it, and reprogram that register from a
raster interrupt a few lines above the object. Three parts, in this order:

- **Sort by Y.** Insertion sort over an *index* array (`sortix`) with the
  keys copied alongside it (`sortkey`), never over the object records
  themselves. Quadratic in the worst case and linear in practice, because a
  real game hands it last frame's order and nothing moved more than a few
  pixels — an entry already above its predecessor costs one compare and no
  copy at all. Stop on equal keys as well as smaller ones, or a band of
  objects sharing one Y goes quadratic on ties alone.
- **Assign greedily.** Keep one "free at line" byte per register, walk the
  sorted list, and take the first register whose free-line the beam has
  reached. Because the list ascends in Y, greedy is *optimal* here — a
  register passed over could not have served this object either — so there
  is no search and no backtracking. Reserve it for `MUXGAP` lines: the 21
  lines of the sprite plus at least one more for the reprogramming to land
  in. Saturate that addition rather than let it wrap, or an object near the
  bottom of the screen frees its register at line 4.
- **Publish counters.** `DISPLAYED` is what the frame put on screen,
  `OVERFLOW` is what no register could hold. Both are plain memory, and that
  is the point: a screenshot shows the result, never the budget. A
  multiplexer quietly dropping a third of its objects still makes a
  perfectly good PNG — it fails `assert mem OVERFLOW equals 0`.

The demo runs the build once over a fixed list of 18 objects, ten of them
crowded into 18 scanlines (more than eight registers can cover), and leaves
the first object on each register on screen with the counters and the
reposition schedule in memory:

```asm
; mux.s — 18 objects on 8 sprite registers: sort by Y, assign, count.
NOBJ    = 18
MUXREGS = 8                     ; hardware sprites 0-7
MUXGAP  = 22                    ; 21 sprite lines, plus one to reprogram in
MAXEV   = 24                    ; cap on the reposition schedule
SPR0X   = $D000                 ; register r's X/Y pair is SPR0X + r*2
SPRENA  = $D015
SPRCOL0 = $D027
SPRPTR  = $07F8
SHAPE   = $0340                 ; block 13 (832 = 13*64): tape buffer, unused

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  ldx     #62             ; one solid 24x21 shape, shared by every object
shp:    lda     #$FF
        sta     SHAPE,x
        dex
        bpl     shp
        lda     #0
        sta     DONE
        ldx     #NOBJ-1         ; gather: the index list in slot order and the
gath:   txa                     ; sort keys beside it
        sta     sortix,x
        lda     objy,x
        sta     sortkey,x
        dex
        bpl     gath
        jsr     muxsort
        jsr     muxassign
        lda     #$2a
        sta     DONE            ; marker: the counters below are final
        rts                     ; the eight registers stay on screen

; --- sort: insertion, over a list that is already nearly in order ----------
muxsort:
        ldx     #1
ms1:    lda     sortkey,x
        cmp     sortkey-1,x
        bcs     ms4             ; above its predecessor: nothing to do at all
        sta     tmpk            ; the key being placed...
        lda     sortix,x
        sta     tmpi            ; ...and the object it belongs to
        txa
        tay                     ; Y = the hole
ms2:    dey
        bmi     ms3
        lda     sortkey,y
        cmp     tmpk
        bcc     ms3             ; predecessor is smaller: the hole is here
        beq     ms3             ; equal: ties stay put, so a band sharing one Y
        sta     sortkey+1,y     ;   does not go quadratic
        lda     sortix,y
        sta     sortix+1,y
        jmp     ms2
ms3:    iny
        lda     tmpk
        sta     sortkey,y
        lda     tmpi
        sta     sortix,y
ms4:    inx
        cpx     #NOBJ
        bne     ms1
        rts

; --- assign: the first register free by this object's line -----------------
muxassign:
        ldx     #MUXREGS-1
        lda     #0
ma0:    sta     regfree,x       ; "free at line": 0 = free from the top
        sta     regused,x
        dex
        bpl     ma0
        sta     DISPLAYED
        sta     OVERFLOW
        sta     EVCOUNT
        sta     k
ma1:    ldy     k
        cpy     #NOBJ
        bcc     ma1a
        jmp     ma8
ma1a:   lda     sortkey,y
        sta     ytop            ; this object's Y...
        ldx     sortix,y        ; ...and the object itself, in X from here on
        ldy     #0
ma2:    lda     regfree,y
        cmp     ytop
        beq     ma3
        bcc     ma3             ; free at or above this line: take it
        iny
        cpy     #MUXREGS
        bne     ma2
        inc     OVERFLOW        ; nothing comes free in time — drop the object
        jmp     ma7
ma3:    lda     ytop
        clc
        adc     #MUXGAP
        bcc     ma4
        lda     #$FF            ; saturate: an object near the bottom holds its
ma4:    sta     regfree,y       ;   register to the end of the frame
        tya
        asl     a
        sta     mreg,x          ; register * 2, ready for SPR0X,y
        lda     regused,y
        bne     ma5
        lda     #1              ; first object on this register: program it now,
        sta     regused,y       ;   at the top of the frame
        jsr     program
        jmp     ma6
ma5:    jsr     emit            ; a later one: it needs a reposition interrupt
ma6:    inc     DISPLAYED
ma7:    inc     k
        jmp     ma1
ma8:    ldy     #MUXREGS-1      ; the enable mask falls out of which registers
        lda     #0              ;   were used at all
        sta     tmpk
mm1:    lda     regused,y
        beq     mm2
        lda     regbit,y
        ora     tmpk
        sta     tmpk
mm2:    dey
        bpl     mm1
        lda     tmpk
        sta     SPRENA
        rts

; --- program: X = object, mreg,x = its register * 2 ------------------------
program:
        txa                     ; this demo's X: 24 + object*8, all under 256
        asl     a
        asl     a
        asl     a
        clc
        adc     #24
        ldy     mreg,x
        sta     SPR0X,y
        lda     objy,x
        sta     SPR0X+1,y
        tya
        lsr     a
        tay                     ; Y = the register number again
        lda     #13
        sta     SPRPTR,y        ; every object shares the one shape here
        txa
        and     #7
        ora     #8
        sta     SPRCOL0,y
        rts

; --- emit: X = object, ytop = its Y — append a reposition event ------------
emit:   ldy     EVCOUNT
        cpy     #MAXEV
        bcs     em9
        lda     ytop
        sec
        sbc     #3              ; reprogram three lines early...
        bcc     emtop
        cmp     #51
        bcs     emok
emtop:  lda     #51             ; ...but never above the first visible line
emok:   sta     evline,y
        txa
        sta     evobj,y
        inc     EVCOUNT
em9:    rts

regbit: .byte   $01, $02, $04, $08, $10, $20, $40, $80
objy:   .byte   140, 60, 240, 66, 100, 74, 180, 62, 220
        .byte   70, 120, 78, 160, 64, 200, 72, 76, 68

        .segment "BSS"
DISPLAYED: .res 1               ; objects the frame actually put on screen
OVERFLOW:  .res 1               ; objects no register could hold
EVCOUNT:   .res 1
DONE:      .res 1
sortix:    .res NOBJ
sortkey:   .res NOBJ
mreg:      .res NOBJ
regfree:   .res MUXREGS
regused:   .res MUXREGS
evline:    .res MAXEV
evobj:     .res MAXEV
k:         .res 1
ytop:      .res 1
tmpk:      .res 1
tmpi:      .res 1
```

`DISPLAYED` = 16, `OVERFLOW` = 2: the pile at the top fills all eight
registers and the last two objects in it are dropped, while the eight
objects spread down the rest of the screen reuse registers 0 and 1 between
them. That leaves `EVCOUNT` = 8 reposition events at `evline` = 97, 117 …
237, each three lines above its object; playing them out down the screen is
the [raster event chain](#raster-event-chain-one-sorted-interrupt-list-per-frame)'s
job. Build at the *top* of the tick, before any game logic — a schedule
built at the end of the tick is rewritten under the beam that is already
playing it.

Two things a real game does differently. It keeps the object list from frame
to frame instead of rebuilding it in slot order, which is what makes the
sort nearly free (rebuilding hands it a fresh permutation every frame — 4,875
cycles for eighteen objects in the demo this recipe came from). And it starts
the register search at a round-robin cursor rather than at register 0,
because with the list ascending the register that comes free soonest is
always the one used longest ago, so the search hits on the first try. Both
are in `demos/la-galaxia/mux.s`, which multiplexes six registers under two
reserved for the player. X above 255 needs the MSB bit in `$D010` (see
hardware.md), and the key is the sprite's Y register, not a screen row.

### Raster event chain: one sorted interrupt list per frame

Once more than one thing has to happen at a known scanline — a multiplexer's
repositions, a split-screen mode change, a scroll register that goes on for
the playfield and off for the HUD — stop writing one raster handler per
effect and build a list. Three parallel arrays, sorted by line, one entry per
event: `evline` (the scanline), `evkind` (what to do), `evarg` (who to do it
to). The handler dispatches on `evkind`, advances the cursor, arms the next
`$D012` and returns. `EV_FRAME` at line 0 is the frame marker: it hands the
tick to the main loop, so the main loop is paced by the chain instead of by
the jiffy clock. `EV_END` parks the cursor back on the marker.

Two things about that are not obvious, and both cost real debugging time:

**Compare the line you just armed against the live raster, and loop instead
of returning.** Events one or two lines apart are ordinary — two sprites a
pixel apart in Y produce exactly that — and by the time the handler has
finished the first the beam is already past the second. Arming `$D012` and
returning then means the compare does not match again until the *next*
frame: the event is a whole frame late and so is everything after it in the
list. After arming, subtract the slack you need and compare against `$D012`
read back — the same register returns the *current* raster line — and if the
beam is already there, jump back into the dispatcher and run the event now.

**Acknowledge `$D019` again on the way out.** The compare register is written
*before* that check, so when the check dispatches inline the beam crosses the
just-armed line while the handler is still running and re-sets the latch —
for an event this handler has by then already run. Left set, the `RTI`
re-enters immediately, and with the cursor parked at 0 by `EV_END` that means
`EV_FRAME` fires mid-frame: the tick runs twice, the chain replays from the
top, and the main loop gets two frames of logic inside one frame. Deleting
just the second `sta $D019` from the program below takes `MIDFRAME` from 0 to
90 and `LASTLOOP` from 1 to 10 over the same 180 ticks.

```asm
; rasterchain.s — one sorted (line, kind, arg) event list, replayed per frame.
CINV     = $0314
EV_FRAME = 0                    ; hand the tick to the main loop
EV_BACK  = 1                    ; arg -> $D021
EV_BORDER= 2                    ; arg -> $D020
EV_END   = 3                    ; wrap to the frame marker

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     #0
        sta     FRAMES
        sta     DONE
        sta     MIDFRAME
        sta     OVERRUN
        sta     RELATCH
        sta     tickpend
        jsr     irqon
mainloop:
        lda     tickpend        ; the frame marker handed us the tick
        beq     mainloop
        lda     #0
        sta     tickpend
        inc     FRAMES          ; ...one frame of game logic would go here
        lda     FRAMES
        cmp     #180            ; three seconds of chain, then stop
        bne     mainloop
        jsr     irqoff
        lda     #$2a
        sta     DONE
        rts

irqon:  sei
        lda     #$7F
        sta     $DC0D           ; CIA1 timer IRQ off: no keyboard jitter, and
        lda     $DC0D           ;   ack whatever it had pending
        lda     CINV
        sta     oldvec
        lda     CINV+1
        sta     oldvec+1
        lda     #<irq
        sta     CINV
        lda     #>irq
        sta     CINV+1
        lda     $D011
        and     #$7F            ; every event line is below 256
        sta     $D011
        lda     #0
        sta     evidx
        lda     evline          ; arm the frame marker
        sta     $D012
        lda     #$01
        sta     $D01A           ; raster source on...
        sta     $D019           ; ...with no stale latch
        cli
        rts

irqoff: sei
        lda     #0
        sta     $D01A
        lda     #$01
        sta     $D019
        lda     oldvec
        sta     CINV
        lda     oldvec+1
        sta     CINV+1
        lda     #$81
        sta     $DC0D           ; jiffy clock and keyboard scan back on
        lda     #6
        sta     $D021           ; the screen as BASIC left it
        lda     #14
        sta     $D020
        cli
        rts

; --- the chain -------------------------------------------------------------
; Entry is through the KERNAL's $0314 vector, so A/X/Y are already on the
; stack; $EA81 pulls them and RTIs without running any KERNAL work.
irq:    lda     #$01
        sta     $D019           ; ack the latch that got us here
        ldx     evidx
irqdisp:
        lda     evkind,x
        beq     irqframe        ; EV_FRAME
        cmp     #EV_BACK
        beq     irqback
        cmp     #EV_BORDER
        beq     irqborder
irqend: lda     seen            ; EV_END: publish what this frame played...
        sta     LASTSEEN
        lda     loops
        sta     LASTLOOP
        lda     #0              ; ...and park on the marker's line
        sta     evidx
        sta     $D012
        jmp     irqexit

irqframe:
        lda     $D012           ; the marker is armed at line 0, so a frame
        cmp     #60             ;   tick from down the screen is a phantom
        bcc     irqf1
        inc     MIDFRAME
irqf1:  lda     tickpend        ; still pending? the main loop missed a frame
        beq     irqf2
        inc     OVERRUN
irqf2:  lda     #1
        sta     tickpend
        lda     #0
        sta     seen
        sta     loops
        jmp     irqadv

irqback:
        lda     evarg,x
        sta     $D021
        inc     seen
        jmp     irqadv

irqborder:
        lda     evarg,x
        sta     $D020
        inc     seen
        ; fall through

irqadv: inx
        stx     evidx
        lda     evkind,x
        cmp     #EV_END
        beq     irqend
        lda     evline,x
        sta     $D012           ; arm the next event...
        sec
        sbc     #2
        cmp     $D012           ; ...and compare it with the LIVE raster line
        bcs     irqexit         ; two clear lines in hand: return and wait
        inc     loops
        jmp     irqdisp         ; the beam is already there — run it now

irqexit:
        ; Ack AGAIN on the way out. The compare register was written before
        ; the guard above, so when the guard dispatches inline the beam has
        ; crossed that line meanwhile and re-set the latch — for an event
        ; this handler has already run. Left set, the RTI re-enters at once
        ; with evidx parked at 0: EV_FRAME fires mid-frame, the tick runs
        ; twice, and the chain replays from the top. The final $D012 write is
        ; always >= 2 lines ahead, so nothing legitimate can latch in between.
        lda     $D019
        and     #$01
        beq     irqx1
        inc     RELATCH         ; it happened — this is the ack that matters
irqx1:  lda     #$01
        sta     $D019
        jmp     $EA81           ; pull A/X/Y and RTI

; --- the list: ascending in line, EV_END last ------------------------------
; The frame's two restores land one line apart, and that pair is the case the
; guard in irqadv exists for: a multiplexer gets one every time two objects
; sit within a line of each other in Y.
evline: .byte     0,  50,  60,  84, 108, 132, 156, 180, 204, 228, 229, $FF
evkind: .byte     0,   2,   1,   1,   1,   1,   1,   1,   1,   1,   2,   3
evarg:  .byte     0,   0,   6,  14,   3,  13,   7,   8,   2,   6,  14,   0

        .segment "BSS"
FRAMES:      .res 1
DONE:        .res 1
MIDFRAME:    .res 1             ; frame markers that fired away from line 0
OVERRUN:     .res 1             ; ticks the main loop had not consumed
LASTSEEN:    .res 1             ; events the last whole frame dispatched
LASTLOOP:    .res 1             ; ...of which, ones the guard ran inline
RELATCH:     .res 1             ; exits that found the latch re-set (running)
evidx:       .res 1
tickpend:    .res 1
seen:        .res 1
loops:       .res 1
oldvec:      .res 2
```

The counters are the whole test surface. `LASTSEEN` = 10 events dispatched
in the last complete frame — the chain played the entire list. `LASTLOOP` =
1 of them run inline by the guard: the 228/229 pair. `MIDFRAME` = 0 frame
markers fired anywhere but the top of the screen, and `OVERRUN` = 0 ticks
the main loop failed to consume before the next one arrived — a real game's
"am I still inside my frame budget?" pair. `RELATCH` reaches 179 over 180
frames: that is the re-latch warning above happening on the machine rather
than in a comment, once a frame, acknowledged.

While the chain owns the IRQ the jiffy clock and the keyboard scan are dead
— `$DC0D` bit 7 is clear and the exit at `$EA81` runs no KERNAL code — so
`TI` and `GETIN` come back only when `irqoff` restores them. To keep the
clock alive instead, exit the *frame marker* through `$EA31` and every other
event through `$EA81`; the price is the keyboard scan's ~15 lines of jitter
on whatever event follows it. Feed this the schedule from the
[sprite multiplexer](#sprite-multiplexer-more-objects-than-sprites) and one
more event kind — `EV_MUX`, `evarg` = the object to reprogram — is all it
takes.

### Custom character set: copy the ROM charset to RAM and redefine glyphs

Giving a game its own bricks, snake segments or spaceships means pointing
the VIC-II at a charset in RAM. The character ROM is not in the CPU's
address space by default — it hides *behind* the I/O registers at `$D000`,
so the copy has to bank I/O out (`$01` bit 2 = 0) with interrupts off, then
put it back. Copy all 2 KB, patch only the glyphs you want, and the other
254 stay exactly as the ROM drew them:

```asm
; charset.s — ROM charset -> RAM at $3000, then redefine screen codes 96/97.
CHARSET = $3000                 ; must be in the VIC's bank ($0000-$3FFF)
SCREEN  = $0400
COLOR   = $D800
CHROUT  = $FFD2
SRC     = $FB                   ; two user pointers (see zero-page.md)
DST     = $FD

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
        ldx     #0
banner: lda     msg,x
        beq     copy
        jsr     CHROUT
        inx
        bne     banner

copy:   sei                     ; the char ROM replaces I/O at $D000, so the
        lda     $01             ; IRQ must not run while it is banked in
        pha
        and     #$FB            ; CHAREN ($01 bit 2) = 0 -> char ROM visible
        sta     $01
        lda     #$00
        sta     SRC
        sta     DST
        lda     #$D0
        sta     SRC+1           ; from $D000
        lda     #>CHARSET
        sta     DST+1           ; to $3000
        ldx     #8              ; 8 pages = 2048 bytes = 256 glyphs
cpage:  ldy     #0
cbyte:  lda     (SRC),y
        sta     (DST),y
        iny
        bne     cbyte
        inc     SRC+1
        inc     DST+1
        dex
        bne     cpage
        pla
        sta     $01             ; I/O back at $D000
        cli

        ldx     #15             ; two glyphs, 8 bytes each, at codes 96-97
patch:  lda     shapes,x
        sta     CHARSET + 96*8,x
        dex
        bpl     patch

        lda     #$1C            ; screen $0400 + charset $3000 (math below)
        sta     $D018

        lda     #96             ; show them on row 5
        sta     SCREEN + 5*40
        lda     #97
        sta     SCREEN + 5*40 + 1
        lda     #1
        sta     COLOR + 5*40
        sta     COLOR + 5*40 + 1
        rts                     ; back to BASIC, custom charset still live

msg:    .byte   "CHARSET IN RAM", $0D, $00

; the binary literals read as pictures in the source
shapes: .byte   %00111100       ; 96: a face
        .byte   %01111110
        .byte   %11011011
        .byte   %11111111
        .byte   %11111111
        .byte   %10111101
        .byte   %01111110
        .byte   %00111100
        .byte   %00011000       ; 97: a heart
        .byte   %00111100
        .byte   %01111110
        .byte   %11111111
        .byte   %11111111
        .byte   %01111110
        .byte   %00111100
        .byte   %00011000
```

**The `$D018` arithmetic.** Bits 7-4 are the screen base in 1 KB steps,
bits 3-1 the character base in 2 KB steps, bit 0 is unused. Screen `$0400`
= 1 → `$10`; charset `$3000` = `$3000/$0800` = 6, shifted left one → `$0C`;
together `$1C`. **It does not read back as `$1C`**: the unused bit 0 reads
as 1, so `c64 mem read '$D018'` returns `$1D` — the same readback trap the
4-bit color registers have. Compare against `$1D`, or mask with `and $FE`.

Five more things this encodes:

- **Where the charset can live.** The VIC-II sees only one 16 KB bank at a
  time, bank 0 (`$0000-$3FFF`) at power-on — a charset outside it is
  invisible no matter what `$D018` says. `$3000` is the usual home: inside
  the bank, above a `.prg` of a few KB. Check `load_addr + len - 2` still
  lands below it every time the code grows (see the 6502-assembly skill).
- **Leave the screen at `$0400`.** The `$D018` high nybble can move it, but
  the toolset's screen reader assumes `$0400`.
- **Hand the ROM charset back before returning to BASIC** if the program
  quits for real — `lda #$15 / sta $D018` — or `READY.` and everything the
  user types afterwards is drawn in your glyphs. This demo deliberately
  leaves it installed so the effect is visible.
- **`c64 screen` text does not follow your charset.** It decodes screen
  *codes* through their ROM meanings, so a redefined glyph reads back as
  whatever the ROM drew there — and screen codes 32, 96 and 224 decode to a
  **blank**, so a glyph parked on 96 is invisible in decoded text while
  sitting plainly in the PNG. Assert with `c64 screen --codes` or
  `c64 mem read`, look with `c64 screen --png`, and prefer codes whose ROM
  glyph is distinctive for anything you want to eyeball as text.
- **Stay out of 128-154.** Screen codes 128+ are the reverse-video set —
  129-154 is reverse A-Z — so glyphs parked there turn reverse-video
  headings into game objects. This recipe's 96/97 are safe from this trap
  (96's blank-decode, above, still applies); a game needing a contiguous
  run has one at 112-123 (Snake's choice, after learning this at 128-139).
  Reverse text is also invisible to `wait --text` — `c64 screen` decodes
  reverse space as a block — so assert reverse-video headings by screen
  code, not text.

#### The bank-0 budget

"Check `load_addr + len - 2` lands below `$3000`" is the one-consumer
version. A real game has three consumers of the same 16 KB, and the
arithmetic shapes the whole program layout before a line is written:

| Consumer | Cost |
|---|---|
| VIC bank 0, total | `$0000`-`$3FFF` |
| Screen RAM (fixed — the toolset assumes `$0400`) | `$0400`-`$07FF` |
| A `.prg` starts at | `$0801` |
| **Left for program + charset + sprite blocks** | **14,335 bytes** |
| A RAM charset | 2,048 bytes, on a 2 KB boundary — only `$2000`, `$2800`, `$3000` or `$3800` are usable (`$1000`/`$1800` are the char-ROM shadow) |
| Each sprite shape | 64 bytes, on a 64-byte boundary |

A charset and a couple of dozen sprite shapes is ~3.7 KB before your code
exists, and it all has to be *below* whatever else you place. Three ways
out, in order of preference:

1. **Relocate data the VIC never reads.** Sprite *source* art, charset
   source glyphs and level tables are read by the CPU only — they have no
   reason to be in the bank at all. Link them last, between two labels, and
   copy them above `$4000` (`$C000`-`$CFFF` is the 4 KB BASIC never touches)
   in the first instructions of `start:`. `demos/ms-muncher` moved 2,545
   bytes this way and its low program ended at `$2DE5` instead of `$36CA` —
   1,738 bytes over the ceiling before, 755 bytes of headroom after.
2. **`c64 build --area NAME=START:SIZE`** when the data has to be *at* a
   fixed address rather than merely out of the way. The flag pads the gap
   below the area so the segment really lands there; the cost is that the
   padding is real file bytes.
3. **Put variables in `CODE` with `.res`, not in `BSS`,** if anything must
   be linked after them. BSS is placed last, so a `.prg` whose tail is
   relocatable art would otherwise have its variables land on top of the
   sprite blocks.

**Then make the ceiling a build failure.** The overrun is otherwise a
wrong-pixels mystery found at the end, when the layout is expensive to
change. A deferred `.assert` next to the boundary costs one line:

    .import __BSS_LOAD__, __BSS_SIZE__
    .assert (__BSS_LOAD__ + __BSS_SIZE__) <= $3000, error, "BSS ran into the charset"

(the 6502-assembly skill's "BSS consumes address space" note has the full
version, and `--area` declares its areas `define = yes` so `__NAME_LOAD__`
works the same way).

### Multicolor bitmap: mode, clear, and one masked span

Bitmap mode replaces the charset with 8000 bytes of raw pixels. In
multicolor, each byte is four 2-bit pixels (160×200): bit-pair `00` shows
the background (`$D021`), `01` the cell's screen-RAM **high** nybble,
`10` its **low** nybble, `11` the cell's colour-RAM low nybble. The
address of pixel row `y`, cell column `c` is
`$2000 + (y & 248)*40 + (y & 7) + 8*c` — rows of cells are 320 bytes
apart, the 8 bytes within a cell stack vertically. A real rasteriser
precomputes that per scanline into `rowaddrl/h` tables (see
`demos/1812/tables.inc`, generated by `demos/1812/tools/gentables.py`);
this demo computes it once with shifts, plotaddr-style.

Fill bytes, not pixels: a span's middle cells take whole bytes; only the
two end cells need masks (`leftmask` keeps pixels `x&3`.., `rightmask`
keeps ..`x&3`; a single-cell span ANDs both). Ink `01` replicated across
a byte is `$55` (`10` would be `$AA`, `11` `$FF`).

```asm
; bitmapspan.s — multicolor bitmap from zero: set the mode, clear the
; canvas, paint one span (y=100, pixels 10-117, ink 01) with masked end
; cells. $2A at $03F0 is the done marker.
BMP    = $2000
SCREEN = $0400          ; in bitmap mode: per-cell palette, not text
PTR    = $fb            ; $FB/$FC zero-page pointer

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  lda     $d011           ; bitmap mode on (BMM, bit 5)
        ora     #$20
        sta     $d011
        lda     $d016           ; multicolor on (MCM, bit 4)
        ora     #$10
        sta     $d016
        lda     #$18            ; screen $0400 (hi nybble 1), bitmap $2000
        sta     $d018           ;   (bit 3) — both inside VIC bank 0

        ; ---- clear: bitmap = 0, palette = $16, colour RAM = 2 ----------
        lda     #>BMP
        sta     PTR+1
        lda     #0
        sta     PTR
        tay
        ldx     #32             ; 32 pages: $2000-$3FFF
clrbmp: sta     (PTR),y
        iny
        bne     clrbmp
        inc     PTR+1
        dex
        bne     clrbmp
        ldx     #0
clrscr: lda     #$16            ; 01 -> white (hi nybble 1), 10 -> blue (6)
        sta     SCREEN,x
        sta     SCREEN+$100,x
        sta     SCREEN+$200,x
        sta     SCREEN+$300,x
        lda     #2              ; 11 -> red
        sta     $d800,x
        sta     $d900,x
        sta     $da00,x
        sta     $db00,x
        inx
        bne     clrscr

        ; ---- rowbase = BMP + (y & 248)*40 + (y & 7), y = 100 -----------
        ; (y & 248)*40 = t*8 + t*32 with t = y & 248: shifts, no multiply.
        lda     #(100 & 248)
        sta     t8l
        lda     #0
        sta     t8h
        asl     t8l
        rol     t8h
        asl     t8l
        rol     t8h
        asl     t8l
        rol     t8h             ; t8 = t*8
        lda     t8l
        sta     t32l
        lda     t8h
        sta     t32h
        asl     t32l
        rol     t32h
        asl     t32l
        rol     t32h            ; t32 = t*32
        lda     t8l
        clc
        adc     t32l
        sta     PTR
        lda     t8h
        adc     t32h
        adc     #>BMP           ; low byte of BMP is 0, so no low-byte add
        sta     PTR+1
        lda     PTR
        clc
        adc     #(100 & 7)      ; + (y & 7)
        sta     PTR
        bcc     ptrok
        inc     PTR+1
ptrok:
        ; ---- advance to the first cell: pixels 10-117 = cells 2-29 -----
        lda     PTR
        clc
        adc     #(2 * 8)        ; 8 bytes per cell column
        sta     PTR
        bcc     spango
        inc     PTR+1
spango: ldy     #0
        ldx     #2              ; cell counter, 2..29
cell:   lda     #$ff            ; middle cells: the whole byte
        cpx     #2
        bne     notl
        lda     #$0f            ; left edge: first pixel 10 & 3 = 2
notl:   cpx     #29
        bne     notr
        and     #$f0            ; right edge: last pixel 117 & 3 = 1
notr:   sta     mask
        eor     #$ff
        and     (PTR),y         ; keep what the mask does not claim
        sta     keep
        lda     #$55            ; ink 01 in all four pixel slots
        and     mask
        ora     keep
        sta     (PTR),y
        lda     PTR             ; next cell column: +8
        clc
        adc     #8
        sta     PTR
        bcc     nc
        inc     PTR+1
nc:     inx
        cpx     #30
        bne     cell

        lda     #$2a            ; done marker for tests
        sta     $03f0
        rts                     ; back to BASIC — the bitmap stays on show

        .segment "BSS"
t8l:    .res 1
t8h:    .res 1
t32l:   .res 1
t32h:   .res 1
mask:   .res 1
keep:   .res 1
```

Verify from the host, not the picture: row 100 starts at
`$2000 + 96*40 + 4 = $2F04`, so cell 2's byte is `$2F14` (= `$55 & $0F` =
`$05` after the left mask), cell 3 is `$2F1C` (`$55`), cell 29 is `$2FEC`
(`$50`). `c64 screen --png` shows the line; `c64 mem read` proves it. Keep
the read-back rule in mind: the palette lives in screen RAM (readable
as-is) and colour RAM (4-bit — mask with `$0F`).

### Read the screen code you are moving into (collision by glyph)

Every character-mode game needs "what is in the cell I am about to enter?".
Read the target cell's screen code and dispatch on glyph ranges: unlike the
VIC collision latches (`$D01E`/`$D01F` — see the hardware reference's
gotchas), this is deterministic under a debugger, costs a handful of
cycles, and names *which* object was hit, which is what scoring needs. The
ranges below are this demo's allocation — a real game tests its own glyph
codes (a custom charset makes them contiguous by construction).

```asm
; collide.s — screen-code readback: know WHAT the bolt is about to hit.
; A bolt climbs column 20 from row 24; before each move it reads the
; screen code of the cell above and dispatches on glyph ranges.
PTR     = $fb                   ; zero-page pointer (see zero-page.md)
HITCODE = $03f0                 ; test hook: the screen code that stopped us
HITKIND = $03f1                 ; 1 = invader, 2 = shield, 0 = anything else

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
        lda     #1              ; an "invader" (glyph A) at row 5, column 20
        sta     $0400 + 5*40 + 20
        lda     #<($0400 + 24*40 + 20)
        sta     PTR             ; bolt cell: row 24, column 20
        lda     #>($0400 + 24*40 + 20)
        sta     PTR+1
step:   sec                     ; the cell above: PTR - 40
        lda     PTR
        sbc     #40
        sta     PTR
        bcs     read
        dec     PTR+1
read:   ldy     #0
        lda     (PTR),y         ; what is in the cell we are moving into?
        cmp     #$20            ; space: nothing there, fly on
        beq     draw
        sta     HITCODE         ; something — the code says exactly what
        cmp     #27             ; 0-26: @ and the letter glyphs play invaders here
        bcs     shield
        lda     #1
        sta     HITKIND
        rts                     ; back to BASIC (READY.)
shield: cmp     #102            ; 102: the checkerboard, playing a shield
        bne     other
        lda     #2
        sta     HITKIND
        rts
other:  lda     #0
        sta     HITKIND
        rts
draw:   lda     #$2a            ; '*': leave a trail so the flight shows
        sta     (PTR),y
        jmp     step
```

The bolt flies up the column instantly (no pacing — pace with the jiffy
clock in a real game, like the game-loop recipe), hits the `A` at row 5,
and stops with `HITCODE`=1, `HITKIND`=1. Verify live:
`c64 run collide.s`, then `c64 mem get $03f0 2` → `1 1`. A real game
bounds the climb at row 0; here the hit always lands first.

## Verifying a recipe-based program

For BASIC, static-check the source first — `c64 basic check mygame.bas`
catches keyword fusion (`total=5` tokenizes as `TO TAL=5`), missing
GOTO/GOSUB targets, out-of-range POKEs and non-V2 keywords without an
emulator round trip. Fix every `E…` before running.

Then run it and assert on the screen, exactly like the tests here do:

```
c64 run mygame.s
c64 wait --text "expected output"
c64 screen
```

or wrap it in a YAML test (`c64 test run` — format in docs/cli.md).
