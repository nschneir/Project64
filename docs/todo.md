# TODO

Open items carried out of the `.crt` cartridge support work (2026-07-26) plus
the standing project backlog. Strike items as they land.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

## Decisions (maintainer)

- [ ] **Release timing for 0.5.0.** `pyproject.toml:7` (`version = "0.5.0"`),
      `CHANGELOG.md`'s `## [0.5.0]` heading and `README.md:180` ("Stable —
      current release **v0.5.0**") are coherent today.
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
      version revert can leave `README.md:180` ("current release **v0.5.0**")
      stale and green. Add the assertion to `tests/test_docs_readme.py`,
      reusing `tests/test_package.py::_pyproject_version()` and a regex over
      the README release line — parse, never hard-code.

## Accepted behavior (documented, revisit only if it bites)

- [x] Stale `.crt`/`.bin` beside the output path after a failed rebuild —
      consistent with `build_asm`'s `.prg`/`.lbl` behavior; documented in
      `docs/cli.md:523-525` ("a failed rebuild leaves the outputs of the
      previous one in place … do not trust a `.crt`/`.bin` already sitting at
      the output path").
- [x] `index.html` tool count and missing cartridge card — fixed (55 tools,
      CARTRIDGES card now at `index.html:193`). Note: the 55 has since gone
      stale again (measured 61 `@srv.tool()` today) — see the counts item in
      the disk section below.

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

## Disk plan deferred items (in-flight — the plan's deferred wave owns these; strike when it lands)

Originally mirrored from `.superpowers/sdd/2026-07-24-disk-file-block-ops/progress.md`
(the disk file/block-ops plan's ledger, which is deleted when that plan
finishes). Every line below is scheduled for that plan's own deferred-fix wave
before it completes — this is a visibility copy, not standing backlog and not a
maintainer decision queue. Each item is self-contained; if the plan is
abandoned, they become standing backlog as written.

- [ ] **Sweep every remaining `# Measured:` claim in `src/c64lib/disk.py` and
      its tests.** Named a deferred-wave item by the Task 3 fixer: three drift
      findings across two tasks makes this a class, not incidents (e.g. "a
      short bwrite is a silent no-op" did not reproduce — c1541 exits 1 with
      "floppy read failed"; "an out-of-range bpoke exits 0" holds for the
      offset only, not for track/sector, which exit 1). Re-measure each claim
      against real c1541 and correct or delete it. Known contradiction to
      resolve in the sweep: the `_FAILURE_TEXT` comment at `disk.py:111`
      ("none of which change the exit code") versus the measured
      floppy-read-failed `rc 1`. House rule for the wave: measure before
      writing any measured-behavior claim.
- [ ] **Decide/implement `.lbl` label persistence for asm-built disks.**
      `build_disk` (`disk.py:557`) assembles `.s` manifest entries through
      `_manifest_artifact` (`disk.py:542`) into a `tempfile.TemporaryDirectory`
      workdir, so `build_asm`'s `.lbl` dies with the temp dir and a
      disk-loaded program cannot be symbolically debugged. Task 5 reviewer
      ruling: deferrable, because the result dict is additive and a user can
      run `c64 build` separately. Two options — document the build-separately
      flow in the spec/skill, or extend `build_disk` with an additive `labels`
      key that copies the `.lbl` beside OUT. Verify: `tests/test_disk_build.py`.
- [ ] **Neutral lead-in for non-ENOENT `OSError`s** (one sweep covers both
      sightings): `block_write_file`'s broadened catch (`disk.py:351-352`)
      reports "no such file to write" for every `OSError`, including `EACCES`,
      and `validate_image`'s (`disk.py:409-410`) "no such image to validate"
      overclaims the cause the same way. Fix = a cause-neutral lead-in that
      still prints `e.strerror` (e.g. "cannot read <path> (<strerror>)").
      Verify: `tests/test_disk_blocks.py` with a chmod-000 case.
- [ ] **`cbm_lookup_name` upper-cases per character.** `disk.py:270` tests
      `0x20 <= ord(ch.upper()) <= 0x5D`; `'ß'.upper()` is `'SS'`, so `ord()`
      raises `TypeError` instead of `DiskError`, and `'ı'`/`'ſ'` uppercase into
      range and pass through into a c1541 argument. Fix = case the whole string
      once and then `ord(ch)` per character, matching `cbm_title`'s idiom
      (`packaging.py:26-37`, `t = str(raw).upper().strip()`). Verify:
      `tests/test_disk_blocks.py`.
- [ ] **`get_file`'s `name` is still raw.** `disk.py:221-226` passes `name`
      straight into `_run([image, "-read", name, dest])` with no
      `cbm_lookup_name` — the same `":,=` metacharacter exposure the write
      paths were hardened against in commit 10fe436, here as a read-only risk
      (a crafted name retargets the read at a different file). Pre-existing
      function that predates the plan. Fix = validate through
      `cbm_lookup_name` in the wave, with a test in `tests/test_disk.py`.
- [ ] **Case asymmetry in the file API.** `cbm_lookup_name` now lowercases
      (`disk.py:275`), so `rename_file`/`delete_file` are normalized; the
      residue is `put_file` (`disk.py:215`: `cbm_name = name or
      src.stem.lower()` — an explicit `name=` is neither lowercased nor
      validated) and `get_file` (raw, above). Net effect: a name written via
      `put_file(img, src, "ALPHA")` cannot be found by `delete_file(img,
      "ALPHA")`. Normalize both ends. Verify: `tests/test_disk.py`.
- [ ] **`delete_file` re-parses `dos_status` from stdout only.** `disk.py:307`
      parses `_run_checked`'s return value, which is `stdout` alone
      (`disk.py:172`), while `_run_checked` itself parses `stdout + stderr`
      (`disk.py:160`). If c1541 ever emitted the `ERR =` line on stderr, the
      scratch count would read 0 and a successful delete would raise "no file
      named …" — a safe failure mode today, but a silent coupling. Fix = have
      `_run_checked` expose the parsed status, or return the combined text.
- [ ] **An over-long lookup name reports "no file named …"** instead of a
      length message. **Appears already fixed** by commit 10fe436:
      `cbm_lookup_name` raises "filename … is N chars; CBM names max out at 16"
      at `disk.py:261-263` before any c1541 call, and `tests/test_disk_blocks.py`
      pins `match="17 chars"`. Confirm and strike; if some path still reaches
      c1541 with a >16-char name, that path is the actual bug.
- [ ] **The `'title'` noun leaks into filename error messages** (cosmetic,
      pinned by tests). `cbm_filename` (`disk.py:229-241`) delegates to
      `packaging.cbm_title`, whose messages all begin "title …"
      (`packaging.py:30/32/36`); `cbm_filename` only appends "— not a legal CBM
      filename" when the substring "CBM filename" is absent. Fix = give
      `cbm_title` a noun parameter (default `"title"`), pass `"filename"` from
      `cbm_filename`, and update the assertions that pin the current wording.
- [ ] **`_run_checked`'s `"Error -"` scan and `_FAILURE_TEXT` branches are dead**
      under measured behavior. `disk.py:166-171` runs only after `_run2`
      (`disk.py:140-141`) has already raised on any non-zero exit, and every
      case that emits those strings exits 1. Harmless future-proofing against
      an exit-0 regression — either say exactly that in a comment or delete the
      branches. Overlaps the `# Measured:` sweep above (the `_FAILURE_TEXT`
      comment is one of the wrong claims).
- [ ] **`GEOMETRY`/`IMAGE_DRIVE_TYPES` key-set coupling is unenforced.**
      `_geometry_for` (`disk.py:68-71`) validates the suffix through
      `drive_type_for` (which reads `IMAGE_DRIVE_TYPES`, `disk.py:38`) and then
      indexes `GEOMETRY` (`disk.py:60`) bare; `build_disk` likewise indexes
      `TOTAL_BLOCKS` (`disk.py:56`) and `MAX_DIR_ENTRIES` (`disk.py:442`)
      unguarded. Adding a fifth image format to one dict and not the other
      three yields a bare `KeyError` instead of a `DiskError` naming the
      supported types. Fix = a test in `tests/test_disk_blocks.py` asserting
      all four key sets are identical.
- [ ] **`_ERR_RE` requires all four fields.** `disk.py:108-109`
      (`^ERR = (\d+),\s*([^,]+?),\s*(\d+),\s*(\d+)`): if c1541's status format
      ever drops or reorders the track/sector fields, `dos_status` returns
      `None` and every check that depends on it degrades silently to "no
      status"; `[^,]+?` also truncates the DOS message at its first comma. The
      `"Error -"` scan (`disk.py:167`) additionally requires column 0
      (`line.startswith`). Fix direction open: loosen the trailing fields,
      and/or raise when a line begins `ERR =` but does not parse.
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
- [ ] **The d71 test misses side-two zone boundaries 52/59/60/66.**
      `tests/test_disk_blocks.py::test_d71_second_side_mirrors_the_first`
      (line 50) parametrizes only `(36, 21), (53, 19), (65, 18), (70, 17)`,
      while `GEOMETRY[".d71"]` (`disk.py:63`) declares zones
      `(36,52,21), (53,59,19), (60,65,18), (66,70,17)`. Add the last track of
      each zone and the first of the next: 52→21, 59→19, 60→18, 66→17.
- [ ] **Record (don't change) the accepted `validate`/repair costs from Task 4:**
      `validate_image` (`disk.py:389-435`) performs 2 whole-image
      `read_bytes()` plus 3 c1541 spawns per call (two `list_files`, one
      `-validate`) — the correct trade for deciding cleanliness
      format-agnostically, since c1541 reports nothing either way.
      `repaired_blocks` really means the free-count delta (plan-mandated name,
      already documented in the docstring). And
      `test_validate_detects_and_repairs_a_corrupted_bam` /
      `test_validate_reclaims_blocks_no_file_owns`
      (`tests/test_disk_blocks.py`, ~lines 334 and 355) assert the same
      poke-BAM-then-validate path and should be absorbed into one. Action is
      documentation + test tidy-up; no behavior change.
- [ ] **The disk-id coercion hint echoes the coerced value verbatim.**
      `_disk_id` (`disk.py:456-467`) ends its YAML-coercion hint with
      `quote it: id: "{disk_id.zfill(2)}"`. Right for `id: 01` (YAML → int 1 →
      suggests `"01"`), wrong for `id: 12345`, where it suggests quoting a
      value the very next length check rejects. Cosmetic, on an
      already-failing path. Fix = only offer the quote-it hint when
      `zfill(2)` yields a legal two-character id. Verify:
      `tests/test_disk_build.py`.
- [ ] **A SIGKILL mid-`build_disk` can orphan a `.<stem>-build-*` staging
      directory beside the output.** `build_disk` (`disk.py:606-608`) stages
      into `tempfile.TemporaryDirectory(dir=image.parent,
      prefix=f".{image.stem}-build-")` — deliberately on the output's own
      filesystem so the final `os.replace` (`disk.py:630`) stays atomic.
      Ordinary failures clean up via the context manager; only an uncatchable
      kill leaves the directory behind. Fix direction: document it, or sweep
      matching siblings at the start of the next build. Verify:
      `tests/test_disk_build.py`.
- [ ] **`docs/cli.md:744-745` overstates the `disk block read` JSON parity with
      `mem read`:** "`bytes` is the count and `hex` the sector as a hex string,
      the same pair of names `c64 mem read` uses" — but `c64 mem read`'s
      `bytes` is "always present as a decimal int array" (`docs/cli.md:222-224`),
      not a count. Trim to say the two commands share the key names and differ
      in what `bytes` means. Doc-only. Verify: `tests/test_docs_cli.py`.
- [ ] **Re-measure and update the tool/skill counts now that the disk work has
      landed.** `index.html:196` still claims "A 67-command CLI, 55 MCP tools,
      four skills". Measured today: **61** `@srv.tool()` in
      `src/c64lib/mcp_server.py`; **5** skills under `skills/` (6502-assembly,
      6502-debugging, c64-development, cartridge-programming,
      disk-io-programming); the CLI is still **67** (63 `@<group>.command(`
      decorators plus 4 `add_command` aliases at `cli.py:1030-1032` and
      `cli.py:1351`). Re-check `docs/agent-setup.md` and
      `skills/c64-development/SKILL.md` too — neither carried a numeric count
      at last check, but both name the skill set.
- [ ] **MCP disk-tool minors (`src/c64lib/mcp_server.py`, `tests/test_mcp_disk.py`).**
      All small, deferred as a group: (a) nothing asserts the documented tool
      roster against `list_tools()` (helper exists at
      `tests/test_mcp_scaffold.py:29`); (b) `bytes(values)`
      (`mcp_server.py:762`) surfaces Python's bare "bytes must be in range(0,
      256)" where the CLI's `parse_number` names the offending token — fix once
      at library level; (c) the `c64_disk_rename`/`c64_disk_rm` payloads (lines
      702, 713) are never cross-checked against the CLI runner the way the
      block tools are (a one-liner each); (d) the guard
      `(src is None) == (values is None)` (line 750) diverges from the CLI's
      `bool(src) == bool(values)` (`cli.py:1415`) for `values=[]` —
      `(src is None) == (not values)` matches exactly; (e) `image` is echoed
      unnormalized (lines 702/713/732/764) where the CLI emits `str(Path)`;
      (f) the `-o` failure re-raise (`mcp_server.py:729-731`) flattens
      `PermissionError` and friends into a bare `OSError`; (g)
      `tests/test_mcp_disk.py:161` passes a filesystem path to `match=` as a
      regex — needs `re.escape`.
- [ ] **Uneven error-path coverage in the disk CLI tests**
      (`tests/test_cli_disk.py`): the `ValueError` arm of `disk block write`'s
      byte parsing (`cli.py:1428`, `bytes(parse_number(v) for v in values)`) is
      untested, so a bad token's raw-Python wording has never been read;
      `disk validate` (`cli.py:1437`) has no error-path test at all; and
      `disk build` exercises only the unknown-model `KeyError` arm
      (`test_cli_build_rejects_an_unknown_model`, line 283) — not the
      `DiskError` arms. Add one test per gap.

## Standing backlog (pre-cartridge)

- [ ] **Dogfood the six remaining C64 demo prompts.** `demos/README.md:12-18`:
      demo 01 is ✅ dogfooded; 02-07 are 🔲 "awaiting C64 dogfood". 01-06 were
      ported from the PET edition, where each passed a real dogfooding run;
      07 (1812) was written for the C64 and has never been agent-run. Done =
      an agent given only this toolset builds and verifies the demo on a real
      VICE session, then the row's status flips.
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
