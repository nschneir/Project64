# Amiga Ball — the 1984 Boing Ball, on VIC-II sprites

Using the c64 CLI (see skills/c64-development/SKILL.md, the 6502-assembly
skill, and docs/cli.md), build a Commodore 64 demo in pure 6502 assembly
that replicates the Amiga **Boing Ball** — the checkered sphere Commodore
bounced across a purple wire grid at CES in 1984 — as faithfully as the
VIC-II and the SID allow. Everything for this demo lives in
`demos/amiga_ball/`.

The interesting part of this brief is the *as the hardware allows*. The
Amiga drew a shaded, texture-mapped sphere into a bitmap every frame; the
C64 cannot, and a demo that tries will drop frames and look worse than one
that plays to the machine's strengths. So the ball is **hardware sprites**,
the rotation is **precomputed frames** rather than runtime geometry, and
the spec has to say — with arithmetic, not adjectives — what that trade
costs and what it buys. Where you deviate from the Amiga original, say so
in `SPEC.md` and say why the deviation is the better C64 demo.

**Work in three phases, in this order — do not start coding at phase 3.**

1. **Spec.** Use the `superpowers:brainstorming` skill to settle the open
   design questions with me, then write `demos/amiga_ball/SPEC.md`: the
   VIC bank and memory map, the ball's construction and how many rotation
   frames it has, the sphere-texture math the generator uses, the palette
   and what each of the three sprite colors is *for*, the room (grid, floor,
   horizon) and how it is drawn, the bounce and travel tables with the
   numbers in them, the shadow's rule, the impact sound's registers, the
   observable state bytes (every signal listed under **Make it observable**
   below, each with the address and label you picked for it), and the
   acceptance criteria — each one written as an observation a stopped
   machine can be read for, not as an adjective. That list is what the
   build gets judged against, so it has to cover everything this prompt
   asks the demo to be, the audio evidence included, even where the proof
   is a capture rather than a stopped machine: a criterion that lives only
   in this prompt and never reaches your own PASS list is the one that
   quietly never gets met. The spec states *what* and *why*, with the
   hardware facts (register values, addresses, byte counts, frame budgets)
   pinned down and cited to the reference files below.
2. **Plan.** Use the `superpowers:writing-plans` skill to turn the spec into
   `demos/amiga_ball/PLAN.md` — ordered, independently verifiable steps,
   each with the test or observation that proves it. A ball on screen
   early: one static sprite frame in the right place beats a perfect
   generator with nothing to look at.
3. **Build.** Execute the plan (`superpowers:executing-plans`,
   `superpowers:test-driven-development`), keeping the source in
   `demos/amiga_ball/`. A step is done when the observation the plan named
   for it is read back off the running machine — not when the code
   assembles — and the build is done when every acceptance criterion in
   `SPEC.md` passes there, with the evidence listed below. Update the plan
   as the running machine corrects you.

**Skills and references to use — read these before writing the spec:**

- `skills/c64-development/SKILL.md` — the write→run→observe→debug loop, the
  stopped-state discipline, sessions (`--warp --headless` for automation),
  and how sprites are observed (`c64 sprite status`/`show`/`png`, never
  `c64 screen` text). `docs/cli.md` is the full command reference; every
  command takes `--json`.
- `skills/c64-development/references/hardware.md` — the sprite registers
  (`$D000`-`$D02E`, the `$D010` X-MSB, the `$D017`/`$D01D` expansion bits,
  `$D01C` multicolor, `$D01B` priority), the fixed sprite-vs-sprite
  priority order, the multicolor bit-pair → color mapping, `$D018`'s
  bit-fields, the raster-interrupt sequence, and the whole SID register
  map with the envelope-rate table.
- `skills/c64-development/references/memory-maps.md` — what the VIC can see
  from bank 0, and the trap that matters here: the character ROM's **4 KB**
  image covers *two* of the eight charset bases, so `$1000` **and** `$1800`
  are unusable for a RAM charset and RAM written there is invisible to the
  chip. Sprite blocks and a RAM charset both have to live somewhere else in
  `$0000-$3FFF`.
