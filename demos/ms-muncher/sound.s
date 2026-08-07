; sound.s -- three SID voices, shadowed, with a priority rule.
;
; The chip is write-only, so every write goes through sidput and lands in
; sidshad as well.  Those 25 bytes are the only testable evidence that a
; sound happened at all, and routing *every* write through one place is what
; stops the shadow drifting from the chip.
;
; Voices are claimed by priority: death > ghost eaten > fruit > siren >
; munch > music.  A claim carries a frame count, and sndtick releases the
; voice when it runs out -- the failure this guards against is an effect
; that takes a voice and never gives it back, which shows up in a piano roll
; as a track that simply stops.

SIDBASE = $D400
V0      = 0                             ; register offsets of the three voices
V1      = 7
V2      = 14
FCLO    = 21
FCHI    = 22
RESFILT = 23
MODEVOL = 24

PR_MUNCH = 1
PR_SIREN = 2
PR_FRUIT = 3
PR_EATEN = 4
PR_DEATH = 5

FX_NONE  = 0
FX_SIREN = 1
FX_EATEN = 2
FX_FRUIT = 3
FX_DEATH = 4
FX_MUNCH = 5

MUSDIV  = 8                             ; frames per sequencer row

        .segment "CODE"

; sidput: A -> SID register X, and its shadow.
sidput: sta     SIDBASE,x
        sta     sidshad,x
        rts

sndinit:
        lda     #0
        ldx     #0
sinit1:    jsr     sidput
        lda     #0
        inx
        cpx     #25
        bne     sinit1
        lda     #%00011111              ; low-pass, volume 15
        ldx     #MODEVOL
        jsr     sidput
        lda     #$80
        ldx     #FCHI
        jsr     sidput
        lda     #$F0                    ; resonance, nothing routed yet
        ldx     #RESFILT
        jsr     sidput
        rts

; gateoff: release voice X (0-2) and clear its effect slot.
gateoff:
        lda     #0
        sta     vfx,x
        lda     vbase,x
        clc
        adc     #4
        tax
        lda     #0
        jmp     sidput

; claim: voice X, priority A, Y frames, effect tmp+3.  C=1 if we got it.
claim:  cmp     vprio,x
        bcc     clno
        sta     vprio,x
        tya
        sta     vtimer,x
        lda     tmp+3
        sta     vfx,x
        sec
        rts
clno:   clc
        rts

; setvoicehit: drop the gate, then set the note -- a real retrigger, which
; is what a percussive effect needs.  The music deliberately does NOT do
; this: a gate that blinks between two writes inside one frame is sampled as
; a one-frame rest by an audio capture, and that phantom event breaks every
; reference score it lands in.  Under a held gate a pitch change is still a
; new note to the transcriber, so nothing is lost.
setvoicehit:
        stx     svx
        pha
        lda     vbase,x
        clc
        adc     #4
        tax
        lda     sidshad,x
        and     #$FE
        jsr     sidput
        pla
        ldx     svx
        ; fall through

; setvoice: voice X gets frequency tmp/tmp+1, control A, AD tmp+2, SR tmp+6.
setvoice:
        sta     tmp+3
        lda     vbase,x
        sta     tmp+5
        ldx     tmp+5
        lda     tmp
        jsr     sidput
        ldx     tmp+5
        inx
        lda     tmp+1
        jsr     sidput
        ldx     tmp+5
        inx
        inx
        lda     #$00
        jsr     sidput
        ldx     tmp+5
        inx
        inx
        inx
        lda     #$08                    ; pulse width $0800 -- a square
        jsr     sidput
        ldx     tmp+5
        txa
        clc
        adc     #5
        tax
        lda     tmp+2
        jsr     sidput
        ldx     tmp+5
        txa
        clc
        adc     #6
        tax
        lda     tmp+6
        jsr     sidput
        ldx     tmp+5
        lda     tmp+3
svctl:  stx     tmp+4
        pha
        lda     tmp+4
        clc
        adc     #4
        tax
        pla
        jmp     sidput

; setfreq: voice X frequency only, from tmp/tmp+1.
setfreq:
        lda     vbase,x
        tax
        lda     tmp
        jsr     sidput
        inx
        lda     tmp+1
        jmp     sidput

; ---- effects -------------------------------------------------------------
sfxmunch:
        ldx     #2
        lda     #FX_MUNCH
        sta     tmp+3
        lda     #PR_MUNCH
        ldy     #5
        jsr     claim
        bcc     smdone
        lda     munchtog
        eor     #1
        sta     munchtog
        beq     sm2
        lda     #<$0900
        sta     tmp
        lda     #>$0900
        sta     tmp+1
        jmp     sm3
