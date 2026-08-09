; hud.s -- the score, the counters, the panels, and the extra lives.
;
; The HUD lives in the eight bezel columns each side of the 24-column
; playfield, so nothing it draws can ever collide with the formation.  All
; of it is on ordinary letter and digit screen codes, which is what keeps
; `c64 screen` and `wait --text` working on a game with a custom charset.

        .segment "ENGINE"

; ---- addscore -- A = low byte, Y = high byte ----------------------------
addscore:
        clc
        adc     score
        sta     score
        tya
        adc     score+1
        sta     score+1
        lda     score+2
        adc     #0
        sta     score+2
        ; checkextra starts `ldx dip_extra_life`, and hitenemy is holding the
        ; slot it is scoring in X across this call -- so every kill came back
        ; with X = 0 and went on to run the trio tally, the explosion, the
        ; block erase and the enemies_left decrement against slot 0 instead of
        ; the enemy that was actually hit.
        txa
        pha
        jsr     checkextra
        pla
        tax
        rts

; ---- extra lives ---------------------------------------------------------
; Thresholds live in a table with a `dip_extra_life` selector byte, the
; equivalent of the arcade's DIP switches: row 0 awards at 20,000 then every
; 70,000, row 1 at 30,000 then every 100,000, row 2 never.
extrafirst:
        .byte   <20000, <30000, $FF
        .byte   >20000, >30000, $FF
        .byte   ^20000, ^30000, $FF
extrastep:
        .byte   <70000, <100000, 0
        .byte   >70000, >100000, 0
        .byte   ^70000, ^100000, 0

checkextra:
        ldx     dip_extra_life
        cpx     #2
        bcs     ce9
        ; §8: the first award is at 20,000 and every one after it is at a
        ; multiple of 70,000 -- 70,000, 140,000, 210,000.  Adding the step to
        ; the first instead put the second award at 90,000 and the whole
        ; ladder 20,000 too high for ever after.  Accumulated, not multiplied:
        ; there is no multiply in this program.
        ldy     extraidx
        bne     ce0
        lda     extrafirst,x
        sta     tmp0
        lda     extrafirst+3,x
        sta     tmp1
        lda     extrafirst+6,x
        sta     tmp2
        jmp     ce2
ce0:    lda     #0
        sta     tmp0
        sta     tmp1
        sta     tmp2
ce1:    lda     tmp0
        clc
        adc     extrastep,x
        sta     tmp0
        lda     tmp1
        adc     extrastep+3,x
        sta     tmp1
        lda     tmp2
        adc     extrastep+6,x
        sta     tmp2
        dey
        bne     ce1
ce2:    lda     score+2
        cmp     tmp2
        bcc     ce9
        bne     ce3
        lda     score+1
        cmp     tmp1
        bcc     ce9
        bne     ce3
        lda     score
        cmp     tmp0
        bcc     ce9
ce3:    inc     extraidx
        lda     lives
        cmp     #9
        bcs     ce9
        inc     lives
        lda     #SFX_EXTRA
        jmp     sfxstart
ce9:    rts

; ---- decimal rendering ---------------------------------------------------
; Repeated subtraction of the 24-bit powers of ten: six digits, at most nine
; subtractions each, and no divide anywhere.
powlo:  .byte   <100000, <10000, <1000, <100, <10, <1
powmid: .byte   >100000, >10000, >1000, >100, >10, >1
powhi:  .byte   ^100000, ^10000, ^1000, ^100, ^10, ^1

; num2dec -- 24-bit value in tmp0/tmp1/tmp2 -> six screen codes in digbuf
num2dec:
        ldx     #0
n2d1:   lda     #0
        sta     digbuf,x
n2d2:   lda     tmp0
        sec
        sbc     powlo,x
        sta     tmp3
        lda     tmp1
        sbc     powmid,x
        sta     tmp4
        lda     tmp2
        sbc     powhi,x
        bcc     n2d3
        sta     tmp2
        lda     tmp3
        sta     tmp0
        lda     tmp4
        sta     tmp1
        inc     digbuf,x
        jmp     n2d2
n2d3:   lda     digbuf,x
        clc
        adc     #48                     ; screen code of '0'
        sta     digbuf,x
        inx
        cpx     #6
        bne     n2d1
        rts

; The only two digit renderers are putnumall (all six) and putnum3 (the last
; three) at the bottom of this file.  A general `putnum A digits` used to sit
; here and was both unused and wrong -- it indexed `digbuf+6,y`, off the end
; of the eight-byte buffer, instead of `digbuf + 6 - count`.

