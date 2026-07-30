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
      defects; the six observability gaps it did find are closed in the
      Unreleased section of the changelog.
- [ ] **Next tranche of the ROM label DB.**
      `src/c64lib/data/rom_labels/basic2.lbl` is 184 `al C:xxxx .NAME` lines
      after the first curated tranche: the interpreter and editor
      paths a debugging agent actually lands on — 78 zero-page cells
      (`CHRGET`/`CHRGOT`/`TXTPTR`, the `$2B`-`$4A` pointer block, FAC1/FAC2,
      the screen-editor and KERNAL I/O bytes), 39 BASIC ROM entries
      (`READY`/`MAIN`/`NEWSTT`/`GONE`, `ERROR`, `FRMEVL`, the `CHKCOM`
      family, `GETADR`/`GIVAYF`/`FOUT`), and 67 KERNAL (the jump table plus
      `RESET`/`NMI`/`IRQMAIN`/`KEYSCAN`/`BASIN`/`BSOUT`, and `INLOOP`, the
      direct-mode loop `ops.IDLE_PC_RANGE` watches). Still missing, in rough
      order of usefulness: the **BASIC token and statement dispatch table**
      (`$A00C` statement vectors, `$A052` function vectors, `$A09E` keywords,
      and the statement handlers they point at), the **floating-point
      package** (`$B7xx`-`$BFxx` arithmetic and transcendentals — start by
      adopting the ten rows `references/kernal-routines.md` already documents
      and verified: `MOVFM`, `MOVMF`, `FADDT`, `FSUBT`, `FMULTT`, `FDIVT`,
      `FPWRT`, `SIGN`, `ABS`, `INT`), and
      **tape/serial internals** (`$ED09`-`$EE13` IEC, `$F49E` LOAD /
      `$F5DD` SAVE and their tape paths). Same file, same format
      `symbols.parse_labels` reads, loaded by `romdoc.rom_labels`
      (`src/c64lib/romdoc.py:21-26`, keyed on BASIC version via
      `_LABEL_FILES`) and merged into lookups at `cli.py:585`, `cli.py:1748`,
      `mcp_server.py:269` and `mcp_server.py:942`. Licensing posture stated
      in `romdoc.py`'s module docstring and binding on every tranche: ship
      only annotations we authored (names and addresses); ROM bytes are read
      from the user's emulator at runtime and never enter the repo — so
      **every new address is verified against the live machine**, not copied
      (`c64 disasm <NAME> 8`, or a memory read for zero page), and anything
      that does not check out is dropped rather than guessed at.
      Two tests gate a tranche:
      `test_romdoc.py::test_label_file_hygiene` (format, uniqueness, address
      order, legal ranges) and
      `test_docs_rom_basic.py::test_label_db_is_documented`, which requires
      every name to be written up beside its address in
      `references/kernal-routines.md` (ROM) or `references/zero-page.md`
      (zero page) — budget the doc rows with the labels. Verify with
      `.venv/bin/pytest tests/test_romdoc.py tests/test_docs_rom_basic.py -q`
      plus a live `.venv/bin/c64 disasm <NEW_NAME> 8` for each name added.
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
