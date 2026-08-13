# 1812 — random shapes painted to the Overture

Using the c64 CLI (see skills/c64-development/SKILL.md, the 6502-assembly
skill, and docs/cli.md), build a Commodore 64 graphics demo in pure 6502
assembly that paints randomized shapes onto a bitmap canvas in time with
the **1812 Overture**. Everything for this demo lives in `demos/1812/`.

**Work in three phases, in this order — do not start coding at phase 3.**

1. **Spec.** Use the `superpowers:brainstorming` skill to settle the open
   design questions with me, then write `demos/1812/SPEC.md`: the
   graphics mode and memory map, the shape vocabulary, the rotation and
   fill-pattern math, the color policy, the arrangement's sections and
   how each drives the visuals, the RNG, the observable state bytes
   (every signal listed under **Make it observable** below, each with the
   address and label you picked for it), and the acceptance criteria —
   each one written as an observation a stopped machine can be read for,
   not as an adjective. That list is what the build gets judged against,
   so it has to cover everything this prompt asks the demo to be, the
   arrangement's audio evidence included, even where the proof is a
   capture rather than a stopped machine: a criterion that lives only in
   this prompt and never reaches your own PASS list is the one that
   quietly never gets met. The spec states *what* and *why*, with the
   hardware facts (register values, addresses, cycle budgets) pinned down
   and cited to the reference files below.
2. **Plan.** Use the `superpowers:writing-plans` skill to turn the spec
   into `demos/1812/PLAN.md` — ordered, independently verifiable steps,
   each with the test or observation that proves it. Rasterizer before
   music; something on screen early.
3. **Build.** Execute the plan (`superpowers:executing-plans`,
   `superpowers:test-driven-development`), keeping the source in
   `demos/1812/`. A step is done when the observation the plan named for
   it is read back off the running machine — not when the code
   assembles — and the build is done when every acceptance criterion in
   `SPEC.md` passes there, with the evidence listed below. Update the
   plan as the running machine corrects you.

**Skills and references to use — read these before writing the spec:**

- `skills/c64-development/SKILL.md` — the write→run→observe→debug loop,
  the stopped-state discipline, sessions (`--warp --headless` for
  automation), and how graphics get observed. `docs/cli.md` is the full
  command reference; every command takes `--json`.
- `skills/c64-development/references/hardware.md` — VIC-II bitmap modes
  (`$D011` bit 5, `$D016` bit 4, `$D018` base select) and the full SID
  register map, ADSR, waveforms, and filter.
- `skills/c64-development/references/memory-maps.md` and `zero-page.md` —
  where the 8 KB bitmap can live without colliding with your code, BASIC,
  or the KERNAL, and which zero-page bytes you may use for rasterizer
  pointers.
- `skills/c64-development/references/kernal-routines.md` — only for setup
  and teardown; nothing from ROM in the hot path.
- `skills/c64-development/references/cookbook.md` — working recipes
  (raster IRQ, SID, held-key input) to start from rather than reinvent.
- `skills/6502-assembly/SKILL.md` — the `$0801` load address, the BASIC
  SYS stub, ca65 segments, and the 6502 gotchas that bite in tight loops.
- `skills/6502-debugging/SKILL.md` — when it misbehaves, follow the
  symptom-indexed procedure (starting with rule zero: prove you are
  debugging the binary you think you are) instead of guessing from
  source. `superpowers:systematic-debugging` for the surrounding
  discipline.
- `docs/graphics-and-sprites.md` — **policy, not a
  tutorial**: how graphic data is authored (commented `.byte` rows in the
  source, no binary blobs), what tests may assert (memory and registers,
  never PNG pixels), and the `evidence/` screenshot convention. Bitmap
  mode is explicitly allowed for a demo that is *about* bitmap graphics —
  this one is. Raster-chasing is out of scope; one interrupt per frame is
  fine.

**The demo:**

- **Canvas.** Black background *and* black border (`$D021` = `$D020` = 0),
  set once. Multicolor bitmap (160×200) is the recommended mode — it
  gives four colors per 4×8 cell and makes the color budget the
  interesting problem — but justify your choice in the spec and state the
  exact `$D011`/`$D016`/`$D018` values and the memory map you picked — as
  arithmetic that adds up, naming what is left over and where data that
  exists only at runtime lives. Keep that spare figure current as the
  build grows: it is the number that later decides whether a faster inner
  loop or a longer arrangement fits at all.
  Clear the bitmap to black **once** at start.
- **Accumulation, never a clear.** Every shape is painted over what is
  already there. The canvas only ever gets denser; nothing is erased, no
  frame is blanked. This is a hard rule and it must be provable at
  runtime (see the evidence list).
