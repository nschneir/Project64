; shots.s -- player missiles and enemy bullets, in character space.
;
; Two missiles in flight per fighter (four when dual) and up to eight enemy
; bullets is twelve more objects; as sprites they would eat the multiplexer
; alive.  So they are character cells instead, drawn with half-cell glyph
; phases so they move in four-pixel steps on the character grid -- and all
; eight sprites stay with the fighters, the divers and the beam.
;
; Every shot restores what it covered from the background shadow (screen.s),
; so a missile crossing the starfield does not eat a star.

        .segment "ENGINE"

MIS_SPEED = 4                   ; 4.0 px/frame, exactly half a cell
MIS_TOP   = 4
PLY_ROW   = (PLY - 51) / 8      ; the fighter's text row

shotsinit:
        ldx     #MAXMIS-1
        lda     #0
si1:    sta     mis_on,x
        dex
        bpl     si1
        ldx     #MAXBUL-1
si2:    sta     bul_on,x
        dex
        bpl     si2
        sta     bullets_live
        ldx     #MAXMIS-1
        lda     #$FF
si3:    sta     mis_prow,x
        dex
        bpl     si3
        ldx     #MAXBUL-1
si4:    sta     bul_prow,x
        dex
        bpl     si4
        rts

; ---- firemissile -- one per fighter, two in flight each -----------------
firemissile:
        lda     #0
        sta     tmp3                    ; how many launched
        lda     plx
        clc
        adc     #8                      ; the art's centre, in window pixels
        lsr     a
        lsr     a
        lsr     a
        clc
        adc     #PFCOL
        sta     tmp2
        jsr     newmissile
        lda     pldual
        beq     fm9
        lda     tmp2
        clc
        adc     #2                      ; the right-hand fighter
        sta     tmp2
        jsr     newmissile
fm9:    lda     tmp3
        beq     :+
        lda     #SFX_LASER
        jsr     sfxstart
:       rts

newmissile:
        ldx     #0
nm1:    lda     mis_on,x
        beq     nm2
        inx
        cpx     #MAXMIS
        bne     nm1
        rts
nm2:    lda     #1
        sta     mis_on,x
        lda     tmp2
        sta     mis_col,x
        lda     #(PLY - 51 - 10)
        sta     mis_y,x
        lda     #$FF
        sta     mis_prow,x
        inc     tmp3
        rts

; ---- spawnbullet -- X = the enemy firing --------------------------------
; The bullet is aimed: its X velocity is one of five fixed values chosen by
; which side of the fighter the enemy is on and how far away, which is a
; compare and a table read rather than a divide.
spawnbullet:
        stx     tmp4
        ldy     #0
sb1:    lda     bul_on,y
        beq     sb2
        iny
        cpy     #MAXBUL
        bne     sb1
        ldx     tmp4
        rts
sb2:    ; X position: enemy sprite X + 12, minus the window origin
        lda     enemy_x_lsb,x
        sec
        sbc     #(24 + PFCOL*8 - 12)
        sta     tmp0
        lda     enemy_x_msb,x
        sbc     #0
        beq     @far16
        jmp     sbout
@far16:
        lda     tmp0
        cmp     #PFW*8
        bcc     @far17
        jmp     sbout
@far17:
        sta     bul_x,y
        lda     enemy_y,x
        sec
        sbc     #(51 - 10)
        bcs     @far18
        jmp     sbout
@far18:
        cmp     #190
        bcs     sbout
        sta     bul_y,y
        lda     #1
        sta     bul_on,y
        lda     #0
        sta     bul_xf,y
        sta     bul_yf,y
        sta     bul_vxh,y
        lda     #$FF
        sta     bul_prow,y
        lda     bulspeed
        sta     bul_vyh,y
        lda     #0
        sta     bul_vy,y
        ; aim
        lda     plx
        clc
        adc     #8
        sta     tmp1                    ; the fighter's centre, window pixels
        lda     bul_x,y
        cmp     tmp1
        bcc     sbleftof
        sec
        sbc     tmp1
        cmp     #24
        bcc     sbslow_l
        lda     #$00
        sta     bul_vx,y
        lda     #$FF                    ; -1.0 px/frame
        sta     bul_vxh,y
        jmp     sbdone
sbslow_l:
        lda     #$80                    ; -0.5 px/frame
        sta     bul_vx,y
        lda     #$FF
        sta     bul_vxh,y
        jmp     sbdone
sbleftof:
        lda     tmp1
        sec
        sbc     bul_x,y
        cmp     #24
        bcc     sbslow_r
        lda     #$00
        sta     bul_vx,y
        lda     #$01                    ; +1.0 px/frame
        sta     bul_vxh,y
        jmp     sbdone
sbslow_r:
        lda     #$80                    ; +0.5 px/frame
        sta     bul_vx,y
        lda     #$00
        sta     bul_vxh,y
