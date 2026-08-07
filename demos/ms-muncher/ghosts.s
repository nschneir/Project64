; ghosts.s -- four personalities, the phase table, the house, and fright.
;
; The whole point of this file is that the four ghosts do NOT share a chase
; routine.  Each computes its own target tile every time it reaches a
; centre, and then picks the legal direction whose *straight-line* distance
; to that target is smallest, ties broken up > left > down > right -- which
; is the arcade's rule, and why Pixie cuts corners while Sable loses
; interest.  The up-quirk (a target computed ahead of an upward-facing
; player is displaced sideways as well) is reproduced on purpose: it is a
; bug in the original that the game's geometry grew around.
;
; What separates this game from its predecessor is the randomised opening:
; during the first scatter phase of every board the ghosts choose randomly
; at junctions, so no memorised pattern survives.

        .segment "CODE"

; ghostcentre: actor `ai` (1-4) is on a tile centre.
ghostcentre:
        lda     ai
        sec
        sbc     #1
        sta     gi
        ldx     ai
        lda     astate,x
        cmp     #GS_SCATTER
        bcc     gcret                   ; GS_HOUSE / GS_LEAVE: housetick owns it
        cmp     #GS_ENTER
        beq     gcret
        cmp     #GS_EYES
        bne     gcalive
        lda     #1                      ; eyes: the door is open to them
        sta     passhouse
        ldy     gi
        lda     #13
        sta     gtx,y
        lda     #8
        sta     gty,y
        jsr     loadtarget
        lda     tcol                    ; home?  drop back in
        cmp     #13
        bne     gcgo
        lda     trow
        cmp     #8
        bne     gcgo
        lda     #GS_ENTER
        sta     astate,x
        rts
gcgo:   jmp     gchoose
gcrnd:  jmp     gcrandom
gcalive:
        cmp     #GS_FRIGHT
        beq     gcrnd
        lda     scatteropen
        bne     gcrnd
        jsr     gtarget
        jsr     loadtarget
        jmp     gchoose
gcret:  rts

; loadtarget: copy this ghost's target into the chooser's inputs.
loadtarget:
        ldy     gi
        lda     gtx,y
        sta     tgtx
        lda     gty,y
        sta     tgty
        rts

; gtarget: fill this ghost's target tile.
gtarget:
        jsr     playertile
        ldy     gi
        ldx     ai
        lda     astate,x
        cmp     #GS_SCATTER
        bne     gtchase
        lda     cornerx,y               ; scatter: each has its own corner
        sta     gtx,y
        lda     cornery,y
        sta     gty,y
        rts
gtchase:
        lda     gi
        beq     gtbruiser
        cmp     #1
        beq     gtpixie
        cmp     #2
        beq     gtivy
; --- Sable: chases while she is far away, bolts for his corner when close
        lda     tcol
        sta     tmp
        lda     trow
        sta     tmp+1
        lda     ptcol
        sta     tmp+2
        lda     ptrow
        sta     tmp+3
        jsr     sqdist
        lda     dhi                     ; 8 tiles squared = 64
        bne     gtsfar
        lda     dlo
        cmp     #64
        bcs     gtsfar
        ldy     gi
        lda     cornerx,y
        sta     gtx,y
        lda     cornery,y
        sta     gty,y
        rts
gtsfar: ldy     gi
gtbruiser:
        lda     ptcol                   ; --- Bruiser: straight at her
        sta     gtx,y
        lda     ptrow
        sta     gty,y
        rts
gtpixie:
        lda     #4                      ; --- Pixie: four tiles ahead of her
        jsr     aheadtile
        ldy     gi
        lda     tmp
        sta     gtx,y
        lda     tmp+1
        sta     gty,y
        rts
gtivy:
        lda     #2                      ; --- Ivy: the pivot two tiles ahead,
        jsr     aheadtile               ; then that vector doubled through
        lda     axhi+A_G0               ; Bruiser
        lsr     a
        lsr     a
        lsr     a
        sta     tmp+2
        lda     ayhi+A_G0
        lsr     a
        lsr     a
        lsr     a
        sta     tmp+3
        ldy     gi
        lda     tmp
        asl     a
        sec
        sbc     tmp+2
        sta     gtx,y
        lda     tmp+1
        asl     a
        sec
        sbc     tmp+3
        sta     gty,y
        rts

; playertile: ptcol/ptrow, the tile Ms. Muncher is standing on.
playertile:
        lda     axhi
        lsr     a
        lsr     a
        lsr     a
        sta     ptcol
        lda     ayhi
        lsr     a
        lsr     a
        lsr     a
        sta     ptrow
        rts

