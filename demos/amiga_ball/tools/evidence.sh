#!/bin/sh
# evidence.sh -- regenerate demos/amiga_ball/evidence/ in one command.
#
#   caffeinate -dimsu sh demos/amiga_ball/tools/evidence.sh   # macOS
#   sh demos/amiga_ball/tools/evidence.sh                     # Linux
#
# `#!/bin/sh`, and run as `sh ...`, on purpose: the `C=`/`S=` helper idiom below
# relies on an unquoted `$S` splitting into two words.  zsh does NOT word-split
# unquoted parameters, so under zsh `$S` arrives as the single argument
# " ballev" and every command fails with `no session named ' ballev'` -- which
# reads as a broken session rather than a quoting bug.  All seven shipped demo
# evidence scripts are /bin/sh for this reason.
#
# `caffeinate -dimsu`, also on purpose, and macOS ONLY: a headless VICE session
# idle-throttles on a Mac nobody is touching and presents as a WEDGED emulator
# -- binary-monitor timeouts with x64sc alive at ~2% CPU.  See `docs/cli.md`
# under `c64 session start`.  Linux has no equivalent idle throttle and no
# `caffeinate` binary, so run the script bare there; the wrapper to reach for
# is `systemd-inhibit --what=sleep --`, and only if the box suspends on idle.
#
# Audio evidence is separate and costs real time (warp has to be off, so a
# capture runs at ~42 ms per frame); see SPEC.md Section 13.2.
#
# ---------------------------------------------------------------------------
# The five rules of `docs/graphics-and-sprites.md` Section 5, plus the two this
# demo had to establish for itself (SPEC.md Section 13.1 A and B).
#
# 1. One `run`, then `until tick --count N` before every capture.  `tick` is the
#    frame anchor and `mainloop` is not: the main loop free-runs, so
#    `until mainloop --count N` counts loops, not frames (SPEC.md Section 10.2).
#    Inspection never advances the machine, so the same script produces the same
#    frames every time -- `cksum evidence/*.png` is identical across runs, and a
#    PNG that churns means an unanchored capture, not an acceptable wobble.
#
# 2. Never `wait --mem/--text` straight after an `until`.  A wait polls and does
#    not resume, so after a stop it can only time out.  Nothing here waits.
#
# 3. States that would take a hundred frames of physics to reach are STAGED by
#    poking the demo's own bytes with `freeze` set (SPEC.md Section 12).
#    `ball_step` skips only the *advance* while frozen: it still derives Y from
#    `bounce_phase`, derives X16 and the shadow, and writes every sprite
#    register.  So one tick after a poke is a consistent frame.  These are the
#    same bytes `test.yaml` asserts on -- the wall and impact stagings below are
#    lifted from it verbatim -- so the evidence and the regression agree by
#    construction rather than by coincidence.
#
# 4. `c64 call` only as the final action before a capture.  Not used here at
#    all: a call's fake return address ends the run, and `freeze` reaches every
#    state this demo has to show without one.  That is also why rule 1's cksum
#    promise holds for all fifteen PNGs.
#
# 5. A capture that needs a key uses `key hold KEY --at <anchor>`.  Not
#    applicable: this demo reads no input.
#
# A. FLUSH THE SCANLINE BUFFER.  `c64 screen --png` returns the emulator's
#    rolling raster, not a re-render of video RAM: lines the beam has swept show
#    the current partial frame and lines below it show the PREVIOUS one, which
#    after a warped phase is arbitrarily stale.  `shot` therefore steps exactly
#    ONE more tick immediately before capturing.  Do not optimise it away --
#    `demos/la-galaxia/tools/evidence.sh` states this as its own rule 2, having
#    shipped a capture with boot-screen light blue below the beam.
#
# B. THE PNG HAS SQUARE PIXELS; THE C64 DOES NOT.  `c64 screen --png` writes the
#    raw NTSC raster with no aspect correction -- one PNG pixel per raster pixel
#    at --scale 1.  NTSC pixel aspect is 0.7435 (SPEC.md Section 3.1), so a ball
#    that is genuinely round on a television NECESSARILY reads as a 4:3-wide
#    ellipse in these captures, and one that looked round here would be a
#    29%-too-tall egg on the machine.  Roundness is therefore never judged by
#    eye off these PNGs; it is the measured bounding box of SPEC.md criterion
#    28 -- 96 x 72 raster pixels, being the red-checker bbox of 88 x 68 plus one
#    rim texel each side (+4 px left/right, +2 px top/bottom).  Measured
#    2026-08-14 off apex.png, contact.png, rot05.png and wall-right.png: the red
#    bbox is 88 x 68 raster px in all four, so the sphere is 96 x 72 and
#    96 x 0.7435 / 72 = 0.991.  apex.png and contact.png are evidence of
#    POSITION, not of shape.

