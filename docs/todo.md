# TODO

Open items carried out of the `.crt` cartridge support work (2026-07-26) plus
the standing project backlog. Strike items as they land.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

## Decisions (maintainer)

- [ ] **Release timing for 0.7.0.** `pyproject.toml:7` (`version = "0.7.0"`),
      `CHANGELOG.md`'s `## [0.7.0]` heading and `README.md:185` ("Stable —
      current release **v0.7.0**") are coherent today.
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
- [ ] **Version-coherence test.**
      `tests/test_package.py::test_changelog_has_current_version` already pins
      `CHANGELOG.md` to `pyproject.toml`, but nothing pins the README: a
      version revert can leave `README.md:185` ("current release **v0.7.0**")
      stale and green. The 0.7.0 bump had to update it by hand. Add the assertion to `tests/test_docs_readme.py`,
      reusing `tests/test_package.py::_pyproject_version()` and a regex over
      the README release line — parse, never hard-code.

## Accepted behavior (documented, revisit only if it bites)

- [x] Stale `.crt`/`.bin` beside the output path after a failed rebuild —
      consistent with `build_asm`'s `.prg`/`.lbl` behavior; documented in
      `docs/cli.md:523-525` ("a failed rebuild leaves the outputs of the
      previous one in place … do not trust a `.crt`/`.bin` already sitting at
      the output path").
- [x] `index.html` tool count and missing cartridge card — fixed (55 tools,
      CARTRIDGES card now at `index.html:193`). The 55 later went stale again
      and was re-measured to 61 in `76f76b2`; the counts line is now enforced
      by `tests/test_mcp_scaffold.py::test_index_html_counts_match_the_real_inventory`
      rather than remembered.

## Test health

- [ ] **`tests/test_integration_debug.py::test_symbolic_debug_loop` flakes
      under load** (line 31: builds `tests/programs/hello-asm/program.s` with
      `-g`, sets the label path, then sets a symbolic breakpoint that is never
      hit). Two sightings, both under parallel load / coverage tracing; passes
      standalone and in plain full runs. Pre-existing, non-cart; cause not
      diagnosed. No retry/xfail guard exists. Needs its own investigation —
      reproduce under `-n auto` + `--cov` before touching the test.
- [ ] **`tests/test_integration_disk.py::test_disk_attach_at_launch` flaked
      once in a full run** (line 44; parametrized over image name × model —
      the failure was a boot-keyboard artifact between `wait_for_text(s,
      "READY.")` and `_load_and_run(s)` during the 0.4.0 release run). Passed
      2/2 in isolation and is untouched by the changes it was seen under.
      Carried out of the demo-01 ledger; no retry/xfail guard exists today.
- [ ] **`tests/test_docs_cookbook.py::test_cookbook_recipe_runs_live[basic-game-loop]`
      failed once in the 0.6.0 pre-merge gate** (full suite under `coverage run`,
      2026-07-27; `1 failed, 1219 passed`). Immediately re-ran green standalone
      (6.7 s) and green with its whole file (24 passed); the commits since the
      previous green full run touch only disk validate/payloads/docs, which that
      BASIC recipe never exercises. No retry/xfail guard exists.
- [ ] **Three live tests have now flaked under full-suite load** (the two above
      plus the cookbook one) while each passes standalone — treat this as one
      harness-level fragility rather than three unrelated tests. Worth
      investigating together: all three run against the shared warp+headless
      emulator (`session`/`shared_launch` in `tests/conftest.py`), and all three
      failures are "expected screen state never arrived" under contention.
      A first step that needs no diagnosis: make live waits' timeouts scale
      when the suite runs under `coverage`/parallel load.

## Disk plan deferred items (the deferred wave landed; one item still open)

Originally mirrored from `.superpowers/sdd/2026-07-24-disk-file-block-ops/progress.md`
(the disk file/block-ops plan's ledger, which is deleted when that plan
finishes). The deferred wave has since landed in two commits — `a7f6ba5` (core:
`disk.py`, `testing.py`, their tests) and `76f76b2` (surfaces: MCP/CLI minors,
counts, CHANGELOG) — plus a seam commit that finished the two front-end tokens
wave A could not reach. Struck lines below record what was actually done,
including the two places measurement contradicted the item as written. Only the
CI item is still open.

- [x] Swept every remaining `# Measured:` claim in `src/c64lib/disk.py` and its
      tests against real c1541 (VICE 3.10) — all reproduced but one: the
      `_FAILURE_TEXT` comment's "none of which change the exit code" was false
      (all three diagnostics arrive with `rc 1`) and now records the exit codes
      (`a7f6ba5`).
- [x] `.lbl` label persistence implemented rather than documented: `build_disk`
      copies each `.s` entry's `.lbl` beside OUT and returns an additive
      `labels` key (one file per entry, not a merged table — a disk can hold
      several independently assembled programs whose symbols would collide)
      (`a7f6ba5`).
- [x] Neutral lead-in for non-ENOENT `OSError`s — both sightings now read
      `cannot read <path> (<strerror>)`. **This item's verification recipe was
      wrong and is corrected here:** a chmod-000 *file* never reaches
      `block_write_file`'s catch, because `stat()` needs no read permission —
      the size check passes and c1541 fails later with its own "floppy read
      failed"; the parent *directory* must be unsearchable for `stat()` itself
      to raise `EACCES`, and the new test does that. `validate_image`'s catch
      wraps `read_bytes()`, which does need read permission, so there a
      chmod-000 file is the genuine case (`a7f6ba5`).
- [x] `cbm_lookup_name` no longer upper-cases per character — the whole string
      is cased once and the cased form is both validated and returned
      (`cbm_title`'s idiom), so nothing non-ASCII reaches a c1541 argument and
      the length check counts what c1541 stores (`'ß'` costs two) (`a7f6ba5`).
- [x] `get_file`'s `name` is now validated through `cbm_lookup_name`
      (`a7f6ba5`). **This item's threat claim was overstated and is corrected
      here:** `-read` is mostly stricter than the write paths — measured,
      `zed:alpha`, `alpha:zed`, `0:alpha`, `alpha=p` and `alpha"zed` all exit 1.
      Only the comma case reproduced: `c1541 img -read 'zed,alpha' out` exits 0
      and returns **zed**'s contents. **Re-measured (final review):** what
      follows the comma is CBM DOS's type/mode field, judged by its first
      character alone — `,alpha` works because `a` is append, as do `,p`, `,r`
      and `,w`, while `,s`, `,z` and a bare `,` exit 1, and `alpha,zed` exits 1
      even though both files exist. So the comma never retargets the read at
      what follows it; it silently reads what *precedes* it. The docstring says
      that now. Wildcards remain legal and are pinned (`-read '*'` is how a
      disk's autostart program is pulled back off an image).
- [x] Case asymmetry in the file API closed at both ends — `put_file`'s explicit
      `name=` now goes through `cbm_filename` (round-trip test added) and
      `get_file` through `cbm_lookup_name`. The `name=None` default
      (`src.stem.lower()`) is deliberately left alone, with the reason in the
      docstring: tightening it would newly reject stems `c64 disk put` accepts
      today (`a7f6ba5`).
- [x] `delete_file`'s `dos_status` re-parse can no longer disagree with
      `_run_checked`'s own — `_run_checked` returns the combined `stdout +
      stderr` it parsed its status from (`a7f6ba5`).
- [x] The over-long lookup name message was confirmed already fixed by `10fe436`
      — `cbm_lookup_name` raises the length message before any c1541 call and no
      path reaches c1541 with a >16-char name (re-verified in `a7f6ba5`).
- [x] The `'title'` noun no longer leaks into filename errors — fixed inside
      `disk.py` (`cbm_filename` rewrites a leading `"title "` to `"filename "`)
      rather than by adding a noun parameter to `packaging.cbm_title`, which is
      outside the disk plan's scope and would have rippled into
      `tests/test_packaging.py` (`a7f6ba5`).
- [x] `_run_checked`'s `"Error -"` scan and `_FAILURE_TEXT` branches were
      measured unreachable on VICE 3.10 and **kept** as the deliberate guard
      against the exit-0 regression class, with a comment saying exactly that
      ("do not delete them because coverage calls them dead"). The `"Error -"`
      scan no longer requires column 0 (`a7f6ba5`).
- [x] `GEOMETRY`/`IMAGE_DRIVE_TYPES`/`TOTAL_BLOCKS`/`MAX_DIR_ENTRIES` key-set
      coupling is now enforced twice, since the repo has no CI: a module-level
      `assert` that fails at import plus the requested test (`a7f6ba5`).
- [x] `_ERR_RE` no longer requires all four fields — the track/sector pair is
      optional (defaults 0/0), the message may contain commas, and a line that
      opens `ERR =` but does not parse now raises instead of degrading silently
      to "no status" (`a7f6ba5`).
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
- [x] The d71 side-two zone-boundary tests went from 4 cases to 8, adding
      52→21, 59→19, 60→18 and 66→17; all four were probed sector by sector
      against a real d71 first (`a7f6ba5`).
- [x] The accepted `validate` costs are recorded in `validate_image`'s
      docstring (2 whole-image `read_bytes()` + 3 c1541 spawns per call, with
      the format-agnostic trade stated), and the two overlapping BAM-repair
      tests were absorbed into one with no assertion lost (`a7f6ba5`).
- [x] The disk-id coercion hint now offers its `quote it:` clause only when
      `zfill(2)` yields a legal two-character id, so `id: 12345` no longer
      suggests quoting a value the next length check rejects (`a7f6ba5`).
- [x] The SIGKILL staging-dir orphan is **documented** in `build_disk`'s
      docstring rather than swept: a sweep cannot tell an orphaned
      `.<stem>-build-*` from the live staging directory of a concurrent build
      against the same output, so it would break a working build to tidy up
      after a dead one (`a7f6ba5`).
- [x] `docs/cli.md`'s "same pair of names" overstatement reworded to say the two
      commands share the key names and differ in what `bytes` means (`76f76b2`).
- [x] Tool/skill counts re-measured and refreshed: `index.html` now reads "A
      67-command CLI, 61 MCP tools, five skills", and the stale CLI-only
      enumerations in `docs/agent-setup.md` and `skills/c64-development/SKILL.md`
      were corrected (every `c64 disk` and `c64 cart` verb has a tool; only five
      commands are genuinely twin-less). Guarded by new
      `tests/test_mcp_scaffold.py` tests rather than remembered (`76f76b2`).
- [x] MCP disk-tool minors: (a) roster/count/CLI-only guards added, (c)
      `c64_disk_rename`/`c64_disk_rm` payloads now cross-checked against the CLI,
      (d) the `values=[]` guard matches the CLI's `bool()` check exactly, (e)
      `image` echoed as `str(Path(...))` like the CLI, (f) the `-o` re-raise
      keeps the `OSError` subclass, (g) `re.escape` on the path passed to
      `match=` — all `76f76b2`. (b) the bare "bytes must be in range(0, 256)"
      was fixed in two halves: `disk.block_bytes` in `a7f6ba5`, then the seam
      commit routed both `cli.py` and `mcp_server.py` through it, so a bad
      element is now named with its position at either front end.
- [x] Uneven error-path coverage in `tests/test_cli_disk.py` closed with four
      tests (both arms of `disk block write`'s byte parsing, `disk validate`'s
      `DiskError`, and `disk build`'s `DiskError`/`BuildError` arms); none need
      c1541 (`76f76b2`).

## Standing backlog (pre-cartridge)

- [ ] **Dogfood the five remaining C64 demo prompts.** `demos/README.md:12-18`:
      demos 01 and 02 are ✅ dogfooded; 03-07 are 🔲 "awaiting C64 dogfood".
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
