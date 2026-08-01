; vars.s — every mutable byte the game owns, with the address labels the
; tests and the evidence protocol read back.
;
; Everything lives in DATA, not BSS: BSS is not part of the .prg, so a `.res`
; there holds whatever was in RAM at load time (the 6502-assembly skill's
; "BSS is not in the .prg" trap).  In DATA the bytes ship as real zeros and a
; fresh LOAD always starts from a known state.

        .segment "DATA"

; ---- scratch -------------------------------------------------------------
tmp0:       .byte 0
tmp1:       .byte 0
tmp2:       .byte 0
ivx:        .byte 0             ; saved invader index across pointer math
txtcol:     .byte 1             ; colour nybble txtat paints text with
seed:       .byte $2a           ; Galois LFSR state — must never be zero

; ---- global game state ---------------------------------------------------
gstate:     .byte 0             ; 0 title, 1 play, 2 base dying, 3 wave clear,
                                ; 4 game over
stinit:     .byte 1             ; 1 = this state has not drawn itself yet
sttimer:    .word 0             ; generic per-state countdown, in ticks
tick:       .byte 0             ; free-running frame counter
curkey:     .byte 64            ; $CB latched at the very top of mainloop

score:      .res 6, 0           ; six decimal digits, most significant first
hiscore:    .res 6, 0           ; survives across games (never cleared)
wave:       .byte 1
lives:      .byte 3
extradone:  .byte 0             ; 1 once the 1500-point extra life was given
scdirty:    .byte 1             ; HUD field dirty flags
hidirty:    .byte 1
wvdirty:    .byte 1
lvdirty:    .byte 1

; ---- the formation -------------------------------------------------------
alive:      .res 55, 0          ; 1 = this invader is on the board
icol:       .res 55, 0          ; its left character column
irow:       .res 55, 0          ; its character row
nalive:     .byte 0
sweep:      .byte 0             ; index of the invader moved this tick
mdir:       .byte 1             ; $01 = right, $FF = left
edgehit:    .byte 0             ; an invader touched an edge during this sweep
dropnext:   .byte 0             ; 1 = the next sweep drops a row and reverses
frame:      .byte 0             ; 0/1 march animation frame
skipcnt:    .byte 0             ; guard for the skip-dead scan in marchstep

; ---- the invader hit explosion (only one, because there is only one shot) -
expcnt:     .byte 0             ; ticks left; 0 = no explosion showing
exprow:     .byte 0
expcol:     .byte 0

; ---- the player ----------------------------------------------------------
; basex is in 2-pixel units: sprite X = 24 + 2*basex, so 0..136 keeps the
; whole 24-pixel sprite on screen and the value still fits in one byte.
basex:      .byte 68
shotact:    .byte 0             ; 1 = the single player shot is in flight
shotxu:     .byte 0             ; shot X in the same 2-pixel units
shotcol:    .byte 0             ; character column the shot travels up
shoty:      .byte 0             ; shot sprite Y (pixels)
shots:      .byte 0             ; shots fired this game — the UFO secret counter
dyingcnt:   .byte 0             ; base-explosion countdown

; ---- invader bombs (three in flight, three flavours) ---------------------
bactive:    .res 3, 0
btype:      .res 3, 0           ; 0 slow straight, 1 fast straight, 2 wiggly
bcol:       .res 3, 0
brow:       .res 3, 0
bdelay:     .res 3, 0
bslot:      .byte 0             ; the bomb slot the current routine is working on
bnexttype:  .byte 0             ; round-robin so all three flavours appear
bombtimer:  .byte 0             ; ticks until the next drop attempt

; ---- the mystery UFO -----------------------------------------------------
ufoact:     .byte 0
ufoxu:      .byte 0             ; X in 2-pixel units: sprite X = 24 + 2*ufoxu
ufodir:     .byte 1
ufoslow:    .byte 0             ; moves one unit every other tick
ufotimer:   .word 0             ; ticks until the next appearance
ufoflip:    .byte 0             ; alternates entry side

; ---- the four shields ----------------------------------------------------
; 4 bunkers x 4 columns x 2 rows = 32 cells, damage 3 (solid) down to 0 (gone)
shdmg:      .res 32, 0

; ---- sound ---------------------------------------------------------------
sidshadow:  .res 25, 0          ; mirror of $D400-$D418 (the SID is write-only)
sndprio2:   .byte 0             ; priority of whatever owns voice 2 (0 = idle)
sndprio3:   .byte 0             ; ... and voice 3
beatidx:    .byte 0             ; which of the four heartbeat notes is next
beatgap:    .byte 0             ; ticks left before a note may retrigger
fx2:        .byte 0             ; 0 none, 1 shot, 2 invader hit
fx2t:       .byte 0             ; ticks left
fx2fh:      .byte 0             ; swept frequency high byte
fx2rate:    .byte 0             ; sweep step per tick
fx2ctl:     .byte 0             ; the waveform+gate byte in use
fx3:        .byte 0             ; 0 none, 1 UFO warble, 3 player explosion
fx3t:       .byte 0
fx3cut:     .byte 0             ; swept filter cutoff for the explosion

; ---- sprite enable shadow ------------------------------------------------
sprena:     .byte 0
