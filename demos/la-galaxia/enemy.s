; enemy.s -- the per-frame enemy update: entrances, dives, escorts, the
; tractor beam, the transforming trios, and the explosions.
;
; This is the heart of the game and the routine the frame budget is really
; about, so it is one flat pass over the structure-of-arrays with no pointer
; chases and no calls per field.  `c64 profile enemytick` prices it; the
; number lives in AUDIT.md.

        .segment "ENGINE"

EXPLODE_FRAMES = 16
BEAM_HOLD      = 110            ; frames a Flagship holds the beam out

expshape:
        .byte   SPR_EXP0, SPR_EXP1, SPR_EXP2, SPR_EXP3

enemytick:
        lda     #0
        sta     divelow
        ldx     #0
; Dead and settled slots are skipped without touching objok: every path that
; puts a slot into EST_DEAD or EST_GRID (etnone, buildformation, and
; spawnsweepers) clears objok as it does so, so re-clearing it here paid five
; cycles per idle slot per frame for a byte that was already zero.
et1:    lda     enemy_state,x
        beq     @skip                  ; EST_DEAD
        cmp     #EST_GRID
        bne     @far3                  ; settled: it is character RAM
@skip:  jmp     etnext
@far3:
        cmp     #EST_EXPLODE
        beq     etboom
        cmp     #EST_ENTER
        beq     etenter
        cmp     #EST_DOCKED
        beq     etdocked
        cmp     #EST_RETURN
        beq     etreturn
        jmp     etdive

; ---- explosion ------------------------------------------------------------
etboom: inc     enemy_timer,x
        lda     enemy_timer,x
        cmp     #EXPLODE_FRAMES
        bcs     etkill
        lsr     a
        lsr     a
        tay
        lda     expshape,y
        sta     enemy_shape,x
        lda     #COL_YELLOW
        sta     enemy_col,x
        jmp     etsnap
etkill: lda     #EST_DEAD
        sta     enemy_state,x
        jmp     etnone

; ---- entrance -------------------------------------------------------------
etenter:
        lda     enemy_timer,x
        beq     etenter2
        dec     enemy_timer,x
        beq     @far4
        jmp     etsnap
@far4:
        jsr     enterstart              ; its stagger is up: on it comes
        jmp     etshape
etenter2:
        jsr     pathstep
        bcs     @far5
        jmp     etshape
@far5:
        jsr     homestep
        bcs     @far6
        jmp     etshape
@far6:
        ; settled
        cpx     #FORMATION_SIZE
        bcs     etkill                  ; a stray has nowhere to settle
        jsr     togrid
        dec     waveleft
        jmp     etnone

; ---- returning to formation ----------------------------------------------
etreturn:
        jsr     homestep
        bcs     @far7
        jmp     etshape
@far7:
        cpx     #FORMATION_SIZE
        bcs     etkill
        jsr     togrid
        jmp     etnone

; ---- the captured fighter, riding its Flagship ---------------------------
etdocked:
        ldy     enemy_slot,x            ; the carrier
        lda     enemy_state,y
        cmp     #EST_DEAD
        beq     etkill
        lda     enemy_x_lsb,y
        sta     enemy_x_lsb,x
        lda     enemy_x_msb,y
        sta     enemy_x_msb,x
        lda     enemy_y,y
        sec
        sbc     #21                     ; docked directly above it
        sta     enemy_y,x
        lda     enemy_y_msb,y
        sbc     #0
        sta     enemy_y_msb,x
        lda     #SPR_CAPTIVE
        sta     enemy_shape,x
        lda     #COL_RED
        sta     enemy_col,x
        jmp     etsnap

; ---- diving ---------------------------------------------------------------
etdive: lda     enemy_timer,x
        beq     etdive2
        dec     enemy_timer,x           ; halted (the beam is out)
        jmp     etshape
etdive2:
        jsr     pathstep
        bcs     etdiveend
        jsr     enemyfire
        jmp     etwrap
