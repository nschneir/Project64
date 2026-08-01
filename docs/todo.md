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
three-iteration fidelity audit (`demos/invaders/AUDIT.md`). The CLI, skills,
and cookbook findings all landed (what was done is in `CHANGELOG.md` and git
history); only the process items below remain.

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
      `docs/graphics-and-sprites.md` (the pixel-assertion
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
      hit was ASCII art, not image input; it was split out and has since
      landed as `c64 charset encode`. This item is now about *image*
      conversion only.

