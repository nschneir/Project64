; music.s -- the sequencer, the SID writes, and the two sweeps.
;
; Split in two on purpose.  musfetch decides what each voice is doing this
; frame; muswrite puts it in the chip.  glowtick runs BETWEEN them, so the
; sprites are positioned from this frame's note instead of lagging it by a
; frame on every attack -- see the frame order in tick (fugue.s).
;
; Every SID write goes through sidwr, which mirrors it into `sidshadow`.  On
; real hardware $D400-$D418 is write-only, so the shadow is the program's own
; evidence and the only kind that survives off the emulator; the register log
; from `c64 audio capture` is the emulator's.  Keep both -- they fail in
; different directions, and the shadow cannot catch a player writing correct
; bytes to the wrong voice because it agrees with the code by construction.

        .segment "CODE"

sidbase: .byte  0, 7, 14        ; voice v's registers start at $D400 + 7*v
wavetab: .byte  $40, $20, $10   ; pulse (subject), sawtooth (countersubject),
                                ;   triangle (bass, through the filter).
                                ;   Chosen so each line stays separable by
                                ;   ear rather than three identical tones.
adtab:  .byte   $08, $17, $09   ; attack/decay
srtab:  .byte   $A6, $95, $B7   ; sustain/release.  Voice 3's sustain is the
                                ;   highest deliberately: low notes sound
                                ;   weaker than high ones of the same
                                ;   amplitude on the 6581, so the bass needs
                                ;   the level (hardware.md, 6581 caveats).

; --------------------------------------------------------------------------
; musinit
; --------------------------------------------------------------------------
musinit:
        lda     #0              ; zero all 25 registers first: SID keeps its
        ldx     #24             ;   values across a stop, and a left-over
mizero: sta     SID,x           ;   gate bit blocks a new note
        sta     sidshadow,x
        dex
        bpl     mizero

        ldx     #0
mienv:  stx     tmpv
        lda     sidbase,x
        clc
        adc     #5
        tax                     ; base+5 = attack/decay
        ldy     tmpv
        lda     adtab,y
        jsr     sidwr
        ldy     tmpv
        lda     sidbase,y
        clc
        adc     #6
        tax                     ; base+6 = sustain/release
        lda     srtab,y
        jsr     sidwr
        ldy     tmpv
        lda     sidbase,y
        clc
        adc     #4
        tax                     ; base+4 = control: waveform, gate low
        lda     wavetab,y
        jsr     sidwr
        ldx     tmpv
        inx
        cpx     #3
        bne     mienv

        ldx     #23             ; $D417 resonance 10 + voice 3 through the
        lda     #$A4            ;   filter
        jsr     sidwr
        ldx     #24             ; $D418 volume 15 + low-pass.  Bit 7 stays
        lda     #$1F            ;   CLEAR -- it would disconnect voice 3
        jsr     sidwr           ;   from the output altogether
        ldx     #22
        lda     #$70            ; base cutoff, high enough that the bass is
        jsr     sidwr           ;   present rather than swallowed
        ldx     #21
        lda     #0
        jsr     sidwr

        ; The note table is built for the machine we are actually on.  An
        ; NTSC-tuned table played on a PAL machine is 65 cents flat on every
        ; note, and shipping both costs 224 bytes.
        lda     videostd
        bne     mipal
        ldx     #55
mintsc: lda     ntsclo,x
        sta     freqlo,x
        lda     ntschi,x
        sta     freqhi,x
        dex
        bpl     mintsc
        rts
mipal:  ldx     #55
mipall: lda     pallo,x
        sta     freqlo,x
        lda     palhi,x
        sta     freqhi,x
        dex
        bpl     mipall
        rts

; --------------------------------------------------------------------------
; musfetch -- advance the musical clock and decide each voice's note.
; Runs every frame; does real work only on attack frames.
; --------------------------------------------------------------------------
musfetch:
        lda     #0
        sta     vatk+0
        sta     vatk+1
        sta     vatk+2
        lda     state
        cmp     #3
        beq     mfrts
        lda     sf+1
        bne     mfplay
        lda     sf
        cmp     #LEADIN
        bcc     mflead          ; scrolling, but still silent
mfplay: lda     #2
        sta     state
        lda     sf
        and     #7
        beq     mfatk