- `skills/c64-development/references/zero-page.md` — which zero-page bytes
  the IRQ handler may use.
- `skills/c64-development/references/cookbook.md` — working recipes to start
  from rather than reinvent: the IRQ wedge, sprite setup and movement, the
  custom character set copy, and the SID beep.
- `skills/6502-assembly/SKILL.md` — the `$0801` load address, the BASIC SYS
  stub, ca65 segments, `--area` for fixed-address data, and the gotchas
  (short-branch range, carry discipline) that bite as the program grows.
- `skills/6502-debugging/SKILL.md` — when it misbehaves, follow the
  symptom-indexed procedure (starting with rule zero: prove you are
  debugging the binary you think you are) instead of guessing from source.
  `superpowers:systematic-debugging` for the surrounding discipline.
- `docs/graphics-and-sprites.md` — **policy, not a tutorial**: sprites are
  first-class here, graphic data is authored as commented `.byte` rows in
  the source (no binary blobs, no committed source images), tests may
  assert memory and registers but never PNG pixels, and `evidence/` has a
  capture convention with five rules an evidence script has to follow.
  Read it before you design the proof protocol, not after.

## The demo

**The ball.** A 2×2 grid of hardware sprites — four sprites, moved as one
object — carrying a red-and-white checkered sphere. All four are
**multicolor** (`$D01C`), which halves horizontal resolution to 12 pixel
pairs per sprite and is what makes the checkers affordable. Say in the spec
whether you expand the ball (`$D017`/`$D01D`) and what that does to its
aspect ratio: a sphere has to read as *round*, and 320×200 pixels are not
square, so the width and height you end up with is arithmetic to show, not
a number to guess. The three sprite colors are red (`$02`), white (`$01`)
and one more that is yours to spend — the Amiga sphere is shaded, and the
obvious C64 answers are a dark rim that keeps the silhouette off the
background or a third checker tone that fakes curvature. State which
gesture you bought with it.

**Rotation.** The ball spins about a vertical axis as it travels, exactly
as the original does, and the spin **reverses when it hits a side wall**.
The rotation is real spherical texture mapping, done **once, ahead of
time**, by a generator in `demos/amiga_ball/tools/`: for each frame, each
sprite pixel is a ray into a sphere, the hit point is converted to
latitude/longitude, and the checker parity at that longitude *plus the
frame's rotation offset* decides the color. Commit the generated `.byte`
rows, not the image and not the generator's output as a blob. The frame
count is a memory decision — each frame is four 64-byte sprite blocks, and
the whole set has to sit inside the VIC's 16 KB bank alongside the charset
— so state the count, the bytes, and what is left over. Switching frames
must cost only the four **sprite pointers**; copying 252 bytes into a fixed
block every frame is the expensive way to do the same thing, and the spec
should say which you chose and why.

**The room.** Background and grid in the spirit of the original: the Amiga's
was a purple wire grid, and the C64 palette will not match it exactly, so
pick a background/grid pair from the sixteen colors and justify it. Draw the
grid with a **custom character set** (screen matrix + `$D018`), not by
plotting into a bitmap — a demo whose moving parts are sprites has no
business spending 8 KB and a frame budget on a static backdrop. The floor
band at the bottom is where the ball lands and where the shadow lives, so
give it a horizon and give it perspective: a floor whose grid spacing does
not change with distance is a wall lying down. Say in the spec how the wall
grid, the horizon and the floor rows divide up the 25 text rows.

**Physics.** Vertical motion is table-driven: a bounce table generated by
the same tools script and indexed by a phase counter, so frame *N* of a
bounce has an exact, documented Y. State whether the table is parabolic
(free fall, what a real ball does) or sinusoidal (what a cheap bounce loop
does) and defend the choice — they look different at the apex, which is
where the eye spends the most time. Horizontal motion is a constant-velocity
sweep in 8.8 fixed point that reverses at the left and right screen
boundaries. The ball may run partly off the screen edges only if you decide
that deliberately and say so; the X-MSB (`$D010`) has to be right either
way, and a sprite whose MSB is stale is a ball that teleports across the
screen.

