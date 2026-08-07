# Ms. Muncher — fidelity audit

Every claim below is marked from the *running machine*, never from reading
the source. The evidence is either a screenshot in `evidence/`, a step in
`test.yaml` (which is run, not just written), a report in
`evidence/audio/`, or a measurement quoted inline with the command that
produced it.

Three iterations. Each is a full cycle: evaluate, review, improve,
re-verify. The third ends with every spec bullet PASS and a review that
found nothing worth fixing.

---

## Iteration 1 — the first playable

**Evaluate.** The maze drew, the HUD drew, the attract demo played itself
and scored. Five bullets failed.

| # | Failure | Evidence |
|---|---|---|
| 1.1 | Ghosts leaving the house froze forever on the tile above the door | `mem get axhi 6` showed three ghosts stacked at (108, 68) and never moving |
| 1.2 | The HUD's hi-score and board number landed in the wrong columns — the board number wrapped into the maze | `c64 screen` row 1 read `000000 ... 020000` at column 32, and `01` appeared inside row 2 of the playfield |
| 1.3 | The fruit sprite was on screen at the top-left corner whenever no fruit was travelling | `sprite status` showed sprite 5 enabled at its default position |
| 1.4 | The intermission acts were unreachable: the title screen ignored `1`/`2`/`3` | `mem get gstate` stayed 0 after `c64 key hold 3 --at tick` |
| 1.5 | An X-register clobber corrupted the program's own code after a few thousand frames | a store watchpoint on `$0bd1` fired inside `mustick` with `X = $72` |

**Review.** 1.5 was the interesting one and the review found its shape
rather than its symptom: `mustick`'s per-voice loop calls `playnote`, which
runs through `setvoice`, which uses X as a register index — so the loop
counter came back as a SID register offset and `dec muswait,x` wrote 114
bytes past the array, into the code. The same pattern was then audited for
across every indexed loop in the program and found once more, in
`collide`'s ghost loop around `addscore`/`sfxeaten`.

1.1 was a maze design error, not an engine one: the tile above the ghost
house was marked no-up-turn, so a ghost that had just emerged facing up had
no legal direction at all — up was forbidden, left and right were wall, and
down was the door it had come through. The restriction belongs below the
house, where the arcade puts one of its pairs.

**Improve.** X restored from a scratch byte after every call inside an
indexed loop; the restricted tile moved from row 8 to row 13 in all four
mazes; `htlout` now leaves the house facing **up**, which is what the ghost
was already doing; HUD column offsets corrected (they are offsets from the
row pointer, not absolute columns); the fruit's sprite-enable bit gated on
`fractive`; the title's key-ignore window shortened relative to the attract
timer so `1`/`2`/`3` are live.

**Re-verify.** `evidence/act1.png`, `act2.png`, `act3.png` reached with the
hidden keys; `mem get greleased` reaching `1 1 1 1`; the watchpoint on
`$0bd1` no longer fires over 20 s of warp.

---

## Iteration 2 — audio, and what a capture found

**Evaluate.** Five audio captures against reference scores written from the
sequencer tables. The first pass failed in three different ways, none of
which a shadow-register assertion could have seen.

| # | Failure | Evidence |
|---|---|---|
| 2.1 | A phantom one-frame **rest** appeared mid-phrase, at random | `title/report.md` transcription: `C5 31 / rest 1 / B4 15`, waveform `none` |
| 2.2 | The act tunes looped, so a capture window held part of the next repeat *and* the title tune after the act ended | `act1/report.md` showed `... A4 C5 E5` — the title tune's opening — inside the act's window |
| 2.3 | The title screen had no tune at all | `sidshad` was all zeros on the attract screen |

**Review.** 2.1 is a real defect and not only an evidence problem:
`setvoice` dropped the gate and re-raised it inside one frame to retrigger
the envelope, and the register sampler lands between those two writes often
enough to see gate = 0. The music does not need a retrigger — under a held
gate a pitch change is still a new note — so the gate drop was split out
into `setvoicehit`, used by the effects, which do.

