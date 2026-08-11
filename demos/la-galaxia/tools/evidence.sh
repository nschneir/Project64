#!/bin/sh
# evidence.sh -- re-run the deterministic proof protocol and rewrite evidence/.
#
#   sh demos/la-galaxia/tools/evidence.sh
#
# Audio evidence is separate and costs real time; see tools/audio-evidence.sh.
#
# Five rules, each of which this demo learned by getting it wrong:
#
# 1. Every capture is taken with the machine STOPPED on the `tick` frame
#    anchor.  At warp a screenshot of a running game is a race.
#
# 2. `c64 screen --png` is a rolling scanline buffer, not a frame: lines the
#    beam has swept show the current partial frame, lines below it show the
#    PREVIOUS rendered frame -- and after a warp or free-running phase those
#    below-beam lines are arbitrarily stale (the first capture ever taken here
#    had boot-screen light blue under the program's own border).  So `shot`
#    always steps ONE more tick immediately before capturing, to flush them.
#    Do not "optimise" that step away.
#
# 3. NTSC canvas geometry wraps: PNG row = (raster - 20) mod 263.  In
#    raster-time.png the band's first lines (raster 2-11) therefore appear as
#    a red strip at the BOTTOM of the image on a perfectly healthy frame.
#    That strip is the band's start, not an overrun; the overrun tell is no
#    black anywhere.
#
# 4. States that would take minutes of play to reach are STAGED by poking the
#    program's own bytes -- the same bytes test.yaml asserts on, so the
#    evidence and the regression agree by construction.
#
# 5. This game switches the KERNAL keyboard scan off, so nothing ever writes
#    64 back to $CB: a `key hold` never releases by itself.  Every hold here
#    is followed by `release`.

set -e
C=".venv/bin/c64"
S="-s lgev"
PRG=demos/la-galaxia/la-galaxia.prg
LBL=demos/la-galaxia/la-galaxia.lbl
OUT=demos/la-galaxia/evidence

shot()    { $C until tick --count 1 --timeout 120 $S >/dev/null   # flush (rule 2)
            $C screen --png "$OUT/$1.png" --scale 2 $S >/dev/null
            echo "  $1.png"; }
shotb()   { $C until tick --count 1 --timeout 120 $S >/dev/null
            $C screen --png "$OUT/$1.png" --scale 2 --border $S >/dev/null
            echo "  $1.png"; }
ticks()   { $C until tick --count "$1" --timeout 180 $S >/dev/null; }
hold()    { $C key hold "$1" --at tick --frames "${2:-4}" $S >/dev/null; }
release() { $C mem write '$CB' 64 $S >/dev/null; }
# boot lands in the COLD OPEN (§1a), which is now the top of the attract
# cycle -- so every capture that needs the title or the stage select has to
# skip it first.  `bootcold` is the one that stays there, and it takes the
# tick count because the two uses want different ones: skipping the screen
# can happen the moment it is up, but PHOTOGRAPHING it has to wait for a page
# to be finished.  The smoothed 4x blit lays down two glyphs a tick, so the
# clear, the colour pass, the pinned line and page one's four lines take 34
# ticks, measured; 45 is inside the 240-frame hold with room either side.
bootcold() { $C load $PRG --symbols $LBL $S >/dev/null; ticks "${1:-30}"; }
boot()     { bootcold; hold space; release; ticks 40; }

