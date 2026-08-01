# Guess the number — a BASIC game, written and played on the machine

The first demo in the sequence: a Commodore BASIC game written, run, and
played through to a win on an emulated C64. It exercises the whole loop —
check the source, boot a session, drive the keyboard, and read the result
back from the screen and the VIC-II registers.

Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
write a Commodore BASIC guess-the-number game for a Commodore 64: the
program picks a random number from 1 to 100, prompts `YOUR GUESS?`,
answers `TOO HIGH`, `TOO LOW`, or `YOU GOT IT IN n GUESSES!`, and then
offers to play again. Give the game its own look by setting the border
and background colors (POKE 53280 and 53281). Keep the source in a
scratch directory of your choosing. Run it on an emulated C64, play one
full round by feeding keyboard input, and show me the final screen.

**What success looks like:** the agent boots a session, writes lowercase
BASIC source, checks it with `c64 basic check`, runs it, drives a round
with `c64 key type` plus a row-anchored `c64 wait --mem '@6,0=20'`, and
finishes on a screen containing `YOU GOT IT` as shown by `c64 screen`.
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