- **Shapes.** Each spawn picks, from the RNG: shape type, size, screen
  position, rotation angle, fill pattern, and colors. The vocabulary
  needs at least: triangle, rectangle, ovals, circles, pentagon/hexagon, five-pointed
  star, and an ellipse. Additional shapes are welcome. Rotation is real geometry — a 256-step angle,
  sin/cos tables in `RODATA`, 8.8 fixed-point vertex transform, then a
  scanline polygon fill. The star is concave, so the fill must be
  even-odd correct, not "convex only". Rotation must be *visible*: a
  rotated square reads as a diamond, a rotated ellipse tilts. Shapes may
  run off the edges — clip, don't skip.
- **Fill patterns.** Each shape is filled through an 8×8 dither mask —
  solid, 50% checker, vertical and horizontal stripes, diagonals, sparse
  dots, cross-hatch, and so on. Patterns are what let a shape read as
  translucent over what it covers.
- **Use the limited colors creatively.** Sixteen fixed colors, four per
  cell, on black. Exploit what the palette gives you: the luminance
  ladder (black → dark grey → medium grey → light grey → white) for
  shading, the dither masks to mix apparent colors that the palette does
  not contain, and a per-section palette so the picture's mood tracks the
  music. Because cells accumulate, a new shape rewriting a cell's
  attributes recolors whatever was already there — **state your
  color-clash policy in the spec and make it deliberate** (the new shape
  claims the cell, or shapes within a section share a color pair so
  overlaps stay coherent). Clash you chose is a look; clash you ignored
  is a bug.
- **The music.** A three-voice SID arrangement of the Overture, abridged
  to roughly two to four minutes but hitting its recognizable sections:
  the opening hymn (*O Lord, Save Thy People*), the Marseillaise
  fragment, the battle, the cannon, and the bell-driven finale. The 1880
  score is public domain but an arrangement of it is not: reduce those
  themes for three voices yourself, as original work composed for this
  demo, rather than transcribing someone else's SID, MIDI, or sheet
  arrangement. Three voices is a reduction, and a reduction that keeps
  all three sounding from the first bar to the last reads as a thin
  orchestra rather than as the Overture: state in the spec how the
  texture evolves across the piece — where it thins, where it fills — and
  why that arc is the right one for this music. Push the SID to its full
  potential — real ADSR envelopes, mixed waveforms (pulse with swept
  width, triangle, sawtooth, noise), and the filter. Say what each
  instrument's envelope is *for* — which physical gesture it imitates —
  and not only which nybbles it holds: an envelope chosen as four numbers
  rather than as a gesture is how a part ends up reading as an organ
  however many voices are playing.
  The cannon is filtered noise with a downward cutoff sweep; the finale's
  bells are bright, fast decays. Drive the sequencer from a single raster
  IRQ (or the jiffy clock) at frame rate. **Shadow every SID write in
  RAM** — the SID is write-only, and the shadow bytes are the only
  evidence a stopped machine can give you that sound happened: necessary,
  and not sufficient.
- **Music drives the picture.** Note onsets spawn shapes; the section
  determines the vocabulary, palette, size range, and spawn rate. That
  coupling puts the arrangement inside the frame budget — a busier part is
  a denser canvas — so say in the spec what gives when the music gets
  busier, and re-check it whenever the arrangement changes. The
  hymn paints few, large, slow, dark shapes; the battle paints small
  jagged ones fast; each of the sixteen cannon shots flashes the whole
  screen (border included — briefly, then back to black) and throws a
  large burst; the finale fills the remaining black with bright rapid
  shapes. When the piece ends, hold the finished canvas; a key — read as
  the live matrix code at `$CB`, not through a ROM call — restarts it
  with a fresh seed.
- **Randomness must be reproducible.** A seeded 16-bit LFSR in software,
  so the same seed paints the same canvas and tests can assert it. Keep
  the seed at a documented address a test can write *before* the run
  starts: reproducibility you cannot set is reproducibility you cannot
  check. (`$D41B`, SID voice 3's oscillator, is the classic hardware RNG,
  but it costs you a voice — if you use it, geneate a pool of random numbers before starting the music.)

**Performance rules.** Multicolor bitmap plotting is expensive: fill
whole bytes (four pixels) along a span with masked edges rather than
plotting pixel by pixel, and use a row-address lookup table instead of
multiplying. No ROM calls in the hot path. Know the cycle cost of a span
fill and of a worst-case shape; a shape that takes longer than its note
is a bug you should find by measuring, not by watching. Painting may
cross frames — say in the spec how a long shape and the music sequencer
coexist.