etdiveend:
        ; the path ran out.  A Flagship on a capture run halts here and
        ; deploys the beam; everyone else turns for home.
        lda     enemy_flags,x
        and     #EFL_SWEEP
        bne     etkillstray             ; a challenging-stage sweeper leaves
        lda     enemy_type,x
        cmp     #ETY_FLAGSHIP
        bne     etgohome
        lda     enemy_flags,x
        and     #EFL_BEAM
        bne     etgohome                ; the beam has already been and gone
        lda     enemy_y,x
        cmp     #150
        bcc     etgohome                ; too high up to reach the fighter
        lda     enemy_flags,x
        ora     #EFL_BEAM
        sta     enemy_flags,x
        stx     beamslot
        lda     #BEAM_HOLD
        sta     enemy_timer,x
        lda     #SFX_BEAM
        jsr     sfxstart
        jmp     etshape
etgohome:
        lda     enemy_flags,x
        and     #<~EFL_BEAM
        sta     enemy_flags,x
        cpx     #FORMATION_SIZE
        bcs     etkillstray
        lda     #EST_RETURN
        sta     enemy_state,x
        jmp     etshape
etkillstray:
        ; A trio member that flies off rather than being shot still has to
        ; come off the tally: triolive stuck at three and picktransform, which
        ; refuses to start a second trio while one is alive, never fired again
        ; for the rest of the game.
        lda     enemy_flags,x
        and     #EFL_TRANS
        beq     :+
        lda     triolive
        beq     :+
        dec     triolive
:       lda     #EST_DEAD
        sta     enemy_state,x
        jmp     etnone

etwrap: ; an enemy that leaves the bottom of the screen comes back at the top
        lda     enemy_y_msb,x
        beq     etshape
        lda     enemy_y,x
        cmp     #60
        bcs     etshape
        lda     #0
        sta     enemy_y_msb,x
        lda     #30
        sta     enemy_y,x
        cpx     #FORMATION_SIZE
        bcs     etkillstray
        lda     enemy_flags,x
        and     #EFL_SWEEP
        bne     etkillstray
        lda     #EST_RETURN
        sta     enemy_state,x

; ---- shape and colour -----------------------------------------------------
etshape:
        lda     enemy_flags,x
        and     #EFL_TRANS
        bne     etsnap                  ; a trio member carries its own shape
        lda     enemy_state,x
        cmp     #EST_DOCKED
        beq     etsnap
        ; The shape and colour only move when the animation phase flips, once
        ; every 32 frames, or when an object first becomes a sprite (its shape
        ; is zeroed then).  Re-deriving them for every object every frame cost
        ; fifty-five cycles each for an answer that had not changed.
        lda     animdirty
        bne     etsh1
        lda     enemy_shape,x
        bne     etsnap
etsh1:  ldy     enemy_type,x
        cpy     #3
        bcs     etsnap
        lda     animphase
        beq     :+
        lda     typeshape1,y
        bne     :++
:       lda     typeshape0,y
:       sta     enemy_shape,x
        lda     typecolour,y
        cpy     #ETY_FLAGSHIP
        bne     :+
        ldy     enemy_hp,x
        cpy     #2
        bcs     :+
        lda     #FLAG_HURT_COL
:       sta     enemy_col,x

; ---- the multiplexer's snapshot ------------------------------------------
; obj* is what the reposition interrupts read, and it has to be a snapshot:
; the chain plays out across the frame while this loop is still moving
; enemies.  It is taken HERE, in the pass that already holds the object in X
; with its new position just written, rather than in a second walk of the
; pool -- which is what the gather used to be, and cost 2,300 cycles a frame
; to re-derive what this loop already knew.  objok is what muxlist reads.
etsnap: lda     #0
        sta     objok,x
        lda     enemy_y_msb,x
        bne     etnext
        lda     enemy_y,x
        cmp     #30
        bcc     etnext
        cmp     #250
        bcs     etnext
        sta     objy,x
        cmp     #190                    ; far enough down to reach the fighter?
        bcc     ets1
        lda     enemy_state,x
        cmp     #EST_ENTER              ; any airborne enemy is lethal by
        bcc     ets1                    ; contact -- entrant, diver, returner
        cmp     #EST_DOCKED
        bcs     ets1
        inc     divelow
ets1:   ldy     enemy_x_msb,x
        beq     ets2
        cpy     #1
        bne     etnext
        lda     enemy_x_lsb,x
        cmp     #89                     ; 256+88 = 344, the right edge
        bcs     etnext
        bcc     ets3
ets2:   lda     enemy_x_lsb,x
        cmp     #20
        bcc     etnext
