; player.s -- input, the fighter, the capture, and the Dual Fighter.
;
; Three input sources are read every frame and folded into one
; `input_state` byte; everything downstream reads that byte and nothing
; else.  Each source has its own decoder taking the raw port byte in A, so
; the two that no CLI can drive -- the matrix scan and the joystick -- are
; still provable one call at a time:
;
;   c64 call joydecode --a '$fb'    then  c64 mem read input_state
;
; $CB is folded in as a third source and never written.  That is what makes
; the game drivable: `c64 key hold` re-pokes the matrix code there before
; each tick, and with the KERNAL's keyboard scan switched off (§0) the value
; simply persists.

        .segment "ENGINE"

PLSPEED  = $0180                ; 1.5 px/frame in 8.8
FIRECOOL = 8

; ---- readinput -----------------------------------------------------------
; Order matters: the matrix rows are driven first, then $DC00 is released to
; $FF and the joystick sampled -- the stick shares its pins with the row
; outputs, so sampling it with a row selected reads a phantom.  A frame in
; which the stick reports a direction wins over the matrix on the same lines.
readinput:
        lda     input_state
        sta     input_prev
        lda     anykey
        sta     anykey_prev
        lda     #0
        sta     input_state
        sta     stage_select
        sta     anykey

        jsr     matscan                 ; rows driven
        lda     #$FF
        sta     CIA1PRA                 ; all rows released
        lda     CIA1PRA
        jsr     joydecode
        lda     KEYDOWN
        jsr     keydecode

        lda     joybits
        and     #IN_LEFT|IN_RIGHT
        beq     ri1
        lda     input_state             ; the stick is authoritative
        and     #<~(IN_LEFT|IN_RIGHT)
        ora     joybits
        sta     input_state
ri1:    lda     input_state
        eor     input_prev
        and     input_state
        sta     input_edge
        ; ... and the same edge on the any-key flag the three decoders have
        ; just set.  It has to be an edge: the cold open is re-entered from
        ; the game over, and a key still held from the last life would
        ; otherwise skip the narration before a single glyph was drawn.
        lda     anykey
        eor     anykey_prev
        and     anykey
        sta     anykey_edge
        rts

; ---- matscan -- the keyboard matrix, read directly ----------------------
; $DC00 selects a row (active low), $DC01 reads the columns (active low).
; This is the only source that reports two keys at once, so it is the real
; control path: a player can move and fire in the same frame.
; The six rows are unrolled.  A subroutine per row cost a jsr, an X save and
; restore, and a cpx ladder that walked past every earlier row to find its own
; -- about thirty cycles a row before a single key bit was tested.
; The start keys are SPACE (one player) and X (two players): F1/F3 do not
; reach VICE reliably from a Mac keyboard, so the maintainer retired them
; from the matrix.  SPACE doubles as fire; that is safe because IN_ST1 only
; starts a game from the title state, and the fire path is edge-triggered,
; so a SPACE still held when play begins launches nothing.
matscan:
        ; Is ANY key down, anywhere on the matrix?  Driving every row low at
        ; once and reading the columns answers that in ten cycles, and it
        ; answers it for all eight rows -- including the three this scan does
        ; not otherwise select, which is the whole point: the cold open must
        ; yield to keys the game has no mapping for (§1a).  Testing each
        ; unrolled row's byte below would have missed rows 0, 5 and 6 and
        ; cost more.  A joystick in port 1 shares these column lines and
        ; would read as a key; on this screen that is the right answer too.
        lda     #$00
        sta     CIA1PRA
        lda     CIA1PRB
        cmp     #$FF                    ; all columns high = nothing down
        beq     :+
        lda     #1
        sta     anykey
:       lda     #0
        sta     matbits

        lda     #$FD                    ; row 1: A bit 2, '3' bit 0, '4' bit 3
        sta     CIA1PRA
        lda     CIA1PRB
        eor     #$FF
        sta     tmp1
        beq     ms2                     ; nothing down on this row at all
        and     #$04
        beq     :+
        lda     matbits
        ora     #IN_LEFT
        sta     matbits
:       lda     tmp1
        and     #$01
        beq     :+
        lda     #3
        sta     stage_select
:       lda     tmp1
        and     #$08
        beq     ms2
        lda     #4
        sta     stage_select

ms2:    lda     #$FB                    ; row 2: D bit 2, X bit 7,
        sta     CIA1PRA                 ;        '5' bit 0, '6' bit 3
        lda     CIA1PRB
        eor     #$FF
        sta     tmp1
        beq     ms3
        and     #$04
        beq     :+
        lda     matbits
        ora     #IN_RIGHT
        sta     matbits
