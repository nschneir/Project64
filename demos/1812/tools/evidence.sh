#!/bin/sh
# evidence.sh — the deterministic proof protocol for demos/1812.
#
# Every capture but three is taken with the machine STOPPED at a `c64 until`
# label: a screenshot of a running machine is a race, and at warp the frame you
# wanted is emulated seconds gone.  Nothing here is staged — the pictures are
# what the state bytes printed beside them produced.
#
# The three exceptions are section 9's rot-a/b/c, which follow a `c64 call`
# and cannot be anchored: the call's fake return address has replaced the
# program's control flow, so there is no label left to stop on.  Those shots
# are torn at the raster split and their BYTES CHURN between runs while their
# content does not — measured 2026-08-12, three replays, byte-identical bitmap
# (lit=6105 checksum=1c454f03) and three different PNGs.  The vertex and angle
# numbers printed beside them are what carries section 9's claim, not the file
# hashes.  See docs/graphics-and-sprites.md section 5 (the note after the rules
# table) and section 6 for why no primitive fixes this yet.
#
# The figures below go to stdout and nowhere else, and README.md/AUDIT.md quote
# them — so keep the run log, or the proof is gone when the terminal scrolls:
#
#   sh demos/1812/tools/evidence.sh 2>&1 | tee /tmp/1812-evidence.log
#
# Re-runnable: it stops and restarts its own session.  Takes a few minutes;
# the whole 10,200-frame piece is played three times.

set -e
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
C="$ROOT/.venv/bin/c64"
DEMO="$ROOT/demos/1812"
EV="$DEMO/evidence"
LIT="python3 $DEMO/tools/litcount.py"
S=ev1812

# The two intermediates of section 7 used to be /tmp/1812-early.txt and
# /tmp/1812-late.json at fixed paths, so two runs — two checkouts, or one
# checkout and a second demo copying this pattern — silently read each other's
# persistence sample.  They are per-run now, and passed to the heredoc as
# arguments rather than hardcoded inside it.
TMPD=$(mktemp -d "${TMPDIR:-/tmp}/1812-evidence.XXXXXX")
trap 'rm -rf "$TMPD"' EXIT INT TERM
EARLY="$TMPD/early.txt"
LATE="$TMPD/late.json"

mkdir -p "$EV"
"$C" -s $S session stop 2>/dev/null || true
"$C" session start --name $S --warp --headless >/dev/null

shot () { "$C" -s $S screen --png "$EV/$1" --scale 2 --border >/dev/null; echo "  captured $1"; }
get  () { "$C" -s $S mem get "$1" "${2:-1}" | tr -d '\n'; }
step () { "$C" -s $S until seqtick --count "$1" --timeout 300 >/dev/null; }
sec  () { "$C" -s $S until secchange --count 1 --timeout 300 >/dev/null; }
lit  () { "$C" -s $S mem read '$2000' 8000 --json | $LIT; }

echo "===================================================================="
echo " 1812 — deterministic proof protocol"
echo "===================================================================="
"$C" -s $S run "$DEMO/1812.s" >/dev/null

echo
echo "== 1. the mode registers (SPEC.md 2.1) =============================="
"$C" -s $S until mainloop >/dev/null
echo "  \$D011=$("$C" -s $S mem get '$D011')  (& \$7F must be \$3B = 59)"
echo "  \$D016=$("$C" -s $S mem get '$D016')  (& \$1F must be \$18 = 24)"
echo "  \$D018=$("$C" -s $S mem get '$D018')  (& \$FE must be \$18 = 24)"
echo "  \$D020/\$D021=$("$C" -s $S mem get '$D020' 2)  (& \$0F must be 0)"

echo
echo "== 2. the canvas before the first shape ============================="
"$C" -s $S until drawshape --count 1 --timeout 120 >/dev/null
echo "  at the entry to the FIRST drawshape: $(lit)"
shot blank.png

echo
echo "== 3. one shape, and the bytes that made it ========================="
"$C" -s $S until shapedone --count 1 --timeout 120 >/dev/null
echo "  lstype=$(get lstype) lssize=$(get lssize) lsx=$(get lsx) lsy=$(get lsy)"
echo "  lsangle=$(get lsangle) lspat=$(get lspat) lsink=$(get lsink) lsbytes=$(get lsbytes 2)"
echo "  shapes=$(get shapes 2)   $(lit)"
shot first-shape.png

