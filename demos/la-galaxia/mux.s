; mux.s -- the raster-IRQ sprite multiplexer and the interrupt chain.
;
; Eight hardware sprites, and never more than eight on a scanline; the
; arcade board had sixty-four.  Sprites 0 and 1 are the fighter (and the
; accent overlay, or the right-hand fighter when dual) and are never
; multiplexed.  Sprites 2-7 are six registers reused down the screen: the
; objects are sorted by Y once a frame, each is given the first register
; that has come free by the time the beam reaches it, and a raster interrupt
; at Y-3 reprograms that register.
;
; `mux_count` is what the chain displayed; `mux_overflow` is what a band
; could not fit.  Both are plain memory, which is the only way a claim about
; a multiplexer can be proved -- a screenshot shows the result, not the
; budget.
;
; The interrupt chain is one sorted event list per frame, three parallel
; arrays deep:
;
;   line 0            EV_FRAME    hand the tick to the main loop
;   BAND_TOP          EV_SCRON    the formation's breathe sway goes on
;   Y-3 per object    EV_MUX      reposition one register
;   BAND_BOT          EV_SCROFF   and comes off again, so the HUD and the
;                                 bezel do not sway with the grid
;   -                 EV_END      wrap to line 0
;
; Entry is through the KERNAL's $0314 vector, which costs the ROM's 20-cycle
; register save and calls no KERNAL routine; the exit is written out here so
; nothing in the chain touches ROM.

        .segment "ENGINE"

