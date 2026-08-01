; sound.s — three SID voices, every write shadowed in RAM.
;
; The SID is write-only, so nothing here can be verified by reading $D400.
; Every single write goes through `sidput`, which stores the byte to the chip
; AND to `sidshadow` — those 25 RAM bytes are the testable evidence that the
; sound engine is doing what it claims.
;
;   voice 1  the four-note descending heartbeat.  Pulse waveform with a pulse
;            width that widens note by note.  sndbeat is called once per
;            formation sweep, so the tempo follows the march: it accelerates
;            because the sweep gets shorter, never from a speed table.
;   voice 2  short effects: the player shot (bright pulse, swept down) and the
;            invader hit (sawtooth, swept down).
;   voice 3  long effects: the UFO warble (triangle, swept back and forth) and
;            the player explosion (NOISE through the low-pass filter, cutoff
;            swept down as it dies away).  Voice 3 is the only voice routed
;            through the filter, so the filter shapes the explosion without
;            touching the music.
;
; Priorities: a request is refused when the voice is already owned by a
; strictly higher-priority effect.  shot = 1, invader hit = 2, UFO = 1,
; player explosion = 3.

        .segment "CODE"

; SID register offsets from $D400
V1FLO = 0
V1FHI = 1
V1PWH = 3
V1CTL = 4
V1AD  = 5
V1SR  = 6
V2FLO = 7
V2FHI = 8
V2PWH = 10
V2CTL = 11
V2AD  = 12
V2SR  = 13
V3FLO = 14
V3FHI = 15
V3CTL = 18
V3AD  = 19
V3SR  = 20
FCHI  = 22
RESFL = 23
MODVOL = 24

; sidput: A = value, X = register offset. The only way to touch the SID.
sidput: sta     $D400,x
        sta     sidshadow,x
        rts

sndinit:
        lda     #0
        ldx     #24
sil2:   jsr     sidput
        lda     #0
        dex
        bpl     sil2
        lda     #$f4                    ; resonance 15, voice 3 -> the filter
        ldx     #RESFL
        jsr     sidput
        lda     #$f0                    ; cutoff wide open to begin with
        ldx     #FCHI
        jsr     sidput
        lda     #$1f                    ; low-pass + volume 15
        ldx     #MODVOL
        jsr     sidput
        ; voice 1: a short percussive thump — attack 2 ms, decay 300 ms,
        ; sustain 0 so it dies on its own between beats
        lda     #$08
        ldx     #V1AD
        jsr     sidput
        lda     #$00
        ldx     #V1SR
        jsr     sidput
        lda     #0
        sta     beatidx
        sta     beatgap
        sta     sndprio2
        sta     sndprio3
        sta     fx2
        sta     fx2t
        sta     fx3
        sta     fx3t
        rts

; ---- the heartbeat -------------------------------------------------------
; sndbeat is called once per completed formation sweep. beatgap is a minimum
; note length (4 ticks): with one invader left the sweep completes every
; frame, and without a floor the notes would retrigger faster than the
; envelope can sound. It bounds the NOTE, never the march.
sndbeat:
        lda     beatgap
        beq     sbgo
        rts
sbgo:   lda     #4
        sta     beatgap
        lda     beatidx
        asl
        tax
        lda     beatfreq,x
        pha
        lda     beatfreq+1,x
        pha
        lda     #$40                    ; gate off first: a retrigger needs an edge
        ldx     #V1CTL
        jsr     sidput
        pla
        ldx     #V1FHI
        jsr     sidput
        pla
        ldx     #V1FLO
        jsr     sidput
        ldx     beatidx
        lda     beatpw,x
        ldx     #V1PWH
        jsr     sidput
        lda     #$41                    ; pulse + gate on
        ldx     #V1CTL
        jsr     sidput
        inc     beatidx
        lda     beatidx
        cmp     #4
        bcc     sbdone
        lda     #0
        sta     beatidx
sbdone: rts

; ---- voice claiming ------------------------------------------------------
; carry set = the voice is yours
claim2: cmp     sndprio2
        bcc     cl2no
        sta     sndprio2
        sec
        rts
cl2no:  clc
        rts

claim3: cmp     sndprio3
        bcc     cl3no
        sta     sndprio3
        sec
        rts
cl3no:  clc
        rts

; ---- effects -------------------------------------------------------------
sfxshot:
        lda     #1
        jsr     claim2
        bcs     sxs
        rts
sxs:    lda     #1
        sta     fx2
        lda     #10
        sta     fx2t
        lda     #$60
        sta     fx2fh
        lda     #8
        sta     fx2rate
        lda     #$41                    ; pulse + gate
        sta     fx2ctl
        lda     #$00
        ldx     #V2AD
        jsr     sidput                  ; attack 2 ms, decay 6 ms
        lda     #$00
        ldx     #V2SR
        jsr     sidput
        lda     #$02                    ; a narrow, bright pulse
        ldx     #V2PWH
        jsr     sidput
        lda     #0
        ldx     #V2FLO
        jsr     sidput
        lda     fx2fh
        ldx     #V2FHI
        jsr     sidput
        lda     fx2ctl
        ldx     #V2CTL
        jmp     sidput

