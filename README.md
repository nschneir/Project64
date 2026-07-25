<p align="center">
  <img src="img/logo.png" alt="Project64 logo" width="360">
</p>

# Project64

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green.svg)
![Built with AI](https://img.shields.io/badge/built%20with-AI-green.svg)

Project64 is a set of tools, skills, and an MCP to enable agentic Commodore
64 coding and debugging using the VICE emulator.

> The Python package is imported as `c64lib`, installed as `c64-tools`, and
> driven by the `c64` command-line tool.

## Install

Requires **Python 3.11+**, **VICE 3.5+** (provides `x64sc` and `petcat`), and
the **cc65** suite (`ca65`/`ld65`, for assembling 6502 programs). Then install
this package.

macOS (Homebrew):

    brew install vice cc65
    pip install -e .

Debian / Ubuntu:

    sudo apt install vice cc65
    pip install -e .

## Quickstart

    pip install -e .
    c64 session start --model c64      # boot an emulated C64 (NTSC)
    c64 run tests/programs/hello-basic/program.bas   # tokenize + load + RUN
    c64 run tests/programs/hello-asm/program.s       # assemble + load + RUN (needs cc65)
    c64 screen                             # read the screen as text
    c64 basic type prog.bas --run          # type a program via the keyboard
    c64 mem read '$0400' 64                # hex dump of screen RAM
    c64 break add start                    # symbolic breakpoint (uses .lbl symbols)
    c64 wait --break                       # block until it fires
    c64 step 5 && c64 reg                  # single-step, inspect (PC annotated)
    c64 continue                           # resume
    c64 disk create work.d64 && c64 disk put work.d64 game.prg game
    c64 session start --disk work.d64      # boot with the disk attached
    c64 disk boot work.d64                 # or attach+run mid-session
    c64 rom info                           # identify the loaded ROM set
    c64 rom disasm CHROUT 16               # annotated live disassembly
    c64 session stop

    c64 test run mytest.yaml               # declarative YAML test (format in docs/cli.md)
    c64 test programs                      # run every example program as a test

Every command takes `--json` for machine-readable output — the intended
interface for AI agents.

## Supported machines

Every session boots a Commodore 64 (`--model`, default `c64`). The two
profiles differ only in video standard — pick PAL when timing against
50 Hz software:

| Model | RAM | Free at boot | BASIC | Screen | Notes |
|-------|-----|--------------|-------|--------|-------|
| `c64` | 64 KB | 38911 bytes | 2.0 | 40×25 | **The default.** NTSC (60 Hz); what the demos use. |
| `c64pal` | 64 KB | 38911 bytes | 2.0 | 40×25 | PAL (50 Hz) — different frame rate and slightly different CPU clock. |

The screen is memory-mapped at `$0400` (the power-on default; the VIC-II
can relocate it); "free at boot" is what BASIC reports, and is the budget
a BASIC program (or a `SYS`-stub assembly program) actually has to fit in.

## Using with AI coding agents

This toolset is built to be driven by an AI agent — every `c64` command
takes `--json`, the `c64-tools-mcp` MCP server exposes the same operations,
and debugging state (a breakpoint halt) persists across the agent's tool
calls. See **[docs/agent-setup.md](docs/agent-setup.md)** for the two
integration routes and step-by-step setup for Claude Code, OpenAI Codex,
Cursor, Gemini CLI, and Google Antigravity.

## Demos — try it with your AI agent

[`demos/`](demos/) is a set of ready-to-paste prompts, graded from a first
BASIC program through a sprite bouncing ball and a machine-level debug hunt
up to the flagships: a full arcade Snake in 6502 assembly (title screen,
levels, SID sound, high score), an arcade-faithful Invaders with sprites,
three-voice sound, waves, and a packaged disk image, and a bitmap-graphics
demo that paints rotating shapes to a SID arrangement of the 1812 Overture.
To use one:

1. Set up your agent (one section up — or use any shell agent with no setup).
2. Open a demo file and copy its prompt.
3. Paste it into your agent and watch it write, run, and debug real C64
   software on the emulated machine.

The reference example programs (with expected screen output, runnable as
regression tests via `c64 test programs`) live in
[`tests/programs/`](tests/programs/).

## Sharing what you built

`c64 package` turns a source file into something any VICE user can run — no
c64-tools needed on their end:

    c64 package snake.s -o snake.d64 --title SNAKE

That assembles the program and writes it as the first file on a fresh disk
image, so it autostarts. The recipient just needs VICE installed:

    x64sc -ntsc snake.d64    # boots a C64, runs SNAKE

(`c64 package` prints this exact command; both profiles pin their video
standard — `-ntsc` / `-pal` — since stock x64sc boots its own default
machine and timing differs.) The bare `.prg` (also produced) works too, as
does VICE's
File → Smart attach. Disk images travel better: they carry a real CBM
directory, so `LOAD"SNAKE",8` then `RUN` works the old-fashioned way.
Neither artifact contains ROMs or anything from this toolset.

## Status

Stable — current release **v0.3.1**. Full history: [CHANGELOG.md](CHANGELOG.md).

## AI Disclosure

Project64 is developed primarily by AI — Anthropic's Claude, working
through Claude Code — under human direction: a human sets the goals,
reviews the designs and plans, and approves the work; the AI writes the
specs, plans, code, tests, and documentation. Every change is verified by
the automated test suite, including integration tests that run against a
real VICE emulator, before it lands. The project also exists *for* AI use —
these tools are built so AI agents can write and debug Commodore 64
software — making it a working example of AI-built developer tooling.

## License

MIT license. Note that VICE is a separate GPLv2+ program invoked as a
subprocess; it is not bundled and must be installed separately.

ROM tooling reads ROM bytes from your running emulator and ships only
original label annotations — no Commodore-copyrighted code lives in this repo.
