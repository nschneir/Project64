; music.s — the sequencer, the SID shadow, and the arrangement.
;
; One CINV wedge per frame drives this (SPEC.md 6.1).  It never rasterises:
; a note onset pushes onto the spawn queue and the main loop paints, so a
; twenty-frame shape cannot stretch a note.
;
; ZERO PAGE: this file uses NONE.  The wedge can interrupt the rasteriser in
; the middle of a span, and the rasteriser's pointers live in zero page, so
; the stream reads below are self-modifying absolute loads instead.  Adding a
; `(zp),y` here would corrupt whatever shape was being painted.
;
; THE ARRANGEMENT is an original three-voice reduction composed for this
; demo.  Tchaikovsky's 1880 score and Rouget de Lisle's 1792 Marseillaise are
; both public domain; the themes below are reduced from their melodic
; outlines, not transcribed from anyone else's SID, MIDI or sheet
; arrangement.

; ---- note names ----------------------------------------------------------
; A note byte is 1..72 = C1..B6, so a pitch is (octave + degree).
; 0 is a rest, $FD fires the cannon, $FF rewinds the stream.

N_C     = 1
N_CS    = 2
N_D     = 3
N_DS    = 4
N_E     = 5
N_F     = 6
N_FS    = 7
N_G     = 8
N_GS    = 9
N_A     = 10
N_AS    = 11
N_B     = 12

OC1     = 0
OC2     = 12
OC3     = 24
OC4     = 36
OC5     = 48
OC6     = 60

REST    = 0
CANNON  = $FD
LOOPS   = $FF                   ; rewind to this section's stream head

        .segment "CODE"

; ==========================================================================
; sidput — the ONLY writer of the SID.
;
;   in: X = register offset $00-$18, A = value
;
; Every write is mirrored into `sidshadow`, because the SID is write-only and
; the shadow is the only testable evidence that sound happened
; (SPEC.md 6.5).  A and X come back unchanged.
; ==========================================================================

sidput: sta     SIDBASE,x
        sta     sidshadow,x
        rts

; --------------------------------------------------------------------------
; sndinit — silence everything, shadow included.
; SID registers survive a program stop, so a left-over gate bit would keep a
; voice sounding or block a new note.
; --------------------------------------------------------------------------

sndinit:
        ldx     #0
        lda     #0
si1:    jsr     sidput
        inx
        cpx     #25
        bne     si1
        rts

; ==========================================================================
; seqreset — point the three voices at the current section's streams and load
; its instruments.  Called from init and from restart, after sndinit.
; ==========================================================================

seqreset:
        lda     #0
        sta     pwphase
        sta     csweep
        sta     noteidx
        jsr     loadpal
        jsr     loadinstr
        jsr     loadstreams
        rts

; --------------------------------------------------------------------------
; loadinstr — write the section's (waveform, AD, SR, PW) for all three voices
; and its filter routing and volume.
; --------------------------------------------------------------------------

loadinstr:
        lda     section         ; section * 15
        asl     a
        asl     a
        asl     a
        asl     a
        sec
        sbc     section
        sta     lisrc
        lda     #0
        sta     livoice
liv:    lda     #0
        sta     liidx
lib:    ldx     lisrc
        lda     secinstr,x
        sta     lival
        ldy     liidx
        lda     instrdst,y
        ldy     livoice
        clc
        adc     vbase,y
        tax
        lda     lival
        jsr     sidput
        inc     lisrc
        inc     liidx
        lda     liidx
        cmp     #5
        bne     lib
        ldy     livoice         ; byte 0 of this voice's row is the waveform
        ldx     lisrc
        lda     secinstr-5,x
        sta     vwave,y
        inc     livoice
        lda     livoice
        cmp     #3
        bne     liv
        ldx     section
        lda     secres,x
        ldx     #$17
        jsr     sidput
        ldx     section
        lda     secvol,x
        ldx     #$18
        jsr     sidput
        rts

; --------------------------------------------------------------------------
; loadstreams — aim the three voices at the section's streams.
; --------------------------------------------------------------------------

