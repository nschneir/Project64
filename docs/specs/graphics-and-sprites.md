# Graphics & Sprites — How Agent-Built Demos Use, Author, and Test Them

Decision document for C64 graphics in this toolset: what demos may use, how
sprite/graphic data is authored, how graphical output is observed, and what
automated tests are allowed to assert. Tutorials and register tables live in
`skills/c64-development/references/hardware.md` and the cookbook; this file
sets policy. Facts cross-checked against the Commodore 64 Programmer's
Reference Guide and Mapping the Commodore 64.

## 1. Scope

Demos and example programs may use, in order of preference:

1. **Character graphics** — screen RAM `$0400` + color RAM `$D800`, PETSCII
   graphics characters, custom charsets. First-class: fully observable as
   text through `c64 screen`.
2. **Hardware sprites** — the VIC-II's 8 sprites. First-class: cheap to set
   up, observable through registers, and the idiomatic C64 way to move
   things smoothly.
3. **Bitmap modes** (hires 320×200, multicolor 160×200) — allowed where a
   demo genuinely needs them, not required anywhere. Costs 8 KB plus color
   setup and is the hardest to verify; prefer 1-2 unless the demo is
   *about* bitmap graphics.

Raster-chasing effects (mid-frame register changes, raster IRQ splits) are
**out of scope for automated demos** — they fight warp mode and
nondeterministic stop points. A demo may install a raster IRQ for timing
(one interrupt per frame), but nothing that must hit an exact scanline to
look right.

## 2. Authoring sprite and graphic data

- Sprite patterns are authored **as commented `.byte` rows in the source**,
  one sprite row per line, binary literals so the shape is readable in the
  code itself:

  ```asm
  ; ball sprite, 24x21 hires (63 bytes: 3 bytes x 21 rows)
  ball:   .byte %00000000, %01111110, %00000000
          .byte %00000011, %11111111, %11000000
          ...
  ```

  The AI writing the demo generates these patterns directly — that IS the
  asset pipeline. No external image files, no binary blobs in the repo.
- Custom charsets follow the same rule: `.byte` rows, 8 bytes per glyph,
  commented with the glyph they draw.
- A demo may include a tiny generator/checker script in its own `tools/`
  directory (Python, stdlib only) when data is large or has invariants worth
  asserting — e.g. converting ASCII art in a text file into `.byte` rows.
  It must be runnable standalone and tested if it has logic.
- Sprite data placement: a fixed, commented block address (e.g. `$2000`,
  pointer value `$80`) set via the sprite pointers at screen+`$3F8`
  (`$07F8-$07FF` for the default screen). The source comments must state
  the pointer math (`block = address / 64`).

## 3. Observing graphics output

Two channels, used for different things:

- **Memory and registers are the ground truth.** `c64 mem read` (and YAML
  `assert: {mem: ...}`) against: `$D015` (enable bits), `$D000/$D001` pairs
  + `$D010` MSB (positions), sprite pointers at `$07F8+n`, `$D01E/$D01F`
  (collision latches — note: reading clears them, so read once and assert
  on the read value), `$D020/$D021` (colors), and the demo's own state
  bytes. This is what tests assert.
- **Screenshots are evidence, not assertions.** `c64 screen --png` captures
  the rendered frame (VICE renders sprites and bitmap into the PNG). Demos
  keep the `evidence/` convention: capture the title screen, a mid-game
  frame, and any claimed visual feature, for human/AI review. `c64 screen`
  (text) only decodes screen RAM — sprites and bitmap pixels are invisible
  to it, so a sprite demo must never claim "verified" from text output
  alone.

## 4. Testing policy

- Every graphics demo must expose **testable non-graphics signals**: a
  score/state byte at a documented address, HUD text in screen RAM, and its
  sprite configuration in the VIC-II registers.
- YAML tests assert memory, registers, and screen-RAM text — never PNG
  pixels. Examples of the allowed shape:

  ```yaml
  - assert: { mem: "$D015", equals: 3 }        # sprites 0+1 enabled
  - assert: { mem: "$07F8", equals: 128 }      # sprite 0 data at $2000
  - assert: { mem: "score", equals_text: null, equals: 0 }   # via label
  - wait:   { text: "GAME OVER" }              # HUD line in screen RAM
  ```

- Motion is tested by sampling: `until` a frame anchor, read `$D000`,
  `until` again, read again, assert the two differ (direction if the demo
  documents it). Collision behavior is tested through the demo's own state
  change (lives byte decremented), not by trying to force `$D01E` timing.
- Determinism rules: run under `--warp --headless`; anchor every sampled
  read on a `c64 until` stop at the demo's main-loop label; never assert
  on free-running frame counts.

## 5. Screenshot capture workflow (evidence)

- `c64 screen --png demos/<name>/evidence/<feature>.png --scale 2` at each
  claimed feature moment, driven by the same until/wait choreography the
  tests use.
- Evidence PNGs are committed with the demo (they are small and load-bearing
  for review); they are not compared programmatically.

## 6. Future work (deliberately deferred)

- Pixel-assertion tooling (golden-image diff with tolerance) — revisit only
  if register+state assertions prove insufficient in practice.
- `c64 sprite` CLI helpers (decode `$D000-$D010` into a table, dump a
  sprite block as ASCII art) — nice-to-have; add when a second demo wants
  it.
- VIC-II bank/screen relocation support in `screen.py` (today the screen
  reader assumes the power-on `$0400`; demos must not relocate the screen).
