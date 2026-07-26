; Bank 1 LOROM — reached only through the resident trampoline. Both cart
; windows switch together on a write to $DE00, so bank 0 cannot JSR here
; directly: `ef_call 1, 0` names the bank and the jump-table index instead.
.include "cart.inc"

.segment "JUMPTAB"
        ef_entry shout                  ; entry 0

.segment "CODE"
shout:  lda     #$05
        sta     $D020                   ; visible proof bank 1 executed
        rts
