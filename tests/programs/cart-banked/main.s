; Bank 0 LOROM — where ef_start hands control over: entry 0 of this bank's
; jump table at $9F00 is the cold start for the whole cartridge.
.include "cart.inc"

.segment "JUMPTAB"
        ef_entry cold                   ; entry 0

.segment "CODE"
cold:   ef_call 1, 0                    ; run the routine that lives in bank 1
        ldx     #0
loop:   lda     msg,x
        beq     done
        jsr     $FFD2                   ; CHROUT — the KERNAL is back by now
        inx
        bne     loop
done:   lda     #1
        sta     $0505                   ; state byte: control came back here
spin:   jmp     spin

msg:    .byte   "BANK OK", $0D, $00