ets3:   sta     objx,x
        tya
        sta     objmsb,x
        lda     enemy_shape,x
        sta     objshape,x
        lda     enemy_col,x
        sta     objcol,x
        inc     objok,x
        ; An object that has just become visible joins the multiplexer's list
        ; here.  muxlist used to find it by walking all 49 pool slots every
        ; frame looking for one that had appeared; this pass is already
        ; standing on it.
        lda     inlist,x
        bne     etnext
        ldy     mux_n
        cpy     #MAXOBJ
        bcs     etnext
        txa
        sta     sortix,y
        lda     objy,x
        sta     sortkey,y
        inc     mux_n
        lda     #1
        sta     inlist,x
        bne     etnext                  ; always

etnone: lda     #0
        sta     objok,x

etnext: inx
        cpx     #MAX_ENEMIES
        beq     :+
        jmp     et1
:       lda     #0
        sta     animdirty
        rts

; --------------------------------------------------------------------------
; startdive -- X = slot: break formation.  The block is erased and the
; sprite spawned in the same call, so the enemy is never both or neither.
; --------------------------------------------------------------------------
startdive:
        lda     enemy_state,x
        cmp     #EST_GRID
        bne     sd9
        jsr     tosprite
        lda     divepath
        sta     enemy_path,x
        lda     #0
        sta     enemy_pathix,x
        sta     enemy_pathct,x
        sta     enemy_timer,x
        lda     divespeed
        sta     enemy_speed,x
        ; the capture run is a Flagship's alone, and only when it is not
        ; already carrying a fighter
        lda     enemy_type,x
        cmp     #ETY_FLAGSHIP
        bne     sd1
        lda     enemy_flags,x
        and     #EFL_CARRIES
        bne     sd1
        lda     pldual
        bne     sd1
        lda     #PATH_DIVE2
        sta     enemy_path,x
sd1:    lda     #SFX_DIVE
        jsr     sfxstart
sd9:    rts

; --------------------------------------------------------------------------
; findgrid -- X = start slot: scan forward (wrapping) for a settled enemy.
; Returns carry set with X on the slot, carry clear if nobody is in the grid.
; --------------------------------------------------------------------------
findgrid:
        ldy     #FORMATION_SIZE         ; at most one full lap
fg1:    lda     enemy_state,x
        cmp     #EST_GRID
        beq     fg9
        inx
        cpx     #FORMATION_SIZE
        bcc     :+
        ldx     #0
:       dey
        bne     fg1
        clc
        rts
fg9:    sec
        rts

; --------------------------------------------------------------------------
; pickdive -- choose a settled enemy and send it down, with escorts from
; stage 8.  Called by the play state on the difficulty tier's cadence.
; The old version sampled one random byte and gave up unless it happened to
; name a settled slot -- with 40 valid values in 64 and the grid thinning as
; a stage is cleared, most attempts did nothing and the real dive rate was a
; fraction of d_cad.  The random byte now only picks where the scan starts;
; the dive itself always happens while anyone is left in the grid.
; --------------------------------------------------------------------------
pickdive:
        jsr     rndstir
        and     #63
        cmp     #FORMATION_SIZE
        bcc     :+
        sbc     #24                     ; fold 40-63 into 16-39 (carry is set)
:       tax
        jsr     findgrid
        bcs     :+
        rts                             ; the grid is empty
:       jsr     startdive
        ; a Flagship dives with two Drones flanking it once escorts are on
        lda     escorts
        beq     pdpair
        lda     enemy_type,x
        cmp     #ETY_FLAGSHIP
        bne     pdpair
        stx     tmp0
        ldx     #FORMATION_SIZE-1
pd1:    lda     enemy_state,x
        cmp     #EST_GRID
        bne     pd2
        lda     enemy_type,x
        cmp     #ETY_DRONE
        bne     pd2
        jsr     startdive
        lda     enemy_flags,x
        ora     #EFL_ESCORT
        sta     enemy_flags,x
        inc     tmp1
        lda     tmp1
        cmp     #2
        bcs     pd9
pd2:    dex
        bpl     pd1
        bmi     pd9                     ; always: escorts sent, no extra pair
pdpair: ; §6.4: enemies dive singly or in pairs -- half the dives bring a
        ; second enemy down from somewhere else in the grid.
        jsr     rndstir
        and     #1
        beq     pd9
        jsr     rndstir
        and     #31                     ; always a valid start slot
        tax
        jsr     findgrid
        bcc     pd9
        jsr     startdive
pd9:    lda     #0
        sta     tmp1
        rts

