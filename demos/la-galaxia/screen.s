; screen.s -- the screen matrix: row tables, the cell pointer, text without
; CHROUT, and the cabinet bezel.
;
; No KERNAL routine is called anywhere in this program, so text is poked as
; screen codes.  The bezel is drawn as charset cells because $D020 cannot do
; it: the border is a fixed width and cannot mask screen columns.

        .segment "ENGINE"

; ---- row base tables ------------------------------------------------------
rowlo:  .repeat PFROWS, i
        .byte   <(SCREEN + 40*i)
        .endrepeat
rowhi:  .repeat PFROWS, i
        .byte   >(SCREEN + 40*i)
        .endrepeat
crowhi: .repeat PFROWS, i
        .byte   >(COLRAM + 40*i)
        .endrepeat

; ---- cellptr -- point PTR/CPTR at (scrrow, scrcol) -----------------------
; The carry out of `rowlo + scrcol` belongs to BOTH high bytes, so it has to
; be kept in Y: `lda rowhi,x / adc #0` consumes it, and the colour pointer's
; `adc #0` then sees a clear carry.  That was a live bug -- every cell whose
; row base plus column crossed a page (row 19 from column 8 on, row 12 from
; column 32, row 6 from column 16) had its colour written a page low, so the
; character appeared in black on black.
cellptr:
        ldx     scrrow
        lda     rowlo,x
        clc
        adc     scrcol
        sta     PTR
        sta     CPTR
        ldy     #0
        bcc     :+
        ldy     #1
:       tya
        clc
        adc     rowhi,x
        sta     PTR+1
        tya
        clc
        adc     crowhi,x
        sta     CPTR+1
        rts

; ---- putcell -- A = screen code, txtcol = colour, at (scrrow, scrcol) ----
putcell:
        pha
        jsr     cellptr
        pla
        ldy     #0
        sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        inc     cells_drawn
        rts

; ---- txtat -- draw the zero-terminated string at TXT ---------------------
; scrrow/scrcol/txtcol set by the caller.  Screen codes, not PETSCII.
txtat:  jsr     cellptr
        ldy     #0
txt1:   lda     (TXT),y
        beq     txt9
        sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        iny
        bne     txt1
txt9:   rts

; ---- prstr -- A/X = string address, then txtat ---------------------------
prstr:  sta     TXT
        stx     TXT+1
        jmp     txtat

; ---- clrscreen -- blank the whole matrix ---------------------------------
clrscreen:
        ldx     #0
        lda     #32
cls1:   sta     SCREEN,x
        sta     SCREEN+$100,x
        sta     SCREEN+$200,x
        sta     SCREEN+$2E8,x
        inx
        bne     cls1
        ldx     #0
        lda     #COL_BLACK
cls2:   sta     COLRAM,x
        sta     COLRAM+$100,x
        sta     COLRAM+$200,x
        sta     COLRAM+$2E8,x
        inx
        bne     cls2
        rts

; ---- clrplayfield -- blank columns 8-31 only -----------------------------
clrplay:
        lda     #0
        sta     scrrow
cpf1:   lda     #PFCOL
        sta     scrcol
        jsr     cellptr
        ldy     #0
        lda     #32
cpf2:   sta     (PTR),y
        iny
        cpy     #PFW
        bne     cpf2
        inc     scrrow
        lda     scrrow
        cmp     #PFROWS
        bne     cpf1
        rts

; --------------------------------------------------------------------------
; The screen rebuild, spread over frames.
;
; Clearing the matrix, drawing the bezel and laying the starfield is roughly
; 60,000 cycles -- three and a half NTSC frames -- and doing it inside one
; state-init tick put that tick's $D020 band round the whole screen and out
; the bottom.  It is a step machine instead: one frame to clear each half of
; the matrix, one for each half of the bezel, and three playfield rows of
; stars a frame.  ST_ANNOUNCE holds its banner for 120 frames and the title
; screen has nothing else to do, so the build is finished long before
; anything moves.  screenstep returns carry set when there is nothing left.
; --------------------------------------------------------------------------
SB_STARROWS = 3
SB_STARS    = 4
SB_DONE     = SB_STARS + (PFROWS + SB_STARROWS - 1) / SB_STARROWS

screenstart:
        lda     #0
        sta     sbstep
        rts

screenstep:
        lda     sbstep
        cmp     #SB_DONE
        bcs     ssfin
        inc     sbstep
        cmp     #0
        beq     ssclr0
        cmp     #1
        beq     ssclr1
        cmp     #2
        beq     ssbez0
        cmp     #3
        beq     ssbez1
        sec                             ; stars: three rows a step
        sbc     #SB_STARS
        sta     tmp0
        asl     a
        adc     tmp0                    ; *3 (carry is clear: the value is small)
        sta     scrrow
        lda     #SB_STARROWS
        sta     tmp5
ssst1:  lda     scrrow
        cmp     #PFROWS
        bcs     ssok
        jsr     starrow
        inc     scrrow
        dec     tmp5
        bne     ssst1
ssok:   clc
        rts
ssfin:  sec
        rts

ssclr0: ldx     #0
        lda     #32
