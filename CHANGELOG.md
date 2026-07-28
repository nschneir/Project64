# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged. Project64 is a Commodore 64 port of
[PET-Project](https://github.com/nschneir/PET-Project); its PET-era history
lives in that repository (and in this one's git history before the fork
commit).

## [0.8.0] — 2026-07-28

What dogfooding runs of demos 03, 04 and 05 walked into. Demo 03 (sieve
benchmark) passed first try — BASIC 933 jiffies, assembly 9.2, both
reporting `168 PRIMES, LARGEST 997` — and turned up documentation friction
only. Demo 04 (Snake in 6502 assembly) also came out working — a custom
charset, a title/play/game-over state machine, `$CB` steering, SID
blip/crash and a high score surviving across games, all proven on a live
machine — but found two real defects on the way. Demo 05 (debug hunt)
passed as well and found no defects; what it walked into was observability
friction, filed in `docs/todo.md`.

### Fixed
- **A freshly built `.s` no longer reports itself STALE.** `c64 status`
  printed `STALE (source changed since load): …/prog.s:` — note the
  trailing colon — after *every* `c64 run FILE.s`, forever. ca65's
  `--create-dep` file ends with a bare `<source>:` phony target per
  prerequisite (GNU make's `-MP` convention); `_parse_deps` split the whole
  file on its first colon, so those lines became paths with a trailing
  colon, which never exist — and `ops.staleness` counts a vanished source
  as stale. The one warning that exists to stop you debugging an
  out-of-date binary cried wolf on every assembly run. Parsing is now per
  line and prerequisites-only. The bug survived because the ca65 stub in
  `tests/test_build.py` emitted a tidier dep file than the real tool; the
  stub now emits the real format.
- **`wait: { mem: "@row,col" }` re-resolves the cell each poll.** `@row,col`
  is resolved against the machine's *live* screen base, and the reset
  `autostart` performs leaves the VIC registers unreadable for a moment —
  `$D018` reads 0, putting the cell at `$00C8` in zero page. Resolved once,
  that address was polled for the whole timeout, so a YAML test whose first
  step waited on a screen cell after `autorun: true` could never fire (and
  reported a zero-page address in its failure). Re-resolving per poll
  self-heals, and follows a screen the program relocates mid-wait.

### Added
- **Cookbook recipe: "Time a section of code with TI"** — the
  `ti$="000000"` / `t=ti` bracket, plus the two facts a benchmark needs:
  `PRINT` prefixes positive numbers with a space, and one jiffy of
  resolution makes any sub-second measurement mostly quantization error
  (repeat N times and divide). Timing was documented only as a fact about
  `TI` in basic-internals.md; the cookbook used jiffies for frame pacing
  and never for measuring.
- **Cookbook recipe: "Time a routine and print the jiffies (LINPRT)"** —
  `$BDCD` prints an unsigned 16-bit number in three instructions. The
  existing "Print a number as decimal digits" recipe only covers 0-255 by
  repeated subtraction, and LINPRT was one table row in
  kernal-routines.md, so the wide case looked like work it isn't. Includes
  the padding trap (LINPRT emits no leading space where BASIC's `PRINT`
  does, which prints `LARGEST997`) and snapshotting the clock before
  formatting.
- **Cookbook recipe: "Custom character set: copy the ROM charset to RAM and
  redefine glyphs"** — the `sei` / clear `$01` bit 2 / copy 2 KB / restore /
  `cli` / patch / `$D018` sequence, live-tested. Demo 04 requires a custom
  charset and demo 06 promises one, but the install sequence existed
  nowhere: `$D018`'s bit-fields were in hardware.md, CHAREN in
  zero-page.md, and the graphics spec covered authoring `.byte` rows only.
  Carries the `$D018` arithmetic (`$0400` + `$3000` = `$1C`), its readback
  trap (unused bit 0 reads as 1, so `$1C` reads back `$1D`), the VIC-bank
  constraint, handing `$15` back before returning to BASIC, and the
  decoded-text caveat below.

### Documentation
- **The string-literal case rule for assembly is now written down**
  (`6502-assembly` SKILL.md, `petscii.md`). Quoted text in a `.byte` goes
  UPPERCASE — ca65 does no translation, and ASCII `A`-`Z` coincides with
  PETSCII's letters while `a`-`z` is the graphics range, so
  `.byte "hello"` prints `└┌○──`. That is the reverse of the loudly
  documented `.bas` rule, and every asm example silently followed it
  without saying so. Scoped explicitly to the characters inside the
  quotes: ca65 is case-insensitive for mnemonics and labels, where
  lowercase stays the house style.
- **How to choose a `wait --text` sentinel** (`c64-development` SKILL.md,
  step 4 of the loop). `c64 run` resets the machine, so a wait can't match
  the previous run's output — but the reset restores the boot banner, and
  waiting on `READY.` or `BASIC` matches that instantly and returns before
  the program prints anything. Bit this run for real while verifying the
  case rule above.
- **A custom charset changes the glyphs, not the screen codes**
  (`c64-development` SKILL.md pitfalls, the new cookbook recipe, and the
  graphics spec, whose §1 claimed custom charsets were "fully observable as
  text through `c64 screen`"). The decoder maps each code through its *ROM*
  meaning, and codes **32, 96 and 224 decode to a blank** — demo 04 parked
  its head-facing-up glyph on 96 and the snake's head was simply absent
  from decoded text while sitting plainly in the PNG, during a death
  verification. Pinned by a test that asserts those three codes are the
  only blanks.
- **Catching the first frame after a trigger** (`c64-development`
  SKILL.md's Debugging section, and the cookbook's frame-stepping recipe).
  `c64 until mainloop` right after the keypress that starts play does not
  stop at move 1: `until` sets its checkpoint when it runs, and at warp the
  wall-clock gap is emulated seconds, so it silently returns an arbitrary
  later arrival. Arm `c64 break add mainloop` *before* the trigger — a
  checkpoint halts the machine on arrival with no gap to race. Cost demo
  04's first play-through.
- **The move that ends the game can't be driven by `c64 key hold`**
  (cookbook, held-key recipe). On the fatal move the program leaves the
  anchor for good, so the hold times out and leaves the machine running
  past the crash; break on the death path and poke `$CB` by hand for that
  one move. The same recipe now also states *why* `$CB` must be read at the
  top of the loop — the IRQ scan restores 64 within a jiffy of the poke.
- **Driving a game move-by-move wants MCP, not the CLI**
  (`c64-development` SKILL.md). Each `c64` invocation is a fresh Python
  process, measured at ~130 ms of startup; at 3-4 calls per move that is
  minutes of process startup while a warp-mode emulator sits idle.
- **A directory-sized demo keeps its prompt in `PROMPT.md`**, not
  `README.md` — `demos/invaders/` and `demos/1812/` renamed, and
  `demos/README.md` now links the file rather than the directory. The
  paste-into-your-agent prompt and documentation *about* a demo are
  different things, and `README.md` reads as the latter.
- **Demo 05 (debug hunt) is dogfooded** — `demos/README.md` and
  `index.html` updated. The run found all three planted bugs from the
  machine (the `?BAD SUBSCRIPT`, the `nop`-for-`inx` wedge proven by PC
  sampling plus a disassembly of the cassette buffer, and the
  PETSCII-vs-screen-code title) and fixed them, and found no product
  defects. The six observability gaps it walked into are recorded in
  `docs/todo.md`, not here, because none has a ruled fix yet.

## [0.7.0] — 2026-07-27

What a dogfooding run of demo 02 (bouncing beach ball) walked into. The
demo itself passed first try; everything here is friction found on the way.

### Added
- **`c64 wait --mem` takes comparisons**, not just equality:
  `ADDR<op>VALUE` with `=` `==` `!=` `>` `>=` `<` `<=` (`'$fb>=20'`). Waits
  poll, so an exact-value wait on a *counter* can hang forever after the
  machine steps past it between two polls — an inequality cannot miss. The
  YAML `wait` step gains the same reach as word keys (`equals`,
  `not_equals`, `above`, `at_least`, `below`, `at_most`, one per step), and
  `c64_wait_mem` gains an `op` argument.
- **`c64 sprite encode --format basic --start-line N`** (with
  `--line-step`, default 10) numbers the emitted `data` lines so the block
  pastes straight into a `.bas`. Numbering runs on across every sprite in
  one file, so a multi-sprite file stays a single ascending listing, and
  numbers past 63999 are refused rather than emitted.
- **Cookbook recipe: "Multicolor sprite from BASIC (ASCII art → DATA)"** —
  the bit-pair→register mapping (`01`→`$D025`, `10`→`$D027`, `11`→`$D026`)
  and the ASCII-art→`sprite encode`→`DATA`/`READ` path in one place, with a
  live test. The existing sprite recipe only covered a solid hires shape.
- **`tests/programs/bouncing-ball/`** — the demo-02 solution as a regression
  test: a multicolor sprite bounced around a character-graphics playfield,
  publishing a saturating edges-seen bitmask at `$02` plus a bounce count
  and last-edge code at `$FB`/`$FC` so a BASIC graphics demo is assertable
  without pixels.

### Fixed
- **`c64 sprite encode --format basic` emitted an uppercase `DATA`**, which
  is shifted PETSCII: the C64 tokenizes it as `STR$ ATN ATN`, so the rows
  had never been paste-able into a working listing. They are lowercase now,
  matching the petcat convention the rest of the toolchain uses.
- **A malformed `--mem` condition was reported as a symbol lookup failure** —
  `c64 wait --mem '251>0'` answered `unknown symbol '251>0'; known: `,
  pointing at the label table instead of at the condition. The condition is
  split on its operator before the address is resolved, so the error now
  names the real problem and lists the operators. A `--mem` timeout also
  reports the last value seen.

### Documentation
- **`c64 wait --break` resumes the machine and runs to the *next* hit** —
  it is the checkpoint counterpart of `c64 until`, not a passive block.
  `SKILL.md` presented it as "block until it fires" with "`c64 continue` to
  resume" as the following step, so the obvious sampling loop
  (`continue` → `wait --break` → inspect) silently advances **two** hits and
  observes every second frame. Documented in `SKILL.md` (with the correct
  frame-stepping loop), in `docs/cli.md`, and in the `--break` help text;
  a diagnosis row catches it by its symptom — sampled deltas exactly 2× what
  the code says. Inspection commands, by contrast, never advance the
  machine; the stopped-state rule now says which commands resume first.
- **`c64 break clear` does not clear watchpoints** — `c64 watch clear` does.
  `SKILL.md` said "clear stale ones (`c64 break clear`) or duplicates
  accumulate" without the caveat and never mentioned `watch clear`, so
  stale watchpoints silently kept stopping the machine.
- **Anchoring an observation on a BASIC program.** Assembly frame-steps with
  `c64 until LABEL`; BASIC has no label to break on, and anything sampled or
  screenshotted while the machine runs is a race under warp. `SKILL.md` and
  the graphics spec now prescribe the substitutes: a store watchpoint on a
  state byte the program pokes at the moment of interest (stops the machine
  *at* the event — the way to capture evidence), and a saturating summary
  byte for tests.
- **Where a demo's solution and evidence go.** The graphics spec required
  evidence at `demos/<name>/evidence/`, which single-file demo prompts
  (`demos/NN-name.md`) have no directory for. Both the spec and
  `demos/README.md` now say: directory demos commit evidence, single-file
  demos don't, and a program worth keeping graduates to `tests/programs/`.

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
  `c1541` accepts silently — are refused. A read reports `bytes` and `hex` —
  the same two key names `c64 mem read` uses, but not the same meanings: here
  `bytes` is the count and `hex` carries the sector, where `c64 mem read`'s
  `bytes` is a decimal int array. The hex payload key is `hex` in the CLI and
  MCP alike, and no release ever carried another name.
- **`c64 disk validate`** (with MCP parity) — the CBM allocation check.
  `c1541 -validate` prints the same line and exits 0 whether it repaired the
  BAM or not, so this compares the image before and after and reports what
  changed: `clean` is the flag to trust, `repaired_blocks` sizes it, and
  `messages` explains it in words. Structural damage c1541 *does* report —
  a directory entry pointing off the end of the disk prints
  `ERR = 65, NO BLOCK`, still at exit 0 — and that is a finding about the
  image rather than a failed command, so it joins `messages` with
  `clean: false` instead of erroring.
- **`c64 disk build game.disk.yaml`** (with MCP parity) — build a populated
  game disk in one reproducible step. Files land in listed order so the first
  one autostarts, `.s` entries are assembled and `.bas` tokenized, and the
  build is atomic: everything is staged beside the output and renamed over it
  only after the last file lands, so a build that fails partway leaves an
  existing image byte-identical. A manifest that would overflow the disk — on
  blocks *or* on the 144 directory entries a `.d64` holds — is refused before
  anything is formatted, because a full disk otherwise leaves a truncated file
  and a corrupt BAM behind. Every `.s` entry also leaves its VICE label file
  beside the output image as `<image-stem>.<cbm-name>.lbl`, reported under the
  payload's `labels` key, so a program loaded off the built disk can still be
  debugged symbolically. One file per entry rather than one merged table: two
  assembled programs on one disk are separate namespaces, and merging them
  would silently collide on every `start`/`loop` they share.
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
  missing file, scratching nothing, or poking past the end of a sector, so
  every verb that touches the DOS command channel — `put` (and `build` through
  it), `rename`, `rm`, `block read`, `block write` — now reads the DOS status
  line and c1541's own diagnostics instead of trusting the exit code.
  `create`, `ls` and `get` are unchanged: they still judge success by the exit
  code and the file they produce.

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