; --------------------------------------------------------------------------
; transform -- turn a diving Sentinel or Drone into three mini-enemies.
; Stages 4-6 onward; destroying all three of one trio pays a bonus.
; --------------------------------------------------------------------------
transform:
        lda     transforms
        bne     @far8
        jmp     tf9
@far8:
        lda     enemy_flags,x
        and     #EFL_TRANS
        beq     @far9
        jmp     tf9
@far9:
        lda     enemy_type,x
        cmp     #ETY_FLAGSHIP
        bne     @far10
        jmp     tf9
@far10:
        ; three free stray slots?
        lda     #0
        sta     tmp1
        ldy     #TRIO_BASE
tf1:    lda     enemy_state,y
        bne     tf2
        inc     tmp1
        lda     tmp1
        cmp     #3
        bcs     tf3
tf2:    iny
        cpy     #SLOT_CAPTIVE
        bne     tf1
        jmp     tf9
; There is room.  Walk slots TRIO_BASE..SLOT_CAPTIVE-1 exactly once, spawning
; into each dead one until three are placed, then stop.  (The old loop reset
; the scan to TRIO_BASE after every spawn and carried a dead `ldy tmp0`; it
; could fall out of the scan with fewer than three placed and still claim a
; full trio.)  tmp0 = the parent, tmp1 = members placed, tmp5 = the slot.
tf3:    stx     tmp0
        lda     #0
        sta     tmp1
        lda     #TRIO_BASE
        sta     tmp5
tf4:    lda     tmp5
        cmp     #SLOT_CAPTIVE
        bcs     tf7                     ; scanned them all
        tay
        lda     enemy_state,y
        bne     tf6                     ; taken
        jsr     spawntrans              ; Y = slot, tmp1 = which of the three
        inc     tmp1
        lda     tmp1
        cmp     #3
        bcs     tf7
tf6:    inc     tmp5
        jmp     tf4

tf7:    ldx     tmp0                    ; the parent is gone: it became three
        lda     #EST_DEAD
        sta     enemy_state,x
        lda     tmp1
        sta     triolive                ; what was really placed, not #3
tf9:    rts

; spawntrans -- Y = the stray slot, tmp0 = the parent, tmp1 = 0, 1 or 2.
; Clobbers X, Y, tmp2-tmp4.
spawntrans:
        ldx     tmp0
        lda     enemy_x_lsb,x
        sta     tmp2
        lda     enemy_x_msb,x
        sta     tmp3
        lda     enemy_y,x
        sta     tmp4
        tya
        tax                             ; X = the stray slot
        lda     #EST_DIVE
        sta     enemy_state,x
        lda     #ETY_TRANS
        sta     enemy_type,x
        lda     tmp2
        sta     enemy_x_lsb,x
        lda     tmp3
        sta     enemy_x_msb,x
        lda     tmp4
        sta     enemy_y,x
        lda     #0
        sta     enemy_y_msb,x
        sta     enemy_x_frac,x
        sta     enemy_y_frac,x
        sta     enemy_pathix,x
        sta     enemy_pathct,x
        sta     enemy_timer,x
        lda     tmp1
        clc
        adc     #PATH_DIVE0
        cmp     #PATH_DIVE2
        bcc     :+
        lda     #PATH_DIVE1
:       sta     enemy_path,x
        lda     divespeed
        sta     enemy_speed,x
        lda     #1
        sta     enemy_hp,x
        lda     #EFL_TRANS
        sta     enemy_flags,x
        ldy     tmp1
        lda     transshape,y
        sta     enemy_shape,x
        lda     transcol,y
        sta     enemy_col,x
        rts

transshape:
        .byte   SPR_TRANS0, SPR_TRANS1, SPR_TRANS2
transcol:
        .byte   COL_LTGREEN, COL_ORANGE, COL_LTBLUE

; --------------------------------------------------------------------------
; enemyfire -- X = slot: a diving enemy takes a shot at the fighter.  Never
; on a challenging stage, where the forty sweep and never fire.
; --------------------------------------------------------------------------
enemyfire:
        lda     challenge
        bne     ef9
        lda     enemy_flags,x
        and     #EFL_BEAM
        bne     ef9
        lda     bullets_live
        cmp     maxbullets
        bcs     ef9
        jsr     rndstir
        cmp     firerate
        bcs     ef9
        jmp     spawnbullet
ef9:    rts