sm2:    lda     #<$0640
        sta     tmp
        lda     #>$0640
        sta     tmp+1
sm3:    lda     #$08                    ; instant attack, quick decay
        sta     tmp+2
        lda     #$00
        sta     tmp+6
        ldx     #2
        lda     #%01000001              ; pulse + gate
        jsr     setvoicehit
smdone: rts

sfxeaten:
        ldx     #0
        lda     #FX_EATEN
        sta     tmp+3
        lda     #PR_EATEN
        ldy     #24
        jsr     claim
        bcc     sedone2
        lda     #<$0800
        sta     tmp
        lda     #>$0800
        sta     tmp+1
        lda     #$09
        sta     tmp+2
        lda     #$F8
        sta     tmp+6
        ldx     #0
        lda     #%00100001              ; sawtooth + gate
        jsr     setvoicehit
sedone2:
        rts

sfxfruit:
        ldx     #0
        lda     #FX_FRUIT
        sta     tmp+3
        lda     #PR_FRUIT
        ldy     #30
        jsr     claim
        bcc     sfdone
        lda     #<$1000
        sta     tmp
        lda     #>$1000
        sta     tmp+1
        lda     #$1A
        sta     tmp+2
        lda     #$A8
        sta     tmp+6
        ldx     #0
        lda     #%01000001
        jsr     setvoicehit
sfdone: rts

sfxextra:
        ldx     #0
        lda     #FX_FRUIT
        sta     tmp+3
        lda     #PR_FRUIT
        ldy     #24
        jsr     claim
        bcc     sxdone
        lda     #<$2000
        sta     tmp
        lda     #>$2000
        sta     tmp+1
        lda     #$08
        sta     tmp+2
        lda     #$C8
        sta     tmp+6
        ldx     #0
        lda     #%00010001              ; triangle: a clean bell
        jsr     setvoicehit
sxdone: rts

sfxstart:
        lda     #4                      ; the short "get ready" fanfare
        jmp     mustart

sfxsiren:
        rts                             ; the siren is maintained by fxtick

sfxdeath:
        jsr     musstop
        ldx     #0
sdv1:    lda     #PR_DEATH
        sta     vprio,x
        lda     #90
        sta     vtimer,x
        lda     #FX_NONE
        sta     vfx,x
        inx
        cpx     #3
        bne     sdv1
        lda     #FX_DEATH
        sta     vfx
        lda     #<$3000
        sta     tmp
        lda     #>$3000
        sta     tmp+1
        lda     #$0A
        sta     tmp+2
        lda     #$FA
        sta     tmp+6
        ldx     #0
        lda     #%00100001
        jsr     setvoicehit
        lda     #<$1800
        sta     tmp
        lda     #>$1800
        sta     tmp+1
        ldx     #1
        lda     #%00010001
        jsr     setvoicehit
        lda     #%00000011              ; run both through the filter
        ldx     #RESFILT
        jsr     sidput
        lda     #$FF
        ldx     #FCHI
        jmp     sidput

; ---- the per-frame effect updates ---------------------------------------
fxtick: lda     gstate                  ; the siren runs all through play
        cmp     #ST_PLAY
        bne     fx0
        ldx     #1
        lda     #FX_SIREN
        sta     tmp+3
        lda     #PR_SIREN
        ldy     #4
        jsr     claim
        bcc     fx0
        jsr     sirentick
fx0:    ldx     #0
fx1:    lda     vfx,x
        cmp     #FX_EATEN
        beq     fxeaten
        cmp     #FX_DEATH
        beq     fxdeath
fxnext: inx
        cpx     #3
        bne     fx1
        rts
fxeaten:
        stx     tmp+7                   ; the ghost-eaten rise
        lda     vbase,x
        tay
        lda     sidshad,y
        sta     tmp
        lda     sidshad+1,y
        clc
        adc     #4
        sta     tmp+1
        ldx     tmp+7
        jsr     setfreq
        ldx     tmp+7
        jmp     fxnext
fxdeath:
        stx     tmp+7                   ; the spiral down
        lda     vbase,x
        tay
        lda     sidshad,y
        sec
        sbc     #$40
        sta     tmp
        lda     sidshad+1,y
        sbc     #0
        sta     tmp+1
        bcs     :+
        lda     #0
        sta     tmp
        sta     tmp+1
:       ldx     tmp+7
        jsr     setfreq
        ldx     tmp+7
        lda     sidshad+FCHI            ; and the filter closing with it
        sec
        sbc     #2
        bcs     :+
        lda     #0
:       stx     tmp+7
        ldx     #FCHI
        jsr     sidput
        ldx     tmp+7
        jmp     fxnext