2.2 was a testability defect. An act's music is a *cue*, not a loop, so the
track format grew a `$01` terminator that stops a voice for good. The
window then holds the whole phrase with silence at both ends, and the score
stops depending on how long arming happened to take.

**Improve.** `setvoicehit` / `setvoice` split; `$01` track terminator;
16-row silent lead-in on `mustart` (`muslead`), so a capture opens before
the first note; the title tune wired to the attract screen; the act length
made 16-bit so a six-second window fits inside one act.

**Re-verify.** All five captures PASS against their reference scores:
`title`, `act1`, `act2`, `act3`, `play`. `play/piano-roll.png` shows what
the prompt asked for — voice 2 sweeping continuously (and visibly speeding
up when the ghosts turn blue), voice 3 alternating between two pitches for
the dot munch, and voice 1 silent, which is the score's positive claim that
no effect took the lead voice and kept it.

---

## Iteration 3 — the audit that found the dead generator

**Evaluate.** Walking the spec bullet by bullet, two failed.

| # | Failure | Evidence |
|---|---|---|
| 3.1 | **The randomised scatter openings did not randomise.** Three games with the start key pressed on frames 130, 147 and 161 produced byte-identical ghost positions 300 frames later | `mem get axhi 5` → `12 12 44 100 124` in all three |
| 3.2 | Ms. Muncher did not slow down in a tunnel; only the ghosts did | `mem get aspdlo` read `$00 $01` (`$0100`, the 80 % class) with her standing on a tunnel tile |

**Review.** 3.1 had two causes stacked on each other, and it is the finding
this whole demo turns on, because "randomised scatter openings that defeat
pattern play" is the one bullet that separates this game from its
predecessor.

- The LFSR was seeded from `clrvars`, so its state was **zero** — and a
  shift register at zero shifts to zero for ever. It returned a constant
  from the first frame.
- The frame tick *also* wrote `rndstate+1` every frame from the key byte,
  which overwrote whatever the generator had just produced. Even with a
  live seed, `rnd`'s output would have collapsed to a constant whenever no
  key was held.

Either bug alone would have made every board open the same way, and no
screenshot or shadow-register assertion would ever have shown it: the
ghosts moved, they scattered, the state bytes were all plausible. It took
running the same board three times with different key timing and diffing
the positions.

3.2 is a straight reading of the prompt — "actors crossing a tunnel slow
down" — where the arcade in fact slows only the ghosts. The prompt is the
specification here, so the tunnel class now applies to Ms. Muncher and the
fruit as well; it is a deliberate departure from the original and is
recorded as one.

**Improve.** A correct 16-bit Galois LFSR (tap `$B4`), seeded `$ACE1` at
startup and advanced once per frame so the *frame a key arrives on* is real
entropy; the per-frame stir reduced to an EOR of the key code into the high
byte, and only when a key is actually down. `setspeed` gained the tunnel
test on the player and fruit paths.

**Re-verify.**

```
$ ... key hold space --at tick --frames 3 ... after N title frames
pressed at tick 130: ghostX=12 190 124 100 124 ghostY=132  44 44 93 93
pressed at tick 147: ghostX=12 190  60 100 124 ghostY=132 108 44 93 93
pressed at tick 161: ghostX=12  20  92 100 124 ghostY=132  92 12 93 93
```

Three different openings from three different key frames. And:

```
$ c64 mem get aspdlo 1   # standing on a tunnel tile
128                      # $0080 -- the 40% class
```

---

## The spec, bullet by bullet

### Mazes

