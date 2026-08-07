; fruit.s -- the bonus fruit that travels.
;
; Not a prize parked under the ghost house: it enters through a tunnel
; mouth, is steered around a route that laps the house above and below, and
; leaves through the other tunnel if nobody eats it.  It reuses the ghosts'
; direction chooser, pointed at a waypoint instead of at Ms. Muncher, which
; is why it corners like something that lives in the maze.

        .segment "CODE"

; fruittick: spawn, expiry, and the "she ate it" test.
fruittick:
        lda     fractive
        bne     ftalive
        lda     frcount                 ; two visits a board
        cmp     #2
        bcs     ftdone2
        tax
        lda     dotseaten
        cmp     fruitdots,x
        bcc     ftdone2
        jmp     fruitspawn
ftalive:
        lda     frlife                  ; a hard stop, in case the route jams
        ora     frlife+1
        beq     ftgone
        lda     frlife
        bne     :+
        dec     frlife+1
:       dec     frlife
        lda     axhi                    ; eaten?
        lsr     a
        lsr     a
        lsr     a
        sta     tmp
        lda     axhi+A_FRUIT
        lsr     a
        lsr     a
        lsr     a
        cmp     tmp
        bne     ftdone2
        lda     ayhi
        lsr     a
        lsr     a
        lsr     a
        sta     tmp
        lda     ayhi+A_FRUIT
        lsr     a
        lsr     a
        lsr     a
        cmp     tmp
        bne     ftdone2
        ldx     frkind                  ; 100 200 500 700 1000 2000 5000
        txa
        asl     a
        tay
        lda     fruitval,y
        pha
        lda     fruitval+1,y
        tax
        pla
        jsr     addscore
        jsr     wonfruit
        jsr     sfxfruit
ftgone: lda     #0
        sta     fractive
ftdone2:
        rts

fruitspawn:
        inc     frcount
        lda     #1
        sta     fractive
        lda     #0
        sta     frwp
        sta     afrac+A_FRUIT
        lda     #<900                   ; fifteen seconds is plenty of route
        sta     frlife
        lda     #>900
        sta     frlife+1
        jsr     rnd                     ; either tunnel mouth, at random
        and     #1
        beq     fsleft
        lda     #(MW-1)*8+4
        sta     axhi+A_FRUIT
        lda     #DIR_LEFT
        jmp     fsdir
fsleft: lda     #4
        sta     axhi+A_FRUIT
        lda     #DIR_RIGHT
fsdir:  sta     adir+A_FRUIT
        sta     awant+A_FRUIT
        lda     #11*8+4                 ; the tunnel row
        sta     ayhi+A_FRUIT
        rts

; fruitcentre: steer toward the current waypoint; leaving by a tunnel ends
; the visit.
fruitcentre:
        lda     fractive
        beq     fcdone
        ldx     frwp
        lda     froutex,x
        cmp     tcol
        bne     fcgo
        lda     froutey,x
        cmp     trow
        bne     fcgo
        inc     frwp
        ldx     frwp
        cpx     #NROUTE
        bcc     fcgo
        dex                             ; sit on the last waypoint: the exit
        stx     frwp
fcgo:   lda     tcol
        bne     fcsel
        lda     adir+A_FRUIT
        cmp     #DIR_LEFT
        bne     fcsel
        lda     #0
        sta     fractive
        rts
fcsel:  ldx     frwp
        lda     froutex,x
        sta     tgtx
        lda     froutey,x
        sta     tgty
        jmp     gchoose
fcdone: rts

; wonfruit: push this fruit onto the strip along the bottom.
wonfruit:
        ldx     #6
wfsh:    lda     fruitwon,x
        sta     fruitwon+1,x
        dex
        bpl     wfsh
        lda     frkind
        clc
        adc     #1                      ; 0 means "no pip here"
        sta     fruitwon
        lda     #1
        sta     huddirty
        rts

; setfruit: which fruit this board shows.  Boards 1-7 walk the ladder; from
; board 8 each board draws one at random, as the arcade does.
setfruit:
        lda     board
        cmp     #8
        bcs     sfrand
        sec
        sbc     #1
        jmp     sfset
sfrand: jsr     rnd
        and     #7
        cmp     #7
        bcc     sfset
        lda     #6
sfset:  sta     frkind
        jmp     setfruitshape

        .segment "RODATA"

; the route: under the house, over it, under it again, then out of the left
; tunnel.  Every one of these tiles is a corridor in all four mazes.
NROUTE  = 4
froutex: .byte  13, 13, 13, 0
froutey: .byte  13, 8, 13, 11
fruitdots: .byte 70, 170
fruitval: .word 100, 200, 500, 700, 1000, 2000, 5000

        .segment "CODE"
