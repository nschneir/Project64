# Bouncing ball (sprite)

Paste this prompt into your agent:

> Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
> write a Commodore BASIC program for a Commodore 64 that bounces a ball
> around the screen as a **hardware sprite**: define a round 24×21 sprite
> shape, enable sprite 0, and move it by updating the VIC-II position
> registers, reversing direction at the screen edges. Draw a border around
> the playfield with graphics characters (with color RAM set) so the ball
> visibly bounces off something. Let it run for a while, then prove it
> works: show that sprite 0 is enabled (`c64 mem read '$D015' 1`), sample
> the position registers twice a few frames apart to show motion, and take
> two screenshots with `c64 screen --png` showing the ball at different
> places.

**What success looks like:** a sprite defined in a data block with its
pointer at 2040, `$D015` reading 1, position-register samples that differ
between reads, and screenshots showing the sprite mid-flight inside the
character border. Sprites don't appear in `c64 screen` text — the agent
must verify through registers and PNGs (see
docs/superpowers/specs/graphics-and-sprites.md).
