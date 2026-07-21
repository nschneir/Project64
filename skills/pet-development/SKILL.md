---
name: pet-development
description: Use when developing, running, or debugging Commodore PET software (Commodore BASIC or 6502 assembly) on the VICE emulator with the c64 CLI or the c64-tools MCP server. Covers the build/run/observe/debug loop, the stopped-state discipline, PET text encodings, and per-model differences.
---

# Developing for the Commodore PET

This skill drives an emulated Commodore PET through the `c64` command line (or
the equivalent `c64-tools` MCP tools). Full command reference: `docs/cli.md`.
Every command takes `--json` for machine-readable output.

**Using MCP instead of the CLI?** The tools map mechanically — `c64 screen`
→ `c64_screen_text`, `c64 break add` → `c64_break_add`, and so on — with the
same sessions, semantics, and stopped-state rule. Two differences: `c64 wait`
is split into `c64_wait_text` / `c64_wait_mem` / `c64_wait_break`, and wait
timeouts return `{"fired": null, ...}` as data instead of an error.

## The loop

Write → run → observe → fix:

1. Write BASIC (`.bas`) or 6502 assembly (`.s`).
2. `c64 run FILE` — tokenizes/assembles as needed, loads, and RUNs.
3. Observe with `c64 screen` (decoded screen text) — this is the primary way
   to see output. Use `c64 wait --text "..."` to block until expected output
   appears; loading and running take a few emulated seconds even in warp, so
   never assume a program has finished — wait for a signal.
4. Fix and repeat.

Start a machine with `c64 session start` before anything else, and
`c64 session stop` when done.

## Sessions and models

`c64 session start --model pet4032` boots a PET 4032 (the default). Add
`--warp` to run at full speed for automation and `--headless` to suppress the
window. Models: `pet2001` (BASIC 1.0), `pet3032` (BASIC 2.0), `pet4032`
(BASIC 4.0), `pet8032` and `pet8296` (BASIC 4.0, 80-column). The 40- vs
80-column split matters when reading the screen; BASIC version matters for
which tokens and ROM routines exist.

## Writing BASIC

BASIC sources follow the `petcat` convention: **write keywords AND string
text in lowercase.** Lowercase ASCII maps to unshifted PETSCII, which the PET
displays as uppercase — so `10 print "hello"` shows on screen as
`10 PRINT "HELLO"`. Writing uppercase in the source produces shifted PETSCII,
which shows as graphics characters instead of letters. This is the single most
common mistake.

- `c64 run prog.bas` — tokenize, load, and RUN in one step.
- `c64 basic type prog.bas --run` — type the program in through the keyboard
  instead, which works mid-session and exercises the real ROM tokenizer.
- `c64 basic tokenize` / `c64 basic detokenize` — convert between `.bas` and
  `.prg` without a session.

## Writing assembly

6502 assembly is assembled with ca65/ld65 via `c64 build` or run directly with
`c64 run prog.s`. A PET program loads at `$0401` and needs a small BASIC `SYS`
stub so `RUN` starts it; the `6502-assembly` skill has the working skeleton and
the details. `c64 run` on a `.s` file automatically registers the assembled
label file on the session, so you can immediately set symbolic breakpoints like
`c64 break add start`.

## Debugging

Breakpoints and watchpoints are set while the machine runs, then you block on
them:

1. `c64 break add SYMBOL` (or an address) — set an execution breakpoint. It
   also accepts `--condition 'A != 0'` and `--temporary`. Checkpoints survive a
   later `c64 load`/`c64 run`, so set the breakpoint first, then load.
   Checkpoints persist across c64 run/rebuilds by design — clear stale ones
   (c64 break clear) or duplicates accumulate.
2. `c64 wait --break` — block until it fires; this leaves the machine stopped.
3. Inspect: `c64 reg` (registers, PC annotated with the nearest symbol),
   `c64 mem read ADDR LEN`, `c64 break list`.
4. Single-step: `c64 step N` (add `--over` to step over `JSR`s), `c64 finish`
   (run to the current subroutine's return), or `c64 until SYMBOL` (run to a
   point). Use `c64 watch add ADDR --store` to break on writes.
5. `c64 continue` to resume.

**The stopped-state rule.** The machine's run/stop state persists across `c64`
commands (a per-session monitor daemon holds it). Four commands intentionally
halt it so you can inspect it: `c64 step`, `c64 finish`, `c64 until`, and
`c64 wait --break` when it fires. After any of those the machine STAYS paused —
through as many inspection commands (`screen`, `mem`, `reg`, ...) as you like —
until you `c64 continue` or an explicitly-resuming command (`c64 run`,
`c64 load`, `c64 disk boot`, `c64 session reset`). Inspection never disturbs
the state.

## Text encodings — keep three straight

The PET uses three different byte encodings, and confusing them is a frequent
source of bugs:

- **ASCII** — what your host files and the CLI use.
- **PETSCII** — what the keyboard produces and what ROM output routines
  (CHROUT) consume. `$0D` is RETURN; letters are ASCII-uppercase codes.