**The shadow.** A dark ellipse on the floor that tracks the ball's X. It is
not the ball's silhouette — it is the ball's *contact*, so it belongs on the
floor plane, and the spec should say what it does as the ball rises (nothing,
shrink, or fade) and why that reads. Use the sprites you have left; the ball
uses four of eight, and per-scanline sprite budget is not a constraint you
can reach here. Decide its `$D01B` priority deliberately: a shadow the grid
lines run *over* sits on the floor, and a shadow that covers them floats
above it.

**The sound.** A "boing" through the SID on every impact — floor and walls
both, with the two distinguishable. The Amiga played a digitized sample; the
SID has three oscillators and a filter, so this is a *synthesis* problem, and
the spec should describe the sound as a physical gesture before it describes
it as nybbles: a struck body has a transient (fast, bright, inharmonic), a
pitched thump under it, and a decay. Voice 1 carries the thump. Whatever
else you use — a noise transient through the low-pass with a downward cutoff
sweep is the obvious one, ring modulation is another — say what it imitates.
The floor thump should be lower than the wall thump; a ball that makes the
same sound off a wall as off the ground is a ball with no mass.
**Shadow every SID write in RAM** — the SID is write-only, and the shadow
bytes are the only evidence a stopped machine can give you that sound
happened: necessary, and not sufficient.

**Structure.** A BASIC stub so the program starts from `RUN` (the standard
skeleton in the 6502-assembly skill emits `10 SYS 2061` for a 12-byte stub —
use the layout that skill documents and say in the spec which entry address
your stub actually names, rather than copying a `SYS` line from elsewhere
and hoping the arithmetic agrees). One **raster interrupt** per frame
through the `$0314`/`$0315` vector, acknowledged at `$D019`, doing the whole
per-frame job: physics, sprite positions and pointers, shadow, sound. The
main loop below it should have nothing to do but prove it is still alive.
The code is **modular and commented to the standard this repo already
holds** — comments state contracts, hardware quirks and non-obvious *why*,
and every claim in one carries the same evidence burden as a finding.
Explain the sprite grouping arithmetic, the pointer math (`block =
address / 64`), the memory map, the raster timing, and every SID register
you write.

## Make it observable

Per the graphics policy, a demo whose whole output is pixels must publish
bytes. Expose, at documented, labeled addresses: the ball's 8.8 X and Y, the
bounce phase index, the rotation frame index, the spin direction, a bounce
counter, a wall-hit counter, the last impact's kind, a frame counter, the
per-frame IRQ cost (a high-water mark the program keeps — a sampler is the
wrong instrument for a per-frame quantity, and `docs/graphics-and-sprites.md`
§4 has the worked case), and the SID shadow block. Record each address in
`SPEC.md` and export it as a label, so tests and `c64 until` name the signal
rather than hard-coding a number that drifts on the next build.

Write `demos/amiga_ball/test.yaml` for `c64 test run` that asserts, at
minimum: the mode and memory registers (`$D011`, `$D016`, `$D018`, `$D020`,
`$D021` — masked, they are 4-bit); the sprite configuration (`$D015`,
`$D01C`, `$D017`/`$D01D`, `$D01B`, `$D025`/`$D026`, the four ball colors,
and the sprite pointers); that the four ball sprites keep their 2×2 offsets
from each other as the ball moves; that the X-MSB agrees with the 16-bit X;
that Y traverses the bounce table and returns to the floor; that the bounce
and wall counters climb; that the rotation frame index cycles and that its
direction byte flips at a wall; that the shadow's X tracks the ball's; and
that the SID shadow shows a gated voice on the frame of an impact and a
released one after it. Never PNG pixels.

## Performance rules

The whole per-frame job is a fixed cost — no allocation, no search, no
variable-length loop that depends on the ball's position — so it should be
measurable and stable. Measure it (`c64 profile`, and the program's own
high-water mark) rather than watching for tearing, and put the number in
the spec. Nothing from ROM in the interrupt. The interrupt must finish
inside a frame with margin: state the margin.

