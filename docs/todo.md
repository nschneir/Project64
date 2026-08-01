# TODO

Open items carried out of the `.crt` cartridge support work (2026-07-26) plus
the standing project backlog. Items are deleted as they land — what was
actually done is recorded in `CHANGELOG.md` and in git history, so this file
stays a list of work still open.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

## Cartridge follow-ups

- [ ] **EasyFlash window configs have no BSS/RAM area.** `ef_window_config`
      (`src/c64lib/cart_build.py:682`) emits `ZP` + `ROM` (+ `JT` for lo, `VEC`
      for the boot window) and no `RAM:` line or `BSS:` segment in any of its
      three branches, so `.segment "BSS"` will not link in an EasyFlash bank.
      Deliberate for now: the `.org`-based resident block at `$0900` needs
      none, and where per-bank RAM should live after the `$DE02 = $87`
      16K-mode switch is an open design question. Contrast
      `cart_linker_config` (line 79) and `wrap_linker_config` (line 132),
      which both call `_ram_area()` (line 73) and map `BSS -> RAM`.
- [ ] **`wrap_prg` still accepts ML load addresses in `$A000-$BFFF` (8k),
      `$D000-$DFFF`, and `$E000-$FFFF`.** `wrap_prg`
      (`src/c64lib/cart_build.py:501`) rejects only programs overlapping the
      mapped window — `if load_addr <= win_end and prog_end > ROML_START`,
      where `win_end = ROML_START + ct.image_bytes - 1` (~line 578). Everything
      above that window passes, so the launcher copies under BASIC ROM / I/O /
      KERNAL and then jumps into what reads back as ROM: the same silent
      dead-cart class as the fixed `$8000-$9FFF`/window case. (A BASIC-kind
      program on a 16k cart is already refused separately, ~line 564.) Fix
      direction open — widen the guard, or document the ranges as caller
      responsibility. Verify: `tests/test_cart_build.py`, `tests/test_cli_cart.py`.
- [ ] **`src/c64lib/build.py` starts the ZP memory area at `$0000`** —
      `linker_config()` line 45 emits `ZP: start = $0000, size = $0100;`, so
      the first two zero-page variables an ordinary (non-cart) program declares
      land on the 6510 port registers `$00`/`$01`; writing `$01` re-banks the
      machine under the running code. The cart linker configs were fixed to
      `start = $0002, size = $00FE` (`cart_build.py:62`, `_ZP`, with the
      reasoning in the comment above it); `build.py` should match — note the
      size shrinks too. Verify: `tests/test_build.py`,
      `tests/test_integration_build.py`.

## Invaders dogfood results

Friction found by the demo-06 dogfood (2026-08-01), which built
`demos/invaders/` from `demos/invaders/PROMPT.md` — a ~5.3 KB pure-asm arcade
game across ten `.include`d sources, with a custom multicolor charset,
hardware sprites, three-voice SID, an 82-step `c64 test run` spec and a
three-iteration fidelity audit (`demos/invaders/AUDIT.md`). One real defect
shipped *into* the demo because of the sprite-Y item below; everything else
is tooling ergonomics. Ordered CLI, then skills, then cookbook, then process.

A fifteenth finding is already closed and is not listed: the "ship it" step
of a directory demo produced a `.d64` the repository threw away, because
`.gitignore` ignored `*.prg`/`*.d64` unconditionally. It now carves out
`demos/*/*.prg` and `demos/*/*.d64` (and nothing else — the `.lbl` and every
`tests/programs/` build output stay ignored), so `demos/invaders/invaders.d64`
ships beside its sources.

### CLI

