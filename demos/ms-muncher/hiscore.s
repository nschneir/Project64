; hiscore.s -- the top five, and typing your initials into it.
;
; The table lives in RAM and survives every game in the session; there is no
; disk write, which is the honest thing for a .prg that may be running off a
; write-protected image.
;
; Initials are read from the keyboard buffer at $0277 directly -- decoded
; PETSCII, no ROM call.  `c64 key type ABC` fills exactly that buffer, so
; the entry screen is drivable from a test.

        .segment "CODE"

hiscoreinit:
        ldx     #0
hi1:    lda     definames,x
        sta     hinames,x
        inx
        cpx     #15
        bne     hi1
        ldx     #0
hi2:    lda     defscores,x
        sta     hitab,x
        inx
        cpx     #15
        bne     hi2
        lda     hitab
        sta     hiscore
        lda     hitab+1
        sta     hiscore+1
        lda     hitab+2
        sta     hiscore+2
        rts

; hientry: does this game's score make the table?  entryslot = -1 if not.
hientry:
        lda     #$FF
        sta     entryslot
        ldx     #4
he1:    stx     tmp+3
        txa                             ; slot X starts at 3*X
        asl     a
        clc
        adc     tmp+3
        tay
        lda     score+2
        cmp     hitab+2,y
        bcc     hedone
        bne     hefits
        lda     score+1
        cmp     hitab+1,y
        bcc     hedone
        bne     hefits
        lda     score
        cmp     hitab,y
        bcc     hedone
        beq     hedone
hefits: stx     entryslot
        dex
        bpl     he1
hedone: lda     entryslot
        bmi     hend
        ldx     #3                      ; shift the losers down one slot
hesh:   cpx     entryslot
        bcc     heins
        stx     tmp+3
        txa
        asl     a
        clc
        adc     tmp+3
        tay
        lda     hitab,y
        sta     hitab+3,y
        lda     hitab+1,y
        sta     hitab+4,y
        lda     hitab+2,y
        sta     hitab+5,y
        lda     hinames,y
        sta     hinames+3,y
        lda     hinames+1,y
        sta     hinames+4,y
        lda     hinames+2,y
        sta     hinames+5,y
        ldx     tmp+3
        dex
        bpl     hesh
heins:  lda     entryslot
        asl     a
        clc
        adc     entryslot
        tay
        lda     score
        sta     hitab,y
        lda     score+1
        sta     hitab+1,y
        lda     score+2
        sta     hitab+2,y
        lda     #32                     ; three blanks to type over
        sta     hinames,y
        sta     hinames+1,y
        sta     hinames+2,y
        lda     hitab                   ; the displayed hi-score follows
        sta     hiscore
        lda     hitab+1
        sta     hiscore+1
        lda     hitab+2
        sta     hiscore+2
hend:   rts

; ---- state: typing your initials ----------------------------------------
stentry:
        lda     stinit
        beq     se2
        lda     #0
        sta     stinit
        sta     entrypos
        sta     sprena
        sta     $C6                     ; flush any type-ahead
        jsr     clrscreen
        lda     #7
        sta     txtcol
        SETSTR  txnew
        lda     #7
        ldy     #8
        ldx     #26
        jsr     txtat
        lda     #1
        sta     txtcol
        SETSTR  txtype
        lda     #10
        ldy     #16
        ldx     #19
        jsr     txtat
se2:    jsr     drawentry
        jsr     keyget
        beq     sedone
        cmp     #$0D                    ; RETURN or SPACE saves early
        beq     sesave
        cmp     #$20
        beq     sesave
        cmp     #48                     ; digits
        bcc     sedone
        cmp     #58
        bcc     seok
        cmp     #65                     ; letters
        bcc     sedone
        cmp     #91
        bcs     sedone
seok:   lda     entryslot
        asl     a
        clc
        adc     entryslot
        clc
        adc     entrypos
        tay
        lda     entrychar
        cmp     #64
        bcc     :+
        sec
        sbc     #64                     ; letters -> screen codes
:       sta     hinames,y
        inc     entrypos
        lda     entrypos
        cmp     #3
        bcc     sedone
sesave: lda     #ST_TITLE
        sta     gstate
        lda     #1
        sta     stinit
sedone: jmp     tickend

; drawentry: the three initials, with a cursor under the next one.
drawentry:
        lda     #14
        ldy     #12
        jsr     cellptr
        lda     entryslot
        asl     a
        clc
        adc     entryslot
        tax
        ldy     #0
de1:    lda     hinames,x
        sta     (PTR),y
        lda     #7
        sta     (CPTR),y
        inx
        iny
        cpy     #3
        bne     de1
        lda     #14
        ldy     #13
        jsr     cellptr
        ldy     #0
de2:    lda     #32
        cpy     entrypos
        bne     :+
        lda     frames
        and     #16
        beq     :+
        lda     #100                    ; a horizontal-bar cursor
:       sta     (PTR),y
        lda     #1
        sta     (CPTR),y
        iny
        cpy     #3
        bne     de2
        rts

; keyget: next PETSCII character out of the keyboard buffer, or 0.  Z=1 when
; the buffer was empty.  No ROM call: GETIN would be the same read plus a
; JSR into the KERNAL.
keyget: lda     $C6
        beq     kgnone
        lda     $0277
        sta     entrychar
        ldx     #0
kg1:    lda     $0278,x
        sta     $0277,x
        inx
        cpx     #9
        bne     kg1
        dec     $C6
        lda     entrychar
        rts
kgnone: lda     #0
        rts

        .segment "RODATA"
txnew:  .byte   "YOUR SCORE MAKES THE TABLE"
txtype: .byte   "TYPE THREE INITIALS"
definames:
        .byte   1, 2, 3                 ; screen codes: ABC, DEF, ...
        .byte   4, 5, 6
        .byte   7, 8, 9
        .byte   10, 11, 12
        .byte   13, 14, 15
defscores:
        .byte   <20000, >20000, ^20000
        .byte   <15000, >15000, ^15000
        .byte   <10000, >10000, ^10000
        .byte   <5000, >5000, ^5000
        .byte   <2500, >2500, ^2500

        .segment "CODE"
