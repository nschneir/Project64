; sound.s -- the impact synth (SPEC.md Section 8).
;
; A struck body is three things at once: a bright inharmonic transient, a
; pitched thump under it, and a decay.  Voice 1 is the thump (triangle, one
; pitch per impact), voice 2 is the strike (noise), and the filter's resonant
; low-pass cutoff collapsing over that noise is the "boing" itself.  Voice 3 is
; silent for the life of the run -- an assertion, not an omission, and one the
; SID shadow's bytes 14-20 can be asked about at any stop.
;
; sound_impact only stages the event; sound_step owns every register write, so
; the schedule has exactly one author and a frame's worth of SID state can be
; read off snd_timer alone.

; SID register OFFSETS, which is what sidput takes -- never addresses, so that
; the grep for a bare `sta $D4xx` has exactly one hit to find: the one below,
; written as a literal rather than through an equate precisely so the grep can
; see it and confirm it is the only one.
V1FLO   = $00                   ; voice 1 frequency low / high
V1FHI   = $01
V1CTRL  = $04                   ; waveform + gate: bit 4 triangle, bit 0 gate
V1AD    = $05                   ; attack (high nybble) / decay (low)
V1SR    = $06                   ; sustain LEVEL (high) / release rate (low)
V2FLO   = $07
V2FHI   = $08
V2CTRL  = $0B                   ; bit 7 noise, bit 0 gate
V2AD    = $0C
V2SR    = $0D
FCHI    = $16                   ; filter cutoff, main 8 bits
FCRES   = $17                   ; resonance (bits 4-7) + routing (bit n = voice)
FCMODE  = $18                   ; filter mode (bit 4 low-pass) + volume (0-3)

SNDIDLE = 24                    ; snd_timer's parked value; the window is 0-23

        .segment "CODE"

; ---------------------------------------------------------------------------
; sidput -- A = value, X = SID register offset 0-24.  EVERY SID write in this
; demo goes through here: the SID is write-only, so sid_shadow is the only thing
; a stopped machine can be asked what the program played.  A bare `sta $D4xx`
; anywhere else is a defect, not a shortcut.  A and X come back unchanged, which
; is what lets startup's zeroing loop keep its counter in X.
sidput: sta     $D400,x
        sta     sid_shadow,x
        rts

; ---------------------------------------------------------------------------
; sound_init -- silence the chip, then set the two registers that never change.
;
; The zeroing is not belt-and-braces: SID registers keep their values when a
; program stops and RUN/STOP-RESTORE does not fully silence the chip, so a gate
; bit left set by the previous run keeps a voice sounding or blocks the first
; note of this one (references/hardware.md, "SID technique and gotchas").
; start: has already done this once before room_init; doing it again here is
; what makes sound_init correct on its own terms rather than by arrangement.
;
; $D417 and $D418 are written once and never again: the filter's routing,
; resonance, mode and the master volume are properties of the instrument, not
; of any one impact, so sound_step has one less thing to re-establish per note.
sound_init:
        lda     #$00
        ldx     #24
sndzero: jsr    sidput          ; preserves A and X
        dex
        bpl     sndzero

        lda     #$F2            ; resonance 15, routing bit 1 = voice 2 only:
        ldx     #FCRES          ; the noise goes through the filter, the thump
        jsr     sidput          ; stays dry so the pitch survives the sweep

        lda     #$1F            ; bit 4 low-pass, volume 15
        ldx     #FCMODE
        jsr     sidput

        lda     #SNDIDLE        ; parked: sound_step returns immediately until
        sta     snd_timer       ; an impact stages one
        rts

; ---------------------------------------------------------------------------
; sound_impact -- A = 1 floor, 2 wall-left, 3 wall-right.  Stages the event and
; nothing else; it writes no SID register, because sound_step owns the whole
; schedule and two authors is how a note ends up half-written.  Both walls
; collapse to kind 2: the pitch is a property of the surface struck, and the
; two walls are the same surface.  A new impact inside the window restarts it.
sound_impact:
        cmp     #$02
        bcc     impstore        ; A = 1, the floor, stored as-is
        lda     #$02            ; A = 2 or 3, either wall
