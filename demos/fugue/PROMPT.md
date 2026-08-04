# Fugue No. 2 in C Minor — the score scrolling past as it plays

Using the c64 CLI (see skills/c64-development/SKILL.md, the 6502-assembly
skill, and docs/cli.md), build a Commodore 64 audiovisual demo in pure 6502
assembly that plays **J. S. Bach's Fugue No. 2 in C minor, BWV 847** (from
*The Well-Tempered Clavier*, Book I) while scrolling the notated score
across the screen in time with the music. Everything for this demo lives in
`demos/fugue/`.

**Work in three phases, in this order — do not start coding at phase 3.**

1. **Spec.** Use the `superpowers:brainstorming` skill to settle the open
   design questions with me, then write `demos/fugue/SPEC.md`: the screen
   mode and memory map, the charset design, the staff layout, the
   note-to-color mapping, the scroll mechanism and its timing relationship
   to the sequencer, the sprite backlight, the arrangement's voice
   assignment and envelopes, the observable state bytes (every signal under
   **Make it observable**, each with the address and label you picked), and
   the acceptance criteria — each written as an observation a stopped
   machine can be read for, not as an adjective. Pin the hardware facts
   (register values, addresses, cycle budgets) and cite them to the
   reference files below.
2. **Plan.** Use `superpowers:writing-plans` to turn the spec into
   `demos/fugue/PLAN.md` — ordered, independently verifiable steps, each
   with the test or observation that proves it. Get a static staff on
   screen early, then scrolling, then music, then the coupling between
   them.
3. **Build.** Execute the plan (`superpowers:executing-plans`,
   `superpowers:test-driven-development`), keeping the source in
   `demos/fugue/`. A step is done when the observation the plan named for
   it is read back off the running machine — not when the code assembles —
   and the build is done when every acceptance criterion in `SPEC.md`
   passes there, with the evidence listed below. Update the plan as the
   running machine corrects you.

**Skills and references to use — read these before writing the spec:**

- `skills/c64-development/SKILL.md` — the write→run→observe→debug loop, the
  stopped-state discipline, sessions (`--warp --headless` for automation).
  `docs/cli.md` is the full command reference; every command takes `--json`.
- `skills/c64-development/references/hardware.md` — the VIC-II text mode,
  `$D016` horizontal scroll and 38-column mode, sprite registers and the
  sprite/character priority bit, `$D018` charset base select, and the full
  SID register map: ADSR, waveforms, pulse width, and the filter.
- `skills/c64-development/references/audio-verification.md` — how music is
  proved without ears. Read this before you write a note of the
  arrangement, not after.
- `skills/c64-development/references/memory-maps.md` and `zero-page.md` —
  where a custom charset and screen RAM can live without colliding with
  your code, BASIC, or the KERNAL.
- `skills/c64-development/references/cookbook.md` — working recipes (raster
  IRQ, SID, smooth scrolling) to start from rather than reinvent.
- `skills/6502-assembly/SKILL.md` — the `$0801` load address, the BASIC SYS
  stub, ca65 segments, and the gotchas that bite in tight loops.
- `skills/6502-debugging/SKILL.md` — when it misbehaves, follow the
  symptom-indexed procedure instead of guessing from source.
- `docs/graphics-and-sprites.md` — **policy, not a tutorial**: how graphic
  data is authored (commented `.byte` rows in the source, no binary blobs),
  what tests may assert (memory and registers, never PNG pixels), and the
  `evidence/` screenshot convention.

## The music

BWV 847 is the reason this demo exists. It is a **three-voice fugue**, and
the SID has exactly three voices — so the piece maps onto the chip with no
parts dropped, merged, or compromised. Every voice stays intact.

The fugue is public domain (Bach died in 1750), but *an arrangement* of it
is not: reduce it for three voices yourself as original work for this demo,
from the score, rather than transcribing someone else's SID, MIDI, or sheet
arrangement.

**Voice assignment and timbre — build to this mapping:**

