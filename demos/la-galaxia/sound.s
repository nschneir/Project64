; sound.s -- three SID voices, every write shadowed, effects by priority.
;
; The SID is write-only: $D400-$D418 cannot be read back, so audio leaves no
; trace a debugger can inspect.  Every write therefore goes through `sidput`,
; which mirrors it into the 25-byte block at `sidshad` in the same
; instruction pair.  Those bytes are the testable evidence for sound -- with
; no shadow, no claim about a waveform, an envelope or a channel priority can
; be proved at all.
;
;   voice 1   lead / high-priority FX    melody, the laser
;   voice 2   bass / mid-priority FX     harmony, the dive whine, the beam
;   voice 3   noise / low-priority FX    explosions, the grid march
;
; An effect seizes its voice only if its priority is >= that of whatever
; holds the voice now; a lower-priority effect is dropped, never queued.
; While an effect holds a voice the sequencer keeps running silently and
; resumes at the position it would have reached -- it never pauses.

        .segment "ENGINE"

SID     = $D400
SIDFLO  = 0
SIDFHI  = 1
SIDPWLO = 2
SIDPWHI = 3
SIDCTRL = 4
SIDAD   = 5
SIDSR   = 6
SIDVOL  = 24

SFX_LASER   = 0
SFX_DIVE    = 1
SFX_BEAM    = 2
SFX_EXPLODE = 3
SFX_CAPTURE = 4
SFX_RESCUE  = 5
SFX_EXTRA   = 6
SFX_PLDEATH = 7
NUM_SFX     = 8

sfxvoice:   .byte   0, 1, 1, 2, 1, 0, 0, 2
sfxprio:    .byte   2, 1, 2, 3, 3, 3, 3, 4
sfxlen:     .byte   6, 10, 14, 24, 40, 30, 24, 32

voicebase:  .byte   0, 7, 14

; ---- sidput -- A = value, X = register offset; shadow it as we go -------
sidput: sta     SID,x
        sta     sidshad,x
        rts

sidinit:
        ldx     #24
        lda     #0
sni0:   jsr     sidput
        dex
        bpl     sni0
        lda     #$0F                    ; master volume, filter off
        ldx     #SIDVOL
        jsr     sidput
        ldx     #2
        lda     #0
sni1:   sta     vprio,x
        sta     vtimer,x
        dex
        bpl     sni1
        rts

musicoff:
        ldx     #2
mo1:    lda     voicebase,x
        stx     tmp0
        tax
        inx
        inx
        inx
        inx                             ; the control register
        lda     #0
        jsr     sidput
        ldx     tmp0
        dex
        bpl     mo1
        rts

; ==========================================================================
; soundtick -- once per frame from the tick.
; ==========================================================================
soundtick:
        jsr     sfxcue
        jsr     sfxtick
        jsr     musictick
        rts

; ---- sfxcue -- aim an effect at a moment, for the capture protocol -------
; Effects are started by the game, and `c64 audio capture` cannot drive the
; machine while its window is open -- so an effect poked in from the CLI
; fires during the ~15 frames arming costs and is over before the window
; opens.  There is no way to catch one.  These five bytes aim it instead:
; sfxpend is the effect plus one, sfxdelay the frames to wait, sfxevery the
; gap between repeats, sfxreps how many (0 or 1 = one shot) and sfxalt a
; second effect the repeats alternate with.  Every firing goes through
; `sfxstart`, so the voice allocation and the priority arithmetic on trial
; are the real ones and only the moment is staged.  All five read zero in
; play, where the game does the triggering.
sfxdelay:   .byte   0
sfxevery:   .byte   0
sfxreps:    .byte   0
sfxalt:     .byte   0               ; a second effect, alternated with sfxpend

sfxcue: lda     sfxpend
        beq     sc9
        lda     sfxdelay
        beq     scfire
        dec     sfxdelay
        rts
scfire: lda     sfxpend
        sec
        sbc     #1
        jsr     sfxstart
        ; sfxalt swaps in for the next firing, so one cue can be a shot and
        ; the hit it causes rather than the same effect over and over.
        lda     sfxalt
        beq     scnoalt
        ldy     sfxpend
        sta     sfxpend
        sty     sfxalt