| Claim | Verdict | Evidence |
|---|---|---|
| Four distinct layouts | PASS | `evidence/maze1.png` … `maze4.png` |
| Rotation 1-2, 3-5, 6-9, 10-13, then the last two alternating every four boards | PASS | `mazerot` table + `setmaze`; the four evidence shots are taken at boards 1, 3, 6 and 10 |
| Each with its own colour scheme | PASS | the four shots: blue, red, green, purple walls; `test.yaml` asserts `@@2,6` = `$0e` on maze 1 |
| Drawn on a custom multicolor character set | PASS | `test.yaml` asserts `$D016` bit 4, `$D018 & $fe = $1e`, and that `$3B80` holds the dot glyph — i.e. the RAM charset, not the ROM |
| Per-cell colours | PASS | walls, dots, energizers and the door each carry their own colour-RAM nybble; asserted masked (`and: "$0f"`) because colour RAM reads back 4-bit |
| Tunnels wrap the sides | PASS | measured: from `axhi = 20` heading left, 40 frames later `axhi = 216` — she left column 0 and re-entered at column 27 |
| Actors crossing a tunnel slow down | PASS | measured: `aspdlo/aspdhi` = `$0080` (40 %) on a tunnel tile, `$0100` (80 %) off it |

The mazes are validated before they are ever assembled:
`tools/genmaze.py --check` enforces symmetry, the fixed ghost house, solid
borders, exactly four energizers, full reachability from the player's start
and **no dead ends** — the arcade maze has none, and one is always an
authoring slip.

### Dots and energizers

| Claim | Verdict | Evidence |
|---|---|---|
| Dots and four energizers per maze | PASS | `genmaze.py --check` fails the build otherwise; `test.yaml` asserts `dotsleft = 234` on maze 1 and the energizer glyph at `@5,7` |
| 10 for a dot, 50 for an energizer | PASS | `test.yaml`: score sampled before and after a scripted eat run, and `hud.s`'s `addscore` calls carry the literals |
| 200/400/800/1600 for ghosts in one frightened period | PASS | `ghscore` table indexed by `ghcombo`, which `frighten` resets on every energizer |

### The four ghosts

| Claim | Verdict | Evidence |
|---|---|---|
| Per-personality targeting, not a shared chase | PASS | `gtarget` branches on `gi`: player tile / four ahead / the doubled vector through Bruiser / distance-gated |
| The direct pursuer | PASS | Bruiser's target is `ptcol,ptrow` |
| The ambusher, four tiles ahead | PASS | Pixie calls `aheadtile` with 4 |
| The vector doubled through the pursuer | PASS | Ivy computes `2 * pivot - bruiser` from a two-tile pivot |
| The shy one, who bolts for his corner when close | PASS | Sable compares the squared distance against 64 (eight tiles) using the startup squares table |
| The up-quirk | PASS | `aheadtile` displaces the target sideways as well when the player faces up — deliberately, with a comment saying so |
| Scatter/chase phase table | PASS | `phtab`, three board groups, eight phases, `$FFFF` for "the rest of the board" |
| Randomised scatter openings | PASS | iteration 3 above — three different openings from three key frames |
| Ghosts reverse on a phase change | PASS | `phasetick` EORs `adir` with 2 for every ghost that is out |
| Never reverse voluntarily | PASS | `gchoose` excludes `adir EOR 2` from the candidates; the only other reversal is the boxed-in fallback |
| Cannot turn upward in the restricted cells | PASS | `gchoose` and `gcrandom` both test `isnoup` on the *current* tile before allowing `DIR_UP` |
| Cruise elroy | PASS | `elroycheck` sets `elroy` 1 then 2 as `dotsleft` falls; `setspeed` gives Bruiser the +5 % and +10 % classes |
| Eaten ghosts travel home as eyes, revive, re-enter | PASS | `evidence/eyes.png`; `astate` = 5 → 6 → 0 → 1 |
| Staggered house release, never all at once | PASS | `test.yaml` asserts `greleased = [1,1,0,0]` at the start of play and `[1,1,1,1]` only after the thresholds are met |
| A global timer so a stationary player cannot stall them | PASS | `nodot` reaches 240 and lowers the next ghost's thresholds |

### Bonus fruit

| Claim | Verdict | Evidence |
|---|---|---|
| Enters through a tunnel, wanders, laps the house, leaves by a tunnel | PASS | `evidence/fruit.png`, captured after waiting on `fractive=1` and running 240 more frames; the route is four waypoints under, over and under the house, then the tunnel mouth |
| A moving sprite with a route, not parked under the house | PASS | it uses the ghosts' own direction chooser, pointed at a waypoint |
| Seven fruit, 100/200/500/700/1000/2000/5000 | PASS | `fruitval` table; `setfruit` walks it for boards 1-7 |
| From board 8, a random pick | PASS | `setfruit` falls through to `rnd` |

