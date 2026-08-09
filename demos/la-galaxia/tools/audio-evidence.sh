#!/bin/sh
# audio-evidence.sh -- regenerate the five committed audio captures.
#
# Unlike the screenshot protocol these cost real time: a capture takes the
# machine off warp for its whole duration and roughly three times that in
# wall clock, and one of the five has to be flown into a running game first.
# Budget about four minutes for the set.
#
# The session runs WITHOUT --warp.  A capture clears warp for itself, but the
# staging in between is what puts the game where the window has to open, and
# a warped machine samples faster than it runs -- so the whole run stays at
# real time and pays for it once.
#
# Each capture is staged before it is armed, because the tools record what is
# playing when they are called, and nothing may drive the session while a
# window is open.  The staging bytes in sound.s exist for exactly that, and
# read zero in play:
#
#   muslead   frames of silence before the sequencer's first row, so the
#             window opens before the music rather than a phrase into it
#   muslimit  rows to play before the player stops for good, so it closes
#             after the music -- both edges in silence, every scored
#             duration whole, and no dependence on how long arming took
#   sfxpend   the effect to start, plus sfxdelay/sfxevery/sfxreps/sfxalt: an
#             effect poked in from the CLI fires during arming and is gone
#             before the window opens, so it has to be aimed instead
#
# Every capture reloads the .prg first, which is also what puts those bytes
# back to zero -- they live in the ENGINE segment and ship as zeros.
#
#   sh demos/la-galaxia/tools/audio-evidence.sh

set -e
cd "$(dirname "$0")/../../.."
C=".venv/bin/c64"
S="-s lgaud"
SRC=demos/la-galaxia/la-galaxia.s
PRG=/tmp/la-galaxia-audio.prg
LBL=/tmp/la-galaxia-audio.lbl
OUT=demos/la-galaxia/evidence/audio
DEMO=demos/la-galaxia

# music.inc and the two title scores come out of one source, so the score
# cannot drift away from the notes the C64 plays.
python3 "$DEMO/tools/genmusic.py" -o "$DEMO/music.inc" --score "$OUT" >/dev/null
$C build "$SRC" -o "$PRG" --area 'ENGINE=$4000:$6000' >/dev/null

$C session stop lgaud >/dev/null 2>&1 || true
# --warp, despite every capture needing real time.  `c64 audio capture` pins
# real time for its own window and restores the session afterwards, so the
# session's resting speed is irrelevant to the recording -- but a headless
# session STARTED at 100% with no recorder armed is the wedge documented as
# the first entry in docs/todo.md ("VICE wedges at real time with no recorder
# armed"), and it fails every time on this machine.  Starting warped steps
# around it.  Note the failure is silent: `c64 session start` prints its
# error and still exits 0, so `set -e` does not catch it and the run
# continues against a dead session.
$C session start --name lgaud --headless --warp >/dev/null
trap '$C session stop lgaud >/dev/null 2>&1 || true' EXIT

boot() {                                # boot -- load and stop on the title
    $C load "$PRG" --symbols "$LBL" $S >/dev/null
    $C until tick --count 20 --timeout 60 $S >/dev/null
}

play() {                                # play -- fly into a running stage 1
    # The tick counts are the staging, not a delay: the game is
    # deterministic from load, so 30 ticks of attract, the hidden 1 key and
    # 420 ticks put the window in the middle of stage 1's entrance with the
    # fighter alive.
    #
    # Then the formation is cleared.  With enemies alive the window also
    # picks up whatever dive whines and collisions the game raised in those
    # five seconds, and where those land moves whenever anything in the
    # game's timing moves -- so play.score.yaml would be a hostage to
    # formation.s, and it was: two runs a day apart put the loose events in
    # different places.  The effect routines under test are the same either
    # way.
    $C load "$PRG" --symbols "$LBL" $S >/dev/null
    $C until tick --count 30 --timeout 60 $S >/dev/null
    $C key hold 1 --at tick --frames 4 $S >/dev/null
    $C mem write '$CB' 64 $S >/dev/null  # the KERNAL scan is off: release it
    $C until tick --count 420 --timeout 90 $S >/dev/null
    $C mem write enemy_state $(i=0; while [ $i -lt 48 ]; do printf '0 '; i=$((i+1)); done) $S >/dev/null
}