; sirentick: a slow triangle sweep that speeds up while the ghosts are blue.
sirentick:
        lda     frtimer
        ora     frtimer+1
        beq     sn1
        lda     #6                      ; blue: faster and higher
        .byte   $2C
sn1:    lda     #2
        sta     tmp+4
        lda     sirendir
        bne     sndown
        lda     sirenstep
        clc
        adc     tmp+4
        sta     sirenstep
        cmp     #96
        bcc     snput
        lda     #1
        sta     sirendir
        jmp     snput
sndown: lda     sirenstep
        sec
        sbc     tmp+4
        sta     sirenstep
        cmp     #8
        bcs     snput
        lda     #0
        sta     sirendir
snput:  lda     sirenstep
        clc
        adc     #40
        sta     tmp+1
        lda     #0
        sta     tmp
        lda     frtimer
        ora     frtimer+1
        beq     sn2
        lda     tmp+1
        clc
        adc     #40
        sta     tmp+1
sn2:    lda     #$00
        sta     tmp+2
        lda     #$F0
        sta     tmp+6
        ldx     #1
        lda     sidshad+V1+4            ; already gated?  just retune
        and     #1
        bne     snfreq
        lda     #%00010001              ; triangle + gate
        jmp     setvoice
snfreq: ldx     #1
        jmp     setfreq

; ---- the sequencer -------------------------------------------------------
; mustart: start tune A.  muslead (in rows) is a silent lead-in for THIS
; start only -- a capture needs the music to begin after arming, and a
; lead-in baked into the track data would repeat on every loop.
mustart:
        sta     mustune
        lda     #1
        sta     musplay
        lda     #MUSDIV
        sta     musdiv
        ldx     #0
ms1:    lda     #0
        sta     muspos,x
        lda     muslead
        sta     muswait,x
        inx
        cpx     #3
        bne     ms1
        lda     #0
        sta     muslead
        rts

musstop:
        lda     #0
        sta     musplay
        ldx     #0
mp1:    lda     vprio,x
        bne     mp2
        stx     tmp+7
        jsr     gateoff
        ldx     tmp+7
mp2:    inx
        cpx     #3
        bne     mp1
        rts

mustick:
        lda     musplay
        beq     mtout
        dec     musdiv
        beq     :+
mtout:  rts
:       lda     #MUSDIV
        sta     musdiv
        ldx     #0
mt1:    lda     muswait,x
        beq     mtfetch
        dec     muswait,x
        jmp     mtnext
mtfetch:
        stx     tmp+7
        lda     mustune                 ; track = tune*3 + voice
        asl     a
        clc
        adc     mustune
        clc
        adc     tmp+7
        tay
        lda     tracklo,y
        sta     SP
        lda     trackhi,y
        sta     SP+1
        ldy     muspos,x
        lda     (SP),y
        bne     mtchk
        lda     #0                      ; $00: loop the track
        sta     muspos,x
        tay
        lda     (SP),y
mtchk:  cmp     #1                      ; $01: the tune ends here and stays
        bne     mtplay                  ; ended -- an act's music is a cue,
        ldx     tmp+7                   ; not a loop, so a capture window can
        jsr     gateoff                 ; hold the whole phrase whatever the
        ldx     tmp+7                   ; arming latency was
        lda     #255
        sta     muswait,x
        jmp     mtnext
mtplay: sta     tmp+3                   ; the note
        iny
        lda     (SP),y
        sta     tmp+4                   ; its length in rows
        iny
        tya
        ldx     tmp+7
        sta     muspos,x
        lda     tmp+4
        sec
        sbc     #1
        sta     muswait,x
        lda     vprio,x                 ; an effect owns this voice: stay quiet
        bne     mtnext
        lda     tmp+3
        cmp     #$FF
        beq     mtrest
        jsr     playnote                ; setvoice runs through X: restore it
        ldx     tmp+7
        jmp     mtnext
mtrest: ldx     tmp+7
        jsr     gateoff
        ldx     tmp+7
mtnext: inx
        cpx     #3
        beq     mtdone
        jmp     mt1
mtdone: rts

; playnote: note byte A ((octave<<4)|semitone) on voice tmp+7.
playnote:
        pha
        and     #$0F
        asl     a
        tay
        lda     notetab,y
        sta     tmp
        lda     notetab+1,y
        sta     tmp+1
        pla
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     tmp+5
        lda     #7
        sec
        sbc     tmp+5
        tay
        beq     pn2
pn1:    lsr     tmp+1
        ror     tmp
        dey
        bne     pn1
pn2:    ldx     tmp+7
        lda     insad,x
        sta     tmp+2
        lda     inssr,x
        sta     tmp+6
        lda     inswave,x
        jmp     setvoice