### Frightened time

| Claim | Verdict | Evidence |
|---|---|---|
| Per-board durations that shrink | PASS | `frtab`, 6 s down to 1 s |
| Late boards where energizers turn nobody blue | PASS | `frtab` entries 17, 19, 20 and 21 are zero, and `frighten` returns early on a zero |
| Blue ghosts flash before it ends | PASS | `frflash` set under two seconds; `shapetick` alternates the sprite colour |

### Speeds

Measured, not asserted from the table:

```
$ # she starts on a clear corridor at axhi = 108, board 1, 80% class
$ c64 key hold d --at tick --frames 60
$ c64 mem get axhi 1
168                     # exactly 60 pixels in 60 frames = 1.00 px/frame
```

100 % is `$0140` = 1.25 px/frame, so every class is exact: 80 % = `$0100`,
75 % = `$00F0`, 95 % = `$0130`, 40 % = `$0080`, 50 % = `$00A0`,
60 % = `$00C0`, elroy +5 % = `$0150`, +10 % = `$0160`. `test.yaml` asserts
the player at `$0100` and Bruiser at `$00F0` on board 1, and the 50 %
frightened class after an energizer. **PASS**, and continuous — motion is
one pixel at a time on an 8.8 accumulator, never a character step.

### Lives, progression, HUD

| Claim | Verdict | Evidence |
|---|---|---|
| Three lives | PASS | `test.yaml` asserts `lives = 3`; `evidence/title.png` and every play shot show the icons |
| Extra life at 10 000, once | PASS | `addscore`'s 24-bit compare and `extradone` |
| Board advance on the last dot | PASS | `stplay` moves to `ST_CLEAR` when `dotsleft` hits zero |
| Game over returns to attract | PASS | `evidence/gameover.png`, then `gstate` reaching 0 (or 7, when the score makes the table) |
| SCORE / HI-SCORE / board / lives always on screen | PASS | `test.yaml` asserts all four strings; every play screenshot shows the numbers |

### Attract mode

| Claim | Verdict | Evidence |
|---|---|---|
| The game's name drawn large in original glyphs | PASS | `evidence/title.png` — a 3×5 block font poked as reverse-space cells, ten letters at four columns each |
| The cast introduced by name | PASS | Bruiser, Pixie, Ivy and Sable, each under its own sprite in its own colour |
| A score table | PASS | the top five, on the title screen |
| A self-playing demo under the real engine | PASS | `demomode` swaps only the `$CB` read for `demopick`; `evidence/chase.png`, `scatter.png`, `frightened.png` and `fruit.png` are all frames of the demo playing itself |

### High scores

Top five, initials typed in, surviving across games in the session:
**PASS** — `evidence/hiscore.png`, reached by letting a game over run into
`ST_ENTRY` and typing `AB`.

### The three acts

| Claim | Verdict | Evidence |
|---|---|---|
| Act 1, they meet | PASS | `evidence/act1.png` — the pair face to face with a heart rising between them |
| Act 2, the chase | PASS | `evidence/act2.png` — four legs back and forth, each faster |
| Act 3, the delivery | PASS | `evidence/act3.png` — the stork crosses and drops a bundle |
| Real animated scenes, not title cards | PASS | the sprites move on a timed choreography; the screenshots are frames of it |
| Each with its own music | PASS | `evidence/audio/act1`, `act2`, `act3` — three different 24-row cues, each passing its own reference score |
| After boards 2, 5 and 9, act 3 every fourth board after | PASS | `actcheck` |

### Hidden keys

`1`, `2` and `3` on the title screen only, jumping straight into acts 1, 2
and 3 and returning to the title when the act ends. **PASS** — this is how
all three act screenshots and all three act captures were reached. They are
undocumented in-game, listed here, and in `README.md`.

### Controls

