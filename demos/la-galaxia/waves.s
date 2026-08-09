; waves.s -- the entrance, and the trajectory-LUT player.
;
; Every stage opens with the forty enemies flying on in five groups of
; eight.  A group launches its members six frames apart, so the group flies
; its shape as a stream, and the next group launches before the last one has
; settled -- which is both what the arcade does and what puts sixteen
; objects in the air at once, the load the multiplexer is specified for.
;
; Nothing here computes a sine.  A heading is an index into the velocity
; tables in traj.inc and a path is a run-length list of (heading, frames), so
; flying one is a 24-bit add per axis per frame.

        .segment "ENGINE"

; These two set how many entrants are in the air at once, and that number is
; bounded by the frame budget.  A member is airborne for its path plus about
; twenty frames of homing (~120 frames); launching one every ENTRY_STAGGER
; frames puts roughly 120/ENTRY_STAGGER in flight at the peak.  Measured on
; the machine with tick_overrun and tick_endline (after the raster chain's
; phantom-frame bug was fixed -- the earlier "overruns from twelve objects"
; numbers were taken with that bug live and counted frames that never
; overran): at 12/120 the peak is ten in the air and the worst entrance tick
; ends by ~line 240 with tick_overrun 0.  The arcade's own 6/90 pacing wants
; ~sixteen at once, which the frame will not yet pay for; the maintainer has
; ruled density acceptable and gameplay pressure the priority.
WAVE_GAP    = 120               ; frames between group launches
ENTRY_STAGGER = 12              ; frames between the members of a group

; Which entrance path each successive group flies.  Groups 4 and 5 both come
; up from the bottom, so launching the five in table order put fourteen
; objects inside sixty raster lines at the foot of the screen and the
; multiplexer overflowed by four -- six registers cannot hold fourteen
; sprites in three bands.  Alternating top and bottom entries keeps two
; overlapping groups in different halves of the screen.
waveorder:  .byte   PATH_PATH0, PATH_PATH3, PATH_PATH1, PATH_PATH4, PATH_PATH2

; ---- wavereset -- arm the entrance for a new stage -----------------------
wavereset:
        lda     #0
        sta     wave
        sta     wavemem
        sta     wavetimer
        sta     wavetimer+1
        lda     #FORMATION_SIZE
        sta     waveleft
        rts

; ---- wavetick -- one entrant every ENTRY_STAGGER frames -----------------
; Members used to be armed eight at a time and held back by a per-enemy
; countdown, which meant enemytick paid the full dispatch, snapshot and loop
; cost -- some 57 cycles -- for every one of the two dozen enemies that were
; only waiting their turn.  They are launched one at a time instead, so an
; enemy is only in the pool once it is really flying.
wavetick:
        lda     wave
        cmp     #5
        bcs     wt2                     ; all forty are away
        lda     wavetimer
        bne     wt1
        jsr     launchone
        inc     wavemem
        lda     wavemem
        cmp     #8
        bcc     :+
        lda     #0
        sta     wavemem
        inc     wave
        lda     #WAVE_GAP - 7*ENTRY_STAGGER
        bne     wtset                   ; the extra pause between groups
:       lda     #ENTRY_STAGGER
wtset:  sta     wavetimer
        jmp     wt2
wt1:    dec     wavetimer
wt2:    rts

; ---- launchone -- put slot wave*8 + wavemem on its group's start point ---
launchone:
        lda     wave
        asl     a
        asl     a
        asl     a
        clc
        adc     wavemem
        tax
        lda     enemy_state,x
        cmp     #EST_DEAD
        bne     lo9                     ; already shot down or in the air
        lda     #EST_ENTER
        sta     enemy_state,x
        ldy     wave
        lda     waveorder,y
        sta     enemy_path,x
        lda     #0
        sta     enemy_pathix,x
        sta     enemy_pathct,x
        sta     enemy_timer,x
        lda     divespeed
        sta     enemy_speed,x
        lda     #0
        sta     enemy_shape,x           ; force one shape refresh
        jsr     enterstart
lo9:    rts

