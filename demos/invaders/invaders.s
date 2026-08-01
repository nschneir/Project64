; invaders.s — Space Invaders (Taito, 1978) recreated for the Commodore 64.
;
; Pure 6502 with a BASIC SYS stub.  Custom multicolor character set for the
; formation, the shields and the bombs; hardware sprites for the laser base,
; its shot and the mystery UFO; the authentic one-invader-per-tick march
; engine, so the speed-up is emergent; three-voice SID with every write
; shadowed in RAM.
;
; Controls: A and D held move the laser base, SPACE fires.  Input is the live
; matrix-code byte at $CB, not GETIN — a held key must move you every frame.
;
;   c64 run demos/invaders/invaders.s
;   c64 package demos/invaders/invaders.s -o demos/invaders/invaders.d64 \
;       --title "INVADERS"
;
; Memory map
;   $0801-$080C  BASIC stub "10 SYS 2061"
;   $080D-....   CODE / RODATA / DATA (must end below $3000)
;   $3000-$37FF  RAM character set: ROM copy with codes 64-85 patched
;   $3800-$38FF  sprite data, blocks 224-227
;   $0400/$D800  screen and colour RAM

; ---- hardware ------------------------------------------------------------
SCREEN  = $0400
COLRAM  = $D800
SPRPTR  = $07F8
SPRDATA = $3800                 ; block = address/64, so 224..227
CHARSET = $3000
JIFFLO  = $A2                   ; jiffy clock low byte, 60 Hz
KEYDOWN = $CB                   ; matrix code of the key held right now
KEY_A   = 10
KEY_D   = 18
KEY_SPC = 60
KEY_NONE = 64

