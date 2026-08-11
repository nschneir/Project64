; vars.s -- every mutable byte, in one contiguous block so startup can zero
; it with a single loop.  These live in the ENGINE segment rather than BSS:
; BSS is placed last, and `.res` in a linker-filled area ships as zeros in
; the .prg but says nothing about what is there after a reset, so the loop
; runs anyway and the block has to have known bounds.
;
; Everything a test or the evidence protocol reads by name lives here:
; score, lives, stage, input_state, mux_count, mux_overflow, the enemy
; structure-of-arrays, and the SID shadow.

        .segment "ENGINE"

varsbeg:

; ---- frame and state ------------------------------------------------------
        .export gstate, frames, stage, lives, score, hiscore
        .export input_state, stage_select, mux_count, mux_overflow
        .export sidshad, cells_drawn, cells_peak, breathe, bullets_live, hits
gstate:     .res 1              ; ST_* -- which handler tick dispatches
stinit:     .res 1              ; 1 = the handler must initialise
sttimer:    .res 2              ; generic per-state countdown
tickpend:   .res 1              ; the raster IRQ hands the tick over here
frames:     .res 2              ; free-running frame counter
rnd:        .res 2              ; 16-bit LFSR
cells_drawn: .res 1             ; character cells redrawn this frame (§11)
cells_peak:  .res 1             ; ... and the worst frame so far, so the
                                ; evidence reads a ceiling, not a sample
; §11's real evidence.  A $D020 band capture shows one arbitrary previous
; frame and the frames that overrun are episodic, so the tick measures itself:
; vblank is counted in the raster chain, the count is sampled at tick entry
; and tick exit, and a tick that saw the counter move crossed a frame boundary
; and overran.  tick_endline is the high-water mark of $D012 at tick exit.
        .export tick_overrun, tick_endline, rasterband
; The $D020 band is instrumentation, not decoration: on a real display it
; reads as tearing at the top and bottom of the border.  Default OFF; the
; evidence protocol pokes rasterband to 1 before capturing raster-time.png.
rasterband:  .res 1             ; 1 = paint the tick's cost into $D020
vblcount:    .res 1             ; incremented by the top-of-frame event
tickframe0:  .res 1             ; vblcount as this tick started
tick_overrun: .res 1            ; ticks that crossed a frame boundary
tick_endline: .res 1            ; worst raster line the tick has ended on
sbstep:      .res 1             ; the multi-frame screen rebuild's cursor
sbactive:    .res 1             ; 1 = a rebuild is in progress

; ---- the cold open (§1a) --------------------------------------------------
; Everything the bitmap screen's step machine needs to survive between
; ticks: every phase does a bounded slice of work per frame, because the
; bitmap clear, the 4x blits and the art restore are each several frames of
; cycles and a single tick that ran them whole would show in tick_overrun.
        .export coldphase, coldpage
coldphase:  .res 1              ; CPH_* / CPX_* -- which slice runs this tick
coldpage:   .res 1              ; 0-4 -- which narration page is up
coldline:   .res 1              ; index into the narration line table
coldcp:     .res 1              ; character offset within that line
coldcol:    .res 1              ; cell column the next glyph lands at
coldrow:    .res 1              ; the clear/wipe's row cursor
coldtimer:  .res 1              ; frames left on the page hold
coldn:      .res 1              ; glyphs left in this tick's slice

; ---- input ----------------------------------------------------------------
input_state: .res 1             ; the one byte everything downstream reads
input_prev:  .res 1
input_edge:  .res 1             ; bits that went 0->1 this frame
; The any-key signal, derived beside input_edge from the same three sources
; and kept separate from input_state: it reports keys the game has no
; mapping for, and folding it into input_state would give every one of them
; a meaning everywhere else in the game.  Only the cold open reads it (§1a).
        .export anykey, anykey_edge
anykey:      .res 1             ; 1 = something is down: any key, or fire
anykey_prev: .res 1
anykey_edge: .res 1             ; 1 = it went down THIS frame
stage_select: .res 1            ; 0, or 1-10 chosen on the title screen
matbits:     .res 1             ; what the matrix scan alone reported
joybits:     .res 1             ; what the joystick alone reported
keybits:     .res 1             ; what $CB alone reported

