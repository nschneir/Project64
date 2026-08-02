; chars.s — install the custom character set.
;
; The character ROM is not in the CPU's address space by default: it hides
; behind the I/O registers at $D000.  Copying it out means banking I/O away
; ($01 bit 2 = 0) with interrupts off, then putting it back.  Copy all 2 KB,
; then patch only screen codes 112-123 with the game's glyphs — every other
; character stays exactly as the ROM drew it, which is what keeps the HUD
; text readable, the title's solid block (code 160) solid, and every
; reverse-video letter available.

        .segment "CODE"

; charsinit — charset to $3000, VIC pointed at it.
charsinit:
        sei                     ; the char ROM replaces I/O, so no IRQ may run
        lda     $01
        pha
        and     #$fb            ; CHAREN = 0 -> character ROM visible
        sta     $01
        lda     #$00
        sta     PTR
        sta     AUX
        lda     #$d0
        sta     PTR+1           ; source: $D000
        lda     #>CHARSET
        sta     AUX+1           ; destination: $3000
        ldx     #8              ; 8 pages = 2048 bytes = 256 glyphs
cipage: ldy     #0
cibyte: lda     (PTR),y
        sta     (AUX),y
        iny
        bne     cibyte
        inc     PTR+1
        inc     AUX+1
        dex
        bne     cipage
        pla
        sta     $01             ; I/O back at $D000
        cli

        ; patch the 12 custom glyphs over screen codes 112-123
        ldx     #0
cipatch:
        lda     glyphs,x
        sta     CHARSET + GLYPH0*8,x
        inx
        cpx     #(glyphs_end - glyphs)
        bne     cipatch

        ; $D018: bits 7-4 = screen base in 1 KB steps ($0400 -> 1), bits 3-1
        ; = character base in 2 KB steps ($3000/$0800 = 6, shifted left one
        ; -> $0C).  Together $1C.  Bit 0 is unused and READS BACK AS 1, so a
        ; check sees $1D — mask with $FE before comparing.
        lda     #$1c
        sta     $d018
        rts

        ; generated from chars.txt by `c64 charset encode --hires
        ; --first-code 112`; it brings its own glyphs/glyphs_end labels.
        .segment "RODATA"
        .include "chars.inc"
