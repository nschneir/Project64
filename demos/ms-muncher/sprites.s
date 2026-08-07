; sprites.s -- build the 27 sprite shapes at $3000 (blocks 192-218).
;
; The stored art in sprites.inc is 27 blocks of 63 bytes.  Nine are copied
; straight through (Ms. Muncher, closed plus two mouth frames each way);
; the eight ghost shapes are *composited*: the two body frames are drawn
; with empty eye sockets, so ORing an eye patch on top lands white eyeballs
; and blue pupils in the holes without a mask.  That is also why the
; eyes-only shapes cost nothing extra -- they are the same four patches
; copied without a body.
;
;   shape 0        Ms. Muncher, mouth closed
;   shape 1+2*d    ... half open facing d, 2+2*d wide open
;   shape 9+4*f+d  ghost body frame f with eyes facing d
;   shape 17+f     frightened, frame f
;   shape 19+d     eyes only, facing d
;   shape 23       this board's fruit
;   shape 24-26    the intermission props

SRC_BODY   = 9                  ; stored index of ghost body frame 0
SRC_EYES   = 11                 ; stored index of the four eye patches
SRC_FRIGHT = 15
SRC_FRUIT  = 17                 ; ... seven of them
SRC_ACT    = 24

        .segment "CODE"

spriteinit:
        ldx     #0                      ; 0-8 copy straight through
si1:    txa
        jsr     cpshape
        inx
        cpx     #9
        bne     si1

        lda     #0
        sta     tmp+2                   ; frame
sif:    lda     #0
        sta     tmp+3                   ; direction
sid:    lda     tmp+2                   ; dest = 9 + 4*frame + dir
        asl     a
        asl     a
        clc
        adc     tmp+3
        clc
        adc     #SH_BODY
        tax
        lda     tmp+2
        clc
        adc     #SRC_BODY
        jsr     cpshape                 ; the body, eye sockets open
        lda     tmp+3
        clc
        adc     #SRC_EYES
        jsr     orshape                 ; the eyes drop into the sockets
        inc     tmp+3
        lda     tmp+3
        cmp     #4
        bne     sid
        inc     tmp+2
        lda     tmp+2
        cmp     #2
        bne     sif

        ldx     #SH_FRIGHT
        lda     #SRC_FRIGHT
        jsr     cpshape
        ldx     #SH_FRIGHT+1
        lda     #SRC_FRIGHT+1
        jsr     cpshape

        lda     #0                      ; the eye patches alone: eaten ghosts
        sta     tmp+3
sie:    lda     tmp+3
        clc
        adc     #SH_EYES
        tax
        lda     tmp+3
        clc
        adc     #SRC_EYES
        jsr     cpshape
        inc     tmp+3
        lda     tmp+3
        cmp     #4
        bne     sie
        rts

; setfruitshape: A = fruit kind 0-6 -> shape 23.
setfruitshape:
        clc
        adc     #SRC_FRUIT
        ldx     #SH_FRUIT
        jmp     cpshape

; setactshape: A = prop 0-2 -> shape 24+A.
setactshape:
        pha
        clc
        adc     #SH_ACT
        tax
        pla
        clc
        adc     #SRC_ACT
        jmp     cpshape

; srcptr: SP -> stored sprite A (sprite0 + 63*A).
srcptr: sta     tmp
        lda     #0
        sta     SP+1
        lda     tmp
        asl     a
        rol     SP+1
        asl     a
        rol     SP+1
        asl     a
        rol     SP+1
        asl     a
        rol     SP+1
        asl     a
        rol     SP+1
        asl     a
        rol     SP+1                    ; SP = 64*A
        sec
        sbc     tmp                     ; 63*A = 64*A - A
        sta     SP
        lda     SP+1
        sbc     #0
        sta     SP+1
        clc
        lda     SP
        adc     spritesrc
        sta     SP
        lda     SP+1
        adc     spritesrc+1
        sta     SP+1
        rts

        .segment "RODATA"
; where the sprite sheet ended up after relocart moved the art block
spritesrc: .word HI(sprite0)
        .segment "CODE"

; dstptr: DP -> shape X in sprite RAM (SPRRAM + 64*X).
dstptr: txa
        ldy     #0
        sty     DP+1
        asl     a
        rol     DP+1
        asl     a
        rol     DP+1
        asl     a
        rol     DP+1
        asl     a
        rol     DP+1
        asl     a
        rol     DP+1
        asl     a
        rol     DP+1
        sta     DP
        lda     DP+1
        clc
        adc     #>SPRRAM
        sta     DP+1
        rts

; cpshape: copy stored sprite A into shape X.
cpshape:
        jsr     srcptr
        jsr     dstptr
        ldy     #62
cp1:    lda     (SP),y
        sta     (DP),y
        dey
        bpl     cp1
        rts

; orshape: OR stored sprite A into shape X.
orshape:
        jsr     srcptr
        jsr     dstptr
        ldy     #62
or1:    lda     (DP),y
        ora     (SP),y
        sta     (DP),y
        dey
        bpl     or1
        rts
