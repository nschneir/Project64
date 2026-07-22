# Guess the number

Paste this prompt into your agent:

> Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
> write a Commodore BASIC guess-the-number game for a Commodore 64: the
> program picks a random number from 1 to 100, prompts `YOUR GUESS?`,
> answers `TOO HIGH`, `TOO LOW`, or `YOU GOT IT IN n GUESSES!`, and then
> offers to play again. Give the game its own look by setting the border
> and background colors (POKE 53280 and 53281). Run it on an emulated C64,
> play one full round by feeding keyboard input, and show me the final
> screen.

**What success looks like:** the agent boots a session, writes lowercase
BASIC source, runs it, drives a round with `c64 basic type` or keyboard
input plus `c64 wait --text`, and shows a screen containing `YOU GOT IT`
with the recolored border/background visible in a `c64 screen --png`
screenshot.
