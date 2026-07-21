# Snake in 6502 assembly *(dogfooded 2026-07-11 — first-try pass)*

Paste this prompt into your agent:

> Using the c64 CLI (see skills/pet-development/SKILL.md, the 6502-assembly
> skill, and docs/cli.md), build a complete arcade-style Snake game for a
> PET 4032 in 6502 assembly, working directly with screen memory at $8000
> (40×25). I want the whole arcade experience, not just a moving snake:
>
> - **Title screen** — the game's name drawn large with PET graphics
>   characters (the PET has no bitmap mode; its charm is the character
>   set — use it), plus "PRESS ANY KEY TO PLAY".
> - **Playfield** — a border drawn with graphics characters; the snake dies
>   if it hits the border or its own body.
> - **Play** — the snake moves continuously, W/A/S/D steer it (read the
>   keyboard with the GETIN ROM routine), and it grows each time it eats a
>   `*` that reappears at a random empty position.
> - **Score and levels** — a status line showing SCORE and LEVEL during
>   play; every few pickups the level goes up and the snake speeds up.
> - **Game over and high score** — a game-over screen showing the final
>   score and the best score so far, and a key to play again. The high
>   score must survive across games in the same session.
>
> When something misbehaves, use the debugger — breakpoints, `c64 step`,
> `c64 until` on your main loop, memory inspection — rather than guessing
> from the source. The machine runs far faster than real time, so drive the
> game deterministically: inject keystrokes with `c64 key` to start and
> steer, and step the main loop (`c64 until` on your per-move label) to
> advance an exact number of frames and read the screen between them. Prove
> it works by showing me the title screen, the snake moving and growing, a
> level-up, a game-over, and a second game where the high score from the
> first one is still on screen.

**What success looks like:** an assembled program with a BASIC SYS stub and
a real game state machine (title → play → game over → play again), GETIN
steering, a jiffy-paced main loop that quickens per level, and
screens/screenshots proving each phase — including a second run whose
game-over screen shows the surviving high score. This is the flagship demo —
expect the agent to lean on the debugger (and the frame-stepping recipe in
the cookbook) to get there.
