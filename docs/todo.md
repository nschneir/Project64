# TODO

Open items carried out of the `.crt` cartridge support work (2026-07-26) plus
the standing project backlog. Strike items as they land.

## Decisions (maintainer)

- [ ] **Release timing for 0.5.0.** `pyproject.toml`, `CHANGELOG.md`, and
      `README.md` are coherent at 0.5.0; pushing `main` arms the release
      workflow. Revert the bump as a unit to ship later.

## Cartridge follow-ups

- [ ] **EasyFlash window configs have no BSS/RAM area.** Deliberate for now
      (the `.org`-based resident block needs none, and the design question —
      where per-bank RAM should live after the 16K-mode switch — is open).
      Wrapped and native single-region carts do get a BSS area.
- [ ] **`wrap_prg` still accepts ML load addresses in `$A000-$BFFF` (8k),
      `$D000-$DFFF`, and `$E000-$FFFF`** — the launcher copies under
      BASIC ROM / I/O / KERNAL and then jumps into what reads back as ROM.
      Same silent-dead-cart class as the fixed `$8000-$9FFF`/window case.
- [ ] **`src/c64lib/build.py` starts the ZP memory area at `$0000`** for
      ordinary (non-cart) programs — the first two zero-page variables land on
      the 6510 port registers `$00`/`$01`. The cart linker configs were fixed
      to `$0002`; `build.py` should match.
- [ ] **Version-coherence test.** Assert `README.md`'s release line matches
      `pyproject.toml`'s `version` (parse, don't hard-code — survives a
      revert). Suggested home: `tests/test_docs_readme.py`.

## Accepted behavior (documented, revisit only if it bites)

- [x] Stale `.crt`/`.bin` beside the output path after a failed rebuild —
      consistent with `build_asm`'s `.prg`/`.lbl` behavior; now documented in
      `docs/cli.md`.
- [x] `index.html` tool count and missing cartridge card — fixed (55 tools,
      CARTRIDGES card added).

## Test health

- [ ] **`tests/test_integration_debug.py::test_symbolic_debug_loop` flakes
      under load** (breakpoint-never-hit; two sightings, both under parallel
      load/coverage tracing; passes standalone and in plain full runs).
      Pre-existing, non-cart. Needs its own investigation.
- [ ] **`tests/test_integration_disk.py::test_disk_attach_at_launch` flaked
      once in a full run** (boot-keyboard artifact during the 0.4.0 release
      run; passed 2/2 in isolation and is untouched by the changes it was
      seen under). Carried out of the demo-01 ledger; no retry/xfail guard
      exists today.

## Disk plan deferred items (in-flight — the plan's deferred wave owns these; strike when it lands)

Mirrored from `.superpowers/sdd/2026-07-24-disk-file-block-ops/progress.md`, the
authoritative ledger for the disk file/block-ops plan. Every line below is already
scheduled for that plan's own deferred-fix wave before it finishes — this is a
visibility copy, not standing backlog and not a maintainer decision queue.

- [ ] **Sweep every remaining `# Measured:` claim in `disk.py` and its tests.**
      Named a DEFERRED WAVE ITEM by the Task 3 fixer: three drift findings across
      two tasks makes this a class, not incidents. One known contradiction to
      resolve in the sweep — the `_FAILURE_TEXT` comment "none of which change the
      exit code" versus the measured floppy-read-failed `rc 1`.
- [ ] **Decide/implement `.lbl` labels persistence for asm-built disks.** Task 5
      reviewer ruling: deferrable because the `labels` key is additive and a user
      can `c64 build` separately. Task 8 carries the caveat; the wave owns the
      decision — build labels separately in the spec flow, or extend `build_disk`
      with an additive `labels` key.
- [ ] **Neutral lead-in for non-ENOENT `OSError`s** (one sweep covers both
      sightings): Task 3's broadened catch reports "no such file" even for
      `EACCES`, and Task 4's "no such image to validate" overclaims the cause the
      same way.
- [ ] **`cbm_lookup_name` upper-cases per character.** `'ß'` raises `TypeError`
      instead of `DiskError`; `'ı'`/`'ſ'` uppercase into range and pass through.
      Fix = case the whole string, then `ord(ch)`, matching `cbm_title`'s idiom.
- [ ] **`get_file`'s `name` is still raw** — the same metachar exposure as the
      write paths, read-only risk. Pre-existing function that predates the plan;
      apply `cbm_lookup_name` in the wave, with a test.
- [ ] **Case asymmetry in the file API** — the API lowercases on write but demands
      lowercase on lookup. Normalize lookup args.
- [ ] **`delete_file` re-parses `dos_status` from stdout only**, where
      `_run_checked` parses stdout+stderr (safe failure mode today). Fix = expose
      the parsed status, or the combined text.
- [ ] **An over-long lookup name reports "no file named …"** instead of a length
      message.
- [ ] **The `'title'` noun leaks into filename error messages** (pinned by tests,
      cosmetic).
- [ ] **`_run_checked`'s `"Error -"` scan and `_FAILURE_TEXT` branches are dead**
      under measured behavior — rc-1 cases raise in `_run2` first. Harmless
      future-proofing; reconcile or comment.
- [ ] **`GEOMETRY`/`IMAGE_DRIVE_TYPES` key-set coupling is unenforced** — a
      mismatch takes a bare `KeyError` path.
- [ ] **`_ERR_RE` requires all four fields** (silent degradation if c1541's format
      shifts) and truncates at the comma; the `"Error -"` match also requires
      column 0.
- [ ] **The `needs_c1541` marker is dead in the test file** — the suite is pure
      Python, so c1541 drift is invisible to CI.
- [ ] **The d71 test misses side-two zone boundaries 52/59/60/66.**
- [ ] **Record (don't change) the accepted `validate`/repair costs from Task 4:**
      2 reads + 3 subprocess spawns per call — the correct trade for
      format-agnosticism; `repaired_blocks` really means the free-count delta
      (plan-mandated, documented); tests 333/356 overlap and should be absorbed.

## Standing backlog (pre-cartridge)

- [ ] Dogfood the six C64 demo prompts (statuses in `demos/README.md` are
      "awaiting C64 dogfood").
- [ ] Build the full annotated C64 ROM label DB (only the KERNAL jump-table
      seed ships today).
- [ ] Deferred spec items: sprite-aware screenshot diffing, `c64 sprite` CLI
      helpers, VIC-II screen relocation support.
- [ ] Charset/bitmap PNG conversion — `c64 sprite from-png` handles sprites
      only. The other still-open bullet in §6 of
      `docs/superpowers/specs/graphics-and-sprites.md`.
- [ ] `c64 sprite encode` exits **2** on a missing `FILE` (Click's
      `Path(exists=True)`) while `c64 sprite from-png` exits **1** (it opens
      the path itself and calls `fail()`). Flagged during the sprite-encode
      work as "pre-existing house pattern, accepted" and never adjudicated;
      `test_sprite_encode_missing_file` only asserts non-zero.
