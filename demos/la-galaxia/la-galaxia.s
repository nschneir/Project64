; la-galaxia.s -- La Galaxia, a 1981 arcade fixed-shooter recreated for the
; Commodore 64.  Pure 6502 with a BASIC SYS stub.
;
; Forty enemies on eight sprites: the settled formation is 2x2 character
; blocks in the screen matrix, an enemy that breaks formation becomes a
; hardware sprite carried by a raster-IRQ multiplexer, and the parallax
; starfield is a character layer whose glyph bitmaps rotate.  Missiles and
; enemy bullets are character-space objects, so all eight sprites stay
; available to the fighters, the divers and the tractor beam.
;
; Controls: A/D move, SPACE fires; SPACE starts one player, X two.  On the
; title screen the digit keys pick a starting stage (1-9, and 0 for ten).
; The cold open is the one screen that answers to ANY key -- it is a story
; nobody should have to sit through twice -- so it watches `anykey_edge`
; rather than a mapped bit; the title's start keys are unchanged.
; Input is read from the keyboard matrix, from $CB, and from joystick
; port 2, folded into one `input_state` byte.
;
;   c64 run demos/la-galaxia/la-galaxia.s --area 'ENGINE=$4000:$6000'
;   c64 package demos/la-galaxia/la-galaxia.s \
;       -o demos/la-galaxia/la-galaxia.d64 --title "LA GALAXIA" \
;       --area 'ENGINE=$4000:$6000'
;
; Memory map -- see PLAN.md §0 for why the charset is at $3800 and not at
; the $1800 PROMPT.md §10 asks for (in VIC bank 0 the chip sees character
; ROM at $1000-$1FFF, so RAM there is invisible; proved on the machine).
;
;   $0801-$080C  BASIC stub "10 SYS 2061"
;   $080D-$1FFF  zero padding written by --area's fill
;   $2000-$37FF  sprite shapes, blocks 128-148, copied here at startup
;   $3800-$3FFF  the character set, built at startup
;   $4000-$8FFF  ENGINE: all code, all variables, the SID shadow
;   $0400/$D800  screen and colour RAM

; ---- hardware ------------------------------------------------------------
SCREEN  = $0400
COLRAM  = $D800
SPRPTR  = $07F8
SPRRAM  = $2000                 ; shape n at SPRRAM + n*64; block = 128 + n
SPRBLK  = SPRRAM / 64           ; 128
CHARSET = $3800
KEYDOWN = $CB                   ; the current-key byte -- read, never written

VIC     = $D000
SPR0X   = $D000
SPR0Y   = $D001
SPRXMSB = $D010
SPRCTRL1 = $D011
SPRENA  = $D015
SPRCTRL2 = $D016
VMCSB   = $D018
IRQFLAG = $D019
IRQMASK = $D01A
SPRMC   = $D01C
BORDER  = $D020
BACKGND = $D021
SPRMC0  = $D025
SPRMC1  = $D026
SPRCOL0 = $D027

CIA1ICR = $DC0D
CIA2ICR = $DD0D
CIA1PRA = $DC00
CIA1PRB = $DC01

; ---- colours -------------------------------------------------------------
COL_BLACK  = $00
COL_WHITE  = $01
COL_RED    = $02
COL_CYAN   = $03
COL_PURPLE = $04
COL_GREEN  = $05
COL_BLUE   = $06
COL_YELLOW = $07
COL_ORANGE = $08
COL_LTRED  = $0A
COL_DKGREY = $0B
COL_GREY   = $0C
COL_LTGREEN = $0D
COL_LTBLUE = $0E
COL_LTGREY = $0F

; ---- keyboard matrix codes ----------------------------------------------
KEY_A    = 10
KEY_D    = 18
KEY_SPC  = 60
KEY_X    = 23
KEY_F1   = 4
KEY_F3   = 5
KEY_NONE = 64

; ---- input_state bits ----------------------------------------------------
IN_LEFT  = $01
IN_RIGHT = $02
IN_FIRE  = $04
IN_ST1   = $08
IN_ST2   = $10

