# Guess the number

The first demo in the sequence: a Commodore BASIC guess-the-number game,
recolored border and background, played through to a win. A run exercises
the whole write→run→verify loop — write lowercase BASIC, check it with
`c64 basic check` as the skill's loop requires, boot a session, drive a
full round from the keyboard, and prove the result from the screen, the
VIC-II color registers, and a screenshot.

**What a passing run shows.** The agent boots a session, writes lowercase
BASIC source, checks it with `c64 basic check` — the prompt never asks for
that check, but the skill's write→run→observe→fix loop opens with it for
BASIC, so an agent following the skill runs it unprompted — then runs the
program, drives a round with `c64 key type` plus a row-anchored
`c64 wait --mem '@6,0=20'`, and finishes on a screen containing
`YOU GOT IT` as shown by `c64 screen`.
The row anchor is the point: screen output persists, so a bare `--text`
wait matches the *previous* `TOO HIGH` still on screen, while anchoring
the cell the verdict lands in polls the byte directly — `--since` is for
the other case, where a real gap separates the keypress from what it
produces. The recolor is proved from the registers rather than from the
picture: `c64 mem read '$D020' 2` reads back whichever pair of colors the
agent picked, say `f0 fb` for a black border on a dark-grey background,
because VIC-II color registers are 4-bit and read back with the high
nybble set. The evidence also includes a screenshot from
`c64 screen --png shot.png --border --scale 2`, where `--border` matters
because without it the capture is the 320x200 inner screen only and the
border color is cropped out.

Beyond this README, `PROMPT.md` is all this directory holds. The program the
agent writes, the screenshots it captures, and the session it runs are the
deliverable of the run, not files committed here.