; ---- drawhud -------------------------------------------------------------
; Repainting the whole panel every frame -- six labels, fifteen digits, three
; num2dec passes -- measured 4,233 cycles, a quarter of an NTSC frame, to
; redraw values that change a few times a second.  Each part is now guarded by
; the value behind it, and hud_dirty forces the lot after a state change has
; cleared the screen.  The guard costs about sixty cycles on a quiet frame.
drawhud:
        lda     hud_dirty
        bne     dhall
        lda     curplayer
        cmp     hs_player
        bne     dhall
        ; The sections fall through in order, so the guard jumps to the
        ; earliest one that has gone stale and everything after it follows.
        ; Order them rarest first -- high score, stage, lives, score -- and a
        ; kill, which is the only common change, costs one num2dec.
        ; ca65 branch range: every one of these is more than 127 bytes from
        ; its target, so the test is inverted over a jmp.
        lda     hiscore
        cmp     hs_hi
        bne     dhjhi
        lda     hiscore+1
        cmp     hs_hi+1
        bne     dhjhi
        lda     hiscore+2
        cmp     hs_hi+2
        beq     dhg1
dhjhi:  jmp     dhhi
dhg1:   lda     stage
        cmp     hs_stage
        beq     dhg2
        jmp     dhstage
dhg2:   lda     lives
        cmp     hs_lives
        beq     dhg3
        jmp     dhlives
dhg3:   lda     score
        cmp     hs_score
        bne     dhjsc
        lda     score+1
        cmp     hs_score+1
        bne     dhjsc
        lda     score+2
        cmp     hs_score+2
        beq     dhg9
dhjsc:  jmp     dhscore
dhg9:   rts

; ---- the labels, and everything after them ------------------------------
dhall:  lda     #0
        sta     hud_dirty
        lda     #COL_WHITE
        sta     txtcol
        lda     #1
        sta     scrrow
        lda     #LCOL
        sta     scrcol
        lda     curplayer
        sta     hs_player
        beq     :+
        lda     #<t_jug2
        ldx     #>t_jug2
        bne     :++
:       lda     #<t_jug1
        ldx     #>t_jug1
:       jsr     prstr

        lda     #COL_CYAN
        sta     txtcol
        lda     #3
        sta     scrrow
        lda     #LCOL
        sta     scrcol
        lda     #<t_puntos
        ldx     #>t_puntos
        jsr     prstr

        lda     #COL_CYAN
        sta     txtcol
        lda     #6
        sta     scrrow
        lda     #LCOL
        sta     scrcol
        lda     #<t_record
        ldx     #>t_record
        jsr     prstr

        lda     #COL_CYAN
        sta     txtcol
        lda     #1
        sta     scrrow
        lda     #RCOL+2
        sta     scrcol
        lda     #<t_etapa
        ldx     #>t_etapa
        jsr     prstr

        lda     #COL_CYAN
        sta     txtcol
        lda     #4
        sta     scrrow
        lda     #RCOL+2
        sta     scrcol
        lda     #<t_naves
        ldx     #>t_naves
        jsr     prstr

dhhi:   lda     hiscore
        sta     hs_hi
        sta     tmp0
        lda     hiscore+1
        sta     hs_hi+1
        sta     tmp1
        lda     hiscore+2
        sta     hs_hi+2
        sta     tmp2
        jsr     num2dec
        lda     #7
        sta     scrrow
        lda     #LCOL
        sta     scrcol
        lda     #COL_YELLOW
        sta     txtcol
        jsr     putnumall

dhstage:
        lda     stage
        sta     hs_stage
        sta     tmp0
        lda     #0
        sta     tmp1
        sta     tmp2
        jsr     num2dec
        lda     #2
        sta     scrrow
        lda     #RCOL+3
        sta     scrcol
        lda     #COL_WHITE
        sta     txtcol
        jsr     putnum3

dhlives:
        lda     lives
        sta     hs_lives
        lda     #5
        sta     scrrow
        lda     #COL_WHITE
        sta     txtcol
        ldx     #0
dh1:    txa
        clc
        adc     #RCOL+2
        sta     scrcol
        cpx     lives
        bcs     :+
        lda     #GLY_LIFE
        bne     :++
:       lda     #32
:       stx     tmp5
        jsr     putcell
        ldx     tmp5
        inx
        cpx     #5
        bne     dh1

