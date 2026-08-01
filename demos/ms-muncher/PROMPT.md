# Ms. Muncher — the 1982 maze chase, recreated

Using the c64 CLI (see skills/c64-development/SKILL.md, the 6502-assembly
skill, and docs/cli.md), build the closest recreation of the 1982 arcade
*Ms. Pac-Man* that a Commodore 64 can express — pure 6502 assembly with a
BASIC SYS stub. That name appears here so you know exactly which game's
behavior to study, and nowhere else in this directory. Everything for
this demo lives in `demos/ms-muncher/`.

**This is an homage, not a port — and that distinction is a hard
requirement.** The game is *Ms. Muncher*; the cast is Ms. Muncher and
four ghosts named **Bruiser**, **Pixie**, **Ivy**, and **Sable**. Every
glyph, sprite, and note is yours — original character art, original
sprite art, an original three-voice SID score composed for this game.
What you recreate from the 1982 arcade maze chase this honors is its
*behavior*: the rules, the timing, the structure, the feel. Never its
assets — no ripped graphics, no transcribed tunes, and no arcade names
anywhere on screen or in any file but this one.

**First, write the plan.** Before any code, turn this spec into
`demos/ms-muncher/PLAN.md` — ordered, independently verifiable steps,
each naming the observation that proves it — and build from that plan,
updating it as the running machine corrects you.

Push the C64's graphics to their fullest: draw the maze and HUD in a
**graphics mode built on a custom multicolor character set** (screen at
$0400, color RAM at $D800, per-cell colors — design your own wall,
corner, dot, and energizer glyphs rather than settling for stock
PETSCII), and use **hardware sprites** for everything that moves
smoothly: Ms. Muncher, all four ghosts, and the wandering bonus fruit.
Six sprites of the VIC-II's eight, so no multiplexing is needed. They
carry real animation: Ms. Muncher's mouth cycling with her direction,
and her bow; each ghost's own body and eye direction, its frightened
state, and the eyes-only state that floats home.
(docs/graphics-and-sprites.md has the authoring and
testing rules.)

**The arcade spec — recreate each of these faithfully:**

- **Mazes** — four distinct layouts on the arcade's rotation: maze 1
  for boards 1–2, maze 2 for boards 3–5, maze 3 for boards 6–9, maze 4
  for boards 10–13, the last two alternating every four boards after
  that — each with its own color scheme in color RAM. Tunnels wrap the
  sides, and actors crossing a tunnel slow down.
- **Dots and energizers** — dots and four energizers per maze, with the
  arcade's scoring: 10 for a dot, 50 for an energizer, and the
  200/400/800/1600 doubling chain for ghosts eaten within one
  frightened period.
- **The four ghosts** — the arcade's real per-personality targeting, not
  a shared chase routine: the direct pursuer, the ambusher aiming ahead
  of Ms. Muncher, the one whose target is a vector doubled through the
  pursuer, and the shy one who chases until she is close and then bolts
  for its corner. Reproduce the up-quirk (a target computed ahead of an
  upward-facing player is also displaced sideways), the scatter/chase
  phase table, and the **randomized scatter openings** that defeat
  pattern play — exactly what separates this game from its predecessor.
  Ghosts reverse on a phase change, never reverse voluntarily, and
  cannot turn upward in the restricted cells. Cruise-elroy speeds the
  direct pursuer up as the dots run out. Eaten ghosts travel home as
  eyes, revive in the house, and re-enter; ghosts leave the house on
  the arcade's staggered per-ghost schedule, never all at once.
- **Bonus fruit that travels** — the fruit enters through a tunnel,
  wanders the maze, laps the ghost house, and leaves by a tunnel. It is
  a moving sprite with a route, never a static fruit parked under the
  house. Seven fruit across the boards with the arcade's value ladder
  (100, 200, 500, 700, 1000, 2000, 5000); from board 8 on, each board's
  fruit is a random pick from the set.
- **Frightened time** — per-board "blue" durations that shrink as the
  boards advance, down to boards where energizers turn no one blue at
  all and only score.
- **Speeds** — reproduce the arcade's speed classes *continuously*, not
  in lumpy character steps: player 80/90/100%, ghosts 75–95%, tunnel
  crawl 40–50%, frightened 50–60%, cruise elroy +5% then +10%. A
  half-cell actor grid (double the character grid) driven by 8.8
  fixed-point speed accumulators is the mechanism that made this work
  before — guidance, not mandate, but whatever you choose must hit those
  percentages measurably.
- **Lives, progression, HUD** — three lives, an extra life at 10,000
  points, board advance on the last dot, a game over that
  returns to attract mode, and SCORE / HI-SCORE / board / lives always
  on screen.
