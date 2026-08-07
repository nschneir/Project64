; actor.s -- the shared movement engine.
;
; Six actors on one grid.  Position is the *pixel* of the actor's centre
; plus an 8.8 sub-pixel accumulator, and speed is a 16-bit per-frame
; increment where 100% is $0140 -- 1.25 pixels a frame.  Every speed class
; the arcade names is then an exact value (80% = $0100, 75% = $00F0,
; 95% = $0130, 40% = $0080), which is what makes "the speed classes" a
; thing you can measure with `c64 until tick` rather than a thing you claim.
;
; Whole pixels are walked ONE AT A TIME by stepone: at 1.25 px/frame the
; accumulator hands back 1 or 2 pixels, and stepping two at once would let
; an actor jump a tile centre -- and with it a wall, a dot, or a junction.
;
; Turning happens only at a tile centre ((px&7)==4 and (py&7)==4), which is
; what keeps every actor lane-locked; a 180 degree reversal is legal
; anywhere, because the tile behind is by definition the one you came from.

        .segment "CODE"

; movetick: advance every actor by this frame's worth of pixels.
movetick:
        jsr     animtick
        lda     #0
        sta     ai
mtl:    ldx     ai
        jsr     setspeed
        ldx     ai
        lda     afrac,x
        clc
        adc     aspdlo,x
        sta     afrac,x
        lda     #0
        adc     aspdhi,x
        sta     steps
mts:    lda     steps
        beq     mtn
        dec     steps
        jsr     stepone
        jmp     mts
mtn:    inc     ai
        lda     ai
        cmp     #NACT
        bne     mtl
        rts

; stepone: move actor `ai` exactly one pixel, deciding at a tile centre.
stepone:
        ldx     ai
        lda     axhi,x
        and     #7
        cmp     #4
        bne     s1mv
        lda     ayhi,x
        and     #7
        cmp     #4
        bne     s1mv
        jsr     atcentre
        lda     blocked
        beq     s1mv
        rts
s1mv:   ldx     ai
        ldy     adir,x
        lda     dxtab,y
        clc
        adc     axhi,x
        sta     axhi,x
        lda     dytab,y
        clc
        adc     ayhi,x
        sta     ayhi,x
        rts

; atcentre: the actor is exactly on a tile centre.  Let it decide, wrap it
; through a tunnel if it is leaving the map, then find out whether the tile
; it now faces can be entered at all.
atcentre:
        ldx     ai
        lda     #0
        sta     blocked
        sta     passhouse
        lda     axhi,x
        lsr     a
        lsr     a
        lsr     a
        sta     tcol
        lda     ayhi,x
        lsr     a
        lsr     a
        lsr     a
        sta     trow
        lda     ai
        bne     acnp
        jsr     playercentre
        jmp     acwrap
acnp:   cmp     #A_FRUIT
        beq     acfr
        jsr     ghostcentre
        jmp     acwrap
acfr:   jsr     fruitcentre
acwrap: ldx     ai
        lda     adir,x
        cmp     #DIR_LEFT
        bne     acw2
        lda     tcol
        bne     acblk
        lda     #(MW-1)*8+4             ; out the left tunnel mouth
        sta     axhi,x
        lda     #MW-1
        sta     tcol
        jmp     acblk
acw2:   cmp     #DIR_RIGHT
        bne     acblk
        lda     tcol
        cmp     #MW-1
        bne     acblk
        lda     #4                      ; ... and in the right one
        sta     axhi,x
        lda     #0
        sta     tcol
acblk:  ldx     ai
        ldy     adir,x
        lda     tcol
        clc
        adc     dxtab,y
        sta     ncol
        lda     trow
        clc
        adc     dytab,y
        sta     nrow
        jsr     tilerd
        jsr     canpass
        bcs     acok
        lda     #1
        sta     blocked
acok:   rts

; cantake: C=1 if actor `ai` may turn to face direction A from (tcol,trow).
; `noup` at the caller's discretion: ghosts obey the restricted cells, Ms.
; Muncher does not.
cantake:
        tay
        lda     tcol
        clc
        adc     dxtab,y
        sta     ncol
        lda     trow
        clc
        adc     dytab,y
        sta     nrow
        jsr     tilerd
        jmp     canpass

; setspeed: choose actor X's speed class for this frame.
setspeed:
        cpx     #0
        beq     ssplayer
        cpx     #A_FRUIT
        beq     ssfruit
        ; --- ghosts ---
        lda     astate,x
        cmp     #GS_SCATTER
        bcs     ssg1                    ; GS_HOUSE / GS_LEAVE: housetick moves it