impstore:
        sta     snd_kind
        lda     #$00
        sta     snd_timer
        rts

; ---------------------------------------------------------------------------
; sound_step -- one frame of the schedule, called from tick every frame.
;
;   timer  writes
;   0      both envelopes, both frequencies, both gates on
;   0-15   $D416 <- cut_floor[timer] or cut_wall[timer]
;   20     both gates off (the release, 6 ms, is already over by 24)
;   24     idle: return before touching anything
;
; The envelope is a pure decay -- sustain level 0 -- so the note is over well
; before the gate falls at 20.  That is what a struck body does, and it is why
; sustain is 0 rather than a level (SPEC.md Section 8).
sound_step:
        lda     snd_timer
        cmp     #SNDIDLE
        bcs     stepout         ; idle (>= 24): nothing to do, and do not count
        cmp     #$00
        bne     stepswp
        jsr     sndattack       ; the frame of the strike

stepswp:
        lda     snd_timer
        cmp     #16
        bcs     stepgate        ; past the sweep window
        tax
        ldy     snd_kind
        cpy     #$01
        bne     stepwcut
        lda     cut_floor,x
        jmp     stepput
stepwcut:
        lda     cut_wall,x
stepput:
        ldx     #FCHI           ; the descending resonant cutoff: the "boing"
        jsr     sidput

stepgate:
        lda     snd_timer
        cmp     #20
        bne     stepinc
        lda     #$10            ; triangle, gate off -> release
        ldx     #V1CTRL
        jsr     sidput
        lda     #$80            ; noise, gate off
        ldx     #V2CTRL
        jsr     sidput

stepinc:
        inc     snd_timer
stepout:
        rts

; ---------------------------------------------------------------------------
; sndattack -- everything that happens on the frame of the impact itself.
;
; Frequencies are Fn = round(Hz x 16.40483) at the NTSC clock: floor A2 110.00
; Hz = 1805 = $070D, wall E3 164.81 Hz = 2704 = $0A90.  The floor is the lower
; note because it is the heavier body.  Voice 2's "frequency" is the noise
; generator's clock rather than a pitch: it sets how bright the hiss is before
; the filter touches it, $1000 floor / $1800 wall.
sndattack:
        lda     #$08            ; attack nybble 0 = 2 ms, decay nybble 8 = 300 ms
        ldx     #V1AD
        jsr     sidput
        lda     #$00            ; sustain level 0, release 6 ms
        ldx     #V1SR
        jsr     sidput
        lda     #$06            ; attack 2 ms, decay 204 ms -- the transient is
        ldx     #V2AD           ; still shorter than the thump it sits on (300
                                ; ms), and now it outlasts about three quarters
                                ; of the 267 ms cutoff sweep instead of being
                                ; 30 dB down by frame 7.  $04 = 114 ms spent
                                ; nine of the sixteen sweep frames on a voice
                                ; nobody could hear (AUDIT.md iteration 1).
        jsr     sidput
        lda     #$00
        ldx     #V2SR
        jsr     sidput

        lda     snd_kind
        cmp     #$01
        bne     atkwall

        lda     #$0D            ; floor: voice 1 = 1805 ($070D), A2
        ldx     #V1FLO
        jsr     sidput
        lda     #$07
        ldx     #V1FHI
        jsr     sidput
        lda     #$00            ; floor: voice 2 noise clock = $1000
        ldx     #V2FLO
        jsr     sidput
        lda     #$10
        ldx     #V2FHI
        jsr     sidput
        jmp     atkgate

atkwall:
        lda     #$90            ; wall: voice 1 = 2704 ($0A90), E3
        ldx     #V1FLO
        jsr     sidput
        lda     #$0A
        ldx     #V1FHI
        jsr     sidput
        lda     #$00            ; wall: voice 2 noise clock = $1800, brighter
        ldx     #V2FLO
        jsr     sidput
        lda     #$18
        ldx     #V2FHI
        jsr     sidput

atkgate:
        lda     #$11            ; triangle + gate on
        ldx     #V1CTRL
        jsr     sidput
        lda     #$81            ; noise + gate on, struck with the same frame
        ldx     #V2CTRL
        jsr     sidput
        rts
