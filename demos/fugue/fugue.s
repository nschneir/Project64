; fugue.s -- J. S. Bach, Fugue No. 2 in C minor, BWV 847, played on three SID
; voices while its notated score scrolls right to left across a custom-charset
; grand staff, in time with the music.
;
; Spec: SPEC.md.  Plan: PLAN.md.  Every design decision below is argued there;
; the comments here state contracts and hardware quirks only.
;
; THE ONE CLOCK.  Everything is a function of `frame`, incremented once per
; raster IRQ:
;
;   $D016 fine scroll = 6 - 2*(frame & 3)      -> 2 pixels of travel a frame
;   column shift      when (frame & 3) == 0    -> 8 pixels every 4 frames
;   note attack       when (frame & 7) == 0    -> 16 pixels a sixteenth
;                     and frame >= LEADIN
;
; so one sixteenth note is two character columns and eight frames, and the
; scroll offset counter IS the sixteenth-note subdivision counter.  The
; picture and the music cannot drift apart because there is one counter and
; both read it.

        .import __BSS_LOAD__, __BSS_SIZE__

; ---- hardware ------------------------------------------------------------
CINV     = $0314                ; KERNAL IRQ vector
BLNSW    = $00CC                ; non-zero = cursor blink off
SCREEN   = $0400
COLRAM   = $D800
SPRPTR   = SCREEN + $03F8       ; sprite data pointers (memory-maps.md)
CHARSET  = $2000                ; NOT $1000/$1800: the char ROM's 4 KB image
SPRDATA  = $2800                ;   covers both of those bases in VIC bank 0
SPRBLK   = SPRDATA / 64         ; pointer value = data address / 64
SID      = $D400
PALFLAG  = $02A6                ; 0 = NTSC, 1 = PAL (zero-page.md)
IRQLINE  = 204                  ; the raster the per-frame tick is armed at.
                                ;   Not the top border: once the VIC has
                                ;   latched a text row's matrix and colour on
                                ;   its badline (raster 51 + 8*R), later
                                ;   writes to that row cannot affect the
                                ;   current frame -- so the shift may begin
                                ;   the moment the LAST band row has latched,
                                ;   at 51 + 8*19 = 203, and prepare the next
                                ;   frame across the whole bottom border and
                                ;   top border together.  That is 263 raster
                                ;   lines of room instead of 215, and it is
                                ;   what the 12,856-cycle shift needs.

; ---- geometry (SPEC.md section 3) ----------------------------------------
; The position ladder is absolute: p = 0 is D6 at LADTOP's upper half, p = 29
; is C2 at LADTOP+14's lower half.  row = LADTOP + (p >> 1), half = p & 1, and
; sprite Y = 42 + 8*LADTOP + 4*p because 8*(p>>1) + 4*(p&1) == 4*p, which is
; 74 + 4*p at LADTOP = 4.  BANDTOP/BANDROWS only choose which of those rows
; are live; neither formula depends on them.
LADTOP   = 5                    ; screen row of ladder positions 0 and 1
                                ;   (D6 and C6).  row = LADTOP + (p >> 1),
                                ;   sprite Y = 42 + 8*LADTOP + 4*p.
STAFFTOP = LADTOP + 2           ; treble top line (F5) is ladder p = 5
BANDTOP  = 5                    ; first scrolled screen row
BANDROWS = 15                   ; rows 5..19 -- dead centre of the 25-row
                                ;   screen, and every row lower raises the
                                ;   last row's badline deadline by 8 rasters,
                                ;   which is the whole budget argument in
                                ;   SPEC.md section 5
NOWCOL   = 10                   ; screen column a head occupies as it sounds
HOLD     = 150                  ; frames the picture stands still before the
                                ;   scroll starts.  Without it the clefs are
                                ;   gone in twelve frames -- measured, on the
                                ;   first build: at frame 30 the score had
                                ;   already advanced 7 columns and score
                                ;   columns 1-2 were off the left edge.  The
                                ;   hold is what gives the reader (and the
                                ;   evidence protocol) a look at the staves,
                                ;   the clefs and the first bar line before
                                ;   anything moves.
LEADIN   = 88                   ; scrolling but silent frames after the hold.
                                ;   HOLD + LEADIN = 238 frames = 4.0 s of
                                ;   silence, which covers the ~84 frames
                                ;   arming an audio capture costs.
SC0      = 31                   ; score column of sixteenth 0's accidental
                                ;   slot; its head is at SC0+1 = 32 and
                                ;   reaches NOWCOL after LEADIN/4 = 22
                                ;   shifts.  SC0 = LEADIN/4 + NOWCOL - 1.
