#!/bin/sh
# audio-evidence.sh — the audio half of demos/1812's proof protocol.
#
# Five captures, one per recognizable section (PROMPT.md's audio-evidence
# paragraph), each writing the five artifacts `c64 audio capture` pins the
# names of: capture.wav, sid-log.jsonl, piano-roll.png, spectrogram.png and
# report.md.  The reference scores are generated first, from music.s's own
# note streams, by tools/genscore.py.
#
#   caffeinate -dimsu sh demos/1812/tools/audio-evidence.sh   # macOS
#   sh demos/1812/tools/audio-evidence.sh                     # Linux
#
# RUN IT DETACHED, AND ON macOS UNDER caffeinate.  A capture takes the machine
# OFF WARP for its window — under warp VICE writes a zero-frame WAV, nothing at
# all — so the five windows are 73 seconds of emulated time and about four
# minutes of wall clock, and headless VICE wedges on a user-idle Mac.  Linux
# has no equivalent idle throttle and no `caffeinate` binary: run it bare
# there, under `systemd-inhibit --what=sleep --` only if the box suspends.
#
# NOTHING ELSE MAY TOUCH THE SESSION while a window is open: the sampling loop
# owns it for the whole capture, so a second command would simply queue behind
# it.  That is also why the sequencer is rewound with `--at-frame 0` rather
# than by a poke beforehand — see below.
#
# WHY EACH CAPTURE REWINDS ITS SECTION'S STREAMS.  Arming a capture spends
# emulated frames before log frame 0, and how many is not fixed, so a window
# staged only by `until secchange` opens at an unknown tick of the section and
# no generated score could be positionally aligned to it.  Each capture
# therefore writes, at log frame 0, exactly what `loadstreams` writes at a
# section change: the three stream pointers, their rewind bases, and
# vcnt/vnote/vrel (plus `noteidx`, which `nextsec` zeroes).  Log frame f is
# then the state after section tick f + 1 whatever the arming cost, and the
# committed score passes on a re-capture instead of being fitted to one run.
# The instruments, the palette and `secframe` are untouched: the section is
# the program's own, only its streams are back at their heads.
#
# One consequence, and it is audio-only: rewinding section 3 re-fires shot 1,
# so `cannons` over-counts during THIS run.  The sixteen-shot claim is the
# visual protocol's (tools/evidence.sh), taken on a run nothing pokes.

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
C="$ROOT/.venv/bin/c64"
DEMO="$ROOT/demos/1812"
EV="$DEMO/evidence/audio"
GEN="python3 $DEMO/tools/genscore.py"
S=aud1812
FAILED=0

mkdir -p "$EV"
echo "== generating the reference scores from music.s ====================="
$GEN --out "$EV" || exit 1

echo
echo "== booting the session (NTSC, warped, headless) ====================="
"$C" -s $S session stop 2>/dev/null || true
"$C" session start --name $S --warp --headless >/dev/null
"$C" -s $S run "$DEMO/1812.s" >/dev/null
"$C" -s $S until mainloop --timeout 120 >/dev/null

# cap NAME FRAMES — capture NAME's window, then report where it landed.
# `seconds` is emulated time and the tool rounds it by the machine's 60 fps,
# so the frame count is passed as its own quotient and comes back exact.
cap () {
  name=$1
  secs=$(python3 -c "print($2 / 60.0)")
  echo
  echo "== $name: $2 frames =================================================="
  # Not `set -e`: a FAIL exits 1, and one section's diff must not cost the
  # other four their windows.  --strict makes a silent capture an error too.
  if "$C" -s $S audio capture "$secs" "$EV/$name" \
        --ref "$EV/$name.score.yaml" \
        --at-frame 0 "$($GEN --pokes "$name")" --strict; then
    echo "  $name: PASS"
  else
    echo "  $name: capture exited $? — see $EV/$name/report.md"
    FAILED=$((FAILED + 1))
  fi
}

sec () { "$C" -s $S until secchange --count 1 --timeout 300 >/dev/null; }

cap hymn 1089
sec
cap marseillaise 892
sec
cap battle 599
sec
cap cannon 905
sec
cap finale 900

"$C" -s $S session stop >/dev/null 2>&1 || true

echo
echo "== done: $EV ($FAILED of 5 did not pass) ============================"
exit $FAILED
