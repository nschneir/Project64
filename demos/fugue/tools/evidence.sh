#!/bin/sh
# evidence.sh -- re-run the deterministic proof protocol and rewrite
# demos/fugue/evidence/.  One command, same frames every time.
#
# This is #!/bin/sh on purpose: the `S="-s fugev"` idiom below relies on word
# splitting, which zsh does not do for unquoted parameter expansions.  Pasted
# into a zsh prompt these helpers pass `-s " fugev"` and the session lookup
# fails with a puzzling `no session named ' fugev'`.
#
# The five rules from docs/graphics-and-sprites.md section 5, and the sixth
# this demo needed:
#
#   1. One `run`, then `until <anchor> --count N` before every capture.
#   2. Never `wait --mem/--text` straight after an `until` -- a wait polls and
#      does not resume, so it can only time out.
#   3. Stage unreachable states by poking the program's own state bytes.
#   4. `c64 call` only as the final action before a capture.
#   5. Step ONE MORE TICK immediately before every capture: `screen --png`
#      returns the emulator's rolling scanline buffer, not a re-render.
#   6. ARM THE CHECKPOINT BEFORE `run`.  `c64 run` resumes the machine, and at
#      warp the wall-clock gap before the next command is emulated seconds:
#      `run` then `until tick --count 30` landed this demo on frame 3,774.
#      `break add tick` first, then `run`, then `wait --break` parks on frame
#      0 -- and from there `until tick --count N` IS frame N.

set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HERE/../fugue.s"
OUT="$HERE/../evidence"
AREAS="--area CHARS=\$2000:\$0800 --area SPRITES=\$2800:\$0100"
C="$HERE/../../../.venv/bin/c64"
S="-s fugev"

mkdir -p "$OUT"

shot()  { $C screen --png "$OUT/$1.png" --scale 2 --border $S >/dev/null; echo "  $1.png"; }
ticks() { $C until tick --count "$1" --timeout 240 $S >/dev/null; }
# Rule 5, built into the helper so it cannot be forgotten.
grab()  { ticks 1; shot "$1"; }

$C session stop fugev >/dev/null 2>&1 || true
$C session start --name fugev --warp --headless >/dev/null

# Rule 6: arm, then run, then park on frame 0.
$C break add tick $S >/dev/null 2>&1 || true
# shellcheck disable=SC2086
$C run "$SRC" $AREAS $S >/dev/null
$C break add tick $S >/dev/null
$C wait --break --timeout 120 $S >/dev/null
$C break clear $S >/dev/null
echo "parked at frame 0"

# `until tick --count N` from frame 0 lands on frame N, so every stop below
# is an exact frame of the program's own clock.  The musical frames come from
# the arrangement via genscore.py --shots, so this script and the reference
# scores cannot drift apart.
FRAME=0
goto() {   # goto <absolute frame>
    delta=$(( $1 - FRAME ))
    # `[ ... ] && ticks` would return non-zero when the guard fails, and
    # `set -e` would kill the script on the first shot that needs no travel.
    if [ "$delta" -gt 0 ]; then ticks "$delta"; fi
    FRAME=$1
}

# --- the staves, drawn before the music starts -------------------------
goto 60
grab staves
FRAME=$((FRAME + 1))

# --- the musical moments, each named by the arrangement ----------------
python3 "$HERE/genscore.py" --shots > /tmp/fugue-shots.$$
while read -r name frame; do
    goto "$frame"
    grab "$name"
    FRAME=$((FRAME + 1))
    # the backlight shot is the first entry, one frame in, where a glow is lit
    if [ "$name" = "entry1" ]; then
        grab backlight
        FRAME=$((FRAME + 1))
    fi
done < /tmp/fugue-shots.$$
rm -f /tmp/fugue-shots.$$

$C session stop fugev >/dev/null
echo "evidence written to $OUT"