NSIX     = 496                  ; 31 bars x 16 sixteenths
RENDAHEAD = 15                  ; drawcol is always this many sixteenths ahead
                                ;   of the sequencer: (shifts+39-SC0)/2 -
                                ;   (shifts-60)/2 == 15, identically

; ---- glyph codes (PLAN.md, "Glyph code map") -----------------------------
; All in 32..79.  Never 96 or 224 (they decode to a blank in `c64 screen`),
; never 128..154 (reverse A-Z).
GBLANK   = 32
GLINE    = 33
GHEAD1   = 34                   ; + (online<<2) + (hollow<<1) + half
GHEAD2   = 42                   ; + (online<<2) + (lowerhollow<<1) + upperhollow
GACC     = 50                   ; + (online<<2) + (half<<1) + flat
GBAR     = 58                   ; + online
GTREB    = 64                   ; + col*5 + (row-6)
GBASS    = 74                   ; + col*3 + (row-12)

CWHITE   = 1

; ---- zero page -----------------------------------------------------------
; $FB-$FE are the four bytes zero-page.md documents as free.  BASIC is still
; resident, so nothing else in zero page is touched.
ptr      = $FB                  ; screen pointer
cptr     = $FD                  ; colour RAM pointer

; ==========================================================================
        .segment "LOADADDR"
        .word   $0801

        .segment "EXEHDR"
        .word   nextln          ; pointer to the next BASIC line
        .word   10              ; line number 10
        .byte   $9E, "2061", $00 ; SYS 2061
nextln: .word   $0000           ; end of BASIC program

; The generated note tables come first so that every reference to posmidi,
; midicol, notes and pedal0/1 below is a BACKWARD one.  ca65 sizes a forward
; reference by guessing, and `lda midicol-33,y` guessed zero page -- which has
; no such addressing mode, so it failed the build outright.  A guess that had
; gone the other way would have assembled and read the wrong bytes.
        .segment "RODATA"
        .include "notes.inc"

; ==========================================================================
        .segment "CODE"

; --------------------------------------------------------------------------
; init -- black screen, our charset, the staff drawn, the IRQ armed.
; --------------------------------------------------------------------------
start:
        sei
        lda     #0
        sta     $D020           ; border black
        sta     $D021           ; background black
        lda     #1
        sta     BLNSW           ; cursor blink OFF.  Belt and braces: the IRQ
                                ;   below runs no ROM code, so nothing would
                                ;   blink it -- but BASIC is still resident
                                ;   and a blink writes a character cell, which
                                ;   on this screen would be a corrupted note.

        ; ---- clear all 1000 cells to blank / white -----------------------
        ldx     #0
clrlp:  lda     #GBLANK
        sta     SCREEN + $0000,x
        sta     SCREEN + $0100,x
        sta     SCREEN + $0200,x
        sta     SCREEN + $02E8,x
        lda     #CWHITE
        sta     COLRAM + $0000,x
        sta     COLRAM + $0100,x
        sta     COLRAM + $0200,x
        sta     COLRAM + $02E8,x
        inx
        bne     clrlp

        ; ---- video mode --------------------------------------------------
        lda     #$1B
        sta     $D011           ; text, 25 rows, DEN on, raster MSB clear
        lda     xsc             ; 6 -- initialised in vars.s, never left to
        sta     $D016           ;   chance (la-galaxia/AUDIT.md:40)
        lda     #$18
        sta     $D018           ; screen $0400 + charset $2000.
                                ;   Reads back as $19: bit 0 is unused and
                                ;   reads 1.  Verified live.

        ; ---- which machine are we on? ------------------------------------
        lda     PALFLAG
        sta     videostd

        ; ---- sprites ------------------------------------------------------
        lda     #SPRBLK
        sta     SPRPTR + 0      ; all three glows are the same shape...
        sta     SPRPTR + 1
        sta     SPRPTR + 2
        lda     #6              ; ...and differ only in colour: blue,
        sta     $D027           ;   dark gray, brown -- the two colours too
        lda     #11             ;   dim to be note heads, plus brown, put to
        sta     $D028           ;   use where dimness is the point
        lda     #9
        sta     $D029
        lda     #%00000111
        sta     $D01B           ; sprites 0-2 BEHIND character data.  This is
                                ;   the bit that makes it read as backlit:
                                ;   the glow shows only through the cell's
                                ;   background pixels, never over the head.
        lda     #0
        sta     $D010           ; no X MSBs: the glow lives at x 88..102
        sta     $D015           ; all off until a voice sounds
        sta     $D017           ; no expansion
        sta     $D01D
        sta     $D01C           ; hires

        jsr     musinit
        jsr     drawscreen
        jsr     irqon
        cli

