# Snake — a complete arcade game in 6502 assembly

Using the c64 CLI (see skills/c64-development/SKILL.md, the 6502-assembly
skill, and docs/cli.md), build a complete arcade-style Snake game for a
Commodore 64 in 6502 assembly, working directly with screen memory at
$0400 and color RAM at $D800 (40×25). Everything for this demo lives in
`demos/snake/`.

**First, write the plan.** Before any code, turn this spec into
`demos/snake/PLAN.md` — ordered, independently verifiable steps, each
naming the observation that proves it — and build from that plan, updating
it as the running machine corrects you. Everything you generate is
committed: the plan, the sources in `demos/snake/`, the audit, the
evidence frames, the regression spec, and the packaged disk.

**Make deliberate use of color** — the C64 has a 16-color palette and this
game should look vivid, not monochrome: write color RAM ($D800) alongside
every character you draw, and give the title, border, snake, food, and HUD
their own distinct colors. Use a custom character set to give the snake,
food, and other elements a more realistic look
(docs/graphics-and-sprites.md has the authoring and
testing rules). I want the whole arcade experience, not just a moving
snake:

- **Title screen** — the game's name drawn large with PETSCII graphics
  characters in bright colors, plus "PRESS ANY KEY TO PLAY".
- **Playfield** — a border drawn with graphics characters; the snake dies
  if it hits the border or its own body. Use color RAM: border, snake,
  and food in distinct colors.
- **Play** — the snake moves continuously, W/A/S/D steer it (read the
  held key's matrix code from $CB so steering doesn't depend on key
  repeat — see the cookbook's held-key recipe), and it grows each time
  it eats a piece of food, which reappears at a random empty position.
- **Sound** — a short SID blip when the snake eats, a longer crash sound
  when it dies (the hardware reference has the register recipe). Shadow
  every SID write in RAM — the SID is write-only, so your shadow bytes
  are the testable evidence for sound.
- **Score and levels** — a status line showing SCORE and LEVEL during
  play; every few pickups the level goes up, the snake speeds up, and
  its color changes so each level looks distinct.
- **Game over and high score** — a game-over screen showing the final
  score and the best score so far, and a key to play again. The high
  score must survive across games in the same session.

**Use the debugger.** When something misbehaves, reach for breakpoints,
`c64 step`, `c64 until` on your main loop, and memory inspection rather
than guessing from the source.

**The improvement loop.** A first playable build is the *start* of this
demo, not the end. From there, work in explicit numbered iterations,
each one a full cycle:

1. **Evaluate** — play the game deterministically (see the proof
   protocol below) and walk every bullet of the spec above, marking it
   PASS or FAIL with evidence from the running game, never from reading
   the source.
2. **Review** — do a detailed code review of the current build: inner
   loops cycle-counted, the per-move update scrutinized, dead code and
   slack removed, and gameplay feel judged against an arcade Snake
   (steering response, the speed curve across levels, the fairness of a
   death).
3. **Improve** — fix every FAIL and act on every review finding.
4. **Re-verify** — prove each fix in the running game before counting
   it done.

Log each iteration in `demos/snake/AUDIT.md` so progress is visible, and
keep looping until an iteration ends with every spec bullet PASS and a
review that finds nothing worth fixing. Expect this to take several
cycles — "it runs" and "it's an arcade game" are different claims.

**Prove it deterministically.** The machine runs far faster than real
time, so drive the game frame by frame: `c64 key hold` steers with real
matrix codes, `c64 key type` sends buffered presses, and stepping the main
loop (`c64 until` on your per-move label) advances an exact number of
frames so you can read the screen between them. Collect evidence PNGs into
`demos/snake/evidence/` per
docs/graphics-and-sprites.md, each captured from the
stopped machine: the title screen; the playfield mid-game with the snake
grown and food on the board; a level change (the speed-up and the new
snake color); a game over showing the final score; a second game whose
game-over screen still shows the first game's score as the high score; and
your SID shadow bytes captured as a blip plays. Then write
`demos/snake/test.yaml` — a deterministic regression spec runnable with
`c64 test run` — asserting the title text, the border and snake in screen
RAM, the score and level in the status line, the surviving high score, and
non-zero SID shadows.

**Ship it.** When everything passes, package the game so anyone with stock
VICE can play it: `c64 package` your source into `demos/snake/snake.d64`
with `--title "SNAKE"` (the `.prg` lands beside it), and tell the user the
exact run command `c64 package` prints — including the video-standard
flag, so they get the timing you tested. On a real keyboard, the $CB scan
then gives them exactly the held-key steering you tested.
