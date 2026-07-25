; cart.inc — resident EasyFlash bank-switch runtime (c64-tools).
;
; The constraint this solves: an EasyFlash cartridge's $8000 and $A000 windows
; switch TOGETHER on a write to $DE00, so no ROM bank is ever permanently
; resident and bank 1 cannot JSR into bank 5. The trampoline below lives in
; RAM, which never switches, and every cross-bank call goes through it.
;
; Boot facts, all measured on VICE 3.10:
;   * the cart powers up in Ultimax mode; RESET comes from $FFFC, which is
;     bank 0 HIROM assembled for $E000 — the CBM80 header is never scanned
;   * in Ultimax mode only $0000-$0FFF is RAM
;   * RAMTAS ($FD50) clears $0002-$0101 and $0200-$03FF
;   * CINT ($FF5B) clears the screen at $0400-$07FF
;   -> the resident block goes at $0900, and it must be copied down BEFORE
;      the cart leaves Ultimax mode, because $E000 becomes KERNAL the instant
;      it does.
;
; Why `.org` and not an ld65 `load = ROM, run = RESIDENT` segment: this file is
; included by EVERY bank's source, because every bank needs `ef_call` and the
; address of `bankcall`. Only the boot window's linker config has a RESIDENT
; area, so a `.segment "RAMCODE"` here is a hard `ld65` error — "Missing memory
; area assignment for segment 'RAMCODE'" — in each of the other windows.
; Assembling the block absolute at EF_RESIDENT instead needs no segment that a
; non-boot window lacks, and it makes the addresses identical in every bank by
; construction: bank 5's `jsr bankcall` and bank 0's resolve to the same byte
; of RAM without the two links ever having to agree on anything. The cost is
; one copy of the block (~70 bytes) in each window's ROM; only the boot
; window's copy is ever executed.

.ifndef CART_INC_INCLUDED
CART_INC_INCLUDED = 1

EF_BANK      = $DE00            ; bank register (write-only on real hardware)
EF_CONTROL   = $DE02            ; mode/LED register
EF_MODE_16K  = $87              ; leave Ultimax for 16K cart mode, LED on
EF_JUMPTABLE = $9F00            ; each code bank's entry table
EF_RESIDENT  = $0900            ; where the trampoline runs from
EF_MAX_ENTRY = 84               ; 3 bytes per entry, one page of table: a page
                                ; holds 85 of them, so the last index is 84

; Declare an entry point in this bank's jump table. Order defines the index:
; the first ef_entry is index 0, the second index 1, and so on. Cross-bank
; callers name the index, never an address, so banks relink freely.
.macro ef_entry target
        jmp     target
.endmacro

; Call entry `index` in `bank` and come back to the caller's bank.
.macro ef_call bank, index
        .if index > EF_MAX_ENTRY
        .error "ef_call: entry index above EF_MAX_ENTRY"
        .endif
        lda     #bank
        ldx     #(index * 3)
        jsr     bankcall
.endmacro

.segment "CODE"

; --- the resident block: stored here in ROM, assembled to run at $0900 ------
ef_resident_rom:
        .org    EF_RESIDENT

ef_start:
        lda     #EF_MODE_16K
        sta     EF_CONTROL              ; KERNAL and BASIC exist again
        jsr     $FDA3                   ; IOINIT
        jsr     $FD50                   ; RAMTAS  — its size probe writes and
                                        ; restores $0900, so the block survives
        jsr     $FD15                   ; RESTOR
        jsr     $FF5B                   ; CINT
        cli
        lda     #$00
        sta     ef_cur_bank
        sta     EF_BANK
        jmp     EF_JUMPTABLE            ; bank 0 LOROM, entry 0

; A = target bank, X = entry offset (index * 3). Restores the caller's bank
; on return, and nests safely: the caller's bank rides the stack, and the
; self-modified JSR has already been executed by the time a nested call
; overwrites it.
bankcall:
        sta     ef_target
        stx     @jsr + 1
        lda     ef_cur_bank
        pha
        lda     ef_target
        sta     ef_cur_bank
        sta     EF_BANK
@jsr:   jsr     EF_JUMPTABLE
        pla
        sta     ef_cur_bank
        sta     EF_BANK
        rts

; Switch banks without calling — for streaming data out of a bank. The caller
; is responsible for switching back.
ef_setbank:
        sta     ef_cur_bank
        sta     EF_BANK
        rts

ef_cur_bank:
        .byte   $00
ef_target:
        .byte   $00
ef_resident_end:

        .reloc
; --- end of the resident block ---------------------------------------------

EF_RESIDENT_SIZE = ef_resident_end - EF_RESIDENT
.assert EF_RESIDENT_SIZE < 256, error, "resident block outgrew the copy loop"

; Cold entry. The boot window's reset vectors point here.
ef_boot:
        sei
        cld
        ldx     #$FF
        txs
        ldx     #$00
@copy:  lda     ef_resident_rom,x       ; ROM at $E0xx...
        sta     EF_RESIDENT,x           ; ...to RAM at $0900
        inx
        cpx     #EF_RESIDENT_SIZE
        bne     @copy
        jmp     ef_start                ; runs from RAM from here on

.endif  ; CART_INC_INCLUDED
