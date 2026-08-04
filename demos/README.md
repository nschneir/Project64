# Demos — prompts to try with your AI agent

Each file in this directory is a ready-to-run prompt for an AI coding agent
set up with this toolset (see [docs/agent-setup.md](../docs/agent-setup.md)).
Give one to your agent and watch it write, run, and debug real
Commodore 64 software on the emulated machine.

## Test demos

Graded exercises that put the toolset through its paces — start at 01 if
you're new:

| # | Demo | Language | Description |
|---|------|----------|-------------|
| 01 | [Guess the number](01-guess-the-number/PROMPT.md) | BASIC | A number game played through to a win — the write→run→verify loop end to end |
| 02 | [Bouncing beach ball](02-bouncing-ball/PROMPT.md) | BASIC | A multicolor hardware sprite bounced off all four borders, proved from the VIC-II registers rather than screen text |
| 03 | [Sieve benchmark](03-sieve-benchmark/PROMPT.md) | BASIC + asm | The sieve of Eratosthenes written twice and timed off the jiffy clock — the asm speedup, then a second optimizing pass |
| 04 | [Debug hunt](04-debug-hunt/PROMPT.md) | BASIC + debugger | A dashboard broken in three layers, found with breakpoints, stepping, and memory inspection |
| 05 | [Bach's Invention No. 13](05-bach-invention/PROMPT.md) | BASIC | A two-part invention on voices 1 and 2 with noise percussion on voice 3 — proved by register-level audio capture, a reference score, and a piano roll the agent has to read |

## Game demos

Full games, each with its own fidelity bar and evidence protocol:

| Demo | Language | Description |
|------|----------|-------------|
| [Snake](snake/PROMPT.md) | 6502 assembly | Arcade Snake on a custom hires charset — the assembler + debugger workflow, `$CB` held-key steering, SID sound, nine speeding-up levels |
| [Invaders](invaders/PROMPT.md) | 6502 assembly | The 1978 arcade original to an arcade-fidelity spec — sprites and custom charset, the one-invader-per-tick march, 3-voice SID, review loop, packaging |
| [Ms. Muncher](ms-muncher/PROMPT.md) | 6502 assembly | A maze chase with four rotating mazes — per-ghost targeting AI, six sprites, animated cut scenes, 3-voice SID |
| [La Galaxia](la-galaxia/PROMPT.md) | 6502 assembly | A fixed shooter with sprite multiplexing — formation flights and dive patterns, the capture/dual-fighter mechanic, Spanish throughout |

## Miscellaneous cool stuff

Audiovisual builds that aren't games:

| Demo | Language | Description |
|------|----------|-------------|
| [1812](1812/PROMPT.md) | 6502 assembly | Randomised shapes painted to Tchaikovsky's *1812 Overture* — spec→plan→build, bitmap mode, a rotating polygon rasterizer, 3-voice SID |

**Where the work goes.** Every demo is a directory holding its prompt in
`PROMPT.md` and a `README.md` describing it — the prompt is named `PROMPT.md`,
not `README.md`, so that what you give the agent is never confused with
documentation *about* the demo. The test demos keep nothing else: the agent
writes the program wherever it likes, proves it on a live session, and
nothing is committed — the run itself is the deliverable. Every demo outside
the test tier keeps everything: sources, plan, audit, `evidence/`
screenshots, and the artefact the prompt tells the agent to build, so
`invaders/invaders.d64`, `snake/snake.d64` and `1812/1812.d64` run in stock
VICE without a checkout of this toolset. Ms. Muncher and La Galaxia are
prompt-only so far; their directories fill in the same way once built.
The three finished builds are written up in
[invaders/AUDIT.md](invaders/AUDIT.md), [snake/AUDIT.md](snake/AUDIT.md), and
[1812/AUDIT.md](1812/AUDIT.md).

<p align="center">
  <img src="invaders/evidence/title.png" alt="Invaders attract screen" width="260">
  <img src="invaders/evidence/formation.png" alt="Invaders wave 1 in play" width="260">
  <img src="invaders/evidence/ufo.png" alt="The mystery UFO crossing above eroded bunkers" width="260">
</p>
<p align="center"><sub>The Invaders run's output: the attract screen, wave 1, and the mystery UFO
— captured from the running machine, stopped at its frame anchor.</sub></p>

<p align="center">
  <img src="snake/evidence/title.png" alt="Snake title screen" width="260">
  <img src="snake/evidence/levelup.png" alt="Snake at level 2, recoloured" width="260">
  <img src="snake/evidence/gameover.png" alt="Snake game over with a new high score" width="260">
</p>
<p align="center"><sub>The Snake run's output: the title screen, level 2 after the snake has been
recoloured, and the game-over panel — same protocol, same frame anchor.</sub></p>