mfrts:  rts
mflead: lda     #1
        sta     state
        rts

mfatk:  lda     sf              ; sixteenth = (sf - LEADIN) >> 3
        sec
        sbc     #<LEADIN
        sta     tmp0
        lda     sf+1
        sbc     #>LEADIN
        sta     tmp1
        lsr     tmp1
        ror     tmp0
        lsr     tmp1
        ror     tmp0
        lsr     tmp1
        ror     tmp0
        lda     tmp1
        cmp     #>NSIX
        bcc     mfok
        bne     mfend
        lda     tmp0
        cmp     #<NSIX
        bcc     mfok
mfend:  lda     #3              ; the piece is over: release every gate and
        sta     state           ;   halt the scroll, leaving the final chord
        lda     #0              ;   on screen and backlit.  No loop, no fade.
        sta     vnote+0
        sta     vnote+1
        sta     vnote+2
        lda     #$FF
        sta     vpos+0
        sta     vpos+1
        sta     vpos+2
        rts

mfok:   lda     tmp0
        sta     sixteenth
        sta     dk
        lda     tmp1
        sta     sixteenth+1
        sta     dk+1
        lda     tmp0            ; bar / beat / slot, for the tests and the
        and     #15             ;   evidence protocol to name a moment by
        sta     slot
        lsr     a
        lsr     a
        clc
        adc     #1
        sta     beat
        lda     tmp0
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     tmp2
        lda     tmp1
        beq     mfbar
        lda     tmp2
        clc
        adc     #16
        sta     tmp2
mfbar:  lda     tmp2
        clc
        adc     #1
        sta     bar

        jsr     fetchnotes      ; staff.s -- the SAME fetch and the SAME
                                ;   decoder the renderer uses, so the pitch
                                ;   heard and the head drawn cannot disagree
        ldx     #0
mfv:    lda     nb,x
        cmp     #$FF
        beq     mfvnx           ; hold: the note continues, gate untouched
        cmp     #0
        bne     mfvon
        lda     #0              ; rest
        sta     vnote,x
        lda     #$FF
        sta     vpos,x
        jmp     mfvnx
mfvon:  lda     nmidi,x
        sta     vnote,x
        lda     np,x
        sta     vpos,x
        lda     nacc,x
        sta     vacc,x
        lda     #1
        sta     vatk,x
        stx     tmpv            ; bump this voice's 16-bit attack counter.
        txa                     ;   v1idx/v2idx/v3idx are contiguous words.
        asl     a
        tax
        inc     v1idx,x
        bne     mfvi
        inc     v1idx+1,x
mfvi:   ldx     tmpv
mfvnx:  inx
        cpx     #3
        bne     mfv
        rts

; --------------------------------------------------------------------------
; muswrite -- put this frame's decision in the chip.
; --------------------------------------------------------------------------
muswrite:
        lda     #0
        sta     tmpv
mwv:    ldx     tmpv
        lda     vatk,x
        bne     mwatk
        lda     vnote,x
        bne     mwnx            ; sounding, no new attack: leave it alone
        jsr     gateoff
        jmp     mwnx
mwatk:  jsr     gatenote
mwnx:   inc     tmpv
        lda     tmpv
        cmp     #3
        bne     mwv
        jsr     pwmtick
        jmp     filttick

sidwr:                          ; X = register offset 0..24, A = value
        sta     SID,x
        sta     sidshadow,x
        rts

gateoff:
        ldx     tmpv
        lda     wavetab,x
        sta     tmp2
        lda     sidbase,x
        clc
        adc     #4
        tax
        lda     tmp2
        jmp     sidwr

; gatenote -- frequency, then gate LOW and HIGH inside this one call.
; Both writes land between two samples of the register log, so the sampler
; never sees the gate low: every note is articulated audibly and every scored
; duration stays a whole multiple of eight frames, with no 1-frame rests for
; the reference score to list.  The cost of that choice is that two
; consecutive equal pitches merge into one transcribed event -- which is why
; tools/genscore.py models the player frame by frame and run-length encodes,
; rather than emitting one score entry per notated note.
gatenote:
        ldx     tmpv
        lda     vnote,x
        bne     gnon
        jmp     gateoff