## The improvement loop

A first build that bounces a ball is the *start* of this demo, not the end.
From there, work in explicit numbered iterations, each one a full cycle:

1. **Evaluate** — run the demo deterministically (see the proof protocol
   below) and audit it against every bullet of your own `SPEC.md`, marking
   each PASS or FAIL with evidence from the running machine, never from
   reading the source.
2. **Review** — do a detailed code review of the current build: the IRQ
   handler's cost, the generator's math, dead code and slack removed — then
   judge the result the way a viewer would, and say whether it actually
   looks like the Boing Ball and whether the impact actually sounds like a
   ball hitting something. That second judgment has to come off captures of
   the running machine (the frames and the WAV below), because shadow bytes
   prove only that writes happened and cannot tell you how a sound reads; an
   iteration whose review has to write "I cannot hear this" has not done this
   step.
3. **Improve** — fix every FAIL and act on every review finding.
4. **Re-verify** — prove each fix on the running machine before counting it
   done.

Log each iteration in `demos/amiga_ball/AUDIT.md` so progress is visible, and
keep looping until an iteration ends with every spec bullet PASS and a review
that finds nothing worth fixing. Use
`superpowers:verification-before-completion` before any claim that it works.

## Prove it deterministically

Run under `--warp --headless`, anchor every observation on a `c64 until` stop
at a labeled point (the IRQ tick, the impact routine), and read memory and
registers between stops. Show me: the room before the ball moves; the ball at
the apex and at floor contact, with the state bytes that put it there beside
each frame; the same ball at three different rotation frames, with the frame
index and the four sprite pointers that produced them; the ball at both side
walls, with the spin-direction byte before and after; the shadow's X against
the ball's X at three positions; and the SID shadow read on the frame of a
floor impact and again eight frames later.

Keep the pictures: every visual claim above is captured as a named PNG under
`demos/amiga_ball/evidence/` per `docs/graphics-and-sprites.md`
(`c64 screen --png … --scale 2 --border`), taken while the machine is
*stopped* at a `c64 until` label — never staged, never drawn by hand — and
committed with the demo rather than deleted after the run. Add
`c64 sprite png` renders of the ball's four blocks at one rotation frame:
that is the one instrument that shows the shape the VIC is actually reading,
independent of where the ball happens to be. Ship
`demos/amiga_ball/tools/evidence.sh` that regenerates all of it in one
command, following the five rules in §5 of the graphics policy.

## Audio evidence

Shadow bytes prove the writes happened; they cannot tell you whether the
impact sounds like an impact. Capture it with `c64 audio capture` (`c64 audio
capture` from the shell, `c64_audio_capture` over MCP) and commit its five
artifacts — `capture.wav`, `sid-log.jsonl`, `piano-roll.png`,
`spectrogram.png`, `report.md` — under `demos/amiga_ball/evidence/audio/`:
one window covering a floor impact and one covering a wall impact, long
enough to carry the decay. Captures run **with warp off, in real time**, so
budget wall clock rather than emulated seconds. Write the reference score
from your own impact schedule — the bounce table says exactly which frame
each impact lands on, so the score is generated, not fitted — and the report
must pass. Then read the artifacts for what each one can settle: the piano
roll for which voices gate and when, the spectrogram for what the notes
cannot show — the noise transient and the filter's downward sweep. The
maintainer's listen of `capture.wav` is the final gate on whether it sounds
like a boing; `skills/c64-development/references/audio-verification.md` has
the method.

## Ship it

When everything passes, package the demo so anyone with stock VICE can run
it: `c64 package` your source into `demos/amiga_ball/amiga_ball.d64` with
`--title "AMIGA BALL"` (the `.prg` lands beside it), and report the exact run
command `c64 package` prints (`x64sc -ntsc amiga_ball.d64` — the
video-standard flag keeps the 60 Hz timing the bounce table is written for).
Then write `demos/amiga_ball/README.md` in the shape the other built demos
use: what it is, how to watch it, a table of what each file is, what a
passing run shows, and the two or three bits of the build that are actually
worth reading.
