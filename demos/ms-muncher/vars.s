; vars.s -- every mutable byte, in one contiguous block so startup can zero
; it with a single loop.
;
; These live in CODE, not BSS, on purpose.  BSS is the last thing the linker
; places, and the art block at the end of this program has to be the last
; thing in the *file* so it can be relocated out of the VIC's bank at
; startup -- variables after it would land on top of the sprite shapes.
; Reserving them here costs 270-odd zero bytes in the .prg and buys a layout
; that cannot silently break.
;
; Everything a test or the evidence protocol reads by name lives here:
; score, lives, board, dotsleft, gstate, dir/state arrays, and the SID
; shadow.  The tile map itself is at $C000, outside the .prg entirely.

        .segment "CODE"

varsbeg:

; ---- game -----------------------------------------------------------------
gstate:     .res 1              ; ST_* -- which state handler tick dispatches
stinit:     .res 1              ; 1 = the state handler must initialise
sttimer:    .res 1              ; generic per-state countdown
curkey:     .res 1              ; the held key's matrix code, latched at the
                                ; top of tick
frames:     .res 2              ; free-running frame counter
rndstate:   .res 2              ; 16-bit LFSR, stirred by key timing
board:      .res 1              ; 1-based board number
maze:       .res 1              ; 0-3, which layout this board uses
lives:      .res 1
score:      .res 3              ; 24-bit binary; hud.s renders the decimals
hiscore:    .res 3
extradone:  .res 1              ; the 10 000-point extra life is once only
dotsleft:   .res 1
sprena:     .res 1              ; shadow of $D015
huddirty:   .res 1
txtcol:     .res 1              ; colour nybble txtat writes
wallhi:     .res 1              ; this maze's $D022 wall highlight
wallcol:    .res 1              ; this maze's per-cell wall colour nybble
spdgroup:   .res 1              ; 0-3, which row of the speed table
demomode:   .res 1              ; 1 = attract mode is playing itself

; ---- actors ---------------------------------------------------------------
axhi:       .res NACT           ; X pixel of the actor's centre, 0..223
ayhi:       .res NACT           ; Y pixel, 0..175
afrac:      .res NACT           ; 8.8 sub-pixel accumulator
aspdlo:     .res NACT           ; speed, 16-bit: 100% = $0140 = 1.25 px/frame
aspdhi:     .res NACT
adir:       .res NACT
awant:      .res NACT           ; buffered turn, taken at the next centre
astate:     .res NACT           ; GS_* for the ghosts
ashape:     .res NACT           ; sprite block written to SPRPTR+n

; ---- per-centre scratch ---------------------------------------------------
ai:         .res 1              ; actor being stepped
tcol:       .res 1              ; the actor's tile
trow:       .res 1
ncol:       .res 1              ; the tile it is testing
nrow:       .res 1
blocked:    .res 1
passhouse:  .res 1              ; 1 = door and house interior are passable
steps:      .res 1              ; whole pixels still owed this frame
tmp:        .res 8
gi:         .res 1              ; ghost index, 0-3 (actor index minus one)
ptcol:      .res 1              ; the tile Ms. Muncher stands on
ptrow:      .res 1
tgtx:       .res 1              ; the tile the chooser is steering toward
tgty:       .res 1
dlo:        .res 1              ; squared distance out of sqdist
dhi:        .res 1
bestlo:     .res 1
besthi:     .res 1
bestdir:    .res 1
dirlist:    .res 4
dscore:     .res 1              ; the demo player's score for one option
hidx:       .res 1              ; row counter for the score table
rowbuf:     .res MW             ; one unpacked, mirrored maze row

; ---- ghosts ---------------------------------------------------------------
gtx:        .res 4              ; target tile, one per ghost
gty:        .res 4
gdots:      .res 4              ; personal dot counters for the house
greleased:  .res 4
housedots2: .res 4          ; the live release thresholds, which the
housetime2: .res 4          ; global no-dot timer lowers to zero
nodot:      .res 1          ; frames since the last dot was eaten
ghcombo:    .res 1              ; ghosts eaten in this frightened period
phase:      .res 1              ; index into the scatter/chase table
phtimer:    .res 2
frtimer:    .res 2              ; frightened countdown
frflash:    .res 1
boardfrm:   .res 2              ; frames since this board started
dotseaten:  .res 1              ; dots eaten this board (house release)
animframe:  .res 1              ; ghost body frame, 0 or 1
animcount:  .res 1
elroy:      .res 1              ; 0, 1 or 2 -- Bruiser's cruise level
scatteropen: .res 1             ; 1 = the randomised opening scatter

; ---- fruit ----------------------------------------------------------------
fractive:   .res 1
frwp:       .res 1              ; index into this fruit's waypoint route
frkind:     .res 1              ; 0-6, which fruit this board shows
frcount:    .res 1              ; how many have appeared this board
frlife:     .res 2
fruitwon:   .res 8              ; the pips along the bottom, newest last

; ---- intermission acts ----------------------------------------------------
actnum:     .res 1              ; 0-2
actnext:    .res 1              ; 1 = an act is due after this board
actstep:    .res 1
actfrm:     .res 2              ; frames into the current act
af:         .res 1              ; ... clamped to 255 for the scene code
acttimer:   .res 1
actret:     .res 1              ; ST_* to return to when the act ends

; ---- high scores ----------------------------------------------------------
hitab:      .res 5*3            ; five 24-bit scores, highest first
hinames:    .res 5*3            ; three initials each
entryslot:  .res 1              ; -1 = the score did not make the table
entrypos:   .res 1
entrychar:  .res 1
entrydelay: .res 1

; ---- sound ----------------------------------------------------------------
sidshad:    .res 25             ; mirror of $D400-$D418 -- the chip is
                                ; write-only, so these are the evidence
vfx:        .res 3              ; which effect is sweeping each voice
vprio:      .res 3              ; which effect owns each voice (0 = music)
vtimer:     .res 3              ; frames until the owner releases it
muslead:    .res 1              ; rows of silence before the next tune
musplay:    .res 1              ; 1 = a tune is running
mustune:    .res 1              ; which tune
musrow:     .res 1
musdiv:     .res 1
muswait:    .res 3              ; per-voice rows left on the current note
muspos:     .res 3              ; per-voice cursor into its track
sirenstep:  .res 1
sirendir:   .res 1
munchtog:   .res 1
svx:        .res 1              ; voice index across setvoicehit

varsend:

; clrvars: the .prg does ship these as zeros, but a second game in the same
; session must start from zero too -- so nothing above may rely on the load.
clrvars:
        lda     #<varsbeg
        sta     PTR
        lda     #>varsbeg
        sta     PTR+1
        lda     #0
        ldx     #>(varsend-varsbeg)     ; whole pages first
        beq     cvtail
cvpage: ldy     #0
cvp1:   sta     (PTR),y
        iny
        bne     cvp1
        inc     PTR+1
        dex
        bne     cvpage
cvtail: ldy     #<(varsend-varsbeg)
        beq     cvdone
cvt1:   dey
        sta     (PTR),y
        bne     cvt1
cvdone: rts