gnon:   sec
        sbc     #33
        tay                     ; Y = index into freqlo/freqhi, MIDI 33..88
        lda     sidbase,x
        sta     tmp1
        ldx     tmp1
        lda     freqlo,y
        jsr     sidwr
        ldx     tmp1
        inx
        lda     freqhi,y
        jsr     sidwr
        ldx     tmpv
        lda     wavetab,x
        sta     tmp2
        lda     tmp1
        clc
        adc     #4
        tax
        lda     tmp2
        jsr     sidwr           ; gate low...
        lda     tmp1
        clc
        adc     #4
        tax
        lda     tmp2
        ora     #1
        jmp     sidwr           ; ...and high again, same frame

; --------------------------------------------------------------------------
; pwmtick -- voice 1's pulse width, a 128-frame triangle over $0400..$0C00.
; $0800 is a square wave, so the sweep passes through it and out both sides:
; a chorusing, phasing lead that carries the subject.  The spectrogram is the
; evidence for it; the note transcription cannot describe it at all.
; --------------------------------------------------------------------------
pwmtick:
        lda     pwmdir
        bmi     pwmdn
        lda     pwmval
        clc
        adc     #16
        sta     pwmval
        lda     pwmval+1
        adc     #0
        sta     pwmval+1
        cmp     #$0C
        bcc     pwmwr
        lda     #$FF
        sta     pwmdir
        jmp     pwmwr
pwmdn:  lda     pwmval
        sec
        sbc     #16
        sta     pwmval
        lda     pwmval+1
        sbc     #0
        sta     pwmval+1
        cmp     #$04
        bcs     pwmwr
        lda     #1
        sta     pwmdir
pwmwr:  ldx     #2
        lda     pwmval
        jsr     sidwr
        ldx     #3
        lda     pwmval+1
        and     #$0F            ; the pulse width is 12 bits
        jmp     sidwr

; --------------------------------------------------------------------------
; filttick -- the cutoff sits at $70 until the closing pedal point, then
; sweeps down to $10 and back at one step every two frames.  That warm
; resonant crunch is unique to this chip and the pedal is the moment to spend
; it on; on the spectrogram it is a moving edge.
; --------------------------------------------------------------------------
filttick:
        lda     bar
        cmp     pedal0
        bcc     fthigh
        cmp     pedal1
        beq     ftsweep
        bcc     ftsweep
fthigh: lda     #$70
        sta     cutoff+1
        ldx     #23             ; ordinary routing: voice 3 only
        lda     #$A4
        jsr     sidwr
        jmp     ftwr
ftsweep:
        lda     frame
        and     #1              ; one step every TWO frames.  At one step in
        bne     ftwr            ;   four the sweep took 96 steps x 4 = 384
                                ;   frames to fall from $70 to $10 -- exactly
                                ;   the length of the three-bar pedal, so it
                                ;   bottomed out as the last chord died and
                                ;   never came back up.  Measured: cutoff
                                ;   112, 95, 72, 50, 27, 26 across bars 28-31.
                                ;   Halved, it falls over a bar and a half and
                                ;   returns over the next, which is a sweep
                                ;   the spectrogram can show.
        lda     cutdir
        bmi     ftdn
        lda     cutoff+1
        clc
        adc     #1
        cmp     #$71
        bcc     ftput
        lda     #$70
        ldx     #$FF
        stx     cutdir
        jmp     ftput
ftdn:   lda     cutoff+1
        sec
        sbc     #1
        cmp     #$10
        bcs     ftput
        lda     #$10
        ldx     #1
        stx     cutdir
ftput:  sta     cutoff+1
        ldx     #23             ; THROUGH THE PEDAL, ALL THREE VOICES GO
        lda     #$A7            ;   THROUGH THE FILTER.  Voice 3 alone is a
        jsr     sidwr           ;   triangle, which has almost no high
                                ;   harmonics for a low-pass to take away:
                                ;   measured, the sweep moved `cutoff` from
                                ;   112 to 22 and back and was barely visible
                                ;   on the mix spectrogram.  Opening the
                                ;   routing for the climax is what makes the
                                ;   resonant crunch audible, and it is the one
                                ;   moment the demo spends it on.
ftwr:   ldx     #22             ; $D416, the cutoff's main eight bits
        lda     cutoff+1
        jsr     sidwr
        ldx     #21             ; $D415, bits 0-2 only
        lda     #0
        jmp     sidwr
