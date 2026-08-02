; title.s — the two full-screen states: the attract screen and the game-over
; panel.
;
; The title letters are 4x5 cells of ROM screen code 160 (reverse space — a
; solid block), one colour per letter.  Nothing here uses the custom charset
; except the little snake under the name, which is exactly the glyphs the
; game plays with.

        .segment "CODE"

; drawtitle — SNAKE in blocks, a snake and an apple, the instructions and the
; standing high score.
drawtitle:
        lda     #0
        sta     clrcol
        jsr     clrscr
        lda     #0
        sta     dtidx
dtloop: ldx     dtidx
        lda     titlecol,x
        sta     pcolor
        txa                     ; column = 8 + index*5
        asl
        asl
        clc
        adc     dtidx
        clc
        adc     #8
        tax
        lda     dtidx
        jsr     bigchar
        inc     dtidx
        lda     dtidx
        cmp     #5
        bne     dtloop

        lda     #10             ; a six-segment snake reaching for an apple
        ldy     #14
        jsr     plotaddr
        lda     #5
        sta     pcolor
        ldy     #0
dtsnak: lda     #BODY
        jsr     putcell
        iny
        cpy     #6
        bne     dtsnak
        lda     #HEADRT            ; head facing right, column 20
        jsr     putcell
        lda     #FOODCOL
        sta     pcolor
        ldy     #9              ; column 23
        lda     #FOODCODE
        jsr     putcell

        lda     #13
        sta     pcolor
        lda     #14
        ldy     #9
        jsr     plotaddr
        ldx     #<mspress
        ldy     #>mspress
        jsr     putstr

        lda     #14
        sta     pcolor
        lda     #17
        ldy     #12
        jsr     plotaddr
        ldx     #<mssteer
        ldy     #>mssteer
        jsr     putstr

        lda     #7
        sta     pcolor
        lda     #19
        ldy     #12
        jsr     plotaddr
        ldx     #<mshiscr
        ldy     #>mshiscr
        jsr     putstr
        lda     #19
        ldy     #23
        jsr     plotaddr
        lda     #1
        sta     pcolor
        ldx     #<hidig
        ldy     #>hidig
        lda     #4
        jsr     putdig

        lda     #12
        sta     pcolor
        lda     #22
        ldy     #2
        jsr     plotaddr
        ldx     #<msmade
        ldy     #>msmade
        jsr     putstr
        rts

; bigchar — draw one 4x5 title letter.  In: A = letter index 0-4, X = left
; column; `pcolor` = its colour.  Rows 3-7.
bigchar:
        sta     bcidx
        stx     bccol
        lda     #0
        sta     bcrow
bcrowl: lda     bcidx
        asl
        asl
        clc
        adc     bcidx           ; index*5 = the letter's first font row
        clc
        adc     bcrow
        tax
        lda     bigfont,x
        sta     bcbits
        lda     bcrow
        clc
        adc     #3
        ldy     bccol
        jsr     plotaddr
        ldy     #0
bccoll: lda     bcbits
        and     bcmask,y
        beq     bcskip
        lda     #BLOCK            ; ROM reverse-space: a solid block
        jsr     putcell
bcskip: iny
        cpy     #4
        bne     bccoll
        inc     bcrow
        lda     bcrow
        cmp     #5
        bne     bcrowl
        rts

; drawover — a ten-row panel over the middle of the dead playfield: rows
; 8-17, columns 4-35.  The longest line it carries is 25 characters, and the
; panel is 32 wide so that line has real margin on both sides rather than
; running into its own border.  The field and the snake that died stay
; visible around it, which is what makes the frame worth capturing.
;
; PPWIDE = the interior width; the loops below all run 1..PPWIDE+1.
PPWIDE  = 30

drawover:
        lda     #10
        sta     pcolor
        lda     #8
        ldy     #4
        jsr     plotaddr
        ldy     #0
        lda     #BORDTL
        jsr     putcell
        ldy     #1
dotop:  lda     #BORDH
        jsr     putcell
        iny
        cpy     #PPWIDE+1
        bne     dotop
        lda     #BORDTR
        jsr     putcell
        lda     #17
        ldy     #4
        jsr     plotaddr
        ldy     #0
        lda     #BORDBL
        jsr     putcell
        ldy     #1
dobot:  lda     #BORDH
        jsr     putcell
        iny
        cpy     #PPWIDE+1
        bne     dobot
        lda     #BORDBR
        jsr     putcell

        ldx     #9              ; interior rows: side pieces, blank between
dorow:  txa
        ldy     #4
        jsr     plotaddr
        lda     #10
        sta     pcolor
        ldy     #0
        lda     #BORDV
        jsr     putcell
        ldy     #PPWIDE+1
        lda     #BORDV
        jsr     putcell
        lda     #0
        sta     pcolor
        ldy     #1
doclr:  lda     #BLANK
        jsr     putcell
        iny
        cpy     #PPWIDE+1
        bne     doclr
        inx
        cpx     #17
        bne     dorow

        ; the heading is a full-width reverse bar: solid red across the panel
        ; with GAME OVER knocked out of it in the background colour
        lda     #2
        sta     pcolor
        lda     #10
        ldy     #5
        jsr     plotaddr
        ldy     #0
dobar:  lda     #BLOCK
        jsr     putcell
        iny
        cpy     #PPWIDE
        bne     dobar
        lda     #10
        ldy     #15
        jsr     plotaddr
        lda     #REVERSE
        sta     pcodeor
        ldx     #<msover
        ldy     #>msover
        jsr     putstr
        lda     #0
        sta     pcodeor

        lda     #14
        sta     pcolor
        lda     #12
        ldy     #15
        jsr     plotaddr
        ldx     #<msscore
        ldy     #>msscore
        jsr     putstr
        lda     #12
        ldy     #21
        jsr     plotaddr
        lda     #1
        sta     pcolor
        ldx     #<scdig
        ldy     #>scdig
        lda     #4
        jsr     putdig

        lda     #14
        sta     pcolor
        lda     #13
        ldy     #15
        jsr     plotaddr
        ldx     #<mshi
        ldy     #>mshi
        jsr     putstr
        lda     #13
        ldy     #21
        jsr     plotaddr
        lda     #1
        sta     pcolor
        ldx     #<hidig
        ldy     #>hidig
        lda     #4
        jsr     putdig

        lda     newhi
        beq     donewhi
        lda     #7
        sta     pcolor
        lda     #14
        ldy     #13
        jsr     plotaddr
        ldx     #<msnewhi
        ldy     #>msnewhi
        jsr     putstr
donewhi:
        lda     #13
        sta     pcolor
        lda     #16
        ldy     #7
        jsr     plotaddr
        ldx     #<msagain
        ldy     #>msagain
        jsr     putstr
        rts
