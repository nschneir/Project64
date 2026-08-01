# Demos — prompts to try with your AI agent

Each file in this directory is a ready-to-run prompt for an AI coding agent
set up with this toolset (see [docs/agent-setup.md](../docs/agent-setup.md)).
Give one to your agent and watch it write, run, and debug real
Commodore 64 software on the emulated machine.

## Test demos

Graded exercises that put the toolset through its paces — start at 01 if
you're new:

| # | Demo | Language | Shows off | Status |
|---|------|----------|-----------|--------|
| 01 | [Guess the number](01-guess-the-number/PROMPT.md) | BASIC | The write→run→verify loop | ✅ dogfooded |
| 02 | [Bouncing beach ball](02-bouncing-ball/PROMPT.md) | BASIC | Multicolor sprites from BASIC | ✅ dogfooded |
| 03 | [Sieve benchmark](03-sieve-benchmark/PROMPT.md) | BASIC + asm | Timing, iteration, the asm speedup | ✅ dogfooded |
| 04 | [Debug hunt](04-debug-hunt/PROMPT.md) | BASIC + debugger | Breakpoints, stepping, memory inspection | ✅ dogfooded |

## Game demos

Full games, each with its own fidelity bar and evidence protocol:

| Demo | Language | Shows off | Status |
|------|----------|-----------|--------|
| [Snake](snake/PROMPT.md) | 6502 assembly | Assembler + debugger workflow, $CB input, SID sound | 🔲 awaiting C64 dogfood |
| [Invaders](invaders/PROMPT.md) | 6502 assembly | Arcade-fidelity spec, sprites + charset, 3-voice SID, review loop, packaging | ✅ dogfooded |
| [Ms. Muncher](ms-muncher/PROMPT.md) | 6502 assembly | Maze-chase ghost AI, six sprites, animated cut scenes, 3-voice SID | 🔲 awaiting C64 dogfood |
| [La Galaxia](la-galaxia/PROMPT.md) | 6502 assembly | Sprite multiplexing, formation flights and dive patterns, the capture/dual-fighter mechanic | 🔲 awaiting C64 dogfood |

## Miscellaneous cool stuff

Audiovisual builds that aren't games:

| Demo | Language | Shows off | Status |
|------|----------|-----------|--------|
| [1812](1812/PROMPT.md) | 6502 assembly | Spec→plan→build, bitmap mode, rotating polygon rasterizer, 3-voice SID | 🔲 awaiting C64 dogfood |

**What ✅ means.** An agent given only this toolset built and verified the
demo on a real emulated C64. A prompt's status flips only when such a run
passes here — the test demos and Invaders were ported from the PET edition
of this project and have each now had their own C64 run. Snake passed a run
too, but as a test demo under a lighter prompt; its prompt has since been
promoted to keep everything a game demo keeps, so it is awaiting a run under
that promoted prompt. 1812, Ms. Muncher, and La Galaxia are still waiting
for their first run of any kind. The Invaders run is written up in
[invaders/AUDIT.md](invaders/AUDIT.md).
Graphics and sprite expectations follow docs/superpowers/specs/graphics-and-sprites.md.

**Where the work goes.** Every demo is a directory holding its prompt in
`PROMPT.md` and a `README.md` describing it — the prompt is named `PROMPT.md`,
not `README.md`, so that what you give the agent is never confused with
documentation *about* the demo. The test demos keep nothing else: the agent
writes the program wherever it likes, proves it on a live session, and
nothing is committed — the run itself is the deliverable. Every demo outside
the test tier keeps everything: sources, plan, audit, `evidence/`
screenshots, and the artefact the prompt tells the agent to build, so
`invaders/invaders.d64` runs in stock VICE without a checkout of this
toolset (the other prompts will fill in the same way when their runs land).

<p align="center">
  <img src="invaders/evidence/title.png" alt="Invaders attract screen" width="260">
  <img src="invaders/evidence/formation.png" alt="Invaders wave 1 in play" width="260">
  <img src="invaders/evidence/ufo.png" alt="The mystery UFO crossing above eroded bunkers" width="260">
</p>
<p align="center"><sub>The Invaders run's output: the attract screen, wave 1, and the mystery UFO
— captured from the running machine, stopped at its frame anchor.</sub></p>

Reference example programs with expected output (runnable as regression tests
via `c64 test programs`) live in `tests/programs/` — solutions that come out
of these demos particularly well can graduate there, which is the way a
single-file demo's program becomes durable. `tests/programs/bouncing-ball/`
came out of demo 02 this way.
