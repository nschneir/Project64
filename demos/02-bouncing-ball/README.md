# Bouncing beach ball

A Commodore BASIC program that bounces a multicolor hardware sprite — a
two-color beach ball — off all four screen borders, inside a playfield
drawn with graphics characters. A run shows off sprites from BASIC and the
fact that sprites are invisible to `c64 screen` text: the proof has to come
from the VIC-II registers (`$D015`, `$D01C`, the position registers sampled
across frames) and from PNG screenshots.

**What a passing run shows.** A two-color beach ball defined in a data
block with its pointer at 2040 and multicolor enabled (`$D01C` bit 0 set,
the two shared colors set at `$D025`/`$D026`), `$D015` reading 1,
position-register samples that differ between reads and reverse at each
of the four borders, and screenshots showing the ball mid-flight bouncing
off different edges. Sprites don't appear in `c64 screen` text — the
agent must verify through registers and PNGs (see
[docs/graphics-and-sprites.md](../../docs/graphics-and-sprites.md)).

Beyond this README, `PROMPT.md` is all this directory holds. The program the
agent writes and the screenshots it captures are the deliverable of the run,
not files committed here.
