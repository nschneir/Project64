; formation.s — the 5x11 formation and the one-invader-per-tick march engine.
;
; This is the heart of the demo.  The arcade hardware could only afford to
; touch one alien per frame, and every famous property of the game falls out
; of that: the formation ripples rather than snapping, and it accelerates as
; aliens die because a thinner formation finishes its sweep in fewer ticks.
; There is no speed table anywhere in this file.

        .segment "CODE"

; newwave: build the formation for the current `wave` and draw it.
; Wave 1 starts at row 3; each wave after that starts one row lower, and
; wave 10 resets to the wave-1 height (topr = 3 + ((wave-1) mod 9)).
newwave:
        lda     wave
        sec
        sbc     #1
nwmod:  cmp     #9
        bcc     nwok
        sbc     #9
        jmp     nwmod
nwok:   clc
        adc     #3
        sta     tmp0
        ldx     #0
nwl:    lda     #1
        sta     alive,x
        lda     irowidx,x
        asl                             ; two text rows between invader rows
        clc
        adc     tmp0
        sta     irow,x
        lda     icolbase,x
        sta     icol,x
        inx
        cpx     #NINV
        bne     nwl
        lda     #NINV
        sta     nalive
        lda     #0
        sta     sweep
        sta     edgehit
        sta     dropnext
        sta     frame
        sta     expcnt
        lda     #1
        sta     mdir
        ldx     #0
nwd:    jsr     drawinv
        inx
        cpx     #NINV
        bne     nwd
        rts

; marchstep: move EXACTLY ONE live invader, then advance the sweep index.
; Dead entries are skipped within the same tick, which is what makes the last
; survivor move every single frame while a full formation takes 55 ticks to
; complete one sideways step.
marchstep:
        lda     #NINV
        sta     skipcnt
msloop: ldx     sweep
        lda     alive,x
        bne     msmove
        jsr     msadv
        dec     skipcnt
        bne     msloop
        rts                             ; nothing alive at all

msmove: jsr     erainv
        lda     dropnext
        beq     msside
        inc     irow,x                  ; the drop pass: down one row
        jmp     msdraw
msside: lda     icol,x
        clc
        adc     mdir                    ; mdir is $01 or $FF
        sta     icol,x
msdraw: jsr     drawinv

        ; marching over a shield destroys it, exactly as in the arcade
        lda     irow,x
        cmp     #SHROW0
        beq     mssh
        cmp     #SHROW1
        bne     msedgechk
mssh:   jsr     wipeshieldcells

msedgechk:
        lda     dropnext
        bne     msbase                  ; no edge test on a drop pass
        lda     icol,x
        beq     msedge
        cmp     #38
        bne     msbase
msedge: lda     #1
        sta     edgehit

msbase: lda     irow,x
        cmp     #BASELINE
        bcc     msdone
        lda     #4                      ; an invader reached the baseline
        sta     gstate
        lda     #1
        sta     stinit
msdone: jsr     msadv
        rts

; msadv: step the sweep index; at the wrap, commit the formation-wide
; decisions (animation frame, drop, reverse) and play one heartbeat note.
msadv:  inc     sweep
        lda     sweep
        cmp     #NINV
        bcc     msaend
        lda     #0
        sta     sweep
        lda     frame
        eor     #1
        sta     frame
        lda     dropnext
        beq     msaedge
        lda     #0
        sta     dropnext
        sta     edgehit
        lda     mdir
        eor     #$fe                    ; $01 <-> $FF
        sta     mdir
        jmp     msabeat
msaedge:
        lda     edgehit
        beq     msabeat
        lda     #1
        sta     dropnext
msabeat:
        jsr     sndbeat
msaend: rts

; invptr: X = invader index -> PTR/CPTR at its left cell. X survives.
invptr: stx     ivx
        lda     icol,x
        sta     tmp1
        lda     irow,x
        tax
        ldy     tmp1
        jsr     cellptr
        ldx     ivx
        rts

; drawinv: X = invader index. Two cells, current animation frame, class colour.
drawinv:
        jsr     invptr
        lda     irowidx,x
        tay
        lda     classtab,y
        tax                             ; X = class 0/1/2
        lda     invcolor,x
        ldy     #0
        sta     (CPTR),y
        iny
        sta     (CPTR),y
        txa
        asl
        asl                             ; class * 4 glyph codes
        sta     tmp0
        lda     frame
        asl                             ; + frame * 2
        clc
        adc     tmp0
        adc     #GLYPHBASE
        ldy     #0
        sta     (PTR),y
        tax
        inx
        txa
        iny
        sta     (PTR),y
        ldx     ivx
        rts

; erainv: X = invader index. Blanks its two cells.
erainv: jsr     invptr
        lda     #32
        ldy     #0
        sta     (PTR),y
        iny
        sta     (PTR),y
        rts

; wipeshieldcells: X = invader index; blank the shield damage state under it
; so the bunker really is gone rather than redrawable.
wipeshieldcells:
        stx     ivx
        lda     irow,x
        sta     tmp0
        lda     icol,x
        tay
        lda     tmp0
        jsr     shzero
        ldx     ivx
        lda     icol,x
        clc
        adc     #1
        tay
        lda     irow,x
        jsr     shzero
        ldx     ivx
        rts

; ---- geometry tables -----------------------------------------------------
; invader i = rowidx*11 + colidx, rowidx 0 at the top.
irowidx: .repeat NINV, I
        .byte   I / 11
        .endrepeat
icolbase: .repeat NINV, I
        .byte   FORMLEFT + 2 * (I .MOD 11)
        .endrepeat
rowbase: .byte  0, 11, 22, 33, 44

; rowidx -> class (0 squid / 1 crab / 2 octopus)
classtab: .byte 0, 1, 1, 2, 2
; class -> colour-RAM nybble: bit 3 turns the cell multicolor, low 3 bits are
; the "11" pixel colour (cyan / green / red).
invcolor: .byte 8|3, 8|5, 8|2
; class -> points/10 (30, 20, 10)
invpts:  .byte  3, 2, 1
