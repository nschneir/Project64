; stars.s -- the parallax starfield, as a character layer.
;
; Three layers of stars, drawn once into the playfield window and never
; redrawn.  What scrolls is the *glyph*: each layer's eight charset bytes are
; rotated down one row at its own cadence, so every cell showing that glyph
; scrolls together.  It costs about forty cycles a frame and, unlike the fine
; scroll registers, leaves $D011 and $D016 free for the formation's breathe
; sway (§7).
;
; Which layer a cell belongs to comes off a fixed 32-entry pattern indexed by
; row*5 + column, so the field looks scattered without a per-cell table and
; without any run-time randomness to reproduce.

        .segment "ENGINE"

starglyph:
        .byte   GLY_STAR0, GLY_STAR1, GLY_STAR2
starcolour:
        .byte   COL_WHITE, COL_GREY, COL_DKGREY
starrate:                               ; frames between rotations
        .byte   1, 2, 3

starpat:
        .byte   0,2,1,0,1,2,2,0,1,1,2,0,2,1,0,2
        .byte   1,0,2,2,0,1,0,2,1,2,0,1,1,0,2,1

row5:   .repeat PFROWS, i
        .byte   (i * 5) & 31
        .endrepeat

; ---- starrow -- lay one playfield row of stars, screen and shadow ---------
; One pointer for the whole row and a Y walk, the same trick drawslot uses:
; going through pfput per cell rebuilt four pointers for every star.
starrow:
        lda     #PFCOL
        sta     scrcol
        jsr     pfptr
        ldx     scrrow
        lda     row5,x
        clc
        adc     #PFCOL
        sta     tmp4                    ; star pattern index of the first cell
        ldy     #0
strow1: jsr     starput
        inc     tmp4
        iny
        cpy     #PFW
        bne     strow1
        lda     cells_drawn
        clc
        adc     #PFW
        sta     cells_drawn
        rts

; ---- starat -- A = glyph, txtcol = colour, for (scrrow, scrcol) ----------
starat: ldx     scrrow
        lda     row5,x
        clc
        adc     scrcol
        and     #31
        tax
        ldy     starpat,x
        lda     starcolour,y
        sta     txtcol
        lda     starglyph,y
        rts

; ---- starstick -- rotate each layer's glyph on its own cadence -----------
starstick:
        ldx     #0
st1:    inc     starphase,x
        lda     starphase,x
        cmp     starrate,x
        bcc     st2
        lda     #0
        sta     starphase,x
        stx     tmp3
        jsr     rotglyph
        ldx     tmp3
st2:    inx
        cpx     #3
        bne     st1
        rts

; ---- rotglyph -- X = layer 0-2; roll its eight charset bytes down a row ---
; The three glyph addresses are constants, so they come off a table instead of
; being shifted out of the screen code; and the roll is unrolled, because the
; loop spent as long stepping Y back and forth as it did moving bytes.
glyphlo:
        .byte   <(CHARSET + GLY_STAR0*8)
        .byte   <(CHARSET + GLY_STAR1*8)
        .byte   <(CHARSET + GLY_STAR2*8)
glyphhi:
        .byte   >(CHARSET + GLY_STAR0*8)
        .byte   >(CHARSET + GLY_STAR1*8)
        .byte   >(CHARSET + GLY_STAR2*8)

rotglyph:
        lda     glyphlo,x
        sta     PTR
        lda     glyphhi,x
        sta     PTR+1
        ldy     #7
        lda     (PTR),y                 ; the bottom row wraps to the top
        pha
.repeat 7, i
        ldy     #6-i
        lda     (PTR),y
        ldy     #7-i
        sta     (PTR),y
.endrepeat
        pla
        ldy     #0
        sta     (PTR),y
        rts