set -e
C=".venv/bin/c64"
S="-s ballev"
SRC=demos/amiga_ball/amiga_ball.s
OUT=demos/amiga_ball/evidence

# The three areas go through a function rather than a variable: they contain
# `$`, and a variable holding `--area 'CHARS=$2000:$0800'` would be re-scanned
# by the shell as `$2` followed by `000` -- the quotes inside a variable are not
# re-parsed.  SPEC.md Section 2 fixes all three, and VARS at $4000 is what makes
# every address in Section 9 a constant a poke can name.
run_demo() {
    $C run $SRC $S \
        --area 'CHARS=$2000:$0800' \
        --area 'SPRITES=$2800:$1800' \
        --area 'VARS=$4000:$0100' >/dev/null
}

shot()  { $C until tick --count 1 --timeout 120 $S >/dev/null   # flush (rule A)
          $C screen --png "$OUT/$1.png" --scale 2 --border $S >/dev/null
          echo "  $1.png"; }
ticks() { $C until tick --count "$1" --timeout 120 $S >/dev/null; }
poke()  { a=$1; shift; $C mem write "$a" "$@" $S >/dev/null; }
g()     { $C mem get "$@" $S; }

# state -- the numeric companion to a picture.  Every visual claim in this demo
# has one, because the picture cannot be read for the byte that produced it.
# $1 is the capture name, the rest is the claim.
state() {
    n=$1; shift
    { echo "# $n.png -- $*"
      echo "#"
      echo "# Captured with the machine STOPPED at a \`tick\` anchor."
      echo "# Decoded state (SPEC.md Section 9):"
      echo "#   freeze=$(g freeze)  bounce_phase=$(g bounce_phase)  rot_frame=$(g rot_frame)  spin_dir=$(g spin_dir)"
      echo "#   ball_xi=$(g ball_xi)  ball_x16=$(g ball_x16 2)  ball_yi=$(g ball_yi)"
      echo "#   shadow_x16=$(g shadow_x16 2)  shadow_size=$(g shadow_size)"
      echo "#   last_impact=$(g last_impact)  bounce_count=$(g bounce_count)  wall_count=$(g wall_count)"
      echo "#   \$D000-\$D00B=$(g '$D000' 12)"
      echo "#   \$D010=$(g '$D010')  (\$00 while ball_xi < 184, \$2A at or above it)"
      echo "#"
      echo "# \$4000 ball_xf .. \$4019 sptr+3, in SPEC.md Section 9's order:"
      echo "#   +0  ball_xf       +1  ball_xi       +2  ball_x16 lo,hi"
      echo "#   +4  ball_vx lo,hi +6  ball_yf       +7  ball_yi"
      echo "#   +8  bounce_phase  +9  rot_frame     +10 spin_dir"
      echo "#   +11 bounce_count  +12 wall_count    +13 last_impact"
      echo "#   +14 frame_count lo,hi               +16 irq_hwm"
      echo "#   +17 irq_last      +18 shadow_x16 lo,hi"
      echo "#   +20 shadow_size   +21 freeze        +22 sptr[4]"
      $C mem read ball_xf 26 $S
      echo "#"
      echo "# \$07F8-\$07FF -- the six live sprite pointers, plus two unused:"
      echo "#   0-3 ball  = 160 + 4*rot_frame + n     (SPEC.md Section 5.4)"
      echo "#   4-5 shadow= 224 + 2*shadow_size + n   (SPEC.md Section 7)"
      echo "#   6-7 sprites 6 and 7 are disabled in \$D015 = \$3F"
      $C mem read '$07F8' 8 $S
    } > "$OUT/$n.txt"
    echo "  $n.txt"
}

mkdir -p "$OUT"
$C session stop ballev >/dev/null 2>&1 || true
$C session start --name ballev --warp --headless >/dev/null
trap '$C session stop ballev >/dev/null 2>&1 || true' EXIT
run_demo

echo "evidence:"

# --- the room, before the ball moves (SPEC.md Section 4) -------------------
# The first `tick` anchor is the initial state itself: ball_init has run and no
# frame of physics has yet.  Freezing here holds it, so `shot`'s flush tick
# derives and draws ball_init's own numbers -- ball_xi 40, bounce_phase 32 (the
# apex), rot_frame 0 -- rather than one frame past them.
ticks 1
poke freeze 1
shot room
state room "the room and the ball at ball_init's state, before any physics runs"

# --- the two ends of the bounce (SPEC.md Section 6.1) ----------------------
# Mid-field, so neither end is confused with a wall.  ball_xi 100 -> ball_x16
# 124; the ball spans 124-219 of the 24-343 visible window.
poke ball_xi 100
poke ball_xf 0
poke rot_frame 0
poke bounce_phase 32       # the table's minimum: ball_yi 54, sphere 60-131
ticks 1                    # derive: freeze skips only the ADVANCE
shot apex
state apex "the apex -- ball_yi 54, the sphere entirely above the horizon at raster 171, and the smallest shadow (size 3, 48 px)"

