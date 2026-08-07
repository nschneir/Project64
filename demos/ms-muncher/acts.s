; acts.s -- the three intermission scenes.
;
; Real animation, not title cards: each act moves sprites on a timed
; choreography with its own music, and each ends by itself (or on SPACE).
; They are reachable from the title with the undocumented keys 1, 2 and 3 so
; a reviewer never has to play nine boards to see them.
;
; The acts drive $D000-$D010 directly rather than going through the actor
; engine -- nothing here is on the maze grid, and the sprites run right
; across the screen, past the 255 an X register holds.

ACTLEN  = 400                           ; frames before an act ends by itself
ACTROW  = 51 + 12*8                     ; the raster the pair walk along

        .segment "CODE"

stact:  lda     stinit
        beq     sa2
        lda     #0
        sta     stinit
        sta     actstep
        sta     actfrm
        sta     actfrm+1
        sta     $D010
        jsr     clrscreen
        lda     #1
        sta     txtcol
        ldx     actnum
        lda     acttitlo,x
        sta     SP
        lda     acttithi,x
        sta     SP+1
        lda     #12
        ldy     #22
        ldx     #16
        jsr     txtat
        lda     #16                     ; lead-in, so a capture of the act's
        sta     muslead                 ; music opens before its first note
        lda     actnum
        clc
        adc     #1                      ; tunes 1, 2 and 3 are the act music
        jsr     mustart
        jsr     actsetup
sa2:    inc     actfrm                  ; the acts run past 255 frames, so the
        bne     saf0                    ; counter is 16-bit and the scenes
        inc     actfrm+1                ; read a clamped copy
saf0:   ldx     actfrm+1
        lda     actfrm
        cpx     #0
        beq     saf1
        lda     #255
saf1:   sta     af
        lda     actnum
        beq     saa1
        cmp     #1
        beq     saa2
        jsr     act3
        jmp     sa3
saa1:   jsr     act1
        jmp     sa3
saa2:   jsr     act2
sa3:    lda     curkey                  ; SPACE skips an act
        cmp     #KEY_SPC
        beq     saend
        lda     actfrm+1
        beq     sadone
        lda     actfrm
        cmp     #ACTLEN-256
        bcc     sadone
saend:  jsr     musstop
        lda     #0
        sta     sprena
        sta     $D010
        lda     actret
        sta     gstate
        lda     #1
        sta     stinit
        cmp     #ST_READY               ; back to play?  the next board first
        bne     sadone
        jsr     newboard
sadone: jmp     tickend

; actsetup: shapes, colours and starting places for this act.
actsetup:
        lda     #SPRBLK+SH_CLOSED       ; Ms. Muncher and her counterpart
        sta     SPRPTR
        sta     SPRPTR+1
        lda     #7
        sta     $D027
        lda     #8                      ; he is orange
        sta     $D028
        lda     actnum
        cmp     #2
        beq     as3
        lda     #0                      ; acts 1 and 2 need the heart
        jsr     setactshape
        lda     #SPRBLK+SH_ACT
        sta     SPRPTR+2
        lda     #2
        sta     $D029
        lda     #%00000011
        sta     sprena
        rts
as3:    lda     #1                      ; act 3: the stork and the bundle
        jsr     setactshape
        lda     #2
        jsr     setactshape
        lda     #SPRBLK+SH_ACT+1
        sta     SPRPTR+3
        lda     #SPRBLK+SH_ACT+2
        sta     SPRPTR+4
        lda     #1
        sta     $D02A
        lda     #10
        sta     $D02B
        lda     #SPRBLK+SH_CLOSED
        sta     SPRPTR+2
        lda     #7
        sta     $D029
        lda     #%00011011
        sta     sprena
        rts

; ---- act 1: they meet ----------------------------------------------------
; She sweeps in from the right, he from the left; they pass, turn round,
; walk back until they are face to face, and a heart rises between them.
act1:   lda     #ACTROW
        sta     $D001
        sta     $D003
        lda     af
        cmp     #100
        bcs     a1b
        sta     tmp                     ; --- the pass, three pixels a frame
        lda     #3
        jsr     mul16
        lda     #<340
        sec
        sbc     tmp+4
        sta     tmp+4
        lda     #>340
        sbc     tmp+5
        sta     tmp+5
        ldx     #0
        jsr     sprx
        lda     af
        sta     tmp
        lda     #3
        jsr     mul16
        lda     tmp+4
        clc
        adc     #20
        sta     tmp+4
        bcc     :+
        inc     tmp+5
