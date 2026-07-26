; cart-hello: the smallest useful cartridge — print through the KERNAL and
; stay running. Boots from ROM at power-on, so there is no BASIC stub and no
; load address; the 8K build generates the CBM80 boot header and the reset
; stub that initialises the machine before jumping here.

CHROUT = $FFD2

        .export cart_main
        .segment "CODE"
cart_main:
        ldx     #0
loop:   lda     msg,x
        beq     done
        jsr     CHROUT
        inx
        bne     loop
done:   jmp     done

msg:    .byte   "CART HELLO", $0D, $00
