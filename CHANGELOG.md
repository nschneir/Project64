# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged. Project64 is a Commodore 64 port of
[PET-Project](https://github.com/nschneir/PET-Project); its PET-era history
lives in that repository (and in this one's git history before the fork
commit).

## [Unreleased]

Removed the pyright CI workflow — type checks are a local, pre-commit gate
again rather than a CI job that could go red on unrelated dependency churn.
Closed out the ROM label database with its final tranche: `basic2.lbl` grew
184 → 291 labels, covering the BASIC token dispatch tables, the
floating-point package, and the IEC serial and tape KERNAL internals.
Dogfooded demo 06 (Invaders), which now ships its whole solution — sources,
a fidelity audit, a regression test and a runnable `.d64` — and closed the
twelve CLI, skill and cookbook gaps it found (only its process items are
still open in `docs/todo.md`). Dogfooded Snake under its promoted game-demo
prompt: `demos/snake/` now ships the same way, with a three-iteration audit,
a 101-step regression spec, seven evidence frames and `snake.d64`. This
changelog itself was cut from 843 lines to something a person can actually
skim.

Out of that dogfood: `c64 profile REF` reports hardware cycle counts for one
routine (CIA#2 cascade, IRQs masked by default, `--with-irq`), with the MCP
twin `c64_profile`; and `c64 charset encode` turns ASCII art into charset
`.byte` rows (multicolor `.123`, hires `.#`), retiring the invaders demo's
local converter. `-s/--session` is now accepted after the subcommand, like
`--json`. Disk boots register symbols — `c64 disk boot`,
`c64 session start --disk/--cart`, and disk test specs pick up a sibling
`.lbl` (or `disk build`'s first-entry label), silently skipped when absent.
`mem get`/`mem read` JSON payloads now both carry `values` and `bytes`, and
`c64 mem write` names a bad byte token instead of dumping a traceback and
accepts one whitespace-separated byte string; bad LENGTH/COUNT/VALUE args
across the CLI fail cleanly too. Newly documented: the sprite-Y ↔ text-row
mapping (`51 + 8*R`), the `.include` resolution contract (now build-tested),
routine-level unit testing with `c64 call`, the misleading-`until` diagnosis
row, and a live-tested screen-code-readback collision recipe.

## [0.9.0] — 2026-07-31

Closed out the test-health and observability backlog from dogfooding demo
05: fixed a "headless" VICE launch that was actually stealing keyboard
focus (the likely cause of prior test flakiness), and made hex dumps,
disassembly, register output, and BASIC linting report enough context that
a debugging agent no longer has to guess. Also grew the ROM label database
(44 → 184 labels) and made `pyright` a required, zero-error CI gate.

## [0.8.0] — 2026-07-28

Dogfooding runs of demos 03-05 (benchmark, Snake, and a debug hunt) found
and fixed a stale-build false positive and a screen-wait race, and
documented a batch of C64-specific pitfalls (custom charsets, timing,
frame-stepping, and driving a game via MCP vs. the CLI).

## [0.7.0] — 2026-07-27

Dogfooding demo 02 (bouncing ball) added comparison operators to
`c64 wait --mem`, numbered BASIC sprite-data output, and fixed a
non-pasteable uppercase `DATA` bug, alongside documentation on checkpoint
vs. watchpoint semantics.

## [0.6.0] — 2026-07-27

Disks: complete file CRUD, raw block access, disk validation, one-command
game-disk builds, and the runtime half of disk I/O, plus fixes for c1541
calls that failed silently.

## [0.5.0] — 2026-07-25

Cartridges: build, verify, boot and debug `.crt` images, including an
EasyFlash banking runtime and skill.

## [0.4.0] — 2026-07-25

Driving interactive programs: bordered screenshots, since-aware text
waits, numbered screen output, and a fix for `c64 key type` mishandling a
literal `\n`.

## [0.3.1] — 2026-07-25

Test-suite change only: live tests now share one emulator session instead
of launching a fresh one each, roughly halving full-suite runtime.

## [0.3.0] — 2026-07-24

Added `c64 basic check`, a static BASIC V2 linter that models the real
tokenizer to catch errors petcat would otherwise accept.

## [0.2.0] — 2026-07-22

Added sprite tooling — the `c64 sprite` command group and YAML-based
motion testing.

## [0.1.0] — 2026-07-21

The founding release: the PET edition ported to the Commodore 64.