; aheadtile: tmp/tmp+1 = the tile A steps ahead of Ms. Muncher.  When she
; faces up the target is *also* displaced A tiles left: the arcade's
; overflow, kept because the ghosts' cornering depends on it.
aheadtile:
        sta     tmp+2
        lda     ptcol
        sta     tmp
        lda     ptrow
        sta     tmp+1
        lda     adir
        cmp     #DIR_UP
        bne     ah1
        lda     tmp+1
        sec
        sbc     tmp+2
        sta     tmp+1
        lda     tmp
        sec
        sbc     tmp+2
        sta     tmp
        rts
ah1:    cmp     #DIR_LEFT
        bne     ah2
        lda     tmp
        sec
        sbc     tmp+2
        sta     tmp
        rts
ah2:    cmp     #DIR_DOWN
        bne     ah3
        lda     tmp+1
        clc
        adc     tmp+2
        sta     tmp+1
        rts
ah3:    lda     tmp
        clc
        adc     tmp+2
        sta     tmp
        rts

; sqdist: dlo/dhi = squared distance between (tmp,tmp+1) and (tmp+2,tmp+3).
; A squares table beats a multiply here, and a 16-bit compare is the only
; honest way to rank them -- bmi after a compare is a magnitude test only
; for signed bytes, and these are not.
sqdist: lda     tmp
        sec
        sbc     tmp+2
        bcs     sqd1
        eor     #$FF
        clc
        adc     #1
sqd1:    cmp     #32
        bcc     sqd2
        lda     #31
sqd2:    tax
        lda     SQLO,x
        sta     dlo
        lda     SQHI,x
        sta     dhi
        lda     tmp+1
        sec
        sbc     tmp+3
        bcs     sqd3
        eor     #$FF
        clc
        adc     #1
sqd3:    cmp     #32
        bcc     sqd4
        lda     #31
sqd4:    tax
        clc
        lda     dlo
        adc     SQLO,x
        sta     dlo
        lda     dhi
        adc     SQHI,x
        sta     dhi
        rts

; gchoose: take the legal direction nearest the target.  Never the reverse
; of the way we came -- ghosts only turn round when a phase change or an
; energizer tells them to.
gchoose:
        ldx     ai
        lda     adir,x
        eor     #2
        sta     tmp+4
        lda     #$FF
        sta     bestlo
        sta     besthi
        lda     #DIR_NONE
        sta     bestdir
        lda     #0
        sta     tmp+5
gch1:   lda     tmp+5
        cmp     tmp+4
        beq     gchnext
        cmp     #DIR_UP
        bne     gch2
        lda     tcol                    ; the restricted cells: no turn up
        sta     ncol
        lda     trow
        sta     nrow
        jsr     isnoup
        beq     gchnext
gch2:   lda     tmp+5
        jsr     cantake
        bcc     gchnext
        lda     ncol
        sta     tmp
        lda     nrow
        sta     tmp+1
        lda     tgtx
        sta     tmp+2
        lda     tgty
        sta     tmp+3
        jsr     sqdist
        lda     dhi
        cmp     besthi
        bcc     gchbest
        bne     gchnext
        lda     dlo
        cmp     bestlo
        bcs     gchnext
gchbest:
        lda     dlo
        sta     bestlo
        lda     dhi
        sta     besthi
        lda     tmp+5
        sta     bestdir
gchnext:
        inc     tmp+5
        lda     tmp+5
        cmp     #4
        bne     gch1
        ldx     ai
        lda     bestdir
        cmp     #DIR_NONE
        beq     gchback
        sta     adir,x
        rts
gchback:
        lda     adir,x                  ; boxed in: turn round
        eor     #2
        sta     adir,x
        rts

; gcrandom: a legal direction at random -- frightened ghosts, and every
; ghost during the opening scatter.  This is the pattern-killer.
gcrandom:
        lda     #0
        sta     tmp+5
        sta     tmp+6
        ldx     ai
        lda     adir,x
        eor     #2
        sta     tmp+4
grn1:   lda     tmp+5
        cmp     tmp+4
        beq     grnnext
        cmp     #DIR_UP
        bne     grn2
        lda     tcol
        sta     ncol
        lda     trow
        sta     nrow
        jsr     isnoup
        beq     grnnext
grn2:   lda     tmp+5
        jsr     cantake
        bcc     grnnext
        ldx     tmp+6
        lda     tmp+5
        sta     dirlist,x
        inc     tmp+6
grnnext:
        inc     tmp+5
        lda     tmp+5
        cmp     #4
        bne     grn1
        lda     tmp+6
        beq     grnback                 ; boxed in: turn round
        jsr     rnd
        and     #3
grnm:   cmp     tmp+6
        bcc     grnok
        sec
        sbc     tmp+6
        jmp     grnm
grnok:  tax
        lda     dirlist,x
        ldx     ai
        sta     adir,x
grndone:
        rts
grnback:
        ldx     ai
        lda     adir,x
        eor     #2
        sta     adir,x
        rts

