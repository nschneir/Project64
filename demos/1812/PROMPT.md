# 1812 — random shapes painted to the Overture

A bitmap-graphics demo in 6502 assembly: randomized shapes accumulating on a
black canvas, spawned in time with a three-voice SID arrangement of
Tchaikovsky's *1812 Overture* (1880, public domain).

Paste this prompt into your agent:

> Build a Commodore 64 graphics demo in pure 6502 assembly that paints
> randomized shapes onto a bitmap canvas in time with the **1812 Overture**.
> Everything for this demo lives in `demos/1812/`.
>
> **Work in three phases, in this order — do not start coding at phase 3.**
>
> 1. **Spec.** Use the `superpowers:brainstorming` skill to settle the open
>    design questions with me, then write `demos/1812/SPEC.md`: the graphics
>    mode and memory map, the shape vocabulary, the rotation and fill-pattern
>    math, the color policy, the arrangement's sections and how each drives
>    the visuals, the RNG, the observable state bytes, and the acceptance
>    criteria. The spec states *what* and *why*, with the hardware facts
>    (register values, addresses, cycle budgets) pinned down and cited to the
>    reference files below.
> 2. **Plan.** Use the `superpowers:writing-plans` skill to turn the spec into
>    `demos/1812/PLAN.md` — ordered, independently verifiable steps, each with
>    the test or observation that proves it. Rasterizer before music;
>    something on screen early.
> 3. **Build.** Execute the plan (`superpowers:executing-plans`,
>    `superpowers:test-driven-development`), keeping the source in
>    `demos/1812/`.
>
> **Skills and references to use — read these before writing the spec:**
>
> - `skills/c64-development/SKILL.md` — the write→run→observe→debug loop, the
>   stopped-state discipline, sessions (`--warp --headless` for automation),
>   and how graphics get observed. `docs/cli.md` is the full command
>   reference; every command takes `--json`.
> - `skills/c64-development/references/hardware.md` — VIC-II bitmap modes
>   (`$D011` bit 5, `$D016` bit 4, `$D018` base select) and the full SID
>   register map, ADSR, waveforms, and filter.
> - `skills/c64-development/references/memory-maps.md` and `zero-page.md` —
>   where the 8 KB bitmap can live without colliding with your code, BASIC, or
>   the KERNAL, and which zero-page bytes you may use for rasterizer pointers.
> - `skills/c64-development/references/kernal-routines.md` — only for setup
>   and teardown; nothing from ROM in the hot path.
> - `skills/c64-development/references/cookbook.md` — working recipes
>   (raster IRQ, SID, held-key input) to start from rather than reinvent.
> - `skills/6502-assembly/SKILL.md` — the `$0801` load address, the BASIC SYS
>   stub, ca65 segments, and the 6502 gotchas that bite in tight loops.
> - `skills/6502-debugging/SKILL.md` — when it misbehaves, follow the
>   symptom-indexed procedure (starting with rule zero: prove you are
>   debugging the binary you think you are) instead of guessing from source.
>   `superpowers:systematic-debugging` for the surrounding discipline.
> - `docs/superpowers/specs/graphics-and-sprites.md` — **policy, not a
>   tutorial**: how graphic data is authored (commented `.byte` rows in the
>   source, no binary blobs), what tests may assert (memory and registers,
>   never PNG pixels), and the `evidence/` screenshot convention. Bitmap mode
>   is explicitly allowed for a demo that is *about* bitmap graphics — this
>   one is. Raster-chasing is out of scope; one interrupt per frame is fine.
>
> **The demo:**
>
> - **Canvas.** Black background *and* black border (`$D021` = `$D020` = 0),
>   set once. Multicolor bitmap (160×200) is the recommended mode — it gives
>   four colors per 4×8 cell and makes the color budget the interesting
>   problem — but justify your choice in the spec and state the exact
>   `$D011`/`$D016`/`$D018` values and the memory map you picked. Clear the
>   bitmap to black **once** at start.
> - **Accumulation, never a clear.** Every shape is painted over what is
>   already there. The canvas only ever gets denser; nothing is erased, no
>   frame is blanked. This is a hard rule and it must be provable at runtime
>   (see the evidence list).
> - **Shapes.** Each spawn picks, from the RNG: shape type, size, screen
>   position, rotation angle, fill pattern, and colors. The vocabulary needs
>   at least: triangle, rectangle, pentagon/hexagon, five-pointed star, and
>   an ellipse. Rotation is real geometry — a 256-step angle, sin/cos tables
>   in `RODATA`, 8.8 fixed-point vertex transform, then a scanline polygon
>   fill. The star is concave, so the fill must be even-odd correct, not
>   "convex only". Rotation must be *visible*: a rotated square reads as a
>   diamond, a rotated ellipse tilts. Shapes may run off the edges — clip,
>   don't skip.
> - **Fill patterns.** Each shape is filled through an 8×8 dither mask —
>   solid, 50% checker, vertical and horizontal stripes, diagonals, sparse
>   dots, cross-hatch, and so on. Patterns are what let a shape read as
>   translucent over what it covers.
> - **Use the limited colors creatively.** Sixteen fixed colors, four per
>   cell, on black. Exploit what the palette gives you: the luminance ladder
>   (black → dark grey → medium grey → light grey → white) for shading, the
>   dither masks to mix apparent colors that the palette does not contain,
>   and a per-section palette so the picture's mood tracks the music. Because
>   cells accumulate, a new shape rewriting a cell's attributes recolors
>   whatever was already there — **state your color-clash policy in the spec
>   and make it deliberate** (the new shape claims the cell, or shapes within
>   a section share a color pair so overlaps stay coherent). Clash you chose
>   is a look; clash you ignored is a bug.
> - **The music.** A three-voice SID arrangement of the Overture, abridged to
>   roughly two to four minutes but hitting its recognizable sections: the
>   opening hymn (*O Lord, Save Thy People*), the Marseillaise fragment, the
>   battle, the cannon, and the bell-driven finale. Push the SID as demo 06
>   does — real ADSR envelopes, mixed waveforms (pulse with swept width,
>   triangle, sawtooth, noise), and the filter. The cannon is filtered noise
>   with a downward cutoff sweep; the finale's bells are bright, fast decays.
>   Drive the sequencer from a single raster IRQ (or the jiffy clock) at frame
>   rate. **Shadow every SID write in RAM** — the SID is write-only, and the
>   shadow bytes are the only testable evidence that sound happened.
> - **Music drives the picture.** Note onsets spawn shapes; the section
>   determines the vocabulary, palette, size range, and spawn rate. The hymn
>   paints few, large, slow, dark shapes; the battle paints small jagged ones
>   fast; each of the sixteen cannon shots flashes the whole screen (border
>   included — briefly, then back to black) and throws a large burst; the
>   finale fills the remaining black with bright rapid shapes. When the piece
>   ends, hold the finished canvas; a key restarts with a fresh seed.
> - **Randomness must be reproducible.** A seeded 16-bit LFSR in software, so
>   the same seed paints the same canvas and tests can assert it. (`$D41B`,
>   SID voice 3's oscillator, is the classic hardware RNG, but it costs you a
>   voice — if you use it, say why in the spec.)
>
> **Performance rules.** Multicolor bitmap plotting is expensive: fill whole
> bytes (four pixels) along a span with masked edges rather than plotting
> pixel by pixel, and use a row-address lookup table instead of multiplying.
> No ROM calls in the hot path. Know the cycle cost of a span fill and of a
> worst-case shape; a shape that takes longer than its note is a bug you
> should find by measuring, not by watching. Painting may cross frames — say
> in the spec how a long shape and the music sequencer coexist.
>
> **Make it observable.** Per the graphics policy, expose testable
> non-graphics signals at documented, labeled addresses: shapes-drawn
> counter, current section index, current note index, RNG state, and the last
> shape's type/size/position/angle/pattern/colors. Write a
> `demos/1812/test.yaml` for `c64 test run` that asserts the mode registers
> (`$D011`, `$D016`, `$D018`, `$D020`, `$D021`), section progression, a
> monotonically increasing shape counter, and the same seed producing the
> same state — never PNG pixels.
>
> **Prove it deterministically.** Run under `--warp --headless`, anchor every
> observation on a `c64 until` stop at a labeled point (spawn, section
> change, cannon), and read memory and registers between stops. Show me:
> the black canvas before the first shape; a single shape with its recorded
> type/angle/pattern next to `c64 sprite`-free bitmap evidence
> (`c64 screen --png`); the same shape type at three different rotations; the
> canvas after each section; a cannon flash; the finished canvas at the end
> of the piece; SID shadow bytes captured mid-cannon and mid-finale; and — the
> proof that nothing is ever cleared — a set of bitmap bytes sampled early and
> re-read late showing the early pixels still lit while the total lit-pixel
> count only rose. Collect evidence PNGs under `demos/1812/evidence/` per
> `docs/superpowers/specs/graphics-and-sprites.md`.
>
> **Iterate before you call it done.** A first build that paints shapes is the
> start. Loop: evaluate against every bullet of your own SPEC.md, marking each
> PASS/FAIL with evidence from the *running machine*, never from reading the
> source; review the code (cycle-count the rasterizer, cut dead code, judge
> whether the picture actually looks good and the arrangement actually sounds
> like the Overture); fix everything; re-verify. Log each round. Keep going
> until a round finds nothing. Use `superpowers:verification-before-completion`
> before any claim that it works.
>
> **Ship it.** `c64 package` the source into `demos/1812/1812.d64` with
> `--title "1812"`, and tell me the exact run command it prints
> (`x64sc -ntsc 1812.d64`).

**What success looks like:** `demos/1812/` containing `SPEC.md`, `PLAN.md`, the
assembled 6502 source with its BASIC SYS stub, `test.yaml`, an `evidence/`
directory, and a bootable `1812.d64`. On screen: a black field that fills up
over a few minutes with rotated, dithered, overlapping shapes whose color and
character change as the arrangement moves from hymn to battle to cannon to
finale — never cleared, never repainted, the whole picture a record of the
piece. This demo is the toolset's graphics stress test: bitmap mode, a real
rotating polygon rasterizer, a color budget used on purpose, and three voices
of SID, all verified through registers and state bytes rather than
screenshots.