:       ldx     #1
        jsr     sprx
        jmp     a1shape
a1b:    cmp     #160
        bcs     a1c
        sec                             ; --- turn round and close the gap
        sbc     #100
        sta     tmp
        lda     #2
        jsr     mul16
        lda     tmp+4
        clc
        adc     #43
        sta     tmp+4
        lda     tmp+5
        adc     #0
        sta     tmp+5
        ldx     #0
        jsr     sprx
        lda     #<317
        sec
        sbc     tmp+4
        sta     tmp+6
        lda     #>317
        sbc     tmp+5
        sta     tmp+5
        lda     tmp+6
        sta     tmp+4
        ldx     #1
        jsr     sprx
        jmp     a1shape
a1c:    lda     #161                    ; --- face to face, heart between
        sta     tmp+4
        lda     #0
        sta     tmp+5
        ldx     #0
        jsr     sprx
        lda     #<199
        sta     tmp+4
        lda     #>199
        sta     tmp+5
        ldx     #1
        jsr     sprx
        lda     #180
        sta     tmp+4
        lda     #0
        sta     tmp+5
        ldx     #2
        jsr     sprx
        lda     af                  ; the heart floats up and stops
        sec
        sbc     #160
        lsr     a
        sta     tmp
        lda     #ACTROW
        sec
        sbc     tmp
        cmp     #ACTROW-24
        bcs     :+
        lda     #ACTROW-24
:       sta     $D005
        lda     sprena
        ora     #%00000100
        sta     sprena
        lda     #SPRBLK+SH_CLOSED+7     ; she faces him, he faces her
        sta     SPRPTR
        lda     #SPRBLK+SH_CLOSED+3
        sta     SPRPTR+1
        rts
a1shape:
        lda     frames                  ; mouths working while they run
        lsr     a
        lsr     a
        and     #3
        tay
        lda     mouthtab,y
        beq     a1sc
        clc
        adc     #SPRBLK+SH_CLOSED+2     ; she runs left, he runs right
        sta     SPRPTR
        clc
        adc     #4
        sta     SPRPTR+1
        rts
a1sc:   lda     #SPRBLK+SH_CLOSED
        sta     SPRPTR
        sta     SPRPTR+1
        rts

; ---- act 2: the chase ----------------------------------------------------
; Four legs back and forth, each faster than the last, passing and
; re-passing.
act2:   lda     af
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a                       ; one leg every 64 frames
        and     #3
        sta     tmp+7
        lda     af
        and     #63
        sta     tmp
        ldy     tmp+7
        lda     a2speed,y
        jsr     mul16
        lda     tmp+7
        and     #1
        bne     a2back
        lda     tmp+4                   ; left to right
        clc
        adc     #24
        sta     tmp+4
        lda     tmp+5
        adc     #0
        sta     tmp+5
        ldx     #0
        jsr     sprx
        lda     tmp+4
        sec
        sbc     #24
        sta     tmp+4
        lda     tmp+5
        sbc     #0
        sta     tmp+5
        ldx     #1
        jsr     sprx
        jmp     a2y
a2back: lda     #<320                   ; right to left
        sec
        sbc     tmp+4
        sta     tmp+6
        lda     #>320
        sbc     tmp+5
        sta     tmp+5
        lda     tmp+6
        sta     tmp+4
        ldx     #0
        jsr     sprx
        lda     tmp+4
        clc
        adc     #24
        sta     tmp+4
        lda     tmp+5
        adc     #0
        sta     tmp+5
        ldx     #1
        jsr     sprx
a2y:    lda     tmp+7
        asl     a
        asl     a
        asl     a
        clc
        adc     #ACTROW-12
        sta     $D001
        clc
        adc     #12
        sta     $D003
        jmp     a1shape

