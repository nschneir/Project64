; stage.s -- stage flow, the difficulty tiers, and the challenging stages.
;
; Challenging stage <=> stage mod 4 == 3, so 3, 7, 11, 15 ...  The tiers
; below describe the ordinary stages between them, and they are a *table*
; indexed by tier rather than a chain of compares: that is what makes stage
; 255 read the same row as stage 11 and still play, instead of falling off
; the end of a comparison ladder.

        .segment "ENGINE"

TIER_EARLY  = 0                 ; stages 1-2
TIER_TRANS  = 1                 ; stages 4-6: transforming enemies
TIER_ESCORT = 2                 ; stages 8-10: escorts and multi-shot dives
TIER_MAX    = 3                 ; stage 11 and up: everything clamped
TIER_CHAL   = 4                 ; a challenging stage

; Retuned on the maintainer's verdict that the game was far too easy: the
; old cadences were dive *attempts* that mostly missed (pickdive sampled a
; random slot and gave up), and firerate 3/256 per diver per frame meant a
; bullet every few hundred frames.  pickdive now always finds a settled
; enemy, so d_cad is the real gap between dives; §7's ceilings (2 bullets in
; flight at stages 1-2, 8 from stage 8, bullet speed 2.0 rising to 3.0)
; still bound d_maxbul and d_bulspeed.
;                    early trans escort max  chal
d_speed:    .byte   0,    1,    1,    2,    2
d_cad:      .byte   70,   52,   38,   26,   255
d_maxbul:   .byte   2,    4,    8,    8,    0
d_firerate: .byte   10,   14,   20,   26,   0
d_bulspeed: .byte   2,    2,    2,    3,    0
d_escorts:  .byte   0,    0,    1,    1,    0
d_trans:    .byte   0,    1,    1,    1,    0
d_path:     .byte   PATH_DIVE0, PATH_DIVE0, PATH_DIVE1, PATH_DIVE1, PATH_SWEEP0

; ---- setdifficulty -- from `stage`, fill the tier and its parameters ----
setdifficulty:
        lda     stage
        and     #3
        cmp     #3
        bne     sdnorm
        lda     #1
        sta     challenge
        lda     #TIER_CHAL
        jmp     sdset
sdnorm: lda     #0
        sta     challenge
        lda     stage
        cmp     #3
        bcc     sdearly
        cmp     #7
        bcc     sdtrans
        cmp     #11
        bcc     sdescort
        lda     #TIER_MAX
        jmp     sdset
sdearly:
        lda     #TIER_EARLY
        jmp     sdset
sdtrans:
        lda     #TIER_TRANS
        jmp     sdset
sdescort:
        lda     #TIER_ESCORT
sdset:  sta     tier
        tax
        lda     d_speed,x
        sta     divespeed
        lda     d_cad,x
        sta     divecad
        sta     divetimer
        lda     d_maxbul,x
        sta     maxbullets
        lda     d_firerate,x
        sta     firerate
        lda     d_bulspeed,x
        sta     bulspeed
        lda     d_escorts,x
        sta     escorts
        lda     d_trans,x
        sta     transforms
        lda     d_path,x
        sta     divepath
        rts

; ==========================================================================
; startgame -- a new game, from the title screen
; ==========================================================================
startgame:
        lda     #0
        sta     score
        sta     score+1
        sta     score+2
        sta     extraidx
        sta     curplayer
        sta     altstarted
        lda     #3
        sta     lives
        lda     stage_select
        bne     :+
        lda     #1
:       sta     stage
        jsr     playerinit
        jsr     shotsinit
        lda     #$FF
        sta     beamslot
        jmp     newstage

; ---- newstage ------------------------------------------------------------
newstage:
        jsr     setdifficulty
        jsr     buildformation
        jsr     wavereset
        jsr     clearshots
        lda     #0
        sta     hits
        sta     perfect
        sta     breathe
        sta     gridexp
        sta     redrawslot
        lda     #$FF
        sta     beamslot
        lda     #ST_ANNOUNCE
        jmp     setstate

; ---- nextstage -- clamp at 255 rather than roll over --------------------
nextstage:
        lda     stage
        cmp     #255
        beq     :+
        inc     stage
:       jmp     newstage

; ==========================================================================
; The state handlers.  Each is entered once per tick; `stinit` is set on the
; first tick after a transition.
; ==========================================================================