:       lda     tmp1
        and     #$80                    ; X -- start a two-player game
        beq     :+
        lda     matbits
        ora     #IN_ST2
        sta     matbits
:       lda     tmp1
        and     #$01
        beq     :+
        lda     #5
        sta     stage_select
:       lda     tmp1
        and     #$08
        beq     ms3
        lda     #6
        sta     stage_select

ms3:    lda     #$F7                    ; row 3: '7' bit 0, '8' bit 3
        sta     CIA1PRA
        lda     CIA1PRB
        eor     #$FF
        sta     tmp1
        beq     ms4
        and     #$01
        beq     :+
        lda     #7
        sta     stage_select
:       lda     tmp1
        and     #$08
        beq     ms4
        lda     #8
        sta     stage_select

ms4:    lda     #$EF                    ; row 4: '9' bit 0, '0' bit 3
        sta     CIA1PRA
        lda     CIA1PRB
        eor     #$FF
        sta     tmp1
        beq     ms7
        and     #$01
        beq     :+
        lda     #9
        sta     stage_select
:       lda     tmp1
        and     #$08
        beq     ms7
        lda     #10
        sta     stage_select

ms7:    lda     #$7F                    ; row 7: SPACE bit 4, '1' bit 0, '2' bit 3
        sta     CIA1PRA
        lda     CIA1PRB
        eor     #$FF
        sta     tmp1
        beq     ms9
        and     #$10
        beq     :+
        lda     matbits                 ; SPACE fires in play and starts a
        ora     #IN_FIRE|IN_ST1         ; one-player game from the title
        sta     matbits
:       lda     tmp1
        and     #$01
        beq     :+
        lda     #1
        sta     stage_select
:       lda     tmp1
        and     #$08
        beq     ms9
        lda     #2
        sta     stage_select

ms9:    lda     matbits
        ora     input_state
        sta     input_state
        rts

; ---- joydecode -- A = CIA1 port A; joystick port 2, active low ----------
; The joystick cannot be driven from the CLI, so this is written to be
; called on its own with the port byte you want:
;   c64 call joydecode --a '$fb'   -- left     $f7 right   $ef fire
joydecode:
        eor     #$FF
        sta     tmp1
        lda     #0
        sta     joybits
        lda     tmp1
        and     #$04                    ; bit 2 -- left
        beq     :+
        lda     joybits
        ora     #IN_LEFT
        sta     joybits
:       lda     tmp1
        and     #$08                    ; bit 3 -- right
        beq     :+
        lda     joybits
        ora     #IN_RIGHT
        sta     joybits
:       lda     tmp1
        and     #$10                    ; bit 4 -- fire
        beq     :+
        lda     joybits
        ora     #IN_FIRE
        sta     joybits
        lda     #1                      ; the stick has no keys, so fire is
        sta     anykey                  ; its "get on with it" (§1a)
:       lda     joybits
        ora     input_state
        sta     input_state
        rts

; ---- keydecode -- A = $CB, the matrix code of the key held right now ----
; Two byte values mean "nothing down", not one.  KEY_NONE is what Commodore's
; KERNAL leaves; 0 is what a KERNAL that never writes $CB leaves, and the web
; player boots one -- MEGA65 open-roms, where the byte reads 0 forever.  Read
; as a key, that 0 pinned `anykey` high every frame, and with it high there
; was no anykey_edge and the cold open could not be dismissed at all.  Code 0
; is INST/DEL, which is in neither table, so nothing else here loses a key.
keydecode:
        sta     tmp1
        lda     #0
        sta     keybits
        lda     tmp1
        and     #<~KEY_NONE             ; KEY_NONE is the usual answer and it
        beq     kd8                     ; is not in the table: walking all
                                        ; fifteen to find that out cost 300
                                        ; cycles.  Clearing bit 6 folds the
                                        ; other "nothing down" value, 0, into
                                        ; the same branch for the same four
                                        ; bytes -- and A is dead either way,
                                        ; because the walk below matches tmp1.
        ldx     #1                      ; a code here is a key down, mapped
        stx     anykey                  ; or not (§1a)
        ldx     #0
kd1:    lda     keycodes,x
        cmp     #$FF
        beq     kd8
        cmp     tmp1
        bne     kd2
        lda     keyvals,x
        cmp     #$80
        bcs     kd3                     ; a stage-select digit
        ora     keybits
        sta     keybits
        jmp     kd8
kd3:    and     #$7F
        sta     stage_select
        jmp     kd8
