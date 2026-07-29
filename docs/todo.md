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

## Decisions (maintainer)

- [ ] **Release timing for 0.8.0.** `pyproject.toml:7` (`version = "0.8.0"`),
      `CHANGELOG.md`'s `## [0.8.0]` heading and `README.md:185` ("Stable —
      current release **v0.8.0**") are coherent today.
      `.github/workflows/release.yml` triggers on `push: branches: [main]`, so
      pushing `main` arms the release workflow — there is no tag gate. To ship
      later, revert the bump as a unit (all three files together;
      `tests/test_package.py::test_changelog_has_current_version` enforces the
      pyproject↔CHANGELOG half and must stay green).

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

## Disk plan deferred items (one item still open)

Originally mirrored from `.superpowers/sdd/2026-07-24-disk-file-block-ops/progress.md`
(the disk file/block-ops plan's ledger, which is deleted when that plan
finishes). The deferred wave landed in two commits — `a7f6ba5` (core:
`disk.py`, `testing.py`, their tests) and `76f76b2` (surfaces: MCP/CLI minors,
counts, CHANGELOG) — plus a seam commit that finished the two front-end tokens
wave A could not reach; read those commits for what each item turned into,
including the two places measurement contradicted the item as written. One
item is still open.

- [ ] **c1541-dependent tests are invisible to CI.** The `needs_c1541` marker
      (`tests/test_disk_blocks.py:27`, `tests/test_disk.py:29`,
      `tests/test_disk_build.py:16`, `tests/test_mcp_disk.py:19`) skips when
      `shutil.which("c1541")` is None — measured today: 29 + 2 + 7 + 23 tests
      guarded. There is no CI test workflow at all
      (`.github/workflows/release.yml` only builds a dist), so c1541 drift is
      caught only on a developer machine with VICE installed. Fix direction
      open: install VICE in a CI job, or state the local-only contract
      explicitly. (Task 1's original wording — "the marker is dead in the test
      file" — is stale; later tasks applied it widely.)

## Observability gaps (demo-05 dogfooding, 2026-07-28)

Six items the debug-hunt run surfaced. They share a theme: the machine tells
the truth, but the *tooling that reports it* is either silent, misleading, or
undocumented at the exact moment a debugging agent needs it.

- [ ] **`c64 basic check` passes a statically-provable `?BAD SUBSCRIPT`.**
      `dim v(4)` followed by `for i=1 to 5: read v(i)` lints clean, then dies
      on the first line it executes. The pieces to catch it are already there:
      `_check_ranges` (`src/c64lib/basic_lint.py:512-524`) does exactly this
      class of literal-argument range analysis for POKE (`E150`), and
      `_check_loops` (line 381) already models FOR bounds — a narrow rule
      (literal DIM bound + literal FOR bounds + subscript is exactly the loop
      variable) would catch the classic 0-based/1-based DIM off-by-one.
      **Decide before building:** demo 05 *wants* this bug found at runtime as
      its first layer, so catching it statically changes what that demo
      teaches. Either accept that, or rule that check stays silent here
      deliberately and record the reason. Verify: `tests/test_basic_lint.py`
      plus a fixture pair under `tests/test_basic_lint_fixtures.py`.

## Standing backlog (pre-cartridge)

- [ ] **Dogfood the two remaining C64 demo prompts.** `demos/README.md:12-18`:
      demos 01-05 are ✅ dogfooded; 06-07 are 🔲 "awaiting C64 dogfood".
      01-06 were ported from the PET edition, where each passed a real
      dogfooding run; 07 (1812) was written for the C64 and has never been
      agent-run. Done = an agent given only this toolset builds and verifies
      the demo on a real VICE session, then the row's status flips.
      Demo 02 passed first try (2026-07-27); its solution graduated to
      `tests/programs/bouncing-ball/` and the friction it turned up is the
      0.7.0 section of the changelog.
      Demo 03 passed first try (2026-07-27): BASIC 933 jiffies vs 9.2 for
      the asm sieve, both `168 PRIMES, LARGEST 997`, ~101x. Its friction is
      the Unreleased section of the changelog; the solution has not
      graduated to `tests/programs/` yet.
      Demo 04 passed (2026-07-27): a ~700-line asm Snake with a custom
      charset, title/play/game-over state machine, `$CB` steering, SID
      blip/crash and a session-persistent high score, all proven live. It
      found two real defects (the ca65 phony-target dep parse and the
      `@row,col` re-resolve) plus the doc gaps in the Unreleased changelog
      section; the solution has not graduated to `tests/programs/` yet.
      Demo 05 passed (2026-07-28): all three layers found from the machine —
      `?BAD SUBSCRIPT ERROR IN 30`, then the `sys 828` wedge proven by
      sampling PC (pinned at `$0340`/`$0343`), `c64 rom disasm 828` showing
      `$0343 ea nop` where `inx` belongs, and a `c64 step` trace with X frozen
      at 0, then the PETSCII-vs-screen-code title read out of `$0400`. Fixed
      and re-proven with a passing `c64 test run` spec. It found no product
      defects; its friction is the "Observability gaps" section above.
- [ ] **Build the full annotated C64 ROM label DB.** Only a seed ships:
      `src/c64lib/data/rom_labels/basic2.lbl`, 44 `al C:xxxx .NAME` lines —
      the KERNAL jump table `$FF81`-`$FFF3`, the vectors up to `$FFFE`, and a
      few zero-page pointers (`$002B TXTTAB`, `$002D VARTAB`). Loaded by
      `romdoc.rom_labels` (`src/c64lib/romdoc.py:21-26`, keyed on BASIC
      version via `_LABEL_FILES`) and merged into label lookups at
      `cli.py:1667` and `mcp_server.py:886`. Licensing posture stated in
      `romdoc.py`'s module docstring: ship only annotations we authored (names
      and addresses); ROM bytes are read from the user's emulator at runtime
      and never enter the repo. Extend with BASIC/KERNAL internals in the same
      `.lbl` format `symbols.parse_labels` already reads.