- [ ] **`-s/--session` is rejected after the subcommand, and the error names
      the wrong flag.** `c64 mem get basex 1 --session inv` fails with
      `Error: No such option '--session'. Did you mean '--json'?` — but
      `--json` is the one option explicitly accepted in *both* positions
      (`cli.py`'s group help says so), so the suggestion sends you looking at
      output formatting instead of argument order. The group help does say
      "Must come before the subcommand"; the error does not. Fix direction
      open: either accept `-s/--session` on subcommands the way `--json` is
      accepted, or make the message say where the option belongs. Verify:
      `tests/test_cli.py`.
- [ ] **An unparseable byte value in `c64 mem write` dumps a Python
      traceback.** `c64 mem write score "0 0 1 4 9 0"` ends in a ~20-line
      stack terminating at `parse_number` (`src/c64lib/ops.py:80`)
      `ValueError: invalid literal for int() with base 10`. Every other bad
      input in the CLI is a clean `error:` line; this one leaks the
      implementation. Fix: catch it at the `mem_write` boundary
      (`src/c64lib/cli.py:503`) and raise a usage error naming the offending
      token. Cheap adjacent win while in there: accept one whitespace-
      separated string as a byte list, since that is what a shell variable
      expands to and zsh does not word-split unquoted expansions. Verify:
      `tests/test_cli.py`.
- [ ] **`mem get --json` returns `values`, `mem read --json` returns
      `bytes`.** Two near-identical commands, two key names for the same
      concept (`{"addr", "values"}` versus
      `{"addr", "length", "hex", "bytes", "text_encoding"}`). A script
      written against one silently `KeyError`s against the other, which reads
      as a tool bug. Fix direction open: alias one key into the other's
      payload, or say plainly in `docs/cli.md` that `mem get` is the
      print-formatting variant with its own shape. Verify:
      `tests/test_cli.py`, `docs/cli.md`.
- [ ] **There is no cycle counter, and the demo prompts ask for one.**
      `demos/invaders/PROMPT.md` requires "know the cycle cost of your
      per-tick invader update"; the only instrument is `LIN`/`CYC` from
      `c64 reg` (raster line + cycle within it), so measuring a routine means
      `until` → read → `finish` → read → `LIN*65+CYC` → handle the frame
      wrap by hand. Worse, the KERNAL IRQ lands inside the window silently:
      the dogfood measured `marchstep` at 396 cycles three times and then
      1695 once, with nothing in the output to distinguish a clean sample
      from an interrupted one, and separately measured a whole frame at 226
      cycles when the true figure was 1179 (the misleading-`until` item under
      Skills below). Fix direction: expose the emulator's total cycle count as a
      monotonic field on `c64 reg` — the delta then needs no wrap handling
      and an IRQ shows up as an obvious outlier — or add a `c64 profile REF`
      that reports cycles between a label and its `rts`. **Highest-value CLI
      gap this dogfood found.** Verify: `tests/test_cli.py` plus a live
      measurement of a known-cost routine.
- [ ] **`c64 disk boot` registers no symbols, but a cartridge does.**
      Proving the *shipped* artefact means booting the `.d64` in a fresh
      session — which is exactly when `until mainloop` and
      `key hold --at mainloop` stop working, because a disk boot loads no
      label file and both need a symbol or an address. The dogfood had to
      read `mainloop`'s address out of `invaders.lbl` by hand and anchor on
      `$0824`. The test-spec path already solves this for the other format:
      per `docs/cli.md`, a ready-made `.crt` picks up a sibling `.lbl` of the
      same stem. Fix: do the same for `c64 disk boot IMAGE` (and for
      `c64 session start --disk`), picking up `IMAGE`'s sibling `.lbl` when
      one exists and staying silent when it does not. Verify:
      `tests/test_cli_disk.py`.
- [ ] **`c64 session start --disk` attaches without autostarting, and
      `c64 disk boot` then wants the image named again.** Not wrong, but the
      pairing reads as redundant the first time. Doc-level fix: one line
      under `c64 session start` saying `--disk` attaches only, and that
      `c64 disk boot IMAGE` is what starts it. Verify: `docs/cli.md`.

### Skills

- [ ] **Nothing documents the sprite-Y ↔ text-row mapping, and what is
      documented invites an off-by-one.** `references/hardware.md:119` says
      "Visible X range starts at 24, Y at 50" and
      `skills/6502-assembly/SKILL.md:189` says "Y is in the visible range
      **50-249**" — both of which read as `Y = 50 + 8*row`. The 25-row
      display window actually starts at **raster 51**, so it is
      `Y = 51 + 8*row`. The dogfood shipped the mystery UFO one raster line
      high; its dome sat on the bottom pixel row of the HUD text and survived
      a whole audit iteration, because "off by one raster line" is invisible
      until a sprite lands next to text. The same constant skewed the shot's
      row calculation. Fix: one line in `references/hardware.md` under
      Sprites — "sprite Y for text row R is `51 + 8*R`; the 25-row window
      spans rasters 51-250, so a sprite at Y=50 is one line *above* row 0" —
      and the same note beside the 6502-assembly skill's visible-range
      bullet. Verify: inspection, plus the live check in
      `demos/invaders/AUDIT.md` iteration 2.
- [ ] **`.include` behaviour under `c64 build` is undocumented.** The
      6502-assembly skill warns that segment state leaks across `.include`
      (correct, and it earned its place — the invaders build put an explicit
      `.segment "CODE"` at the top of all nine includes and never hit it),
      but never says whether `c64 build` resolves include paths relative to
      the *source file* or the CWD. For a ten-file program that is
      load-bearing, so the dogfood spent a round trip building a throwaway
      two-file program to find out. Fix: one sentence in
      `skills/6502-assembly/SKILL.md` beside the segment-state gotcha —
      "`.include` resolves relative to the including file; `c64 build` needs
      no `-I`". Verify: inspection.
- [ ] **`c64 call` is framed as a debugging tool, never as a testing
      technique.** It appears in `skills/6502-debugging/SKILL.md:103,152`
      under "audit by isolation" and in `skills/6502-assembly/SKILL.md:233`
      under Debugging — both symptom-driven framings, for when something is
      already wrong. The single highest-leverage thing the dogfood did was
      the opposite: *unit-testing routines against a live machine before
      anything was wrong*. `ufoscore` was proven at shot counts 1/5/8/22/23/
      24/37/38/39/52/53 in one loop; proving the arcade's 23rd-shot secret by
      actually firing 23 shots into a moving saucer would have taken hours.
      `addscore` was proven across the digit-carry chain and both sides of
      the 1500-point boundary; `newwave` across waves 1/2/5/9/10/11/18/19.
      The `c64-development` skill's "Verifying a change" section offers only
      `wait --text` and whole-program YAML specs. Fix: name routine-level
      unit testing there as a first-class option, with `c64 call` and the
      YAML `call:` step beside it. Verify: inspection.
- [ ] **`c64 until LABEL` can succeed misleadingly, and only the timeout
      case is documented.** The `c64-development` diagnosis table covers "the
      program branched away and never executes LABEL again → times out".
      The case that actually bit: the game was in a state whose dispatch does
      not call `marchstep`, so `until marchstep` ran forward an *unknown*
      number of frames and returned a perfectly plausible raster position —
      yielding a whole-frame cost of 226 cycles for work that really costs
      1179. It does not fail; it answers a different question. Fix: a row in
      the diagnosis table — "`until LABEL` returned but the numbers are
      nonsense → the current state does not reach LABEL every tick, so you
      landed an arbitrary number of frames later; check the state byte before
      anchoring". Verify: inspection.

### Cookbook

- [ ] **No recipe for screen-code readback as a collision mechanic.** Every
      character-mode game needs "what is in the cell I am moving into?", and
      the invaders build wrote it from scratch: read the screen byte at the
      bolt's row/column and dispatch on glyph-code ranges (invader / shield /
      bomb / blank). It is cheaper than the VIC-II collision latches,
      deterministic under a debugger, and — unlike `$D01E`/`$D01F` — it says
      *which* object was hit, which is what scoring needs. It is also the
      argument every graphics demo ends up re-deriving against the latches
      (`demos/invaders/AUDIT.md` deviation 2 spends a paragraph on it). Fix:
      a ~30-line assembly recipe in `references/cookbook.md`, cross-linked
      from the hardware reference's collision-latch gotchas. Verify: the
      recipe runs as a `tests/programs/` entry like the others.
