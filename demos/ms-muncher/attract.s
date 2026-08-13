; attract.s -- the title screen, the cast, the score table, and the demo
; that plays itself.
;
; The demo is not a canned recording: demomode simply replaces the keyboard
; with demopick, and everything else -- the ghosts, the phases, the fruit,
; the speeds -- is the game engine running normally.  That is why watching
; the attract screen is a fair advertisement for the game, and why a bug in
; the ghosts shows up there.
;
; The title lettering is drawn from a 3x5 block font poked as reverse-space
; cells, not from charset glyphs: ten letters at four columns each is
; exactly the 40-column screen, and it costs 50 bytes instead of 40 glyphs.

        .segment "CODE"

sttitle:
        lda     stinit
        beq     tt2
        lda     #0
        sta     stinit
        sta     demomode
        sta     sprena
        jsr     clrscreen
        jsr     drawtitle
        jsr     castsprites
        lda     #250                    ; ticked every fourth frame, so the
        sta     sttimer                 ; attract screen holds ~16 seconds
        lda     #16                     ; two seconds of lead-in, so an audio
        sta     muslead                 ; capture opens before the first note
        lda     #0
        jsr     mustart                 ; the title tune
tt2:    lda     sttimer
        cmp     #230                    ; ignore the key that ended the game
        bcs     ttcount
        lda     curkey
        cmp     #KEY_NONE
        beq     ttcount
        cmp     #KEY_1
        beq     ttact1
        cmp     #KEY_2
        beq     ttact2
        cmp     #KEY_3
        beq     ttact3
        jsr     musstop
        jsr     newgame
        jmp     tickend
ttcount:
        lda     frames
        and     #3
        bne     ttdone
        dec     sttimer
        bne     ttdone
        jsr     startdemo
ttdone: jmp     tickend
ttact1: lda     #0
        beq     ttact
ttact2: lda     #1
        bne     ttact
ttact3: lda     #2
ttact:  sta     actnum
        lda     #ST_TITLE
        sta     actret
        lda     #ST_ACT
        sta     gstate
        lda     #1
        sta     stinit
        jmp     tickend

; startdemo: the real engine, with demopick where the keyboard was.
startdemo:
        jsr     newgame
        lda     #1
        sta     demomode
        rts

drawtitle:
        lda     #7
        sta     txtcol
        SETSTR  txtitle
        lda     #0                      ; ten letters x 4 columns = 40
        ldy     #1
        ldx     #10
        jsr     drawbig
        lda     #1
        sta     txtcol
        SETSTR  txcast
        lda     #13
        ldy     #7
        ldx     #13
        jsr     txtat
        lda     #0                      ; the four names under their sprites
        sta     hidx
dt1:    ldx     hidx
        lda     castcol,x
        sta     txtcol
        txa
        asl     a
        asl     a
        asl     a
        clc
        adc     #<txnames
        sta     SP
        lda     #>txnames
        adc     #0
        sta     SP+1
        ldx     hidx
        lda     castlen,x
        sta     tmp+3
        lda     castat,x
        ldx     tmp+3
        ldy     #13
        jsr     txtat
        inc     hidx
        lda     hidx
        cmp     #4
        bne     dt1
        jsr     drawhitable
        lda     #3
        sta     txtcol
        SETSTR  txpress
        lda     #10
        ldy     #22
        ldx     #19
        jsr     txtat
        SETSTR  txkeys
        lda     #12
        ldy     #23
        ldx     #16
        jmp     txtat

; drawhitable: the top five, on the title screen and nowhere else.
drawhitable:
        lda     #12
        sta     txtcol
        SETSTR  txtop
        lda     #15
        ldy     #15
        ldx     #10
        jsr     txtat
        lda     #0
        sta     hidx
dht1:   lda     #1
        sta     txtcol
        lda     hidx
        clc
        adc     #16
        tay
        lda     #12
        jsr     cellptr
        lda     hidx                    ; rank
        clc
        adc     #49
        ldy     #0
        sta     (PTR),y
        lda     #46                     ; '.'
        iny
        sta     (PTR),y
        lda     hidx                    ; three initials
        asl     a
        clc
        adc     hidx
        tax
        ldy     #3
dht2:   lda     hinames,x
        sta     (PTR),y
        inx
        iny
        cpy     #6
        bne     dht2
        lda     hidx                    ; and the score
        asl     a
        clc
        adc     hidx
        tax
        lda     hitab,x
        sta     tmp
        lda     hitab+1,x
        sta     tmp+1
        lda     hitab+2,x
        sta     tmp+2
        lda     #8
        jsr     putnum6
        ldy     #0
dht3:   lda     #1                      ; colour the whole line
        sta     (CPTR),y
        iny
        cpy     #14
        bne     dht3
        inc     hidx
        lda     hidx
        cmp     #5
        bne     dht1
        rts

; castsprites: the line-up under "meet the cast", 48 pixels apart so no two
; 24-pixel-wide sprites overlap.
castsprites:
        lda     #SPRBLK+SH_CLOSED       ; Ms. Muncher leads the line-up
        sta     SPRPTR
        lda     #52
        sta     $D000
        lda     #51+9*8+2
        sta     $D001
        lda     #7
        sta     $D027
        ldx     #0
