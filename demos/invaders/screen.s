; screen.s — character-screen plumbing: row tables, the cell pointer, text
; output without CHROUT, the HUD, and the title screen.
;
; Nothing here calls ROM: CHROUT prints at the cursor and scrolls, which is
; wrong for a fixed HUD, and the spec bans ROM calls in the hot path anyway.

        .segment "CODE"

; --- row base addresses ---------------------------------------------------
; The colour-RAM row shares the low byte; its high byte is rowhi + $D4
; ($D800 - $0400), which is what cellptr adds.
rowlo:  .repeat 25, I
        .byte   <(SCREEN + 40*I)
        .endrepeat
rowhi:  .repeat 25, I
        .byte   >(SCREEN + 40*I)
        .endrepeat

; --- cellptr: X = row (0-24), Y = column (0-39) ---------------------------
; Leaves PTR at the screen cell and CPTR at the matching colour cell.
; Clobbers A. X and Y survive.
cellptr:
        tya
        clc
        adc     rowlo,x
        sta     PTR
        sta     CPTR
        lda     rowhi,x
        adc     #0
        sta     PTR+1
        clc
        adc     #$d4
        sta     CPTR+1
        rts

; --- clrscreen: blank every cell and paint colour RAM black ---------------
clrscreen:
        ldx     #0
csl:    lda     #32
        sta     SCREEN,x
        sta     SCREEN+250,x
        sta     SCREEN+500,x
        sta     SCREEN+750,x
        lda     #1
        sta     COLRAM,x
        sta     COLRAM+250,x
        sta     COLRAM+500,x
        sta     COLRAM+750,x
        inx
        cpx     #250
        bne     csl
        rts

; --- txtat: A = row, Y = column, STR -> ASCII text, txtcol = colour nybble
; Folds ASCII to screen codes: codes below $40 already are screen codes,
; letters $41-$5A fold down by $40.
txtat:  tax
        jsr     cellptr
putstr: ldy     #0
psl:    lda     (STR),y
        beq     psdone
        cmp     #$40
        bcc     psput
        sbc     #$40            ; the cmp left carry set, so this is exact
psput:  sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        iny
        bne     psl
psdone: rts

; --- putblocks: A = row, Y = column, STR -> a '#'/' ' picture -------------
; '#' becomes screen code 160 (reverse space: a solid block), anything else
; becomes a space.  Colour cycles through `rainbow` every 8 columns, so the
; big title letters come out multi-coloured.  All colours are < 8, which
; keeps these cells in hires mode while multicolor text mode is enabled.
putblocks:
        tax
        jsr     cellptr
        ldy     #0
pbl:    lda     (STR),y
        beq     pbdone
        cmp     #'#'
        bne     pbspc
        lda     #160
        sta     (PTR),y
        lda     rainbow,y
        sta     (CPTR),y
        jmp     pbnext
pbspc:  lda     #32
        sta     (PTR),y
pbnext: iny
        bne     pbl
pbdone: rts

; one colour per title-letter column group (letters are 4 wide + 1 gap).
; Every value is < 8, which keeps these cells in hires while multicolor text
; mode is on.
rainbow: .byte  1,1,1,1,1, 7,7,7,7,7, 7,7,7,7,7, 5,5,5,5,5
         .byte  5,5,5,5,5, 3,3,3,3,3, 3,3,3,3,3, 1,1,1,1,1

; --- the HUD --------------------------------------------------------------
; Static labels and colours are drawn once per state entry; the digit cells
; are rewritten only when their dirty flag is set, so nothing repaints the
; whole screen per frame.
HUDROW   = 0
SCORECOL = 6
HICOL    = 18
WAVECOL  = 33
LIVEROW  = 24
LIVECOL  = 6

drawhud:
        lda     #1
        sta     txtcol
        SETSTR  txscore
        lda     #HUDROW
        ldy     #0
        jsr     txtat
        SETSTR  txhi
        lda     #HUDROW
        ldy     #15
        jsr     txtat
        SETSTR  txwave
        lda     #HUDROW
        ldy     #28
        jsr     txtat
        SETSTR  txlives
        lda     #LIVEROW
        ldy     #0
        jsr     txtat
        ; paint the digit cells' colour once
        ldx     #0
dhc:    lda     #1
        sta     COLRAM + 40*HUDROW + SCORECOL,x
        sta     COLRAM + 40*HUDROW + HICOL,x
        inx
        cpx     #6
        bne     dhc
        lda     #1
        sta     COLRAM + 40*HUDROW + WAVECOL
        sta     COLRAM + 40*HUDROW + WAVECOL + 1
        sta     COLRAM + 40*LIVEROW + LIVECOL
        lda     #1
        sta     scdirty
        sta     hidirty
        sta     wvdirty
        sta     lvdirty
        rts

updhud:
        lda     scdirty
        beq     uh2
        lda     #0
        sta     scdirty
        ldx     #0
uh1:    lda     score,x
        ora     #48
        sta     SCREEN + 40*HUDROW + SCORECOL,x
        inx
        cpx     #6
        bne     uh1