; rnd: a 16-bit Galois LFSR, tap $B400, seeded non-zero at startup -- a
; shift register whose state reaches zero is stuck there for good, and one
; whose state is overwritten from outside every frame never shifts at all.
; A key press is stirred into the high byte by tick; the frame it lands on
; is the entropy that makes two games open differently.
rnd:    lsr     rndstate+1
        ror     rndstate
        bcc     rnd1
        lda     rndstate+1
        eor     #$B4
        sta     rndstate+1
rnd1:   lda     rndstate
        rts

; ---- the scatter/chase phase table --------------------------------------
; Even phases scatter, odd phases chase; $FFFF means "for the rest of the
; board".  Every phase change reverses every ghost that is out.
phaseload:
        lda     #0
        sta     phase
        lda     #1
        sta     scatteropen
        jsr     phreload
        ldx     #0
plg:    lda     astate+1,x
        cmp     #GS_SCATTER
        bcc     plnext
        cmp     #GS_EYES
        bcs     plnext
        lda     #GS_SCATTER
        sta     astate+1,x
plnext: inx
        cpx     #4
        bne     plg
        rts

phreload:
        lda     spdgroup
        cmp     #3
        bcc     :+
        lda     #2
:       asl     a                       ; 8 phases x 2 bytes = 16 a group
        asl     a
        asl     a
        asl     a
        clc
        adc     phase
        adc     phase
        tay
        lda     phtab,y
        sta     phtimer
        lda     phtab+1,y
        sta     phtimer+1
        rts

phasetick:
        lda     phtimer
        and     phtimer+1
        cmp     #$FF
        beq     ptdone                  ; $FFFF: this phase never ends
        lda     phtimer
        bne     :+
        dec     phtimer+1
:       dec     phtimer
        lda     phtimer
        ora     phtimer+1
        bne     ptdone
        inc     phase
        lda     #0
        sta     scatteropen
        jsr     phreload
        lda     phase                   ; even scatter, odd chase
        and     #1
        beq     ptscat
        lda     #GS_CHASE
        .byte   $2C
ptscat: lda     #GS_SCATTER
        sta     tmp+7
        ldx     #0
ptg:    lda     astate+1,x
        cmp     #GS_SCATTER
        bcc     ptnext
        cmp     #GS_FRIGHT
        bcs     ptnext
        lda     tmp+7
        sta     astate+1,x
        lda     adir+1,x                ; a phase change reverses everyone
        eor     #2
        sta     adir+1,x
ptnext: inx
        cpx     #4
        bne     ptg
ptdone: rts

; ---- frightened ----------------------------------------------------------
frighten:
        ldx     board
        cpx     #21
        bcc     :+
        ldx     #21
:       dex
        lda     frtab,x
        beq     frnone                  ; late boards: the energizer only scores
        lda     #0
        sta     frtimer+1
        lda     frtab,x
        asl     a                       ; the table is in units of 4 frames
        rol     frtimer+1
        asl     a
        rol     frtimer+1
        sta     frtimer
        lda     #0
        sta     frflash
        sta     ghcombo
        ldx     #0
frg:    lda     astate+1,x
        cmp     #GS_SCATTER
        bcc     frnext
        cmp     #GS_FRIGHT
        bcs     frnext
        lda     #GS_FRIGHT
        sta     astate+1,x
        lda     adir+1,x
        eor     #2
        sta     adir+1,x
frnext: inx
        cpx     #4
        bne     frg
        jmp     sfxsiren
frnone: lda     #0
        sta     ghcombo
        rts

frighttick:
        lda     frtimer
        ora     frtimer+1
        beq     ftdone
        lda     frtimer
        bne     :+
        dec     frtimer+1
:       dec     frtimer
        lda     frtimer
        ora     frtimer+1
        beq     ftexpire
        lda     frtimer+1
        bne     ftdone
        lda     frtimer                 ; under two seconds: flash white
        cmp     #120
        bcs     ftdone
        lda     #1
        sta     frflash
        rts
ftexpire:
        lda     #0
        sta     frflash
        lda     phase
        and     #1
        beq     ftscat
        lda     #GS_CHASE
        .byte   $2C
ftscat: lda     #GS_SCATTER
        sta     tmp+7
        ldx     #0
ftg:    lda     astate+1,x
        cmp     #GS_FRIGHT
        bne     ftnext
        lda     tmp+7
        sta     astate+1,x
ftnext: inx
        cpx     #4
        bne     ftg
ftdone: rts

; ---- the ghost house -----------------------------------------------------
; Ghosts leave on a staggered schedule, never together: each waits for its
; own dot count AND its own slice of the board clock.
housetick:
        inc     boardfrm
        bne     :+
        inc     boardfrm+1