loadstreams:
        ldx     section
        lda     sv1l,x
        sta     vptrl+0
        sta     vbasel+0
        lda     sv1h,x
        sta     vptrh+0
        sta     vbaseh+0
        lda     sv2l,x
        sta     vptrl+1
        sta     vbasel+1
        lda     sv2h,x
        sta     vptrh+1
        sta     vbaseh+1
        lda     sv3l,x
        sta     vptrl+2
        sta     vbasel+2
        lda     sv3h,x
        sta     vptrh+2
        sta     vbaseh+2
        ldx     #0
        lda     #0
ls1:    sta     vcnt,x
        sta     vnote,x
        sta     vrel,x
        inx
        cpx     #3
        bne     ls1
        rts

; ==========================================================================
; seqtick — THE FRAME ANCHOR.  Executed once per frame in every section, from
; the wedge.  `c64 until seqtick --count N` is exactly N frames.
; ==========================================================================

seqtick:
        lda     section
        cmp     #5
        beq     sqret           ; the hold: silence, nothing to sequence
        ldx     section
        lda     secframe
        cmp     secframel,x
        lda     secframe+1
        sbc     secframeh,x
        bcc     sqrun
        jsr     nextsec
        lda     section
        cmp     #5
        beq     sqret
sqrun:  ldx     #0
        jsr     voicetick
        ldx     #1
        jsr     voicetick
        ldx     #2
        jsr     voicetick
        jsr     pwtick
        jsr     cantick
sqret:  rts

; --------------------------------------------------------------------------
; nextsec — the section has used its frame budget.  `secchange` is the label
; evidence and tests anchor on.
; --------------------------------------------------------------------------

nextsec:
secchange:
        inc     section
        lda     #0
        sta     secframe
        sta     secframe+1
        sta     noteidx
        jsr     loadpal         ; NOT setpal — see the comment on loadpal
        lda     section
        cmp     #5
        bne     nsplay
        jsr     silence
        rts
nsplay: jsr     loadinstr
        jsr     loadstreams
        rts

; --------------------------------------------------------------------------
; silence — gate every voice off and drop the volume to 0.
; --------------------------------------------------------------------------

silence:
        lda     #0
        sta     cfn
sil1:   ldx     cfn
        lda     vwave,x
        and     #$fe
        sta     gnv
        lda     vbase,x
        clc
        adc     #4
        tax
        lda     gnv
        jsr     sidput
        inc     cfn
        lda     cfn
        cmp     #3
        bne     sil1
        lda     #0
        ldx     #$18
        jsr     sidput
        rts

; ==========================================================================
; voicetick — advance one voice by one frame.
;
;   in: X = voice 0..2
;
; A note is released three frames before its event ends, so the envelope
; retriggers on the next one instead of running the whole section legato.
; ==========================================================================

voicetick:
        stx     vcur
        lda     vcnt,x
        beq     vtfetch
        dec     vcnt,x
        lda     vcnt,x
        cmp     #4
        bcs     vtret
        lda     vrel,x
        bne     vtret
        lda     #1
        sta     vrel,x
        jsr     gateoff
vtret:  rts

; The stream read is self-modifying: see the zero-page note at the top.
; A stream may never BEGIN with $FF, or the rewind below would spin.
vtfetch:
        lda     vptrl,x
        sta     vtld+1
        sta     vtdd+1
        lda     vptrh,x
        sta     vtld+2
        sta     vtdd+2
        ldy     #0
vtld:   lda     $ffff,y         ; the note byte
        cmp     #LOOPS
        bne     vtn2
        lda     vbasel,x
        sta     vptrl,x
        lda     vbaseh,x
        sta     vptrh,x
        jmp     vtfetch
vtn2:   sta     vnote,x
        ldy     #1
vtdd:   lda     $ffff,y         ; the duration in frames
        sta     vcnt,x
        lda     vptrl,x
        clc
        adc     #2
        sta     vptrl,x
        bcc     :+
        inc     vptrh,x
:       lda     #0
        sta     vrel,x
        lda     vnote,x
        beq     vtrest
        cmp     #CANNON
        beq     vtcan
        jsr     gateon
        lda     vcur            ; voice 1's events are the section's note index
        bne     :+
        inc     noteidx
