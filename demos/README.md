# Demos — prompts to try with your AI agent

Each file in this directory is a ready-to-paste prompt for an AI coding agent
set up with this toolset (see the README's "Using with AI coding agents").
Paste one into your agent and watch it write, run, and debug real Commodore
PET software on the emulated machine.

They're graded — start at 01 if you're new:

| # | Demo | Language | Shows off | Status |
|---|------|----------|-----------|--------|
| 01 | Guess the number | BASIC | The write→run→verify loop | ✅ passed |
| 02 | Bouncing ball | BASIC | Screen-memory animation | ✅ passed |
| 03 | Sieve benchmark | BASIC + asm | Timing, iteration, a ~93× asm speedup | ✅ passed |
| 04 | Snake | 6502 assembly | The full assembler + debugger workflow | ✅ passed |
| 05 | Debug hunt | BASIC + debugger | Breakpoints, stepping, memory inspection | ✅ passed |
| 06 | Invaders | 6502 assembly | Arcade-fidelity spec, CB2 sound, review loop, packaging | ✅ passed |
| 07 | Ms. Muncher | 6502 assembly | Full spec→plan→implement workflow: half-cell actor engine, 4 mazes, cutscenes, demo mode, high scores | ✅ passed |

Demo 07 has no prompt file: it was built interactively through the
brainstorm → spec → plan → implement workflow rather than from a single
pasted prompt. The playable result and its deterministic test suite live
in [`muncher/`](muncher/).

Dogfooding status: each prompt is validated by handing it to a real AI agent
(given only this toolset) and confirming the result independently. Demos
01-05 passed on the first agent attempt; demo 06 needed one follow-up
prompt — the first build's audit passed, but on a real keyboard the
controls were dead under stock x64sc's default model (the BASIC 2 vs 4
`$97` split; see `invaders/AUDIT.md`, iteration 3). Each file carries its
dogfood date and outcome.

Reference example programs with expected output (runnable as regression tests
via `c64 test programs`) live in `tests/programs/` — solutions that come out
of these demos particularly well can graduate there.