:       inc     nodot                   ; the arcade's global release timer:
        lda     nodot                   ; four seconds without a dot and the
        cmp     #240                    ; next ghost is pushed out anyway, so
        bcc     htg                     ; standing still cannot stall them
        lda     #0
        sta     nodot
        ldx     #0
htfree: lda     greleased,x
        beq     htforce
        inx
        cpx     #4
        bne     htfree
        beq     htg
htforce:
        lda     #0
        sta     housedots2,x
        sta     housetime2,x
htg:    ldx     #0
htgl:   lda     astate+1,x
        bne     :+
        jmp     hthouse
:       cmp     #GS_LEAVE
        beq     htleave
        cmp     #GS_ENTER
        bne     htnext
        jmp     htenter
htnext: inx
        cpx     #4
        bne     htgl
        rts

hthouse:                                ; bob gently, and test for release
        lda     frames
        and     #16
        beq     :+
        lda     #11*8+3
        bne     htbob
:       lda     #11*8+5
htbob:  sta     ayhi+1,x
        lda     dotseaten
        cmp     housedots2,x
        bcc     htnext
        lda     boardfrm+1              ; ... and its slice of the clock
        bne     htgo
        lda     boardfrm
        cmp     housetime2,x
        bcc     htnext
htgo:   lda     #11*8+4
        sta     ayhi+1,x
        lda     #GS_LEAVE
        sta     astate+1,x
        lda     #1
        sta     greleased,x
        jmp     htnext

htleave:                                ; slide to the door column, then up
        lda     axhi+1,x
        cmp     #13*8+4
        beq     htlup
        bcs     htlleft
        inc     axhi+1,x
        jmp     htnext
htlleft:
        dec     axhi+1,x
        jmp     htnext
htlup:  lda     ayhi+1,x
        cmp     #8*8+4
        beq     htlout
        dec     ayhi+1,x
        lda     #DIR_UP
        sta     adir+1,x
        jmp     htnext
htlout: lda     phase                   ; out: join the current phase
        and     #1
        beq     htlscat
        lda     #GS_CHASE
        .byte   $2C
htlscat:
        lda     #GS_SCATTER
        sta     astate+1,x
        lda     #DIR_UP                 ; still travelling up as it emerges
        sta     adir+1,x
        lda     #0
        sta     afrac+1,x
        jmp     htnext

htenter:                                ; eyes drop back in and revive
        lda     ayhi+1,x
        cmp     #11*8+4
        bcs     htedone
        inc     ayhi+1,x
        inc     ayhi+1,x
        jmp     htnext
htedone:
        lda     #GS_LEAVE               ; revived, and straight back out
        sta     astate+1,x
        jmp     htnext

; housedot: a dot was eaten -- the house release counter, and the reset of
; the global timer above.
housedot:
        inc     dotseaten
        lda     #0
        sta     nodot
        rts

; houseload: copy this board's release thresholds into the live pair the
; global timer is allowed to lower.
houseload:
        ldx     #3
:       lda     housedots,x
        sta     housedots2,x
        lda     housetime,x
        sta     housetime2,x
        dex
        bpl     :-
        lda     #0
        sta     nodot
        rts

; elroycheck: Bruiser speeds up as the board empties.
elroycheck:
        lda     #0
        sta     elroy
        lda     board
        cmp     #11
        bcc     :+
        lda     #10
:       asl     a
        clc
        adc     #20
        sta     tmp
        lda     dotsleft
        cmp     tmp
        bcs     eldone
        lda     #1
        sta     elroy
        lda     tmp
        lsr     a
        cmp     dotsleft
        bcc     eldone
        lda     #2
        sta     elroy
eldone: rts

        .segment "RODATA"

; scatter corners, one per ghost: top right, top left, bottom right,
; bottom left -- the arcade's assignment, which is why two ghosts sweep
; past each other at the start of every scatter.
cornerx: .byte  25, 2, 25, 2
cornery: .byte  0, 0, 21, 21

; dots eaten before each ghost may leave, and the frames it must wait
; anyway -- the second is what staggers them when the board opens.
housedots: .byte 0, 0, 20, 45
housetime: .byte 0, 30, 150, 250

; eight phases a board group, alternating scatter and chase, in frames
phtab:
        .word   420, 1200, 420, 1200, 300, 1200, 300, $FFFF
        .word   420, 1200, 420, 1200, 300, $FFFF, $FFFF, $FFFF
        .word   300, 1200, 300, 1200, 300, $FFFF, $FFFF, $FFFF

; frightened time per board in units of 4 frames: 6s, 5s, 4s, 3s, 2s, 5s,
; 2s, 2s, 1s, 5s, 2s, 1s, 1s, 3s, 1s, 1s, none, 1s, then none at all
frtab:  .byte   90, 75, 60, 45, 30, 75, 30, 30, 15, 75
        .byte   30, 15, 15, 45, 15, 15, 0, 15, 0, 0, 0

        .segment "CODE"