- [ ] **Deferred spec items from §6 of
      `docs/superpowers/specs/graphics-and-sprites.md`.** Two of the three
      originally listed have since landed (the `c64 sprite` command group and
      relocation-aware screen reads — see that section's "Implemented since
      this spec was written" note, release 0.2.0). What remains is
      **sprite-aware screenshot diffing** = §6's "pixel-assertion tooling
      (golden-image diff with tolerance)", which the spec says to revisit only
      if register+state assertions prove insufficient in practice. Re-scope
      against current needs before starting.
- [ ] **Charset/bitmap PNG conversion.** `c64 sprite from-png`
      (`src/c64lib/cli.py:1931`, via `sprites.sprite_from_image`) handles 24×21
      sprites only. This is the other still-open bullet in §6 of
      `docs/superpowers/specs/graphics-and-sprites.md`. Needs a target-format
      decision first — 8×8 charset cells versus a full 320×200 hires /
      160×200 multicolor bitmap plus screen and color RAM — since the two
      imply different outputs and different verification.
- [ ] **`c64 sprite encode` exits 2 on a missing `FILE` while `c64 sprite
      from-png` exits 1.** `sprite_encode` (`cli.py:1962-1963`) declares
      `click.Path(exists=True, dir_okay=False)`, so Click raises `UsageError`
      → exit 2; `sprite_from_png` (`cli.py:1931-1932`) declares a bare
      `click.Path()`, opens the path itself and calls `fail()` on
      `FileNotFoundError` (`cli.py:1949-1953`) → exit 1. Flagged during the
      sprite-encode work as "pre-existing house pattern, accepted" and never
      adjudicated; `tests/test_cli_sprite.py::test_sprite_encode_missing_file`
      (line 254) only asserts non-zero, so either convention passes today.
      Decide one convention repo-wide, then tighten the test.
- [ ] **The YAML test DSL spells the same substring check two ways:
      `wait: {text: ...}` but `assert: {screen: ...}`.**
      `src/c64lib/testing.py:447` takes `text` for a wait, `:478` takes
      `screen` for an assert, and `:569` rejects `assert: {text: ...}` with
      "assert step needs 'screen', 'mem', or 'reg'". Both read the decoded
      screen and both do a substring test, so the natural move after
      writing a `wait` — copy the line, change the verb — fails, which is
      exactly how it was hit while adding the demo-03 cookbook recipes.
      `mem` is spelled the same in both, which makes `text`/`screen` read
      as an oversight rather than a distinction. Cheapest fix: accept
      `text` as an alias in `assert` (and/or `screen` in `wait`), keeping
      both spellings working, then say so in the `c64 test run` step table
      in `docs/cli.md:1197-1230`. Decide whether one spelling becomes
      canonical in the docs or both stay first-class.
