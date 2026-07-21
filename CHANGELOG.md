# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged.

## [1.3.0] — 2026-07-21

Routine-level unit testing and a debugging playbook — the two additions a
post-project retrospective ranked worth building.

### Added
- **`c64 call ROUTINE`** — the unit-test primitive: emulates a `JSR` in
  isolation (fake return address on the stack, optional `--a/--x/--y` on
  entry) and stops at the routine's own `RTS`, leaving registers and
  memory holding its results. Poke inputs, call one routine, assert
  outputs — nothing else runs in between. Also a YAML **`call:` step**
  (`call: { routine: addscore, a: 5 }`) and MCP `c64_call`. The Ms.
  Muncher suite now unit-tests `addscore` (BCD adds, hiscore chase, the
  10,000-point bonus life) and `cell_glyph`'s door special case this way.
- **`6502-debugging` skill** — a symptom-indexed playbook of the
  procedures that cracked the dogfood's hard bugs: prove-the-binary-first
  (stale-load rule zero), store-watchpoint corruption hunts,
  register-clobber audits by isolation, deterministic reproduction with
  poke + frame-stepping, branch-away deadlock avoidance, exact-glyph
  assertions, and warp inspection discipline.

## [1.2.0] — 2026-07-21

The friction-fixes release: every change answers a concrete pain point hit
while building Ms. Muncher (demo 07, an arcade-faithful maze chaser in
`demos/muncher/`) with the 1.1 toolset.

### Added
- **Stale-binary guard** — the trap that cost the most dogfood time: a
  failed rebuild left the emulator running the previous binary while
  "verification" proceeded against it. `c64 build` now records the full
  dependency list (ca65 `--create-dep`, so `.include`d files count);
  `c64 run`/`c64 load` stamp load provenance on the session; `c64 status`
  reports the loaded program and a loud `STALE (source changed since
  load:)` line; a failed `c64 run` says the emulator is still running the
  PREVIOUS program.
- **Unicode screen decoding** — `c64 screen` now decodes graphics codes to
  real box/block/shape glyphs (`╭─╮ ● ▌ █ …`), with reverse-video codes
  mapped to their pixel-complement glyph where Unicode has one
  (`▌`↔`▐`, quadrants → `▛▜▙▟`, `$A0` → `█`); `--ansi-reverse` for
  terminal inverse on the rest, `--style ascii` for the legacy mapping.
  **Migration:** `wait --text` patterns matching the old `·` placeholder
  need updating (plain text is unaffected) — see docs/cli.md.
- **`c64 screen --codes`** — the raw 25×40 screen-code matrix (exact glyph
  assertions), and **`c64 screen --png --scale N`** — nearest-neighbour
  upscale (PET screens read better at 2–3×).
- **`c64 session ensure`** — attach-or-start, idempotent; the recovery
  one-liner the daemon circuit-breaker error now points at. A test
  documents the `c64 test run` isolation contract (throwaway uniquely
  named session, user sessions untouched).