; ---- ST_ANNOUNCE: ETAPA n, or the challenging stage's banner ------------
stannounce:
        lda     stinit
        beq     sa0
        lda     #0
        sta     stinit
        jsr     screenstart             ; rebuilt over the next dozen frames
        lda     #1
        sta     sbactive
        lda     #120
        sta     sttimer
        lda     #0
        sta     sttimer+1
sa0:    lda     sbactive
        beq     sa1
        jsr     screenstep
        bcc     sa9                     ; still rebuilding
        lda     #0
        sta     sbactive
        lda     #1
        sta     hud_dirty
        jsr     drawhud
        jsr     announcetext
        rts
sa1:    jsr     formtick
        dec     sttimer
        bne     sa9
        jsr     clearplaytext
        lda     #ST_ENTER
        jsr     setstate
sa9:    rts

; ---- ST_ENTER: the five groups fly on -----------------------------------
stenter:
        lda     stinit
        beq     se1
        lda     #0
        sta     stinit
        lda     challenge
        beq     se1
        jsr     spawnsweepers
        lda     #ST_PLAY
        jsr     setstate
        rts
se1:    jsr     wavetick
        jsr     enemytick
        jsr     playertick
        jsr     collidetick
        jsr     shotstick
        jsr     formtick
        jsr     drawhud
        lda     wave
        cmp     #5
        bcc     se9
        lda     waveleft
        bne     se9
        lda     #ST_PLAY
        jsr     setstate
se9:    rts

; ---- ST_PLAY -------------------------------------------------------------
stplay: lda     stinit
        beq     sp1
        lda     #0
        sta     stinit
sp1:    jsr     enemytick
        jsr     playertick
        jsr     collidetick
        jsr     shotstick
        jsr     formtick
        jsr     drawhud

        lda     challenge
        bne     spchal

        ; send someone down on the tier's cadence
        lda     divetimer
        beq     :+
        dec     divetimer
        jmp     sp2
:       lda     divecad
        sta     divetimer
        jsr     pickdive
sp2:    ; A diving enemy may transform, one trio at a time and only from stage
        ; 4.  The old gate looked once every 64 frames and only counted a
        ; diver already between Y 90 and 180, two conditions that almost never
        ; coincided -- six hundred frames of stage 4 produced no trio at all.
        lda     transforms
        beq     sp3
        lda     frames
        and     #$0F
        bne     sp3
        jsr     picktransform
sp3:    lda     enemies_left
        bne     sp8
        lda     #ST_CLEAR
        jsr     setstate
        rts

spchal: ; the stage ends when the last sweeper has left, hit or not
        jsr     sweeptick
        lda     sweepnext
        cmp     #FORMATION_SIZE
        bcc     sp8                     ; still some to send on
        jsr     countlive
        bne     sp8
        lda     #ST_RESULT
        jsr     setstate
        rts

sp8:    lda     plalive
        bne     sp9
        lda     plstate
        bne     sp9
        lda     #ST_DEAD
        jsr     setstate
sp9:    rts

; ---- countlive -- Z set when nothing is in the air ----------------------
countlive:
        ldx     #0
        ldy     #0
cl1:    lda     enemy_state,x
        beq     :+
        iny
:       inx
        cpx     #MAX_ENEMIES
        bne     cl1
        tya
        rts

; ---- ST_CLEAR ------------------------------------------------------------
stclear:
        lda     stinit
        beq     sc1x
        lda     #0
        sta     stinit
        lda     #90
        sta     sttimer
sc1x:   jsr     playertick
        jsr     shotstick
        jsr     drawhud
        dec     sttimer
        bne     sc9x
        jmp     nextstage
sc9x:   rts

; ---- ST_DEAD -------------------------------------------------------------
stdead: lda     stinit
        beq     sd1x
        lda     #0
        sta     stinit
        jsr     clearshots
        lda     #70
        sta     sttimer
sd1x:   jsr     enemytick
        jsr     formtick
        jsr     drawhud
        dec     sttimer
        bne     sd9x
        lda     lives
        beq     sdover
        jsr     playerinit
        lda     #ST_PLAY
        jsr     setstate
        rts
sdover: lda     #ST_OVER
        jsr     setstate
sd9x:   rts

; ---- ST_OVER -------------------------------------------------------------
stover: lda     stinit
        beq     so1
        lda     #0
        sta     stinit
        jsr     gameovertext
        jsr     savehiscore
        lda     #180
        sta     sttimer