sndtick:
        ldx     #0
sn3:    lda     vtimer,x
        beq     sn4
        dec     vtimer,x
        bne     sn4
        lda     #0
        sta     vprio,x
        stx     tmp+7
        jsr     gateoff
        ldx     tmp+7
sn4:    inx
        cpx     #3
        bne     sn3
        jsr     fxtick
        jmp     mustick

        .segment "RODATA"

vbase:  .byte   V0, V1, V2
; one instrument a voice: a pulse lead, a sawtooth harmony, a triangle bass
inswave: .byte  %01000001, %00100001, %00010001
insad:   .byte  $28, $48, $18
inssr:   .byte  $A8, $88, $C8

; the top octave, C7 to B7; a note an octave down is one shift right, which
; is why only twelve values are stored
notetab:
        .word   34336, 36376, 38536, 40832, 43256, 45832
        .word   48560, 51440, 54504, 57744, 61176, 64816

; note bytes are (octave << 4) | semitone; $FF is a rest, $00 ends the track
A2 = $29
C3 = $30
D3 = $32
E3 = $34
F3 = $35
G3 = $37
A3 = $39
C4 = $40
D4 = $42
E4 = $44
F4 = $45
G4 = $47
A4 = $49
B4 = $4B
C5 = $50
D5 = $52
E5 = $54
F5 = $55
G5 = $57
A5 = $59

; ---- tune 0: the title ---------------------------------------------------
t0v0:   .byte   A4,2, C5,2, E5,4, D5,2, C5,2, B4,4
        .byte   A4,2, C5,2, E5,4, G5,2, E5,2, A5,4
        .byte   G5,2, E5,2, D5,4, C5,2, B4,2, A4,4
        .byte   E5,2, D5,2, C5,4, B4,2, A4,2, A4,4, 0
t0v1:   .byte   C4,4, E4,4, A4,4, E4,4
        .byte   C4,4, E4,4, A4,4, C5,4
        .byte   B4,4, G4,4, D4,4, G4,4
        .byte   A4,4, E4,4, C4,4, A3,4, 0
t0v2:   .byte   A2,8, A2,8, F3,8, F3,8
        .byte   C3,8, C3,8, E3,8, E3,8, 0

; ---- tune 1: act 1, they meet -------------------------------------------
; Each act's music is a 24-row cue that plays once and stops ($01), not a
; loop: a capture window then holds the whole phrase with silence at both
; ends, and the reference score does not depend on how long arming took.
t1v0:   .byte   E4,4, G4,4, C5,6, $FF,2, D5,4, C5,4, 1
t1v1:   .byte   C4,8, F4,8, G4,8, 1
t1v2:   .byte   C3,8, F3,8, G3,8, 1

; ---- tune 2: act 2, the chase -------------------------------------------
t2v0:   .byte   A4,1, C5,1, E5,1, A5,1, E5,1, C5,1, A4,1, C5,1
        .byte   B4,1, D5,1, F5,1, A5,1, F5,1, D5,1, B4,1, D5,1
        .byte   C5,1, E5,1, G5,1, C5,1, G5,1, E5,1, C5,1, E5,1, 1
t2v1:   .byte   A4,4, G4,4, F4,4, E4,4, A4,4, G4,4, 1
t2v2:   .byte   A2,2, A2,2, G3,2, G3,2, F3,2, F3,2
        .byte   E3,2, E3,2, A2,2, A2,2, G3,2, G3,2, 1

; ---- tune 3: act 3, the delivery ----------------------------------------
t3v0:   .byte   C5,4, E5,4, G5,8, F5,4, E5,4, 1
t3v1:   .byte   E4,8, C4,8, F4,8, 1
t3v2:   .byte   C3,8, C3,8, F3,8, 1

; ---- tune 4: the short "get ready" fanfare -------------------------------
t4v0:   .byte   C4,2, E4,2, G4,2, C5,2, G4,2, C5,4, $FF,32, 0
t4v1:   .byte   $FF,48, 0
t4v2:   .byte   C3,4, G3,4, C3,4, $FF,32, 0

tracklo: .byte  <t0v0, <t0v1, <t0v2, <t1v0, <t1v1, <t1v2
         .byte  <t2v0, <t2v1, <t2v2, <t3v0, <t3v1, <t3v2
         .byte  <t4v0, <t4v1, <t4v2
trackhi: .byte  >t0v0, >t0v1, >t0v2, >t1v0, >t1v1, >t1v2
         .byte  >t2v0, >t2v1, >t2v2, >t3v0, >t3v1, >t3v2
         .byte  >t4v0, >t4v1, >t4v2

        .segment "CODE"