| SID voice | Musical role | Waveform |
|---|---|---|
| 1 | High voice — subject / soprano | Pulse, with pulse-width modulation |
| 2 | Middle voice — countersubject | Sawtooth |
| 3 | Bass line — pedal / ground | Triangle, through the resonant filter |

The mapping is chosen so each line stays separable by ear: PWM gives voice 1
a chorusing, phased lead that carries the subject; the sawtooth's buzzy
attack keeps the middle voice present without masking the top; the triangle
sits under both. Use the SID's own character rather than three identical
tones — this is the difference between "the notes are correct" and "it
sounds like the C64 playing Bach".

**Push the chip.** Real ADSR envelopes per voice, swept pulse width on voice
1, and the resonant filter on voice 3 — the fugue's driving perpetual-motion
sixteenths are exactly the material that rewards a crisp attack. Sweep the
filter cutoff through the climactic pedal point near the end; that warm
resonant crunch is unique to this hardware and is the moment to spend it on.
Drive the sequencer from a single raster IRQ at frame rate. **Shadow every
SID write in RAM** — the SID is write-only, and the shadow bytes are the
only testable evidence that a write happened.

Play enough of the fugue that its structure is unmistakable: at minimum the
complete exposition, with the three voice entries clearly individually
audible as each enters, through to a proper ending rather than a fade. More
is welcome if the timing holds.

## The screen

**Text mode with a custom character set.** Screen and border both black
(`$D021` = `$D020` = 0), set once.

- **Staves in white.** Draw real musical staves — five lines, clef, and bar
  lines — from custom characters. Decide in the spec whether the three
  voices share one system or get their own staves, and justify it against
  the 25-row budget and against legibility when two voices cross.
- **Notes colored by pitch class.** Each of the twelve pitch classes gets
  its own bright color, repeating every octave, so the same note name is
  always the same color regardless of register. Color RAM is per character
  cell, which makes a note head one cell's worth of color — state the
  mapping in the spec as a table. Be honest about the constraint: the C64's
  sixteen colors do not divide into twelve equally legible bright ones
  against black, so say which colors you chose, which pitch classes got the
  weaker ones, and why that is the least bad assignment.
- **Accidentals are drawn.** Sharps and flats appear as their own
  characters beside the note heads they modify. C minor means flats are
  routine and the fugue's chromaticism means accidentals are not
  decoration — if a note sounds a semitone away from the staff position it
  occupies, the symbol saying so must be on screen.
- **The score scrolls right to left**, so notes travel toward a fixed
  "now" column and the music reads as arriving rather than sitting still.
  Use the VIC-II's horizontal fine scroll (`$D016` bits 0-2) with a
  character-column shift of screen and color RAM every eight pixels, and
  38-column mode to hide the entering edge. Say in the spec how you keep
  the shift within the frame budget — moving 25 rows of screen *and* color
  RAM every eighth frame is real work, and doing it in one raster IRQ is
  the thing most likely to break.
- **A sprite backlights the sounding note.** The note currently being
  played is lit from behind: position a sprite at that note's cell with the
  sprite-behind-character priority bit set (`$D01B`), so the glow shows
  through the cell's background around the white note head rather than
  covering it. That priority choice is what makes it read as backlit
  instead of pasted on top — verify it looks that way and say so. With
  three voices sounding at once, state your policy in the spec: one sprite
  per voice, or one that follows a chosen voice.

**Scroll timing is a correctness property, not a feel.** The scroll rate and
the sequencer must derive from one clock, so a note reaches the "now" column
on the frame it sounds. If they drift apart, the demo is showing one thing
and playing another — and that is a bug you must find by measuring, not by
watching.

## Make it observable

Per the graphics policy, expose testable non-graphics signals at documented,
labeled addresses: current bar and beat, current note index per voice, the
scroll offset and column-shift counter, the sounding-note cell each sprite
is tracking, and the SID shadow block. Record each address in `SPEC.md` and
export it as a label so tests and `c64 until` name the signal rather than
hard-coding a number that drifts on the next build.