uh2:    lda     hidirty
        beq     uh4
        lda     #0
        sta     hidirty
        ldx     #0
uh3:    lda     hiscore,x
        ora     #48
        sta     SCREEN + 40*HUDROW + HICOL,x
        inx
        cpx     #6
        bne     uh3
uh4:    lda     wvdirty
        beq     uh6
        lda     #0
        sta     wvdirty
        lda     wave
        ldx     #0
uh5:    cmp     #10
        bcc     uh5d
        sbc     #10
        inx
        jmp     uh5
uh5d:   ora     #48
        sta     SCREEN + 40*HUDROW + WAVECOL + 1
        txa
        ora     #48
        sta     SCREEN + 40*HUDROW + WAVECOL
uh6:    lda     lvdirty
        beq     uh7
        lda     #0
        sta     lvdirty
        lda     lives
        ora     #48
        sta     SCREEN + 40*LIVEROW + LIVECOL
        ; ...and one little laser base per remaining life, as the cabinet did
        ldx     #0
        ldy     #0                      ; every other cell, so they read as
uhl:    lda     #32                     ; separate little ships
        cpx     lives
        bcs     uhl2                    ; X >= lives: leave the slot blank
        lda     #BASEICON
uhl2:   sta     SCREEN + 40*LIVEROW + LIVECOL + 3,y
        lda     #8|5                    ; multicolor, green
        sta     COLRAM + 40*LIVEROW + LIVECOL + 3,y
        iny
        iny
        inx
        cpx     #5
        bne     uhl
uh7:    rts

; --- the title screen -----------------------------------------------------
drawtitle:
        jsr     clrscreen
        SETSTR  titl0
        lda     #2
        ldy     #0
        jsr     putblocks
        SETSTR  titl1
        lda     #3
        ldy     #0
        jsr     putblocks
        SETSTR  titl2
        lda     #4
        ldy     #0
        jsr     putblocks
        SETSTR  titl3
        lda     #5
        ldy     #0
        jsr     putblocks
        SETSTR  titl4
        lda     #6
        ldy     #0
        jsr     putblocks

        lda     #1
        sta     txtcol
        SETSTR  txadv
        lda     #9
        ldy     #10
        jsr     txtat

        ; three sample invaders with their point values, then the UFO line
        ldx     #11                     ; row
        ldy     #13                     ; column
        lda     #64                     ; squid frame A, left half
        jsr     samplerow
        SETSTR  tx30
        lda     #11
        ldy     #17
        jsr     txtat

        ldx     #13
        ldy     #13
        lda     #68                     ; crab frame A
        jsr     samplerow
        SETSTR  tx20
        lda     #13
        ldy     #17
        jsr     txtat

        ldx     #15
        ldy     #13
        lda     #72                     ; octopus frame A
        jsr     samplerow
        SETSTR  tx10
        lda     #15
        ldy     #17
        jsr     txtat

        lda     #7
        sta     txtcol
        SETSTR  txmyst
        lda     #17
        ldy     #13
        jsr     txtat

        lda     #1
        sta     txtcol
        SETSTR  txplay
        lda     #21
        ldy     #9
        jsr     txtat
        rts

; samplerow: X = row, Y = column, A = the left-half glyph code of a class.
; Draws the two cells in that class's colour (the same colour table the
; formation uses), so the score-advance table shows the real artwork.
samplerow:
        sta     tmp0
        jsr     cellptr
        lda     tmp0
        ldy     #0
        sta     (PTR),y
        clc
        adc     #1
        iny
        sta     (PTR),y
        lda     tmp0
        sec
        sbc     #64
        lsr
        lsr                             ; 0 squid, 1 crab, 2 octopus
        tax
        lda     invcolor,x
        ldy     #0
        sta     (CPTR),y
        iny
        sta     (CPTR),y
        rts

        .segment "RODATA"
txscore: .byte "SCORE", 0
txhi:    .byte "HI", 0
txwave:  .byte "WAVE", 0
txlives: .byte "LIVES", 0
txadv:   .byte "SCORE ADVANCE TABLE", 0
tx30:    .byte "= 30 POINTS", 0
tx20:    .byte "= 20 POINTS", 0
tx10:    .byte "= 10 POINTS", 0
txmyst:  .byte "? MYSTERY", 0
txplay:  .byte "PRESS ANY KEY TO PLAY", 0
txover:  .byte "GAME OVER", 0
txwaveup: .byte "WAVE CLEAR", 0

; INVADERS, five rows of 4x5 block letters separated by one blank column.
titl0:   .byte "#### #  # #  #  ##  ###  #### ###   ###", 0
titl1:   .byte " ##  ## # #  # #  # #  # #    #  # #   ", 0
titl2:   .byte " ##  # ## #  # #### #  # ###  ###   ## ", 0
titl3:   .byte " ##  #  # #  # #  # #  # #    # #    # ", 0
titl4:   .byte "#### #  #  ##  #  # ###  #### #  # ### ", 0
