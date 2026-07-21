# Invaders — Space Invaders for the Commodore PET 4032

A from-scratch Space Invaders recreation in pure 6502 assembly for a PET 4032
(40×25 screen, one CB2 sound voice), written and verified with the `c64`
toolset. This is **demo 06** — the flagship dogfood; see
[`AUDIT.md`](AUDIT.md) for the fidelity log (every feature confirmed on the
running machine, not inferred from source).

It has the full arcade: a 5×11 marching formation with the classic
one-alien-per-tick speed-up, three bomb types, four eroding shields, the
mystery UFO (with the 23rd-shot 300-point secret), waves, extra life at 1500,
a high score, a title screen with the score-advance table, and march-locked
CB2 sound.

## What's in this directory

| File | What it is |
|------|------------|
| `invaders.d64` | **The shareable disk image.** Its first (and only) file is the program — this is what you hand to anyone with VICE. |
| `invaders.prg` | The assembled program: a BASIC `SYS 1037` stub plus the machine code, load address `$0401`. Runs directly (`x64sc invaders.prg`). |
| `invaders.s` | The 6502 assembly source (ca65 syntax). |
| `invaders.lbl` | VICE label file (symbols) emitted by `c64 build` — used for symbolic debugging (`c64 break add tick`, `c64 until tick`, …). |
| `invaders-test.yaml` | A deterministic `c64 test` smoke test (title → start → held-key steering, frame-stepped). Run: `c64 test run demos/invaders/invaders-test.yaml`. |
| `AUDIT.md` | The fidelity audit — each spec bullet with its evidence from the live game. |
| `evidence/` | Screenshots captured from the running game (title, march frames, shields eroding, UFO, bombs, attract loop). |
| `plans/` | The implementation plan the demo was built from. |

## Running the `.d64`

The disk image is self-contained — the recipient only needs **VICE** installed
(`x64sc` on the PATH); nothing from this toolset is required to play.

**Quickest — boot and autostart:**

```sh
x64sc -model 4032 invaders.d64
```

VICE smart-attaches the image and runs the first program. (You can also do
this from the GUI with **File → Smart attach**.)

**The old-fashioned way** — attach the disk, then load and run by name at the
`READY.` prompt:

```basic
LOAD"INVADERS",8
RUN
```

**With the `c64` toolset** (from the repo root), on a running session:

```sh
c64 session start
c64 disk boot demos/invaders/invaders.d64   # attaches + LOAD + RUN
c64 screen                                  # watch it
```

Or skip the disk and run the source or program directly:

```sh
c64 run demos/invaders/invaders.s     # assembles, loads, runs
# or
x64sc -model 4032 invaders.prg         # the bare program, no disk
```

## Controls

| Key | Action |
|-----|--------|
| **A** | move the laser base left |
| **D** | move the laser base right |
| **Space** | fire (one shot on screen at a time) |
| any key | start a game from the title / attract screen |

The game reads the *held-key* state (`$97`), so movement is continuous while a
key is down — no key-repeat delay.