kd2:    inx
        bne     kd1
kd8:    lda     keybits
        ora     input_state
        sta     input_state
        rts

; SPACE carries both fire and 1P-start; X (code 23) is 2P-start.  The old
; F1/F3 codes stay decoded from $CB so existing evidence scripts that hold
; them still work; only the matrix scan retired their row.
keycodes:
        .byte   KEY_A, KEY_D, KEY_SPC, KEY_X, KEY_F1, KEY_F3
        .byte   56, 59, 8, 11, 16, 19, 24, 27, 32, 35
        .byte   $FF
keyvals:
        .byte   IN_LEFT, IN_RIGHT, IN_FIRE|IN_ST1, IN_ST2, IN_ST1, IN_ST2
        .byte   $81, $82, $83, $84, $85, $86, $87, $88, $89, $8A

; ==========================================================================
; The fighter
; ==========================================================================
playerinit:
        lda     #PLW_MAX/2
        sta     plx
        lda     #0
        sta     plx+1
        sta     plxf
        sta     plstate
        sta     pldual
        sta     plspin
        sta     firecool
        lda     #1
        sta     plalive
        lda     #$FF
        sta     plcapt
        rts

playertick:
        lda     plalive
        bne     pt0
        rts
pt0:    lda     plstate
        beq     ptfly
        cmp     #1
        bne     @far15
        jmp     ptcaptured
@far15:
        jmp     ptdying

ptfly:  lda     #1
        sta     dirlast                 ; 1 = the last move was rightward
        lda     input_state
        and     #IN_LEFT
        beq     ptr
        lda     #0
        sta     dirlast
        lda     plxf
        sec
        sbc     #<PLSPEED
        sta     plxf
        lda     plx
        sbc     #>PLSPEED
        sta     plx
ptr:    lda     input_state
        and     #IN_RIGHT
        beq     ptclamp
        lda     #1
        sta     dirlast
        lda     plxf
        clc
        adc     #<PLSPEED
        sta     plxf
        lda     plx
        adc     #>PLSPEED
        sta     plx

ptclamp:
        ; The fighter's travel is bounded by the playfield window.  Its
        ; position is kept in *window* pixels, 0-176, not in sprite
        ; coordinates: the window's right edge is sprite X 260, which does
        ; not fit a byte, and a 9-bit clamp in the movement path would be
        ; nine instructions where the draw already has to do the arithmetic
        ; once anyway.
        bcs     :+                      ; carry from the add/subtract above
        lda     dirlast
        beq     ptlow
:       lda     plx
        ldy     pldual
        beq     ptsingle
        cmp     #PLW_MAX_DUAL+1
        bcc     ptfire
        lda     #PLW_MAX_DUAL
        bne     ptset
ptsingle:
        cmp     #PLW_MAX+1
        bcc     ptfire
        lda     #PLW_MAX
        bne     ptset
ptlow:  lda     #0
ptset:  sta     plx
        lda     #0
        sta     plxf
        sta     plx+1

ptfire: lda     firecool
        beq     :+
        dec     firecool
:       lda     input_edge
        and     #IN_FIRE
        beq     pt9
        lda     firecool
        bne     pt9
        jsr     firemissile
        lda     #FIRECOOL
        sta     firecool
pt9:    rts

; ---- captured: the fighter spins, reddens and is drawn up to the Flagship
ptcaptured:
        inc     plspin
        lda     plspin
        cmp     #90
        bcc     pt9
        ; the docking is done: the fighter now rides the Flagship
        lda     #0
        sta     plstate
        lda     #0
        sta     plalive
        jsr     loselife
        rts

ptdying:
        inc     pltimer
        lda     pltimer
        cmp     #40
        bcc     pt9
        lda     #0
        sta     plstate
        sta     plalive                 ; dead: without this the play state
                                        ; never reached ST_DEAD, so a fighter
                                        ; shot down respawned in place and a
                                        ; bullet or a ram could never end the
                                        ; game -- only a capture could
        jsr     loselife
        rts

; ---- capture -- X = the Flagship's slot ---------------------------------
capture:
        lda     plstate
        bne     cap9
        stx     plcapt
        lda     enemy_flags,x
        ora     #EFL_CARRIES
        sta     enemy_flags,x
        and     #<~EFL_BEAM
        sta     enemy_flags,x
        lda     #$FF
        sta     beamslot
        ; the captive becomes an object of its own, docked above the carrier
        ldy     #SLOT_CAPTIVE
        lda     #EST_DOCKED
        sta     enemy_state,y
        lda     #ETY_CAPTIVE
        sta     enemy_type,y
        txa
        sta     enemy_slot,y
        lda     #1
        sta     enemy_hp,y
        lda     #0
        sta     enemy_flags,y
        lda     #1
        sta     plstate
        lda     #0
        sta     plspin
        lda     #SFX_CAPTURE
        jsr     sfxstart
