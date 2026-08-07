; maze.s -- the four playfields: unpack, auto-tile, draw, and eat.
;
; mazes.inc stores only the left 14 columns of each row, two tile codes to a
; byte, because every layout is left-right symmetric.  Nothing stores wall
; *art*: a wall cell's glyph is picked from which of its four neighbours are
; also wall, so one set of sixteen glyphs draws all four mazes and any maze
; you author next is drawn correctly without touching this file.

        .segment "CODE"

; loadmaze: unpack maze A into the live tile map at $C000.
loadmaze:
        tax
        clc                             ; the packed rows moved with the art
        lda     HI(mazeptr_lo),x
        adc     #<(HIGHRAM-highstart)
        sta     SP
        lda     HI(mazeptr_hi),x
        adc     #>(HIGHRAM-highstart)
        sta     SP+1
        lda     HI(mazedots),x
        sta     dotsleft
        lda     mzwallhi,x
        sta     wallhi
        sta     $D022
        lda     mzwallcol,x
        sta     wallcol
        lda     #0
        sta     nrow
lmrow:  ldy     #0                      ; unpack seven bytes into 14 tiles
        ldx     #0
lmnib:  lda     (SP),y
        pha
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     rowbuf,x
        inx
        pla
        and     #$0F
        sta     rowbuf,x
        inx
        iny
        cpy     #7
        bne     lmnib
        ldx     #0                      ; mirror into columns 14-27
lmmir:  stx     tmp
        lda     #MW-1
        sec
        sbc     tmp
        tay
        lda     rowbuf,x
        sta     rowbuf,y
        inx
        cpx     #MW/2
        bne     lmmir
        ldy     nrow                    ; and into the live map
        jsr     tileptr
        ldy     #MW-1
lmsto:  lda     rowbuf,y
        sta     (TP),y
        dey
        bpl     lmsto
        clc                             ; next packed row
        lda     SP
        adc     #7
        sta     SP
        bcc     :+
        inc     SP+1
:       inc     nrow
        lda     nrow
        cmp     #MH
        bne     lmrow
        rts

; drawmaze: paint every playfield cell.  Only used on a board change --
; during play a single eaten dot blanks a single cell.
drawmaze:
        lda     #0
        sta     nrow
dmrow:  lda     nrow
        clc
        adc     #MROW0
        tay
        lda     #MCOL0
        jsr     cellptr
        lda     #0
        sta     ncol
dmcol:  jsr     drawcell
        inc     ncol
        lda     ncol
        cmp     #MW
        bne     dmcol
        inc     nrow
        lda     nrow
        cmp     #MH
        bne     dmrow
        rts

; drawcell: paint the cell at (ncol, nrow); PTR/CPTR already point at the
; start of its screen row.
drawcell:
        jsr     tilerd
        cmp     #T_WALL
        beq     dcwall
        cmp     #T_DOT
        beq     dcdot
        cmp     #T_NOUP
        beq     dcdot
        cmp     #T_ENER
        beq     dcener
        cmp     #T_DOOR
        beq     dcdoor
        lda     #32                     ; empty, house interior, tunnel
        ldx     #0
        jmp     dcput
dcwall: jsr     wallglyph
        ldx     wallcol
        jmp     dcput
dcdot:  lda     #GL_DOT
        ldx     #8|7
        jmp     dcput
dcener: lda     #GL_ENER
        ldx     #8|1
        jmp     dcput
dcdoor: lda     #GL_DOOR
        ldx     #8|0
dcput:  ldy     ncol
        sta     (PTR),y
        txa
        sta     (CPTR),y
        rts

; wallglyph: A = the connectivity glyph for the wall at (ncol, nrow).
; bit0 up, bit1 left, bit2 down, bit3 right; off-map counts as wall, so the
; border closes instead of sprouting stubs.
wallglyph:
        lda     #0
        sta     tmp+1
        dec     nrow
        jsr     nbwall
        inc     nrow
        bcc     wg1
        lda     tmp+1
        ora     #1
        sta     tmp+1
