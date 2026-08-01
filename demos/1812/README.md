# 1812

A bitmap-graphics demo for the Commodore 64: randomized shapes — rotated
triangles, stars and ellipses, filled through 8×8 dither masks — accumulating
on a black canvas that is never cleared, each one spawned in time with a
three-voice SID arrangement of Tchaikovsky's *1812 Overture* (1880, public
domain). The prompt asks for real geometry rather than sprite tricks (a
256-step angle, sin/cos tables, 8.8 fixed-point vertex transforms, an even-odd
scanline fill), a sixteen-color palette spent deliberately per musical
section, and work in three phases in that order — spec, then plan, then build —
with every claim proved from registers and state bytes on the running machine.

**What a passing run shows.** `demos/1812/` containing `SPEC.md`,
`PLAN.md`, the assembled 6502 source with its BASIC SYS stub, `test.yaml`,
`AUDIT.md`, an `evidence/` directory, and a bootable `1812.d64`. On
screen: a black field that fills up over a few minutes with rotated,
dithered, overlapping shapes whose color and character change as the
arrangement moves from hymn to battle to cannon to finale — never cleared,
never repainted, the whole picture a record of the piece. This demo is the
toolset's graphics stress test: bitmap mode, a real rotating polygon
rasterizer, a color budget used on purpose, and three voices of SID —
every claim about it settled by registers and state bytes, with the
screenshots kept as the record of what those bytes drew.

`PROMPT.md` was drafted with Claude's help from detailed human direction, and a
human edited the result. Beyond this README, it is everything this directory
holds today; no code has been generated from it yet. Running the prompt fills
in the rest — the spec (`SPEC.md`), the plan (`PLAN.md`), the assembled
sources, the regression test, the audit log (`AUDIT.md`), the evidence
frames, and the packaged disk.