; ---- enterstart -- X = slot: put it on its wave's start point ------------
enterstart:
        ldy     enemy_path,x
        lda     wavestartx,y
        sta     enemy_x_lsb,x
        lda     wavestartmsb,y
        sta     enemy_x_msb,x
        lda     wavestarty,y
        sta     enemy_y,x
        lda     #0
        sta     enemy_y_msb,x
        sta     enemy_x_frac,x
        sta     enemy_y_frac,x
        rts

; --------------------------------------------------------------------------
; pathload -- X = slot: point PTR at this enemy's path table.
; --------------------------------------------------------------------------
pathload:
        ldy     enemy_path,x
        lda     pathtablo,y
        sta     PTR
        lda     pathtabhi,y
        sta     PTR+1
        rts

; --------------------------------------------------------------------------
; pathstep -- X = slot: advance one frame along the current path.  Returns
; with carry set when the path has run out and the caller should home.
; --------------------------------------------------------------------------
pathstep:
        lda     enemy_pathix,x
        cmp     #$FF
        bne     :+
        jmp     psdone                  ; already homing
:       lda     enemy_pathct,x
        beq     :+
        jmp     psfly                   ; mid-segment: the cache is warm
:       ; load the next segment
        jsr     pathload
        ldy     enemy_pathix,x
        lda     (PTR),y
        cmp     #$FF
        beq     psend
        sta     enemy_head,x
        iny
        lda     (PTR),y
        sta     enemy_pathct,x
        iny
        tya
        sta     enemy_pathix,x
        ; Cache the segment's velocity, sign-extended, on the enemy itself.
        ; Heading and speed cannot change until the next segment, so velload
        ; and the two sign-extensions run once per segment instead of once
        ; per frame.
        jsr     velload
        lda     vxlo
        sta     enemy_vxl,x
        lda     vxhi
        sta     enemy_vxh,x
        ldy     #0
        bit     vxhi
        bpl     :+
        dey
:       tya
        sta     enemy_vxs,x
        lda     vylo
        sta     enemy_vyl,x
        lda     vyhi
        sta     enemy_vyh,x
        ldy     #0
        bit     vyhi
        bpl     :+
        dey
:       tya
        sta     enemy_vys,x
psfly:  dec     enemy_pathct,x
        ; movebyvel, inlined: it is called from nowhere else and this is the
        ; hottest path in the game -- once per flying object per frame.
        lda     enemy_x_frac,x
        clc
        adc     enemy_vxl,x
        sta     enemy_x_frac,x
        lda     enemy_x_lsb,x
        adc     enemy_vxh,x
        sta     enemy_x_lsb,x
        lda     enemy_x_msb,x
        adc     enemy_vxs,x
        sta     enemy_x_msb,x
        lda     enemy_y_frac,x
        clc
        adc     enemy_vyl,x
        sta     enemy_y_frac,x
        lda     enemy_y,x
        adc     enemy_vyh,x
        sta     enemy_y,x
        lda     enemy_y_msb,x
        adc     enemy_vys,x
        sta     enemy_y_msb,x
        clc
        rts
psend:  lda     #$FF
        sta     enemy_pathix,x
psdone: sec
        rts

; --------------------------------------------------------------------------
; velload -- X = slot: put this enemy's velocity into vxlo/vxhi/vylo/vyhi.
; Three speed tiers, each its own straight-line copy: a table-of-tables would
; cost a pointer chase per axis per enemy per frame.
; --------------------------------------------------------------------------
velload:
        ldy     enemy_head,x
        lda     enemy_speed,x
        beq     vl0
        cmp     #1
        beq     vl1
        lda     v2xlo,y
        sta     vxlo
        lda     v2xhi,y
        sta     vxhi
        lda     v2ylo,y
        sta     vylo
        lda     v2yhi,y
        sta     vyhi
        rts
vl1:    lda     v1xlo,y
        sta     vxlo
        lda     v1xhi,y
        sta     vxhi
        lda     v1ylo,y
        sta     vylo
        lda     v1yhi,y
        sta     vyhi
        rts