:       jsr     maybespawn
        ldx     vcur
        rts
vtrest: jsr     gateoff
        ldx     vcur
        rts
vtcan:  jsr     cannonfire
        ldx     vcur
        rts

; --------------------------------------------------------------------------
; maybespawn — push a spawn request if this section listens to this voice.
; This is the ONLY place a note onset becomes a shape (SPEC.md 6.2).
; --------------------------------------------------------------------------

maybespawn:
        ldx     section
        lda     secspawn,x
        ldx     vcur
        beq     ms0
        cpx     #1
        beq     ms1
        and     #%100
        jmp     msgo
ms0:    and     #%001
        jmp     msgo
ms1:    and     #%010
msgo:   beq     msno
        lda     vcur
        jsr     qpush
msno:   rts

; --------------------------------------------------------------------------
; gateon / gateoff — X = voice.  Both leave X pointing at the voice again.
; --------------------------------------------------------------------------

gateon: lda     vbase,x
        sta     gnr
        lda     vnote,x
        sec
        sbc     #1              ; note 1 = C1 = notefreq index 0
        tay
        lda     notefreql,y
        ldx     gnr
        jsr     sidput
        ldx     vcur
        lda     vnote,x
        sec
        sbc     #1
        tay
        lda     notefreqh,y
        ldx     gnr
        inx
        jsr     sidput
        ldx     vcur
        lda     vwave,x
        ora     #1              ; gate on: attack/decay/sustain
        sta     gnv
        lda     gnr
        clc
        adc     #4
        tax
        lda     gnv
        jsr     sidput
        ldx     vcur
        rts

gateoff:
        lda     vwave,x
        and     #$fe            ; gate off: release
        sta     gnv
        lda     vbase,x
        clc
        adc     #4
        tax
        lda     gnv
        jsr     sidput
        ldx     vcur
        rts

; ==========================================================================
; cannonfire — one of the sixteen shots (SPEC.md 6.6).
;
; Filtered noise on voice 3 with the cutoff swept down over 24 frames, a
; six-frame whole-screen flash (border included — bit-pair 00 is the
; unpainted ink, so flashing $D021 flashes everything that is still black),
; and a burst of one large shape plus six small ones.
; ==========================================================================

cannonfire:
        lda     #$80            ; voice 3 is noise for the duration
        sta     vwave+2
        ldx     #14+5
        lda     #$0a            ; attack 2 ms, decay 1.5 s
        jsr     sidput
        ldx     #14+6
        lda     #$08            ; no sustain, release 300 ms
        jsr     sidput
        ldx     #14+0
        lda     #$40            ; a low noise pitch: a boom, not a hiss
        jsr     sidput
        ldx     #14+1
        lda     #$04
        jsr     sidput
        ldx     #14+4
        lda     #$81            ; noise + gate on
        jsr     sidput
        ldx     #$17
        lda     #$f4            ; resonance $F, voice 3 through the filter
        jsr     sidput
        ldx     #$18
        lda     #$1f            ; low-pass, volume 15
        jsr     sidput
        lda     #$ff            ; the sweep's SEED, not a register write: this
        sta     cutoff          ; is the `cutoff` variable, and cantick — the
                                ; only writer of $D416 outside sndinit — runs
                                ; later in the same seqtick and subtracts 10
                                ; before its first store, so the first value
                                ; the chip ever sees is $F5.
        lda     #24
        sta     csweep
        lda     #6
        sta     flash
        inc     cannons
        lda     #128            ; the one large shape
        jsr     qpush
        lda     #6
        sta     cfn
cf1:    lda     #129            ; and six small ones
        jsr     qpush
        dec     cfn
        bne     cf1
        rts

; --------------------------------------------------------------------------
; cantick — sweep the cannon's cutoff down one step per frame.
; --------------------------------------------------------------------------

cantick:
        lda     csweep
        beq     ctret
        dec     csweep
        lda     cutoff
        cmp     #$1a
        bcc     ctfloor
        sec
        sbc     #10
        jmp     ctset
ctfloor:
        lda     #$10
ctset:  sta     cutoff
        ldx     #$16
        jsr     sidput
ctret:  rts

