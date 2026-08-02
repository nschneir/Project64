; spawn.s — randomness, the spawn queue, and the per-section shape policy.
;
; The queue is the whole coupling between the music and the picture: the
; sequencer pushes on a note onset and the main loop pops and paints, so a
; slow shape can never stretch a note (SPEC.md 6.2).

        .segment "CODE"

; ==========================================================================
; rnd — 16-bit Galois LFSR, taps $B400 (period 65535).
;
;   out: A = a fresh pseudo-random byte (low EOR high), rng advanced
;
; The state must never be zero — 0 is the fixed point.  `resetstate` forces a
; zero seed to 1, and the taps never reach 0 from a nonzero state, so there
; is no check in here.
; ==========================================================================

rnd:    lsr     rng+1
        ror     rng
        bcc     :+
        lda     rng+1
        eor     #$b4
        sta     rng+1
:       lda     rng
        eor     rng+1
        rts

; --------------------------------------------------------------------------
; rndlt — a random value in 0..A-1, by SCALING: v = (rnd * bound) >> 8.
;
; Reject-and-retry is the textbook answer and it was wrong twice over here.
;
; It was BIASED: consecutive outputs of a right-shifting LFSR differ by one
; shift, so they are not independent draws.  Rejecting until a value fell
; below 8 therefore almost always stopped on the value whose bit 3 had just
; shifted into bit 2 — patterns 4-7 came up four times as often as 0-3, and
; pattern 3 never appeared at all across a whole 889-shape run (patseen =
; $F3, measured, not suspected).
;
; It was also SLOW: the expected number of draws is 256/bound, so the bounds
; this demo actually uses — 3 for the ink, 4 for the type, 8 for the dither —
; cost 85, 64 and 32 draws each, about 200 per shape.  That alone was enough
; to blow the battle's shape budget.
;
; Scaling reads the TOP bits of one draw, which are the freshly shifted-in
; bits, so it is both correlation-free and a single draw.  It is uniform to
; within one part in floor(256/bound): exact for the powers of two, and a few
; percent for 3 and 21 — far inside what a random picture can show.
; --------------------------------------------------------------------------

rndlt:  sta     MULB            ; the bound
        jsr     rnd
        sta     MULA
        jsr     umul
        lda     MULR+1          ; the high byte IS (rnd * bound) >> 8
        rts

; ==========================================================================
; qpush / qpop — the 16-entry spawn ring buffer.
;
; One slot is left unused so head == tail means empty and never "full", which
; caps the real capacity at 15.  A push onto a full queue increments
; `dropped` and is discarded: shapes must never lag the music, and `dropped`
; is the measurement that prices the shape budget (SPEC.md 6.2).
; `dropped` saturates at 255 rather than wrapping, so it can't read as 0.
; ==========================================================================

qpush:  sta     qpv
        lda     qhead
        clc
        adc     #1
        and     #15
        cmp     qtail
        beq     qfull
        ldx     qhead
        lda     qpv
        sta     queue,x
        lda     qhead
        clc
        adc     #1
        and     #15
        sta     qhead
        rts
qfull:  inc     dropped
        bne     :+
        dec     dropped
:       rts

qpop:   lda     qtail
        cmp     qhead
        beq     qempty
        tax
        lda     queue,x
        sta     qpv
        txa
        clc
        adc     #1
        and     #15
        sta     qtail
        lda     qpv
        sec                     ; carry set: A holds a payload
        rts
qempty: clc
        rts

; ==========================================================================
; pickshape — draw one shape's parameters from the RNG, inside the current
; section's policy (SPEC.md 5.1).
;
;   in:  A = the queue payload
;          0..2   a note onset on that voice
;          128    the cannon's one large shape
;          129    one of the cannon's six small ones
;   out: sh_type sh_size sh_cx sh_cy sh_angle sh_pat sh_ink
;
; The type is drawn from the section's 16-bit mask by first flattening the
; mask into a list, so every allowed type is equally likely however sparse
; the mask is — a reject-and-retry on the mask would loop unboundedly if a
; section ever allowed only one type.
; ==========================================================================

pickshape:
        sta     pspay
        ldx     section
        lda     secshapel,x
        sta     t0
        lda     secshapeh,x
        sta     t1
        lda     #0
        sta     psn
        sta     psi
psscan: lsr     t1
        ror     t0
        bcc     psnb
        ldx     psn
        lda     psi
        sta     pslist,x
        inc     psn
psnb:   inc     psi
        lda     psi
        cmp     #NSHAPE
        bne     psscan
        lda     psn
        jsr     rndlt
        tax
        lda     pslist,x
        sta     sh_type

        lda     pspay           ; the cannon overrides the section's range
        cmp     #128
        beq     psbig
        cmp     #129
        beq     pssmall
        ldx     section
        lda     secsizehi,x
        sec
        sbc     secsizelo,x
        clc
        adc     #1
        jsr     rndlt
        ldx     section
        clc
        adc     secsizelo,x
        sta     sh_size
        jmp     pspos
psbig:  lda     #21             ; 70..90
        jsr     rndlt
        clc
        adc     #70
        sta     sh_size
        jmp     pspos
pssmall:
        lda     #13             ; 8..20
        jsr     rndlt
        clc
        adc     #8
        sta     sh_size

pspos:  lda     #160            ; centres anywhere on the canvas; a shape near
        jsr     rndlt           ; an edge simply runs off it and is clipped
        sta     sh_cx
        lda     #200
        jsr     rndlt
        sta     sh_cy
        jsr     rnd
        sta     sh_angle
        lda     #NPAT
        jsr     rndlt
        sta     sh_pat
        lda     #3
        jsr     rndlt
        clc
        adc     #1              ; ink 1..3; 0 is the background
        sta     sh_ink
        rts