echo
echo "== 4. the canvas at the end of each section ========================="
for n in 0 1 2 3; do
  sec
  echo "  end of section $n: frames=$(get frames 2) shapes=$(get shapes 2) dropped=$(get dropped)"
  echo "                     $(lit)"
  shot "sec$n.png"
  if [ "$n" = "3" ]; then
    # A7 is `cannons == 16` at the END of section 3, and the single shot the
    # cannon block below samples is not that claim.  This stop is the fourth
    # `secchange` — the top of nextsec at the end of section 3, before
    # `inc section` — so it is the last frame on which the counter can be
    # read as the section's own total.
    echo "                     cannons=$(get cannons) at the end of section 3 (A7 wants 16)"
  fi
  if [ "$n" = "0" ]; then
    "$C" -s $S mem read '$2000' 8000 --json | $LIT --sample 64 > "$EARLY"
    echo "  sampled 64 lit bitmap addresses for the persistence check"
  fi
  if [ "$n" = "2" ]; then
    echo
    echo "== 5. a cannon shot: the flash and the SID shadow =================="
    "$C" -s $S until cannonfire --count 1 --timeout 120 >/dev/null
    step 1
    echo "  cannons=$(get cannons) flash=$(get flash)   (the FIRST shot; A7's"
    echo "                                       count of 16 is read at the end"
    echo "                                       of the section, in 4. above)"
    echo "  \$D020/\$D021 during the flash = $("$C" -s $S mem get '$D020' 2)  (& \$0F must be 1)"
    echo "  sidshadow \$D400-\$D418 mid-cannon:"
    echo "    $(get sidshadow 25)"
    echo "    voice 3 control = $(get sidshadow+18) (bit 7 noise + bit 0 gate = \$81 = 129)"
    echo "    filter routing  = $(get sidshadow+23) (bit 2 routes voice 3)"
    echo "    mode + volume   = $(get sidshadow+24) (bit 4 low-pass, volume 15)"
    shot cannon.png
    step 8
    echo "  eight frames later \$D020/\$D021 = $("$C" -s $S mem get '$D020' 2)  (back to black)"
  fi
done

sec
echo "  end of section 4: frames=$(get frames 2) shapes=$(get shapes 2) dropped=$(get dropped)"
echo "                    $(lit)"
echo "  sidshadow mid-finale (voice 3 control = \$14 ring + triangle):"
echo "    $(get sidshadow 25)"
shot sec4.png

echo
echo "== 6. the finished canvas, held ====================================="
step 2
echo "  section=$(get section) frames=$(get frames 2) shapes=$(get shapes 2) dropped=$(get dropped)"
echo "  typeseen=$(get typeseen 2) (must be \$03FF = 255 3)  patseen=$(get patseen) (must be 255)"
echo "  maxcross=$(get maxcross) (the MAXX ceiling is 8)"
echo "  SID volume shadow = $(get sidshadow+24) (must be 0 — the piece has ended)"
SHAPES_AT_END=$(get shapes 2)
shot final.png

echo
echo "== 7. nothing is ever cleared ======================================="
"$C" -s $S mem read '$2000' 8000 --json > "$LATE"
python3 - "$EARLY" "$LATE" <<'PY'
import json, sys
early_path, late_path = sys.argv[1], sys.argv[2]
late = json.load(open(late_path))['bytes']
still = tot = 0
for line in open(early_path):
    line = line.strip()
    if not line:
        continue
    addr, val = line.split('=')
    i = int(addr[1:], 16) - 0x2000
    ev = int(val, 16)
    tot += 1
    still += all(((late[i] >> s) & 3) != 0 for s in (0, 2, 4, 6) if ((ev >> s) & 3) != 0)
print(f"  of {tot} bitmap addresses lit at the end of section 0, {still} are still lit")
print("  at frame 10201 — every pixel the hymn painted survived the whole piece.")
PY

