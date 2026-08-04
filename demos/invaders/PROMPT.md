# Invaders — the 1978 arcade game, recreated

Using the c64 CLI (see skills/c64-development/SKILL.md, the 6502-assembly
skill, and docs/cli.md), build the closest recreation of the 1978 arcade
Space Invaders that a Commodore 64 can express — pure 6502 assembly with
a BASIC SYS stub. Everything for this demo lives in `demos/invaders/`.

**First, write the plan.** Before any code, turn this spec into
`demos/invaders/PLAN.md` — ordered, independently verifiable steps, each
naming the observation that proves it — and build from that plan, updating
it as the running machine corrects you.

Push the C64's graphics to their fullest: use a
**graphics mode built on a custom multicolor character set** for the
invaders, shields, and HUD (drawn at $0400 with color RAM at $D800 —
design your own invader glyphs rather than settling for stock PETSCII),
and use **hardware sprites** for the smooth movers: the laser base, the
player shot, and the mystery UFO
(docs/graphics-and-sprites.md has the authoring and testing rules).
The keyboard replaces the arcade controls: A/D held down move the laser
base, space fires.

**The arcade spec — recreate each of these faithfully:**

- **Formation** — 5 rows of 11 invaders in three classes: top row worth
  30 points, next two rows 20, bottom two rows 10 (990 points per wave).
  Every invader alternates between two shapes as it marches — pick
  character pairs (or a custom charset) that make the three classes
  visually distinct, with per-class colors in color RAM.
- **The march** — use the authentic engine: move ONE invader per tick,
  sweeping the formation in order (the arcade updated one alien per
  frame). The formation steps sideways; when any live invader touches an
  edge it drops one row and reverses. The famous speed-up as invaders die
  must be *emergent* from the one-per-tick engine — fewer invaders means
  the sweep completes sooner — never a scripted speed table. The final
  invader should be visibly frantic.
- **Player** — the laser base is sprite 0, moved smoothly by pixels, with
  three lives, an extra life at 1500 points, and only one player shot
  (its own sprite) on screen at a time.
- **Bombs** — up to three invader bombs in flight, dropped from the
  lowest live invader in a column, in the three classic flavours: slow
  straight, fast straight, and the wiggly one (character-mode bombs are
  fine). A bomb and the player shot cancel each other when they collide —
  use the VIC-II collision latches or your own grid math, but say which.
- **Shields** — four bunkers between the base and the formation that
  erode piecemeal under fire from BOTH sides. Character-granular erosion
  is fine; better still give each cell damage states (solid →
  checkerboard → gone) so bunkers crumble rather than vanish.
- **Mystery UFO** — a sprite that crosses the top of the screen
  periodically with its own warbling sound, worth 50–300 points — and
  implement the real arcade secret: it pays 300 when hit by the player's
  23rd shot, then by every 15th shot after that. Count the shots.
- **Waves** — wave 1 starts high; waves 2 through 9 start one step
  lower each time; wave 10 resets to wave-1 height. The game ends when
  the lives run out or any invader reaches the baseline.
- **HUD** — SCORE, HI-SCORE, WAVE, and remaining lives always visible.
  The high score must survive across games in the same session.
- **Title screen** — the game's name drawn large with graphics
  characters, a SCORE ADVANCE TABLE listing the point values of the
  three invader classes and the UFO's `? MYSTERY`, and "PRESS ANY KEY
  TO PLAY".
- **Sound** — push the SID chip to its **full potential** across all
  three voices (see the c64-development hardware reference): the four-note
  descending bass heartbeat on one voice, locked to the march tempo so it
  accelerates naturally as the formation thins; shot, invader-hit,
  player-explosion, and UFO warble effects on the other two. Use real
  ADSR envelopes, a mix of waveforms (pulse with swept pulse-width,
  triangle, sawtooth, and noise), and the filter — the player explosion
  should be filtered noise, the UFO warble a ring-modulated or
  fast-swept tone, the shot a short bright pulse. Define priorities for
  when effects contend, and shadow every SID write in RAM — the SID is
  write-only, and your shadow bytes are the testable evidence for sound.

**Performance rules.** Pace the game with the jiffy clock. Redraw only
the character cells that changed — never repaint the whole screen. No
ROM calls in the hot path. Know the cycle cost of your per-tick invader
update; it is the heart of the game. For input, read the live held-key
matrix code at $CB (the IRQ scanner maintains it; A=10, D=18, space=60)
so a held A or D moves continuously while space fires — GETIN's buffered
keys would stall movement during fire.

**The improvement loop.** A first playable build is the *start* of this
demo, not the end. From there, work in explicit numbered iterations,
each one a full cycle:

1. **Evaluate** — play the game deterministically (see the proof
   protocol below) and run a fidelity audit: walk every bullet of the
   spec above and mark it PASS or FAIL with evidence from the running
   game, never from reading the source.
2. **Review** — do a detailed code review of the current build: inner
   loops cycle-counted, the per-tick invader update scrutinized, dead
   code and slack removed, and gameplay feel compared against the arcade
   (march rhythm, bomb pressure, speed-up curve).
3. **Improve** — fix every FAIL and act on every review finding.
4. **Re-verify** — prove each fix in the running game before counting
   it done.

Log each iteration's audit results so progress is visible, and keep
looping until an iteration ends with every spec bullet PASS and a
review that finds nothing worth fixing. Expect this to take several
cycles — "it runs" and "it's Space Invaders" are different claims.

**Prove it deterministically.** The machine runs far faster than real
time, so drive it like the debugger demo: `c64 key hold` (or poke $CB
yourself) for held movement, `c64 key type` for buffered presses, and
step the game with `c64 until` on your per-tick label, reading the
screen and registers between frames. Show me: the title screen; the
formation marching and animating; a shield eroding; bombs of different
flavours in flight; the UFO sprite crossing (with $D015 showing which
sprites are live); your SID shadow bytes captured mid-heartbeat; wave 2
starting lower than wave 1; a game over; and a second game whose
HI-SCORE is the first game's final score. Collect the screenshots as
evidence PNGs per docs/graphics-and-sprites.md.

**Audio evidence.** The shadow bytes prove your player wrote something;
they cannot prove the heartbeat is in tune, that it accelerates with the
march, or that an effect handed its voice back. Capture the sound itself
with `c64_audio_capture` (`c64 audio capture` from the shell) and commit
its five artifacts — `capture.wav`, `sid-log.jsonl`, `piano-roll.png`,
`spectrogram.png`, `report.md` — under `demos/invaders/evidence/audio/`:
the heartbeat with a full formation, the same heartbeat with the last
invader frantic, and a capture holding the shot, the invader hit, the
player explosion and the UFO warble. Write a reference score (YAML) from
your own music data and capture against it; the report must pass. Then
read your piano roll the way you read a screenshot — a wrong contour, a
missing voice, or bars that drift off the rhythm are bugs — and use the
spectrogram for what notes cannot show: the explosion's filtered noise and
the UFO's sweep. The maintainer's listen of `capture.wav` is the final
gate; skills/c64-development/references/audio-verification.md has the
method.

**Ship it.** When everything passes, package the game so anyone with
stock VICE can play it: `c64 package` your source into
`demos/invaders/invaders.d64` with `--title "INVADERS"` (the `.prg` lands
beside it),
and tell the user the exact run command `c64 package` prints
(`x64sc -ntsc invaders.d64` — the video-standard flag keeps the timing
you tested). On a real keyboard, the $CB scan then gives them exactly
the held-key controls you tested.
