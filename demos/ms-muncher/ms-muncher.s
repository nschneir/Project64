; ms-muncher.s -- Ms. Muncher, an arcade maze chase recreated for the C64.
;
; Pure 6502 with a BASIC SYS stub.  Custom multicolor character set for the
; four mazes and the HUD; six hardware sprites for Ms. Muncher, the ghosts
; Bruiser, Pixie, Ivy and Sable, and the travelling fruit; the arcade's
; per-personality ghost targeting, scatter/chase phases with randomised
; openings, continuous speed classes on 8.8 accumulators, three animated
; intermission acts, and three-voice SID with every write shadowed in RAM.
;
; Controls: W/A/S/D steer, SPACE starts and skips an act.  Steering reads
; the live matrix code at $CB, not GETIN -- a held key must turn you at the
; next corner, and a buffered key would stall the turn.
;
;   c64 run demos/ms-muncher/ms-muncher.s
;   c64 package demos/ms-muncher/ms-muncher.s \
;       -o demos/ms-muncher/ms-muncher.d64 --title "MS MUNCHER"
;
; Memory map
;   $0801-$080C  BASIC stub "10 SYS 2061"
;   $080D-$2FFF  CODE / RODATA / DATA / BSS  (ceiling enforced at link time)
;   $3000-$37FF  sprite shapes, blocks 192-218 (built at startup)
;   $3800-$3FFF  character set: ROM copy with codes 96-122 patched
;   $C000-$C2FF  the 616-byte live tile map and the squares table -- put
;                outside the VIC's bank so they cost no low RAM at all
;   $0400/$D800  screen and colour RAM

; ---- hardware ------------------------------------------------------------
SCREEN  = $0400
COLRAM  = $D800
SPRPTR  = $07F8
SPRRAM  = $3000                 ; shape n at SPRRAM + n*64; block = 192 + n
CHARSET = $3800
JIFFLO  = $A2                   ; jiffy clock low byte, 60 Hz
KEYDOWN = $CB                   ; matrix code of the key held right now

KEY_W   = 9
KEY_A   = 10
KEY_S   = 13
KEY_D   = 18
KEY_SPC = 60
KEY_1   = 56
KEY_2   = 59
KEY_3   = 8
KEY_NONE = 64

; ---- zero page -----------------------------------------------------------
; $FB-$FE are the documented free pair; $22-$27 belong to BASIC's INDEX
; scratch, which is dead the moment this program takes the machine over --
; nothing here ever returns to the interpreter or calls a ROM routine.
PTR     = $FB                   ; screen cell pointer
CPTR    = $FD                   ; matching colour-RAM pointer
TP      = $22                   ; tile-map pointer
SP      = $24                   ; sprite/blit source pointer
DP      = $26                   ; sprite/blit destination pointer

; ---- playfield geometry --------------------------------------------------
MCOL0   = 6                     ; screen column of playfield column 0
MROW0   = 2                     ; screen row of playfield row 0
MW      = 28                    ; playfield width in tiles
MH      = 22                    ; playfield height in tiles
TILES   = $C000                 ; MW*MH live tile bytes
SQLO    = $C270                 ; squares 0..31, low bytes
SQHI    = $C290                 ; ... high bytes

; The charset sheet, the sprite art and the four mazes are read by the CPU
; and never by the VIC-II, so they do not have to live in bank 0 at all.
; They are linked as the LAST thing in the .prg -- which puts them straight
; on top of where the sprite shapes are about to be built -- and copied up
; here before anything else runs.  That is what buys the program its whole
; $0801-$3000 window instead of sharing it with 2.5 KB of art.
HIGHRAM = $C400
        .define HI(sym) HIGHRAM + (sym) - highstart

; sprite X = 61 + axhi, sprite Y = 57 + ayhi (art centred at row 10, col 11
; of the 24x21 box; playfield pixel 0,0 sits at raster 67, sprite X 72)
SPRXOFF = 61
SPRYOFF = 57

; ---- tile codes (must match tools/genmaze.py) ----------------------------
T_EMPTY  = 0
T_DOT    = 1
T_ENER   = 2
T_WALL   = 3
T_DOOR   = 4
T_HOUSE  = 5
T_NOUP   = 6
T_TUNNEL = 7
T_NOUPE   = 8                   ; a no-up-turn tile whose dot is gone

; ---- glyph codes ---------------------------------------------------------
WALLBASE = 96                   ; 96-111: the sixteen wall connectivity shapes
GL_DOT   = 112
GL_ENER  = 113
GL_DOOR  = 114
GL_LIFE  = 115
GL_FRUIT = 116                  ; 116-122: the seven fruit pips

; ---- directions ----------------------------------------------------------
DIR_UP    = 0
DIR_LEFT  = 1
DIR_DOWN  = 2
DIR_RIGHT = 3
DIR_NONE  = 4

