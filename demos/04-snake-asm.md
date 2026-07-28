# Snake in 6502 assembly

Paste this prompt into your agent:

> Using the c64 CLI (see skills/c64-development/SKILL.md, the 6502-assembly
> skill, and docs/cli.md), build a complete arcade-style Snake game for a
> Commodore 64 in 6502 assembly, working directly with screen memory at
> $0400 and color RAM at $D800 (40×25). **Make deliberate use of color** —
> the C64 has a 16-color palette and this game should look vivid, not
> monochrome: write color RAM ($D800) alongside every character you draw,
> and give the title, border, snake, food, and HUD their own distinct
> colors. Use a custom character set to give the snake, food, and other elements a more realistic look. I want the whole arcade experience, not just a moving snake:
>
> - **Title screen** — the game's name drawn large with PETSCII graphics
>   characters in bright colors, plus "PRESS ANY KEY TO PLAY".
> - **Playfield** — a border drawn with graphics characters; the snake dies
>   if it hits the border or its own body. Use color RAM: border, snake,
>   and food in distinct colors.
> - **Play** — the snake moves continuously, W/A/S/D steer it (read the
>   held key's matrix code from $CB so steering doesn't depend on key
>   repeat — see the cookbook's held-key recipe), and it grows each time
>   it eats a piece of food, which reappears at a random empty position.
> - **Sound** — a short SID blip when the snake eats, a longer crash sound
>   when it dies (the hardware reference has the register recipe).
> - **Score and levels** — a status line showing SCORE and LEVEL during
>   play; every few pickups the level goes up, the snake speeds up, and
>   its color changes so each level looks distinct.
> - **Game over and high score** — a game-over screen showing the final
>   score and the best score so far, and a key to play again. The high
>   score must survive across games in the same session.
>
> When something misbehaves, use the debugger — breakpoints, `c64 step`,
> `c64 until` on your main loop, memory inspection — rather than guessing
> from the source. The machine runs far faster than real time, so drive the
> game deterministically: `c64 key hold` steers with real matrix codes, and
> stepping the main loop (`c64 until` on your per-move label) advances an
> exact number of frames so you can read the screen between them. Prove
> it works by showing me the title screen, the snake moving and growing, a
> level-up, a game-over, and a second game where the high score from the
> first one is still on screen.

**What success looks like:** an assembled program with a BASIC SYS stub and
a real game state machine (title → play → game over → play again), $CB
held-key steering, SID sound effects, a jiffy-paced main loop that quickens
per level, and screens/screenshots proving each phase — including a second
run whose game-over screen shows the surviving high score. Expect the agent
to lean on the debugger (and the frame-stepping recipe in the cookbook) to
get there.
