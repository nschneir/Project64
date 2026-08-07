; screen.s -- row address tables, the cell pointer, and text without CHROUT.
;
; No ROM output routine is ever called: CHROUT costs cycles the frame does
; not have and scrolls the screen the moment something reaches the last
; column.  Text is poked as screen codes through the same row tables the
; maze drawing uses.

        .segment "RODATA"

; SCREEN + 40*row, one entry per text row.  Colour RAM shares the low byte
; and adds $D4 to the high byte, which is why only one pair of tables exists.
srowlo: .repeat 25, I
        .byte   <(SCREEN + I*40)
        .endrepeat
srowhi: .repeat 25, I
        .byte   >(SCREEN + I*40)
        .endrepeat

; TILES + 28*row, one entry per playfield row.
trowlo: .repeat MH, I
        .byte   <(TILES + I*MW)
        .endrepeat
trowhi: .repeat MH, I
        .byte   >(TILES + I*MW)
        .endrepeat

        .segment "CODE"

; cellptr: PTR -> SCREEN cell (col A, row Y), CPTR -> the matching colour cell.
cellptr:
        clc
        adc     srowlo,y
        sta     PTR
        sta     CPTR
        lda     srowhi,y
        adc     #0
        sta     PTR+1
        clc
        adc     #$D4
        sta     CPTR+1
        rts

; tileptr: TP -> TILES byte for playfield (col X, row Y).  Y survives; the
; caller indexes with the column, so this leaves TP pointing at the row.
tileptr:
        lda     trowlo,y
        sta     TP
        lda     trowhi,y
        sta     TP+1
        rts

; tilerd: A = the tile at (ncol, nrow).  Out-of-range rows read as wall so
; the tiler and the movement code never fall off the top or bottom.
tilerd:
        ldy     nrow
        cpy     #MH
        bcs     trwall
        jsr     tileptr
        ldy     ncol
        cpy     #MW
        bcs     trwall
        lda     (TP),y
        rts
trwall: lda     #T_WALL
        rts

; tilewr: store A at (ncol, nrow).
tilewr:
        pha
        ldy     nrow
        jsr     tileptr
        ldy     ncol
        pla
        sta     (TP),y
        rts

; clrscreen: blank all 1000 cells and set colour RAM to white.
clrscreen:
        ldx     #0
cs1:    lda     #32
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
        bne     cs1
        rts

; txtat: draw X characters of the string at SP to column A, row Y, in the
; colour in txtcol.  Letters arrive as ASCII and are folded to screen codes
; by subtracting 64; digits, space and punctuation already match.
txtat:  jsr     cellptr
        stx     tmp
        ldy     #0
tx1:    cpy     tmp
        beq     txdone
        lda     (SP),y
        cmp     #64
        bcc     tx2
        sbc     #64
tx2:    sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        iny
        bne     tx1
txdone: rts