scnoalt:
        lda     sfxreps
        beq     sclast
        dec     sfxreps
        bne     scmore
sclast: lda     #0
        sta     sfxpend
        rts
scmore: lda     sfxevery
        sta     sfxdelay
sc9:    rts

; ---- sfxstart -- A = SFX_*; seize the voice if the priority allows ------
; X is preserved: this is called from inside enemytick's slot loop (the beam
; deploy) and from pickdive's escort scan, both of which keep their slot in X.
; The old `tax` handed the loop the effect number as its index -- the beam
; deploy restarted the enemy walk at slot 2 and double-moved everything after
; it for a frame, and the escort branch read slot 1's type whatever dived.
sfxstart:
        cmp     #NUM_SFX
        bcs     ss9x
        stx     sfxsavex
        tax
        ldy     sfxvoice,x
        lda     sfxprio,x
        cmp     vprio,y
        bcc     ss9                     ; something louder holds it
        sta     vprio,y
        txa
        sta     vfx,y
        lda     sfxlen,x
        sta     vtimer,y
        lda     #0
        sta     vfxstep,y
ss9:    ldx     sfxsavex
ss9x:   rts

; ---- sfxtick -- run each held voice's effect, and hand it back ----------
sfxtick:
        ldx     #0
sft1:   lda     vprio,x
        beq     sft8
        stx     tmp3
        lda     vfx,x
        asl     a
        tay
        lda     sfxjmplo,y
        sta     sfxvec+1
        lda     sfxjmphi,y
        sta     sfxvec+2
sfxvec: jsr     $FFFF
        ldx     tmp3
        inc     vfxstep,x
        ; The beam is a hum, not a blip: while a Flagship still has it out
        ; (beamslot != $FF) the effect re-arms itself, so the sound lasts as
        ; long as the thing making it.  Every other effect just counts down.
        lda     vfx,x
        cmp     #SFX_BEAM
        bne     sft2
        ldy     beamslot
        cpy     #$FF
        beq     sft2
        lda     enemy_flags,y           ; and it really is still out: beamslot
        and     #EFL_BEAM               ; is not cleared when a beam retracts
        beq     sft2
        lda     sfxlen+SFX_BEAM
        sta     vtimer,x
sft2:   dec     vtimer,x
        bne     sft8
        lda     #0
        sta     vprio,x
        ; release the gate and let the sequencer take the voice back
        lda     voicebase,x
        clc
        adc     #SIDCTRL
        stx     tmp3
        tax
        lda     sidshad,x
        and     #$FE
        jsr     sidput
        ldx     tmp3
sft8:   inx
        cpx     #3
        bne     sft1
        rts

sfxjmplo:
        .byte   <fx_laser, 0, <fx_dive, 0, <fx_beam, 0, <fx_explode, 0
        .byte   <fx_capture, 0, <fx_rescue, 0, <fx_extra, 0, <fx_pldeath, 0
sfxjmphi:
        .byte   >fx_laser, 0, >fx_dive, 0, >fx_beam, 0, >fx_explode, 0
        .byte   >fx_capture, 0, >fx_rescue, 0, >fx_extra, 0, >fx_pldeath, 0

; ---- fx_laser: voice 1, triangle, $4000 swept down to $1000 in 5 frames -
lasertab:
        .byte   $40, $34, $28, $1C, $10, $10
fx_laser:
        ldx     #0
        lda     #0
        jsr     sidput                  ; frequency low
        ldy     vfxstep
        cpy     #6
        bcc     :+
        ldy     #5
:       lda     lasertab,y
        ldx     #1
        jsr     sidput                  ; frequency high
        lda     #$08
        ldx     #SIDAD
        jsr     sidput
        lda     #$00
        ldx     #SIDSR
        jsr     sidput
        lda     #$11                    ; triangle, gate on
        ldx     #SIDCTRL
        jmp     sidput

; ---- fx_dive: voice 2, a falling sawtooth whine -------------------------
fx_dive:
        lda     #$00
        ldx     #7+SIDFLO
        jsr     sidput
        lda     vfxstep+1
        eor     #$FF
        lsr     a
        clc
        adc     #$18
        ldx     #7+SIDFHI
        jsr     sidput
        lda     #$0A
        ldx     #7+SIDAD
        jsr     sidput
        lda     #$68
        ldx     #7+SIDSR
        jsr     sidput
        lda     #$21                    ; sawtooth, gate on
        ldx     #7+SIDCTRL
        jmp     sidput

