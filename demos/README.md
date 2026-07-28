# Demos — prompts to try with your AI agent

Each file in this directory is a ready-to-paste prompt for an AI coding agent
set up with this toolset (see [docs/agent-setup.md](../docs/agent-setup.md)).
Paste one into your agent and watch it write, run, and debug real
Commodore 64 software on the emulated machine.

They're graded — start at 01 if you're new:

| # | Demo | Language | Shows off | Status |
|---|------|----------|-----------|--------|
| 01 | Guess the number | BASIC | The write→run→verify loop | ✅ dogfooded |
| 02 | Bouncing beach ball | BASIC | Multicolor sprites from BASIC | ✅ dogfooded |
| 03 | Sieve benchmark | BASIC + asm | Timing, iteration, the asm speedup | 🔲 awaiting C64 dogfood |
| 04 | Snake | 6502 assembly | Assembler + debugger workflow, $CB input, SID sound | 🔲 awaiting C64 dogfood |
| 05 | Debug hunt | BASIC + debugger | Breakpoints, stepping, memory inspection | 🔲 awaiting C64 dogfood |
| 06 | [Invaders](invaders/) | 6502 assembly | Arcade-fidelity spec, sprites + charset, 3-voice SID, review loop, packaging | 🔲 awaiting C64 dogfood |
| 07 | [1812](1812/) | 6502 assembly | Spec→plan→build, bitmap mode, rotating polygon rasterizer, 3-voice SID | 🔲 awaiting C64 dogfood |

Demos 01–06 were ported from the PET edition of this project, where each
passed a real dogfooding run (an agent given only the toolset built and
verified the result); 07 was written for the C64. The ports still marked 🔲
await their own dogfooding runs — a prompt's status flips to ✅ only when a
real agent run passes on the C64.
Graphics and sprite expectations follow docs/superpowers/specs/graphics-and-sprites.md.

**Where the work goes.** A single-file prompt (`NN-name.md`) doesn't ship a
solution: the agent writes the program wherever it likes, proves it on a live
session, and nothing is committed — the run itself is the deliverable. Demos
that *are* directories (`invaders/`, `1812/`) keep their sources, spec and
`evidence/` screenshots in place.

Reference example programs with expected output (runnable as regression tests
via `c64 test programs`) live in `tests/programs/` — solutions that come out
of these demos particularly well can graduate there, which is the way a
single-file demo's program becomes durable. `tests/programs/bouncing-ball/`
came out of demo 02 this way.