MUXREGS = 6                     ; hardware sprites 2-7
; MUXGAP is the reuse distance: a register handed to an object at line Y is
; not offered again until Y+MUXGAP.  21 covers the sprite's own lines, so 22
; reads like one line to spare -- but emitmux arms the reposition THREE lines
; early (`sbc #3` below), so the honest safe distance is 21+3 = 24.  At 22 an
; object reusing a register 22 or 23 lines below its predecessor has that
; register reprogrammed over the last lines of the sprite still being drawn.
; Left at 22 deliberately: raising it moves this demo's committed .prg and
; the evidence captured from it.  Copy the rule (21 + the emitter's lead),
; not the number.
MUXGAP  = 22                    ; see above -- 24 is the safe value, 22 ships

irqinit:
        sei
        lda     #<irq
        sta     $0314
        lda     #>irq
        sta     $0315
        lda     #$01
        sta     IRQMASK                 ; raster interrupts only
        lda     SPRCTRL1
        and     #$7F                    ; every event line is below 256
        sta     SPRCTRL1
        lda     #0
        sta     evidx
        sta     $D012
        lda     #EV_FRAME
        sta     evkind
        lda     #EV_END
        sta     evkind+1
        lda     #$01
        sta     IRQFLAG
        rts

; --------------------------------------------------------------------------
irq:    lda     #$01
        sta     IRQFLAG
        ldx     evidx
irqdisp:
        lda     evkind,x
        cmp     #EV_MUX
        beq     irqmux
        cmp     #EV_FRAME
        beq     irqframe
        cmp     #EV_SCRON
        beq     irqscron
        cmp     #EV_SCROFF
        beq     irqscroff
        ; EV_END -- park on line 0 and wait for the next frame
irqend: lda     #0
        sta     evidx
        sta     $D012
        jmp     irqexit

irqframe:
        inc     vblcount
        inc     tickpend
        lda     scrolloff
        sta     SPRCTRL2
        jmp     irqadv

irqscron:
        lda     scrollon
        sta     SPRCTRL2
        jmp     irqadv

irqscroff:
        lda     scrolloff
        sta     SPRCTRL2
        jmp     irqadv

irqmux: ldy     evarg,x                 ; Y = the object this event repositions
        stx     evtmp
        ldx     mreg,y                  ; hardware sprite number * 2
        lda     objx,y
        sta     SPR0X,x
        lda     objy,y
        sta     SPR0Y,x
        lda     objmsb,y
        beq     irqmsb0
        lda     SPRXMSB
        ora     mbit,y
        sta     SPRXMSB
        jmp     irqmsb9
irqmsb0:
        lda     SPRXMSB
        and     mnbit,y
        sta     SPRXMSB
irqmsb9:
        txa
        lsr     a
        tax
        lda     objshape,y
        sta     SPRPTR,x
        lda     objcol,y
        sta     SPRCOL0,x
        ldx     evtmp
        ; fall through

irqadv: inx
        stx     evidx
        lda     evkind,x
        cmp     #EV_END
        beq     irqend
        lda     evline,x
        sta     $D012
        sec
        sbc     #2
        cmp     $D012                   ; the *current* raster line
        bcs     irqexit                 ; still ahead of the beam
        jmp     irqdisp                 ; already past it -- do it now

irqexit:
        ; Ack the raster latch AGAIN on the way out.  When irqadv finds the
        ; next event's line already passed it dispatches it inline -- but the
        ; compare register was written before the check, so the beam crossing
        ; that line has re-set the latch for an event this handler has now
        ; already run.  Left set, the RTI re-enters immediately with evidx
        ; parked at 0 and EV_FRAME fires mid-frame: vblcount double-counts
        ; (a phantom tick_overrun) and tickpend runs the next tick early in
        ; the same frame.  The final $D012 write is guaranteed >= 2 lines
        ; ahead by irqadv's guard, so nothing legitimate can have latched
        ; between it and this ack.
        lda     #$01
        sta     IRQFLAG
        pla
        tay
        pla
        tax
        pla
        rti

; --------------------------------------------------------------------------
; muxbuild -- gather, sort, assign, publish.  Runs at the TOP of the tick,
; before any game logic, because the schedule it writes is played out from
; line 51 of this same frame: built at the end of the tick it would be
; rewritten under the beam.
; --------------------------------------------------------------------------
muxbuild:
        jsr     playerdraw              ; sprites 0/1 and plena, which ma8 ORs
        jsr     muxlist
        jsr     muxsort
        jmp     muxassign

; ---- the object list -----------------------------------------------------
; obj* is a snapshot, and the list of objects in it survives from one frame to
; the next.  That is the whole point: an object at position k means the same
; object next frame, so the list arrives at the sort already in Y order bar a
; few adjacent swaps, and the sort is an insertion pass that hardly ever
; shifts.  Rebuilding the list in slot order every frame handed the sort a
; random permutation -- quadratic work, 4,875 cycles for eighteen objects.
;
; This pass only has to drop what has gone: whatever has just appeared was
; appended by the snapshot in enemytick (and, for the beam, by beamupdate) at
; the moment it became visible.  An object that leaves has its inlist flag
; cleared here, and here is the only place it is ever cleared.
muxlist:
        jsr     beamupdate
        lda     #0
        sta     tmp2                    ; read cursor into last frame's list
        sta     tmp3                    ; write cursor into this frame's

ml1:    ldy     tmp2
        cpy     mux_n
        bcs     ml3
        ldx     sortix,y
        lda     objok,x
        beq     ml2
        ldy     tmp3
        txa
        sta     sortix,y
        lda     objy,x
        sta     sortkey,y
        inc     tmp3
        jmp     ml1b
ml2:    lda     #0
        sta     inlist,x                ; gone: it may be appended again later
ml1b:   inc     tmp2
        jmp     ml1

ml3:    lda     tmp3
        sta     mux_n
        rts

; beamupdate -- the tractor beam is object BEAM_OBJ, one past the enemy pool,
; so the list has no special case in it.  enemytick never sees this slot, so
; its snapshot is taken here.
beamupdate:
        lda     #0
        sta     objok+BEAM_OBJ
        ldy     beamslot
        bmi     bu9
        lda     enemy_flags,y
        and     #EFL_BEAM
        beq     bu9
        lda     enemy_y_msb,y
        bne     bu9
        lda     enemy_y,y
        clc
        adc     #16                     ; it hangs below its Flagship
        bcs     bu9
        cmp     #250
        bcs     bu9
        sta     objy+BEAM_OBJ
        lda     enemy_x_lsb,y
        sta     objx+BEAM_OBJ
        lda     enemy_x_msb,y
        sta     objmsb+BEAM_OBJ
        lda     frames
        and     #$04
        beq     :+
        lda     #SPR_BEAM1
        bne     :++
:       lda     #SPR_BEAM0
:       sta     objshape+BEAM_OBJ
        lda     #COL_CYAN
        sta     objcol+BEAM_OBJ
        inc     objok+BEAM_OBJ
        ; and it joins the list exactly the way an enemy does from etsnap
        lda     inlist+BEAM_OBJ
        bne     bu9
        ldy     mux_n
        cpy     #MAXOBJ
        bcs     bu9
        lda     #BEAM_OBJ
        sta     sortix,y
        lda     objy+BEAM_OBJ
        sta     sortkey,y
        inc     mux_n
        lda     #1
        sta     inlist+BEAM_OBJ
bu9:    rts

; muxadd -- X = object: snapshot it and put it in the list right now, for the
; handoff in formation.s.  etsnap does the same thing inline for the pool.
muxadd:
        lda     #0
        sta     objok,x
        lda     enemy_y_msb,x
        bne     mad9
        lda     enemy_y,x
        cmp     #30
        bcc     mad9
        cmp     #250
        bcs     mad9
        sta     objy,x
        lda     enemy_x_lsb,x
        sta     objx,x
        lda     enemy_x_msb,x
        sta     objmsb,x
        lda     enemy_shape,x
        sta     objshape,x
        lda     enemy_col,x
        sta     objcol,x
        inc     objok,x
        lda     inlist,x
        bne     mad9
        ldy     mux_n
        cpy     #MAXOBJ
        bcs     mad9
        txa
        sta     sortix,y
        lda     objy,x
        sta     sortkey,y
        inc     mux_n
        lda     #1
        sta     inlist,x
mad9:   rts

; ---- sort ----------------------------------------------------------------
; Insertion sort over a list that is already almost in order, because it is
; last frame's order and nothing moved more than a few pixels.  Only the
; entries step B appended have to travel, and there are rarely more than one
; or two of those in a frame.
muxsort:
        lda     mux_n
        cmp     #2
        bcs     mq0
        rts
mq0:    ldx     #1
        ; An entry already above its predecessor needs nothing done to it at
        ; all -- not even the copy out to tmp and back -- and on a list that
        ; is last frame's order that is nearly every entry.
mq5:    lda     sortkey,x
        cmp     sortkey-1,x
        bcs     mq8
        sta     tmp1                    ; the key being placed
        lda     sortix,x
        sta     tmp0                    ; ... and its object
        txa
        tay                             ; Y = hole
mq6:    dey
        bmi     mq7
        lda     sortkey,y
        cmp     tmp1
        bcc     mq7                     ; predecessor is smaller: stop
        beq     mq7                     ; equal: stop, so ties stay put and a
                                        ; band full of one Y is not quadratic
        sta     sortkey+1,y             ; shift the pair up one
        lda     sortix,y
        sta     sortix+1,y
        jmp     mq6
mq7:    iny
        lda     tmp1
        sta     sortkey,y
        lda     tmp0
        sta     sortix,y
mq8:    inx
        cpx     mux_n
        bne     mq5
        rts

; ---- assign --------------------------------------------------------------
; Greedy: walk the sorted list and take the first register that has come
; free.  Because the list ascends in Y, greedy is optimal here -- a register
; passed over could not have served this object either.
; X stays on the object and Y on the register for the whole body, so the
; assignment is a handful of table reads and no shuffling through tmp.
muxassign:
        ldx     #MUXREGS-1
        lda     #0
ma0:    sta     regfree,x
        sta     regused,x
        dex
        bpl     ma0
        sta     mux_count
        sta     mux_overflow
        sta     tmp4                    ; k -- position in the sorted list
        sta     sprena_sh
        sta     rrnext                  ; the round robin starts at register 0
        sta     bandix                  ; and the band edges are both to come
        ; The event list is built in this same pass.  It used to be a second
        ; walk of the schedule that re-derived the raster line from a Y this
        ; loop already had in tmp1, and cost 150 cycles per event to do it.
        sta     evline
        sta     evkind                  ; EV_FRAME = 0, at line 0
        lda     #1
        sta     evcur

ma1:    ldy     tmp4
        cpy     mux_n
        bcc     :+
        jmp     ma8                     ; out of branch range
:       lda     sortkey,y
        sta     tmp1                    ; this object's Y
        ldx     sortix,y                ; X = the object, from here on

        ; The list ascends in Y and the registers are handed out in turn, so
        ; the one that comes free soonest is always the one used longest ago:
        ; start the search at the round-robin cursor and it hits on the first
        ; try.  Scanning from register 0 every time cost forty cycles an
        ; object for an answer the rotation already knew.
        ldy     rrnext
ma2:    lda     regfree,y
        cmp     tmp1
        beq     ma3
        bcc     ma3
        iny
        cpy     #MUXREGS
        bne     :+
        ldy     #0
:       cpy     rrnext
        bne     ma2
        inc     mux_overflow            ; no band could hold it
        jmp     ma7

ma3:    sty     tmp2                    ; the register this object took
        lda     tmp1
        clc
        adc     #MUXGAP
        bcc     :+
        lda     #$FF                    ; saturate rather than wrap
:       sta     regfree,y

        lda     regspr2,y               ; (register+2) * 2
        sta     mreg,x
        lda     regbit,y
        sta     mbit,x
        eor     #$FF
        sta     mnbit,x
        ; the first object on a register is programmed here and now, at the
        ; top of the frame; every later one gets a reposition interrupt
        lda     regused,y
        bne     ma5
        lda     #1
        sta     regused,y
        jsr     muxprogram
        jmp     ma6
ma5:    jsr     emitmux                 ; a later object on a register in use
ma6:    ldy     tmp2                    ; advance the round robin past it
        iny
        cpy     #MUXREGS
        bcc     :+
        ldy     #0
:       sty     rrnext
        inc     mux_count
ma7:    inc     tmp4
        jmp     ma1

ma8:    ; The $D015 mask falls out of which registers were used at all, so it
        ; is built once here rather than OR-ed together object by object.
        ldy     #MUXREGS-1
        lda     #0
        sta     sprena_sh
mae1:   lda     regused,y
        beq     mae2
        lda     regbit,y
        ora     sprena_sh
        sta     sprena_sh
mae2:   dey
        bpl     mae1
        ; whatever band edges are left sit below the last object
        lda     #$FF
        sta     evtline
        jsr     emitbands
        ldy     evcur
        lda     #EV_END
        sta     evkind,y
        lda     #$FF
        sta     evline,y
        ; sprites 0-1 belong to the fighter; player.s owns their enables
        lda     sprena_sh
        ora     plena
        sta     SPRENA
        rts

; --------------------------------------------------------------------------
; emitmux -- X = the object, tmp1 = its Y: emit any band edge at or above the
; line this reposition wants, then the reposition itself.  Objects arrive in
; ascending Y, so the merge is one comparison per event.  X is preserved.
; --------------------------------------------------------------------------
emitmux:
        lda     tmp1
        sec
        sbc     #3                      ; program it three lines early
        bcs     :+
        lda     #51
:       cmp     #51                     ; never above the first visible line
        bcs     :+
        lda     #51
:       sta     evtline
        jsr     emitbands
        ldy     evcur
        cpy     #MAXEV-1
        bcs     em9
        lda     evtline
        sta     evline,y
        lda     #EV_MUX
        sta     evkind,y
        txa
        sta     evarg,y                 ; irqmux reprograms from the OBJECT
        inc     evcur
em9:    rts

; emitbands -- emit every band edge whose line is at or above evtline.
emitbands:
        ldy     bandix
        lda     bandline,y
        cmp     #$FF
        beq     eb9
        cmp     evtline
        beq     :+
        bcs     eb9
:       ldy     evcur
        cpy     #MAXEV-1
        bcs     eb9
        sta     evline,y
        ldy     bandix
        lda     bandkind,y
        ldy     evcur
        sta     evkind,y
        inc     evcur
        inc     bandix
        jmp     emitbands
eb9:    rts

; muxprogram -- X = object; write it straight into the VIC.  X is preserved.
muxprogram:
        ldy     mreg,x
        lda     objx,x
        sta     SPR0X,y
        lda     objy,x
        sta     SPR0Y,y
        lda     objmsb,x
        beq     mp0
        lda     SPRXMSB
        ora     mbit,x
        sta     SPRXMSB
        jmp     mp1
mp0:    lda     SPRXMSB
        and     mnbit,x
        sta     SPRXMSB
mp1:    tya
        lsr     a
        tay
        lda     objshape,x
        sta     SPRPTR,y
        lda     objcol,x
        sta     SPRCOL0,y
        rts

regspr2:                                ; (register + 2) * 2
        .byte   4, 6, 8, 10, 12, 14
regbit:                                 ; 1 << (register + 2)
        .byte   $04, $08, $10, $20, $40, $80

bandline:
        .byte   BAND_TOP, BAND_BOT, $FF
bandkind:
        .byte   EV_SCRON, EV_SCROFF, EV_END
