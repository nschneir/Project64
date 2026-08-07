#!/bin/sh
# evidence.sh -- re-run the deterministic proof protocol and rewrite evidence/.
#
# Every capture is taken with the machine STOPPED on the `tick` frame anchor.
# At warp, a screenshot of a running game is a race; `c64 until tick` parks
# the machine on the exact frame first, and inspection never advances it.
#
# States that would take minutes of play to reach are staged instead of
# waited for: the board number is poked and `newboard` called for the four
# mazes, `frighten` is called for the blue ghosts, and a ghost's state byte
# is set to GS_EYES.  Everything else -- the fruit's lap, the ghosts leaving
# the house, the score climbing -- happens because the attract demo is
# playing the real game.
#
#   sh demos/ms-muncher/tools/evidence.sh
#
# Audio evidence is separate and costs real time; see
# tools/audio-evidence.sh.

set -e
cd "$(dirname "$0")/../../.."
C=".venv/bin/c64"
S="-s mmev"
SRC=demos/ms-muncher/ms-muncher.s
OUT=demos/ms-muncher/evidence

shot() { $C screen --png "$OUT/$1.png" --scale 2 $S >/dev/null; echo "  $1.png"; }
ticks() { $C until tick --count "$1" --timeout 120 $S >/dev/null; }

mkdir -p "$OUT"
$C session stop mmev >/dev/null 2>&1 || true
$C session start --name mmev --warp --headless >/dev/null
trap '$C session stop mmev >/dev/null 2>&1 || true' EXIT

echo "evidence:"
$C run $SRC $S >/dev/null

# --- the attract screen ---------------------------------------------------
ticks 30
shot title

# --- the three intermission acts, reached with the hidden keys ------------
for a in 1 2 3; do
    $C run $SRC $S >/dev/null
    ticks 120                          # past the title's key-ignore window
    $C key hold "$a" --at tick --frames 3 $S >/dev/null
    ticks 160
    shot "act$a"
done

# --- the four mazes -------------------------------------------------------
# `c64 call` replaces the running program's control flow -- the docs are
# explicit that the run is over afterwards -- so each maze gets its own run
# and the shot is taken before anything tries to resume.
for b in 1:1 2:3 3:6 4:10; do
    m=${b%%:*}; n=${b##*:}
    $C run $SRC $S >/dev/null
    ticks 400                          # the attract demo is playing by now
    $C mem write board "$n" $S >/dev/null
    $C call newboard $S >/dev/null
    shot "maze$m"
done

# --- play: scatter, chase, frightened, eyes -------------------------------
$C run $SRC $S >/dev/null
ticks 800                              # phase 0 is the randomised opening
shot scatter
ticks 900                              # ... and phase 1 is chase
shot chase
# Frightened is staged by poking the state the energizer would have set, not
# by calling frighten -- a call would end the run and the shapes would never
# be updated.
$C mem write 'astate+1' 4 4 4 4 $S >/dev/null
$C mem write frtimer 200 1 $S >/dev/null
ticks 20
shot frightened
$C mem write 'astate+1' 5 $S >/dev/null
ticks 40
shot eyes

# --- the travelling fruit -------------------------------------------------
$C run $SRC $S >/dev/null
$C wait --mem 'fractive=1' --timeout 180 $S >/dev/null
ticks 240
shot fruit

# --- a death, a game over, and the initials screen ------------------------
$C mem write gstate 3 $S >/dev/null
$C mem write stinit 1 $S >/dev/null
ticks 40
shot death
$C mem write score 255 255 0 $S >/dev/null
$C mem write lives 1 $S >/dev/null
$C mem write gstate 5 $S >/dev/null
$C mem write stinit 1 $S >/dev/null
ticks 30
shot gameover
$C continue $S >/dev/null             # a wait polls; it does not resume
$C wait --mem 'gstate=7' --timeout 60 $S >/dev/null
$C key type AB $S >/dev/null
ticks 30
shot hiscore

# --- the SID shadow, mid-tune ---------------------------------------------
$C run $SRC $S >/dev/null
ticks 120
{
    echo "# sidshad, 25 bytes mirroring \$D400-\$D418, captured on the title"
    echo "# tune at frame 120.  The chip is write-only: these are the only"
    echo "# bytes a test can assert a sound happened at all."
    $C mem read sidshad 25 $S
} > "$OUT/sid-shadow.txt"
echo "  sid-shadow.txt"
