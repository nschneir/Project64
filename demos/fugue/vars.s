; vars.s -- every mutable byte the demo owns, with the labels test.yaml,
; c64 until and the evidence protocol read back.
;
; Everything lives in DATA, not BSS: BSS is not part of the .prg, so a `.res`
; there holds whatever was in RAM at load time (the 6502-assembly skill's
; "BSS is not in the .prg" trap).  In DATA the bytes ship as real zeros --
; or as the initialisers below -- and a fresh LOAD always starts known.
;
; ld65's -Ln emits every label, exported or not, so nothing here needs
; .export.  Equates do NOT reach the label file, which is why every signal a
; test names is storage in this file rather than a constant in fugue.s.

        .segment "DATA"

; ---- the one clock -------------------------------------------------------
; Everything in the demo is a function of `frame`.  See SPEC.md section 1.
frame:      .word 0             ; frames since init; incremented once per IRQ
state:      .byte 0             ; 0 HOLD (static), 1 LEAD (scrolling,
                                ;   silent), 2 PLAY, 3 FINE
xsc:        .byte 6             ; the $D016 fine-scroll value written this
                                ;   frame: 6,4,2,0.  Initialised here and not
                                ;   in init(): la-galaxia shipped a bug where
                                ;   an uninitialised $D016 shadow wrote 0
                                ;   every frame (its AUDIT.md:40).
shifts:     .word 0             ; column shifts performed since init
scrollon:   .byte 1             ; 1 while the score is still moving.  Goes to
                                ;   0 when `shifts` reaches `stopshift`, which
                                ;   is where the LAST ATTACK's head sits on
                                ;   the now column -- not where the sequencer
                                ;   runs out, which is eight sixteenths later.
                                ;   glowtick freezes `sprage` on it, so the
                                ;   final chord keeps its backlight instead of
                                ;   ageing out while standing still.
sf:         .word 0             ; the scroll clock: frame less HOLD.  Every
                                ;   scroll and sequencer derivation reads
                                ;   this, never `frame`, so the static hold
                                ;   at the start shifts the whole timeline by
                                ;   a constant and one clock still drives
                                ;   both the picture and the music.

; ---- musical position ----------------------------------------------------
sixteenth:  .word 0             ; index of the SOUNDING sixteenth, 0..495
rendk:      .word 0             ; the sixteenth index drawcol last drew.
                                ;   rendk - sixteenth is invariably 15.
bar:        .byte 1             ; 1..31
beat:       .byte 1             ; 1..4
slot:       .byte 0             ; 0..15, the sixteenth within the bar

; ---- per voice -----------------------------------------------------------
; Index 0 = SID voice 1 (subject), 1 = voice 2 (countersubject), 2 = voice 3
; (bass).  Held as three parallel 3-byte arrays so a loop can walk them; the
; per-voice labels below alias the elements for tests that want to name one.
vnote:      .res 3, 0           ; MIDI number sounding, 0 = silent
vpos:       .res 3, $FF         ; staff ladder position p, $FF = none
vacc:       .res 3, 0           ; 0 none, 1 sharp, 2 flat
vatk:       .res 3, 0           ; 1 on the frame this voice attacked
v1idx:      .word 0             ; attacks played on voice 1 so far
v2idx:      .word 0
v3idx:      .word 0

; ---- the sprite backlight ------------------------------------------------
sprx:       .res 3, 0           ; the X register value written this frame
spry:       .res 3, 0           ; the Y register value written this frame
sprage:     .res 3, 0           ; frames since that voice last attacked
sprcol:     .res 3, 0           ; screen column of the head being backlit
sprena:     .byte 0             ; the $D015 value written this frame

; ---- accounting ----------------------------------------------------------
collide:    .word 0             ; cells where two voices wanted the same half
                                ;   of the same character cell.  Two voices a
                                ;   diatonic step apart share a cell and get
                                ;   the both-halves glyph -- that is not a
                                ;   collision and is not counted here.
pwmval:     .word $0400         ; voice 1 pulse width, as written
pwmdir:     .byte 1             ; +1 rising, $FF falling
cutoff:     .word $7000         ; filter cutoff, as written (hi byte is $D416)
cutdir:     .byte $FF           ; $FF descending, +1 returning
freqlo:     .res 56, 0          ; MIDI 33..88 for THIS machine, copied out of
freqhi:     .res 56, 0          ;   the NTSC or PAL table at init
videostd:   .byte 0             ; 0 NTSC, 1 PAL, latched from $02A6 at init

; ---- the frame budget, measured by the program ---------------------------
; Kept only on frames that shift, because a non-shift frame exits in the
; border at raster ~260 and would poison a high-water mark that included it.
; docs/graphics-and-sprites.md section 4: "a per-frame budget is measured by
; the program, not by the harness".
shiftline:  .byte 0             ; high-water $D012 immediately after shiftband
tickend:    .byte 0             ; high-water $D012 at tick's exit

; ---- the SID shadow ------------------------------------------------------
; $D400-$D418 mirrored in order.  On real hardware those 25 registers are
; write-only, so this block is the program's own evidence and the only one
; that survives off the emulator; the register log from c64 audio capture is
; the emulator's.  Keep both -- they fail in different directions.
sidshadow:  .res 25, 0

; ---- drawcol's working set -----------------------------------------------
dcol:       .word 0             ; score column to render
dscr:       .byte 0             ; screen column to render it into, 0..39
colbuf:     .res 15, 0          ; one screen code per band row, staged here
colclr:     .res 15, 0          ; ... and one colour nybble
curline:    .res 15, 0          ; 1 where this column's row carries a line
                                ;   (staff row, or a lit ledger)
colocc:     .res 15, 0          ; bit0 upper half taken, bit1 lower half
                                ;   taken, bit2 an accidental is here
colhol:     .res 15, 0          ; bit0 upper head hollow, bit1 lower hollow --
                                ;   `and #3` of this IS the both-halves glyph
                                ;   index, (lowerhollow<<1)+upperhollow
ledgset:    .byte 0             ; bitmask of ledger positions lit this column

; This sixteenth's three note bytes, fetched and decoded ONCE per column and
; then read from these arrays by the ledger pass, the head pass, the
; accidental pass and the sequencer alike.  The first build decoded per pass
; per voice and drawcol cost 2,776 cycles measured; the arrays are what took
; it down.
dk:         .word 0             ; the sixteenth this column belongs to
nb:         .res 3, 0           ; the raw byte: $00 rest, $FF hold, else a note
np:         .res 3, 0           ; ladder position 0..29
nhalf:      .res 3, 0           ; 0 upper, 1 lower
ni:         .res 3, 0           ; band row index
nacc:       .res 3, 0           ; 0 none, 1 sharp, 2 flat
nhol:       .res 3, 0           ; 1 = hollow head (quarter or longer)
nmidi:      .res 3, 0           ; sounding MIDI number

; ---- scratch -------------------------------------------------------------
tmp0:       .byte 0
tmp1:       .byte 0
tmp2:       .byte 0
tmpv:       .byte 0             ; voice index across pointer math -- an
                                ;   indexed loop that calls a subroutine must
                                ;   reload its index (asm/SKILL.md)
oldvec:     .word 0             ; the $0314 vector irqon displaced
