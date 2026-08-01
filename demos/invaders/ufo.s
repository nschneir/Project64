; ufo.s — the mystery ship, and the arcade's best-known secret.
;
; The saucer is worth 50-300 points, but the value is not random: the original
; hardware indexed a 15-entry table with a counter of shots the player had
; fired, and the table is arranged so that the 23rd shot always pays 300, and
; then every 15th shot after that.  This file counts shots the same way.

        .segment "CODE"

ufostep:
        lda     ufoact
        bne     ufomove
        lda     ufotimer
        ora     ufotimer+1
        beq     ufospawn
        lda     ufotimer
        bne     utdec
        dec     ufotimer+1
utdec:  dec     ufotimer
        rts

ufospawn:
        lda     nalive
        cmp     #9
        bcs     ufogo
        jmp     uforeload               ; too few invaders left: no saucer
ufogo:  lda     #1
        sta     ufoact
        lda     ufoflip
        eor     #1
        sta     ufoflip
        beq     ufoleft
        lda     #UFOMAX
        sta     ufoxu
        lda     #$ff
        sta     ufodir
        jmp     ufoon
ufoleft:
        lda     #0
        sta     ufoxu
        lda     #1
        sta     ufodir
ufoon:  lda     #58
        sta     $D005                   ; sprite 2 Y: text row 1
        jsr     sfxufo
        jmp     uforeload

ufomove:
        lda     ufoslow
        eor     #1
        sta     ufoslow
        beq     ufodraw                 ; one 2-pixel step every other tick
        lda     ufoxu
        clc
        adc     ufodir
        sta     ufoxu
        cmp     #UFOMAX+2
        bcc     ufodraw                 ; also catches the $FF wrap going left
        jmp     ufooff
ufodraw:
        lda     #2
        sta     tmp2
        lda     ufoxu
        jmp     setspx

ufooff: lda     #0
        sta     ufoact
        jsr     sfxufooff
        jmp     uforeload

uforeload:
        lda     #<UFOPERIOD
        sta     ufotimer
        lda     #>UFOPERIOD
        sta     ufotimer+1
        rts

; chkufohit: tmp0 = the shot's row. Carry set if the shot took the saucer.
chkufohit:
        lda     ufoact
        bne     cugo
        clc
        rts
cugo:   lda     tmp0
        cmp     #3                      ; the saucer occupies rows 1-2
        bcc     cucol
        clc
        rts
cucol:  lda     ufoxu
        lsr
        lsr
        sta     tmp1                    ; its leftmost character column
        lda     shotcol
        sec
        sbc     tmp1
        bcc     cuno
        cmp     #3
        bcs     cuno
        jsr     ufoscore
        jsr     ufooff
        jsr     killshot
        sec
        rts
cuno:   clc
        rts

; ufoscore: the shot-count secret, then the ordinary table.
ufoscore:
        lda     shots
        cmp     #23
        beq     uf300
        bcc     uftab
        sec
        sbc     #23
ufm:    cmp     #15
        bcc     ufm2
        sbc     #15
        jmp     ufm
ufm2:   cmp     #0
        beq     uf300                   ; every 15th shot after the 23rd
uftab:  lda     shots
uftm:   cmp     #15
        bcc     uftd
        sbc     #15
        jmp     uftm
uftd:   tax
        lda     ufotab,x
        jmp     addscore
uf300:  lda     #30                     ; 300 points
        jmp     addscore

; points/10, indexed by (shots mod 15) — the arcade's own table shape
ufotab: .byte   5, 5, 5, 10, 15, 10, 10, 5, 30, 10, 10, 10, 5, 15, 10