; ---- zero page -----------------------------------------------------------
; $FB-$FE are the documented free pair.  $22-$27 are BASIC's INDEX scratch,
; dead the moment this program takes the machine over: nothing here returns
; to the interpreter and no KERNAL routine is ever called.
; The hot scratch lives in zero page.  tmp0-tmp5 alone are read and written
; some hundreds of times per tick -- the multiplexer's assignment loop, the
; block renderer, the path player -- and an absolute access to a variable in
; the ENGINE segment costs a cycle more than a zero-page one every time.
tmp0    = $04
tmp1    = $05
tmp2    = $06
tmp3    = $07
tmp4    = $08
tmp5    = $09
vxlo    = $0A                   ; the path player's velocity, 8.8 signed
vxhi    = $0B
vylo    = $0C
vyhi    = $0D
txtcol  = $0E                   ; colour the next cell write uses
scrrow  = $0F                   ; and where it goes
scrcol  = $10
; Two loop indices that cannot share tmp0-tmp5: formtick's repaint budget
; (drawslot and eraseslot use every tmp between them) and the missile index
; hitgrid/hitdivers are working on (hitenemy reaches drawslot and num2dec).
ftrcount = $11
misix   = $12
evtmp   = $13                   ; the IRQ chain's saved event index
digbuf  = $14                   ; six decimal digits, $14-$1B
evcur   = $1C                   ; muxassign builds the event list as it goes
bandix  = $1D                   ; which of the two band edges comes next
evtline = $1E                   ; the raster line of the event being emitted
; The cold open's EPX smoother (cold.s) holds a source row, both of its
; shifted neighbours and both corner masks at once -- five more bytes than
; tmp0-tmp5 has spare.  $1F-$21 and $02-$03 are the free zero page left: $02
; is unused by BASIC and the KERNAL, $03 is the float-to-int vector, and
; nothing here returns to either.
epxP    = $1F                   ; the source row being expanded
epxC    = $20                   ; ... its left neighbours, one bit over
epxB    = $21                   ; ... and its right neighbours
epxSX   = $02                   ; EPX's two corner masks, one bit per pixel
epxSY   = $03

PTR     = $FB                   ; screen cell pointer
CPTR    = $FD                   ; matching colour-RAM pointer
SRC     = $22                   ; block copy source
DST     = $24                   ; block copy destination
TXT     = $26                   ; string pointer

; ---- playfield geometry --------------------------------------------------
; The arcade monitor is vertical, so the play area is a 24-column window and
; the eight columns each side carry the cabinet bezel and the HUD.
PFCOL   = 8                     ; first playfield column
PFW     = 24                    ; playfield width in cells
PFROWS  = 25
LCOL    = 0                     ; left HUD column
RCOL    = 32                    ; right HUD column

; The fighter's position is kept in *window* pixels, 0 to 176: the window is
; 192 pixels wide and the 16-pixel art has to fit inside it.  The window's
; right edge is sprite X 260, which does not fit a byte, so the conversion
; happens once, in playerdraw, where the 9th bit has to be handled anyway.
PLX_BASE     = 84               ; sprite X of window pixel 0 (art inset 4)
PLW_MAX      = PFW*8 - 16       ; 176
PLW_MAX_DUAL = PFW*8 - 32       ; the pair is 32 pixels wide
PLY          = 218              ; the fighter is fixed to the bottom

; ---- formation -----------------------------------------------------------
FORMATION_SIZE = 40
MAX_ENEMIES    = 48
; One object past the pool: the tractor beam.  It is a sprite the chain has to
; carry but not an enemy, and giving it a slot of its own means the
; multiplexer's list is a list of object indices with no special case in it.
BEAM_OBJ       = MAX_ENEMIES
NMUXOBJ        = MAX_ENEMIES + 1
GRIDROWS       = 5
SLOT_CAPTIVE   = 47             ; the docked fighter rides here
TRIO_BASE      = 40             ; slots 40-46: transform trios and strays

; enemy_state
EST_DEAD   = 0
EST_GRID   = 1
EST_ENTER  = 2
EST_DIVE   = 3
EST_RETURN = 4
EST_DOCKED = 5
EST_EXPLODE = 6

; enemy_type
ETY_DRONE    = 0
ETY_SENTINEL = 1
ETY_FLAGSHIP = 2
ETY_TRANS    = 3
ETY_CAPTIVE  = 4

; enemy_flags
EFL_CARRIES = $80               ; this Flagship has the player's fighter
EFL_TRANS   = $40               ; a transformed mini-enemy
EFL_ESCORT  = $20               ; escort of a diving Flagship
EFL_SWEEP   = $10               ; a challenging-stage sweeper
EFL_BEAM    = $08               ; the tractor beam is deployed

; ---- game states ---------------------------------------------------------
ST_TITLE   = 0
ST_ANNOUNCE = 1
ST_ENTER   = 2
ST_PLAY    = 3
ST_CLEAR   = 4
ST_DEAD    = 5
ST_OVER    = 6
ST_RESULT  = 7
ST_COLD    = 8                  ; the cold open (§1a) -- before the title
NUM_STATES = 9

