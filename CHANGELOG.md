# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged. Project64 is a Commodore 64 port of
[PET-Project](https://github.com/nschneir/PET-Project); its PET-era history
lives in that repository (and in this one's git history before the fork
commit).

## [0.6.0] — 2026-07-27

Disks — complete file CRUD, raw block access, validation, one-command game
disks, and the runtime half of disk I/O.

### Added
- **`c64 disk rename` / `c64 disk rm`** (alias `delete`), with MCP parity,
  complete file CRUD on an image. Both error when nothing matched, which
  `c1541` does not: renaming a missing file reports
  `ERR = 62, FILE NOT FOUND` and still exits 0, and a scratch that matched
  nothing answers with the same `ERR = 01, FILES SCRATCHED` line a real one
  does — only its count field tells them apart, so `c64 disk rm` reports the
  count. `rm` takes the CBM wildcards `*` and `?` and the count stays honest
  under them (`"al*"` removes `alpha` and `album` and reports 2); `"`, `:`,
  `,` and `=` are refused in both verbs, because CBM DOS parses them inside a
  name and they would silently retarget the operation at another file.
- **`c64 disk block read` / `c64 disk block write`** (with MCP parity) — raw
  256-byte sector access: whole-sector host file I/O in both directions and
  byte poking at an `--offset`. Track/sector are checked against the image's
  real geometry first, so the error names the bound, and both the wrong-sized
  whole-sector write and the poke that runs off the end of a sector — which
  `c1541` accepts silently — are refused. A read reports the sector as the
  same `bytes`/`hex` pair `c64 mem read` produces; the payload key is `hex`,
  in the CLI and MCP alike, and no release ever carried another name.
- **`c64 disk validate`** (with MCP parity) — the CBM allocation check.
  `c1541 -validate` prints the same line and exits 0 whether it repaired the
  BAM or not, so this compares the image before and after and reports what
  changed: `clean` is the flag to trust, `repaired_blocks` sizes it, and
  `messages` explains it in words.
- **`c64 disk build game.disk.yaml`** (with MCP parity) — build a populated
  game disk in one reproducible step. Files land in listed order so the first
  one autostarts, `.s` entries are assembled and `.bas` tokenized, and the
  build is atomic: everything is staged beside the output and renamed over it
  only after the last file lands, so a build that fails partway leaves an
  existing image byte-identical. A manifest that would overflow the disk — on
  blocks *or* on the 144 directory entries a `.d64` holds — is refused before
  anything is formatted, because a full disk otherwise leaves a truncated file
  and a corrupt BAM behind.
- **`disk-io-programming` skill** — the runtime half: the KERNAL `LOAD`/`SAVE`
  and channel calls, the secondary-address rule that decides where a file
  lands (measured both ways), reading the drive's own answer off the command
  channel, and the build-boot-inspect loop. Plus a
  `references/kernal-disk-io.md` entry-point table checked against the
  umbrella skill's so the two cannot disagree about an address.
- **`disk:` in test specs** (`c64 test run`, `c64 test programs`) — a spec or
  an example-program directory can name a `.d64`/`.d71`/`.d81` or a
  `.disk.yaml` manifest; the image is built as needed, attached to drive 8 at
  power-on and autostarted after `READY.`. It is exclusive with `program:`
  and `cart:`, both of which would otherwise be silently ignored.
- **`tests/programs/disk-loader/`** — a reference program that boots from a
  disk and pulls a second file off the same disk *while running*, regression
  covered end to end on a real emulated 1541. Its data file is a two-byte PRG
  header and a payload, which is the whole point: under secondary address 1
  that header is the only thing that decides where the file lands.

### Fixed
- **`c1541` failures are no longer silent.** It exits 0 when renaming a
  missing file, scratching nothing, or poking past the end of a sector; every
  disk operation now reads the DOS status line and c1541's own diagnostics
  instead of trusting the exit code, so a `c64 disk put` onto a full image
  reports the failure rather than leaving a truncated file behind.

## [0.5.0] — 2026-07-25

Cartridges — build, verify, boot and debug `.crt` images.

### Added
- **`c64 cart` command group** (with MCP parity): `build` assembles a
  multi-bank EasyFlash `.crt` from an `.ef.yaml` manifest with a per-bank fill
  table and hard errors on window overflow; `info` decodes the header and every
  CHIP packet; `verify` catches the failures that are silent on hardware — a
  missing CBM80 signature (the machine just boots to BASIC), a vector pointing
  outside the cartridge, a wrong image size, an EasyFlash image with no bank 0
  HIROM window; `dump` extracts one bank window; `bank` reports live paging
  state; `convert` is a `cartconv` passthrough for exotic types.
- **`c64 package --format crt`** — a cart-native `.s` builds directly into a
  bootable 8K/16K/Ultimax cartridge with a generated boot stub, and any
  `.prg`/`.bas` is wrapped in a launcher cartridge instead.
- **`c64 session start --cart` and `c64 run game.crt`** — cartridges attach at
  power-on rather than loading, so `run` boots a session with the image mapped.
- **`cart.inc`** — a resident EasyFlash bank-switch runtime (`ef_boot`,
  `bankcall`, the `$9F00` jump-table convention) shipped as package data, so a
  banked program does not re-derive the banking discipline.
- **`cartridge-programming` skill** — the two boot mechanisms, the memory
  modes, the EasyFlash banking rules, and the pitfalls that produce no error
  message.
- **`cart:` / `cart_type:` in test specs** — a YAML test or an example-program
  directory can name a `.crt`, a cart-native `.s`, or an `.ef.yaml` manifest;
  the image is attached at power-on and nothing is autostarted.
- Reference cartridges under `tests/programs/` (`cart-hello`, `cart-banked`)
  that boot on a real emulator as part of the regression suite, plus a live
  wrap-boot regression that proves a wrapped BASIC program actually runs —
  the two wrap bugs this catches both passed `cart verify`.

## [0.4.0] — 2026-07-25

Driving interactive programs — the gaps a demo-01 dogfooding run turned up.

### Added
- **`c64 screen --png --border`** (MCP: `c64_screenshot(border=True)`) —
  capture the whole frame instead of the 320×200 inner screen, so a
  `POKE 53280` border color is visible. The bordered frame was always in the
  VICE response; it was being cropped away.
- **`c64 wait --text --since`** (MCP: `c64_wait_text(since=True)`; YAML
  `wait: {text: ..., since: true}`) — fire only on an occurrence appearing
  after the wait starts. Screen output persists, so a string already printed
  once otherwise matches the stale copy and returns instantly.
- **`c64 screen --numbered`** (MCP: `c64_screen_text(numbered=True)`) — row
  indices and a column ruler, for reading off `@row,col` references.
- **`tests/programs/guess-the-number/`** — an interactive BASIC program as a
  regression test, seeded with `RND(-1)` and driven through a full round via
  `test.yaml` key steps and row-anchored asserts.

### Changed
- `--json` is now accepted after the subcommand as well as before it:
  `c64 session list --json` and `c64 --json session list` are equivalent.
- The invaders demo moved from `demos/06-invaders-asm.md` to
  `demos/invaders/README.md`, matching the `demos/1812/` layout: a demo that
  produces source gets its own directory.

### Fixed
- **`c64 key type` decodes a literal `\n` — the two characters backslash and
  n — as RETURN** (MCP: `c64_key_type`; YAML `key:` steps already decode
  `\n` at the YAML layer in double-quoted strings). `--help`,
  `docs/cli.md` and the cookbook all documented `c64 key type "50\n"` as
  typing 50 and pressing RETURN, but shell double quotes pass backslash-n
  through untouched, so the screen got `50\N` and an `INPUT` stayed blocked.
  `\\` is the escape for a literal backslash; every other pairing is left
  alone (`\q` stays `\q`), and real newlines behave exactly as before.

### Documentation
- **Turn-by-turn waits anchor the cell.** `c64 wait --mem '@6,0=20'` (in
  YAML, `assert: {mem: "@6,0", equals_text: "TOO HIGH"}`) is now the
  documented default for driving a program one turn at a time, with
  `--since` scoped to the case it actually fits: an appearance separated
  from its trigger by a real gap, such as a countdown or an animation frame.
  Live-verified on demo 01 — a program that answers faster than a CLI
  round-trip has already printed the new text into `--since`'s baseline, so
  the wait holds out for a second occurrence that never comes. Polling the
  byte has no count to race, and nothing breaks when an old copy scrolls off.
- VIC-II color registers are 4-bit and read back with the high nybble set
  (`$D020` reads `$F0` after `POKE 53280,0`) — documented in the hardware
  reference, the skill's pitfalls and diagnosis table, and the `c64 test run`
  mask example.
- New cookbook recipe: an `INPUT` prompt loop with `RND` seeding and the CLI
  steps to drive it.
- The skill now says where the `c64` binary lives, how to drive a program
  that blocks on input, that `RND` needs seeding before a program is
  testable, that `c64 key type` does not wait for the keys to be consumed,
  and that decoded screen text is the cheaper observation for text-mode
  programs.
- CLI help matches the CLI: the `--json` and `--session` position rules,
  `c64 run` file handling, and the `rom disasm`/`test programs` defaults are
  stated where they are typed, and `c64 test run` points at `docs/cli.md`
  instead of an unresolvable spec section.
- Demo 01's success criterion names the row-anchored wait the round actually
  needs and no longer asks for a border in a capture that cropped it out; it
  is marked dogfooded.

## [0.3.1] — 2026-07-25

Test-suite change only — no library, CLI, or MCP behavior changed.

### Changed
- **Live tests share one emulator.** Each `@pytest.mark.vice` test used to
  launch its own `x64sc` — 60 per run, each one stealing window focus on
  macOS. The tests that only need a C64 at the READY prompt now share a
  single warp+headless session (`tests/conftest.py`), reset between tests:
  every checkpoint deleted (they survive a machine reset, and a stray
  non-stopping one crawls the emulator), a hard reset confirmed by a screen
  sentinel, and the session record's label/loaded-program bookkeeping
  cleared. Specs run through `run_test` — the cookbook recipes and the YAML
  runner tests — share it too, via an injected launcher, and stay one test
  case each. Tests keep their own emulator where sharing would lie:
  per-model parameterization, anything attaching a disk image (the binary
  monitor has no detach command), and anything asserting launch or
  daemon-spawn behavior itself. 60 → 14 launches, 6:07 → 3:27 for a full run.
- Emulators orphaned by a suite killed before teardown are reaped by the next
  run: pids are recorded at spawn, and only ones still alive that still look
  like an emulator or its daemon are killed, so a concurrent run and the
  developer's own sessions are never touched.

## [0.3.0] — 2026-07-24

BASIC linting — catch the errors petcat accepts before spending a run cycle.

### Added
- **`c64 basic check`** (with MCP parity as `c64_basic_check`) — static lint
  for BASIC V2 that models the real cruncher, so crunched code parses
  correctly and keyword fusion is caught: `total=5` tokenizes as `TO TAL=5`
  on a C64 and cannot run. Also checks jump targets, `IF`/`THEN` shape,
  parentheses, `FOR`/`NEXT` and `GOSUB`/`RETURN` structure, reachability,
  constant hardware ranges, simple type mismatches, `DEF FN` definitions,
  V2 vocabulary, two-character variable aliasing, and exact program size
  against the 38911 free bytes. `--json` reports `tokenized_bytes`.
- `c64lib.basic_tokens` — a cruncher-faithful BASIC V2 tokenizer whose byte
  sizes are checked against real petcat output, so a program's loaded size
  is computed exactly rather than estimated.
- Fixture corpus under `tests/data/basic-lint/`, plus a gate asserting every
  known-good BASIC program in the repo (example programs and the cookbook
  recipes) lints error-free. Each bad fixture records the failure a real
  C64 produces, observed on VICE.
- **`c64 basic check` guidance in the `c64-development` skill** — the lint is
  step 2 of the write → run → observe loop, with the conventions it enforces
  (no keywords inside variable names, two significant characters, 80-char
  lines, V2 vocabulary, the 38911-byte budget) stated alongside it.

## [0.2.0] — 2026-07-22

Sprite tooling — the graphics/sprites spec implemented.

### Added
- **`c64 sprite` command group** (with MCP parity): `status` decodes
  `$D000-$D02E` + the sprite pointers into a per-sprite table; `show`
  renders any shape as ASCII art; `png` renders the exact shape with live
  colors; `from-png` converts any image (from a generative model or
  otherwise) into ready-to-paste `.byte %...` rows — hires threshold or
  multicolor palette quantization, round-trip-tested against `png`.
- **YAML motion testing** — `sample: {mem, as}` captures a byte;
  `assert` gains `differs`/`greater_than`/`less_than` against captures.
  Example programs may ship a `test.yaml` extending their `expect.txt`
  gate.
- **`tests/programs/sprite-ball/`** — sprite reference program covering
  registers, motion sampling, and the state-byte convention end to end.
- **Generative-AI sprite workflow** in the c64-development skill:
  generate an image → `from-png` → paste rows → verify with
  `sprite show`/`sprite png`.

### Changed
- **Screen reads follow VIC-II relocation**: `c64 screen`, `wait --text`,
  and `@row,col` resolve against the live screen base (`$DD00`/`$D018`)
  instead of assuming `$0400`. Color RAM stays `$D800`.

## [0.1.0] — 2026-07-21

The founding release: everything the PET edition could do, ported to the
Commodore 64.

### Added
- **C64 machine profiles** — `c64` (NTSC, the default) and `c64pal`, both
  BASIC 2.0 with 38911 bytes free; BASIC start `$0801`, screen `$0400`.
- **C64 ROM support** — BASIC `$A000` / KERNAL `$E000` identification and
  hashing, plus a curated seed label database: the full KERNAL jump table
  (`$FF81-$FFF3`), hardware vectors, and BASIC pointers, all live-verified.
- **C64 key-hold protocol** — `c64 key hold` drives the current-key matrix
  code at `$CB` (with a full ASCII→matrix-code table), verified against a
  live emulator.
- **C64 disk formats** — d64/d71/d81 (1541/1571/1581 drives) via c1541;
  1541 is the attach default.
- **c64-development skill** — SKILL.md plus references (memory map,
  zero page with the 6510 banking port, KERNAL routines, VIC-II/SID/CIA
  hardware, BASIC internals, PETSCII, cookbook) rewritten from the C64
  reference books; every live-assertable claim measured on a real x64sc.
- **Cookbook** — 16 C64 recipes (sprites, SID sound, `$CB` input, CINV IRQ
  wedge, screen+color pokes ...), all exercised live by the test suite.
- **Graphics & sprites spec** — `docs/superpowers/specs/graphics-and-sprites.md`: how
  demos author sprite data, capture screenshot evidence, and write
  register/memory-based tests.
- **C64 demo prompts** — six graded prompts (bouncing-ball sprite demo,
  Snake with SID + `$CB` steering, sprite-based Invaders flagship),
  awaiting their C64 dogfooding runs.

### Changed
- Renamed throughout from the PET edition: package `petlib` → `c64lib`,
  distribution `pet-tools` → `c64-tools`, CLI `pet` → `c64`, MCP tools
  `pet_*` → `c64_*`, env prefix `PET_TOOLS_` → `C64_TOOLS_`, state dir
  `~/.pet-tools` → `~/.c64-tools`, emulator `xpet` → `x64sc`.
  `petcat`, `PETSCII`, and `c1541` keep their names — they are correct
  for the C64.
- petcat dialects reduced to C64 BASIC 2.0 (`-w2`).
- `c64 package` run hints pin the video standard (`x64sc -ntsc ...`).

### Removed
- PET machine profiles, PET ROM labels, VIA/CB2 sound recipes, BASIC 4
  disk-command docs, and the PET-built demo programs (`demos/invaders/`,
  `demos/muncher/`) — the demo prompts will be re-dogfooded on the C64.
