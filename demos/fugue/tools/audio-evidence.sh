#!/bin/sh
# audio-evidence.sh -- capture the four structural moments and score each one
# against the arrangement's own note data.
#
# Four windows: the three exposition entries, and the closing pedal point with
# its filter sweep.  Each writes the five artifacts `c64 audio capture` always
# writes -- capture.wav, sid-log.jsonl, piano-roll.png, spectrogram.png,
# report.md -- into evidence/audio/<name>/.
#
# CAPTURE ONCE, SCORE MANY TIMES.  A capture pins real time and costs several
# times its emulated length in wall clock; `c64 audio report` is pure analysis
# on the log already written and costs a fraction of a second.  So each window
# is captured once WITHOUT --ref, and the score is diffed against that same log
# afterwards.  Re-capturing to test a score change buys nothing.
#
# That ordering also solves the window-placement problem.  Arming a capture
# spends emulated frames before log frame 0, and how many is a property of the
# host, not of the program -- so the score's start frame is not knowable until
# the capture reports its own `lead_in_frames`.  Park, capture, read the
# number, generate the score at parked + lead_in, then report.
#
# `--strict` on the report is the point of the whole file: "the report was
# written" is not evidence that anything played.  A window that opened on
# silence passes every check by having nothing to disagree with, and --strict
# turns that into exit 1.

set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HERE/../fugue.s"
OUT="$HERE/../evidence/audio"
AREAS="--area CHARS=\$2000:\$0800 --area SPRITES=\$2800:\$0100"
C="$HERE/../../../.venv/bin/c64"
S="-s fugaud"

mkdir -p "$OUT"

frame_now() {
    set -- $($C mem get frame 2 $S)
    echo $(( $1 + 256 * $2 ))
}

$C session stop fugaud >/dev/null 2>&1 || true
$C session start --name fugaud --warp --headless >/dev/null

# EVERY WINDOW GETS A FRESH RUN.  A capture leaves the machine RUNNING, and at
# warp the gap before the next command is emulated seconds -- so reading
# `frame` after a capture and treating it as the park point is wrong by an
# unbounded amount.  The first version did that and window 2 opened 215 frames
# from where it thought, ten sixteenths of music.  Restarting means the
# machine is STOPPED at an exact frame when each capture arms.
python3 "$HERE/genscore.py" --list | while read -r name start frames rest; do
    START=${start#start_frame=}
    FRAMES=${frames#frames=}
    SECS=$(( FRAMES / 60 ))
    DIR="$OUT/$name"
    mkdir -p "$DIR"

    # shellcheck disable=SC2086
    $C run "$SRC" $AREAS $S >/dev/null
    $C break add tick $S >/dev/null
    $C wait --break --timeout 120 $S >/dev/null
    $C break clear $S >/dev/null
    $C until tick --count "$START" --timeout 900 $S >/dev/null
    PARKED=$(frame_now)
    echo "$name: parked at frame $PARKED, capturing ${SECS}s (real time)"

    # No --ref here on purpose: the log is the evidence, and the score cannot
    # be written until lead_in_frames is known.
    # lead_in_frames comes back NULL here, and that is expected rather than a
    # fault: it is measured from the KERNAL jiffy at $A0-$A2, and this demo
    # owns the interrupt and runs no ROM code inside it, so the jiffy does not
    # count.  Null means "not measured", never "no lead-in".  Fall back to the
    # measured typical, 155 frames -- it only has to get the alignment search
    # within half of the pulse-width sweep's 256-frame period, and the search
    # then pins the true start exactly.
    LEAD=$($C audio capture "$SECS" "$DIR" --strict --json $S \
           | python3 -c 'import json,sys; print(json.load(sys.stdin).get("lead_in_frames") or 155)')
    echo "  lead_in_frames = $LEAD"

    # lead_in_frames is accurate to about a frame, which is fine for a window
    # that opens in silence and not fine for one that opens mid-phrase.  The
    # log's own pulse-width sweep pins the true start exactly; --align-log
    # uses it, and uses no pitch information, so it cannot launder a wrong
    # note into a passing score.
    python3 "$HERE/genscore.py" --start-frame $(( PARKED + LEAD )) \
            --align-log "$DIR/sid-log.jsonl" \
            --frames "$FRAMES" -o "$DIR/score.yaml"

    $C audio report "$DIR/sid-log.jsonl" "$DIR" \
       --wav "$DIR/capture.wav" --ref "$DIR/score.yaml" --strict >/dev/null
    echo "  $name: PASS"
done

$C session stop fugaud >/dev/null
echo "audio evidence written to $OUT"
