; collide.s -- collision, as coordinate maths.
;
; $D01E and $D01F report which *hardware sprite* collided, and under
; multiplexing one hardware sprite is a different object on every raster
; band -- so the latches cannot say which enemy was hit.  They are never
; read here.  A missile is tested against the character grid for settled
; enemies (one gridmap byte) and against sprite coordinates for divers.
;
; Everything runs inside the tick, well before the multiplexer's first
; reposition interrupt of the next frame.

        .segment "ENGINE"

; ---- score table: (type, in the grid?) ----------------------------------
; Every value is fixed, and each is an assertion the audit checks by reading
; `score` either side of a staged kill.
gridscorelo:
        .byte   <50, <80, <150, <0, <0
gridscorehi:
        .byte   >50, >80, >150, >0, >0
flyscorelo:
        .byte   <100, <160, <400, <160, <1000
flyscorehi:
        .byte   >100, >160, >400, >160, >1000
CARRIER_FLY_LO = <800
CARRIER_FLY_HI = >800
TRIO_BONUS_LO  = <1000
TRIO_BONUS_HI  = >1000
SWEEP_SCORE    = 100
PERFECT_LO     = <10000
PERFECT_HI     = >10000

collidetick:
        jsr     hitgrid
        jsr     hitdivers
        jsr     hitplayer
        jmp     hitbeam

; --------------------------------------------------------------------------
; hitgrid -- each live missile against the one gridmap byte under it.
; --------------------------------------------------------------------------
hitgrid:
        ldx     #0
hg1:    lda     mis_on,x
        beq     hg8
        lda     mis_y,x
        lsr     a
        lsr     a
        lsr     a
        sta     scrrow
        cmp     #GRIDMAP_ROW0
        bcc     hg8
        cmp     #GRIDMAP_ROW0+10
        bcs     hg8
        lda     mis_col,x
        sta     scrcol
        stx     misix                   ; not tmp4 -- hitenemy eats every tmp
        jsr     gmptr
        ldy     #0
        lda     (PTR),y
        beq     hg7                     ; empty cell: the missile flies on
        sec
        sbc     #1
        tax                             ; the slot that owns this cell
        jsr     hitenemy
        ; A grid hit consumes the missile, full stop.  (The old tail re-read
        ; `(PTR),y` after hitenemy -- which reaches drawslot and cellptr and so
        ; leaves PTR pointing at screen RAM -- and its `hgkill` branch loaded
        ; zero into A without ever storing it, so the missile was never
        ; cleared and went on to eat the rest of the column.)
        ldx     misix
        lda     #0
        sta     mis_on,x
        jsr     miserase
hg7:    ldx     misix
hg8:    inx
        cpx     #MAXMIS
        bne     hg1
        rts

; --------------------------------------------------------------------------
; hitdivers -- missiles against the sprite objects.  A 16-pixel box either
; way; the art is centred in the sprite box, so the box is the art.
; --------------------------------------------------------------------------
hitdivers:
        ldx     #0
hd1:    lda     mis_on,x
        bne     @far19
        jmp     hd8
@far19:
        ; missile centre, in sprite coordinates
        lda     mis_col,x
        asl     a
        asl     a
        asl     a
        clc
        adc     #27
        sta     tmp0                    ; missile X (low; the window fits 9 bits)
        lda     #0
        adc     #0
        sta     tmp1
        lda     mis_y,x
        clc
        adc     #51
        sta     tmp2                    ; missile Y
        stx     misix                   ; survives hitenemy; tmp4 does not

        ldy     #0
hd2:    lda     enemy_state,y
        cmp     #EST_ENTER
        bcc     hd7
        cmp     #EST_EXPLODE
        bcs     hd7
        lda     enemy_y_msb,y
        bne     hd7
        ; |missileY - (enemyY+10)| < 11
        lda     enemy_y,y
        clc
        adc     #10
        sec
        sbc     tmp2
        bcs     :+
        eor     #$FF
        adc     #1
:       cmp     #11
        bcs     hd7
        ; |missileX - (enemyX+12)| < 9, 9-bit
        lda     enemy_x_lsb,y
        clc
        adc     #12
        sta     tmp3
        lda     enemy_x_msb,y
        adc     #0
        sec
        sbc     tmp1
        bne     hd7                     ; more than 256 apart
        lda     tmp3
        sec
        sbc     tmp0
        bcs     :+
        eor     #$FF
        adc     #1
