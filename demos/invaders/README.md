# Invaders — the dogfooded solution

A faithful Space Invaders in pure 6502 assembly — custom multicolor
charset, hardware sprites, the authentic one-invader-per-tick march
engine, three-voice SID, and an explicit audit-and-improve loop that
ran until every spec bullet passed.

`PROMPT.md` started life as a detailed prompt written by a human; Claude
helped draft it into its present shape, and a human edited the result. Every
other file here — the sources, the plan they were built from, the fidelity
audit, the regression test, the evidence frames, and the packaged disk — was
written by Claude Opus 5 in answer to that prompt.

![the attract screen](evidence/title.png)
![wave 1 under way](evidence/formation.png)

## Play it

`invaders.d64` sits beside the sources, so stock VICE is all you need:

```sh
x64sc -ntsc demos/invaders/invaders.d64
```

The `-ntsc` flag matters: given no video-standard flag, stock VICE boots
the PAL machine (verified live — the KERNAL's PAL flag at `$02A6` comes up
set on a bare `x64sc`), and this game was built and tested on the NTSC
machine that c64-tools boots by default. To rebuild the image (and the `.prg` beside it)
from source:

```sh
c64 package demos/invaders/invaders.s -o demos/invaders/invaders.d64 --title "INVADERS"
```

**Controls.** Hold `A` and `D` to move the laser base, `SPACE` to fire. Any
key starts a game from the attract screen. Input is read from `$CB`, the
matrix code of the key held right now, so movement is continuous while
firing.

## What is here

| File | |
|---|---|
| `PROMPT.md` | the human-directed, Claude-assisted prompt everything else answers |
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
| `evidence/` | the screenshots that proof protocol captures, one per claim |
| `invaders.d64` | the packaged disk image, autostartable in stock VICE |
| `invaders.prg` | the assembled program `c64 package` writes beside the image |

## What a passing run shows

An assembled program with a BASIC SYS stub and the full arcade loop —
attract screen → waves → game over → attract — plus the
one-invader-per-tick march engine (so the speed-up is emergent),
sprite-based base/shot/UFO over a custom-charset multicolor formation,
eroding shields, three bomb types, the UFO shot-count secret, and rich
three-voice SID sound (real ADSR, mixed waveforms, filtered effects) with
a heartbeat that audibly quickens; then a written fidelity audit with
every spec bullet marked pass, the deterministic evidence trail the
prompt calls for, and finally an `invaders.d64` the user can autostart in
stock VICE and play with A/D and space. The agent is expected to live in
the debugger and to spend several review cycles closing the gap between
"it runs" and "it's Space Invaders."

## The bit worth reading

`formation.s`. The arcade board could only afford to touch one alien per
frame, and every famous property of the game falls out of that: the
formation ripples instead of snapping, and it accelerates as aliens die
because a thinner formation finishes its sweep in fewer ticks. There is no
speed table anywhere — measured on the running machine, the formation takes
60 ticks to step one column with 55 aliens alive, and one tick with one
alive.
