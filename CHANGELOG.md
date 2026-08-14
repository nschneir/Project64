# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged. Project64 is a Commodore 64 port of
[PET-Project](https://github.com/nschneir/PET-Project); its PET-era history
lives in that repository (and in this one's git history before the fork
commit).

## [1.0.0] — 2026-08-14

One-point-oh gates on the code being right rather than on a feature: a
high-effort review of everything since 0.9.5 (242 commits, ~19k lines across
`src/` and `tests/`) produced ten correctness findings — nine confirmed,
most by live reproduction, and one refuted by a measurement that then
convicted a different site. All nine are fixed in this release, red test
first: a truncated WAV can no longer pass the audio verdict, a refused
`--at-frame` schedule can no longer silently double a capture window, a
corrupt session record can no longer silently reboot a cartridge into the
wrong emulator, `disk get` can no longer be steered outside the working
directory by a hostile disk name, PAL captures get an honest real-time
warning, non-ASCII WAV paths work, and the charset/sprite-sheet, `--area`
and BASIC-lint regressions the review caught are gone. The one refuted
finding is recorded where it was measured, and the new one it exposed is in
`docs/todo.md`.

A landing pass (2026-08-14) closed seventeen `docs/todo.md` items in one
change. The toolchain half: `c64 sprite png` now renders with the emulator's
own palette — the same `mon.palette()` `c64 screen --png` uses — keeping the
hardcoded Pepto table only as the session-less fallback, with a live test
that renders one sprite through both writers and fails if they diverge;
`c64 audio capture --at-frame` accepts a symbol anywhere it accepted a number,
resolved against the session's label file like every other address argument;
an audio `report.md` now names the reference score it diffed against with its
per-voice entry and frame counts, or says "no reference score supplied"
outright, so a committed report can no longer be mistaken for a check that
ran; and the piano roll rules every semitone row, so a bar between two
thinned labels can be named by counting lines. The reference half: the
"toolset's screen reader assumes `$0400`" claim in two skill files was
measured false and corrected (reads follow `$DD00`/`$D018`; colour RAM is
what never moves), the badline row-latch rule that decides every redraw
deadline is now stated in `hardware.md` and scoped into the cookbook's budget
recipe, and the cookbook gained two live-tested recipes it had long promised
— smooth horizontal scrolling and a frame-driven three-voice SID player.
`c64 test run`'s arm-before-run guarantee (a spec's first `until` is the
program's first arrival) is documented against the measured CLI
counter-example, the two encode twins now name each other's hires background,
the evidence-helper snippet names the `#!/bin/sh` it assumes, and the
WAV/log bracket figure is marked host-dependent with a second measurement.
Demo maintenance: `demos/1812`'s audit register table was re-taken on the
machine, its wrap-prone voice-1 witness replaced, and its evidence protocol
now prints all seven determinism bytes and the section-3 cannon count from
collision-free temp files; `demos/la-galaxia`'s fighter-movement flake is
staged free before it samples (5/5 green, and still red under a sabotaged
`keydecode`); `demos/invaders`' one-raster sprite offset was re-judged by eye
and kept, with the judgement recorded at the constants. Shipping a demo is
now a checklist in `demos/README.md` rather than a red suite, and a new
`needs_c1541` test pins every shipped `.d64`'s autostart file to the
committed `.prg` beside it. Measured along the way and recorded in the
graphics policy: `until`-anchored evidence PNGs churn bytes across runs just
as `call`-staged ones do (the raster phase at a label is not fixed), so the
frame-top capture primitive's reopen condition is met and the remaining open
items — with the judgement each survived on — are in `docs/todo.md`.

The demos are playable in a browser. `play.html` embeds vc64web — a
WebAssembly port of VirtualC64 — loaded at runtime from a maintainer-owned
fork, with ▶ PLAY links from the landing page and both READMEs. It boots five
demos from their `.prg` on the MEGA65 open-roms KERNAL, BASIC and character
ROMs, so no Commodore ROM is hosted or sent to a browser, and with no 1541 ROM
in the set there is no drive to load from.

That exposed a ROM dependency nobody had written down: **`$CB` is Commodore's
KERNAL, not the C64.** All five demos polled it for the held key and open-roms
never maintains it, so it reads a constant 0 and no key registers. Each demo
now scans the CIA matrix at `$DC00`/`$DC01`, keeping `$CB` as a fallback so
`c64 key hold` still drives them; the trap is written into the skills.
Separately, `c64 key hold` now *releases* the key — an unreleased hold pinned
it down for the rest of any run that switched the KERNAL scan off.

Operational failures are a contract rather than a traceback. Seven commands
that crashed on ordinary conditions now exit 1 with a parseable `{"error": …}`,
and under them the CLI's root group catches thirteen exception types as a
floor — a `--json` caller previously got empty stdout, indistinguishable from
a crashed process. `c64 session stop --all` reaps the emulators an interrupted
run leaves behind, and `c64 profile --samples N` reports min, max and mean,
because one measurement of a data-dependent routine is a distribution reported
as a fact.

A timed-out `--mem`, `--text` or `--idle` wait now says **where the machine
was**: all three only poll, so a machine stopped for the whole window burned
the timeout and reported nothing useful.

Sound is verifiable. Capture windows can be aimed and report the arming cost
they measured, `sid-log.jsonl` carries its own clock stamp, the score diff
compares pitch rather than spelling, `--strict` turns a silent capture into a
failure, and the `warp on` wedge is fixed at its cause. 1812's iteration 3 put
that to work: the arrangement was rebuilt as a texture arc from solo piano
outward, and the demo gained the audio evidence it never had.

An MCP-wired agent no longer needs a shell, and `docs/mcp.md` maps every tool
to the command it twins. Elsewhere: `--area` reaches the places that could not
use it, so a segment links where the VIC needs it and a spec builds from
source; a ready-made `cart:` is judged for staleness; a `c64 test run`
comparator given a literal says what it wanted; the sprite and charset sheet
encoders share a header parser and take named blocks, per-block modes and
`--background`; `fix-branch-range.py` makes the ±127 branch trap mechanical;
and a batch of skill and reference gaps that cost real dogfood time are
closed, each with the test that would have caught it.

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