- **Screen codes** — what actually sits in screen RAM at `$8000`. These are
  *not* PETSCII: `0` is `@`, `1`–`26` are `A`–`Z`, and bit 7 means reverse
  video. Reading screen RAM with `c64 mem read '$8000'` shows raw screen codes;
  `c64 screen` decodes them to text for you.

## Common pitfalls

- Uppercase in BASIC source → graphics garbage on screen (write lowercase).
- Multi-file assembly crashing with `?SYNTAX ERROR` at RUN, or a build
  failing with branch "Range error" after adding code — both are ca65
  traps (segment state leaking across `.include`; short branches
  outgrowing ±127 bytes). See the `6502-assembly` skill's gotchas for the
  fixes.
- Forgetting to `c64 wait` after `c64 run` and reading the screen too early.
- Reading `$8000` and expecting ASCII — it holds screen codes.
- Assuming the machine is running after `c64 step`/`finish`/`until` — it is
  stopped; `c64 continue` to resume.
- **Warp discipline.** At `--warp`, wall-clock seconds between your commands
  are emulated *minutes* — a game left running between two inspection
  batches will have played on (lives lost, screens changed, state moved).
  End every inspection batch STOPPED (`c64 until <label>`) and do
  multi-command verification in one atomic sequence, or expect drift.
- **`c64 wait --text/--mem` POLL.** Transient states (a 3-second game-over
  screen, a byte that holds a value for a few frames) can slip between
  polls at warp. For transitions, prefer a watchpoint:
  `c64 watch add ADDR --store` then `c64 wait --break`.
- Driving a game that reads held keys from `$97`? `c64 key type` only fills
  the type-ahead buffer — use `c64 key hold KEY --at <loop-label>`
  (BASIC 4 models; see the hardware reference for why).

## When something goes wrong — diagnosis table

(Quick lookups only — for full procedures such as store-watchpoint
corruption hunts, register-clobber audits, and deterministic
reproduction, use the `6502-debugging` skill.)

| Symptom | First move |
|---------|------------|
| Screen shows graphics glyphs instead of text | Uppercase in the `.bas` source — rewrite keywords AND strings lowercase. |
| `c64 wait --text` times out | `c64 screen` and look. The program may be awaiting input (feed it with `c64 basic type` or a `key` step), still loading, or crashed. |
| `c64 until LABEL` times out on a label that used to fire | The program branched away (death/menu/pause) and never executes LABEL again. Break at a code path that must still run and `c64 wait --break`. |
| Program seems to hang | Sample it: run `c64 reg` two or three times and compare PC. PC stuck in your code = your loop is wrong; PC around $E4xx = the machine is idling in BASIC waiting for input. |
| Assembly crashes or drops to READY immediately | The SYS stub math is off — `c64 rom disasm 1037 16` and confirm your first instruction is at $040D. |
| `?SYNTAX ERROR` when running a loaded program | Inspect what actually loaded: `c64 basic detokenize file.prg`. |
| Machine appears frozen after debugging | It's stopped (step/finish/until/wait --break leave it stopped) — `c64 continue`. |
| Program vanished after `c64 run` | Autostart resets the machine first — that's normal; reload anything else you need. |
| Disk command misbehaves | Check the drive status: `print ds$` (error table in references/basic-internals.md). |

## When the tooling itself misbehaves

The `c64` CLI drives a real VICE emulator process, so occasionally an
*operational* failure happens that has nothing to do with your program. Stay
out of the weeds — do NOT read c64-tools' own source or launch `x64sc` by
hand. The fixes are simple:

- **`c64 session start` fails ("monitor never answered").** A cold emulator
  under load can be slow to come up. Just run `c64 session start` again
  (add `--warp` for a faster boot). If it keeps failing, list what's running
  with `c64 session list`, `c64 session stop` anything stale, and retry.
- **"session already running" / a name is taken.** `c64 session stop <name>`
  (or pick a different `--name`), then start fresh.
- **Commands say "no PET session running."** You have no session, or you're
  not naming it — start one, or pass `--session <name>`.
- **A session seems wedged.** `c64 session stop <name>` and start a new one;
  a fresh session is cheap.

## Verifying a change

Prove a change works, don't assume it. Either assert on output with
`c64 wait --text "EXPECTED"`, or write a declarative test and run it with
`c64 test run mytest.yaml` (a `program` plus `wait`/`key`/`assert` steps —
full format under `c64 test run` in docs/cli.md). Existing example
programs can all be run as tests with `c64 test programs`.

## References

Read the matching file when you need the detail:

- `references/cookbook.md` — **start here for a new program**: tested,
  copy-adaptable recipes (game loops, screen pokes, sound) in BASIC and asm.
- `references/memory-maps.md` — per-model memory layout (RAM, screen, ROM, I/O).
- `references/zero-page.md` — BASIC pointer chain and low-memory usage.
- `references/rom-routines.md` — kernal jump table and hardware vectors.
- `references/basic-internals.md` — program storage format and token table.
- `references/petscii.md` — the three text encodings and the screen-code table.
- `references/hardware.md` — I/O chip base addresses (PIA/VIA/CRTC), IEEE-488.