cap() {                                 # cap <dir> <seconds> <score>
    mkdir -p "$OUT/$1"
    $C audio capture "$2" "$OUT/$1" --ref "$OUT/$3" $S
}

# --- open: the theme from row 0, both edges of the window in silence ------
boot
$C mem write --stdin $S >/dev/null <<'EOF'
mus_ord 0 0 0
mus_note 0 0 0
mus_inst 0 0 0
mus_trig 0 0 0
mus_gate 0 0 0
muslead 140
muslimit 40
musdone 0
EOF
cap open 7 title-open.score.yaml

# --- seam: rows 580-599 then 0-19, scored as one phrase across the loop ---
# mus_ord/mus_row aim the sequencer; mus_note/mus_inst/mus_gate stage the
# voices that are mid-note there, which `genmusic.py --state 580` derives.
boot
$C mem write --stdin $S >/dev/null <<'EOF'
mus_ord 24 4 0
mus_note 47 23 52
mus_inst 3 4 2
mus_trig 0 0 0
mus_gate 1 1 0
muslead 140
muslimit 40
musdone 0
EOF
cap seam 7 title-seam.score.yaml

# --- play: three shots and the three hits they caused --------------------
# $CB held on fire gives exactly ONE shot: the fighter fires on the input
# EDGE, `c64 key hold` holds $CB at one value, and the KERNAL scan is off --
# so input_state never falls and no second edge ever arrives.  The volley is
# aimed with the cue instead: sfxpend and sfxalt alternate, so each firing
# is a laser and the next, 26 frames later, is the explosion it caused.
play
$C mem write --stdin $S >/dev/null <<'EOF'
$CB 60
sfxpend 1
sfxalt 4
sfxdelay 40
sfxevery 25
sfxreps 6
EOF
cap play 5 play.score.yaml

# --- beam: the tractor-beam hum, sustained while the beam is out ---------
# enemy_flags bit 3 is EFL_BEAM and beamslot names the Flagship holding it;
# with both set the effect re-arms itself every frame, so the hum lasts as
# long as the beam instead of blipping for fourteen frames.  Voice 2 is
# sounding at both edges of this window on purpose: the claim is that every
# one of its 120 frames is a gated pulse note, alternating.
#
# Staged on the title screen and not in play, because in play it works: a
# beam deployed over the fighter captures it within a few frames, and
# SFX_CAPTURE (voice 2, priority 3) then takes the voice off the beam
# (priority 2) exactly as the rule says it should -- so a window aimed at
# the hum records the capture swoop instead.  Here the music is switched off
# and the three control registers cleared by hand, so voices 1 and 3 can be
# scored empty and the hum is the only thing in the window.
boot
$C mem write --stdin $S >/dev/null <<'EOF'
mus_on 0
$D404 0
$D40B 0
$D412 0
enemy_flags 8
beamslot 0
sfxpend 3
sfxdelay 0
sfxevery 0
sfxreps 0
EOF
cap beam 2 beam.score.yaml

# --- priority: four lasers taking voice 1 off the theme, and giving it back
# muslead and sfxdelay are both counted down once per tick by the same
# soundtick, so the gap between them is fixed however long arming takes:
# with muslead 140 the sequencer's frame 0 is tick 141, and sfxdelay 200
# puts the first laser on music frame 60, sfxevery 59 the rest 60 apart.
# The score is generated with those four frames in it, and every note after
# a seizure is the one the sequencer would have been playing had the laser
# never fired -- so a PASS is the resume half of §9's priority rule.
boot
$C mem write --stdin $S >/dev/null <<'EOF'
mus_ord 0 0 0
mus_note 0 0 0
mus_inst 0 0 0
mus_trig 0 0 0
mus_gate 0 0 0
muslead 140
muslimit 44
musdone 0
sfxpend 1
sfxdelay 200
sfxevery 59
sfxreps 4
EOF
cap priority 7 title-priority.score.yaml