poke bounce_phase 0        # the table's floor: ball_yi 158, sphere 164-235
ticks 1
shot contact
state contact "floor contact -- ball_yi 158, the sphere's bottom raster at 235, the largest shadow (size 0, 96 px), and the floor's grid lines drawn OVER it (\$D01B = \$30)"

# --- three rotation phases (SPEC.md Section 5.3) ---------------------------
# Against the plain purple wall, so the checker phase is the only thing that
# changes between the three.  16 frames span the texture's 45-degree period, so
# 0, 5 and 10 are 14.06 degrees apart -- a third of a checker.
#
# bounce_phase 16 (ball_yi 80), NOT the apex: at bounce_phase 32 with the same
# X and rot_frame 0 this capture would be byte-for-byte apex.png, and two files
# with one picture between them are one piece of evidence wearing two labels.
poke bounce_phase 16
poke rot_frame 0
ticks 1
shot rot00
state rot00 "rotation frame 0 at ball_yi 80 -- pointers 160-163, and the state file for the four ball-*.png quadrant renders below"

# The four blocks the VIC actually reads at rot_frame 0, independent of where
# the ball is: sprites 0-3 are TL, TR, BL, BR of one sphere (Section 3.2).
# `sprite png` takes its colours from the live registers, so these carry the
# real palette: rim black, red checker, white checker, transparent.  Butted
# together 2x2 they are one sphere -- which is the check these four are for.
# Note that transparent and the rim are BOTH rendered black, here and on the
# machine: $D021 is black and $D025 is black, so the rim is invisible against
# the background by construction.  What it buys is that no purple wall-grid
# pixel ever touches a checker (SPEC.md Section 3.3) -- measured on apex.png,
# zero orthogonal contacts and six diagonal corner touches at the limb.
for q in '0 ball-tl' '1 ball-tr' '2 ball-bl' '3 ball-br'; do
    set -- $q
    $C sprite png "$1" -o "$OUT/$2.png" --scale 8 $S >/dev/null
    echo "  $2.png"
done

poke rot_frame 5
ticks 1
shot rot05
state rot05 "rotation frame 5 -- pointers 180-183, the checkers 14.06 degrees round from rot00"

poke rot_frame 10
ticks 1
shot rot10
state rot10 "rotation frame 10 -- pointers 200-203, 28.13 degrees round from rot00"

# --- the shadow tracks X and shrinks with height (SPEC.md Section 7) -------
# Three positions, three shadow sizes, and in all three shadow_x16 equals
# ball_x16 exactly -- no lag, because ball_step derives both from the same byte
# in the same frame.  The shadow's Y never moves: it lives on the floor plane.
poke rot_frame 0
poke ball_xi 20
poke bounce_phase 0        # h = 0   -> size 0, 96 px
ticks 1
shot shadow-1
state shadow-1 "shadow at left-of-centre, ball on the floor -- shadow_size 0, the full 96 px, shadow_x16 = ball_x16"

poke ball_xi 110
poke bounce_phase 8        # ball_yi 112, h = 46 -> size 1, 80 px
ticks 1
shot shadow-2
state shadow-2 "shadow mid-field, ball 46 rasters up -- shadow_size 1, 80 px, still shadow_x16 = ball_x16"

poke ball_xi 200
poke bounce_phase 32       # ball_yi 54, h = 104 -> size 3, 48 px
ticks 1
shot shadow-3
state shadow-3 "shadow at right-of-centre, ball at the apex -- shadow_size 3, 48 px, and \$D010 = \$2A because ball_xi >= 184"

# --- both walls, hit by the program's own reversal (Section 6.2) -----------
# Not poked into place: ball_xi is parked one step short of the bound with a
# known velocity and spin, freeze is released for exactly the tick that carries
# the reversal, and freeze goes straight back on so the flush tick cannot move
# the ball off the wall.  That is `test.yaml`'s staging for criteria 15 and 19,
# reused byte for byte.  Reading spin_dir either side of the release is the
# whole claim: the ball rolls the way it travels, so the spin reverses with it.
poke bounce_phase 8        # ball_yi 112 -- clear of both the floor and the apex
poke ball_xi 223
poke ball_xf 0
poke ball_vx '$c0' '$01'   # +1.75 px/frame
poke spin_dir 1
SPIN_BEFORE_R=$(g spin_dir)
poke freeze 0
ticks 1                    # 223 + 1.75 overshoots -> clamp, reverse, count, boing
poke freeze 1
SPIN_AFTER_R=$(g spin_dir)
shot wall-right
state wall-right "the right wall -- ball_xi clamped to 223, ball_x16 247, the ball's right edge at 343 and still fully on screen; spin_dir $SPIN_BEFORE_R before the hit and $SPIN_AFTER_R after"