; --------------------------------------------------------------------------
; pwtick — sweep voice 1's pulse width with a slow triangle, in the sections
; whose voice 1 is a pulse.  A static pulse is a dead sound; the sweep is
; what makes the march and the finale move.
; --------------------------------------------------------------------------

pwtick: ldx     section
        lda     secpw,x
        beq     ptret
        sta     gnv             ; the base $D403 value
        lda     pwphase
        clc
        adc     #2
        sta     pwphase
        tax
        lda     sintab,x
        cmp     #$80            ; arithmetic >> 5: +-127 becomes +-3
        ror     a
        cmp     #$80
        ror     a
        cmp     #$80
        ror     a
        cmp     #$80
        ror     a
        cmp     #$80
        ror     a
        clc
        adc     gnv
        ldx     #$03
        jsr     sidput
ptret:  rts

        .segment "RODATA"

vbase:  .byte   0, 7, 14        ; SID register base per voice
instrdst:
        .byte   4, 5, 6, 2, 3   ; where secinstr's five bytes go, relative to
                                ; the voice base: ctrl, AD, SR, PW lo, PW hi

; ==========================================================================
; The score.  Each stream is (note, duration-in-frames) pairs, ending in
; LOOPS so a short ostinato fills its section.  Durations are frames at
; 60 Hz, so 60 = one second; the maximum is 255.
; ==========================================================================

sv1l:   .byte   <s0v1, <s1v1, <s2v1, <s3v1, <s4v1, <s5v
sv1h:   .byte   >s0v1, >s1v1, >s2v1, >s3v1, >s4v1, >s5v
sv2l:   .byte   <s0v2, <s1v2, <s2v2, <s3v2, <s4v2, <s5v
sv2h:   .byte   >s0v2, >s1v2, >s2v2, >s3v2, >s4v2, >s5v
sv3l:   .byte   <s0v3, <s1v3, <s2v3, <s3v3, <s4v3, <s5v
sv3h:   .byte   >s0v3, >s1v3, >s2v3, >s3v3, >s4v3, >s5v

; ---- 0: the hymn, "O Lord, Save Thy People" ------------------------------
; E minor, quarter = 60 frames (one second).  A rising fourth, a stepwise
; descent, and a long held tonic — the shape of the troparion, reduced.

s0v1:   .byte   OC4+N_E, 120,  OC4+N_E,  60,  OC4+N_FS, 60,  OC4+N_G, 120
        .byte   OC4+N_A, 120,  OC4+N_G,  60,  OC4+N_FS, 60,  OC4+N_E, 240
        .byte   OC4+N_G, 120,  OC4+N_A, 120,  OC4+N_B, 240,  OC4+N_A, 120
        .byte   OC4+N_G, 120,  OC4+N_FS,120,  OC4+N_E, 240,  REST,    120
        .byte   LOOPS

s0v2:   .byte   OC3+N_B, 120,  OC3+N_B,  60,  OC3+N_A,  60,  OC3+N_B, 120
        .byte   OC4+N_C, 120,  OC3+N_B,  60,  OC3+N_A,  60,  OC3+N_G, 240
        .byte   OC4+N_E, 120,  OC4+N_FS,120,  OC4+N_G, 240,  OC4+N_FS,120
        .byte   OC4+N_E, 120,  OC4+N_D, 120,  OC3+N_B, 240,  REST,    120
        .byte   LOOPS

s0v3:   .byte   OC2+N_E, 240,  OC2+N_E, 240,  OC2+N_A, 240,  OC2+N_A, 120
        .byte   OC2+N_B, 240,  OC2+N_B, 120,  OC2+N_E, 240,  OC2+N_E, 240
        .byte   OC3+N_C, 240,  OC3+N_C, 120,  OC2+N_A, 240,  OC2+N_B, 240
        .byte   OC2+N_E, 240,  REST,     60
        .byte   LOOPS

; ---- 1: the Marseillaise fragment ----------------------------------------
; G major, quarter = 32 frames.  The dotted anacrusis and the rising fourth
; into the held note — the anthem's first gesture, reduced.

