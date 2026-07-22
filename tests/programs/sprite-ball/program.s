; sprite-ball: sprite 0 ball sweeping right, HUD text, mirrored state byte.
; Demonstrates the graphics spec: sprite data as commented .byte rows,
; testable non-graphics signals (ballx), HUD text in screen RAM.
JIFFLO = $A2
SPBLOCK = $0340                 ; block 13 (= $0340/64); tape unused
SCREEN  = $0400
COLOR   = $D800

        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  ldx     #62             ; copy the ball shape into block 13
copy:   lda     ball,x
        sta     SPBLOCK,x
        dex
        bpl     copy
        ldx     #0              ; HUD: "SPRITE BALL" at row 0 (screen codes)
hud:    lda     msg,x
        beq     hudend
        cmp     #$40
        bcc     put             ; digit/space: already a screen code
        sbc     #$40            ; letter: fold (carry set by cmp)
put:    sta     SCREEN,x
        lda     #1
        sta     COLOR,x         ; color RAM: white
        inx
        bne     hud
hudend: lda     #13
        sta     $07F8           ; sprite 0 pointer: block 13
        lda     #7
        sta     $D027           ; sprite 0 color: yellow
        lda     #120
        sta     $D001           ; y
        lda     #30
        sta     ballx
        lda     #1
        sta     $D015           ; enable sprite 0
mainloop:
        lda     ballx
        sta     $D000           ; x position
        ldy     #1              ; pace: 1 jiffy per step
pace:   lda     JIFFLO
pw:     cmp     JIFFLO
        beq     pw
        dey
        bne     pace
        inc     ballx
        lda     ballx
        cmp     #220            ; sweep 30 -> 219, then wrap
        bne     mainloop
        lda     #30
        sta     ballx
        jmp     mainloop

msg:    .byte   "SPRITE BALL", 0

; ball sprite, 24x21 hires (63 bytes: 3 bytes x 21 rows)
ball:   .byte   %00000000, %01111110, %00000000
        .byte   %00000001, %11111111, %10000000
        .byte   %00000111, %11111111, %11100000
        .byte   %00001111, %11111111, %11110000
        .byte   %00011111, %11111111, %11111000
        .byte   %00111111, %11111111, %11111100
        .byte   %00111111, %11111111, %11111100
        .byte   %01111111, %11111111, %11111110
        .byte   %01111111, %11111111, %11111110
        .byte   %01111111, %11111111, %11111110
        .byte   %01111111, %11111111, %11111110
        .byte   %01111111, %11111111, %11111110
        .byte   %01111111, %11111111, %11111110
        .byte   %01111111, %11111111, %11111110
        .byte   %00111111, %11111111, %11111100
        .byte   %00111111, %11111111, %11111100
        .byte   %00011111, %11111111, %11111000
        .byte   %00001111, %11111111, %11110000
        .byte   %00000111, %11111111, %11100000
        .byte   %00000001, %11111111, %10000000
        .byte   %00000000, %01111110, %00000000

        .segment "BSS"
ballx:  .res 1
