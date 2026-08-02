#!/bin/sh
# evidence.sh — play the game deterministically and capture the evidence PNGs
# in demos/snake/evidence/.
#
# Every capture is taken with the machine STOPPED at the `mainloop` frame
# anchor: a screenshot of a running machine is a race, and at warp the frame
# you wanted is long gone.  Input is injected the way a player supplies it —
# the held-key matrix code at $CB, through `c64 key hold` — and nothing here
# pokes game state, beyond pinning the RNG seed once before the first game so
# the same apples come up every run.  The apples are still the ones the game's
# own LFSR deals; the routing below reads where they landed and steers there.
#
#   sh demos/snake/tools/evidence.sh
#
# Re-runnable: it stops and restarts its own session.

set -e
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
C="$ROOT/.venv/bin/c64"
DEMO="$ROOT/demos/snake"
EV="$DEMO/evidence"
S=snakeev

mkdir -p "$EV"
"$C" -s $S session stop 2>/dev/null || true
"$C" session start --name $S --warp --headless >/dev/null
"$C" -s $S run "$DEMO/snake.s" >/dev/null
"$C" -s $S wait --text "PRESS ANY KEY TO PLAY" --timeout 20 >/dev/null

# --scale 2, no --border: the frames match the other demos' 640x400, and the
# blue $D020 frame is proved by an assertion in test.yaml instead of a picture.
shot () { "$C" -s $S screen --png "$EV/$1" --scale 2 >/dev/null; echo "  captured $1"; }
step () { "$C" -s $S until mainloop --count "$1" >/dev/null; }
get  () { "$C" -s $S mem get "$1" "${2:-1}" | tr -d '\n' | sed 's/^ *//'; }
tap  () { "$C" -s $S mem write '$CB' "$1" >/dev/null; step 1; }   # one held tick
hold () {
  if [ "$2" -gt 0 ]; then "$C" -s $S key hold "$1" --at mainloop --frames "$2" >/dev/null; fi
}
# die_on — hand the fatal move to a breakpoint.  `key hold` cannot drive it:
# the snake leaves mainloop for good, so the hold's wait for the anchor times
# out and leaves the machine running past the crash.  $1 = matrix code.
die_on () {
  "$C" -s $S break add died >/dev/null
  "$C" -s $S mem write '$CB' "$1" >/dev/null
  "$C" -s $S wait --break --timeout 30 >/dev/null
  "$C" -s $S break clear >/dev/null
  step 1
}

# run_to [short] — steer the head onto the apple.  Legs are taken on whichever
# axis is not the reverse of the current heading (the game rejects a 180,
# which would otherwise leave the snake ploughing on into the wall); an apple
# dead astern gets one sidestep first so the turn becomes legal.
#
# With `short`, the final move is left undone and $LASTMK holds the matrix
# code that completes it — so the caller can hand that one move to a
# breakpoint and stop the machine inside the routine it triggers.
run_to () {
  SHORT=${1:-0}
  FR=$(get foodr); FC=$(get foodc); HR=$(get hrow); HC=$(get hcol); D=$(get curdir)
  DC=$((FC - HC)); DR=$((FR - HR))
  REV=0
  if [ "$D" = 3 ] && [ $DC -lt 0 ]; then REV=1; fi
  if [ "$D" = 2 ] && [ $DC -gt 0 ]; then REV=1; fi
  if [ $REV = 1 ] && [ $DR = 0 ]; then          # dead astern: sidestep, then turn
    if [ "$HR" -lt 12 ]; then hold s 1; else hold w 1; fi
    HR=$(get hrow); DR=$((FR - HR))
  fi
  if [ $REV = 1 ]; then ORDER="v h"; else ORDER="h v"; fi
  LAST=h; if [ $DR -ne 0 ]; then LAST=v; fi     # provisional; fixed below
  case $ORDER in
    "h v") if [ $DR -ne 0 ]; then LAST=v; else LAST=h; fi ;;
    "v h") if [ $DC -ne 0 ]; then LAST=h; else LAST=v; fi ;;
  esac
  for AX in $ORDER; do
    if [ $AX = h ]; then
      HC=$(get hcol); N=$((FC - HC)); K=d
      if [ $N -lt 0 ]; then N=$((-N)); K=a; fi
    else
      HR=$(get hrow); N=$((FR - HR)); K=s
      if [ $N -lt 0 ]; then N=$((-N)); K=w; fi
    fi
    if [ $N -gt 0 ] || [ "$AX" = "$LAST" ]; then
      if [ "$SHORT" = 1 ] && [ "$AX" = "$LAST" ]; then
        N=$((N - 1))
        case $K in d) LASTMK=18;; a) LASTMK=10;; s) LASTMK=13;; w) LASTMK=9;; esac
      fi
      hold $K $N
    fi
  done
}

# cwkey — the matrix code of the direction 90 degrees clockwise from $1.
# up(0) -> right(3) -> down(1) -> left(2) -> up(0).
cwdir () { case $1 in 0) echo 3;; 3) echo 1;; 1) echo 2;; 2) echo 0;; esac; }
mk    () { case $1 in 0) echo 9;; 1) echo 13;; 2) echo 10;; 3) echo 18;; esac; }
dkey  () { case $1 in 0) echo w;; 1) echo s;; 2) echo a;; 3) echo d;; esac; }