Write `demos/fugue/test.yaml` for `c64 test run` asserting the mode
registers (`$D011`, `$D016`, `$D018`, `$D01B`, `$D020`, `$D021`), the charset
base, staff characters present at their expected screen positions, the
scroll offset advancing and wrapping correctly, note colors matching the
pitch-class table, and sprite position tracking the sounding note — never
PNG pixels.

## Prove it

**Deterministically.** Run under `--warp --headless`, anchor every
observation on a `c64 until` stop at a labeled point (a voice entry, a bar
line, the pedal point), and read memory and registers between stops. Show
me: the staves drawn before the music starts; the first subject entry with
the state bytes recording which voice and which note; a frame where two
voices cross, proving the layout stays legible; a scroll offset sampled
across successive frames showing smooth advance and a clean column wrap; the
sprite's coordinates beside the cell coordinates of the note the sequencer
says is sounding, at the same stop; and an accidental on screen beside the
shadow bytes showing the pitch it modifies.

Keep the pictures: every visual claim is a named PNG under
`demos/fugue/evidence/` per `docs/graphics-and-sprites.md`
(`c64 screen --png … --scale 2 --border`), taken while the machine is
*stopped* at a `c64 until` label — never staged, never drawn by hand.

**Audio evidence.** Shadow bytes prove writes happened; on a demo whose
whole point is an arrangement, that is nowhere near enough. Capture the
music with `c64_audio_capture` (`c64 audio capture` from the shell) and
commit its five artifacts — `capture.wav`, `sid-log.jsonl`,
`piano-roll.png`, `spectrogram.png`, `report.md` — under
`demos/fugue/evidence/audio/`. Take one capture per structural moment: each
of the three voice entries in the exposition, and the pedal point with the
filter sweep. Captures run with warp off, in real time, so take the ten or
fifteen seconds carrying each moment rather than the whole fugue.

Write a reference score (YAML) from **your own arrangement data** and
capture against it — never from the transcription the tool produces, which
cannot fail. The report must pass. Then read your piano roll the way you
read the screenshots: three independent lines, the subject recognizably
restated in each voice as it enters, no voice silently dropped. Use the
spectrogram for what the notes cannot show — the pulse-width modulation on
voice 1 and the filter sweep on voice 3.

**The cross-check that matters most.** This demo displays the same note data
it plays, so the two evidence streams must agree: the piano roll from the
capture and the notes on the scrolling staff are two renderings of one
source. Put them side by side and confirm they tell the same story — same
pitches, same order, same rhythm. If the screen and the piano roll disagree,
one of the two paths is wrong and finding out which is the most valuable
debugging this demo will give you.

The maintainer's listen of `capture.wav` is the final gate on whether it
sounds like Bach. `skills/c64-development/references/audio-verification.md`
has the method.

## The improvement loop

A first build that plays and scrolls is the *start* of this demo. Work in
explicit numbered iterations, each a full cycle:

1. **Evaluate** — run deterministically and audit against every bullet of
   your own `SPEC.md`, marking each PASS or FAIL with evidence from the
   running machine, never from reading the source.
2. **Review** — review the build: the scroll and sequencer cycle-counted
   where they contend for a frame, the charset audited for legibility at
   1× scale, dead code removed. Then judge it as a viewer and listener
   would: does the score on screen actually read as music, and does the
   arrangement actually sound like the C minor fugue?
3. **Improve** — fix every FAIL and act on every finding.
4. **Re-verify** — prove each fix on the running machine before counting it
   done.

Log each iteration in `demos/fugue/AUDIT.md`, and keep looping until an
iteration ends with every spec bullet PASS and a review that finds nothing
worth fixing. Use `superpowers:verification-before-completion` before any
claim that it works.

## Ship it

When everything passes, package it so anyone with stock VICE can run it:
`c64 package` your source into `demos/fugue/fugue.d64` with
`--title "FUGUE IN C MINOR"` (the `.prg` lands beside it), and report the
exact run command `c64 package` prints — the video-standard flag keeps the
timing you tested, and on a demo where the picture is synchronized to the
music, the timing is the whole point.