; ---- raster event kinds --------------------------------------------------
EV_FRAME  = 0                   ; top of frame: hand the tick to the main loop
EV_MUX    = 1                   ; reposition one multiplexed sprite
EV_SCRON  = 2                   ; formation band: apply the breathe sway
EV_SCROFF = 3                   ; formation band ends: back to the base scroll
EV_END    = 4                   ; nothing left this frame

MAXOBJ    = 24                  ; sprite objects the multiplexer will carry
MAXEV     = 28
BAND_TOP  = 74                  ; raster line where the formation band starts
BAND_BOT  = 148                 ; and where it ends

; --------------------------------------------------------------------------
        .segment "LOADADDR"
        .word   $0801

        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

; MAIN holds nothing but the jump into the engine; --area fills $080D-$3FFF
; with zeros, which is exactly the blank slate the charset and the sprite
; blocks want before startup writes the art into them.
        .segment "CODE"
        jmp     start

; --------------------------------------------------------------------------
        .segment "ENGINE"

; scrtext -- assemble a string as screen codes.  ca65 emits raw ASCII and
; screen codes are not ASCII: letters are ASCII-64, and digits, space and
; punctuation happen to coincide.  The six lowercase letters are the aliases
; for the glyphs Spanish needs and the ROM has not got.
.macro  scrtext str
        .repeat .strlen(str), i
        .if (.strat(str, i) >= 65) .and (.strat(str, i) <= 90)
        .byte   .strat(str, i) - 64
        .elseif .strat(str, i) = 97
        .byte   27                      ; a-acute
        .elseif .strat(str, i) = 101
        .byte   28                      ; e-acute
        .elseif .strat(str, i) = 105
        .byte   29                      ; i-acute
        .elseif .strat(str, i) = 111
        .byte   30                      ; o-acute
        .elseif .strat(str, i) = 117
        .byte   31                      ; u-acute
        .elseif .strat(str, i) = 110
        .byte   59                      ; n-tilde
        .elseif .strat(str, i) = 63
        .byte   60                      ; inverted exclamation
        .else
        .byte   .strat(str, i)
        .endif
        .endrepeat
.endmacro

.macro  scrline str
        scrtext str
        .byte   0
.endmacro

; ==========================================================================
start:  sei
        cld
        lda     #$37                    ; KERNAL banked in, and never called
        sta     $01
        ldx     #$FF
        txs

        ; Silence both CIAs.  With the CIA#1 timer interrupt gone the
        ; KERNAL's keyboard scan never runs, so $CB is a byte this program
        ; only ever reads and a value `c64 key hold` pokes there persists --
        ; which is what makes the game drivable from the CLI (PLAN.md §0).
        lda     #$7F
        sta     CIA1ICR
        sta     CIA2ICR
        lda     CIA1ICR
        lda     CIA2ICR

        jsr     clearvars
        jsr     installart
        jsr     sidinit
        jsr     hiscoreinit

        lda     #$1E                    ; screen $0400, charset $3800
        sta     VMCSB
        lda     #COL_BLACK
        sta     BORDER
        sta     BACKGND
        lda     #$0B                    ; text mode, 25 rows, screen OFF --
        sta     SPRCTRL1                ; the cold open owns $D011 from here
                                        ; and its exit turns the screen on
        lda     #$08                    ; 40 columns, hires text, scroll 0
        sta     SPRCTRL2
        sta     scrolloff
        sta     scrollon                ; until formtick runs; a zero here is
                                        ; 38 columns and eats screen column 0
        lda     #0
        sta     SPRENA
        lda     #COL_RED                ; the two shared multicolour values,
        sta     SPRMC0                  ; chosen once for the whole cast
        lda     #COL_BLUE
        sta     SPRMC1

        jsr     screenbuild             ; before cli: no frame to overrun yet
        jsr     coldenter               ; the cold open comes before the
                                        ; title, and is the attract loop's top

        jsr     irqinit
        cli

mainloop:
        lda     tickpend
        beq     mainloop
        lda     #0
        sta     tickpend
        jsr     tick
        jmp     mainloop

; --------------------------------------------------------------------------
; tick -- one game tick, once per frame, entered from the main loop the
; instant the top-of-frame raster interrupt hands it over.  This is the
; anchor every deterministic observation uses:
;
;   c64 until tick --count N      frame stepping
;   c64 key hold a --at tick      held input
;
; $D020 goes red at the top and black at the bottom, so the coloured band
; down the border *is* this routine's cost (PROMPT.md §11).
;
; muxbuild runs FIRST, before any game logic, and that ordering is
; load-bearing: it publishes the sprite schedule the raster chain will play
; out from line 51 onward, so it has to be finished before the beam gets
; there.  Running it last would have the game update rewriting the arrays
; the multiplexer was reading.
; --------------------------------------------------------------------------
tick:   lda     rasterband              ; §11's cost band, off by default --
        beq     :+                      ; on screen it reads as border tearing
        lda     #COL_RED
        sta     BORDER
        ; The cell count of the frame just gone is the one worth keeping: it
        ; is a per-frame budget, so a sampler that reads it every Nth tick
        ; measures a spot value and misses the repaint spikes entirely.  The
        ; program keeps the high-water mark instead, the way it already does
        ; for tick_endline, and the evidence reads that.
