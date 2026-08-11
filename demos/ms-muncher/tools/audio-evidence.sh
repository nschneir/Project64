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
    # --strict on both branches, and on the scored branch it is the only thing
    # `play` has.  play.score.yaml is `voices: {1: []}` with voices 2 and 3
    # left unscored on purpose, and diff_score compares only the voices a score
    # lists and reads an empty list as "should be silent" -- so a silent play
    # window diffs clean, raises no anomaly, and PASSes at exit 0.  The other
    # four scores list notes, so there the diff already FAILs a silent window
    # and the flag is a second line of defence that names the cause once.
    # The no-score branch cannot fire today (all five captures have a committed
    # score) and is there for when a new capture arrives without one: with no
    # --ref there is no diff to fail on either.  Staging that missed -- a
    # hidden key that no longer reaches its act -- is exactly what produces a
    # silent window, and would land a committed report proving nothing.
    # docs/cli.md's `c64 audio capture` entry has the general rule and why the
    # flag is opt-in.
    mkdir -p "$OUT/$1"
    if [ -f "$OUT/$1.score.yaml" ]; then
        $C audio capture "$2" "$OUT/$1" --ref "$OUT/$1.score.yaml" --strict $S
    else
        $C audio capture "$2" "$OUT/$1" --strict $S
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
