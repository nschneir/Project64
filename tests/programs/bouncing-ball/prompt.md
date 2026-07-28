Write a Commodore BASIC program for a Commodore 64 that bounces a beach ball
around the screen as a hardware sprite: define a round 24x21 two-color beach
ball as a *multicolor* sprite so the ball shows two distinct colors (red and
white segments) over the background, enable sprite 0, and move it by updating
the VIC-II position registers. The ball bounces off all four screen borders —
reverse the horizontal velocity at the left and right edges and the vertical
velocity at the top and bottom. Draw a border around the playfield with
graphics characters (with color RAM set) marking the edges it bounces off,
and a `BOUNCES` counter in screen RAM.

Sprites are invisible to `c64 screen` text, so publish the state a test can
assert on: a saturating bitmask of which edges have been hit, a bounce count,
the last edge's code, and the two direction signs — in zero-page bytes that
are free under BASIC.