cs2:    lda     #SPRBLK+SH_BODY+DIR_DOWN
        sta     SPRPTR+1,x
        txa
        asl     a
        tay
        lda     castx,x
        sta     $D002,y
        lda     #51+9*8+2
        sta     $D003,y
        lda     ghostcol,x
        sta     $D028,x
        inx
        cpx     #4
        bne     cs2
        lda     #0
        sta     $D010
        lda     #%00011111
        sta     sprena
        rts

; drawbig: X letters of the string at SP, in the 3x5 block font, with the
; top-left cell at column A, row Y.
drawbig:
        sta     tmp+4
        sty     tmp+5
        stx     tmp+6
        lda     #0
        sta     tmp+3
db1:    ldy     tmp+3
        lda     (SP),y
        ldx     #0
dbfind: cmp     bigchars,x
        beq     dbgot
        inx
        cpx     #10
        bne     dbfind
        ldx     #2                      ; unknown: draw a blank
dbgot:  stx     tmp+7
        txa
        asl     a
        asl     a
        clc
        adc     tmp+7                   ; five bytes a glyph
        tax
        lda     #0
        sta     tmp+7                   ; row within the glyph
dbrow:  lda     tmp+5
        clc
        adc     tmp+7
        tay
        lda     tmp+4
        jsr     cellptr
        lda     bigfont,x
        sta     tmp+2
        ldy     #0
dbcol:  lda     tmp+2
        and     dbbit,y
        beq     dbblank
        lda     #160                    ; reverse space: a solid block
        .byte   $2C
dbblank:
        lda     #32
        sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        iny
        cpy     #3
        bne     dbcol
        inx
        inc     tmp+7
        lda     tmp+7
        cmp     #5
        bne     dbrow
        lda     tmp+4
        clc
        adc     #4
        sta     tmp+4
        inc     tmp+3
        lda     tmp+3
        cmp     tmp+6
        bne     db1
        rts

; ---- the demo's player ---------------------------------------------------
; Scores every legal direction: a dot is worth taking, a ghost within six
; tiles is worth avoiding, and the reverse is never chosen.
demoai: rts                             ; per-frame input: the demo decides
                                        ; at tile centres instead

demopick:
        lda     adir
        sta     awant
        lda     #0
        sta     bestlo
        lda     adir
        eor     #2
        sta     tmp+4
        lda     #0
        sta     tmp+5
dp1:    lda     tmp+5
        cmp     tmp+4
        beq     dpskip
        lda     tmp+5
        jsr     cantake
        bcs     dpscore
dpskip: jmp     dpnext
dpscore:
        lda     #100
        sta     dscore
        jsr     tilerd
        cmp     #T_DOT
        beq     dpdot
        cmp     #T_ENER
        beq     dpdot
        cmp     #T_NOUP
        bne     dpghosts
dpdot:  lda     dscore
        clc
        adc     #30
        sta     dscore
dpghosts:
        ldx     #0
dpg1:   lda     astate+1,x
        cmp     #GS_SCATTER
        bcc     dpgn
        cmp     #GS_FRIGHT
        bcs     dpgn                    ; blue or eaten: not a threat
        lda     ncol
        sta     tmp
        lda     nrow
        sta     tmp+1
        lda     axhi+1,x
        lsr     a
        lsr     a
        lsr     a
        sta     tmp+2
        lda     ayhi+1,x
        lsr     a
        lsr     a
        lsr     a
        sta     tmp+3
        stx     tmp+6
        jsr     sqdist
        ldx     tmp+6
        lda     dhi
        bne     dpgn
        lda     dlo
        cmp     #36                     ; six tiles
        bcs     dpgn
        lda     dscore
        sec
        sbc     #60
        bcs     :+
        lda     #0
:       sta     dscore
dpgn:   inx
        cpx     #4
        bne     dpg1
        lda     dscore
        cmp     bestlo
        bcc     dpnext
        sta     bestlo
        lda     tmp+5
        sta     awant
dpnext: inc     tmp+5
        lda     tmp+5
        cmp     #4
        beq     dpend
        jmp     dp1
dpend:  rts

        .segment "RODATA"
txtitle: .byte  "MS MUNCHER"
txcast:  .byte  "MEET THE CAST"
txnames: .byte  "BRUISER", 0
         .byte  "PIXIE  ", 0
         .byte  "IVY    ", 0
         .byte  "SABLE  ", 0
castcol: .byte  2, 10, 3, 8
castat:  .byte  8, 16, 22, 27          ; screen column of each name
castlen: .byte  7, 5, 3, 5
castx:   .byte  100, 148, 196, 244   ; sprite X of each ghost in the line-up
txtop:   .byte  "TOP SCORES"
txpress: .byte  "PRESS SPACE TO PLAY"
txkeys:  .byte  "W A S D TO STEER"

; the 3x5 block font, one byte a row, bits 2-0 left to right
bigchars: .byte "MSU NCHER."
bigfont:
        .byte   %101, %111, %111, %101, %101   ; M
        .byte   %111, %100, %111, %001, %111   ; S
        .byte   %101, %101, %101, %101, %111   ; U
        .byte   %000, %000, %000, %000, %000   ; (space)
        .byte   %101, %111, %111, %111, %101   ; N
        .byte   %111, %100, %100, %100, %111   ; C
        .byte   %101, %101, %111, %101, %101   ; H
        .byte   %111, %100, %111, %100, %111   ; E
        .byte   %111, %101, %111, %110, %101   ; R
        .byte   %000, %000, %000, %000, %010   ; .
dbbit:  .byte   %100, %010, %001

        .segment "CODE"