mainloop:
        jmp     mainloop        ; every moving part is in the IRQ

; --------------------------------------------------------------------------
; irqon / irqoff -- the raster interrupt.
;
; Armed at IRQLINE = 204, immediately after the last band row's badline, so
; the whole bottom-plus-top border is available to prepare the next frame.
; SPEC.md section 5 has the arithmetic.
;
; One event per frame, so there is no next line to arm and the recipe's
; "compare the line you just armed against the live raster" loop does not
; apply.  204 < 256 keeps $D011 bit 7 clear.
; --------------------------------------------------------------------------
irqon:
        sei
        lda     #$7F
        sta     $DC0D           ; CIA1 timer IRQ off: one interrupt source,
        lda     $DC0D           ;   or the raster high-water mark is fiction.
                                ;   Read to ack whatever it had pending.
        lda     CINV
        sta     oldvec
        lda     CINV+1
        sta     oldvec+1
        lda     #<irq
        sta     CINV
        lda     #>irq
        sta     CINV+1
        lda     $D011
        and     #$7F            ; compare line is below 256
        sta     $D011
        lda     #IRQLINE
        sta     $D012
        lda     #$01
        sta     $D01A           ; raster source on...
        sta     $D019           ; ...with no stale latch
        cli
        rts

irqoff:
        sei
        lda     #0
        sta     $D01A
        lda     oldvec
        sta     CINV
        lda     oldvec+1
        sta     CINV+1
        lda     #$81
        sta     $DC0D           ; jiffy clock and keyboard scan back on
        cli
        rts

irq:
        lda     #$01
        sta     $D019           ; ack first: an unacked raster IRQ re-fires
                                ;   the instant the RTI runs
        cld                     ; an IRQ does not clear D on the NMOS 6502,
                                ;   and everything below is binary
        jsr     tick
        lda     #$01
        sta     $D019           ; ack again on the way out
        ; Exit by pulling A/X/Y here, NOT through $EA31 or $EA81.  Nothing
        ; from ROM runs inside this interrupt, which is what lets the demo
        ; run on the MEGA65 open-roms KERNAL the browser page boots: $EA31
        ; and $EA81 are Commodore KERNAL internals, not published entry
        ; points, and a clean-room ROM has no reason to put anything at
        ; either address.  `demos/amiga_ball` sets the same rule for the same
        ; reason.  The KERNAL's $FF48 entry pushed A, X and Y before
        ; `jmp (CINV)`, so these three pulls are the exact complement.
        ;
        ; The cost is the jiffy clock: with CIA1's timer IRQ off and no
        ; KERNAL handler running, $A0-$A2 stops counting, so `c64 audio
        ; capture` reports `lead_in_frames` as null -- "not measured", never
        ; "no lead-in".  tools/audio-evidence.sh handles that by measuring
        ; the window start off the log's own pulse-width sweep instead, which
        ; is more exact than the jiffy estimate was anyway.
        pla
        tay
        pla
        tax
        pla
        rti

; --------------------------------------------------------------------------
; tick -- the whole per-frame job, as a subroutine ending in RTS so that
; `c64 profile tick` can price it.  A raster handler entered through $0314 is
; not callable and cannot be profiled; this split is what makes the frame
; budget measurable rather than asserted.
;
; The order is fixed by two deadlines (SPEC.md section 5):
;   1  $D016            before raster 51, when the display window opens
;   2  musfetch         no deadline -- but it must precede glowtick, so the
;                       sprites show THIS frame's note and not last frame's
;   3  glowtick         before raster 74, the topmost glow Y
;   4  muswrite         no deadline
;   5  shiftband+drawcol before raster 195, the last band row's badline
; --------------------------------------------------------------------------
tick:
        inc     frame
        bne     :+
        inc     frame+1
:
        ; ---- 0. the hold -------------------------------------------------
        ; sf is the scroll clock: frame less the static hold.  Everything
        ; below reads sf, never frame, so the hold shifts the whole timeline
        ; by a constant and leaves the one-clock property intact.
        lda     frame+1
        bne     tkgo
        lda     frame
        cmp     #HOLD
        bcs     tkgo
        lda     #0
        sta     state
        sta     sf
        sta     sf+1
        lda     #6
        sta     xsc
        sta     $D016
        jsr     glowtick        ; nothing sounds yet, so this just keeps the
        rts                     ;   sprites off and the published bytes true
