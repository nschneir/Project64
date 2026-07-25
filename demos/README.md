# Demos — prompts to try with your AI agent

Each file in this directory is a ready-to-paste prompt for an AI coding agent
set up with this toolset (see the README's "Using with AI coding agents").
Paste one into your agent and watch it write, run, and debug real
Commodore 64 software on the emulated machine.

They're graded — start at 01 if you're new:

| # | Demo | Language | Shows off | Status |
|---|------|----------|-----------|--------|
| 01 | Guess the number | BASIC | The write→run→verify loop | 🔲 awaiting C64 dogfood |
| 02 | Bouncing beach ball | BASIC | Multicolor sprites from BASIC | 🔲 awaiting C64 dogfood |
| 03 | Sieve benchmark | BASIC + asm | Timing, iteration, the asm speedup | 🔲 awaiting C64 dogfood |
| 04 | Snake | 6502 assembly | Assembler + debugger workflow, $CB input, SID sound | 🔲 awaiting C64 dogfood |
| 05 | Debug hunt | BASIC + debugger | Breakpoints, stepping, memory inspection | 🔲 awaiting C64 dogfood |
| 06 | [Invaders](invaders/) | 6502 assembly | Arcade-fidelity spec, sprites + charset, 3-voice SID, review loop, packaging | 🔲 awaiting C64 dogfood |
| 07 | [1812](1812/) | 6502 assembly | Spec→plan→build, bitmap mode, rotating polygon rasterizer, 3-voice SID | 🔲 awaiting C64 dogfood |

These prompts were ported from the PET edition of this project, where each
passed a real dogfooding run (an agent given only the toolset built and
verified the result). The C64 ports await their own dogfooding runs — a
prompt's status flips to ✅ only when a real agent run passes on the C64.
Graphics and sprite expectations follow docs/superpowers/specs/graphics-and-sprites.md.

Reference example programs with expected output (runnable as regression tests
via `c64 test programs`) live in `tests/programs/` — solutions that come out
of these demos particularly well can graduate there.