; ---- actors --------------------------------------------------------------
A_PLAYER = 0
A_G0     = 1                    ; Bruiser, the direct pursuer
A_G1     = 2                    ; Pixie, the ambusher
A_G2     = 3                    ; Ivy, the doubled vector
A_G3     = 4                    ; Sable, the shy one
A_FRUIT  = 5
NACT     = 6

; ---- sprite shape numbers (index into SPRRAM) ----------------------------
SH_CLOSED = 0                   ; +1+2*dir half open, +2+2*dir wide open
SH_BODY   = 9                   ; +frame*4+dir
SH_FRIGHT = 17                  ; +frame
SH_EYES   = 19                  ; +dir
SH_FRUIT  = 23
SH_ACT    = 24                  ; 24 heart, 25 stork, 26 bundle
SPRBLK    = SPRRAM / 64         ; 192

; ---- ghost states --------------------------------------------------------
GS_HOUSE  = 0                   ; bobbing inside, waiting for release
GS_LEAVE  = 1                   ; walking out through the door
GS_SCATTER = 2
GS_CHASE  = 3
GS_FRIGHT = 4
GS_EYES   = 5                   ; eaten: eyes travelling home
GS_ENTER  = 6                   ; eyes dropping back into the house

; ---- game states ---------------------------------------------------------
ST_TITLE  = 0
ST_READY  = 1
ST_PLAY   = 2
ST_DYING  = 3
ST_CLEAR  = 4
ST_OVER   = 5
ST_ACT    = 6
ST_ENTRY  = 7

        .macro  SETSTR addr
        lda     #<addr
        sta     SP
        lda     #>addr
        sta     SP+1
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
        sei
        lda     #0
        sta     $D01A                   ; no VIC interrupts of our own
        cli
        jsr     relocart
        jsr     clrvars
        lda     #$E1                    ; the LFSR must not start at zero
        sta     rndstate
        lda     #$AC
        sta     rndstate+1
        jsr     charsinit
        jsr     spriteinit
        jsr     sqinit
        jsr     sndinit
        jsr     hiscoreinit
        lda     #$1E                    ; screen $0400, charset $3800
        sta     $D018
        lda     $D016
        ora     #$10                    ; multicolor text mode
        sta     $D016
        lda     #0
        sta     $D020
        sta     $D021
        lda     #10                     ; $D023: the house door's pink
        sta     $D023
        lda     #1                      ; $D025: sprite white (eyes, bow)
        sta     $D025
        lda     #6                      ; $D026: sprite blue (pupils)
        sta     $D026
        lda     #%00111111              ; six sprites, all multicolor
        sta     $D01C
        lda     #ST_TITLE
        sta     gstate
        lda     #1
        sta     stinit

; ---- tick: THE frame anchor ---------------------------------------------
; Runs exactly once per frame in every state, which is what makes
; `c64 until tick` and `c64 key hold --at tick` deterministic.  $CB is
; latched on the first instruction, before any pacing, so a poked matrix
; code is still live when the state code reads it.
tick:
        lda     KEYDOWN
        sta     curkey
        jsr     rnd                     ; turn the generator every frame, so
        lda     curkey                  ; the frame a key arrives on is real
        cmp     #KEY_NONE               ; entropy; then stir that key in.  The
        beq     :+                      ; LFSR owns rndstate -- a blind stir
        eor     rndstate+1              ; every frame would overwrite the
        sta     rndstate+1              ; state rnd had just produced, and
:                                       ; rnd would return a constant
        lda     gstate
        asl     a
        tax
        lda     statetab+1,x
        pha
        lda     statetab,x
        pha
        rts                             ; jump to the state handler
tickend:
        jsr     sndtick
        lda     sprena
        sta     $D015
        jsr     waitframe
        inc     frames
        bne     :+
        inc     frames+1
:       jmp     tick

; relocart: lift the art block out of the VIC's bank, in whole pages.  It
; must run before charsinit or spriteinit, which write over where it loaded.
relocart:
        lda     #<highstart
        sta     SP
        lda     #>highstart
        sta     SP+1
        lda     #<HIGHRAM
        sta     DP
        lda     #>HIGHRAM
        sta     DP+1
        ldx     #>(highend-highstart)
        inx                             ; one page more than needed is fine:
ra1:    ldy     #0                      ; nothing lives past HIGHRAM + size
ra2:    lda     (SP),y
        sta     (DP),y
        iny
        bne     ra2
        inc     SP+1
        inc     DP+1
        dex
        bne     ra1
        rts

waitframe:
        lda     JIFFLO
wf1:    cmp     JIFFLO
        beq     wf1
        rts

; state dispatch table -- each entry is (address-1) for the RTS trick
statetab:
        .word   sttitle-1
        .word   stready-1
        .word   stplay-1
        .word   stdying-1
        .word   stclear-1
        .word   stover-1
        .word   stact-1
        .word   stentry-1

; ---- state: play ---------------------------------------------------------
stplay: lda     stinit
        beq     spgo
        lda     #0
        sta     stinit