; ---- act 3: the delivery -------------------------------------------------
; A stork crosses the top carrying a bundle, drops it, and a junior muncher
; stands up beside the pair.
act3:   lda     #100                    ; the pair wait, facing each other
        sta     tmp+4
        lda     #0
        sta     tmp+5
        ldx     #0
        jsr     sprx
        lda     #<210
        sta     tmp+4
        lda     #>210
        sta     tmp+5
        ldx     #1
        jsr     sprx
        lda     #ACTROW+16
        sta     $D001
        sta     $D003
        lda     #SPRBLK+SH_CLOSED+7
        sta     SPRPTR
        lda     #SPRBLK+SH_CLOSED+3
        sta     SPRPTR+1
        lda     af
        cmp     #80
        bcs     a3drop
        sta     tmp                     ; the stork crosses, two a frame
        lda     #2
        jsr     mul16
        lda     tmp+4
        clc
        adc     #20
        sta     tmp+4
        lda     tmp+5
        adc     #0
        sta     tmp+5
        ldx     #3
        jsr     sprx
        lda     #80
        sta     $D007
        lda     tmp+4                   ; the bundle rides under its beak
        sta     tmp+6
        ldx     #4
        jsr     sprx
        lda     #98
        sta     $D009
        rts
a3drop: sta     tmp                     ; the stork flies on and out
        lda     #2
        jsr     mul16
        lda     tmp+4
        clc
        adc     #20
        sta     tmp+4
        lda     tmp+5
        adc     #0
        sta     tmp+5
        ldx     #3
        jsr     sprx
        lda     #80
        sta     $D007
        lda     #180                    ; the bundle stays where it was let go
        sta     tmp+4
        lda     #0
        sta     tmp+5
        ldx     #4
        jsr     sprx
        lda     af                  ; ... and falls
        sec
        sbc     #80
        clc
        adc     #98
        cmp     #ACTROW+16
        bcc     :+
        lda     #ACTROW+16
:       sta     $D009
        cmp     #ACTROW+16
        bne     a3done
        lda     #180                    ; the junior muncher stands up
        sta     tmp+4
        lda     #0
        sta     tmp+5
        ldx     #2
        jsr     sprx
        lda     #ACTROW+16
        sta     $D005
        lda     #SPRBLK+SH_CLOSED
        sta     SPRPTR+2
        lda     sprena
        ora     #%00000100
        sta     sprena
a3done: rts

; sprx: sprite X gets the 16-bit position in tmp+4/tmp+5, ninth bit and all.
sprx:   txa
        asl     a
        tay
        lda     tmp+4
        sta     $D000,y
        lda     bitmask,x
        eor     #$FF
        and     $D010
        sta     tmp+3
        lda     tmp+5
        beq     :+
        lda     bitmask,x
        ora     tmp+3
        sta     tmp+3
:       lda     tmp+3
        sta     $D010
        rts

; mul16: tmp+4/tmp+5 = A * tmp, for A of 1 to 4.  Four adds beat a shift
; chain here and keep the act code readable.
mul16:  sta     tmp+6
        lda     #0
        sta     tmp+4
        sta     tmp+5
m16l:   lda     tmp+6
        beq     m16d
        dec     tmp+6
        lda     tmp+4
        clc
        adc     tmp
        sta     tmp+4
        bcc     m16l
        inc     tmp+5
        jmp     m16l
m16d:   rts

; actcheck: is an act due after the board just finished?  After boards 2, 5
; and 9, and act 3 again every fourth board after that.
actcheck:
        lda     #0
        sta     actnext
        lda     board                   ; board has already advanced
        cmp     #3
        beq     ac1
        cmp     #6
        beq     ac2
        cmp     #10
        beq     ac3
        cmp     #14
        bcc     acdone
        sec
        sbc     #10
        and     #3
        bne     acdone
        lda     #2
        jmp     acset
ac1:    lda     #0
        jmp     acset
ac2:    lda     #1
        jmp     acset
ac3:    lda     #2
acset:  sta     actnum
        lda     #1
        sta     actnext
        lda     #ST_READY
        sta     actret
acdone: rts

        .segment "RODATA"
acttitlo: .byte <txact1, <txact2, <txact3
acttithi: .byte >txact1, >txact2, >txact3
txact1: .byte   "ACT 1 THEY MEET "
txact2: .byte   "ACT 2 THE CHASE "
txact3: .byte   "ACT 3 A DELIVERY"
a2speed: .byte  1, 2, 3, 4

        .segment "CODE"
