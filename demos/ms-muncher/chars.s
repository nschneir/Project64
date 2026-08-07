; chars.s -- put a copy of the ROM character set in RAM at $3800 and patch
; the 27 game glyphs over codes 96-122.
;
; The character ROM is not in the CPU's address space: it hides behind the
; I/O registers at $D000, so the copy has to bank I/O out with interrupts
; off and put it back.  Copying all 2 KB and patching 27 glyphs leaves the
; other 229 exactly as the ROM drew them, which is what the HUD text uses.
;
; Codes 96-122 are deliberate: 128-154 is the reverse-video alphabet, and a
; glyph parked there turns every reverse-video heading into maze pipework.
; Code 96 also decodes to a blank in `c64 screen`, so maze assertions read
; screen *codes*, never decoded text.

        .segment "CODE"

charsinit:
        sei
        lda     $01
        pha
        and     #$FB                    ; CHAREN = 0: char ROM visible
        sta     $01
        lda     #$00
        sta     SP
        sta     DP
        lda     #$D0
        sta     SP+1
        lda     #>CHARSET
        sta     DP+1
        ldx     #8                      ; 8 pages = 2048 bytes = 256 glyphs
cipage: ldy     #0
cibyte: lda     (SP),y
        sta     (DP),y
        iny
        bne     cibyte
        inc     SP+1
        inc     DP+1
        dex
        bne     cipage
        pla
        sta     $01                     ; I/O back at $D000
        cli

        lda     glyphsrc                ; patch the game glyphs over 96+
        sta     SP
        lda     glyphsrc+1
        sta     SP+1
        lda     #<(CHARSET + 96*8)
        sta     DP
        lda     #>(CHARSET + 96*8)
        sta     DP+1
        .assert (glyphs_end - glyphs) < 256, error, "glyph sheet outgrew the one-page patch loop"
        ldy     #0
cig:    lda     (SP),y
        sta     (DP),y
        iny
        cpy     #(glyphs_end - glyphs)
        bne     cig
        rts

        .segment "RODATA"
; where the glyph sheet ended up after relocart moved the art block
glyphsrc: .word HI(glyphs)
        .segment "CODE"
