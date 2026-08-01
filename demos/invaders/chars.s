; chars.s — install the custom multicolor character set.
;
; The character ROM is not in the CPU's address space by default: it hides
; behind the I/O registers at $D000.  Copying it out means banking I/O away
; ($01 bit 2 = 0) with interrupts off, then putting it back.  Copy all 2 KB,
; then patch only screen codes 64-85 with the game's glyphs — every other
; character (letters, digits, the reverse-space block the title uses) stays
; exactly as the ROM drew it, which is what keeps the HUD readable.

        .segment "CODE"

; charsinit: charset to $3000, VIC pointed at it, multicolor text mode on.
charsinit:
        sei                     ; the char ROM replaces I/O, so no IRQ may run
        lda     $01
        pha
        and     #$fb            ; CHAREN = 0 -> character ROM visible
        sta     $01
        lda     #$00
        sta     PTR
        sta     CPTR
        lda     #$d0
        sta     PTR+1           ; source: $D000
        lda     #>CHARSET
        sta     CPTR+1          ; destination: $3000
        ldx     #8              ; 8 pages = 2048 bytes = 256 glyphs
cipage: ldy     #0
cibyte: lda     (PTR),y
        sta     (CPTR),y
        iny
        bne     cibyte
        inc     PTR+1
        inc     CPTR+1
        dex
        bne     cipage
        pla
        sta     $01             ; I/O back at $D000
        cli

        ; patch the 22 custom glyphs over screen codes 64-85
        ldx     #0
cipatch:
        lda     glyphs,x
        sta     CHARSET + 64*8,x
        inx
        cpx     #(glyphs_end - glyphs)
        bne     cipatch

        ; $D018: screen $0400 (high nybble 1) + charset $3000 ($3000/$0800 = 6,
        ; shifted left one = $0C) = $1C.  Bit 0 is unused and reads back as 1,
        ; so a read of $D018 returns $1D, not $1C.
        lda     #$1c
        sta     $D018
        lda     $D016
        ora     #$10            ; multicolor text mode
        sta     $D016
        lda     #0
        sta     $D020           ; border black
        sta     $D021           ; background black (multicolor pair 00)
        lda     #1
        sta     $D022           ; pair 01: white — invader eyes
        lda     #8
        sta     $D023           ; pair 10: orange — scorch marks
        rts

        .segment "RODATA"
        .include "chars.inc"