; ---- fx_beam: voice 2, pulse with PWM and a two-note arpeggio ----------
beamarp:
        .byte   $2E, $3B
fx_beam:
        lda     #$00
        ldx     #7+SIDFLO
        jsr     sidput
        lda     vfxstep+1
        and     #1
        tay
        lda     beamarp,y
        ldx     #7+SIDFHI
        jsr     sidput
        lda     vfxstep+1
        asl     a
        asl     a
        asl     a
        ldx     #7+SIDPWLO
        jsr     sidput
        lda     vfxstep+1
        lsr     a
        and     #$07
        clc
        adc     #$04
        ldx     #7+SIDPWHI
        jsr     sidput
        lda     #$00
        ldx     #7+SIDAD
        jsr     sidput
        lda     #$F0
        ldx     #7+SIDSR
        jsr     sidput
        lda     #$41                    ; pulse, gate on
        ldx     #7+SIDCTRL
        jmp     sidput

; ---- fx_explode: voice 3, noise, sharp attack and a long decay ---------
fx_explode:
        lda     #$00
        ldx     #14+SIDFLO
        jsr     sidput
        lda     vfxstep+2
        eor     #$FF
        lsr     a
        lsr     a
        clc
        adc     #$10
        ldx     #14+SIDFHI
        jsr     sidput
        lda     #$09                    ; attack 0, decay 9
        ldx     #14+SIDAD
        jsr     sidput
        lda     #$00
        ldx     #14+SIDSR
        jsr     sidput
        lda     #$81                    ; noise, gate on
        ldx     #14+SIDCTRL
        jmp     sidput

; ---- fx_pldeath: voice 3, the fighter's own death ----------------------
; The enemies' explosion is a 24-frame crack whose pitch barely moves, and
; the player's death used to fire that same effect -- so the one event in the
; game that costs a life sounded exactly like the dozen before it.  This one
; is told apart by all three of the things an ear can use: it runs 32 frames
; (the length of the blast animation, so the sound ends when the fire does),
; it sweeps a long way down ($3000 to $1100, a rumble collapsing rather than
; a crack), and it releases over ~170 ms instead of being cut off.  Priority
; 4 is above every other effect, so an enemy blowing up in the same frame
; cannot take the voice off it half way through.
fx_pldeath:
        lda     #$00
        ldx     #14+SIDFLO
        jsr     sidput
        lda     vfxstep+2               ; $30 at step 0 down to $11 at step 31
        eor     #$FF
        clc
        adc     #49                     ; = 48 - step (mod 256)
        ldx     #14+SIDFHI
        jsr     sidput
        lda     #$0A                    ; attack 0, decay 1.5 s
        ldx     #14+SIDAD
        jsr     sidput
        lda     #$05                    ; sustain 0, release 168 ms
        ldx     #14+SIDSR
        jsr     sidput
        lda     #$81                    ; noise, gate on
        ldx     #14+SIDCTRL
        jmp     sidput

; ---- fx_capture: voice 2, a rising ring-modulated swoop ----------------
fx_capture:
        lda     #$00
        ldx     #7+SIDFLO
        jsr     sidput
        lda     vfxstep+1
        lsr     a
        clc
        adc     #$08
        ldx     #7+SIDFHI
        jsr     sidput
        lda     #$0A
        ldx     #7+SIDAD
        jsr     sidput
        lda     #$A8
        ldx     #7+SIDSR
        jsr     sidput
        lda     #$15                    ; triangle + ring modulation, gate on
        ldx     #7+SIDCTRL
        jmp     sidput

; ---- fx_rescue: voice 1, a hard-synced fanfare rip ---------------------
fx_rescue:
        lda     #$00
        ldx     #SIDFLO
        jsr     sidput
        lda     vfxstep
        clc
        adc     #$14
        ldx     #SIDFHI
        jsr     sidput
        lda     #$06
        ldx     #SIDAD
        jsr     sidput
        lda     #$C8
        ldx     #SIDSR
        jsr     sidput
        lda     #$23                    ; sawtooth + hard sync, gate on
        ldx     #SIDCTRL
        jmp     sidput

