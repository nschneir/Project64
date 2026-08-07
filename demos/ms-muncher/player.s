; player.s -- steering, eating, and being caught.
;
; Input is the live matrix code at $CB, latched once at the top of tick.
; GETIN would hand back a *buffered* key: hold D and the buffer empties
; after one repeat, so she stops dead at the next corner.  Reading the
; held-key byte is also what makes `c64 key hold D --at tick` drive her.

        .segment "CODE"

playerinput:
        lda     demomode
        beq     piread
        jmp     demoai
piread: lda     curkey
        cmp     #KEY_W
        beq     piup
        cmp     #KEY_A
        beq     pileft
        cmp     #KEY_S
        beq     pidown
        cmp     #KEY_D
        beq     piright
        rts
piup:   lda     #DIR_UP
        jmp     piset
pileft: lda     #DIR_LEFT
        jmp     piset
pidown: lda     #DIR_DOWN
        jmp     piset
piright:
        lda     #DIR_RIGHT
; piset: buffer the turn.  A reversal is instant -- the tile behind is by
; definition passable -- and everything else waits for the next centre.
piset:  sta     awant
        eor     adir
        cmp     #2
        bne     pidone
        lda     awant
        sta     adir
pidone: rts

; playercentre: called from atcentre with tcol/trow set.
playercentre:
        jsr     eatcell
        lda     demomode
        beq     :+
        jsr     demopick
:       lda     awant
        cmp     adir
        beq     pcdone
        jsr     cantake
        bcc     pcdone
        lda     awant
        sta     adir
pcdone: rts

; collide: same tile as a ghost?  Eat it if it is blue, die if it is not.
; Tested through tile equality and the program's own state bytes, never
; through $D01E, whose latch clears on read.
collide:
        lda     axhi
        lsr     a
        lsr     a
        lsr     a
        sta     tmp
        lda     ayhi
        lsr     a
        lsr     a
        lsr     a
        sta     tmp+1
        ldx     #0
co1:    lda     astate+1,x
        cmp     #GS_SCATTER
        bcc     conext                  ; still in the house
        cmp     #GS_EYES
        bcs     conext                  ; already eaten
        lda     axhi+1,x
        lsr     a
        lsr     a
        lsr     a
        cmp     tmp
        bne     conext
        lda     ayhi+1,x
        lsr     a
        lsr     a
        lsr     a
        cmp     tmp+1
        bne     conext
        lda     astate+1,x
        cmp     #GS_FRIGHT
        beq     coeat
        jmp     cohit
coeat:  stx     tmp+2                   ; addscore and the sfx run through X
        lda     #GS_EYES
        sta     astate+1,x
        inc     ghcombo
        lda     ghcombo                 ; 200, 400, 800, 1600
        cmp     #5
        bcc     :+
        lda     #4
:       sec
        sbc     #1
        asl     a
        tay
        lda     ghscore,y
        pha
        lda     ghscore+1,y
        tax
        pla
        jsr     addscore
        jsr     sfxeaten
        ldx     tmp+2
conext: inx
        cpx     #4
        bne     co1
        rts
cohit:  lda     demomode                ; the attract demo just goes home
        beq     codie
        lda     #ST_TITLE
        sta     gstate
        lda     #1
        sta     stinit
        rts
codie:  lda     #ST_DYING
        sta     gstate
        lda     #1
        sta     stinit
        rts

        .segment "RODATA"
ghscore: .word  200, 400, 800, 1600
        .segment "CODE"
