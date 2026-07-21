# Guess the number *(dogfooded 2026-07-10 — first-try pass)*

Paste this prompt into your agent:

> Using the c64 CLI (see skills/pet-development/SKILL.md and docs/cli.md),
> write a Commodore BASIC guess-the-number game for a PET 4032: the program
> picks a random number from 1 to 100, prompts `YOUR GUESS?`, answers
> `TOO HIGH`, `TOO LOW`, or `YOU GOT IT IN n GUESSES!`, and then offers to
> play again. Run it on an emulated PET, play one full round by feeding
> keyboard input, and show me the final screen.

**What success looks like:** the agent boots a session, writes lowercase
BASIC source, runs it, drives a round with `c64 basic type` or keyboard
input plus `c64 wait --text`, and shows a screen containing `YOU GOT IT`.