:       sta     SCREEN,x
        sta     SCREEN+$100,x
        inx
        bne     :-
        lda     #COL_BLACK
:       sta     COLRAM,x
        sta     COLRAM+$100,x
        inx
        bne     :-
        clc
        rts
ssclr1: ldx     #0
        lda     #32
:       sta     SCREEN+$200,x
        sta     SCREEN+$2E8,x
        inx
        bne     :-
        lda     #COL_BLACK
:       sta     COLRAM+$200,x
        sta     COLRAM+$2E8,x
        inx
        bne     :-
        clc
        rts
ssbez0: lda     #0
        sta     scrrow
        ldx     #13
        bne     ssbez
ssbez1: lda     #13
        sta     scrrow
        ldx     #PFROWS-13
ssbez:  stx     tmp5
ssbz1:  jsr     bezelrow
        inc     scrrow
        dec     tmp5
        bne     ssbz1
        lda     #0
        sta     cells_drawn
        clc
        rts

; screenbuild -- run the whole rebuild here and now.  Only startup uses it,
; where there is no frame to overrun yet.
screenbuild:
        jsr     screenstart
:       jsr     screenstep
        bcc     :-
        rts

; GLY_* -- the game glyphs, screen codes 64-99 (see tools/glyphs.txt).
GLY_BLOCK0 = 64                 ; first enemy block quadrant
GLY_STAR0  = 88
GLY_STAR1  = 89
GLY_STAR2  = 90
GLY_MIS0   = 91
GLY_MIS1   = 92
GLY_BUL0   = 93
GLY_BUL1   = 94
GLY_RAIL   = 95
GLY_GRILLE = 96
GLY_LIFE   = 97
GLY_BRACKET = 98

bezelrow:
        ; the rail sits immediately beside the playfield on both sides
        lda     #PFCOL-1
        sta     scrcol
        lda     #GLY_RAIL
        ldx     #COL_BLUE
        stx     txtcol
        jsr     putcell
        lda     #PFCOL+PFW
        sta     scrcol
        lda     #GLY_RAIL
        jsr     putcell
        ; a grille panel one column further out, in dark grey
        lda     #PFCOL-2
        sta     scrcol
        lda     #COL_DKGREY
        sta     txtcol
        lda     #GLY_GRILLE
        jsr     putcell
        lda     #PFCOL+PFW+1
        sta     scrcol
        lda     #GLY_GRILLE
        jmp     putcell

; --------------------------------------------------------------------------
; The playfield's background shadow.
;
; A missile or a bullet is a character cell, so drawing it destroys whatever
; was underneath -- and underneath is a starfield.  bgbuf/bgcol hold what the
; window shows with no shot on it (stars, and the settled formation blocks),
; so a shot can put back exactly what it covered.  Everything that paints the
; *world* goes through pfput and so keeps the shadow true; only shots use
; pfshot, and only shots call pfrestore.
; --------------------------------------------------------------------------
BGP     = $28
BGC     = $2A

bgrowlo: .repeat PFROWS, i
        .byte   <(bgbuf + 40*i)
        .endrepeat
bgrowhi: .repeat PFROWS, i
        .byte   >(bgbuf + 40*i)
        .endrepeat
bgcrowlo: .repeat PFROWS, i
        .byte   <(bgcol + 40*i)
        .endrepeat
bgcrowhi: .repeat PFROWS, i
        .byte   >(bgcol + 40*i)
        .endrepeat

; bgcol needs its OWN low-byte table.  PTR and CPTR can share rowlo because
; $0400 and $D800 differ only in the high byte, but bgbuf and bgcol are two
; arrays at unrelated addresses: building BGC from bgrowlo put every colour
; shadow write 24 bytes past where it belonged, and at the bottom of the
; screen that ran off the end of bgcol and straight through mis_on, mis_col,
; mis_y and mis_prow -- so drawing the starfield left four phantom missiles
; in flight before the first frame of play.
pfptr:  jsr     cellptr
        ldx     scrrow
        lda     bgrowlo,x
        clc
        adc     scrcol
        sta     BGP
        lda     bgrowhi,x
        adc     #0
        sta     BGP+1
        lda     bgcrowlo,x
        clc
        adc     scrcol
        sta     BGC
        lda     bgcrowhi,x
        adc     #0
        sta     BGC+1
        rts

; pfput -- A = screen code, txtcol = colour: to the screen and the shadow.
pfput:  pha
        jsr     pfptr
        pla
        ldy     #0
        sta     (PTR),y
        sta     (BGP),y
        lda     txtcol
        sta     (CPTR),y
        sta     (BGC),y
        inc     cells_drawn
        rts

; pfshot -- A = screen code, txtcol = colour: screen only, shadow untouched.
pfshot: pha
        jsr     cellptr
        pla
        ldy     #0
        sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        inc     cells_drawn
        rts

; pfrestore -- put back whatever the shadow says belongs at (scrrow, scrcol).
pfrestore:
        jsr     pfptr
        ldy     #0
        lda     (BGP),y
        sta     (PTR),y
        lda     (BGC),y
        sta     (CPTR),y
        inc     cells_drawn
        rts
