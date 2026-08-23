#!/bin/sh
# audio-evidence.sh -- regenerate the two committed audio captures (SPEC.md
# 13.2, criteria 21-22).
#
# Separate from evidence.sh because these cost REAL TIME.  A capture takes the
# machine off warp for its whole window and pays roughly 42 ms of wall clock
# per frame on about 1.1 s of fixed overhead, so the two 90-frame windows here
# are about 12 s of captures inside a run of well under a minute.  The frame
# protocol next door is warped and costs nothing; putting them in one script
# would make the cheap half pay for the expensive one on every regeneration.
#
#   caffeinate -dimsu sh demos/amiga_ball/tools/audio-evidence.sh   # macOS
#   sh demos/amiga_ball/tools/audio-evidence.sh                     # Linux
#
# `caffeinate -dimsu` is not decoration, and it is a macOS remedy only.  A
# headless VICE idle-throttles on a Mac nobody is touching, and a capture that
# gets throttled part-way through its window is silently wrong rather than
# obviously broken -- it presents as a wedged emulator or as a log that is
# short.  Linux has no equivalent idle throttle and no `caffeinate` binary, so
# the run goes bare there; use `systemd-inhibit --what=sleep --` only if the
# box suspends while idle.
#
# The session runs WITHOUT --warp, unlike demos/la-galaxia's, which starts
# warped to step around a wedge it documents.  `c64 audio capture` pins real
# time for its own window either way; what a real-time session buys here is
# that the staging in between happens on the same clock the window will, so
# there is nothing to re-establish when the window opens.  If this ever wedges
# on a machine, la-galaxia's --warp is the known workaround and it does not
# change what the captures record.
#
# --- how the windows are staged -------------------------------------------
#
# Both impacts are rare events in a 1.5-second window and neither can be poked
# in from outside it: arming spends frames before frame 0, and once the window
# is open the sampling loop owns the session, so a `c64 mem write` from here
# would be queued behind the whole capture.  So the ball is FROZEN before the
# capture is armed, the state that is one frame short of the impact is poked
# in, and `--at-frame` releases the freeze inside the window:
#
#   --at-frame 12 '$4015=0'   one frame of physics: the impact
#   --at-frame 13 '$4015=1'   frozen again before it can raise another
#
# `freeze` skips only the ADVANCE (ball.s), so sound_step still runs every
# frame and the whole 20-frame gate plus its filter sweep play out inside the
# window.  Re-freezing at 13 is what makes the score a claim about the window
# rather than a hostage to it: with physics running, frame 12+64 wraps the
# bounce phase and drops a second, unscored floor impact into the tail of a
# 90-frame window.
#
# `--at-frame` takes LITERAL addresses -- it parses through the number parser,
# with no session and no label file, so `freeze=0` is refused as "not a
# number" where every other address argument in the CLI would have taken it.
# That is why VARS is an --area at a fixed base: `freeze` is $4015 by
# arrangement (SPEC.md 9), not by where the assembler happened to put it.
#
#   floor  bounce_phase 63: the next advance wraps 63 -> 0, which IS the
#          floor impact (ball.s tests the wrap, not the Y coordinate)
#   wall   ball_xi 223 with ball_vx positive: the next advance reaches 224,
#          one past the bound, and ball.s reads the sign of the velocity to
#          know it was the RIGHT wall
#
# Each window also stages the other axis away from its own impact -- the floor
# window's ball_xi is nowhere near a wall, the wall window's bounce_phase is
# nowhere near the wrap -- so exactly one impact fires and voice 1 holds
# exactly one note.

set -e
cd "$(dirname "$0")/../../.."
C=".venv/bin/c64"
S="-s ballaud"
SRC=demos/amiga_ball/amiga_ball.s
EV=demos/amiga_ball/evidence
OUT="$EV/audio"
# Single-quoted so the $ survives the assignment; unquoted below so sh splits
# it into six words.  Note that this only works under sh: zsh does not
# word-split an unquoted parameter, and the failure reads as "no session
# named ' ballaud'" rather than as a quoting problem.
AREAS='--area CHARS=$2000:$0800 --area SPRITES=$2800:$1800 --area VARS=$4000:$0100'

# The scores come from the demo's own constants, and they are written BEFORE
# the captures on purpose: a score fitted to a transcription cannot fail, and
# a check that cannot fail is not evidence (docs/cli.md, `c64 audio report`).
python3 demos/amiga_ball/tools/score.py

$C session stop ballaud >/dev/null 2>&1 || true
$C session start --name ballaud --headless >/dev/null
trap '$C session stop ballaud >/dev/null 2>&1 || true' EXIT

boot() {                                # boot -- fresh load, frozen and quiet
    $C run "$SRC" $AREAS $S >/dev/null
    $C until tick --count 2 --timeout 60 $S >/dev/null
    # snd_timer 20 rather than the idle 24: 20 is the frame sound_step drops
    # both gates, so whatever impact the free-running load was in the middle of
    # is RELEASED instead of being left gated forever under a frozen timer.
    # The six ticks after it are the schedule draining to idle, so the window
    # opens on a chip that is silent because it was told to be.
    $C mem write --stdin $S >/dev/null <<'EOF'
freeze 1
snd_timer 20
EOF
    $C until tick --count 6 --timeout 60 $S >/dev/null
}

cap() {                                 # cap <kind>
    # --strict, for the reason both other demos pass it: "the report was
    # written" is not evidence that anything played.  Here the --ref already
    # fails a silent window -- the score lists a sounding note, so an empty
    # capture diffs as "heard nothing (log ended)" -- and the flag is the
    # second line of defence for the day a score loses its note or a window
    # loses its --ref, where the reference-free reading of silence is PASS.
    mkdir -p "$OUT/$1"
    $C audio capture 1.5 "$OUT/$1" \
        --at-frame 12 '$4015=0' --at-frame 13 '$4015=1' \
        --ref "$EV/$1.score.yaml" --strict $S
}

# --- floor: the heavier body, A2 under a noise transient ------------------
boot
$C mem write --stdin $S >/dev/null <<'EOF'
bounce_phase 63
ball_xi 40
ball_xf 0
ball_vx $C0 $01
last_impact 0
EOF
cap floor

# --- wall: the harder surface, E3 and a brighter, higher-cut sweep --------
boot
$C mem write --stdin $S >/dev/null <<'EOF'
bounce_phase 0
ball_xi 223
ball_xf 0
ball_vx $C0 $01
last_impact 0
EOF
cap wall