; ---- game -----------------------------------------------------------------
stage:      .res 1              ; 1-based, clamps at 255
tier:       .res 1              ; index into difftab
lives:      .res 1
score:      .res 3              ; 24-bit binary, little endian
hiscore:    .res 3
extraidx:   .res 1              ; how many extra lives have been awarded
dip_extra_life: .res 1          ; which row of extratab is in force
players:    .res 1              ; 1 or 2
curplayer:  .res 1              ; 0 or 1
altscore:   .res 3              ; the other player's saved state
altstage:   .res 1
altlives:   .res 1
altstarted: .res 1
enemies_left: .res 1            ; live formation members
hits:       .res 1              ; challenging-stage hit count
perfect:    .res 1              ; 1 = all 40 hit on a challenging stage
challenge:  .res 1              ; 1 = this is a challenging stage

; ---- the player's fighter -------------------------------------------------
        .export plx, plstate, pldual, plalive
plxf:       .res 1              ; fighter X, 8.8 in window pixels
plx:        .res 2
dirlast:    .res 1              ; 1 = the last move was rightward
plstate:    .res 1              ; 0 flying, 1 captured, 2 exploding
pldual:     .res 1              ; 1 = Dual Fighter
plalive:    .res 1
plspin:     .res 1              ; capture animation frame
pltimer:    .res 1
plcapt:     .res 1              ; slot of the Flagship carrying the fighter
firecool:   .res 1

; ---- enemies: structure of arrays ----------------------------------------
; Forty enemies on a 1 MHz 6502 means every per-enemy field is one
; `LDA absolute,X` away and never a pointer chase.  Position is 16.8 signed
; fixed point so a 2.0 px/frame dive is exactly that and not an alternating
; 1 and 2.
        .export enemy_state, enemy_type, enemy_x_lsb, enemy_x_msb, enemy_y
        .export enemy_hp, enemy_flags, enemy_path, enemy_slot
enemy_state:  .res NMUXOBJ      ; EST_*
enemy_type:   .res NMUXOBJ      ; ETY_*
enemy_x_frac: .res NMUXOBJ    
enemy_x_lsb:  .res NMUXOBJ      ; X, low 8 bits
enemy_x_msb:  .res NMUXOBJ      ; X, 9th bit for the VIC (and the sign)
enemy_y_frac: .res NMUXOBJ    
enemy_y:      .res NMUXOBJ      ; Y, low 8 bits
enemy_y_msb:  .res NMUXOBJ    
enemy_path:   .res NMUXOBJ      ; PATH_* -- which trajectory it is flying
enemy_pathix: .res NMUXOBJ      ; byte offset into that path
enemy_pathct: .res NMUXOBJ      ; frames left in the current segment
enemy_head:   .res NMUXOBJ      ; current heading, 0-63
enemy_speed:  .res NMUXOBJ      ; 0/1/2 -- which velocity table
enemy_hp:     .res NMUXOBJ      ; 2 for an undamaged Flagship, else 1
enemy_flags:  .res NMUXOBJ      ; EFL_*
enemy_slot:   .res NMUXOBJ      ; formation slot this object belongs to
enemy_timer:  .res NMUXOBJ      ; launch delay, halt countdown, explosion age
enemy_shape:  .res NMUXOBJ      ; sprite block
enemy_col:    .res NMUXOBJ      ; sprite colour
homex:        .res NMUXOBJ      ; the grid cell this enemy is homing on, in
homexm:       .res NMUXOBJ      ; pixels, cached while gridexp holds still
homey:        .res NMUXOBJ
homeok:       .res NMUXOBJ
; The current path segment's velocity, cached with its sign extension when
; the segment loads.  Heading and speed only change at a segment boundary,
; so re-deriving this through velload every frame cost ~65 cycles per flying
; object for an answer that holds for the whole segment.
enemy_vxl:    .res NMUXOBJ
enemy_vxh:    .res NMUXOBJ
enemy_vxs:    .res NMUXOBJ      ; $00 or $FF -- vx sign-extended
enemy_vyl:    .res NMUXOBJ
enemy_vyh:    .res NMUXOBJ
enemy_vys:    .res NMUXOBJ