- [ ] **No charset equivalent of `c64 sprite encode` — and PNG is not the
      gap.** `c64 sprite encode` is the model: ASCII art in, `.byte` rows
      out, and the invaders build's four sprites took one command. For the
      *charset* the demo had to ship `demos/invaders/tools/charset.py` (123
      lines: a legend, a validator, a packer) plus its own art format. The
      standing-backlog item below scopes the remaining work as charset/bitmap
      **PNG** conversion, but PNG was never what a hand-authored multicolor
      charset needed — **ASCII art → charset** was, in the same input format
      `sprite encode` already parses. Fix direction: `c64 charset encode`
      taking `.`/`1`/`2`/`3` for the four multicolor pair values (background,
      `$D022`, `$D023`, cell colour), 8 rows of 4 characters per glyph,
      emitting 8 `.byte` rows per glyph — which would delete every line of
      that demo-local tool. Note this narrows the standing-backlog item
      below: it is about *image* input, and this is not. Verify:
      `tests/test_sprites.py` alongside the `sprite encode` cases.

### Process and repo

- [ ] **`superpowers:writing-plans` defaults to a gitignored directory.**
      `.gitignore` ignores `docs/superpowers/`, but the skill's documented
      save path is `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`, so a
      plan written at the default location can never be committed. The
      invaders run was told to put its plan in the demo directory and did
      (`demos/invaders/PLAN.md`); the next agent will not be. Fix: a line in
      `AGENTS.md` saying plans that are meant to survive go beside the work,
      not under `docs/superpowers/`. Verify: inspection.