s1v1:   .byte   OC4+N_D,  16,  OC4+N_D,  16,  OC4+N_G,  48,  OC4+N_G,  16
        .byte   OC4+N_A,  48,  OC4+N_A,  16,  OC5+N_D,  64,  OC4+N_B,  48
        .byte   OC4+N_G,  16,  OC4+N_G,  32,  OC4+N_B,  32,  OC4+N_G,  32
        .byte   OC4+N_E,  32,  OC4+N_D,  64
        .byte   OC4+N_G,  16,  OC4+N_G,  16,  OC4+N_B,  48,  OC4+N_B,  16
        .byte   OC5+N_D,  48,  OC5+N_D,  16,  OC5+N_G,  64,  OC5+N_D,  48
        .byte   OC4+N_B,  16,  OC4+N_G,  32,  OC4+N_A,  32,  OC4+N_B,  32
        .byte   OC4+N_A,  32,  OC4+N_G,  64
        .byte   LOOPS

s1v2:   .byte   OC3+N_B,  32,  OC4+N_D,  32,  OC3+N_B,  32,  OC4+N_D,  32
        .byte   OC4+N_C,  32,  OC4+N_E,  32,  OC4+N_C,  32,  OC4+N_E,  32
        .byte   OC3+N_B,  32,  OC4+N_D,  32,  OC3+N_B,  32,  OC4+N_D,  32
        .byte   OC3+N_A,  32,  OC4+N_D,  32,  OC3+N_B,  32,  OC3+N_G,  32
        .byte   LOOPS

s1v3:   .byte   OC2+N_G,  32,  OC2+N_G,  32,  OC3+N_D,  32,  OC3+N_D,  32
        .byte   OC3+N_C,  32,  OC3+N_C,  32,  OC3+N_D,  32,  OC3+N_D,  32
        .byte   OC2+N_G,  32,  OC2+N_G,  32,  OC2+N_B,  32,  OC2+N_B,  32
        .byte   OC3+N_D,  32,  OC3+N_D,  32,  OC2+N_G,  64
        .byte   LOOPS

; ---- 2: the battle -------------------------------------------------------
; Chromatic, sixteenths at 6 frames.  Running figures against off-beat stabs
; over a driving octave bass — agitation, not melody.

s2v1:   .byte   OC4+N_E,   6,  OC4+N_F,   6,  OC4+N_FS,  6,  OC4+N_G,   6
        .byte   OC4+N_GS,  6,  OC4+N_A,   6,  OC4+N_AS,  6,  OC4+N_B,   6
        .byte   OC4+N_AS,  6,  OC4+N_A,   6,  OC4+N_GS,  6,  OC4+N_G,   6
        .byte   OC4+N_FS,  6,  OC4+N_F,   6,  OC4+N_E,   6,  OC4+N_DS,  6
        .byte   OC4+N_B,   6,  OC5+N_C,   6,  OC5+N_CS,  6,  OC5+N_D,   6
        .byte   OC5+N_DS,  6,  OC5+N_E,   6,  OC5+N_DS,  6,  OC5+N_D,   6
        .byte   OC5+N_CS,  6,  OC5+N_C,   6,  OC4+N_B,   6,  OC4+N_AS,  6
        .byte   OC4+N_A,   6,  OC4+N_GS,  6,  OC4+N_G,   6,  OC4+N_FS,  6
        .byte   LOOPS

s2v2:   .byte   REST,      6,  OC5+N_E,   6,  REST,      6,  OC4+N_B,   6
        .byte   REST,      6,  OC5+N_E,   6,  REST,      6,  OC4+N_G,   6
        .byte   REST,      6,  OC5+N_FS,  6,  REST,      6,  OC4+N_B,   6
        .byte   REST,      6,  OC5+N_E,   6,  REST,      6,  OC5+N_G,   6
        .byte   LOOPS

s2v3:   .byte   OC2+N_E,  12,  OC3+N_E,  12,  OC2+N_E,  12,  OC3+N_E,  12
        .byte   OC2+N_D,  12,  OC3+N_D,  12,  OC2+N_D,  12,  OC3+N_D,  12
        .byte   OC2+N_C,  12,  OC3+N_C,  12,  OC2+N_C,  12,  OC3+N_C,  12
        .byte   OC1+N_B,  12,  OC2+N_B,  12,  OC1+N_B,  12,  OC2+N_B,  12
        .byte   LOOPS

