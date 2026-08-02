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

## Deferred from the 2026-08-01 dogfood-fixes review

- [ ] **`c64 disk block write` lacks the byte-list ergonomics `mem write`
      gained.** `disk_block_write` (`src/c64lib/cli.py`, the
      `block_bytes(parse_number(v) for v in values)` site) is guarded — no
      traceback — but gets neither the whitespace-joined-string acceptance
      nor the per-index "which byte was bad" naming that `mem write` and
      `mem find` now get from `ops.parse_byte_values`. Fix direction: route
      it through `parse_byte_values`, keeping `block_bytes`'s 256-byte
      length check. Verify: `tests/test_cli_disk.py`.
- [ ] **`c64 profile` has no impossible-count guard.** A raw cascade count
      of 0 cannot happen for a real routine (a bare `RTS` costs 6 cycles),
      yet `_CIA_START_SLACK` would dress one up as `"cycles": 3`. It would
      mean the CIA pokes never reached the chip model (e.g. a future VICE
      change, or I/O banked out so `$DD0E` wrote to RAM underneath) — a
      silent wrong number rather than an error. Fix direction: treat
      `raw == 0` in `profile_routine` (`src/c64lib/ops.py`) as a failure
      naming the likely cause, not a measurement. Verify:
      `tests/test_ops.py -k profile`.

## From the 2026-08-01 Snake dogfood

Six items the Snake run hit (`demos/snake/`, audit in `demos/snake/AUDIT.md`).
None blocked the run; each cost a debug cycle that the docs or the CLI could
have saved.

- [ ] **`c64 key hold --frames 0` reports a timeout and blames a checkpoint
      that was never armed.** `key_hold` (`src/c64lib/ops.py:645`) loops
      `for i in range(frames)` and returns the initial `{"registers": None}`
      when `frames` is 0; `cli.key_hold` (`src/c64lib/cli.py:1995`) reads that
      as a timeout and fails with "only 0/0 frame(s) reached … machine left
      RUNNING, checkpoint removed" — but nothing ran, nothing was set, and
      nothing was removed. A computed hold length of zero is ordinary in a
      scripted protocol (`demos/snake/tools/evidence.sh` guards every call in
      shell for exactly this). Fix direction: make 0 a no-op that returns
      `{"frames": 0, "requested": 0}` with the machine untouched, or reject it
      at the click layer saying so. Verify: `tests/test_cli_key.py`,
      `tests/test_ops.py -k hold`.
- [ ] **`@row,col` has no colour-RAM twin.** The cell reference resolves to
      screen RAM only (`src/c64lib/ops.py`, the `@` branch of the address
      parser), so asserting the *colour* of a cell means hand-computing
      `$D800 + row*40 + col`. `docs/graphics-and-sprites.md` §3 makes colour
      RAM ground truth for assertions and the demos write it alongside every
      character, so this is the common case, not an edge one — Snake's
      `test.yaml` and `tools/evidence.sh` both do the arithmetic by hand, and
      a stale constant produced a false FAIL mid-run. Fix direction open: a
      `@@row,col` form, or `--color` on `mem read`/`mem get`, resolving
      through the same relocation-aware path. Verify: `tests/test_ops.py -k
      addr`, `tests/test_cli_mem.py`, and the YAML `mem:` step.
- [ ] **Colour RAM's 4-bit readback is undocumented where the VIC-II
      registers' is.** `skills/c64-development/SKILL.md` warns about it twice
      — the "Common pitfalls" bullet and the diagnosis table row — and both
      name only `$D020`/`$D021`. `$D800-$DBE7` behaves identically: a cell
      written 13 reads back `$FD`. `docs/graphics-and-sprites.md` §3 lists
      colour RAM as assertion ground truth with no caveat, and §4's example
      asserts show no mask. Fix: extend both pitfall entries to name colour
      RAM, and add a masked colour-RAM assert to §4's allowed shapes. Verify:
      `tests/test_docs_skills.py`, plus a live write-then-read.
- [ ] **The cookbook's "the move that ends the game can never be driven by
      `key hold`" is true only for a play-loop anchor.** The claim sits under
      the held-key recipe in `references/cookbook.md` and is stated
      absolutely. It holds when the anchor label lives inside the play loop —
      but not when the tick is shared: Snake's `mainloop` runs in title, play
      and game-over alike, so `key hold d --at mainloop --frames 1` drives the
      fatal move and comes back stopped with the game-over screen already
      drawn. Fix: qualify the claim, and recommend the shared-tick shape,
      which makes every state drivable from one anchor and one `until`.
      Verify: `tests/test_docs_cookbook.py`.
- [ ] **`c64 call` and `c64 profile` don't say the interrupted program is
      unrecoverable.** `docs/cli.md` says the machine "ends **STOPPED** at
      the trap" for both, which reads as ordinary stopped state — but the
      synthetic return address means the program that was running is gone,
      not paused. A `call:` step in the middle of a YAML spec therefore kills
      every step after it: in Snake's spec the next `until` timed out with the
      machine back at `READY.`. Fix: say it plainly in `### c64 call`,
      `### c64 profile`, and the `call:` line under `### c64 test run`, with
      the rule — put `call:` steps last, or in a spec of their own. Verify:
      `tests/test_docs_cli.py`.
- [ ] **Reverse-video text is invisible to `wait --text`, and custom glyphs at
      128+ make reverse video unusable at all.** Two joined facts a game meets
      together, and neither is written down. `c64 screen` decodes reverse
      space to a block, so `wait --text "GAME OVER"` cannot match a
      reverse-video heading (Snake asserts its nine screen codes instead).
      And screen codes 129-154 are reverse A-Z, so a charset that patches
      there — as the cookbook's custom-character-set recipe does at 96/97,
      and as Snake first did at 128-139 — makes reverse-video text draw game
      objects. Snake moved its glyphs to 112-123 for that reason. Fix: one
      line in the SKILL's custom-charset pitfall (which already covers codes
      32/96/224 decoding blank) and one in the cookbook recipe. Verify:
      `tests/test_docs_skills.py`, `tests/test_docs_cookbook.py`.

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