:       cmp     #9
        bcs     hd7
        ; hit
        sty     tmp5
        ldx     misix
        lda     #0
        sta     mis_on,x
        jsr     miserase
        ldx     tmp5
        jsr     hitenemy
        ldx     misix
        jmp     hd8
hd7:    iny
        cpy     #MAX_ENEMIES
        bne     hd2
        ldx     misix
hd8:    inx
        cpx     #MAXMIS
        beq     @far20
        jmp     hd1
@far20:
        rts

; --------------------------------------------------------------------------
; hitenemy -- X = slot.  One hit point comes off; a Flagship survives its
; first.  Scores by (type, was it in the grid), and handles the rescue, the
; freed captive, the transform trio and the challenging-stage tally.
; --------------------------------------------------------------------------
hitenemy:
        lda     enemy_state,x
        bne     @far21
        jmp     he9
@far21:
        cmp     #EST_EXPLODE
        bne     @far22
        jmp     he9
@far22:
        cmp     #EST_GRID               ; remember where it was hit
        beq     hegrid
        lda     #1
        sta     tmp2                    ; in flight
        jmp     hedmg
hegrid: lda     #0
        sta     tmp2
hedmg:  dec     enemy_hp,x
        beq     hedead
        ; a Flagship's first hit only changes its colour
        lda     #0
        sta     enemy_shape,x           ; and the sprite has to re-derive it
        lda     enemy_state,x
        cmp     #EST_GRID
        bne     he8
        jsr     drawslot                ; repaint it in purple/red
he8:    rts

hedead: lda     challenge
        beq     henorm
        ; challenging stage: every hit is 100, and the tally decides the bonus
        inc     hits
        lda     #<SWEEP_SCORE
        ldy     #>SWEEP_SCORE
        jsr     addscore
        jmp     heboom

henorm: ldy     enemy_type,x
        cpy     #5
        bcc     :+
        ldy     #0
:       lda     tmp2
        beq     hescoregrid
        ; in flight -- and a carrier in flight is worth 800
        lda     enemy_flags,x
        and     #EFL_CARRIES
        beq     :+
        lda     #CARRIER_FLY_LO
        ldy     #CARRIER_FLY_HI
        jsr     addscore
        jsr     rescue
        jmp     heboom
:       ldy     enemy_type,x
        cpy     #5
        bcc     :+
        ldy     #0
:       lda     flyscorelo,y
        pha
        lda     flyscorehi,y
        tay
        pla
        jsr     addscore
        jmp     hetrio
hescoregrid:
        lda     enemy_flags,x
        and     #EFL_CARRIES
        beq     :+
        jsr     freecaptive             ; killed in the grid: it turns hostile
:       ldy     enemy_type,x
        cpy     #5
        bcc     :+
        ldy     #0
:       lda     gridscorelo,y
        pha
        lda     gridscorehi,y
        tay
        pla
        jsr     addscore

hetrio: lda     enemy_flags,x
        and     #EFL_TRANS
        beq     heboom
        dec     triolive
        bne     heboom
        lda     #TRIO_BONUS_LO          ; all three of a trio: a bonus
        ldy     #TRIO_BONUS_HI
        jsr     addscore

heboom: lda     enemy_state,x
        cmp     #EST_GRID
        bne     :+
        stx     tmp3
        jsr     eraseslot
        ldx     tmp3
:       ; An entrant shot down never settles, so nothing else would ever
        ; decrement waveleft and ST_ENTER would wait for it for ever.
        lda     enemy_state,x
        cmp     #EST_ENTER
        bne     :+
        lda     waveleft
        beq     :+
        dec     waveleft
:       lda     #EST_EXPLODE
        sta     enemy_state,x
        lda     #0
        sta     enemy_timer,x
        lda     enemy_flags,x
        and     #<~EFL_BEAM
        sta     enemy_flags,x
        cpx     beamslot
        bne     :+
        lda     #$FF
        sta     beamslot
:       cpx     #FORMATION_SIZE
        bcs     :+
        dec     enemies_left
:       lda     #SFX_EXPLODE
        jsr     sfxstart
he9:    rts