echo
echo "== 8. the hold, and the restart key ================================="
step 120
echo "  120 frames into the hold: shapes=$(get shapes 2) (unchanged from $SHAPES_AT_END)"
echo "  rng and seed before the restart = $(get rng 2) / $(get seed 2)"
# The key goes in with `key hold`, not a bare poke of $CB: the KERNAL's
# keyboard scan runs later in the same interrupt and puts 64 back, so a poke
# made while stopped inside the wedge is gone before mainloop ever reads it.
# `key hold` re-pokes the matrix code at the anchor, which is how a player
# actually holds a key.
"$C" -s $S until mainloop >/dev/null
"$C" -s $S key hold space --at mainloop --frames 3 --timeout 60 >/dev/null
echo "  after the keypress:  shapes=$(get shapes 2)  section=$(get section)"
echo "  rng and seed after   = $(get rng 2) / $(get seed 2)  (the seed is mixed with the jiffy clock)"
echo "  first 32 bitmap bytes: $("$C" -s $S mem get '$2000' 32)"

echo
echo "== 9. rotation is real geometry ====================================="
echo "  the same shape type at three angles, drawn on a blank canvas."
"$C" -s $S run "$DEMO/1812.s" >/dev/null
"$C" -s $S until mainloop >/dev/null
i=0
for ang in 0 48 96; do
  "$C" -s $S mem write sh_type 1 >/dev/null      # the rectangle: a rotated
  "$C" -s $S mem write sh_size 80 >/dev/null     # square must read as a diamond
  "$C" -s $S mem write sh_cx 40 >/dev/null
  "$C" -s $S mem write sh_cy 100 >/dev/null
  "$C" -s $S mem write sh_pat 0 >/dev/null
  "$C" -s $S mem write sh_ink 3 >/dev/null
  "$C" -s $S mem write sh_angle $ang >/dev/null
  "$C" -s $S call drawshape >/dev/null
  echo "  angle $ang: lsangle=$(get lsangle) vertices x=$(get vxl 4) y=$(get vyl 4)"
  case $i in
    0) shot rot-a.png ;;
    1) shot rot-b.png ;;
    2) shot rot-c.png ;;
  esac
  i=$((i + 1))
  "$C" -s $S run "$DEMO/1812.s" >/dev/null
  "$C" -s $S until mainloop >/dev/null
done

echo
echo "== 10. the same seed paints the same canvas ========================="
echo "  Anchored on a SHAPE boundary, not a frame: a frame boundary can fall"
echo "  inside a half-painted shape, and then the two passes are compared at"
echo "  different points of the same sequence rather than at the same one."
for seedpair in "18:12" "99:77"; do
  hi=${seedpair%%:*}; lo=${seedpair##*:}
  for pass in 1 2; do
    "$C" -s $S session stop >/dev/null 2>&1 || true
    "$C" session start --name $S --warp --headless >/dev/null
    "$C" -s $S load "$DEMO/1812.prg" --no-run --symbols "$DEMO/1812.lbl" >/dev/null
    # Wait for the autostart to finish before touching the keyboard: typing
    # RUN into the buffer while autostart is still using it loses the keys,
    # and the program then never starts at all.
    "$C" -s $S wait --idle --timeout 60 >/dev/null
    "$C" -s $S mem write seed "\$$lo" "\$$hi" >/dev/null
    "$C" -s $S key type "run
" >/dev/null
    "$C" -s $S until shapedone --count 400 --timeout 300 >/dev/null
    # ALL SEVEN last-shape bytes, which is what A9 claims: lstype/lsangle/lspat
    # alone left lssize, lsx, lsy and lsink unprinted, so the log did not show
    # what the criterion says it shows.
    echo "  seed \$$hi$lo pass $pass @400 shapes: frames=$(get frames 2) rng=$(get rng 2)  $(lit)"
    echo "    last shape: lstype=$(get lstype) lssize=$(get lssize) lsx=$(get lsx) \
lsy=$(get lsy) lsangle=$(get lsangle) lspat=$(get lspat) lsink=$(get lsink)"
  done
done

"$C" -s $S session stop >/dev/null
echo
echo "== done: $EV ======================================================="