; ---- fx_extra: voice 1, the extra-life chime ---------------------------
extratab2:
        .byte   $22, $2B, $33, $44, $33, $44, $33, $44
fx_extra:
        lda     vfxstep
        lsr     a
        lsr     a
        and     #$07
        tay
        lda     #$00
        ldx     #SIDFLO
        jsr     sidput
        lda     extratab2,y
        ldx     #SIDFHI
        jsr     sidput
        lda     #$08
        ldx     #SIDAD
        jsr     sidput
        lda     #$88
        ldx     #SIDSR
        jsr     sidput
        lda     #$41
        ldx     #SIDCTRL
        jmp     sidput

; ==========================================================================
; The sequencer.
;
; A row is one eighth note, six frames long -- ten rows a second, which puts
; a 6/8 bar at six rows and lets the same six rows be read as 3/4 for the
; sesquialtera bars.  The order list is patterns; a pattern is 32 rows of
; three voices; each row entry is (note, instrument+flags).
; ==========================================================================
NOTE_HOLD = 0
NOTE_OFF  = 1

; muslead / muslimit / musdone exist for the audio capture protocol, and are
; zero in normal play.  Arming a capture costs real frames, so a tune that
; starts on the first one loses its opening to the arming: `muslead` is a
; count of silent frames to burn first, consumed once, so the window opens
; before row 0 rather than a phrase and a half into it.  `muslimit` is the
; other edge -- rows to play before the player stops for good -- which turns
; a looping tune into a one-shot cue whose window closes in silence too.
; With both edges silent the reference score is the whole passage and does
; not depend on how long arming took.  Neither touches the position, so a
; capture can be aimed anywhere in the piece (the seam, say) and still get
; clean edges.  The lead-in is NOT baked into the track data: a player that
; looped that would replay the silence every time round.
muslead:    .byte   0
muslimit:   .byte   0
musdone:    .byte   0

musictick:
        lda     mus_on
        bne     mt0
        rts
mt0:    lda     muslead
        beq     mtl
        dec     muslead
        jmp     musicoff                ; silent, and the position does not move
mtl:    lda     mus_tick
        beq     mtrow
        dec     mus_tick
        jmp     mtvoices
mtrow:  lda     musdone
        bne     mtstop
        ; MUS_ROWTICKS-1, not MUS_ROWTICKS: this frame IS the row's first
        ; frame, so the counter only has to carry the other five.  Setting it
        ; to 6 here made every row seven frames long and the whole tune 17%
        ; slow -- a tempo error nothing but a capture could have caught.
        lda     #MUS_ROWTICKS-1
        sta     mus_tick
        jsr     musrow
        lda     muslimit                ; 0 = play forever, which play does
        beq     mtvoices
        dec     muslimit
        bne     mtvoices
        inc     musdone                 ; this row still sounds; the next one
        jmp     mtvoices                ; never comes
mtstop: lda     #0
        sta     mus_on
        jmp     musicoff
mtvoices:
        inc     mus_pw+1                ; the pulse widths breathe on their own
        lda     mus_pw+1                ; slow cycle, independent of the tune
        and     #$07
        bne     :+
        inc     mus_pw
:       ldx     #0
mtv1:   stx     tmp3
        jsr     musvoice
        ldx     tmp3
        inx
        cpx     #3
        bne     mtv1
        rts

; ---- musrow -- read one row of the current pattern into the voices -----
musrow: ldy     mus_ord
        lda     musorder,y
        cmp     #$FF
        bne     mr0
        ; the seam: back to the top with every voice's state reset to what
        ; bar 1 expects, which is what makes the loop inaudible
        lda     #0
        sta     mus_ord
        sta     mus_row
        ldx     #2
mr00:   lda     #0
        sta     mus_vib,x
        sta     mus_slide,x
        sta     mus_slide+3,x
        dex
        bpl     mr00
        lda     #0
        sta     mus_pw
        sta     mus_pw+1
        ldy     #0
        lda     musorder
