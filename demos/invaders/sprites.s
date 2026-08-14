; sprites.s — the three smooth movers (laser base, player shot, mystery UFO)
; plus the base-explosion shape, all VIC-II hardware sprites.
;
; The shapes are authored as ASCII art in tools/sprites.txt and converted with
; `c64 sprite encode`; sprites.inc is the committed artifact.  They are copied
; at startup to $3800, which is inside VIC bank 0 and 64-byte aligned:
; block = address / 64, so $3800 -> 224, $3840 -> 225, $3880 -> 226,
; $38C0 -> 227.

        .segment "CODE"

spriteinit:
        ldx     #62
sicp:   lda     sprite0,x
        sta     SPRDATA + 0*64,x        ; block 224: laser base
        lda     sprite1,x
        sta     SPRDATA + 1*64,x        ; block 225: player shot
        lda     sprite2,x
        sta     SPRDATA + 2*64,x        ; block 226: mystery UFO
        lda     sprite3,x
        sta     SPRDATA + 3*64,x        ; block 227: base explosion
        dex
        bpl     sicp

        lda     #224
        sta     SPRPTR + 0
        lda     #225
        sta     SPRPTR + 1
        lda     #226
        sta     SPRPTR + 2

        lda     #5
        sta     $D027                   ; base: green
        lda     #1
        sta     $D028                   ; shot: white
        lda     #2
        sta     $D029                   ; UFO: red
        lda     #1
        sta     $D025                   ; sprite multicolor 0 (the '.' legend)
        lda     #7
        sta     $D026                   ; sprite multicolor 1 (the '+' legend)
        lda     #%00000111
        sta     $D01C                   ; all three are multicolor sprites
        lda     #0
        sta     $D017                   ; no vertical expand
        sta     $D01D                   ; no horizontal expand
        sta     $D01B                   ; sprites in front of the characters
        sta     $D015                   ; nothing enabled until a state asks
        ; The 25-row display window starts at raster 51, so text row R starts
        ; at 51 + 8*R.  A sprite's first row shows on Y+1, so FLUSH with that
        ; row is Y = 50 + 8*R; the constants below are 51 + 8*R and therefore
        ; sit one raster lower, which is what keeps the UFO clear of the HUD's
        ; bottom pixel row.  Deliberate, and not the general rule —
        ; hardware.md's Sprites section has that, and docs/todo.md has why
        ; this demo differs.
        lda     #BASESPY
        sta     $D001                   ; base Y: text row 22
        lda     #UFOSPY
        sta     $D005                   ; UFO Y: text row 1
        rts

; setspx: A = X position in 2-pixel units, tmp2 = sprite number.
; Sprite X = 24 + 2*units, so one byte covers the whole visible width and
; the 9th bit lands in $D010 without any 16-bit arithmetic elsewhere.
setspx:
        ldy     #0
        sty     tmp1
        asl
        rol     tmp1
        clc
        adc     #24
        bcc     ssp1
        inc     tmp1
ssp1:   ldy     tmp2
        ldx     spxreg,y
        sta     $D000,x
        lda     spmask,y
        eor     #$ff
        and     $D010
        sta     tmp0
        lda     tmp1
        beq     ssp2
        ldy     tmp2
        lda     spmask,y
        ora     tmp0
        sta     tmp0
ssp2:   lda     tmp0
        sta     $D010
        rts

setbasex:
        lda     #0
        sta     tmp2
        lda     basex
        jmp     setspx

setshotx:
        lda     #1
        sta     tmp2
        lda     shotxu
        jmp     setspx

spxreg: .byte   0, 2, 4, 6, 8, 10, 12, 14
spmask: .byte   1, 2, 4, 8, 16, 32, 64, 128

        .segment "RODATA"
        .include "sprites.inc"
