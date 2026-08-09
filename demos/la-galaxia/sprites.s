; sprites.s -- the sprite shapes and where they live.
;
; A sprite pointer selects a 64-byte block, so shape n has to start at
; $2000 + n*64 -- but `c64 sprite encode` emits 63 bytes per shape with no
; padding, and 63 does not divide 64.  Rather than pad the generated data
; (which would mean post-processing it and make the file no longer be what
; the encoder wrote), the 21 shapes ship as one 1,323-byte run and startup
; fans them out into their blocks.  It costs 1.3 KB of file and one loop.
;
; Block = address / 64, so shape n is block 128 + n.  $2000-$37FF is inside
; VIC bank 0, which is where the chip has to be able to see it.

        .segment "ENGINE"

NSPRITES = 21

SPR_FIGHTER = SPRBLK + 0        ; hires: the player's fighter
SPR_ACCENT  = SPRBLK + 1        ; hires: the red/cyan accent overlay
SPR_SPIN45  = SPRBLK + 2        ; hires: capture spin, three tilted frames
SPR_SPIN90  = SPRBLK + 3
SPR_SPIN135 = SPRBLK + 4
SPR_CAPTIVE = SPRBLK + 5        ; multicolour from here down
SPR_DRONE0  = SPRBLK + 6
SPR_DRONE1  = SPRBLK + 7
SPR_SENT0   = SPRBLK + 8
SPR_SENT1   = SPRBLK + 9
SPR_FLAG0   = SPRBLK + 10
SPR_FLAG1   = SPRBLK + 11
SPR_BEAM0   = SPRBLK + 12
SPR_BEAM1   = SPRBLK + 13
SPR_TRANS0  = SPRBLK + 14
SPR_TRANS1  = SPRBLK + 15
SPR_TRANS2  = SPRBLK + 16
SPR_EXP0    = SPRBLK + 17
SPR_EXP1    = SPRBLK + 18
SPR_EXP2    = SPRBLK + 19
SPR_EXP3    = SPRBLK + 20

installsprites:
        lda     #0
        ldx     #NSPRITES
        jsr     sprfan
        ; Sprites 2-7 are the multiplexed registers and every shape they
        ; ever carry is multicolour, so the bit can be set once here: a
        ; raster chain cannot flip $D01C per band without a fifth event kind
        ; for no gain.  Sprites 0-1 stay hires for the fighter's sharp edges.
        lda     #$FC
        sta     SPRMC
        rts

; sprfan -- A = first shape, X = count: fan that slice of the packed run out
; into its 64-byte blocks.  The cold open's exit calls it in two halves,
; because all 21 shapes are ~16,000 cycles of copy and one tick cannot
; carry that (§1a); startup calls it once with the lot.
sprfan:
        sta     tmp2
        stx     tmp3
        lda     #0                      ; first*64, 16-bit
        sta     tmp1
        lda     tmp2
        .repeat 6
        asl     a
        rol     tmp1
        .endrepeat
        sta     tmp0
        clc
        adc     #<SPRRAM
        sta     DST
        lda     tmp1
        adc     #>SPRRAM
        sta     DST+1
        lda     tmp0                    ; first*63 = first*64 - first
        sec
        sbc     tmp2
        sta     tmp0
        lda     tmp1
        sbc     #0
        sta     tmp1
        lda     tmp0
        clc
        adc     #<hspr0
        sta     SRC
        lda     tmp1
        adc     #>hspr0
        sta     SRC+1
        ldx     tmp3
is1:    ldy     #62
is2:    lda     (SRC),y
        sta     (DST),y
        dey
        bpl     is2
        ; source advances 63, destination 64
        lda     SRC
        clc
        adc     #63
        sta     SRC
        bcc     :+
        inc     SRC+1
:       lda     DST
        clc
        adc     #64
        sta     DST
        bcc     :+
        inc     DST+1
:       dex
        bne     is1
        rts

; ---- shape tables, indexed by enemy_type ---------------------------------
; Two animation frames each; enemy.s picks the frame from `animphase`.
typeshape0:
        .byte   SPR_DRONE0, SPR_SENT0, SPR_FLAG0, SPR_TRANS0, SPR_CAPTIVE
typeshape1:
        .byte   SPR_DRONE1, SPR_SENT1, SPR_FLAG1, SPR_TRANS1, SPR_CAPTIVE
typecolour:
        .byte   COL_YELLOW, COL_RED, COL_CYAN, COL_LTGREEN, COL_WHITE
; A Flagship that has taken one hit swaps to purple and stays alive.
FLAG_HURT_COL = COL_PURPLE

        .include "sprites.inc"