:       lda     cells_drawn
        cmp     cells_peak
        bcc     :+
        sta     cells_peak
:       lda     #0
        sta     cells_drawn             ; §11's per-frame redraw budget
        lda     vblcount
        sta     tickframe0

        inc     frames
        bne     :+
        inc     frames+1
:       jsr     rndstir

        jsr     muxbuild
        jsr     readinput
        jsr     soundtick
        ; The starfield's glyphs live at $3AC0-$3AD7 -- inside the cold
        ; open's bitmap -- so their rotation is parked while it is up.
        lda     gstate
        cmp     #ST_COLD
        beq     :+
        jsr     starstick
:

        ldx     gstate
        lda     statelo,x
        sta     tickvec+1
        lda     statehi,x
        sta     tickvec+2
tickvec:
        jsr     $FFFF

        ; §11: did this tick outlive its frame?
        lda     vblcount
        cmp     tickframe0
        beq     :+
        inc     tick_overrun
:       lda     SPRCTRL1                ; raster bit 8
        bpl     :+
        lda     #255                    ; lines 256-262 saturate the mark
        bne     :++
:       lda     $D012
:       cmp     tick_endline
        bcc     :+
        sta     tick_endline
:       lda     #COL_BLACK
        sta     BORDER
        rts

statelo:
        .byte   <sttitle, <stannounce, <stenter, <stplay
        .byte   <stclear, <stdead, <stover, <stresult, <stcold
statehi:
        .byte   >sttitle, >stannounce, >stenter, >stplay
        .byte   >stclear, >stdead, >stover, >stresult, >stcold

; setstate -- A = new state; the handler sees stinit set on its first tick.
setstate:
        sta     gstate
        lda     #1
        sta     stinit
        sta     hud_dirty               ; a state change may have cleared it
        rts

; --------------------------------------------------------------------------
; rndstir -- 16-bit Galois LFSR.  Seeded from the raster and the jiffy-free
; frame counter at reset; stirred every frame and again on every keypress,
; so two games started on different frames diverge.
; --------------------------------------------------------------------------
rndstir:
        lda     rnd+1
        asl     a
        rol     rnd
        rol     rnd+1
        bcc     :+
        lda     rnd
        eor     #$2D
        sta     rnd
        lda     rnd+1
        eor     #$B4
        sta     rnd+1
:       lda     rnd
        rts

; --------------------------------------------------------------------------
; clearvars -- BSS is not in the .prg and .res storage in a filled area is
; only zero by luck, so every mutable byte is zeroed here by one loop over a
; contiguous block.
; --------------------------------------------------------------------------
clearvars:
        lda     #<varsbeg
        sta     PTR
        lda     #>varsbeg
        sta     PTR+1
        ldy     #0
        ; Walk PTR itself one byte at a time and stop when it is exactly
        ; varsend.  (The old loop indexed with Y off a fixed PTR but compared
        ; PTR+1/Y against the two halves of varsend -- two different
        ; addresses -- so it ran far past the block and into the code.)
clv1:   lda     PTR+1
        cmp     #>varsend
        bne     clv2
        lda     PTR
        cmp     #<varsend
        beq     clv3
clv2:   tya
        sta     (PTR),y
        inc     PTR
        bne     clv1
        inc     PTR+1
        bne     clv1                    ; always: PTR+1 wrapping to 0 is a bug
clv3:
        ; seed the LFSR from the raster; zero would shift to zero for ever
        lda     $D012
        ora     #$41
        sta     rnd
        lda     #$1D
        sta     rnd+1
        rts

; ==========================================================================
        .include "vars.s"
        .include "screen.s"
        .include "chars.s"
        .include "sprites.s"
        .include "mux.s"
        .include "stars.s"
        .include "formation.s"
        .include "waves.s"
        .include "enemy.s"
        .include "player.s"
        .include "shots.s"
        .include "collide.s"
        .include "stage.s"
        .include "hud.s"
        .include "title.s"
        .include "cold.s"
        .include "sound.s"
        .include "text.inc"
        .include "traj.inc"
        .include "music.inc"

; The engine must not run past $9000; ld65 caps the area, and this names the
; overflow if it ever happens.
        .segment "ENGINE"
enginelast:
