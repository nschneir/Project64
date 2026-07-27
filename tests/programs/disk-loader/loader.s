; disk-loader: boot from a disk, then pull a SECOND file off the same disk
; while running and print it. The whole point is the secondary address: SA 1
; means "load at the address in the file's own 2-byte PRG header", and DATA's
; header says $C000 — so nothing in this program names that address except the
; read loop that goes looking for what landed there.
;
; The disk is built by game.disk.yaml; the runner attaches it at power-on and
; autostarts it (LOAD"*",8,1), which starts this file because build_disk
; writes a manifest in listed order.

SETLFS = $FFBA
SETNAM = $FFBD
LOAD   = $FFD5
CHROUT = $FFD2

DATA   = $C000                  ; where DATA's own header sends it

        .segment "LOADADDR"
        .word   $0801

        .segment "EXEHDR"
        .word   nextln          ; pointer to next BASIC line
        .word   10              ; line number 10
        .byte   $9E, "2061", $00 ; SYS 2061
nextln: .word   $0000           ; end of BASIC program

        .segment "CODE"
start:  lda     #1              ; logical file number (any non-zero value)
        ldx     #8              ; device 8 — the first disk drive
        ldy     #1              ; secondary address 1: use the file's header
        jsr     SETLFS
        lda     #namelen
        ldx     #<name
        ldy     #>name
        jsr     SETNAM
        lda     #0              ; 0 = load, 1 = verify
        jsr     LOAD            ; X/Y come back as the end address + 1
        bcs     failed          ; carry set = failed, A = KERNAL error code

        ldx     #0              ; print what landed at $C000
loop:   lda     DATA,x
        beq     done
        jsr     CHROUT
        inx
        bne     loop
done:   rts

; A failure has to say which one: A holds the KERNAL error code (4 = file not
; found, 5 = device not present), and without it a red test says only that
; nothing was printed.
failed: pha
        ldx     #0
ferr:   lda     errmsg,x
        beq     ferrend
        jsr     CHROUT
        inx
        bne     ferr
ferrend:
        pla
        ora     #$30            ; the code is one digit; $30 = PETSCII '0'
        jsr     CHROUT
        lda     #$0D
        jsr     CHROUT
        rts

name:   .byte   "DATA"
namelen = * - name
errmsg: .byte   "LOAD FAILED ", $00