; ---- the formation --------------------------------------------------------
breathe:    .res 1              ; 0-127, one full expand-and-contract
gridexp:    .res 1              ; 0 or 1 -- the expansion, in cells
redrawslot: .res 1              ; which slot the rolling repaint is up to
; slotexp -- the expansion each slot's block is CURRENTLY DRAWN at.  The
; repaint is spread over many frames, so at any moment some slots sit at the
; old spacing and some at the new; erasing them all at the global gridexp
; cleared cells that were already empty and left the block standing, which is
; the half-block trail at each end of every row.  Every erase goes through the
; slot's own value, so it always clears the cells the slot really occupies.
slotexp:    .res MAX_ENEMIES
scrollon:   .res 1              ; $D016 inside the formation band
scrolloff:  .res 1              ; $D016 everywhere else
animphase:  .res 1              ; settled-enemy animation frame
animdirty:  .res 1              ; 1 = it just flipped; sprites must refresh
wave:       .res 1              ; which entrance group is launching
wavemem:    .res 1              ; and which of its eight is next up
wavetimer:  .res 2
waveleft:   .res 1              ; entrants still in the air
sweepnext:  .res 1              ; challenging stage: the next sweeper to send

; gridmap -- which slot owns each playfield cell of the formation band, so a
; missile tests one byte instead of forty.  Ten rows of 24, slot+1 or zero.
gridmap:    .res 10 * PFW

; bgbuf/bgcol -- the playfield's settled content, shadowed so a missile or a
; bullet can put back exactly the star (or blank, or enemy block) it painted
; over.  Without it a shot crossing the starfield eats a star.
bgbuf:      .res 40 * PFROWS
bgcol:      .res 40 * PFROWS

; ---- shots ----------------------------------------------------------------
; Missiles and enemy bullets are character-space objects: eight bullets and
; four missiles as sprites would eat the multiplexer alive.
MAXMIS  = 4
MAXBUL  = 8
mis_on:     .res MAXMIS
mis_col:    .res MAXMIS         ; screen column: a missile only moves in Y
mis_y:      .res MAXMIS         ; pixel Y in the window, steps of 4
mis_prow:   .res MAXMIS         ; the row it is currently drawn in, $FF = none
bul_on:     .res MAXBUL
bul_xf:     .res MAXBUL         ; 8.8 pixel X inside the 192-pixel window
bul_x:      .res MAXBUL
bul_yf:     .res MAXBUL
bul_y:      .res MAXBUL
bul_vx:     .res MAXBUL         ; 8.8 signed, aimed at the fighter
bul_vxh:    .res MAXBUL
bul_vy:     .res MAXBUL
bul_vyh:    .res MAXBUL
bul_prow:   .res MAXBUL
bul_pcol:   .res MAXBUL
bullets_live: .res 1

; ---- difficulty, set from difftab when a stage starts --------------------
divespeed:  .res 1              ; which velocity table dives use
divepath:   .res 1              ; the dive script in force
divecad:    .res 1              ; frames between dive attempts
maxbullets: .res 1
firerate:   .res 1              ; chance a diving enemy shoots this frame
bulspeed:   .res 1              ; 8.8 high byte of the bullet's Y velocity
escorts:    .res 1              ; 1 = Flagships dive with two Drones
transforms: .res 1              ; 1 = dives can transform into trios
triolive:   .res 1              ; members of the current trio still alive
divetimer:  .res 1