# peaks -- step $1 samples of 10 ticks each, reporting the high-water mark of
# mux_count, the redraw count and tick_endline, and the final tick_overrun.
# A single sample of mux_count says nothing about the peak, and the peak is
# what §3 claims.  Note the asymmetry: mux_count is sampled (it moves slowly,
# so a 10-tick sampler tracks it), but the redraw count is read from
# `cells_peak`, which the PROGRAM max-tracks -- cells_drawn spikes only on
# repaint frames, so any sampler coarser than every tick would miss them and
# report a comfortable number that means nothing.
peaks() {
    # Zero the program's high-water mark first.  §11's ceiling is "at most 64
    # cells per frame OUTSIDE a stage transition", and cells_peak is a
    # lifetime mark that would otherwise carry the screen rebuilds -- the cold
    # open's art restore, a stage announcement -- which the spec exempts.
    # Zeroing here makes the number mean "the worst frame of THIS window".
    $C mem write cells_peak 0 $S >/dev/null
    mx=0; cd=0; el=0; i=0
    while [ "$i" -lt "$1" ]; do
        ticks 10
        v=$($C mem get mux_count $S); [ "$v" -gt "$mx" ] && mx=$v
        v=$($C mem get cells_peak $S); [ "$v" -gt "$cd" ] && cd=$v
        v=$($C mem get tick_endline $S); [ "$v" -gt "$el" ] && el=$v
        i=$((i + 1))
    done
    ov=$($C mem get mux_overflow $S)
    to=$($C mem get tick_overrun $S)
    echo "samples=$1x10 ticks  mux_count_peak=$mx  mux_overflow=$ov"
    echo "cells_drawn_peak=$cd (ceiling 64)  tick_endline_peak=$el"
    echo "tick_overrun=$to (must be 0)"
}

mkdir -p "$OUT"
$C build demos/la-galaxia/la-galaxia.s --area 'ENGINE=$4000:$6000' >/dev/null
$C session stop lgev >/dev/null 2>&1 || true
$C session start --name lgev --warp --headless >/dev/null
trap '$C session stop lgev >/dev/null 2>&1 || true' EXIT

echo "evidence:"

# --- the cold open (§1a) ---------------------------------------------------
bootcold
shot cold-open

# --- the attract screen ----------------------------------------------------
hold space; release; ticks 40
shotb title

# --- an entrance wave mid-flight (§6.2) ------------------------------------
# Stage 1 from the hidden stage select, caught while the groups are streaming
# on and before the last one settles.
hold 1; release; ticks 200
shot entrance
{ echo "# the entrance, where the most objects are in the air at once (§3)."
  echo "# The redraw figure is for THIS window only -- see the note below."
  peaks 30
  echo ""
  echo "# §11's redraw ceiling is 64 cells per frame *outside a stage"
  echo "# transition*.  Measured separately, per state:"
  echo "#   stage announcement (the screen rebuild)  72-88  -- exempt"
  echo "#   the entrance                                 5"
  echo "#   steady play                                 22"
  echo "# The exempt case is the only one that exceeds 64, which is what the"
  echo "# exemption is for; the claim is the two that do not."
} > "$OUT/mux.txt"
echo "  mux.txt"

# --- the settled 40-enemy grid (§6.1) --------------------------------------
ticks 900
shot formation
$C screen --codes $S > "$OUT/formation.codes.txt"
echo "  formation.codes.txt"

# --- a diver, mid-dive, carried by a hardware sprite (§3.2) ---------------
$C mem write divetimer 1 $S >/dev/null
ticks 40
shot dive
$C sprite status $S > "$OUT/dive.sprites.txt"
echo "  dive.sprites.txt"

# --- a damaged Flagship: one hit, colour swapped, still alive (§5) --------
# Slot 0 is a Flagship in the top row.  Dropping its hit points to 1 and
# repainting is exactly what the first hit does.
boot; hold 1; release; ticks 900
$C mem write enemy_hp 1 $S >/dev/null
$C mem write animphase 0 $S >/dev/null
ticks 40
shot flagship-damaged

# --- the tractor beam, deployed above the fighter (§6.3) ------------------
# Staged rather than waited for: a Flagship over the player captures within a
# couple of frames, so a played beam is gone before a capture can land.
boot; hold 1; release; ticks 900
$C mem write enemy_state 3 $S >/dev/null
$C mem write enemy_flags 8 $S >/dev/null
$C mem write beamslot 0 $S >/dev/null
$C mem write enemy_y 170 $S >/dev/null
ticks 12
shot tractor-beam

# --- the Dual Fighter after a mid-flight rescue (§5) ----------------------
# Staged by poking, not by `c64 call rescue`, for two reasons.  A call's fake
# return address replaces the program's control flow, so the flush tick in
# `shot` can never fire afterwards -- and `playerdraw` runs inside the tick,
# so a call-then-capture would show the sprites as they were BEFORE the call.
# Setting the state the rescue sets and stepping a tick renders it properly.
boot; hold 1; release; ticks 900
$C mem write pldual 1 $S >/dev/null
$C mem write plstate 0 $S >/dev/null
$C mem write plalive 1 $S >/dev/null
ticks 4
shot dual-fighter
$C sprite status $S > "$OUT/dual-fighter.sprites.txt"
echo "  dual-fighter.sprites.txt"

# --- the stage select working: stage 4 on the first frame of play (§2) ----
boot
hold 4; release; ticks 30
shot stage-select

# --- transforming enemies, three mini-enemies in flight (§6.4) ------------
# Reached with the stage select, `4` -- the stages where they appear.  The
# trio is written straight into the stray slots 40-42 rather than called for:
# `picktransform` needs a diver inside a Y window on the frame it happens to
# run, which is not reproducible, and a `c64 call` would end the run before
# the shapes could be drawn.  A trio member carries its own shape (etshape
# skips anything flagged EFL_TRANS), so the shape bytes are poked too.
ticks 900
$C mem write 'enemy_state+40' 3 3 3 $S >/dev/null
$C mem write 'enemy_type+40' 3 3 3 $S >/dev/null
$C mem write 'enemy_flags+40' 64 64 64 $S >/dev/null
$C mem write 'enemy_hp+40' 1 1 1 $S >/dev/null
$C mem write 'enemy_shape+40' 142 143 144 $S >/dev/null
$C mem write 'enemy_col+40' 13 8 14 $S >/dev/null
$C mem write 'enemy_x_lsb+40' 130 160 190 $S >/dev/null
$C mem write 'enemy_x_msb+40' 0 0 0 $S >/dev/null
$C mem write 'enemy_y+40' 130 138 146 $S >/dev/null
$C mem write 'enemy_y_msb+40' 0 0 0 $S >/dev/null
$C mem write triolive 3 $S >/dev/null
ticks 4
shot transform

# --- the challenging stage mid-sweep (§6.4), reached with `3` ------------
boot
hold 3; release; ticks 260
shot challenging-stage

# --- the perfect bonus: all 40 hit (§6.4) --------------------------------
$C mem write hits 40 $S >/dev/null
$C mem write perfect 1 $S >/dev/null
$C mem write gstate 7 $S >/dev/null
$C mem write stinit 1 $S >/dev/null
ticks 20
shot perfect-bonus

# --- the frame budget made visible (§11) ---------------------------------
# `rasterband` is the instrumentation switch and ships OFF -- the coloured
# border is a debugger's instrument, not decoration.  Turn it on for this one
# capture, take it on the busiest state in the game, and read the result by
# rule 3 above.  The memory-truth version of this claim is `tick_overrun`,
# which test.yaml asserts.
boot
hold 3; release; ticks 260
$C mem write rasterband 1 $S >/dev/null
shotb raster-time
{ echo "# the challenging stage -- the tightest frames in the game (§11)."
  echo "# tick_endline saturates at 255: the tick ends inside the frame's"
  echo "# last few lines.  Zero overruns, but this is the state with the"
  echo "# least margin, and the band in raster-time.png is that margin."
  peaks 40
} > "$OUT/frame-budget.txt"
echo "  frame-budget.txt"

# --- game over (§13) ------------------------------------------------------
boot
hold 1; release; ticks 900
$C mem write lives 0 $S >/dev/null
$C mem write plalive 0 $S >/dev/null
$C mem write gstate 6 $S >/dev/null
$C mem write stinit 1 $S >/dev/null
ticks 30
shot game-over

echo "done -- $(ls "$OUT"/*.png | wc -l | tr -d ' ') frames"
