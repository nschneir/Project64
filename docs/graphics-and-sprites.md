# Graphics & sprites — how demos use, author, and test them

Policy for C64 graphics in this toolset: what demos may use, how sprite and
graphic data is authored, how graphical output is observed, and what
automated tests may assert. Tutorials and register tables live in
`skills/c64-development/references/hardware.md` and the cookbook, and the
techniques — authoring `.byte` rows, observing sprites, anchoring and
sampling — live in `skills/c64-development/SKILL.md`. This file sets the
rules instead: which modes demos may use, where evidence is committed, what
is deferred. It is repo policy, and it deliberately does not travel with the
skill. Facts cross-checked against the Commodore 64 Programmer's Reference
Guide and Mapping the Commodore 64.

## 1. Scope

Demos and example programs may use, in order of preference:

1. **Character graphics** — screen RAM `$0400` + color RAM `$D800`, PETSCII
   graphics characters, custom charsets. First-class: fully observable as
   text through `c64 screen`. One qualification for **custom charsets**:
   `c64 screen` decodes each screen code through its *ROM* meaning, so a
   redefined glyph reads back as whatever the ROM drew there, and codes 32,
   96 and 224 decode to a blank — a glyph on 96 is invisible in decoded text
   while present in the PNG. The codes themselves are unchanged, so
   `c64 screen --codes` and `mem read` stay exact; it is the *decoded text*
   that must not be trusted to show a custom glyph.
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

  The AI writing the demo generates these patterns directly, converts a
  generated image with `c64 sprite from-png`, or authors plain ASCII art
  and converts it with `c64 sprite encode` (both emit exactly this
  format). Either way the committed artifact is the readable `.byte` rows
  — no external image files, no binary blobs in the repo. ASCII-art
  authoring is first-class via `c64 sprite encode`, so a demo only needs
  its own `tools/` converter for input formats that command doesn't cover.
- Custom charsets follow the same rule: `.byte` rows, 8 bytes per glyph,
  commented with the glyph they draw. `c64 charset encode` emits exactly
  this format from an ASCII sheet, the way `c64 sprite encode` does for
  sprites, so charset authoring is ASCII-art-first too.
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
  on the read value), `$D020/$D021` (colors), colour RAM at `$D800`
  (**4-bit readback — compare masked**, `and: "$0f"`), and the demo's own
  state bytes. This is what tests assert. Screen reads are relocation-aware:
  `c64 screen` and `@row,col` follow `$DD00`/`$D018` to wherever the
  VIC-II put the screen; color RAM stays `$D800`, and `@@row,col` addresses
  it directly (same row/col, fixed base).
- **`c64 sprite` is the sprite inspector.** `sprite status` decodes the
  registers into a table, `sprite show` renders a shape as ASCII art, and
  `sprite png` renders the exact shape with live colors — use these to
  verify a sprite before claiming it works.
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
  - assert: { mem: "score", equals: 0 }        # via label
  - assert: { mem: "@@3,7", mask: { and: "$0f", equals: [7] } }
                                               # a cell's colour: colour RAM
                                               #   reads back 4-bit, mask it
  - wait:   { text: "GAME OVER" }              # HUD line in screen RAM
  ```

- Motion is tested by sampling: `until` a frame anchor, `sample` a
  register under a name, `until` again, `assert ... differs` (or
  `greater_than`/`less_than` when the demo documents direction) — the
  runner supports this natively; see `c64 test run` in docs/cli.md and
  `tests/programs/sprite-ball/test.yaml` for the worked example. Collision
  behavior is tested through the demo's own state change (lives byte
  decremented), not by trying to force `$D01E` timing.
- Determinism rules: run under `--warp --headless`; anchor every sampled
  read on a `c64 until` stop at the demo's main-loop label; never assert
  on free-running frame counts.
- **BASIC demos have no label to anchor on** — `until`/`break add` need a
  symbol or a code address, and a BASIC program has neither. Two
  substitutes, both requiring the program to publish state:
  - a **saturating summary byte** (a bitmask of the events seen so far, a
    high-water mark) that only ever moves one way, so
    `wait: { mem: "$fa", equals: 15 }` cannot race. Prefer this in tests.
  - a **store watchpoint on a state byte** the program pokes at the moment
    of interest (`c64 watch add '$FC' --store` then `c64 wait --break`),
    which stops the machine *at* the event. Prefer this for evidence
    capture and for hand-driven sampling.
  Counters that climb are asserted with `at_least`, never `equals`: waits
  poll, and a counter can step over an exact value between two polls.

## 5. Screenshot capture workflow (evidence)

- Capture at each claimed feature moment, driven by the same anchoring the
  tests use — `c64 until <label>` for assembly, a store watchpoint on a
  state byte for BASIC (§4). Capture while the machine is **stopped**:
  a screenshot taken while it runs is a race, and at warp the frame you
  wanted is long gone.
- **Where the PNGs go depends on the demo's tier.** A demo outside the
  test tier (`demos/invaders/`, `demos/1812/`) commits them to
  `demos/<name>/evidence/<feature>.png` (`--scale 2`). A test-tier demo
  commits nothing: its evidence is shown in the run, and the run itself is
  the deliverable. If a test demo's solution is worth keeping, graduate
  the program to `tests/programs/<name>/` where it becomes a regression
  test; that, not an evidence PNG, is the durable artifact.
- Committed evidence PNGs are small and load-bearing for review; they are
  not compared programmatically.

## 6. Deferred tooling

- **Pixel assertions (golden-image diff) are ruled out** (2026-07-30, on
  demo-02/04 evidence): across a sprite demo and a full arcade game,
  register+state assertions never proved insufficient. Reopen only if a
  future demo actually blocks on pixel assertions.
- **Charset/bitmap PNG conversion** is still open — `c64 sprite from-png`
  handles 24×21 sprites only. The decision waits on the first real
  consumer (the 1812 bitmap demo); tracked in docs/todo.md.