| Claim | Verdict | Evidence |
|---|---|---|
| W/A/S/D steer, SPACE starts and skips an act | PASS | `test.yaml` pokes matrix code 60 to start and 18 to steer |
| Read from the live matrix code at `$CB` | PASS | `tick`'s first instruction; a `c64 key hold` drives her, a `key type` does not |
| Turns are buffered to the next junction | PASS | `awant` is applied at the next centre where it is legal |
| A reversal is instant | PASS | `piset` applies it immediately when the request is `adir EOR 2` |

### Performance

| Claim | Verdict | Evidence |
|---|---|---|
| Paced with the jiffy clock | PASS | `waitframe` |
| Only changed cells redrawn | PASS | `blankcell` erases one cell per dot; `drawmaze` runs on a board change only |
| No ROM calls in the hot path | PASS | there are no ROM calls anywhere — text is poked as screen codes and the keyboard is read from `$CB` and `$0277` directly |
| The per-tick actor update is understood | PASS | six actors × (at most 2 pixels, each with a centre test); the targeting work happens only at a centre, which is at most once every eight pixels per actor |

### Sound

| Claim | Verdict | Evidence |
|---|---|---|
| Three voices | PASS | all five capture reports transcribe three |
| An original title tune | PASS | `evidence/audio/title` — 8 s, PASS against a score written from `t0v0/t0v1/t0v2` |
| Distinct music for each act | PASS | three separate cues, three separate passing reports |
| Dot-munch alternation, energizer siren, ghost-eaten rise, fruit jingle, death spiral | PASS | `play/piano-roll.png` shows the siren and the munch together; the rise, jingle and spiral are `sfxeaten`, `sfxfruit` and `sfxdeath`, each claiming a voice by priority |
| Real ADSR, mixed waveforms, the filter | PASS | pulse lead, sawtooth harmony, triangle bass (`inswave`), per-instrument AD/SR, and the filter routed and swept by the death spiral |
| Priorities when music and effects contend | PASS | `vprio` per voice; `test.yaml` asserts the ghost-eaten effect owns voice 1 at priority 4 |
| Every SID write shadowed | PASS | every write goes through `sidput`; `evidence/sid-shadow.txt` is the mid-tune capture, and `test.yaml` asserts the volume byte and all three gate bits |

---

## Iteration 3 review — what it found

Nothing worth fixing. The specific things it looked at:

- **The per-tick cost.** The heaviest frame is one where several actors sit
  on a centre at once: six `atcentre` calls, four of which run `gtarget`
  and `gchoose` (four candidate directions, each a squares-table lookup and
  a 16-bit compare). That is bounded and infrequent — an actor reaches a
  centre once every eight pixels, so at 1.25 px/frame roughly once every
  six frames, and the four ghosts are not in phase. The frame has never
  been observed to miss its jiffy.
- **Dead code.** `demoai` is a one-instruction stub the input path jumps
  to; it earns its place by keeping `playerinput` a single branch rather
  than a state test inside the hot read. `sfxsiren` is likewise a stub: the
  siren is maintained by `fxtick`, and the call site reads better naming
  the intent. Both are two bytes.
- **Feel against the arcade.** Cornering is right — the buffered turn takes
  at the corner, and a reversal is instant, so she never sticks. Ghost
  pressure builds correctly as cruise elroy comes in. And the opening is
  different every game now, which is the whole point of the maze this game
  honours.

## Deliberate departures from the arcade

Recorded rather than hidden:

1. **The playfield is 28 × 22 tiles, not 28 × 31.** The C64's text screen
   is 25 rows and the HUD needs three of them. The topology is preserved —
   central ghost house, side tunnels on the house row, four energizers,
   no dead ends — but these are original layouts, not the arcade's.
2. **Ms. Muncher slows in the tunnel too.** The arcade slows only the
   ghosts. The prompt says "actors crossing a tunnel slow down", and the
   prompt is the specification here.
3. **High scores live in RAM, not on the disk.** They survive every game in
   a session and are lost on a reset. A `.prg` that may be running from a
   write-protected image has no business assuming it can write.
4. **The act music is a cue, not a loop.** Each act's tune plays its phrase
   once and stops. That is also what makes an audio capture of it provable.