- **CLI paper cuts** — `c64 break rm` / `c64 watch remove` / `c64 watch
  rm`; `c64 break add --once`; `c64 wait --break CK_ID` (id filter so a
  leftover breakpoint can't intercept a watchpoint wait); `c64 mem write
  --stdin` (batch `REF V1 V2 …` lines, heredoc-friendly).
- **Richer YAML asserts** — `equals_any` (alternatives), `mask`
  (`{and: $7f, equals: [...]}` — e.g. ignore the reverse-video bit), and
  `between` (`{min, max}` byte range).

### Fixed
- Unknown symbol in an arithmetic ref (`dots+82`) now reports the symbol
  (`dots`, with candidates), not the whole string.
- `wait_for_break`'s stop-event fast path respects the checkpoint filter.

### Documentation
- 6502-assembly skill: growing code breaks short branches (prefer `jmp`
  trampolines in blocks expected to grow); ca65 segment state carries
  across `.include` (start every include with an explicit `.segment`).
  Both hit repeatedly during the dogfood; pet-development cross-references
  the symptoms.

## [1.1.0] — 2026-07-12

The dogfooding release: everything here came out of building real software
with the toolset — the six demo prompts, capped by an arcade-faithful
Invaders in 6502 assembly (demo 06; the playable
`invaders.d64` ships in `demos/invaders/`).

### Added
- **Per-session monitor daemon** — the machine's run/stop state persists
  across commands, so a breakpoint halt survives any number of inspection
  steps; `c64 status` reports the tracked state (also on `c64 reg`).
- **`c64 package`** — one-step shareable artifacts: a `.prg`, or a
  `.d64`/`.d80`/`.d82` whose first file autostarts in stock VICE.
- **`c64 key hold KEY --frames N --at LABEL`** — held-key game input via the
  `$97` key-down byte, re-poked before each frame-step (CLI + MCP).
- **Address forms** `symbol+offset` (`alienX+49`) and `@row,col` (screen
  cell, resolved against the session model's 40/80-column geometry),
  accepted everywhere an address is.
- **`poke:` and `until:` steps** in the `c64 test run` YAML — deterministic
  frame-stepped game regression tests (see
  `demos/invaders/invaders-test.yaml`); step addresses take symbols,
  offsets, and `@row,col`.
- `c64 mem find` byte-pattern search; decimal reads (`c64 mem get`,
  `--decimal`, `bytes[]` in JSON output).
- `c64 break clear` / `c64 watch clear`.
- The `pet2001-4k` launch profile (the 4 KB entry-level 1977 PET).
- Cookbook recipes, all live-tested: held-key input ($97), charset
  switching, BASIC score HUD, decimal digits, IRQ wedge, note-table melody,
  Galois-LFSR random bytes, plotaddr, poked HUD text.
- Demos 05 (debug hunt) and 06 (Invaders) dogfooded. 05 passed on the
  agent's first attempt; 06 needed one follow-up prompt — the first
  build's keyboard was dead under stock x64sc's default model (the
  BASIC 2 vs 4 `$97` split fixed above).

### Performance
- **Fast frame stepping**: the `c64 until --count` loop runs inside the
  session daemon, and the monitor consumes stop events the moment they land
  instead of listening out the poll window — 200 arrivals in ~0.3 s where
  each previously cost ~0.5 s.

### Fixed
- `c64 package` run hints pin the emulated model
  (`x64sc -model 4032 game.d64`): stock x64sc boots its own default model,
  and ROM behavior differs silently between BASIC generations — the `$97`
  key-down byte holds decoded PETSCII on BASIC 4 but a raw matrix index on
  BASIC 2, which reads as a dead keyboard on an identical-looking screen.
- `c64 until` / `c64 wait` timeouts are loud about leaving the machine
  running (and `until` removes its checkpoint).

### Documentation
- `$97` semantics corrected in the zero-page and hardware references
  (PETSCII vs matrix index, with the scanner addresses pinned by live
  tests on c64 and pet3032).
- Warp discipline and wait-polling pitfalls in the pet-development skill;
  the BSS-is-not-in-the-.prg gotcha in the 6502-assembly skill.
- How `c64 screen` decodes graphics/reverse-video, with live-verified
  free zero-page bytes for user ML pointers.

## [1.0.0] — 2026-07-10

Initial public release — the complete v1 toolset:

- **Sessions** on VICE x64sc: launch/attach/stop, six machine profiles
  (pet2001 through pet8296), `--warp`/`--headless`/`--disk`.
- **Observe**: `c64 screen` (decoded text or PNG), `c64 mem read/write`,
  `c64 reg` with PC symbol annotation.
- **Build & run**: `c64 build` (ca65/ld65 with the PET SYS-stub linker
  config), `c64 basic tokenize/detokenize/type` (petcat), `c64 load` /
  `c64 run` with automatic label registration.
- **Debug**: symbolic breakpoints and watchpoints with conditions,
  `c64 step`/`finish`/`continue`/`until`, and the `c64 wait`
  synchronization primitive (`--text` / `--mem` / `--break`).
- **Disks**: `c64 disk create/ls/put/get/boot` via c1541.
- **ROM tools**: `c64 rom info` (ROM-set identification) and annotated
  live disassembly — reading bytes from the user's emulator, shipping none.
- **Testing**: the declarative YAML runner (`c64 test run`) and example
  programs as regression tests (`c64 test programs`).
- **MCP server** (`c64-tools-mcp`) exposing the same operations as the CLI
  against the same sessions.
- **AI enablement**: the `pet-development` and `6502-assembly` skills, the
  machine/zero-page/ROM/PETSCII references, `docs/cli.md`, and the graded
  demo prompts (01–04 dogfooded at release).