- [ ] **`superpowers:writing-plans`' no-placeholders rule scales badly for
      assembly.** "Every step must contain the actual content" plus "code
      blocks required for code steps" means transcribing a 5.3 KB 6502
      program into the plan before writing it — doubling the work and going
      stale within the hour. What actually carried the invaders build was the
      *interface* half of the plan: exact label names, the byte-level
      variable table, the glyph-code allocation, the memory map, and one
      verification command per task. Fix direction open, and it is a
      Superpowers-side change rather than a repo one: distinguish "a plan for
      an engineer you will never speak to" from "a plan you will execute
      yourself next", and let the second lean on interfaces over bodies.
      Verify: inspection.

## Standing backlog (pre-cartridge)

- [ ] **Charset/bitmap PNG conversion — blocked on demo-07 evidence.**
      `c64 sprite from-png` (`sprite_from_png` in `src/c64lib/cli.py`, via
      `sprites.sprite_from_image`) handles 24×21 sprites only; charset and
      bitmap conversion is the one bullet still open in §6 of
      `docs/superpowers/specs/graphics-and-sprites.md` (the pixel-assertion
      bullet beside it was ruled out 2026-07-30). What blocks it is a
      target-format decision — 8×8 charset cells versus a full 320×200
      hires / 160×200 multicolor bitmap plus screen and color RAM — and the
      two imply different outputs and different verification. Don't rule it
      from first principles: demo 07 (`demos/1812/PROMPT.md`, multicolor
      bitmap, still the one 🔲 row in `demos/README.md`) is the first real
      consumer, so the decision waits on it. Fix direction: when that run
      completes, re-scope this item from what it actually needed out of a
      PNG — and close it if it needed nothing. Verify: inspection.
      Narrowed 2026-08-01 by the invaders dogfood: the charset gap that run
      hit was ASCII art, not image input, and is filed separately above as
      `c64 charset encode`. This item is now about *image* conversion only.

