# La Galaxia — the prompt

A fixed-shooter for the Commodore 64, chasing the 1981 arcade original
named in the prompt as closely as the hardware allows. The spec asks for
the full 40-enemy formation on eight hardware sprites — a hybrid engine
that parks settled aliens in Character RAM and hands each one a
multiplexed sprite the moment it dives — plus the five scripted entrance
waves off sine/cosine lookup tables, the tractor beam that steals your
fighter and the mid-flight rescue that gives you two, transforming
enemies, the no-fire challenging stages with their 10,000 point bonus,
and a three-voice SID engine that ducks its music under the effects.
True to its name, every string the player sees is in Spanish — `PUNTOS`,
`NAVES`, `ETAPA`, `¡PERFECTO!`, `JUEGO TERMINADO`.

`PROMPT.md` came out of detailed human direction written up with Claude's
help, then edited by hand. Today it is the only thing in this directory —
nothing has been generated from it yet. A run will fill the rest in: the
plan the prompt demands as its first step, the 6502 sources, the fidelity
audit and its numbered iterations, the evidence PNGs, and the packaged
disk, arriving here the way [`demos/invaders/`](../invaders/) looks now
that its run is finished.

## The hidden keys

The prompt specifies a stage select, undocumented in-game and active on
the title screen only: `1` through `9` start a one-player game at stages
1–9, and `0` starts at stage 10. Nothing else comes with them — the score
starts at zero, the lives at the normal count, and you begin as a single
fighter. They exist so a reviewer can reach the first challenging stage
(stage 3) and the transforming enemies (stages 4–6) without playing there
first, and the fidelity audit is required to list them in its evidence.
