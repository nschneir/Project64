#!/bin/sh
# audio-evidence.sh -- capture the five audio windows the prompt asks for.
#
# Unlike the screenshot protocol these cost real time: a capture takes the
# machine off warp for its whole duration, and roughly three times that in
# wall clock.  Budget about four minutes for the set.
#
# Each capture is staged first -- driven to the title, into an act with its
# hidden key, or into play -- and only then armed, because the tools record
# what is playing when they are called.  Every tune starts with a 16-row
# silent lead-in (see mustart) so the window opens before the first note and
# the reference score can be written against the whole phrase.
#
#   sh demos/ms-muncher/tools/audio-evidence.sh

set -e
cd "$(dirname "$0")/../../.."
C=".venv/bin/c64"
S="-s mmaud"
SRC=demos/ms-muncher/ms-muncher.s
OUT=demos/ms-muncher/evidence/audio

$C session stop mmaud >/dev/null 2>&1 || true
$C session start --name mmaud --warp --headless >/dev/null
trap '$C session stop mmaud >/dev/null 2>&1 || true' EXIT

cap() {                                 # cap <name> <seconds>
    mkdir -p "$OUT/$1"
    if [ -f "$OUT/$1.score.yaml" ]; then
        $C audio capture "$2" "$OUT/$1" --ref "$OUT/$1.score.yaml" $S
    else
        $C audio capture "$2" "$OUT/$1" $S
    fi
}

# --- the title tune -------------------------------------------------------
$C run $SRC $S >/dev/null
$C until tick --count 1 --timeout 30 $S >/dev/null
cap title 8

# --- each act's music, reached with its hidden key ------------------------
for a in 1 2 3; do
    $C run $SRC $S >/dev/null
    $C until tick --count 120 --timeout 60 $S >/dev/null
    $C key hold "$a" --at tick --frames 3 $S >/dev/null
    cap "act$a" 6
done

# --- play: the siren holding against the dot-munch alternation -----------
$C run $SRC $S >/dev/null
$C wait --mem 'gstate=2' --timeout 120 $S >/dev/null
$C until tick --count 60 --timeout 60 $S >/dev/null
cap play 6
