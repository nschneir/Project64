; hud.s -- score, hi-score, board, lives, the fruit strip, and the two
; routines that start a game and a board.
;
; The score is a 24-bit binary counter, converted to six decimal digits
; only when something changed.  Keeping it binary means addscore is one
; three-byte add rather than a per-digit carry chain, and it is what a test
; asserts on: `assert: { mem: "score", equals: ... }` reads the number, not
; its rendering.

HUDROW  = 0
HUDVAL  = 1
LIFEROW = 24

        .segment "CODE"

; addscore: add the 16-bit value in A (low) / X (high) to the score.
addscore:
        clc
        adc     score
        sta     score
        txa
        adc     score+1
        sta     score+1
        lda     #0
        adc     score+2
        sta     score+2
        lda     #1
        sta     huddirty
        lda     extradone               ; the extra life at 10 000, once
        bne     asdone
        lda     score+2
        bne     asextra
        lda     score+1
        cmp     #>10000
        bcc     asdone
        bne     asextra
        lda     score
        cmp     #<10000
        bcc     asdone
asextra:
        inc     extradone
        inc     lives
        jmp     sfxextra
asdone: rts

; drawhud: the labels, drawn once a board.
drawhud:
        lda     #1
        sta     txtcol
        SETSTR  txscore
        lda     #1
        ldy     #HUDROW
        ldx     #5
        jsr     txtat
        SETSTR  txhigh
        lda     #15
        ldy     #HUDROW
        ldx     #10
        jsr     txtat
        SETSTR  txboard
        lda     #33
        ldy     #HUDROW
        ldx     #5
        jsr     txtat
        lda     #1
        sta     huddirty
        rts

; hudtick: repaint the numbers only when something moved them.
hudtick:
        lda     huddirty
        beq     hudone
        lda     #0
        sta     huddirty
        lda     #7
        sta     txtcol
        lda     score
        sta     tmp
        lda     score+1
        sta     tmp+1
        lda     score+2
        sta     tmp+2
        lda     #1
        ldy     #HUDVAL
        jsr     cellptr
        lda     #0
        jsr     putnum6
        lda     hiscore
        sta     tmp
        lda     hiscore+1
        sta     tmp+1
        lda     hiscore+2
        sta     tmp+2
        lda     #15
        ldy     #HUDVAL
        jsr     cellptr
        lda     #0
        jsr     putnum6
        lda     board                   ; the board number, two digits
        sta     tmp
        lda     #0
        sta     tmp+1
        sta     tmp+2
        lda     #34
        ldy     #HUDVAL
        jsr     cellptr
        lda     #0
        jsr     putnum2
        jsr     drawlives
        jsr     drawfruit
hudone: rts

; putnum6: six decimal digits of the 24-bit value in tmp..tmp+2, starting
; at column A on the row PTR/CPTR already address.
putnum6:
        sta     tmp+6
        ldx     #0
        jmp     pnloop
; putnum2: the last two digits only.
putnum2:
        sta     tmp+6
        ldx     #4
pnloop: lda     #0
        sta     tmp+3
pnsub:  sec
        lda     tmp
        sbc     dectablo,x
        sta     tmp+4
        lda     tmp+1
        sbc     dectabhi,x
        sta     tmp+5
        lda     tmp+2
        sbc     dectabbk,x
        bcc     pndig
        sta     tmp+2
        lda     tmp+4
        sta     tmp
        lda     tmp+5
        sta     tmp+1
        inc     tmp+3
        jmp     pnsub
pndig:  lda     tmp+3
        clc
        adc     #48                     ; screen code '0' is 48, like ASCII
        ldy     tmp+6
        sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        inc     tmp+6
        inx
        cpx     #6
        bne     pnloop
        rts

; drawlives: one little muncher per life still in hand.
drawlives:
        lda     #2
        ldy     #LIFEROW
        jsr     cellptr
        ldy     #0
dl1:    lda     #32
        cpy     lives
        bcs     dl2
        lda     #GL_LIFE
dl2:    sta     (PTR),y
        lda     #8|7
        sta     (CPTR),y
        iny
        cpy     #5
        bne     dl1
        rts

; drawfruit: the strip of fruit already collected, newest on the left.
drawfruit:
        lda     #32
        ldy     #LIFEROW
        jsr     cellptr
        ldy     #0
df1:    lda     fruitwon,y
        beq     df2
        clc
        adc     #GL_FRUIT-1
        .byte   $2C
df2:    lda     #32
        sta     (PTR),y
        lda     fruitwon,y
        beq     df3
        tax
        dex
        lda     fruitcol,x
        ora     #8
        .byte   $2C
df3:    lda     #0
        sta     (CPTR),y
        iny
        cpy     #7
        bne     df1
        rts

; ---- starting a game and a board ----------------------------------------
newgame:
        lda     #0
        sta     score
        sta     score+1
        sta     score+2
        sta     extradone
        sta     frcount
        ldx     #7
:       sta     fruitwon,x
        dex
        bpl     :-
        lda     #3
        sta     lives
        lda     #1
        sta     board
        jsr     newboard
        lda     #ST_READY
        sta     gstate
        lda     #1
        sta     stinit
        rts

newboard:
        lda     board                   ; speed group: 1, 2-4, 5-20, 21+
        cmp     #2
        bcc     nbg0
        cmp     #5
        bcc     nbg1
        cmp     #21
        bcc     nbg2
        lda     #3
        .byte   $2C
nbg2:   lda     #2
        .byte   $2C
nbg1:   lda     #1
        .byte   $2C
nbg0:   lda     #0
        sta     spdgroup
        jsr     setmaze
        jsr     setfruit
        jsr     clrscreen
        jsr     drawmaze
        jsr     drawhud
        lda     #0
        sta     dotseaten
        sta     frcount
        sta     fractive
        sta     elroy
        jsr     resetactors
        jmp     musstop

        .segment "RODATA"
txscore: .byte  "SCORE"
txhigh:  .byte  "HIGH SCORE"
txboard: .byte  "BOARD"
txready: .byte  "READY! "
txblank: .byte  "       "
txover:  .byte  "GAME OVER"

; 100000, 10000, 1000, 100, 10, 1 as 24-bit constants
dectablo: .byte <100000, <10000, <1000, <100, <10, <1
dectabhi: .byte >100000, >10000, >1000, >100, >10, >1
dectabbk: .byte ^100000, ^10000, ^1000, ^100, ^10, ^1

        .segment "CODE"