wg1:    dec     ncol
        jsr     nbwall
        inc     ncol
        bcc     wg2
        lda     tmp+1
        ora     #2
        sta     tmp+1
wg2:    inc     nrow
        jsr     nbwall
        dec     nrow
        bcc     wg3
        lda     tmp+1
        ora     #4
        sta     tmp+1
wg3:    inc     ncol
        jsr     nbwall
        dec     ncol
        bcc     wg4
        lda     tmp+1
        ora     #8
        sta     tmp+1
wg4:    lda     tmp+1
        clc
        adc     #WALLBASE
        rts

nbwall: jsr     tilerd
        cmp     #T_WALL
        beq     nbyes
        clc
        rts
nbyes:  sec
        rts

; canpass: C=1 if tile A may be entered.  The door and the house interior
; are open only while passhouse is set -- that flag is what separates a
; ghost leaving home from Ms. Muncher, who can never get in.
canpass:
        cmp     #T_WALL
        beq     cpno
        cmp     #T_DOOR
        bcc     cpyes                   ; 0, 1, 2
        cmp     #T_NOUP
        bcs     cpyes                   ; 6, 7, 8
        lda     passhouse               ; 4 or 5
        beq     cpno
cpyes:  sec
        rts
cpno:   clc
        rts

; isnoup: Z=1 if the tile at (ncol,nrow) forbids an upward turn.
isnoup: jsr     tilerd
        cmp     #T_NOUP
        beq     inyes
        cmp     #T_NOUPE
inyes:  rts

; eatcell: Ms. Muncher is centred on (tcol, trow); take whatever is there.
eatcell:
        lda     tcol
        sta     ncol
        lda     trow
        sta     nrow
        jsr     tilerd
        cmp     #T_DOT
        beq     ecdot
        cmp     #T_NOUP
        beq     ecnoup
        cmp     #T_ENER
        beq     ecener
        rts
ecnoup: lda     #T_NOUPE                ; eaten, but still no upward turn
        jsr     tilewr
        jmp     ecscore
ecdot:  lda     #T_EMPTY
        jsr     tilewr
ecscore:
        jsr     blankcell
        dec     dotsleft
        jsr     elroycheck
        jsr     housedot
        lda     #<10
        ldx     #>10
        jsr     addscore
        jmp     sfxmunch
ecener: lda     #T_EMPTY
        jsr     tilewr
        jsr     blankcell
        dec     dotsleft
        jsr     elroycheck
        jsr     housedot
        lda     #<50
        ldx     #>50
        jsr     addscore
        jmp     frighten

; blankcell: erase the cell at (tcol, trow) from the screen.
blankcell:
        lda     trow
        clc
        adc     #MROW0
        tay
        lda     #MCOL0
        jsr     cellptr
        ldy     tcol
        lda     #32
        sta     (PTR),y
        rts

; setmaze: pick this board's layout.  1-2 maze 1, 3-5 maze 2, 6-9 maze 3,
; 10-13 maze 4, then the last two alternating every four boards.
setmaze:
        lda     board
        cmp     #14
        bcs     smlate
        tax
        dex
        lda     mazerot,x
        jmp     smset
smlate: sec
        sbc     #14
        lsr     a
        lsr     a
        and     #1
        clc
        adc     #2
smset:  sta     maze
        jmp     loadmaze

        .segment "RODATA"
mazerot:
        .byte   0,0, 1,1,1, 2,2,2,2, 3,3,3,3
; $D022, the wall highlight, and the per-cell wall colour nybble (bit 3 on
; puts the cell in multicolor).
mzwallhi:
        .byte   14, 10, 13, 3
mzwallcol:
        .byte   8|6, 8|2, 8|5, 8|4

        .segment "CODE"
