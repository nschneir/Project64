# Invaders — the dogfooded solution

`PROMPT.md` is what you paste into an agent. This directory is what one run
produced: the sources, the plan it worked from, the fidelity audit, a
regression test, and the evidence frames.

![the attract screen](evidence/title.png)
![wave 1 under way](evidence/formation.png)

## Play it

Build the disk image and run it in stock VICE:

```sh
c64 package demos/invaders/invaders.s -o demos/invaders/invaders.d64 --title "INVADERS"
x64sc -ntsc demos/invaders/invaders.d64
```

`invaders.d64` and `invaders.prg` are not committed — this repository
gitignores build artefacts, and the two commands above rebuild them exactly.
The `-ntsc` flag matters: the game is paced on the jiffy clock and was
tested on the NTSC machine.

**Controls.** Hold `A` and `D` to move the laser base, `SPACE` to fire. Any
key starts a game from the attract screen. Input is read from `$CB`, the
matrix code of the key held right now, so movement is continuous while
firing.

## What is here

| File | |
|---|---|
| `PROMPT.md` | the prompt this was built from |
| `PLAN.md` | the implementation plan written before any code |
| `AUDIT.md` | the three-iteration fidelity audit — every spec bullet, with evidence |
| `invaders.s` | load address, BASIC stub, equates, the state machine, includes |
| `vars.s` | every mutable byte, with the labels the tests read |
| `screen.s` | row tables, the cell pointer, text without CHROUT, HUD, title |
| `chars.s` + `chars.inc` | the custom multicolor charset and its installer |
| `sprites.s` + `sprites.inc` | laser base, shot, UFO, explosion |
| `formation.s` | the one-invader-per-tick march engine |
| `player.s` `bombs.s` `shields.s` `ufo.s` | the rest of the game |
| `sound.s` | three SID voices, every write shadowed in RAM |
| `test.yaml` | 82-step regression test: `c64 test run demos/invaders/test.yaml` |
| `tools/charset.py` `tools/charset.txt` | ASCII art → the charset `.byte` rows |
| `tools/sprites.txt` | ASCII art → `sprites.inc` via `c64 sprite encode` |
| `tools/evidence.sh` | re-runs the deterministic proof protocol and rewrites `evidence/` |

## The bit worth reading

`formation.s`. The arcade board could only afford to touch one alien per
frame, and every famous property of the game falls out of that: the
formation ripples instead of snapping, and it accelerates as aliens die
because a thinner formation finishes its sweep in fewer ticks. There is no
speed table anywhere — measured on the running machine, the formation takes
60 ticks to step one column with 55 aliens alive, and one tick with one
alive.