; ---- zero page (see the c64-development skill's zero-page reference) -----
PTR     = $FB                   ; screen cell pointer
CPTR    = $FD                   ; matching colour-RAM pointer
STR     = $22                   ; text pointer for txtat/putblocks

; ---- geometry ------------------------------------------------------------
NINV      = 55                  ; 5 rows of 11
FORMLEFT  = 9                   ; starting left column of the formation
BASELINE  = 20                  ; an invader at this row ends the game
SHROW0    = 17                  ; the two shield rows
SHROW1    = 18
BASEROW   = 21                  ; the top text row the laser base occupies
BOMBFLOOR = 24                  ; a bomb below this is gone
BASEMAX   = 136                 ; basex is in 2-pixel units: X = 24 + 2*basex
UFOMAX    = 148
UFOPERIOD = 1200                ; ticks between saucers (20 seconds)
BOMBRATE  = 35                  ; ticks between drop attempts
EXPTICKS  = 10                  ; how long an invader's explosion shows

; ---- glyph codes (patched over the ROM charset by charsinit) -------------
GLYPHBASE = 64                  ; 64-75: three classes x two frames x two halves
SHGLYPH   = 76                  ; 76-78: shield solid / cracked / crumbling
BOMBGLYPH = 79                  ; 79-83: the three bomb flavours
BOOMGLYPH = 84                  ; 84-85: the invader explosion, two cells

        .macro  SETSTR addr
        lda     #<addr
        sta     STR
        lda     #>addr
        sta     STR+1
        .endmacro

        .segment "LOADADDR"
        .word   $0801

        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"

start:  cld
        jsr     clrscreen
        jsr     charsinit
        jsr     spriteinit
        jsr     sndinit
        lda     #0
        sta     gstate
        lda     #1
        sta     stinit

; ---- mainloop: THE frame anchor ------------------------------------------
; Executed exactly once per game tick in every state, which is what makes
; `c64 until mainloop` and `c64 key hold --at mainloop` deterministic.
; $CB is latched on the very first instruction, before any pacing delay, so a
; poked matrix code is still live when the player code reads it.
mainloop:
        lda     KEYDOWN
        sta     curkey
        lda     gstate
        beq     mltitle
        cmp     #1
        beq     mlplay
        cmp     #2
        beq     mldying
        cmp     #3
        beq     mlwclr
        jsr     stgover
        jmp     mlend
mltitle:
        jsr     sttitle
        jmp     mlend
mlplay: jsr     stplay
        jmp     mlend
mldying:
        jsr     stdying
        jmp     mlend
mlwclr: jsr     stwclear
mlend:  lda     gstate                  ; the attract screen has no HUD
        beq     mlnohud
        jsr     updhud
mlnohud:
        jsr     sndtick
        lda     sprena
        sta     $D015
        jsr     waitframe
        inc     tick
        jmp     mainloop

waitframe:
        lda     JIFFLO
wf1:    cmp     JIFFLO
        beq     wf1
        rts

; ---- state 0: the attract screen ----------------------------------------
sttitle:
        lda     stinit
        beq     sti2
        lda     #0
        sta     stinit
        sta     sprena
        jsr     drawtitle
        lda     #45                     ; ignore keys briefly, so the key that
        sta     sttimer                 ; ended the last game does not restart
        lda     #0
        sta     sttimer+1
sti2:   lda     sttimer
        beq     sti3
        dec     sttimer
        rts
sti3:   lda     curkey
        cmp     #KEY_NONE
        beq     stidone
        jsr     newgame
stidone:
        rts

newgame:
        lda     #0
        ldx     #5
ngs:    sta     score,x
        dex
        bpl     ngs
        lda     #3
        sta     lives
        lda     #1
        sta     wave
        lda     #0
        sta     extradone
        sta     shots
        sta     shotact
        sta     ufoact
        sta     expcnt
        sta     bnexttype
        lda     #BOMBRATE
        sta     bombtimer
        lda     #68
        sta     basex
        jsr     killallbombs
        jsr     clrscreen
        jsr     drawhud
        jsr     shieldinit
        jsr     newwave
        jsr     uforeload
        jsr     setbasex
        lda     #%00000001
        sta     sprena
        lda     #1
        sta     gstate
        lda     #0
        sta     stinit
        rts

; ---- state 1: play -------------------------------------------------------
stplay: jsr     playerstep
        jsr     marchstep
        jsr     shotstep
        jsr     bombstep
        jsr     ufostep
        jsr     expstep
        lda     #%00000001              ; the base is always live while playing
        ldx     shotact
        beq     spn1
        ora     #%00000010
spn1:   ldx     ufoact
        beq     spn2
        ora     #%00000100
spn2:   sta     sprena
        lda     gstate                  ; marchstep may have ended the game
        cmp     #1
        bne     spdone
        lda     nalive
        bne     spdone
        lda     #3                      ; the wave is cleared
        sta     gstate
        lda     #1
        sta     stinit
spdone: rts

; ---- state 2: the base is exploding --------------------------------------
stdying:
        lda     stinit
        beq     sdy2
        lda     #0
        sta     stinit
        sta     shotact
        lda     #227                    ; swap sprite 0 to the explosion shape
        sta     SPRPTR
        lda     #40
        sta     dyingcnt
        jsr     killallbombs
        jsr     sfxboom
        lda     #%00000001
        sta     sprena
sdy2:   jsr     expstep
        dec     dyingcnt
        bne     sdydone
        lda     #224                    ; the laser base shape again
        sta     SPRPTR
        dec     lives
        lda     #1
        sta     lvdirty
        lda     lives
        bne     sdyresp
        lda     #4
        sta     gstate
        lda     #1
        sta     stinit
        rts
sdyresp:
        lda     #68
        sta     basex
        jsr     setbasex
        lda     #1
        sta     gstate
sdydone:
        rts

; basehit: a bomb reached the laser base.
basehit:
        lda     #2
        sta     gstate
        lda     #1
        sta     stinit
        rts

; ---- state 3: wave cleared ----------------------------------------------
stwclear:
        lda     stinit
        beq     swc2
        lda     #0
        sta     stinit
        sta     shotact
        sta     ufoact
        lda     #90
        sta     sttimer
        lda     #0
        sta     sttimer+1
        jsr     killallbombs
        lda     #1
        sta     txtcol
        SETSTR  txwaveup
        lda     #12
        ldy     #15
        jsr     txtat
swc2:   dec     sttimer
        bne     swcdone
        jsr     clrplayfield
        inc     wave
        lda     #1
        sta     wvdirty
        jsr     shieldinit
        jsr     newwave
        lda     #BOMBRATE
        sta     bombtimer
        lda     #1
        sta     gstate
swcdone:
        rts

; ---- state 4: game over --------------------------------------------------
stgover:
        lda     stinit
        beq     sgo2
        lda     #0
        sta     stinit
        sta     shotact
        sta     ufoact
        sta     sprena
        jsr     killallbombs
        jsr     chkhiscore
        lda     #2
        sta     txtcol
        SETSTR  txover
        lda     #12
        ldy     #15
        jsr     txtat
        lda     #<200
        sta     sttimer
        lda     #>200
        sta     sttimer+1
sgo2:   lda     sttimer
        bne     sgo3
        dec     sttimer+1
sgo3:   dec     sttimer
        lda     sttimer
        ora     sttimer+1
        bne     sgodone
        lda     #0
        sta     gstate
        lda     #1
        sta     stinit
sgodone:
        rts

chkhiscore:
        ldx     #0
chl:    lda     score,x
        cmp     hiscore,x
        bcc     chno
        bne     chyes
        inx
        cpx     #6
        bne     chl
        rts                             ; equal: nothing to do
chyes:  ldx     #0
chc:    lda     score,x
        sta     hiscore,x
        inx
        cpx     #6
        bne     chc
        lda     #1
        sta     hidirty
chno:   rts

; clrplayfield: blank rows 1-19, leaving the HUD rows alone.
clrplayfield:
        ldx     #1
cpfr:   ldy     #0
        jsr     cellptr
        ldy     #39
cpfc:   lda     #32
        sta     (PTR),y
        dey
        bpl     cpfc
        inx
        cpx     #20
        bne     cpfr
        rts

        .include "vars.s"
        .include "screen.s"
        .include "chars.s"
        .include "sprites.s"
        .include "formation.s"
        .include "shields.s"
        .include "player.s"
        .include "bombs.s"
        .include "ufo.s"
        .include "sound.s"