so1:    dec     sttimer
        bne     so9
        jsr     coldenter               ; §1a: the attract loop returns to
                                        ; the cold open, not to the title
so9:    rts

; ---- ST_RESULT: the challenging stage's panel ---------------------------
stresult:
        lda     stinit
        beq     sr1
        lda     #0
        sta     stinit
        lda     hits
        cmp     #FORMATION_SIZE
        bcc     :+
        lda     #1
        sta     perfect
        lda     #PERFECT_LO
        ldy     #PERFECT_HI
        jsr     addscore
:       jsr     resulttext
        lda     #200
        sta     sttimer
sr1:    jsr     drawhud
        dec     sttimer
        bne     sr9
        jmp     nextstage
sr9:    rts

; ==========================================================================
; spawnsweepers -- a challenging stage: forty enemies cross the screen in
; scripted patterns and never fire.
; ==========================================================================
sweeppath:
        .byte   PATH_SWEEP0, PATH_SWEEP1, PATH_SWEEP2
sweepx: .byte   40, 300-256, 40
sweepmsb: .byte 0, 1, 0
sweepy: .byte   70, 90, 120

; The forty are launched one at a time, nine frames apart, exactly as the
; entrance is: a per-enemy stagger byte cannot express the 350-frame spread
; forty sweepers need, and forty in the air at once is neither what six
; multiplexed registers can draw nor what a 1 MHz frame can move.
SWEEP_GAP = 5

spawnsweepers:
        ldx     #0
        lda     #EST_DEAD               ; = 0, which objok needs too:
ss1:    sta     enemy_state,x           ; enemytick no longer re-clears objok
        sta     objok,x                 ; for dead slots every frame
        inx
        cpx     #MAX_ENEMIES
        bne     ss1
        lda     #0
        sta     sweepnext
        sta     wavetimer
        sta     enemies_left
        rts

; ---- sweeptick -- send the next sweeper on when its turn comes ----------
sweeptick:
        lda     sweepnext
        cmp     #FORMATION_SIZE
        bcs     sw9
        lda     wavetimer
        bne     sw1
        ldx     sweepnext
        jsr     armsweeper
        inc     sweepnext
        lda     #SWEEP_GAP
        sta     wavetimer
        rts
sw1:    dec     wavetimer
sw9:    rts

; ---- armsweeper -- X = slot -------------------------------------------
armsweeper:
        lda     #EST_DIVE
        sta     enemy_state,x
        txa
        and     #3
        cmp     #3
        bcc     :+
        lda     #0
:       tay
        lda     sweeppath,y
        sta     enemy_path,x
        lda     sweepx,y
        sta     enemy_x_lsb,x
        lda     sweepmsb,y
        sta     enemy_x_msb,x
        lda     sweepy,y
        sta     enemy_y,x
        lda     #0
        sta     enemy_y_msb,x
        sta     enemy_pathix,x
        sta     enemy_pathct,x
        sta     enemy_x_frac,x
        sta     enemy_y_frac,x
        sta     enemy_timer,x
        sta     enemy_shape,x           ; force one shape refresh
        lda     #EFL_SWEEP
        sta     enemy_flags,x
        lda     #1
        sta     enemy_hp,x
        lda     #ETY_DRONE
        sta     enemy_type,x
        lda     #2
        sta     enemy_speed,x           ; the challenging stages sweep faster
        rts

; ==========================================================================
; picktransform -- a diving Sentinel or Drone becomes three mini-enemies.
; ==========================================================================
picktransform:
        lda     triolive
        bne     pt9x
        ldx     #0
ptx1:   lda     enemy_state,x
        cmp     #EST_DIVE
        bne     ptx2
        lda     enemy_flags,x
        and     #EFL_TRANS|EFL_SWEEP|EFL_CARRIES
        bne     ptx2
        lda     enemy_type,x
        cmp     #ETY_FLAGSHIP
        beq     ptx2
        lda     enemy_y,x
        cmp     #90
        bcc     ptx2
        cmp     #180
        bcs     ptx2
        jmp     transform
ptx2:   inx
        cpx     #FORMATION_SIZE
        bne     ptx1
pt9x:   rts

; ==========================================================================
; loselife
; ==========================================================================
loselife:
        lda     lives
        beq     ll9
        dec     lives
ll9:    lda     #0
        sta     pldual
        rts