sfxhit: lda     #2
        jsr     claim2
        bcs     sxh
        rts
sxh:    lda     #2
        sta     fx2
        lda     #14
        sta     fx2t
        lda     #$30
        sta     fx2fh
        lda     #3
        sta     fx2rate
        lda     #$21                    ; sawtooth + gate
        sta     fx2ctl
        lda     #$05                    ; attack 2 ms, decay 168 ms
        ldx     #V2AD
        jsr     sidput
        lda     #$00
        ldx     #V2SR
        jsr     sidput
        lda     #0
        ldx     #V2FLO
        jsr     sidput
        lda     fx2fh
        ldx     #V2FHI
        jsr     sidput
        lda     fx2ctl
        ldx     #V2CTL
        jmp     sidput

; an extra-life chime: a triangle blip, borrowing voice 2 at hit priority
sfxextra:
        lda     #2
        jsr     claim2
        bcs     sxe
        rts
sxe:    lda     #2
        sta     fx2
        lda     #20
        sta     fx2t
        lda     #$40
        sta     fx2fh
        lda     #0
        sta     fx2rate                 ; no sweep: a steady chime
        lda     #$11                    ; triangle + gate
        sta     fx2ctl
        lda     #$09
        ldx     #V2AD
        jsr     sidput
        lda     #$00
        ldx     #V2SR
        jsr     sidput
        lda     #0
        ldx     #V2FLO
        jsr     sidput
        lda     fx2fh
        ldx     #V2FHI
        jsr     sidput
        lda     fx2ctl
        ldx     #V2CTL
        jmp     sidput

sfxufo: lda     #1
        jsr     claim3
        bcs     sxu
        rts
sxu:    lda     #1
        sta     fx3
        lda     #240
        sta     fx3t
        lda     #$00
        ldx     #V3AD
        jsr     sidput                  ; instant on
        lda     #$f0
        ldx     #V3SR
        jsr     sidput                  ; sustain 15: it holds while gated
        lda     #$f0                    ; filter wide open for the warble
        ldx     #FCHI
        jsr     sidput
        lda     #0
        ldx     #V3FLO
        jsr     sidput
        lda     #$11                    ; triangle + gate
        ldx     #V3CTL
        jmp     sidput

sfxufooff:
        lda     sndprio3
        cmp     #3
        bcs     suoff                   ; an explosion is playing: leave it
        lda     #0
        sta     fx3
        sta     fx3t
        sta     sndprio3
        ldx     #V3CTL
        jsr     sidput
suoff:  rts

sfxboom:
        lda     #3
        jsr     claim3
        bcs     sxb
        rts
sxb:    lda     #3
        sta     fx3
        lda     #60
        sta     fx3t
        lda     #$f0
        sta     fx3cut
        lda     #$09                    ; attack 2 ms, decay 750 ms
        ldx     #V3AD
        jsr     sidput
        lda     #$00
        ldx     #V3SR
        jsr     sidput
        lda     #$20
        ldx     #V3FLO
        jsr     sidput
        lda     #$18
        ldx     #V3FHI
        jsr     sidput
        lda     #$81                    ; noise + gate, routed through the filter
        ldx     #V3CTL
        jmp     sidput

; ---- per-frame envelope/sweep advance ------------------------------------
sndtick:
        lda     beatgap
        beq     st2v
        dec     beatgap
st2v:   lda     fx2t
        beq     st3v
        dec     fx2t
        lda     fx2rate
        beq     st2n
        lda     fx2fh
        sec
        sbc     fx2rate
        bcs     st2s
        lda     #1
st2s:   sta     fx2fh
        ldx     #V2FHI
        jsr     sidput
st2n:   lda     fx2t
        bne     st3v
        lda     fx2ctl
        and     #$fe                    ; gate off -> release
        ldx     #V2CTL
        jsr     sidput
        lda     #0
        sta     fx2
        sta     sndprio2

st3v:   lda     fx3t
        bne     st3go
        rts
st3go:  dec     fx3t
        lda     fx3
        cmp     #3
        beq     st3boom
        ; the UFO warble: swing the pitch back and forth every few frames
        lda     tick
        and     #4
        beq     st3lo
        lda     #$26
        jmp     st3set
st3lo:  lda     #$1a
st3set: ldx     #V3FHI
        jsr     sidput
        jmp     st3chk
st3boom:
        lda     fx3cut
        sec
        sbc     #4
        bcs     st3c
        lda     #2
st3c:   sta     fx3cut
        ldx     #FCHI
        jsr     sidput
st3chk: lda     fx3t
        bne     st3done
        lda     #0
        ldx     #V3CTL
        jsr     sidput
        lda     #0
        sta     fx3
        sta     sndprio3
        lda     #$f0
        ldx     #FCHI
        jsr     sidput
st3done:
        rts

; four descending notes, roughly 110 / 98 / 87 / 82 Hz
beatfreq: .word $070c, $0647, $0593, $0541
; the pulse width widens note by note, so the timbre opens as it descends
beatpw:  .byte  $02, $04, $06, $08