dhscore:
        lda     score
        sta     hs_score
        sta     tmp0
        lda     score+1
        sta     hs_score+1
        sta     tmp1
        lda     score+2
        sta     hs_score+2
        sta     tmp2
        jsr     num2dec
        lda     #4
        sta     scrrow
        lda     #LCOL                   ; six digits in columns 0-5: LCOL+1
        sta     scrcol                  ; ran the last one into the grille
        lda     #COL_WHITE
        sta     txtcol
        jmp     putnumall

; putnumall -- all six digits
putnumall:
        jsr     cellptr
        ldy     #0
pna1:   lda     digbuf,y
        sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        iny
        cpy     #6
        bne     pna1
        rts

; putnum3 -- the last three digits
putnum3:
        jsr     cellptr
        ldy     #0
pn31:   lda     digbuf+3,y
        sta     (PTR),y
        lda     txtcol
        sta     (CPTR),y
        iny
        cpy     #3
        bne     pn31
        rts

; ---- announcetext -- ETAPA n, or the challenging stage's banner ---------
ANNROW = 13
ANNCOL = PFCOL + 2

announcetext:
        lda     #ANNROW
        sta     scrrow
        lda     #ANNCOL
        sta     scrcol
        lda     #COL_YELLOW
        sta     txtcol
        lda     challenge
        beq     at1
        lda     #<t_desafio
        ldx     #>t_desafio
        jsr     prstr
        rts
at1:    lda     #<t_etapa
        ldx     #>t_etapa
        jsr     prstr
        lda     stage
        sta     tmp0
        lda     #0
        sta     tmp1
        sta     tmp2
        jsr     num2dec
        lda     #ANNCOL+6
        sta     scrcol
        jsr     putnum3
        rts

clearplaytext:
        lda     #ANNROW
        sta     scrrow
        lda     #PFCOL
        sta     scrcol
        ldx     #PFW
        jmp     blankrun

blankrun:
        stx     tmp5
        jsr     pfptr
        ldy     #0
br1:    lda     (BGP),y
        sta     (PTR),y
        lda     (BGC),y
        sta     (CPTR),y
        iny
        cpy     tmp5
        bne     br1
        rts

; ---- resulttext -- the challenging stage's result panel ----------------
resulttext:
        lda     #ANNROW-2
        sta     scrrow
        lda     #ANNCOL
        sta     scrcol
        lda     #COL_CYAN
        sta     txtcol
        lda     #<t_aciertos
        ldx     #>t_aciertos
        jsr     prstr
        lda     hits
        sta     tmp0
        lda     #0
        sta     tmp1
        sta     tmp2
        jsr     num2dec
        lda     #ANNCOL+9
        sta     scrcol
        lda     #COL_WHITE
        sta     txtcol
        jsr     putnum3
        lda     #ANNCOL+12
        sta     scrcol
        lda     #<t_de40
        ldx     #>t_de40
        jsr     prstr

        lda     perfect
        beq     rt1
        lda     #ANNROW
        sta     scrrow
        lda     #ANNCOL+4
        sta     scrcol
        lda     #COL_YELLOW
        sta     txtcol
        lda     #<t_perfecto
        ldx     #>t_perfecto
        jsr     prstr
        lda     #ANNROW+2
        sta     scrrow
        lda     #ANNCOL+2
        sta     scrcol
        lda     #COL_WHITE
        sta     txtcol
        lda     #<t_bonif
        ldx     #>t_bonif
        jmp     prstr
rt1:    rts

; ---- gameovertext --------------------------------------------------------
gameovertext:
        lda     #ANNROW
        sta     scrrow
        lda     #ANNCOL+2
        sta     scrcol
        lda     #COL_RED
        sta     txtcol
        lda     #<t_gameover
        ldx     #>t_gameover
        jmp     prstr

; ---- the high score ------------------------------------------------------
hiscoreinit:
        lda     #<20000
        sta     hiscore
        lda     #>20000
        sta     hiscore+1
        lda     #^20000
        sta     hiscore+2
        rts

savehiscore:
        lda     score+2
        cmp     hiscore+2
        bcc     sh9
        bne     sh1
        lda     score+1
        cmp     hiscore+1
        bcc     sh9
        bne     sh1
        lda     score
        cmp     hiscore
        bcc     sh9
sh1:    lda     score
        sta     hiscore
        lda     score+1
        sta     hiscore+1
        lda     score+2
        sta     hiscore+2
sh9:    rts