- **Attract mode** — a title screen with the game's name drawn large in
  your own glyphs, the cast introduced by name (Bruiser, Pixie, Ivy,
  Sable), a score table, and a **self-playing demo**: the game plays
  itself under the real engine until a key is pressed.
- **High scores** — a top-5 table with initials entry (type
  letters/digits; the third character saves, RETURN or SPACE saves
  early) that survives across games in the same session.

**The three acts.** Between boards, at the arcade's authentic points in
the sequence — after boards 2, 5, and 9, with the third act returning
every fourth board thereafter — play three animated intermission cut
scenes, each with its own music:

1. **They meet** — a chase across the screen that ends with the two
   leads facing each other and a heart between them.
2. **The chase** — the pair dart back and forth across the screen at
   increasing speed, passing and re-passing.
3. **The delivery** — a stork crosses and drops a bundle; a junior
   muncher arrives.

These must be *real animated scenes* — sprites moving on timed
choreography with their own score — not title cards, not a line of text
describing what would have happened. Original staging and original art;
the narrative beats are what stays faithful.

**Hidden keys.** On the title screen only, `1`, `2`, and `3` jump
straight into Acts 1, 2, and 3, returning to the title when the act ends.
They exist so a reviewer can reach the scenes without playing three
boards; they stay undocumented in-game and must be listed in the
fidelity audit's evidence section.

**Controls.** W/A/S/D steer, SPACE starts from the title and skips an
intermission. Turns are buffered: a direction entered before a junction
takes effect at the corner if it becomes legal in time; a reversal is
instant. Read the live held-key matrix code at $CB (the IRQ scanner
maintains it) so a held key steers continuously — GETIN's buffered keys
would stall movement mid-corner.

**Performance rules.** Pace the game with the jiffy clock. Redraw only
the character cells that changed — never repaint the whole maze. No ROM
calls in the hot path. Know the cycle cost of your per-tick actor
update; six actors, targeting, and collision are the heart of the frame.

**Sound.** Push the SID chip to its **full potential** across all three
voices (see the c64-development hardware reference): an original title
tune, distinct music for each act, and effects — the dot-munch
alternation, the energizer siren, the ghost-eaten rise, the fruit jingle,
the death spiral. Use real ADSR envelopes, a mix of waveforms (pulse with
swept pulse-width, triangle, sawtooth, noise) and the filter. Define
priorities for when music and effects contend for a voice, and shadow
every SID write in RAM — the chip is write-only, so your shadow bytes are
the testable evidence for sound.

**The improvement loop.** A first playable build is the *start* of this
demo, not the end. From there, work in explicit numbered iterations,
each one a full cycle:

1. **Evaluate** — play the game deterministically (see the proof
   protocol below) and run a fidelity audit: walk every bullet of the
   spec above and mark it PASS or FAIL with evidence from the running
   game, never from reading the source.
2. **Review** — do a detailed code review of the current build: inner
   loops cycle-counted, the per-tick actor update scrutinized, dead code
   and slack removed, and gameplay feel compared against the arcade
   (cornering, ghost pressure, the moment a scatter opens differently
   than last time).
3. **Improve** — fix every FAIL and act on every review finding.
4. **Re-verify** — prove each fix in the running game before counting
   it done.

Log each iteration in `demos/ms-muncher/AUDIT.md` so progress is
visible, and keep looping until an iteration ends with every spec bullet
PASS and a review that finds nothing worth fixing. Expect this to take
several cycles — "it runs" and "it's the arcade game" are different
claims.

**Prove it deterministically.** The machine runs far faster than real
time, so drive it like the debugger demo: `c64 key hold` (or poke $CB
yourself) for held steering, `c64 key type` for buffered presses, and
step the game with `c64 until` on your per-tick label, reading the
screen and registers between frames. Collect evidence PNGs into
`demos/ms-muncher/evidence/` per
docs/graphics-and-sprites.md: the title screen; each of
the four mazes; ghosts in scatter, in chase, frightened, and reduced to
eyes; the fruit mid-lap; each of the three acts (reached with the hidden
keys); a death; a game over; the high-score entry; and SID shadow bytes
captured mid-tune. Then write `demos/ms-muncher/test.yaml` — a
deterministic regression spec runnable with `c64 test run` — asserting
the sprite enables at $D015, maze and dot state in screen RAM, score and
lives, and non-zero SID shadows.

**Ship it.** When everything passes, package the game so anyone with
stock VICE can play it: `c64 package` your source into
`demos/ms-muncher/ms-muncher.d64` with `--title "MS MUNCHER"` (the `.prg`
lands beside it), and tell the user the exact run command `c64 package`
prints — including the video-standard flag, so they get the timing you
tested.

Nothing here is borrowed but the rules — and the rules are borrowed
exactly.
