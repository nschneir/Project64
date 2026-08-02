; sound.s — SID effects, every write mirrored in RAM.
;
; The SID is write-only: reading $D404 back tells you nothing about what the
; chip is doing.  So nothing here writes $D400-$D418 directly — every write
; goes through `sidput`, which stores the byte to the chip AND to
; `sidshadow`.  That array is the testable evidence for sound; the tests and
; the evidence protocol read it, never the chip.
;
; Effects are one-shot: the routine gates a voice on and sets `sfxlen`,
; `pace` counts it down one jiffy at a time, and `sfxoff` gates the voice
; back off.  Nothing here spins, so a sound never costs the game a frame.
;
; Every effect opens the same two ways, and both are load-bearing.  It calls
; `sfxoff` first, because there is only ONE countdown: a level-up lands in the
; same tick as the pickup that earned it and takes `sfxreg` over, so the
; pickup's voice would otherwise never be gated down.  Then it clears its OWN
; control register, because the SID starts an attack on a 0->1 gate transition
; only — writing a gate bit that is already set is silence, which is exactly
; what a stolen countdown leaves behind.

        .segment "CODE"

; sidput — A -> $D400+X and sidshadow+X.  X = 0-24.
sidput: sta     SID,x
        sta     sidshadow,x
        rts

; sidzero — silence the whole chip.  SID registers keep their values across a
; program stop, and a left-over gate bit blocks the next note.
sidzero:
        ldx     #24
szloop: lda     #0
        jsr     sidput
        dex
        bpl     szloop
        lda     #15             ; master volume, no filter
        ldx     #24
        jsr     sidput
        lda     #0
        sta     sfxlen
        sta     sfxctl
        lda     #4              ; a voice-1 control register, so the very
        sta     sfxreg          ; first sfxoff writes 0 where 0 already is
        rts

; sfxeat — a short bright triangle blip on voice 1 (registers $D400+0..6).
sfxeat: jsr     sfxoff          ; gate down whatever was still sounding
        lda     #$00            ; and clear this voice's own gate
        ldx     #4
        jsr     sidput
        lda     #$00
        ldx     #0
        jsr     sidput          ; frequency low
        lda     #$40            ; ~1050 Hz: high and short, an arcade pickup
        ldx     #1
        jsr     sidput          ; frequency high
        lda     #$09            ; attack 2 ms, decay 750 ms
        ldx     #5
        jsr     sidput
        lda     #$00            ; sustain 0, release 6 ms
        ldx     #6
        jsr     sidput
        lda     #$11            ; triangle + gate on
        ldx     #4
        jsr     sidput
        lda     #4
        sta     sfxreg          ; voice 1 control register
        lda     #$10            ; ...gated off = triangle, gate clear
        sta     sfxctl
        lda     #6              ; 6 jiffies = 100 ms
        sta     sfxlen
        rts

; sfxlevel — a higher, longer blip on voice 2 ($D400+7..13) so a level-up
; sounds different from a pickup even though both are triangles.
sfxlevel:
        jsr     sfxoff
        lda     #$00
        ldx     #11
        jsr     sidput
        lda     #$00
        ldx     #7
        jsr     sidput
        lda     #$70            ; roughly two octaves above the pickup
        ldx     #8
        jsr     sidput
        lda     #$0a            ; attack 2 ms, decay 1.5 s
        ldx     #12
        jsr     sidput
        lda     #$00
        ldx     #13
        jsr     sidput
        lda     #$11
        ldx     #11
        jsr     sidput
        lda     #11
        sta     sfxreg          ; voice 2 control register
        lda     #$10
        sta     sfxctl
        lda     #14
        sta     sfxlen
        rts

; sfxdie — a noise burst on voice 3 ($D400+14..20) with a long release: the
; crash the snake dies to.
sfxdie: jsr     sfxoff
        lda     #$00
        ldx     #18
        jsr     sidput
        lda     #$30
        ldx     #14
        jsr     sidput          ; frequency low
        lda     #$08            ; low and rough
        ldx     #15
        jsr     sidput
        lda     #$0c            ; attack 2 ms, decay 3 s
        ldx     #19
        jsr     sidput
        lda     #$0a            ; sustain 0, release 1.5 s
        ldx     #20
        jsr     sidput
        lda     #$81            ; noise + gate on
        ldx     #18
        jsr     sidput
        lda     #18
        sta     sfxreg          ; voice 3 control register
        lda     #$80            ; ...gated off = noise, gate clear
        sta     sfxctl
        lda     #45             ; 45 jiffies = 3/4 second
        sta     sfxlen
        rts

; sfxoff — gate the sounding voice down.  Called by pace when sfxlen expires.
sfxoff: ldx     sfxreg
        lda     sfxctl
        jsr     sidput
        rts