vl0:    lda     v0xlo,y
        sta     vxlo
        lda     v0xhi,y
        sta     vxhi
        lda     v0ylo,y
        sta     vylo
        lda     v0yhi,y
        sta     vyhi
        rts

; --------------------------------------------------------------------------
; homestep -- X = slot: fly straight at the grid cell this enemy belongs to
; at three pixels a frame, and settle when it is within tolerance.  Returns
; carry set once it has settled.
; --------------------------------------------------------------------------
HOMESPD = 3

homestep:
        ; The target is the slot's grid cell in pixels, and re-deriving it
        ; through slotcell and three shifts every frame cost about ninety
        ; cycles per homing enemy for an answer that only changes when the
        ; grid breathes.  homeok says the cached one is good; formtick clears
        ; every flag when gridexp moves.
        lda     homeok,x
        beq     hsmake
        lda     homex,x
        sta     tmp0
        lda     homexm,x
        sta     tmp1
        lda     homey,x
        sta     tmp2
        jmp     hsgo
hsmake: stx     tmp3
        jsr     slotcell                ; where the block wants to be
        ldx     tmp3
        lda     scrcol
        asl     a
        asl     a
        asl     a
        sta     tmp0
        lda     #0
        rol     a
        sta     tmp1
        lda     tmp0
        clc
        adc     #20
        sta     tmp0
        bcc     :+
        inc     tmp1
:       lda     scrrow                  ; target Y
        asl     a
        asl     a
        asl     a
        clc
        adc     #49
        sta     tmp2
        lda     tmp0
        sta     homex,x
        lda     tmp1
        sta     homexm,x
        lda     tmp2
        sta     homey,x
        lda     #1
        sta     homeok,x

hsgo:

        lda     #0
        sta     tmp4                    ; 1 = X has arrived
        sta     tmp5                    ; 1 = Y has arrived

        ; ---- X ----
        lda     enemy_x_msb,x
        cmp     tmp1
        bne     hsx
        lda     enemy_x_lsb,x
        sec
        sbc     tmp0
        bcs     hsxpos
        eor     #$FF
        adc     #1
hsxpos: cmp     #HOMESPD+1
        bcs     hsx
        inc     tmp4                    ; close enough: snap
        lda     tmp0
        sta     enemy_x_lsb,x
        lda     tmp1
        sta     enemy_x_msb,x
        jmp     hsy
hsx:    ; step towards it
        lda     enemy_x_msb,x
        cmp     tmp1
        bcc     hsxup
        bne     hsxdn
        lda     enemy_x_lsb,x
        cmp     tmp0
        bcc     hsxup
hsxdn:  lda     enemy_x_lsb,x
        sec
        sbc     #HOMESPD
        sta     enemy_x_lsb,x
        bcs     hsy
        dec     enemy_x_msb,x
        jmp     hsy
hsxup:  lda     enemy_x_lsb,x
        clc
        adc     #HOMESPD
        sta     enemy_x_lsb,x
        bcc     hsy
        inc     enemy_x_msb,x

        ; ---- Y ----
hsy:    lda     enemy_y_msb,x
        bne     hsystep
        lda     enemy_y,x
        sec
        sbc     tmp2
        bcs     hsypos
        eor     #$FF
        adc     #1
hsypos: cmp     #HOMESPD+1
        bcs     hsystep
        inc     tmp5
        lda     tmp2
        sta     enemy_y,x
        jmp     hs9
hsystep:
        lda     enemy_y_msb,x
        bne     hsyup                   ; above the screen: come down
        lda     enemy_y,x
        cmp     tmp2
        bcc     hsyup
        sec
        sbc     #HOMESPD
        sta     enemy_y,x
        jmp     hs9
hsyup:  lda     enemy_y,x
        clc
        adc     #HOMESPD
        sta     enemy_y,x
        bcc     hs9
        lda     enemy_y_msb,x
        beq     hs9
        dec     enemy_y_msb,x

hs9:    lda     tmp4
        beq     hsnot
        lda     tmp5
        beq     hsnot
        sec
        rts
hsnot:  clc
        rts