; ---- 3: the cannon -------------------------------------------------------
; The hymn returns wide-spaced over sustained chords, and voice 3 is nothing
; but artillery: sixteen shots of duration 112.
;
; 112 is the DURATION BYTE, not the interval.  An event owns duration + 1
; ticks — voicetick fetches on the frame vcnt reaches 0 and does not decrement
; it again that frame (see vtfetch and the `dec vcnt,x` above it) — so the
; shots arrive 113 ticks apart, on section-3 ticks 1 + 113(k-1), and sixteen
; of them ask for 16 * 113 = 1808 ticks against the section's 1800.  Shot 16
; is fetched on tick 1696 and truncated by 8: its gate-off would be due on
; tick 1805, so nothing inside this section clears it and section 4's
; loadinstr does it instead, writing $14 with the gate bit clear.  `cannons`
; still reads 16 either way, because `inc cannons` fires at the fetch.

s3v1:   .byte   OC4+N_E, 240,  OC4+N_G, 240,  OC4+N_A, 240,  OC4+N_B, 240
        .byte   OC4+N_B, 240,  OC4+N_A, 240,  OC4+N_G, 240,  OC4+N_E, 240
        .byte   LOOPS

s3v2:   .byte   OC3+N_B, 240,  OC4+N_C, 240,  OC4+N_D, 240,  OC4+N_E, 240
        .byte   OC4+N_E, 240,  OC4+N_D, 240,  OC3+N_B, 240,  OC3+N_G, 240
        .byte   LOOPS

s3v3:   .byte   CANNON, 112,  CANNON, 112,  CANNON, 112,  CANNON, 112
        .byte   CANNON, 112,  CANNON, 112,  CANNON, 112,  CANNON, 112
        .byte   CANNON, 112,  CANNON, 112,  CANNON, 112,  CANNON, 112
        .byte   CANNON, 112,  CANNON, 112,  CANNON, 112,  CANNON, 112
        .byte   LOOPS

; ---- 4: the finale -------------------------------------------------------
; The hymn in E major, up an octave, over a ring-modulated bell line.

s4v1:   .byte   OC5+N_E,  60,  OC5+N_E,  30,  OC5+N_FS, 30,  OC5+N_GS, 60
        .byte   OC5+N_A,  60,  OC5+N_GS, 30,  OC5+N_FS, 30,  OC5+N_E, 120
        .byte   OC5+N_GS, 60,  OC5+N_A,  60,  OC5+N_B, 120,  OC5+N_A,  60
        .byte   OC5+N_GS, 60,  OC5+N_FS, 60,  OC5+N_E, 180,  REST,     60
        .byte   LOOPS

s4v2:   .byte   OC4+N_B,  30,  OC4+N_GS, 30,  OC4+N_E,  30,  OC4+N_GS, 30
        .byte   OC4+N_B,  30,  OC5+N_CS, 30,  OC4+N_A,  30,  OC5+N_CS, 30
        .byte   OC4+N_B,  30,  OC4+N_GS, 30,  OC4+N_E,  30,  OC4+N_GS, 30
        .byte   OC4+N_FS, 30,  OC4+N_A,  30,  OC5+N_DS, 30,  OC4+N_FS, 30
        .byte   LOOPS

s4v3:   .byte   OC4+N_E,  30,  OC4+N_B,  30,  OC5+N_E,  30,  OC4+N_B,  30
        .byte   OC4+N_GS, 30,  OC5+N_E,  30,  OC4+N_B,  30,  OC5+N_E,  30
        .byte   OC4+N_FS, 30,  OC5+N_CS, 30,  OC5+N_FS, 30,  OC5+N_CS, 30
        .byte   OC4+N_E,  30,  OC4+N_B,  30,  OC5+N_E,  30,  OC4+N_B,  30
        .byte   LOOPS

; ---- 5: the hold ---------------------------------------------------------
; Never ticked (seqtick returns early at section 5), but the pointers have to
; be valid, so all three voices share one silent stream.

s5v:    .byte   REST, 240
        .byte   LOOPS
