# Guess the number

Paste this prompt into your agent:

> Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
> write a Commodore BASIC guess-the-number game for a Commodore 64: the
> program picks a random number from 1 to 100, prompts `YOUR GUESS?`,
> answers `TOO HIGH`, `TOO LOW`, or `YOU GOT IT IN n GUESSES!`, and then
> offers to play again. Give the game its own look by setting the border
> and background colors (POKE 53280 and 53281). Keep the source in a
> scratch directory of your choosing. Run it on an emulated C64, play one
> full round by feeding keyboard input, and show me the final screen.

**What success looks like:** the agent boots a session, writes lowercase
BASIC source, checks it with `c64 basic check`, runs it, drives a round with
`c64 key type` plus `c64 wait --text ... --since` (a bare `--text` wait
matches the *previous* `TOO HIGH` still on screen), and finishes with:

- a screen containing `YOU GOT IT`, shown via `c64 screen`;
- the recolor proved from the registers — `c64 mem read '$D020' 2` shows
  `f0 fb` for black-on-dark-grey, because VIC-II color registers are 4-bit
  and read back with the high nybble set;
- a `c64 screen --png shot.png --border --scale 2` screenshot. `--border`
  matters: without it the capture is the 320x200 inner screen only and the
  border color is cropped out.