# alive — stop with a useful message rather than a checkpoint timeout if the
# routing has walked the snake into something.
alive () {
  if [ "$(get gstate)" != 1 ]; then
    echo "  ABORT: the snake died at $1 (gstate=$(get gstate)) — the route needs rework"
    "$C" -s $S session stop >/dev/null
    exit 1
  fi
}

# segcol — the colour cell of ring entry $1, as a decimal address.
segcol () {
  SL=$(get "bodylo+$1"); SH=$(get "bodyhi+$1")
  echo $(( SH * 256 + SL + 54272 ))
}

echo "== 1. the attract screen =="
step 5
shot title.png
echo "  gstate=$(get gstate)   \$D018=$("$C" -s $S mem get '$D018')  (screen \$0400 + charset \$3000; bit 0 reads 1)"
echo "  title blocks, row 3 columns 8-11: $("$C" -s $S mem get '@3,8' 4)  (160 = reverse space)"
echo "  charset really is the RAM copy: code 123 (apple) at \$3000+123*8 = $("$C" -s $S mem get '$33D8' 8)"

echo "== 2. a game starts =="
"$C" -s $S mem write seed 42 >/dev/null   # the one poke: makes the run repeatable
tap 60                                   # SPACE — a real held key at $CB
echo "  gstate=$(get gstate)  snlen=$(get snlen)  level=$(get level)  speed=$(get speed)"
echo "  head at row $(get hrow) col $(get hcol), heading $(get curdir) (3 = right)"
echo "  first apple at row $(get foodr) col $(get foodc)"

echo "== 3. eating: the snake grows and the score climbs =="
i=0
while [ $i -lt 3 ]; do
  run_to
  alive "apple $((i+1))"
  echo "  apple $((i+1)): score=$(get scdig 4)  snlen=$(get snlen)  eaten=$(get eaten)  gstate=$(get gstate)"
  i=$((i+1))
done
step 2
shot play.png

echo "== 4. the SID shadow, caught with the blip still gated on =="
run_to 1                                 # stop one cell short, already aimed
alive "the approach to the fourth apple"
"$C" -s $S break add sfxeat >/dev/null
"$C" -s $S mem write '$CB' "$LASTMK" >/dev/null
"$C" -s $S wait --break --timeout 30 >/dev/null
"$C" -s $S finish >/dev/null             # let sfxeat finish programming the voice
echo "  sidshadow (\$D400-\$D418): $(get sidshadow 25)"
echo "  voice 1 control = $(get sidshadow+4) (\$11 = triangle + gate on), volume = $(get sidshadow+24)"
shot sid.png
"$C" -s $S break clear >/dev/null
step 1

echo "== 5. level 2: faster, and the whole snake recoloured =="
while [ "$(get level)" = 1 ]; do
  run_to
  alive "a level-up apple"
  echo "  apple: score=$(get scdig 4)  eaten=$(get eaten)  level=$(get level)"
done
step 1
HR=$(get hrow); HC=$(get hcol)
echo "  level=$(get level)  speed=$(get speed) jiffies/move (was 12)  snakecol=$(get snakecol) (was 5)"
# Colour RAM is 4 bits wide: the high nybble reads back as 1s, so $FD is
# colour 13.  Mask before reporting, the way a YAML assert has to.
echo "  head colour cell \$D800+$((HR * 40 + HC)): $(( $("$C" -s $S mem get "$((55296 + HR * 40 + HC))") & 15 ))"
echo "  the TAIL's colour cell too, so recolor walked the whole ring: $(( $("$C" -s $S mem get "$(segcol "$(get tail)")") & 15 ))"
shot levelup.png

echo "== 6. game over, on the border =="
if [ "$(get curdir)" = 2 ]; then tap 9; fi          # unlock a left-heading snake
hold d $(( 38 - $(get hcol) ))                      # up against the right wall
SCORE=$(get scdig 4)
die_on 18                                           # D, straight into the border
echo "  gstate=$(get gstate) (2 = game over)  score=$SCORE  hidig=$(get hidig 4)  newhi=$(get newhi)"
echo "  sidshadow voice 3 control = $(get sidshadow+18) (\$81 = noise + gate)"
shot gameover.png

echo "== 7. a second game — the first game's score stands as HI =="
tap 60                                              # SPACE plays again
echo "  gstate=$(get gstate)  score=$(get scdig 4)  hidig=$(get hidig 4)  level=$(get level)"
run_to                                              # one apple, so the snake is
echo "  one apple in: snlen=$(get snlen)"           # long enough to bite itself
D0=$(get curdir); D1=$(cwdir $D0); D2=$(cwdir $D1); D3=$(cwdir $D2)
hold "$(dkey $D0)" 1
hold "$(dkey $D1)" 1
hold "$(dkey $D2)" 1
echo "  turning into its own body from row $(get hrow) col $(get hcol)"
die_on "$(mk $D3)"                                  # the fourth turn bites
echo "  game 2 over: gstate=$(get gstate)  score=$(get scdig 4)  hidig=$(get hidig 4)  newhi=$(get newhi)"
echo "  (game 1 scored $SCORE — it still stands)"
shot hiscore.png
"$C" -s $S screen | sed -n '9,18p'

"$C" -s $S session stop >/dev/null
echo "== done: $EV =="
