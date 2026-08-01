; bombs.s — up to three invader bombs in flight, in the three arcade
; flavours: slow straight (a rolling zigzag), fast straight (the plunger),
; and the wiggly one.  Bombs are character-mode, dropped from the LOWEST live
; invader in a randomly chosen column.

        .segment "CODE"

bombstep:
        lda     bombtimer
        beq     bspawn
        dec     bombtimer
        jmp     bmove
bspawn: lda     #BOMBRATE
        sta     bombtimer
        jsr     bombspawn
bmove:  lda     #0
        sta     bslot
bml:    ldx     bslot
        lda     bactive,x
        beq     bmnext
        jsr     bombmove
bmnext: inc     bslot
        lda     bslot
        cmp     #3
        bne     bml
        rts

; bombcell: PTR/CPTR at the current cell of slot `bslot`.
bombcell:
        ldx     bslot
        lda     bcol,x
        sta     tmp1
        lda     brow,x
        tax
        ldy     tmp1
        jmp     cellptr

; bombmove: advance slot `bslot` by one row when its per-type delay expires.
bombmove:
        ldx     bslot
        lda     bdelay,x
        beq     bmgo
        dec     bdelay,x
        rts
bmgo:   ldy     btype,x
        lda     bratetab,y
        sta     bdelay,x
        jsr     bombcell
        lda     #32
        ldy     #0
        sta     (PTR),y                 ; erase where it was
        ldx     bslot
        inc     brow,x
        lda     brow,x
        cmp     #BOMBFLOOR
        bcs     bmgone
        jsr     bombcell
        ldy     #0
        lda     (PTR),y
        cmp     #SHGLYPH
        bcc     bmfree                  ; blank cell: keep falling
        cmp     #BOMBGLYPH
        bcs     bmfree                  ; a bomb or an explosion: fly past
        ldx     bslot                   ; codes 76-78: a bunker cell
        lda     brow,x
        ldy     bcol,x
        jsr     sherode
        jmp     bmgone
bmfree: ldx     bslot
        lda     brow,x
        cmp     #BASEROW
        bcc     bmdraw
        lda     basex                   ; the base occupies three columns
        lsr
        lsr
        sta     tmp0
        lda     bcol,x
        sec
        sbc     tmp0
        bcc     bmdraw
        cmp     #3
        bcs     bmdraw
        jsr     bmgone
        jmp     basehit
bmdraw: jsr     bombcell
        ldx     bslot
        ldy     btype,x
        lda     bglyph,y
        sta     tmp0
        lda     bganim,y
        beq     bmg2
        lda     brow,x
        and     #1                      ; two-frame types alternate as they fall
        clc
        adc     tmp0
        sta     tmp0
bmg2:   lda     tmp0
        ldy     #0
        sta     (PTR),y
        lda     #8|7                    ; multicolor, yellow
        sta     (CPTR),y
        rts

; bmgone: retire the slot. Its cell was already blanked by the erase above,
; so this must NOT erase again — that would blank whatever moved in.
bmgone: ldx     bslot
        lda     #0
        sta     bactive,x
        rts

; killbomb: retire slot `bslot` AND blank its glyph — for bombs killed from
; outside bombmove (shot cancellation, a death, a wave change).
killbomb:
        jsr     bombcell
        lda     #32
        ldy     #0
        sta     (PTR),y
        jmp     bmgone

killallbombs:
        lda     #0
        sta     bslot
kab:    ldx     bslot
        lda     bactive,x
        beq     kabn
        jsr     killbomb
kabn:   inc     bslot
        lda     bslot
        cmp     #3
        bne     kab
        rts

; chkbombhit: tmp0 = the shot's row, shotcol its column. A bomb and the
; player shot destroy each other on contact — checked against the bomb list
; (grid math) rather than $D01E, because bombs are characters, not sprites,
; so no sprite-sprite latch could ever see them.
chkbombhit:
        lda     shotact
        bne     cbgo
        clc
        rts
cbgo:   lda     #0
        sta     bslot
cbl:    ldx     bslot
        lda     bactive,x
        beq     cbnext
        lda     bcol,x
        cmp     shotcol
        bne     cbnext
        lda     brow,x
        sec
        sbc     tmp0
        clc
        adc     #1                      ; -1..+1 folds to 0..2
        cmp     #3
        bcs     cbnext
        jsr     killbomb
        jsr     killshot
        sec
        rts
cbnext: inc     bslot
        lda     bslot
        cmp     #3
        bne     cbl
        clc
        rts

; bombspawn: drop from the lowest live invader in a random column.
bombspawn:
        lda     nalive
        bne     bsany
        rts
bsany:  ldx     #0
bsf:    lda     bactive,x
        beq     bsgot
        inx
        cpx     #3
        bne     bsf
        rts                             ; all three slots are busy
bsgot:  stx     bslot
        jsr     randcol
        sta     tmp0                    ; a column index 0-10
        lda     #4
        sta     tmp1                    ; scan upward from the bottom row
bsr:    ldx     tmp1
        lda     rowbase,x
        clc
        adc     tmp0
        tax
        lda     alive,x
        bne     bsfound
        dec     tmp1
        bpl     bsr
        rts                             ; that column is empty this time
bsfound:
        lda     irow,x
        clc
        adc     #1
        sta     tmp2
        lda     icol,x
        clc
        adc     #1                      ; drop from the middle of the alien
        sta     tmp1
        ldx     bslot
        lda     #1
        sta     bactive,x
        lda     tmp2
        sta     brow,x
        lda     tmp1
        sta     bcol,x
        lda     bnexttype
        sta     btype,x
        tay
        lda     bratetab,y
        sta     bdelay,x
        inc     bnexttype
        lda     bnexttype
        cmp     #3
        bcc     bsdone
        lda     #0
        sta     bnexttype
bsdone: rts

; randcol: an unbiased column index 0-10 by reject-and-retry.
randcol:
        jsr     random
        and     #15
        cmp     #11
        bcs     randcol
        rts

; random: 8-bit Galois LFSR. The state must never be zero.
random: lda     seed
        lsr
        bcc     rnofb
        eor     #$b8
rnofb:  sta     seed
        rts

; ticks between row steps: slow, fast, wiggly
bratetab: .byte 4, 2, 3
; base glyph per type; bganim marks the two-frame ones
bglyph:  .byte  BOMBGLYPH, BOMBGLYPH+2, BOMBGLYPH+3
bganim:  .byte  1, 0, 1
