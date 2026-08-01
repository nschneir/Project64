# Bouncing beach ball — a multicolor hardware sprite, driven from BASIC

Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
write a Commodore BASIC program for a Commodore 64 that bounces a beach
ball around the screen as a **hardware sprite**: define a round 24×21
**two-color beach ball** — make it a *multicolor* sprite so the ball
shows two distinct colors (e.g. red and white segments) over the
background — enable sprite 0, and move it by updating the VIC-II
position registers. The ball **bounces off all four screen borders**:
reverse the horizontal velocity at the left and right edges and the
vertical velocity at the top and bottom, so it ricochets around the
whole screen. Draw a border around the playfield with graphics
characters (with color RAM set) marking the edges it bounces off.

**Prove it.** Let it run for a while, then show the evidence from the
running machine: sprite 0 enabled (`c64 mem read '$D015' 1`) and
multicolor on (`c64 mem read '$D01C' 1`), the position registers sampled
a few frames apart to show motion and a reversal at a border, and two
screenshots taken with `c64 screen --png` showing the ball bouncing off
different edges.

Work from this prompt and the skills alone: do not read any
`demos/*/README.md` — those READMEs are documentation for human readers
and can spoil the exercise.