ssz:    jmp     sszero
ssg1:   cmp     #GS_EYES
        bcc     ssalive
        cmp     #GS_ENTER
        beq     ssz                     ; dropping back in: housetick moves it
        lda     #<SPD_EYES              ; eyes go home fast
        sta     aspdlo,x
        lda     #>SPD_EYES
        sta     aspdhi,x
        rts
ssalive:
        lda     astate,x
        cmp     #GS_FRIGHT
        bne     ssnorm
        ldy     #SPD_GFRIGHT
        jmp     ssput
ssnorm: jsr     intunnel
        bcc     ssn2
        ldy     #SPD_TUNNEL
        jmp     ssput
ssn2:   ldy     #SPD_GHOST
        cpx     #A_G0                   ; cruise elroy speeds up the pursuer
        bne     ssput
        lda     elroy
        beq     ssput
        cmp     #1
        bne     ssn3
        ldy     #SPD_ELROY1
        jmp     ssput
ssn3:   ldy     #SPD_ELROY2
        jmp     ssput
ssplayer:
        jsr     intunnel                ; the prompt's rule: every actor
        bcc     ssp1                    ; crossing a tunnel crawls, not just
        ldy     #SPD_TUNNEL             ; the ghosts
        jmp     ssput
ssp1:   lda     frtimer
        ora     frtimer+1
        beq     ssp2
        ldy     #SPD_PFRIGHT
        jmp     ssput
ssp2:   ldy     #SPD_PLAYER
        jmp     ssput
ssfruit:
        lda     fractive
        beq     sszero
        jsr     intunnel
        bcc     ssf1
        ldy     #SPD_TUNNEL
        jmp     ssput
ssf1:   ldy     #SPD_FRUIT
ssput:  lda     spdgroup                ; five classes per board group
        asl     a
        asl     a
        asl     a
        asl     a                       ; 16 bytes = 8 entries a group
        sty     tmp
        clc
        adc     tmp
        tay
        lda     spdtab,y
        sta     aspdlo,x
        lda     spdtab+1,y
        sta     aspdhi,x
        rts
sszero: lda     #0
        sta     aspdlo,x
        sta     aspdhi,x
        rts

; intunnel: C=1 if actor X stands on a tunnel tile.
intunnel:
        lda     axhi,x
        lsr     a
        lsr     a
        lsr     a
        sta     ncol
        lda     ayhi,x
        lsr     a
        lsr     a
        lsr     a
        sta     nrow
        jsr     tilerd
        cmp     #T_TUNNEL
        beq     ityes
        clc
        rts
ityes:  sec
        rts

; animtick: the ghosts' body frame and Ms. Muncher's mouth run off the free
; frame counter, so nothing has to be reset when a state changes.
animtick:
        inc     animcount
        lda     animcount
        and     #7
        bne     atdone
        lda     animframe
        eor     #1
        sta     animframe
atdone: rts

; shapetick: pick every actor's sprite block and colour.
shapetick:
        lda     frames                  ; Ms. Muncher's mouth: 0 1 2 1
        lsr     a
        lsr     a
        and     #3
        tay
        lda     mouthtab,y
        beq     stclosed
        sta     tmp
        lda     adir
        asl     a
        clc
        adc     tmp
        jmp     stput0
stclosed:
        lda     #SH_CLOSED
stput0: clc
        adc     #SPRBLK
        sta     ashape
        lda     #7                      ; she is yellow
        sta     $D027

        ldx     #0                      ; --- the four ghosts ---
stg:    lda     astate+1,x
        cmp     #GS_EYES
        bcc     stgalive
        lda     adir+1,x                ; eyes only
        clc
        adc     #SPRBLK+SH_EYES
        sta     ashape+1,x
        lda     #1
        sta     $D028,x
        jmp     stgnext
stgalive:
        cmp     #GS_FRIGHT
        bne     stgnorm
        lda     animframe
        clc
        adc     #SPRBLK+SH_FRIGHT
        sta     ashape+1,x
        lda     frflash                 ; the last two seconds flash white
        beq     stgblue
        lda     frames
        and     #4
        beq     stgblue
        lda     #1
        .byte   $2C
stgblue:
        lda     #6
        sta     $D028,x
        jmp     stgnext
stgnorm:
        lda     animframe
        asl     a
        asl     a
        clc
        adc     adir+1,x
        clc
        adc     #SPRBLK+SH_BODY
        sta     ashape+1,x
        lda     ghostcol,x
        sta     $D028,x
stgnext:
        inx
        cpx     #4
        bne     stg

        lda     #SPRBLK+SH_FRUIT        ; --- the fruit ---
        sta     ashape+A_FRUIT
        ldx     frkind
        lda     fruitcol,x
        sta     $D027+A_FRUIT
        rts

