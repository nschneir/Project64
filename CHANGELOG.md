# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged. Project64 is a Commodore 64 port of
[PET-Project](https://github.com/nschneir/PET-Project); its PET-era history
lives in that repository (and in this one's git history before the fork
commit).

## [Unreleased]

An MCP-wired agent no longer needs a shell. The six commands both
`docs/agent-setup.md` and the `c64-development` skill told it to shell
out for have tools now — `c64_break_enable`/`c64_break_disable`, the MCP
twin of the monitor's `checkpoint_toggle`, and the four offline ones that
need no session at all: `c64_basic_tokenize`/`c64_basic_detokenize`,
`c64_sprite_encode` and `c64_charset_encode`. That takes the server from
68 tools to 74, covering all 75 CLI commands — the two counts differ
because rows fold, not because anything is missing: `c64 wait` is four
tools, `c64_break_remove` also removes watchpoints, and `c64 mem get` is
a print-formatting variant of `c64_mem_read`. The carve-out list in
`tests/test_mcp_scaffold.py` is empty as a result; the list and its test
stay, so a future exclusion has to be written down with the reason it is
one instead of accumulating in silence. Encoding is shared with the CLI
rather than reimplemented — `sprites.render_sheet` is now the one place a
multi-sprite sheet gets its running line numbers, called by both — and
the two encode tools are the one place a payload deliberately exceeds the
CLI's `--json`: they add `rendered`, the paste-ready text the command
prints to stdout, because MCP has no stdout and without it `fmt`,
`start_line` and `first_code` would be no-ops.

Three smaller gaps went with them. `c64_build` takes `output`, the CLI's
`-o`, which the tool had no way to spell — a build could only land beside
its source. `c64_sid_report` takes `peak_hz`, the same rFFT measurement
as the command's `--peak-hz`, and refuses it without a `wav` because a
dominant partial is a property of the recording and not of the register
log. And `c64_load` records what it loaded, so `c64_status`'s stale-source
warning fires after an MCP load: it had been reporting `"stale": []` no
matter how old the binary was, because the tool never called
`record_loaded` the way `c64 load` and `c64_run` always have.

The map itself is written down and measured, in the new `docs/mcp.md`:
one row per registered tool, naming the command it twins and the one-line
difference where there is one — the folded rows, the renamed parameters
(`--from` → `src`, `--format` → `fmt`, `--peak-hz` → `peak_hz`), the
headless-and-warp sessions the tools hardcode, and the wait timeouts that
return `{"fired": null, ...}` as data where the CLI exits 1. The page
states no tool or command counts of its own, since a second uncounted
copy of index.html's numbers is the drift it exists to prevent; two tests
guard it the way those counts are guarded — every registered tool must
appear in it, and every command its tables name must still exist in the
CLI. `README.md`, `docs/cli.md`, `docs/agent-setup.md` and the
`c64-development` skill point at it, and index.html reads 74 tools.

A segment can be linked where the VIC needs it. `c64 build --area
NAME=START:SIZE` (repeatable; also on `c64 package`, and `areas` on the
`c64_build`/`c64_package` MCP tools) declares an extra linker MEMORY area
and puts the identically named segment in it — so a RAM character set lands
on its 2 KB boundary and sprite blocks on their 64-byte ones without a
startup copy loop. A `.prg` is a flat file, so the flag caps `MAIN` at
`area.start - load_address` and fills it: the gap below the area ships as
real zero bytes, which is what makes the segment land there. Areas are
declared `define = yes`, so `__NAME_LOAD__`/`__NAME_SIZE__` are available
for a link-time `.assert` on the ceiling. Everything a wrong `--area` could
do quietly is a rejection instead, naming the flag rather than the config
generated behind it: a gap between two areas (with the size to raise), an
overlap, an area at or below the load address, a zero size, a name that
would redefine one of the config's own, and — the same way `--cart-type`
already works — `--area` passed for a `.bas`, a `.prg`, or a cartridge.
With no areas the generated config is byte-identical to what it has always
been, pinned by a test.

Two sheet-encoder frictions the same dogfood turned up. `c64 charset encode`
takes a per-block mode — `wall:multicolor`, `letter:hires` — so a multicolor
playfield charset and a hires HUD font are one sheet and one invocation
instead of two of each; `--hires` now sets the file's default, which a block
may override, and an unrecognized suffix is rejected by name. The JSON
payload carries `multicolor` per glyph. And `c64 sprite encode` says *which*
block is malformed: `sprite 12 (line 265): art must be 21 rows, got 14`,
where before a sheet of 27 shapes reported only the row count and had to be
bisected by hand. Sheets that name no mode encode byte-identically to before
— both committed demo sheets re-encode to their existing `.inc` files.

A `c64 test run` comparator given a literal now says what it wanted.
`differs`, `greater_than`, `less_than` and `unchanged` compare against a
recorded `sample:`, never against a number — `differs: 0` used to fail with
"no sample named '0'", which is true and unhelpful. When the operand parses
as a number the error names the design and shows the `sample:` step to add;
when it does not, the message is unchanged, so a typo'd sample name still
reads as a typo. `docs/cli.md` gains the table of which assert keys take a
literal and which take a sample name.

Six things the skills and references were silent about, each of which cost
the Ms. Muncher dogfood a debugging pass or a whole audit iteration. The
`c64-development` skill now says that `c64 call` **ends the run** it is
called in (the CLI reference always said so; the skill that recommends the
command did not) and that `c64 wait --text/--mem` **poll and do not
resume**, so one issued after `until`/`step`/`finish`/`wait --break` can
only time out — inside a YAML spec too. Both get a diagnosis-table row.
`zero-page.md` gains a second, live-measured table: the 75 bytes a program
that owns the machine may claim, with the caveats that make them free (one
ROM call takes them back; `$73-$8A` is the CHRGET *routine*; everything the
KERNAL IRQ maintains stays off the list). The `6502-assembly` skill gains
the gotcha that an indexed loop calling a subroutine must reload its index.
The cookbook gains the bank-0 budget — all three consumers of the VIC's
16 KB, the three ways out, and the `.assert` that turns the ceiling into a
build failure — and the two ways a Galois LFSR silently stops being random,
with the recipe extended to *prove* its 255-value cycle as a live-tested
`DISTINCT 255`. `audio-verification.md` covers assembly lead-ins (taken per
start, not baked into looping track data) and the one-shot cue that makes a
score independent of arming latency. Finally, `docs/graphics-and-sprites.md`
§5 writes down the deterministic evidence protocol both game demos had
reinvented separately.

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
prompts — Snake, Invaders, Ms. Muncher, La Galaxia and 1812 — now require
the artifact set under
`evidence/audio/` and a passing report, alongside the SID shadow bytes they
already required: the shadows prove a write was issued, the capture proves
what came out of the chip. Finally, the method — capturing, authoring a
score from your note tables, reading a roll and a spectrogram, and the
register facts behind all of it — is written up in the new reference at
`skills/c64-development/references/audio-verification.md`. Two demos arrive
with it: `demos/05-bach-invention/`, a test demo asking for Bach's two-part
Invention No. 13 out of BASIC and proved by capture — prompt-only like the
rest of that tier, where the run is the deliverable and nothing is
committed — and `demos/fugue/`, BWV 847 on three voices in assembly with
its score scrolling past as it plays, prompt-only so far and waiting to be
built.

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
