# Bouncing beach ball (multicolor sprite)

Paste this prompt into your agent:

> Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
> write a Commodore BASIC program for a Commodore 64 that bounces a beach
> ball around the screen as a **hardware sprite**: define a round 24×21
> **two-color beach ball** — make it a *multicolor* sprite so the ball
> shows two distinct colors (e.g. red and white segments) over the
> background — enable sprite 0, and move it by updating the VIC-II
> position registers. The ball **bounces off all four screen borders**:
> reverse the horizontal velocity at the left and right edges and the
> vertical velocity at the top and bottom, so it ricochets around the
> whole screen. Draw a border around the playfield with graphics
> characters (with color RAM set) marking the edges it bounces off. Let it
> run for a while, then prove it works: show that sprite 0 is enabled
> (`c64 mem read '$D015' 1`) and multicolor is on (`c64 mem read '$D01C' 1`),
> sample the position registers a few frames apart to show motion and a
> reversal at a border, and take two screenshots with `c64 screen --png`
> showing the ball bouncing off different edges.

**What success looks like:** a two-color beach ball defined in a data block
with its pointer at 2040 and multicolor enabled (`$D01C` bit 0 set, the two
shared colors set at `$D025`/`$D026`), `$D015` reading 1, position-register
samples that differ between reads and reverse at each of the four borders,
and screenshots showing the ball mid-flight bouncing off different edges.
Sprites don't appear in `c64 screen` text — the agent must verify through
registers and PNGs (see docs/superpowers/specs/graphics-and-sprites.md).