; sprupdate: registers from the actor arrays.  Sprite X can exceed 255 in
; the right-hand third of the playfield, so the MSB byte is built as we go.
sprupdate:
        jsr     shapetick
        lda     #0
        sta     tmp+2
        ldx     #0
su1:    lda     axhi,x
        clc
        adc     #SPRXOFF
        sta     tmp
        lda     #0
        adc     #0
        sta     tmp+1
        txa
        asl     a
        tay
        lda     tmp
        sta     $D000,y
        lda     ayhi,x
        clc
        adc     #SPRYOFF
        sta     $D001,y
        lda     tmp+1
        beq     su2
        lda     bitmask,x
        ora     tmp+2
        sta     tmp+2
su2:    lda     ashape,x
        sta     SPRPTR,x
        inx
        cpx     #NACT
        bne     su1
        lda     tmp+2
        sta     $D010
        rts

; resetactors: put everyone back where a life starts.
resetactors:
        lda     #13*8+4                 ; Ms. Muncher below the house
        sta     axhi
        lda     #16*8+4
        sta     ayhi
        lda     #DIR_LEFT
        sta     adir
        sta     awant
        lda     #0
        sta     afrac
        ldx     #0
ral:    lda     ghstx,x                 ; the four ghosts
        sta     axhi+1,x
        lda     ghsty,x
        sta     ayhi+1,x
        lda     ghstdir,x
        sta     adir+1,x
        sta     awant+1,x
        lda     ghststate,x
        sta     astate+1,x
        lda     #0
        sta     afrac+1,x
        sta     greleased,x
        inx
        cpx     #4
        bne     ral
        lda     #1
        sta     greleased               ; Bruiser is already outside
        lda     #0
        sta     fractive
        sta     ghcombo
        sta     frtimer
        sta     frtimer+1
        sta     frflash
        sta     phase
        sta     boardfrm
        sta     boardfrm+1
        jsr     houseload
        jmp     phaseload

; sqinit: build the squares table 0..31 at $C300 -- ghost targeting compares
; squared distances, and a 16-bit compare against a table is both exact and
; cheaper than any multiply.
sqinit: ldx     #0
        lda     #0
        sta     tmp
        sta     tmp+1
sq1:    lda     tmp
        sta     SQLO,x
        lda     tmp+1
        sta     SQHI,x
        txa                             ; (x+1)^2 = x^2 + 2x + 1
        asl     a
        clc
        adc     #1
        clc
        adc     tmp
        sta     tmp
        lda     tmp+1
        adc     #0
        sta     tmp+1
        inx
        cpx     #32
        bne     sq1
        rts

        .segment "RODATA"

dxtab:  .byte   0, $FF, 0, 1
dytab:  .byte   $FF, 0, 1, 0
bitmask: .byte  1, 2, 4, 8, 16, 32
mouthtab: .byte 0, 1, 2, 1

ghostcol:  .byte 2, 10, 3, 8            ; Bruiser, Pixie, Ivy, Sable
fruitcol:  .byte 2, 10, 8, 9, 5, 13, 7

; the ghosts' starting places: Bruiser outside above the door, the other
; three in the house at columns 12, 13 and 15
ghstx:     .byte 13*8+4, 13*8+4, 12*8+4, 15*8+4
ghsty:     .byte 8*8+4, 11*8+4, 11*8+4, 11*8+4
ghstdir:   .byte DIR_LEFT, DIR_UP, DIR_UP, DIR_UP
ghststate: .byte GS_SCATTER, GS_HOUSE, GS_HOUSE, GS_HOUSE

; ---- speed classes -------------------------------------------------------
; Value = pct * 16 / 5, so 100% = $0140 = 1.25 px/frame and every multiple
; of 5% is exact.  Eight 16-bit entries a board group.
SPD_PLAYER  = 0
SPD_PFRIGHT = 2
SPD_GHOST   = 4
SPD_TUNNEL  = 6
SPD_GFRIGHT = 8
SPD_ELROY1  = 10
SPD_ELROY2  = 12
SPD_FRUIT   = 14
SPD_EYES    = $0280                     ; 200%: eaten ghosts race home

spdtab:
        ; board 1:   80  90  75  40  50  80  85  75
        .word   $0100, $0120, $00F0, $0080, $00A0, $0100, $0110, $00F0
        ; boards 2-4: 90  95  85  45  55  90  95  80
        .word   $0120, $0130, $0110, $0090, $00B0, $0120, $0130, $0100
        ; boards 5-20: 100 100  95  50  60 100 105  85
        .word   $0140, $0140, $0130, $00A0, $00C0, $0140, $0150, $0110
        ; boards 21+:  90  90  95  50  60 100 105  85
        .word   $0120, $0120, $0130, $00A0, $00C0, $0140, $0150, $0110

        .segment "CODE"
