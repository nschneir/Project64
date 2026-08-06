# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged. Project64 is a Commodore 64 port of
[PET-Project](https://github.com/nschneir/PET-Project); its PET-era history
lives in that repository (and in this one's git history before the fork
commit).

## [Unreleased]

Sound is verifiable now. `c64 audio capture` (MCP `c64_audio_capture`)
records the machine's audio to a WAV while sampling `$D400–$D418` once per
frame, transcribes the register log into notes, diffs them against a
reference score you write in YAML, and drops five artifacts — `capture.wav`,
`sid-log.jsonl`, `piano-roll.png`, `spectrogram.png`, `report.md` — with a
PASS/FAIL verdict; the pieces are also separately available as `c64 audio
record`, `c64 audio sidlog` and `c64 audio report`, the last of which takes
`--peak-hz` to measure a recording's loudest frequency against the pitch its
registers predict. Piano-roll voice colors are fixed (voice 1 red, 2 green,
3 blue) so rolls compare across demos, and a capture pins real time for its
duration — warp off, `Speed` 100 — so real time is the floor on what it
costs: every logged frame is a monitor round trip on top, which puts a
30-second capture at 60–80 seconds of wall clock. The five full-build demo
prompts — Snake, Invaders, Ms.
Muncher, La Galaxia and 1812 — now require the artifact set under
`evidence/audio/` and a passing report, alongside the SID shadow bytes they
already required: the shadows prove a write was issued, the capture proves
what came out of the chip. Finally, the method — capturing, authoring a
score from your note tables, reading a roll and a spectrogram, and the
register facts behind all of it — is written up in the new reference at
`skills/c64-development/references/audio-verification.md`. Two demos arrive
with it, both prompt-only for now: `demos/05-bach-invention/`, a test demo
asking for Bach's two-part Invention No. 13 out of BASIC and proved by
capture, and `demos/fugue/`, BWV 847 on three voices in assembly with its
score scrolling past as it plays.

## [0.9.5] — 2026-08-03

Removed the pyright CI workflow — type checks are a local, pre-commit gate
again rather than a CI job that could go red on unrelated dependency churn.
Closed out the ROM label database with its final tranche: `basic2.lbl` grew
184 → 291 labels, covering the BASIC token dispatch tables, the
floating-point package, and the IEC serial and tape KERNAL internals.
Dogfooded demo 06 (Invaders), which now ships its whole solution — sources,
a fidelity audit, a regression test and a runnable `.d64` — and closed the
twelve CLI, skill and cookbook gaps it found (its process items were tracked
in `docs/todo.md` and have since landed). Dogfooded Snake under its promoted
game-demo prompt: `demos/snake/` now ships the same way, with a
three-iteration audit, a 101-step regression spec, seven evidence frames and
`snake.d64`. This changelog itself was cut from 843 lines to something a
person can actually skim.

Out of that dogfood: `c64 profile REF` reports hardware cycle counts for
one routine (CIA#2 cascade, IRQs masked by default, `--with-irq`), with the
MCP twin `c64_profile` — and it refuses an impossible measurement,
reporting an error when the timers read back untouched (a raw count of 0,
which no routine can cost, and which the start slack used to dress up as
`"cycles": 3`), with the machine left stopped at the trap as on success;
and `c64 charset encode` turns ASCII art into charset `.byte` rows
(multicolor `.123`, hires `.#`), retiring the invaders demo's local
converter. `-s/--session` is now accepted after the subcommand, like
`--json`. Disk boots register symbols — `c64 disk boot`, `c64 session start
--disk/--cart`, and disk test specs pick up a sibling `.lbl` (or `disk
build`'s first-entry label), silently skipped when absent. `mem get`/`mem
read` JSON payloads now both carry `values` and `bytes`, and `c64 mem
write` names a bad byte token instead of dumping a traceback and accepts
one whitespace-separated byte string — and so do `c64 disk block write`'s
VALUES, which take those same tokens as separate arguments or as one
whitespace-joined string (what an unquoted zsh variable expands to), naming
a bad value by its position; bad LENGTH/COUNT/VALUE args across the CLI
fail cleanly too. Newly documented: the sprite-Y ↔ text-row mapping (`51 +
8*R`), the `.include` resolution contract (now build-tested), routine-level
unit testing with `c64 call`, the misleading-`until` diagnosis row, and a
live-tested screen-code-readback collision recipe.

Out of the Snake dogfood's tool items: `c64 key hold --frames 0` is now a
validated no-op (exit 0, machine untouched) instead of a fabricated
timeout — over the CLI and MCP alike — and `@@row,col` resolves a cell's
color-RAM address (fixed `$D800` base; reads are 4-bit, so compare masked
with `$0F`) everywhere addresses are accepted: mem commands, waits and
watches, YAML `mem:` steps, and the MCP tools.

Three cartridge follow-ups changed shipped behavior. `wrap_prg` now refuses
the load ranges its launcher cannot copy to — `$A000-$BFFF` (under the BASIC
ROM), `$D000-$DFFF` (I/O) and `$E000-$FFFF` (under the KERNAL) — so a
machine-language wrap must land below `$8000` or in `$C000-$CFFF`; images
that used to build, pass `cart_verify` and boot dead are now rejected with
the relocation named. Every EasyFlash window carries a BSS area in RAM, so
`.segment "BSS"` links in a banked cart: `$0A00-$7FFF` for the lo and hi
windows, `$0A00-$0FFF` for the Ultimax boot window, overlapping between banks
by construction. And a non-cart program's ZEROPAGE area starts at `$0002`
rather than `$0000`, off the 6510 port registers at `$00`/`$01` — ZEROPAGE
symbols link two bytes higher than they used to.

Out of the 1812 dogfood's items: `assert:` mem steps now take the same six
word comparisons as `wait:` (`equals`/`not_equals`/`above`/`at_least`/
`below`/`at_most`), a step with no comparison fails naming the step and the
whole comparison menu instead of a bare `KeyError`, and `unchanged: NAME`
asserts sample-vs-sample equality — "this byte did NOT change", the
hold/pause/game-over claim. `c64 test run --json` and `c64 test programs
--json` keep the `{"passed", "tests"}` envelope on spec-level errors, so a
parsing harness reports the failure instead of crashing on a missing key.
The cookbook gained two live-tested recipes — signed 8×8→16 multiply by
quarter squares (512-entry tables built at startup from their own first
difference) and multicolor bitmap from zero (mode bits, clear, one masked
span) — and its LFSR range-trick paragraph now tells the truth:
reject-and-retry yields 1 to N−1 (0 is unreachable), is positionally biased
and slow at small bounds, so scale with `(rnd * bound) >> 8` instead. Newly
documented: equates need `.export`/`.exportzp` to reach the label file, BSS
consumes address space after DATA (guard the ceiling with a deferred linker
`.assert`), and `until --count N` is a frame count only when the anchor
label is frame-paced.

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
