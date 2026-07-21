# Ms. Muncher

An arcade-faithful maze-chase homage for the Commodore PET 4032 — original
name, cast, PETSCII art, and original music. Pure 6502 assembly, 40×25
character mode, one CB2 voice, 9.8 KB of program in a 32K machine.

She munches dots through four rotating mazes while Bruiser, Pixie, Ivy,
and Sable hunt her with the arcade's real targeting rules — including the
randomized scatter openings that make patterns impossible, the up-quirk
ambush, cruise-elroy speed-ups, wandering bonus fruit that enters by a
tunnel and laps the ghost house, per-board blue times, three story
intermissions, an attract mode with a self-playing demo, and a top-5
high-score table with initials entry.

## Run it

Any VICE install:

```sh
x64sc -model 4032 demos/muncher/muncher.d64
```

Or with c64-tools:

```sh
c64 session start --model c64        # no --warp: play at real speed
c64 run demos/muncher/muncher.s
```

## Controls

- **W / A / S / D** — steer (turns buffer until the corner; reversal is
  instant)
- **SPACE** — start from the title (also skips intermissions)
- **1 / 2 / 3** *(hidden, title screen only)* — play Acts 1–3 directly
- High-score initials: just **type them** (letters/digits; the third
  character saves, or **RETURN**/**SPACE** saves early)

## Engineering notes

Actors live on a 56×50 half-cell grid (double the character grid) driven
by 8.8 fixed-point speed accumulators, so the arcade's speed table —
80/90/100% player classes, 75–95% ghosts, 40–50% tunnel crawl, frightened
50–60%, elroy +5/+10% — is reproduced continuously rather than in lumpy
character steps. Mazes are packed 2-bit maps validated by a host-side
Python checker (geometry, symmetry, dead ends, reachability, dot targets,
and cell-by-cell fruit-path validation) that also emits the per-maze
scaled thresholds. The whole game is exercised by a deterministic
poke/until test suite (`c64 test run demos/muncher/muncher-test.yaml`)
plus pytest for the toolchain.