; --------------------------------------------------------------------------
; hitplayer -- enemy bullets, and a diver flown into the fighter.
; --------------------------------------------------------------------------
hitplayer:
        lda     plalive
        bne     @far23
        jmp     hp9
@far23:
        lda     plstate
        beq     @far24
        jmp     hp9
@far24:
        lda     plx                     ; already in window pixels
        sta     tmp0
        ldx     #0
hp1:    lda     bul_on,x
        beq     hp2
        lda     bul_y,x
        cmp     #(PLY - 51 + 2)
        bcc     hp2
        cmp     #(PLY - 51 + 20)
        bcs     hp2
        lda     bul_x,x
        sec
        sbc     tmp0
        bcc     hp2
        cmp     #17
        bcs     hp3
        jsr     bulerase
        lda     #0
        sta     bul_on,x
        dec     bullets_live
        jmp     hpdead
hp3:    ; the second fighter of a pair sits 16 pixels right
        lda     pldual
        beq     hp2
        lda     bul_x,x
        sec
        sbc     tmp0
        cmp     #33
        bcs     hp2
        jsr     bulerase
        lda     #0
        sta     bul_on,x
        dec     bullets_live
        jmp     hpdead
hp2:    inx
        cpx     #MAXBUL
        bne     hp1

        ; An enemy flown into the fighter.  Any airborne enemy is lethal by
        ; contact -- a diver, an entrant sweeping the bottom of the screen,
        ; or one returning to the grid -- exactly as in the arcade.
        ; enemytick already walked the pool this frame and knows whether
        ; anything is down here at all, so the 48-slot scan only runs when
        ; it can find something.
        lda     divelow
        beq     hp9
        lda     plx                     ; the fighter's sprite X, 9-bit, made
        clc                             ; once for the whole scan
        adc     #PLX_BASE
        sta     tmp1
        lda     #0
        adc     #0
        sta     tmp2
        ldy     #0
hp4:    lda     enemy_state,y
        cmp     #EST_ENTER
        bcc     hp5
        cmp     #EST_DOCKED
        bcs     hp5
        lda     enemy_y_msb,y
        bne     hp5
        lda     enemy_y,y
        clc
        adc     #10
        sec
        sbc     #PLY
        bcs     :+
        eor     #$FF
        adc     #1
:       cmp     #14
        bcs     hp5
        ; |enemyX - fighterX| < 18, as a real 9-bit difference.  The old
        ; test required the two X MSBs to be EQUAL, so a fighter pinned near
        ; the right wall (sprite X 256+) could never be rammed by an enemy
        ; at 250 six pixels away.
        lda     enemy_x_lsb,y
        sec
        sbc     tmp1
        sta     tmp3
        lda     enemy_x_msb,y
        sbc     tmp2
        beq     :+                      ; diff is 0..255: |diff| = tmp3
        cmp     #$FF
        bne     hp5                     ; 256 or more apart
        lda     tmp3                    ; negative: two's complement
        eor     #$FF
        clc
        adc     #1
        bcc     :++
:       lda     tmp3
:       cmp     #18
        bcs     hp5
        jmp     hpdead
hp5:    iny
        cpy     #MAX_ENEMIES
        bne     hp4
hp9:    rts
hpdead: jmp     playerhit

; --------------------------------------------------------------------------
; hitbeam -- the tractor beam is a rectangle below its Flagship; touching it
; costs control, not a life directly (player.s finishes the capture).
; --------------------------------------------------------------------------
hitbeam:
        ldx     beamslot
        bmi     hb9
        lda     enemy_flags,x
        and     #EFL_BEAM
        beq     hb9
        lda     plalive
        beq     hb9
        lda     plstate
        bne     hb9
        lda     enemy_y_msb,x
        bne     hb9
        ; the beam reaches 40 pixels below the Flagship's foot
        lda     enemy_y,x
        clc
        adc     #16
        cmp     #PLY+20
        bcs     hb9
        lda     plx
        clc
        adc     #PLX_BASE
        sta     tmp1
        lda     #0
        adc     #0
        cmp     enemy_x_msb,x
        bne     hb9
        lda     enemy_x_lsb,x
        sec
        sbc     tmp1
        bcs     :+
        eor     #$FF
        adc     #1
:       cmp     #20
        bcs     hb9
        jmp     capture
hb9:    rts