poke ball_xi 0
poke ball_xf 0             # ball_vx is already negative, left by the reversal
poke bounce_phase 8
SPIN_BEFORE_L=$(g spin_dir)
poke freeze 0
ticks 1                    # 0 - 1.75 underflows to $FE -- the same branch
poke freeze 1
SPIN_AFTER_L=$(g spin_dir)
shot wall-left
state wall-left "the left wall -- ball_xi clamped to 0, ball_x16 24, the ball's left edge flush with the visible window; spin_dir $SPIN_BEFORE_L before the hit and $SPIN_AFTER_L after"

# --- the SID shadow across a floor impact (SPEC.md Section 8, 14.17-18) ----
# The SID is write-only, so sid_shadow is the only thing a stopped machine can
# be asked what the program played.  The impact is produced by ball_step's own
# wrap from bounce_phase 63 to 0 -- the same code path a free-running bounce
# takes -- not by calling sound_impact.  freeze is back on immediately, so
# nothing else can fire inside the 24-frame window and the schedule below is
# the program's own.  This is `test.yaml`'s staging for criteria 17 and 18.
poke ball_xi 100
poke bounce_phase 63
poke freeze 0
ticks 2
poke freeze 1
{ echo "# sid-impact.txt -- the SID shadow across one floor impact."
  echo "#"
  echo "# sid_shadow (\$401D, 25 bytes) mirrors \$D400-\$D418.  Every SID write in"
  echo "# the demo goes through \`sidput\`, which stores to the register and to the"
  echo "# shadow, so these bytes are proof the writes happened.  They CANNOT prove"
  echo "# the result sounds like an impact -- that is what SPEC.md Section 13.2's"
  echo "# WAV and spectrogram are for."
  echo "#"
  echo "# offset -> register, for the ones this demo uses:"
  echo "#   +0/+1  \$D400/1  voice 1 frequency lo/hi   floor = \$0D/\$07 (A2, 1805)"
  echo "#                                             wall  = \$90/\$0A (E3, 2704)"
  echo "#   +4     \$D404    voice 1 control  \$11 triangle+gate, \$10 released"
  echo "#   +5/+6  \$D405/6  voice 1 AD / SR  \$08 = attack 0, decay 8; sustain 0"
  echo "#   +7/+8  \$D407/8  voice 2 (noise) frequency lo/hi"
  echo "#   +11    \$D40B    voice 2 control  \$81 noise+gate, \$80 released"
  echo "#   +12/13 \$D40C/D  voice 2 AD / SR  \$04 = attack 0, decay 4"
  echo "#   +14..+20        voice 3 -- zero for the life of the run, an assertion"
  echo "#   +22    \$D416    filter cutoff, swept DOWN over 16 frames = the boing"
  echo "#   +23    \$D417    \$F2 resonance 15, voice 2 routed into the filter"
  echo "#   +24    \$D418    \$1F low-pass, volume 15"
  echo ""
  echo "== the floor impact (snd_timer=$(g snd_timer), snd_kind=$(g snd_kind), last_impact=$(g last_impact), bounce_count=$(g bounce_count))"
  echo "   Read at the tick anchor after the two ticks that carry the wrap, which"
  echo "   is why snd_timer is 2 and not 0: sound_step increments it AFTER writing,"
  echo "   so no stop can ever show the window's first frame from inside it.  The"
  echo "   gate-on writes below all happened on the impact tick itself."
  echo "   \$D416 cutoff = $(g 'sid_shadow+22')"
  $C mem read sid_shadow 25 $S
  CUT0=$(g 'sid_shadow+22')
  ticks 8
  echo ""
  echo "== 8 frames later (snd_timer=$(g snd_timer))"
  echo "   \$D416 cutoff = $(g 'sid_shadow+22'), down from $CUT0 -- the sweep is the"
  echo "   descending resonant low-pass over the noise burst (SPEC.md Section 8)."
  $C mem read sid_shadow 25 $S
  ticks 16
  echo ""
  echo "== 24 frames after the impact (snd_timer=$(g snd_timer), idle at 24)"
  echo "   voice 1 control = $(g 'sid_shadow+4') and voice 2 control = $(g 'sid_shadow+11'):"
  echo "   both gates released.  Sustain is 0, so the note was over long before the"
  echo "   gate fell -- which is what a struck body does."
  $C mem read sid_shadow 25 $S
} > "$OUT/sid-impact.txt"
echo "  sid-impact.txt"

echo "done -- $(ls "$OUT"/*.png | wc -l | tr -d ' ') frames, $(ls "$OUT"/*.txt | wc -l | tr -d ' ') state files"