mr0:    tay
        lda     patlo,y
        sta     PTR
        lda     pathi,y
        sta     PTR+1
        ; offset = row*6
        lda     mus_row
        asl     a
        sta     tmp0
        asl     a
        clc
        adc     tmp0                    ; row*6
        sta     tmp0

        ldx     #0
mr1:    txa
        asl     a
        clc
        adc     tmp0
        tay
        lda     (PTR),y
        beq     mr2                     ; NOTE_HOLD
        cmp     #NOTE_OFF
        bne     mr3
        lda     #0
        sta     mus_gate,x
        jmp     mr2
mr3:    sta     mus_note,x
        lda     #1
        sta     mus_gate,x
        iny
        lda     (PTR),y
        sta     mus_inst,x
        lda     #1
        sta     mus_trig,x
mr2:    inx
        cpx     #3
        bne     mr1

        inc     mus_row
        lda     mus_row
        cmp     #MUS_PATROWS
        bcc     mr9
        lda     #0
        sta     mus_row
        inc     mus_ord
mr9:    rts

; ---- musvoice -- X = voice: pitch, envelope, and the gate --------------
; If an effect holds this voice the state is still computed; only the SID
; write is skipped, so when the effect lets go the music is where it would
; have been -- the player keeps running silently, it does not pause.
musvoice:
        ldy     mus_note,x
        bne     @far25                     ; nothing has ever been played here
        jmp     mv9
@far25:
        lda     mus_inst,x
        and     #$07
        sta     tmp5                    ; instrument
        lda     voicebase,x
        sta     tmp4                    ; register base: 0, 7 or 14

        ; ---- pitch, with the instrument's vibrato ----
        ldy     mus_note,x
        lda     notelo,y
        sta     tmp0
        lda     notehi,y
        sta     tmp1
        ldy     tmp5
        lda     i_vib,y
        beq     mv2
        sta     tmp2                    ; depth
        lda     mus_vib,x
        clc
        adc     #17                     ; a prime step, so it never locks
        sta     mus_vib,x
        and     #$1F
        cmp     #$10
        bcc     mv1
        eor     #$1F                    ; fold into a triangle
mv1:    sec
        sbc     #8
        clc
        adc     tmp2                    ; a signed delta, -8..+depth+7
        ; Sign-extend it into the 16-bit frequency.  Adding a negative byte
        ; SETS the carry when the result needs no borrow, so the old
        ; `bcc/inc tmp1` did the opposite of the right thing on every
        ; downward swing: the note jumped 256 up in the register, which is
        ; 60 cents at A4 and audible as the vibrato tearing.
        tay                             ; keep the sign
        clc
        adc     tmp0
        sta     tmp0
        tya
        bmi     mvdn
        bcc     mv2
        inc     tmp1
        jmp     mv2
mvdn:   bcs     mv2
        dec     tmp1

mv2:    lda     vprio,x
        bne     mv9                     ; an effect owns this voice right now
        stx     tmp3
        ldy     tmp5
        ldx     tmp4
        lda     tmp0
        jsr     sidput                  ; +0 frequency low
        inx
        lda     tmp1
        jsr     sidput                  ; +1 frequency high
        inx
        lda     i_pwlo,y
        jsr     sidput                  ; +2 pulse width low
        inx
        lda     i_pwhi,y
        clc
        adc     mus_pw                  ; the pulse breathes under the tune
        and     #$0F
        jsr     sidput                  ; +3 pulse width high
        inx
        inx                             ; +4 is the control register
        lda     i_ad,y
        jsr     sidput                  ; +5 attack/decay
        inx
        lda     i_sr,y
        jsr     sidput                  ; +6 sustain/release

        ldx     tmp3
        lda     i_wave,y
        sta     tmp2
        lda     mus_gate,x
        beq     mvoff
        lda     mus_trig,x
        beq     mvon
        lda     #0                      ; a new note: one frame of gate-off
        sta     mus_trig,x              ; is the retrigger
        beq     mvoff
mvon:   lda     tmp2
        ora     #$01
        bne     mvctl
mvoff:  lda     tmp2
        and     #$FE
mvctl:  sta     tmp2
        lda     tmp4
        clc
        adc     #SIDCTRL
        tax
        lda     tmp2
        jsr     sidput
        ldx     tmp3
mv9:    rts
