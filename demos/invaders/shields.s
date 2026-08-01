; shields.s — four bunkers that erode piecemeal under fire from both sides.
;
; Each bunker is 4 cells wide by 2 rows, and every cell carries its own damage
; state: 3 solid -> 2 cracked -> 1 crumbling -> 0 gone.  The glyphs are three
; progressively holier multicolor characters, so a bunker crumbles instead of
; vanishing.  Both the player's shot and invader bombs call sherode; nothing
; else may touch shdmg except shzero, which the marching formation uses when
; it grinds a bunker away.

        .segment "CODE"

shieldinit:
        ldx     #0
sii:    lda     #3
        sta     shdmg,x
        inx
        cpx     #32
        bne     sii
        ; cut the arch out of each bunker's bottom edge (cells 5 and 6 of the
        ; eight) so it reads as a bunker rather than a green brick
        ldx     #0
sia:    lda     #0
        sta     shdmg+5,x
        sta     shdmg+6,x
        txa
        clc
        adc     #8
        tax
        cpx     #32
        bne     sia
        ldx     #0
sid:    jsr     shdrawone
        inx
        cpx     #32
        bne     sid
        rts

; shindex: A = row, Y = column -> X = shdmg index, carry set if this cell
; belongs to a bunker at all.
shindex:
        cmp     #SHROW0
        beq     shi0
        cmp     #SHROW1
        beq     shi1
        clc
        rts
shi0:   lda     #0
        beq     shifind
shi1:   lda     #4
shifind:
        sta     tmp0
        ldx     #0
shil:   tya
        sec
        sbc     shcolbase,x
        bcc     shinx
        cmp     #4
        bcs     shinx
        sta     tmp1
        txa
        asl
        asl
        asl                             ; bunker * 8
        clc
        adc     tmp0                    ; + row half
        adc     tmp1                    ; + column within the bunker
        tax
        sec
        rts
shinx:  inx
        cpx     #4
        bne     shil
        clc
        rts

; sherode: A = row, Y = column. One damage step. Carry set if a live shield
; cell absorbed the hit (a hole in the bunker returns carry clear, so shots
; and bombs fly straight through it — which is exactly what the arcade did).
sherode:
        jsr     shindex
        bcc     seno
        lda     shdmg,x
        beq     senone
        sec
        sbc     #1
        sta     shdmg,x
        jsr     shdrawone
        sec
        rts
senone: clc
seno:   rts

; shzero: A = row, Y = column. Mark the cell destroyed without redrawing —
; used when an invader has already drawn itself over the bunker.
shzero: jsr     shindex
        bcc     szno
        lda     #0
        sta     shdmg,x
szno:   rts

; shdrawone: X = shdmg index. Paints that one cell from its damage state.
shdrawone:
        stx     tmp2
        txa
        lsr
        lsr
        lsr                             ; which bunker
        tax
        lda     shcolbase,x
        sta     tmp0
        lda     tmp2
        and     #7
        cmp     #4
        bcc     s1r0
        sbc     #4
        ldx     #SHROW1
        bne     s1go                    ; SHROW1 is nonzero, so always taken
s1r0:   ldx     #SHROW0
s1go:   clc
        adc     tmp0
        tay
        jsr     cellptr
        ldx     tmp2
        lda     shdmg,x
        beq     s1blank
        sta     tmp1
        lda     #3
        sec
        sbc     tmp1                    ; 3 solid -> glyph 76, 1 -> glyph 78
        clc
        adc     #SHGLYPH
        ldy     #0
        sta     (PTR),y
        lda     #8|5                    ; multicolor, green
        sta     (CPTR),y
        ldx     tmp2
        rts
s1blank:
        lda     #32
        ldy     #0
        sta     (PTR),y
        ldx     tmp2
        rts

shcolbase: .byte 4, 13, 22, 31