**Make it observable.** Per the graphics policy, expose testable
non-graphics signals at documented, labeled addresses: shapes-drawn
counter, current section index, current note index, RNG state, and the
last shape's type/size/position/angle/pattern/colors. Record each
address in `SPEC.md` and export it as a label, so tests and `c64 until`
name the signal rather than hard-coding a number that drifts on the next
build. Write a `demos/1812/test.yaml` for `c64 test run` that asserts the
mode registers (`$D011`, `$D016`, `$D018`, `$D020`, `$D021`), section
progression, a monotonically increasing shape counter, and the same seed
producing the same state — never PNG pixels.

**The improvement loop.** A first build that paints shapes is the *start*
of this demo, not the end. From there, work in explicit numbered
iterations, each one a full cycle:

1. **Evaluate** — run the demo deterministically (see the proof protocol
   below) and audit it against every bullet of your own `SPEC.md`,
   marking each PASS or FAIL with evidence from the running machine,
   never from reading the source.
2. **Review** — do a detailed code review of the current build: the
   rasterizer's inner loops cycle-counted, the span fill and the music
   sequencer scrutinized where they contend for a frame, dead code and
   slack removed — then judge the result the way a viewer would, and say
   whether the picture actually looks good and the arrangement actually
   sounds like the Overture. That second judgment has to come off a
   capture of the running machine (**Audio evidence** below), because
   shadow bytes prove only that writes happened and cannot tell you how an
   arrangement reads; an iteration whose review has to write "I cannot
   hear this" has not done this step.
3. **Improve** — fix every FAIL and act on every review finding.
4. **Re-verify** — prove each fix on the running machine before counting
   it done.

Log each iteration in `demos/1812/AUDIT.md` so progress is visible, and
keep looping until an iteration ends with every spec bullet PASS and a
review that finds nothing worth fixing. Use
`superpowers:verification-before-completion` before any claim that it
works.

**Prove it deterministically.** Run under `--warp --headless`, anchor
every observation on a `c64 until` stop at a labeled point (spawn,
section change, cannon), and read memory and registers between stops.
Show me: the black canvas before the first shape; a single shape beside
the state bytes recording the type/angle/pattern that produced it; the
same shape type at three different rotations; the canvas after each
section; a cannon flash; the finished canvas at the end of the piece; SID
shadow bytes captured mid-cannon and mid-finale; and — the proof that
nothing is ever cleared — a set of bitmap bytes sampled early and re-read
late showing the early pixels still lit while the total lit-pixel count
only rose (count it off a `c64 mem read` dump of the bitmap, not by eye).
Keep the pictures: every visual claim above is captured as a named PNG
under `demos/1812/evidence/` per
`docs/graphics-and-sprites.md`
(`c64 screen --png … --scale 2 --border`), taken while the machine is
*stopped* at a `c64 until` label — never staged, never drawn by hand —
and committed with the demo rather than deleted after the run. The set
covers, at minimum, the blank canvas before the first shape, the canvas
mid-piece in at least two different sections whose shape activity visibly
differs, a cannon flash, and the finale at full crescendo; the
mid-arrangement SID shadow reads (`c64 mem read` over the shadow block)
go in the run log beside the frame taken at the same stop, since the
proof that sound happened is bytes, not a picture.

**Audio evidence.** Shadow bytes prove the writes happened; on a demo whose
whole point is an arrangement, they are nowhere near enough. Capture the
music itself with `c64_audio_capture` (`c64 audio capture` from the shell)
and commit its five artifacts — `capture.wav`, `sid-log.jsonl`,
`piano-roll.png`, `spectrogram.png`, `report.md` — under
`demos/1812/evidence/audio/`, one capture per recognizable section: the
hymn, the Marseillaise fragment, the battle, a cannon, and the finale.
Captures run with warp off, in real time, so take the ten or fifteen
seconds that carry each section rather than the whole piece. Write a
reference score (YAML) from your own arrangement data and capture against
it; the report must pass. Then read your piano roll the way you read the
canvas frames — a wrong contour, a missing voice, or bars that drift off
the rhythm are bugs, not interpretation — and use the spectrogram for what
the notes cannot show: the cannon's filtered noise and its downward cutoff
sweep. The maintainer's listen of `capture.wav` is the final gate on
whether it sounds like the Overture;
skills/c64-development/references/audio-verification.md has the method.

**Ship it.** When everything passes, package the demo so anyone with
stock VICE can run it: `c64 package` your source into
`demos/1812/1812.d64` with `--title "1812"` (the `.prg` lands beside it),
and report the exact run command `c64 package` prints
(`x64sc -ntsc 1812.d64` — the video-standard flag keeps the timing you
tested, and on this demo the timing is the whole point).
