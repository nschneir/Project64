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
| 03 | Sieve benchmark | BASIC + asm | Timing, iteration, the asm speedup | ✅ dogfooded |
| 04 | Snake | 6502 assembly | Assembler + debugger workflow, $CB input, SID sound | ✅ dogfooded |
| 05 | Debug hunt | BASIC + debugger | Breakpoints, stepping, memory inspection | ✅ dogfooded |
| 06 | [Invaders](invaders/PROMPT.md) | 6502 assembly | Arcade-fidelity spec, sprites + charset, 3-voice SID, review loop, packaging | ✅ dogfooded |
| 07 | [1812](1812/PROMPT.md) | 6502 assembly | Spec→plan→build, bitmap mode, rotating polygon rasterizer, 3-voice SID | 🔲 awaiting C64 dogfood |

**What ✅ means.** An agent given only this toolset built and verified the
demo on a real emulated C64. A prompt's status flips only when such a run
passes here — demos 01–06 were ported from the PET edition of this project
and have each now had their own C64 run; 07 was written for the C64 and is
still waiting for its first. Demo 06's run is written up in
[invaders/AUDIT.md](invaders/AUDIT.md).
Graphics and sprite expectations follow docs/superpowers/specs/graphics-and-sprites.md.

**Where the work goes.** A single-file prompt (`NN-name.md`) doesn't ship a
solution: the agent writes the program wherever it likes, proves it on a live
session, and nothing is committed — the run itself is the deliverable. Demos
that *are* directories keep their prompt in `PROMPT.md` and their sources, spec
and `evidence/` screenshots beside it (`invaders/`, `1812/`) — the prompt is
named `PROMPT.md`, not `README.md`, so that what you paste into the agent is
never confused with documentation *about* the demo. A directory demo also
commits the artefact its prompt tells it to build, so `invaders/invaders.d64`
runs in stock VICE without a checkout of this toolset.

<p align="center">
  <img src="invaders/evidence/title.png" alt="Invaders attract screen" width="260">
  <img src="invaders/evidence/formation.png" alt="Invaders wave 1 in play" width="260">
  <img src="invaders/evidence/ufo.png" alt="The mystery UFO crossing above eroded bunkers" width="260">
</p>
<p align="center"><sub>Demo 06's output: the attract screen, wave 1, and the mystery UFO
— captured from the running machine, stopped at its frame anchor.</sub></p>

Reference example programs with expected output (runnable as regression tests
via `c64 test programs`) live in `tests/programs/` — solutions that come out
of these demos particularly well can graduate there, which is the way a
single-file demo's program becomes durable. `tests/programs/bouncing-ball/`
came out of demo 02 this way.
