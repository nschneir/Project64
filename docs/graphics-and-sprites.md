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

Mid-frame register changes are **in scope when the demo exposes counters a
test can assert on**. Warp mode and nondeterministic stop points make the
*moment* a test observes unpredictable; they do not make the machine's
**state** unpredictable, and state is what these effects leave behind. A
raster-IRQ sprite multiplexer and a single-register split (`$D016`, `$D021`,
`$D018`) both qualify, provided the program publishes bytes that decide the
claim: how many objects the multiplexer placed, an overflow count that must
stay zero, a mismatch counter that catches a handler running late.
`demos/la-galaxia` is the worked example: it runs a raster-IRQ sprite
multiplexer and a `$D016` split confined to the formation band, and its
`test.yaml` settles both under `--warp --headless` by asserting
`mux_overflow` and `tick_overrun` are zero — bytes the program keeps, not a
frame someone looked at.

Still out of scope: an effect whose only evidence is a photograph. If the
claim can only be settled by looking at a captured frame — a stable FLI or
AGSP display, an open border, a plasma — there is nothing for a test to
assert, and a green run means nothing. The dividing line is not the
technique's difficulty; it is whether a failing implementation would produce
a failing *number*.

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
  on the read value), `$D020/$D021` (colors), color RAM at `$D800`
  (**4-bit readback — compare masked**, `and: "$0f"`), and the demo's own
  state bytes. This is what tests assert. Screen reads are relocation-aware:
  `c64 screen` and `@row,col` follow `$DD00`/`$D018` to wherever the
  VIC-II put the screen; color RAM stays `$D800`, and `@@row,col` addresses
  it directly (same row/col, fixed base). Bitmap-mode demos: the cookbook's
  "Multicolor bitmap" recipe is the worked example (mode bits, address
  arithmetic, masked span fill).
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
                                               # a cell's color: color RAM
                                               #   reads back 4-bit, mask it
  - wait:   { text: "GAME OVER" }              # HUD line in screen RAM
                                               #   (normal video —
                                               #   reverse-video headings
                                               #   need codes)
  ```

- Motion is tested by sampling: `until` a frame anchor, `sample` a
  register under a name, `until` again, `assert ... differs` (or
  `greater_than`/`less_than` when the program documents direction, or
  `unchanged` for the opposite claim — a hold or pause state where the
  counter must **not** move) — the runner supports this natively; see
  `c64 test run` in docs/cli.md and `tests/programs/sprite-ball/test.yaml`
  for the worked example. Collision behavior is tested through the demo's
  own state change (lives byte decremented), not by trying to force
  `$D01E` timing.
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
- **A per-frame budget is measured by the program, not by the harness.** If
  the quantity resets every frame — cells redrawn, sprites repositioned,
  cycles spent in the tick — then the *program* keeps the high-water mark
  and the test reads that mark, the way `demos/la-galaxia` already does with
  `tick_endline`. A sampler is the wrong instrument at any rate short of
  every frame: the value spikes only on the frames that do the expensive
  thing, so a coarser sampler steps over them and reports a comfortable
  number that means nothing. La Galaxia's own dogfood is the case: its
  redraw counter, sampled every tenth tick, read **4** against a ceiling of
  64, while the mark the program kept read **88**.
  Two things a mark needs to be evidence:
  - **Scope it to a window.** A lifetime mark carries every exempt frame
    ever run. Ceilings are usually written with carve-outs — La Galaxia's is
    "at most 64 cells per frame *outside a stage transition*", and its
    screen rebuilds legitimately reach 72-88 — so zero the mark, run the
    window the claim is about, then read it, and assert the state byte that
    proves the run stayed inside that window.
  - **Keep the mark saturating and monotone**, so the read cannot race the
    program: `at_most` against a ceiling, `at_least` for a floor.
  `demos/la-galaxia/evidence/mux.txt` is the worked capture and its
  `test.yaml` the worked assertion.

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

### The shape of an evidence script

`demos/invaders/tools/evidence.sh` and `demos/ms-muncher/tools/evidence.sh`
are the same protocol, written twice, each time by rediscovering the same
rules the hard way. A demo that commits evidence should ship a script that
regenerates all of it in one command, and it should follow these five:

| Rule | Why |
|---|---|
| One `run`, then `until <anchor> --count N` before every capture | At warp a screenshot of a running machine is a race. `until` parks it on an exact frame, and inspection never advances it — so the same script produces the same frames every time. |
| Never `wait --mem/--text` straight after an `until` | A wait polls and **does not resume**. After `until`/`step`/`finish`/`wait --break` the machine is stopped, so the wait can only time out. Use another `until`, or `c64 continue` first. |
| Stage unreachable states by poking the program's own state bytes | Cheaper and far more repeatable than playing to them — and they are the same bytes the YAML spec asserts on, so the evidence and the regression test agree by construction. |
| Use `c64 call` only as the final action before a capture, then `run` again | The call's fake return address replaces the program's control flow; that run is over. A following `until` will time out on a label nothing executes any more, and it looks exactly like a wedged machine. |
| A capture that needs a key uses `key hold KEY --at <anchor>` | `key type` fills the type-ahead buffer, which a game reading the live matrix code at `$CB` never looks at. |

The two helpers are worth stealing verbatim — one line each, and every
capture in the file reads as a single verb:

```sh
C=".venv/bin/c64"; S="-s mmev"
shot()  { $C screen --png "$OUT/$1.png" --scale 2 $S >/dev/null; echo "  $1.png"; }
ticks() { $C until tick --count "$1" --timeout 120 $S >/dev/null; }
```

A staged capture then reads as the claim it is making. This one is the
fourth maze, which would take ten boards of play to reach:

```sh
$C run $SRC $S >/dev/null          # a fresh run: the last call ended the one before
ticks 400                          # the attract demo is playing by now
$C mem write board 10 $S >/dev/null
$C call newboard $S >/dev/null     # ... and nothing after this but the shot
shot maze4
```

## 6. Deferred tooling

- **Pixel assertions (golden-image diff) are ruled out** (2026-07-30, on
  demo-02/04 evidence): across a sprite demo and a full arcade game,
  register+state assertions never proved insufficient. Reopen only if a
  future demo actually blocks on pixel assertions.
- **Charset/bitmap PNG conversion is closed as not needed** (2026-08-02, on
  demo-07 evidence): the first real consumer — the 1812 bitmap demo —
  never wanted a PNG-to-bitmap converter. Every shape is generated
  geometry, and every table ships as commented `.byte` rows emitted by a
  generator script (`demos/1812/tools/gentables.py`), which is what the
  authoring policy (§2) asks for anyway. What a bitmap demo *does* need is
  the opposite direction — reading the finished bitmap back to count lit
  pixels and checksum the canvas — and `c64 mem read --json` piped into a
  small stdlib script covers that completely (worked example:
  `demos/1812/tools/litcount.py`). `c64 sprite from-png` (24×21 sprites)
  is unaffected. Reopen only if a demo arrives with source imagery it must
  convert, and re-scope from what that demo actually needs.
