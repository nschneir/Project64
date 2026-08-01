# Bouncing beach ball

A Commodore BASIC program that bounces a multicolor hardware sprite — a
two-color beach ball — off all four screen borders, inside a playfield
drawn with graphics characters. A run shows off sprites from BASIC and the
fact that sprites are invisible to `c64 screen` text: the proof has to come
from the VIC-II registers (`$D015`, `$D01C`, the position registers sampled
across frames) and from PNG screenshots.

`PROMPT.md` is all this directory holds. The program the agent writes and
the screenshots it captures are the deliverable of the run, not files
committed here. For one demo whose answer *is* kept in full — sources,
plan, audit, evidence frames and a packaged disk — see
[`demos/invaders/`](../invaders/).
