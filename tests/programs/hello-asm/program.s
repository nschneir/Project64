; hello-asm: print a message via the ROM CHROUT routine, return to BASIC.
; Layout: 2-byte load address ($0801), then a BASIC stub "10 SYS 2061",
; then code at $080D (= 2061).

CHROUT = $FFD2

        .segment "LOADADDR"
        .word   $0801

        .segment "EXEHDR"
        .word   nextln          ; pointer to next BASIC line
        .word   10              ; line number 10
        .byte   $9E, "2061", $00 ; SYS 2061
nextln: .word   $0000           ; end of BASIC program

        .segment "CODE"
start:  ldx     #0
loop:   lda     msg,x
        beq     done
        jsr     CHROUT
        inx
        bne     loop
done:   rts

msg:    .byte   "HELLO FROM ASM", $0D, $00
