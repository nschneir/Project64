; player.s — the laser base, its single shot, and everything the shot hits.
;
; Input is the matrix code of the key held *right now*, scanned off the CIA
; by `keyscan`.  mainloop latches it into `curkey` as its very first
; instruction, before any pacing, so a held key -- or one `c64 key hold`
; poked into $CB, which `keyscan` falls back to -- is still there when this
; code reads it.
; GETIN would give buffered keys instead, which stall movement while firing.

        .segment "CODE"

playerstep:
        lda     curkey
        cmp     #KEY_A
        bne     plrnl
        lda     basex
        beq     plrnl                    ; already at the left wall
        dec     basex
plrnl:   lda     curkey
        cmp     #KEY_D
        bne     plrnr
        lda     basex
        cmp     #BASEMAX
        bcs     plrnr                    ; already at the right wall
        inc     basex
plrnr:   jsr     setbasex
        lda     curkey
        cmp     #KEY_SPC
        bne     plrdone
        lda     shotact
        bne     plrdone                  ; only one shot on screen at a time
        jsr     fireshot
plrdone: rts

fireshot:
        lda     #1
        sta     shotact
        lda     basex
        clc
        adc     #1
        sta     shotxu
        ; The shot flies straight up, so its character column is fixed at
        ; fire time: pixel X of the bolt is 24 + 2*basex + 12, and column is
        ; (pixelX - 24) / 8 = (basex + 6) / 4.
        lda     basex
        clc
        adc     #6
        lsr
        lsr
        sta     shotcol
        lda     #BASESPY-8              ; the bolt leaves just above the base
        sta     shoty
        inc     shots
        jsr     setshotx
        jmp     sfxshot

killshot:
        lda     #0
        sta     shotact
        rts

; shotstep: move the shot up 6 pixels and resolve what it meets.
; Collision is GRID MATH, not the VIC-II collision latches: the shot's column
; is fixed and its row is exact, so a screen-RAM read tells us what is there
; deterministically.  The latches ($D01E/$D01F) are sprite-vs-sprite and
; sprite-vs-background only, cannot say *which* invader was hit, and clear on
; read — all three make them the wrong tool for a scored hit.
shotstep:
        lda     shotact
        bne     ssgo
        rts
ssgo:   lda     shoty
        sec
        sbc     #6
        sta     shoty
        cmp     #TOPRASTER
        bcs     ssalive
        jmp     killshot                ; off the top of the screen
ssalive:
        sta     $D003                   ; sprite 1 Y
        sec
        sbc     #TOPRASTER
        lsr
        lsr
        lsr
        sta     tmp0                    ; the character row the shot is in
        jsr     chkbombhit              ; a bomb and the shot cancel each other
        bcc     ssnb
        rts
ssnb:   jsr     chkufohit
        bcc     ssnu
        rts
ssnu:   lda     tmp0
        cmp     #25
        bcc     ssread
        rts
ssread: tax
        ldy     shotcol
        jsr     cellptr
        ldy     #0
        lda     (PTR),y
        cmp     #GLYPHBASE
        bcs     sshit
        rts                             ; blank cell or HUD text: keep flying
sshit:  cmp     #SHGLYPH
        bcs     sssh
        jmp     hitinvader              ; codes 64-75
sssh:   cmp     #BOMBGLYPH
        bcc     ssdoshield
        rts                             ; a bomb or explosion glyph: ignore
ssdoshield:
        lda     tmp0
        ldy     shotcol
        jsr     sherode
        jmp     killshot

; hitinvader: tmp0 = row, shotcol = column. Find the owning invader, kill it,
; score it, and start its explosion.
hitinvader:
        ldx     #0
hil:    lda     alive,x
        beq     hinext
        lda     irow,x
        cmp     tmp0
        bne     hinext
        lda     shotcol
        sec
        sbc     icol,x
        bcc     hinext
        cmp     #2                      ; an invader is two cells wide
        bcc     dokill
hinext: inx
        cpx     #NINV
        bne     hil
        jmp     killshot                ; a glyph with no owner: just stop

dokill:
        lda     #0
        sta     alive,x
        dec     nalive
        lda     irow,x
        sta     exprow
        lda     icol,x
        sta     expcol
        lda     #EXPTICKS
        sta     expcnt
        jsr     invptr
        lda     #BOOMGLYPH
        ldy     #0
        sta     (PTR),y
        lda     #BOOMGLYPH+1
        iny
        sta     (PTR),y
        lda     #8|7                    ; multicolor, yellow
        ldy     #0
        sta     (CPTR),y
        iny
        sta     (CPTR),y
        lda     irowidx,x
        tay
        lda     classtab,y
        tay
        lda     invpts,y
        jsr     addscore
        jsr     sfxhit
        jmp     killshot

; expstep: age the invader explosion and blank it when it expires.
expstep:
        lda     expcnt
        bne     esgo
        rts
esgo:   dec     expcnt
        bne     esdone
        ldx     exprow
        ldy     expcol
        jsr     cellptr
        ; blank only cells that still hold the explosion: the formation may
        ; have marched over them while it was showing
        ldy     #0
        lda     (PTR),y
        cmp     #BOOMGLYPH
        bne     esr
        lda     #32
        sta     (PTR),y
esr:    ldy     #1
        lda     (PTR),y
        cmp     #BOOMGLYPH+1
        bne     esdone
        lda     #32
        sta     (PTR),y
esdone: rts

; addscore: A = points/10 (so a 30-point squid passes 3). All arcade scores
; are multiples of ten, so the units digit is always zero.
addscore:
        clc
        adc     score+4
        sta     score+4
        ldx     #5
nsl:    lda     score,x
        cmp     #10
        bcc     nsnext
        sec
        sbc     #10
        sta     score,x
        cpx     #0
        beq     nsnext                  ; saturate at 999990
        dex
        inc     score,x
        inx
        jmp     nsl                     ; re-check this digit, it may still be >=10
nsnext: dex
        bpl     nsl
        lda     #1
        sta     scdirty
        ; the extra life at 1500 points, once per game
        lda     extradone
        bne     asdone
        ldx     #0
cel:    lda     score,x
        cmp     extraval,x
        bcc     asdone                  ; score is below 1500
        bne     ceyes
        inx
        cpx     #6
        bne     cel
ceyes:  lda     #1
        sta     extradone
        inc     lives
        sta     lvdirty
        jsr     sfxextra
asdone: rts

extraval: .byte 0, 0, 1, 5, 0, 0        ; 001500
