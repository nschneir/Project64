# Demos — prompts to try with your AI agent

Each demo here is a ready-to-run prompt for an AI coding agent set up with
this toolset (see [docs/agent-setup.md](../docs/agent-setup.md)). Give one to
your agent and watch it write, run, and debug real Commodore 64 software on
the emulated machine.

**The catalogue lives in the [main README](../README.md#demos--try-it-with-your-ai-agent)**
— full descriptions, screenshots, and ▶ Play links for the five that are
built. This page is the map of the directory itself.

## Test demos

Graded exercises; start at 01 if you're new.

| Demo | Description |
|------|-------------|
| [01 Guess the number](01-guess-the-number/PROMPT.md) | The write→run→verify loop end to end |
| [02 Bouncing beach ball](02-bouncing-ball/PROMPT.md) | A hardware sprite, proved from the VIC-II registers |
| [03 Sieve benchmark](03-sieve-benchmark/PROMPT.md) | BASIC vs. assembly, timed off the jiffy clock |
| [04 Debug hunt](04-debug-hunt/PROMPT.md) | A dashboard broken in three layers, found with the debugger |
| [05 Bach's Invention No. 13](05-bach-invention/PROMPT.md) | Three SID voices, proved by audio capture and a piano roll |

## Game demos

Full games, each with its own fidelity bar and evidence protocol.

| Demo | Description |
|------|-------------|
| [Snake](snake/PROMPT.md) | Arcade Snake on a custom hires charset |
| [Invaders](invaders/PROMPT.md) | The 1978 arcade original, to an arcade-fidelity spec |
| [Ms. Muncher](ms-muncher/PROMPT.md) | A maze chase with four boards and per-ghost AI |
| [La Galaxia](la-galaxia/PROMPT.md) | A fixed shooter in Spanish, with sprite multiplexing |

## Miscellaneous cool stuff

Audiovisual builds that aren't games.

| Demo | Description |
|------|-------------|
| [1812](1812/PROMPT.md) | Shapes painted to Tchaikovsky's *1812 Overture* |
| [Fugue No. 2 in C Minor](fugue/PROMPT.md) | Bach's BWV 847 while its score scrolls past |
| [Amiga Ball](amiga_ball/PROMPT.md) | The 1984 Boing Ball, on four multicolor sprites |

## Where the work goes

Every demo is a directory holding its prompt in `PROMPT.md` and a `README.md`
describing it. The prompt is named `PROMPT.md`, not `README.md`, so that what
you give the agent is never confused with documentation *about* the demo.

The test demos keep nothing else: the agent writes the program wherever it
likes, proves it on a live session, and nothing is committed — the run itself
is the deliverable.

Every demo outside that tier keeps everything: sources, plan, `AUDIT.md`,
`evidence/`, and the artefact the prompt asked for, so `invaders.d64`,
`snake.d64`, `ms-muncher.d64`, `la-galaxia.d64`, `1812.d64` and
`amiga_ball.d64` all run in stock VICE without a checkout of this toolset.
Fugue is prompt-only so far; its directory fills in the same way once built.