tkgo:
        lda     frame
        sec
        sbc     #<HOLD
        sta     sf
        lda     frame+1
        sbc     #>HOLD
        sta     sf+1

        ; ---- 0b. it is over ------------------------------------------------
        ; Once the sequencer has run out, this frame and every frame after it
        ; does NOTHING but keep the counter.  The transition frame itself
        ; still runs the whole tick -- that is where musfetch releases the
        ; gates, glowtick puts the sprites out and muswrite writes the release
        ; -- so by the time this branch is first taken the machine is already
        ; in its final state, and leaving it alone is the entire ending.
        ;
        ; `frame` keeps counting so `c64 until tick` is still an anchor after
        ; the end; nothing else changes, so there is nothing to anchor ON that
        ; could move.
        lda     state
        cmp     #3
        bne     tkalive
        rts
tkalive:

        ; ---- the scroll's own stop condition ------------------------------
        ; Computed before the fine scroll below, because the fine scroll has
        ; to stop when the column shift does.  glowtick reads it too.
        lda     shifts+1
        cmp     stopshift+1
        bcc     tkscron
        bne     tkscroff
        lda     shifts
        cmp     stopshift
        bcc     tkscron
tkscroff:
        lda     #0
        beq     tkscrset
tkscron:
        lda     #1
tkscrset:
        sta     scrollon

        ; ---- 1. fine scroll ----------------------------------------------
        ; ONLY WHILE THE SCORE IS STILL MOVING.  This write used to be
        ; unconditional, and the last chord of the fugue sat there shaking:
        ; the column shift had stopped but `xsc` went on cycling 6, 4, 2, 0,
        ; so the whole picture jittered six pixels back and forth at 15 Hz
        ; for ever.  Freezing it holds the picture exactly where the final
        ; shift left it -- `xsc` is 6 on a shift frame, which is where the
        ; heads at the now column were drawn.
        lda     scrollon
        beq     tknoscr
        lda     sf
        and     #3
        asl     a               ; 0, 2, 4, 6
        sta     tmp0
        lda     #6
        sec
        sbc     tmp0            ; 6, 4, 2, 0
        sta     xsc
        sta     $D016           ; bit 3 clear = 38 columns, which is what
                                ;   hides the column entering at the right
                                ;   edge; bit 4 clear = not multicolour
tknoscr:

        ; ---- 2..4 music and sprites --------------------------------------
        jsr     musfetch
        jsr     glowtick
        jsr     muswrite

        ; ---- 5. shift on phase 0, render the entering column on phase 1 --
        lda     sf
        and     #3
        beq     :+
        cmp     #1
        bne     tickdone2
        lda     scrollon
        bne     tickdraw
tickdone2:
        jmp     tickdone
:
        lda     sf
        ora     sf+1
        bne     :+
        jmp     tickdone        ; sf == 0: the hold has only just ended and
                                ;   init already drew score columns 0..39
:
        lda     scrollon
        bne     :+
        jmp     tickdone        ; the last head is on the now column; the
                                ;   chord rings there rather than scrolling off
:
        jsr     shiftband
        lda     $D012
        cmp     shiftline
        bcc     :+
        sta     shiftline       ; high-water, shift frames only
:
        inc     shifts
        bne     :+
        inc     shifts+1
:
        lda     $D012
        cmp     tickend
        bcc     tickdone
        sta     tickend
tickdone:
        rts

; drawcol runs on the frame AFTER the shift, and that is not a compromise --
; it is free.  Screen column 39 is NEVER VISIBLE in 38-column mode: the mode
; hides the rightmost 9 pixels (X 335-343), and at every fine-scroll value
; the demo uses, column 39 spans X 336-349 at xsc 0 through 342-349 at xsc 6,
; entirely inside that hidden strip.  The column only reaches the eye after
; the next shift has moved it to column 38.  So the newly rendered column has
; a whole four-frame cycle of slack, and taking its ~2,700 cycles off the
; shift frame is what brings that frame inside its badline deadline.
tickdraw:
        lda     shifts          ; render score column shifts+39 into screen
        clc                     ;   column 39
        adc     #39
        sta     dcol
        lda     shifts+1
        adc     #0
        sta     dcol+1
        lda     #39
        sta     dscr
        jmp     drawcol

; ==========================================================================
        .include "vars.s"
        .include "staff.s"
        .include "scroll.s"
        .include "music.s"
        .include "glow.s"

; The custom character set.  Codes 0-31 are deliberately blank: this demo
; draws nothing but its own 48 glyphs, so the ROM charset is never copied and
; there is no CHAREN dance to get wrong.  The .res puts glyph 32 at $2100.
        .segment "CHARS"
        .res    32 * 8, 0
        .include "chars.inc"

        .segment "SPRITES"
        .include "sprites.inc"

; Overrunning the charset is otherwise a wrong-pixels mystery rather than a
; build failure.
        .segment "CODE"
        .assert (__BSS_LOAD__ + __BSS_SIZE__) <= CHARSET, error, "code+data ran into the charset"
