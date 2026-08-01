# Snake

A complete arcade Snake for the Commodore 64 in 6502 assembly, written
straight to screen memory and color RAM. The prompt calls for a title
screen in large PETSCII, a bordered playfield on a custom character set
with deliberate color, `$CB` held-key steering, SID effects with every
write shadowed in RAM, a SCORE/LEVEL status line where the snake speeds up
and changes color per level, a game over, and a high score that survives
into the next game — then an audit-and-improve loop, evidence frames
captured from the stopped machine, a `test.yaml` regression spec, and a
packaged `snake.d64`.

**What a passing run shows.** An assembled program with a BASIC SYS stub
and a real game state machine (title → play → game over → play again),
`$CB` held-key steering, a custom charset and deliberate color across the
title, border, snake, food and HUD, SID sound effects with shadowed
registers, and a jiffy-paced main loop that quickens per level; then an
audit in `AUDIT.md` with every spec bullet marked pass, the deterministic
evidence trail the prompt calls for — including a second run whose
game-over screen shows the surviving high score — a `test.yaml` that
passes under `c64 test run`, and a `snake.d64` the user can autostart in
stock VICE and play with W/A/S/D. Expect the agent to lean on the
debugger (and the frame-stepping recipe in the cookbook) to get there.

`PROMPT.md` was drafted with Claude's help from human direction, and a
human edited the result. Beyond this README, it is all this directory holds
today. Snake passed an earlier C64 dogfood run as a lightweight test demo,
where nothing was committed and the run itself was the deliverable; the
prompt has since been promoted to a game demo that keeps its whole solution
— plan, sources, audit, evidence frames, regression spec, and packaged disk.
None of that exists yet, so the demo awaits a run under the new prompt.