; ---- the multiplexer ------------------------------------------------------
; mux_count is what the chain displayed this frame; mux_overflow is what a
; raster band could not fit.  Both are read straight out of memory by the
; audit, which is the only way to prove a claim about a multiplexer.
mux_count:    .res 1
mux_overflow: .res 1
mux_n:        .res 1            ; objects gathered before sorting
; obj* is this frame's SNAPSHOT of every object the chain may draw, indexed
; by the object itself and not by a position in a compacted list.  It has to
; be a snapshot: the reposition interrupts play out across the frame while the
; main loop is still moving enemies, so a chain reading the live arrays would
; tear.  Indexing it by object is what lets the sorted list survive from one
; frame to the next -- entry k means the same thing next frame -- and that
; turns the sort from a quadratic rebuild into an insertion pass over an
; almost-sorted array.
objy:       .res NMUXOBJ
objx:       .res NMUXOBJ
objmsb:     .res NMUXOBJ
objshape:   .res NMUXOBJ
objcol:     .res NMUXOBJ
inlist:     .res NMUXOBJ        ; 1 = this object is already in sortix
objok:      .res NMUXOBJ        ; 1 = snapshot valid and on screen this frame
divelow:    .res 1              ; a diver has come down into the fighter's rows
sortix:     .res MAXOBJ         ; objects, ascending by Y, kept across frames
sortkey:    .res MAXOBJ         ; each entry's Y, carried alongside so the
                                ; sort compares a byte instead of chasing
                                ; sortix into objy on every step
; The register assignment is recorded ON THE OBJECT, not on a copy of it: the
; schedule used to carry its own msy/msx/mmsb/mshape/mcol, five bytes copied
; per object per frame for arrays that were already sitting in obj*.
mreg:       .res NMUXOBJ        ; hardware sprite number * 2
mbit:       .res NMUXOBJ        ; its $D010 bit, and the complement
mnbit:      .res NMUXOBJ
rrnext:     .res 1              ; round robin: the register to try first
regfree:    .res 8              ; raster line each register comes free at
regused:    .res 8              ; has anything claimed it this frame
plena:      .res 1              ; the fighter's $D015 bits (0, 1 or both)
beamslot:   .res 1              ; Flagship deploying the tractor beam, or $FF

; ---- the raster event chain ----------------------------------------------
evline:     .res MAXEV
evkind:     .res MAXEV
evarg:      .res MAXEV
evidx:      .res 1
sprena_sh:  .res 1              ; shadow of $D015

; ---- the starfield --------------------------------------------------------
starphase:  .res 3              ; per-layer sub-frame counters

; ---- sound ----------------------------------------------------------------
; The SID is write-only, so every write is mirrored here at the moment it is
; issued.  These 25 bytes are the only testable evidence sound leaves.
sidshad:    .res 25
mus_on:     .res 1
mus_ord:    .res 1              ; position in the order list
mus_row:    .res 1              ; row within the pattern
mus_tick:   .res 1              ; frames left in this row
mus_pat:    .res 3              ; the three voices' current patterns
mus_note:   .res 3              ; the note each voice is holding
mus_inst:   .res 3              ; and which instrument is playing it
mus_trig:   .res 3              ; 1 = retrigger the gate this frame
mus_gate:   .res 3
mus_vib:    .res 3              ; vibrato phase
mus_slide:  .res 6              ; portamento accumulator, 16-bit per voice
mus_pw:     .res 2              ; pulse-width drift accumulator
sfxsavex:   .res 1              ; sfxstart preserves its caller's X here
vprio:      .res 3              ; who owns each voice right now
vtimer:     .res 3              ; frames left on the effect holding it
vfx:        .res 3              ; which effect
vfxstep:    .res 3
sfxpend:    .res 1

; The scratch bytes -- tmp0-tmp5, the velocity accumulators, the cell cursor,
; the digit buffer, and the two loop indices that cannot live in tmp -- are
; NOT here: they are zero page (see la-galaxia.s).  Every one of them is
; touched thousands of times a frame and a cycle each way across the whole
; tick is worth more than the tidiness of one contiguous block.

; ---- the HUD's redraw guard ----------------------------------------------
; Redrawing the whole panel every frame cost 4,233 cycles -- a quarter of an
; NTSC frame -- to repaint six labels and fifteen digits that change a few
; times a second.  Each part now redraws only when the value behind it moves,
; and hud_dirty forces the lot after anything has cleared the screen.
hud_dirty:  .res 1
hs_score:   .res 3
hs_hi:      .res 3
hs_stage:   .res 1
hs_lives:   .res 1
hs_player:  .res 1

varsend:
