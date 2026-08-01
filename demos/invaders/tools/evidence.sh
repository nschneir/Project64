#!/bin/sh
# evidence.sh — drive the game deterministically and capture the evidence
# PNGs in demos/invaders/evidence/.
#
# Every capture is taken with the machine STOPPED at the `mainloop` frame
# anchor: a screenshot of a running machine is a race, and at warp the frame
# you wanted is long gone.  Input is injected the way a player supplies it —
# the held-key matrix code at $CB — never by poking game state, except where
# a comment says otherwise.
#
#   sh demos/invaders/tools/evidence.sh
#
# Re-runnable: it stops and restarts its own session.

set -e
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
C="$ROOT/.venv/bin/c64"
DEMO="$ROOT/demos/invaders"
EV="$DEMO/evidence"
S=invev

mkdir -p "$EV"
"$C" -s $S session stop 2>/dev/null || true
"$C" session start --name $S --warp --headless >/dev/null
"$C" -s $S run "$DEMO/invaders.s" >/dev/null

shot () { "$C" -s $S screen --png "$EV/$1" --scale 2 >/dev/null; echo "  captured $1"; }
step () { "$C" -s $S until mainloop --count "$1" >/dev/null; }
hold () { "$C" -s $S mem write '$CB' "$1" >/dev/null; step 1; }   # one held tick
get  () { "$C" -s $S mem get "$1" "${2:-1}" | tr -d '\n'; }

echo "== 1. title screen =="
step 30
shot title.png

echo "== 2. formation marching and animating =="
step 25
hold 60                       # SPACE starts the game
step 20
shot formation.png
WAVE1TOP=$(get irow)
echo "  wave $(get wave) STARTS at top row $WAVE1TOP, bottom row $(get irow+44)"
echo "  sweep=$(get sweep)  frame=$(get frame)  nalive=$(get nalive)  mdir=$(get mdir)"
echo "  invader row 0 columns: $(get icol 11)"
step 60                       # one more full sweep: the formation has stepped
shot formation-2.png
echo "  invader row 0 columns: $(get icol 11)   <- the whole row moved one cell"

echo "== 3. a shield eroding under the player's fire =="
# Bunker 0 covers columns 4-7. The shot's column is (basex+6)/4, so basex 14,
# 18 and 22 aim at bunker cells 1, 2 and 3. One, two and three hits leave
# them cracked, crumbling and gone — three damage states in one picture.
echo "  shdmg[0..7] before: $(get shdmg 8)"
for pair in "14 1" "18 2" "22 3"; do
  set -- $pair
  "$C" -s $S mem write basex "$1" >/dev/null
  i=0
  while [ $i -lt "$2" ]; do
    hold 60                   # fire
    step 8                    # let the bolt reach the bunker
    i=$((i+1))
  done
done
shot shield-eroded.png
echo "  shdmg[0..7] after : $(get shdmg 8)   (3 solid, 2 cracked, 1 crumbling, 0 gone)"

echo "== 4. bombs of different flavours in flight =="
# Only the SPAWN TIMER is forced here, three ticks in a row; the bombs
# themselves are dropped, typed and flown entirely by the game (bombspawn
# round-robins the three flavours, so three consecutive drops give one of each).
i=0
while [ $i -lt 3 ]; do
  "$C" -s $S mem write bombtimer 0 >/dev/null
  step 1
  i=$((i+1))
done
step 14
shot bombs.png
echo "  bactive=$(get bactive 3)  btype=$(get btype 3)  (0 slow straight, 1 fast straight, 2 wiggly)"
echo "  brow=$(get brow 3)  bcol=$(get bcol 3)"

echo "== 4b. shooting invaders for a score =="
i=0
while [ $i -lt 12 ]; do
  TC=$(get icol+49)           # a live column in the bottom row
  "$C" -s $S mem write basex $((TC * 4 - 6)) >/dev/null
  hold 60                     # fire
  step 14                     # let the bolt reach the formation
  i=$((i+1))
done
echo "  score=$(get score 6)  nalive=$(get nalive)"

echo "== 5. the mystery UFO crossing =="
"$C" -s $S mem write ufotimer 0 0 >/dev/null   # only the countdown is skipped
step 3
step 60
shot ufo.png
echo "  \$D015=$("$C" -s $S mem read '$D015' 1 | head -1)"
"$C" -s $S sprite status

echo "== 6. SID shadow captured mid-heartbeat =="
"$C" -s $S break clear >/dev/null
"$C" -s $S break add sndbeat >/dev/null
"$C" -s $S wait --break --timeout 30 >/dev/null
"$C" -s $S finish >/dev/null                   # the note is now programmed
echo "  sidshadow (\$D400-\$D418): $(get sidshadow 25)"
echo "  beatidx=$(get beatidx)"
"$C" -s $S break clear >/dev/null
step 1

echo "== 7. wave 2 starts one row lower than wave 1 =="
echo "  wave 1 STARTED at top row $WAVE1TOP (it has since marched down)"
"$C" -s $S mem write alive 0 >/dev/null        # clearing the wave by hand is
i=1                                            # faster than shooting 55 aliens
while [ $i -lt 55 ]; do
  "$C" -s $S mem write alive+$i 0 >/dev/null
  i=$((i+1))
done
"$C" -s $S mem write nalive 0 >/dev/null
step 95
shot wave2.png
echo "  wave $(get wave) STARTS at top row $(get irow), bottom row $(get irow+44)"

echo "== 8. game over =="
"$C" -s $S mem write lives 1 >/dev/null
"$C" -s $S mem write bactive 1 >/dev/null      # a bomb one row above the base
"$C" -s $S mem write btype 1 >/dev/null
"$C" -s $S mem write bdelay 0 >/dev/null
"$C" -s $S mem write brow 20 >/dev/null
BX=$("$C" -s $S mem get basex | tr -d ' \n')
"$C" -s $S mem write bcol $((BX / 4 + 1)) >/dev/null
step 50
echo "  score at game over: $(get score 6)   gstate=$(get gstate)"
shot game-over.png

echo "== 9. a second game, carrying the first game's score as HI =="
step 210                      # the GAME OVER hold, then back to the title
step 50                       # the attract-screen key lockout
hold 60
step 3
shot hiscore.png
echo "  game 2: score=$(get score 6)  hiscore=$(get hiscore 6)  lives=$(get lives)  wave=$(get wave)"
"$C" -s $S screen | head -1

"$C" -s $S session stop >/dev/null
echo "== done: $EV =="