cap9:   rts

; ---- rescue -- the carrier was destroyed in flight: Dual Fighter --------
rescue: lda     #0
        sta     enemy_state+SLOT_CAPTIVE
        lda     #1
        sta     pldual
        sta     plalive
        lda     #0
        sta     plstate
        lda     #$FF
        sta     plcapt
        lda     #SFX_RESCUE
        jsr     sfxstart
        rts

; ---- freecaptive -- the carrier died in the grid: it turns on the player -
freecaptive:
        ldy     #SLOT_CAPTIVE
        lda     enemy_state,y
        cmp     #EST_DOCKED
        bne     fc9
        lda     #EST_DIVE
        sta     enemy_state,y
        lda     #PATH_DIVE1
        sta     enemy_path,y
        lda     #0
        sta     enemy_pathix,y
        sta     enemy_pathct,y
        sta     enemy_timer,y
        sta     enemy_flags,y
        lda     divespeed
        sta     enemy_speed,y
        lda     #0
        sta     enemy_shape,y           ; force one shape refresh
        lda     #$FF
        sta     plcapt
fc9:    rts

; ---- playerhit -- a bullet or a collision got the fighter ---------------
playerhit:
        lda     plstate
        bne     ph9
        lda     pldual
        beq     ph1
        lda     #0                      ; one of the pair is destroyed
        sta     pldual
        jsr     loselife
        lda     #SFX_EXPLODE
        jmp     sfxstart
ph1:    lda     #2
        sta     plstate
        lda     #0
        sta     pltimer
        lda     #SFX_EXPLODE
        jmp     sfxstart
ph9:    rts

; ---- playerdraw -- sprites 0 and 1, straight into the VIC ---------------
; The accent overlay is a sprite, not a free effect: it is budgeted, and it
; is dropped while the Dual Fighter is on screen because sprite 1 is then
; the second fighter.
playerdraw:
        lda     #0
        sta     plena
        lda     plalive
        bne     :+
        rts
:       ; sprite X = PLX_BASE + window pixel; the carry is the 9th bit
        lda     plx
        clc
        adc     #PLX_BASE
        sta     SPR0X
        lda     SPRXMSB
        and     #$FE
        bcc     :+
        ora     #$01
:       sta     SPRXMSB
        lda     #PLY
        sta     SPR0Y
        lda     plstate
        cmp     #1
        bne     :+
        jsr     spinshape
        jmp     :++
:       lda     #SPR_FIGHTER
:       sta     SPRPTR
        lda     #COL_WHITE
        ldy     plstate
        cpy     #1
        bne     :+
        lda     #COL_RED                ; a captured fighter turns red
:       sta     SPRCOL0
        lda     #$01
        sta     plena

        ; Sprite 1 is the second fighter when dual, and the accent overlay
        ; when not.  The overlay is a sprite, not a free effect: it is
        ; budgeted, and it is dropped while the Dual Fighter is on screen.
        lda     pldual
        beq     pdacc
        lda     plx
        clc
        adc     #PLX_BASE+16
        sta     SPR0X+2
        lda     SPRXMSB
        and     #$FD
        bcc     :+
        ora     #$02
:       sta     SPRXMSB
        lda     #PLY
        sta     SPR0Y+2
        lda     #SPR_FIGHTER
        sta     SPRPTR+1
        lda     #COL_WHITE
        sta     SPRCOL0+1
        lda     #$03
        sta     plena
        rts
pdacc:  lda     plstate
        beq     :+
        rts                             ; no overlay while it is spinning
:       lda     plx
        clc
        adc     #PLX_BASE
        sta     SPR0X+2
        lda     SPRXMSB
        and     #$FD
        bcc     :+
        ora     #$02
:       sta     SPRXMSB
        lda     #PLY
        sta     SPR0Y+2
        lda     #SPR_ACCENT
        sta     SPRPTR+1
        lda     #COL_CYAN
        sta     SPRCOL0+1
        lda     #$03
        sta     plena
        rts

spinshape:
        lda     plspin
        lsr     a
        lsr     a
        and     #3
        tay
        lda     spinshapes,y
        rts
spinshapes:
        .byte   SPR_FIGHTER, SPR_SPIN45, SPR_SPIN90, SPR_SPIN135
