; glow.s -- the sprite backlight, one sprite per voice.
;
; $D01B bits 0-2 are set, so each glow sits BEHIND the character data.  That
; bit is what makes it read as backlit rather than pasted on: the priority
; bit is sprite-versus-character-*data*, and sprites always beat the
; background *colour*, so the glow shows through every background pixel of
; the cell and never over the note head's own white pixels.
;
; TRACKING.  The glow follows the head of the note actually sounding, and
; moves with it as it scrolls:
;
;     x = 102 - 2*age          age = frames since this voice last attacked
;     y = 74 + 4*p             p   = the ladder position of that note
;
; x is the head's own pixel position less 8.  At age 0 the head's left edge
; is 24 + 8*NOWCOL + 6 = 110 and it falls 2 px a frame; the ladder's
; 8*(p>>1) + 4*(p&1) == 4*p identity gives y.  Both are published so a test
; can check the registers against them and against what the sequencer says is
; sounding, at one stop.
;
; A note held longer than five sixteenths loses its glow: at age 40 x would
; reach 24, the left edge of the visible range.  That is a documented limit,
; and `sprage` publishes the age that caused it.

        .segment "CODE"

; The glow's Y origin, DERIVED rather than written down.  A head at ladder
; position p has its top raster at 51 + 8*LADTOP + 4*p and is 4 rasters tall;
; the sprite's lit band is rows 7-13, so its centre shows on raster Y + 11.
; Equating the two centres gives Y = 41.5 + 8*LADTOP + 4*p.
;
; This was a hardcoded 74 in the first build, correct for LADTOP = 4.  When
; the band moved down one row to buy raster budget, the constant did not
; follow and every glow sat 8 rasters above its note head -- visible
; immediately in an evidence PNG, and invisible to every assertion that had
; been written at that point.
GLOWY0  = 42 + 8 * LADTOP

sbit:   .byte   1, 2, 4         ; this voice's bit in $D015

glowtick:
        lda     #0
        sta     sprena
        sta     tmpv

gtv:    ldx     tmpv
        lda     vatk,x
        beq     gtage
        lda     #0              ; attacked this frame: the clock restarts
        sta     sprage,x
        jmp     gtpos
gtage:  lda     vnote,x
        beq     gtoff
        lda     scrollon
        beq     gtpos           ; the score is standing still, so the head is
                                ;   too: freezing the age freezes x with it,
                                ;   and the final chord keeps its glow
        lda     sprage,x
        cmp     #255
        beq     gtpos           ; saturate rather than wrap
        inc     sprage,x

gtpos:  ldx     tmpv
        lda     vnote,x
        beq     gtoff
        ldy     vpos,x
        cpy     #$FF
        beq     gtoff
        lda     sprage,x
        cmp     #40
        bcs     gtoff           ; x would leave the visible range at 24
        asl     a
        sta     tmp0
        lda     #102
        sec
        sbc     tmp0
        sta     sprx,x          ; x = 102 - 2*age
        tya
        asl     a
        asl     a
        clc
        adc     #GLOWY0
        sta     spry,x          ; y = GLOWY0 + 4*p
        lda     sprage,x
        lsr     a
        lsr     a
        sta     tmp0
        lda     #NOWCOL
        sec
        sbc     tmp0
        sta     sprcol,x        ; the screen column the head is in now
        lda     sbit,x
        ora     sprena
        sta     sprena
        jmp     gtnx

gtoff:  ldx     tmpv
        lda     #0
        sta     sprx,x
        sta     spry,x
        sta     sprcol,x

gtnx:   inc     tmpv
        lda     tmpv
        cmp     #3
        beq :+
        jmp gtv
:

        ; Registers last, in one go.  These are written before raster 74 --
        ; the topmost glow Y -- which is why glowtick runs ahead of the
        ; column shift in the frame order.
        ldx     #0
        ldy     #0
gtw:    lda     sprx,x
        sta     $D000,y
        lda     spry,x
        sta     $D001,y
        iny
        iny
        inx
        cpx     #3
        bne     gtw
        lda     sprena
        sta     $D015
        rts