spgo:   jsr     playerinput
        jsr     phasetick
        jsr     frighttick
        jsr     housetick
        jsr     fruittick
        jsr     movetick
        jsr     collide
        lda     #%00011111              ; the fruit's sprite only while it is
        ldx     fractive                ; actually in the maze
        beq     :+
        ora     #%00100000
:       sta     sprena
        jsr     sprupdate
        jsr     hudtick
        lda     dotsleft
        bne     spdone
        lda     #ST_CLEAR               ; last dot: the board is cleared
        sta     gstate
        lda     #1
        sta     stinit
spdone: jmp     tickend

; ---- state: get ready ----------------------------------------------------
stready:
        lda     stinit
        beq     sr2
        lda     #0
        sta     stinit
        jsr     resetactors
        jsr     sprupdate
        lda     #%00111111
        sta     sprena
        SETSTR  txready
        lda     #MCOL0+11
        ldy     #MROW0+13
        ldx     #7
        jsr     txtat
        lda     #120
        sta     sttimer
        jsr     sfxstart                ; the "get ready" fanfare
sr2:    jsr     sprupdate
        jsr     hudtick
        dec     sttimer
        bne     srdone
        SETSTR  txblank
        lda     #MCOL0+11
        ldy     #MROW0+13
        ldx     #7
        jsr     txtat
        lda     #ST_PLAY
        sta     gstate
        lda     #1
        sta     stinit
        jsr     musstop
srdone: jmp     tickend

; ---- state: Ms. Muncher is caught ---------------------------------------
stdying:
        lda     stinit
        beq     sd2
        lda     #0
        sta     stinit
        lda     #%00000001              ; only she is left on screen
        sta     sprena
        lda     #90
        sta     sttimer
        jsr     sfxdeath
sd2:    lda     sttimer                 ; the death spiral: cycle her mouth
        lsr     a                       ; through every direction as she goes
        lsr     a
        and     #3
        tax
        lda     dyingshape,x
        sta     SPRPTR
        jsr     hudtick
        dec     sttimer
        bne     sddone
        dec     lives
        lda     #1
        sta     huddirty
        lda     lives
        bne     sdagain
        lda     #ST_OVER
        sta     gstate
        lda     #1
        sta     stinit
        jmp     tickend
sdagain:
        lda     #ST_READY
        sta     gstate
        lda     #1
        sta     stinit
sddone: jmp     tickend

dyingshape:
        .byte   SPRBLK+SH_CLOSED+2, SPRBLK+SH_CLOSED+4
        .byte   SPRBLK+SH_CLOSED+6, SPRBLK+SH_CLOSED+8

; ---- state: board cleared ------------------------------------------------
stclear:
        lda     stinit
        beq     sc2
        lda     #0
        sta     stinit
        lda     #%00000001
        sta     sprena
        lda     #100
        sta     sttimer
sc2:    lda     sttimer                 ; flash the maze by swapping the
        and     #8                      ; wall highlight between two colours
        beq     scb
        lda     #1
        bne     scc
scb:    lda     wallhi
scc:    sta     $D022
        jsr     hudtick
        dec     sttimer
        bne     scdone
        lda     wallhi
        sta     $D022
        inc     board
        jsr     actcheck                ; boards 2, 5, 9, then every fourth
        lda     actnext
        beq     scnext
        lda     #ST_ACT
        sta     gstate
        lda     #1
        sta     stinit
        jmp     tickend
scnext: jsr     newboard
        lda     #ST_READY
        sta     gstate
        lda     #1
        sta     stinit
scdone: jmp     tickend

; ---- state: game over ----------------------------------------------------
stover: lda     stinit
        beq     so2
        lda     #0
        sta     stinit
        sta     sprena
        SETSTR  txover
        lda     #MCOL0+9
        ldy     #MROW0+13
        ldx     #9
        jsr     txtat
        lda     #<180
        sta     sttimer
so2:    dec     sttimer
        bne     sodone
        jsr     hientry                 ; does the score make the table?
        lda     entryslot
        bpl     soentry
        lda     #ST_TITLE
        sta     gstate
        lda     #1
        sta     stinit
        jmp     tickend
soentry:
        lda     #ST_ENTRY
        sta     gstate
        lda     #1
        sta     stinit
sodone: jmp     tickend

        .include "vars.s"
        .include "screen.s"
        .include "chars.s"
        .include "sprites.s"
        .include "maze.s"
        .include "actor.s"
        .include "player.s"
        .include "ghosts.s"
        .include "fruit.s"
        .include "hud.s"
        .include "attract.s"
        .include "acts.s"
        .include "hiscore.s"
        .include "sound.s"

; ---- the relocatable art block: always last in the file ------------------
        .segment "RODATA"
highstart:
        .include "chars.inc"
        .include "sprites.inc"
        .include "mazes.inc"
highend:

        .assert highstart <= $3000, error, "the program grew into the sprite blocks at $3000"
        .assert (HIGHRAM + highend - highstart + 256) <= $D000, error, "the art block overruns I/O at $D000"