sbdone: inc     bullets_live
        ldx     tmp4
        rts
sbout:  ldx     tmp4
        rts

; ==========================================================================
; shotstick -- move, erase, redraw.  Collision is resolved in collide.s
; before this runs, so a shot is never drawn on a cell it has already hit.
; ==========================================================================
shotstick:
        jsr     mistick
        jmp     bultick

mistick:
        ldx     #0
mt1:    lda     mis_on,x
        beq     mt8
        lda     mis_y,x
        sec
        sbc     #MIS_SPEED
        bcc     mtkill
        cmp     #MIS_TOP
        bcc     mtkill
        sta     mis_y,x
        jsr     misdraw
        jmp     mt8
mtkill: jsr     miserase
        lda     #0
        sta     mis_on,x
mt8:    inx
        cpx     #MAXMIS
        bne     mt1
        rts

miserase:
        lda     mis_prow,x
        cmp     #$FF
        beq     me9x
        sta     scrrow
        lda     mis_col,x
        sta     scrcol
        stx     tmp0
        jsr     pfrestore
        ldx     tmp0
        lda     #$FF
        sta     mis_prow,x
me9x:   rts

; A shot that stays in the cell it is already drawn in does not restore the
; background first -- the draw overwrites the whole cell anyway.  A missile
; moves 4 px a frame, so this halves its erase work; a bullet at 2 px is in
; the same cell three frames out of four.
misdraw:
        lda     mis_y,x
        lsr     a
        lsr     a
        lsr     a
        sta     tmp1                    ; the row it wants
        cmp     mis_prow,x
        beq     mdput                   ; same cell (the column never moves)
        jsr     miserase
mdput:  lda     tmp1
        sta     scrrow
        sta     mis_prow,x
        lda     mis_col,x
        sta     scrcol
        lda     mis_y,x
        and     #$04
        beq     :+
        lda     #GLY_MIS1
        bne     :++
:       lda     #GLY_MIS0
:       stx     tmp0
        ldy     #COL_WHITE
        sty     txtcol
        jsr     pfshot
        ldx     tmp0
        rts

bultick:
        ldx     #0
bt1:    lda     bul_on,x
        beq     bt8
        ; X += vx (8.8 signed), Y += vy
        lda     bul_xf,x
        clc
        adc     bul_vx,x
        sta     bul_xf,x
        lda     bul_x,x
        adc     bul_vxh,x
        sta     bul_x,x
        cmp     #PFW*8
        bcs     btkill
        lda     bul_yf,x
        clc
        adc     bul_vy,x
        sta     bul_yf,x
        lda     bul_y,x
        adc     bul_vyh,x
        sta     bul_y,x
        cmp     #196
        bcs     btkill
        jsr     buldraw
        jmp     bt8
btkill: jsr     bulerase
        lda     #0
        sta     bul_on,x
        dec     bullets_live
bt8:    inx
        cpx     #MAXBUL
        bne     bt1
        rts

bulerase:
        lda     bul_prow,x
        cmp     #$FF
        beq     be9x
        sta     scrrow
        lda     bul_pcol,x
        sta     scrcol
        stx     tmp0
        jsr     pfrestore
        ldx     tmp0
        lda     #$FF
        sta     bul_prow,x
be9x:   rts

buldraw:
        lda     bul_y,x
        lsr     a
        lsr     a
        lsr     a
        sta     tmp1                    ; the row it wants
        lda     bul_x,x
        lsr     a
        lsr     a
        lsr     a
        clc
        adc     #PFCOL
        sta     tmp2                    ; and the column
        cmp     bul_pcol,x
        bne     bdmove
        lda     tmp1
        cmp     bul_prow,x
        beq     bdput                   ; same cell: overdraw, no restore
bdmove: jsr     bulerase
bdput:  lda     tmp1
        sta     scrrow
        sta     bul_prow,x
        lda     tmp2
        sta     scrcol
        sta     bul_pcol,x
        lda     bul_y,x
        and     #$04
        beq     :+
        lda     #GLY_BUL1
        bne     :++
:       lda     #GLY_BUL0
:       stx     tmp0
        ldy     #COL_LTRED
        sty     txtcol
        jsr     pfshot
        ldx     tmp0
        rts

; ---- clearshots -- wipe every shot off the screen and out of play -------
clearshots:
        ldx     #0
cs1:    lda     mis_on,x
        beq     :+
        jsr     miserase
        lda     #0
        sta     mis_on,x
:       inx
        cpx     #MAXMIS
        bne     cs1
        ldx     #0
cs2:    lda     bul_on,x
        beq     :+
        jsr     bulerase
        lda     #0
        sta     bul_on,x
:       inx
        cpx     #MAXBUL
        bne     cs2
        lda     #0
        sta     bullets_live
        rts
