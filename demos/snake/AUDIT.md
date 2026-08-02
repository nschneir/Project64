# Snake — fidelity audit log

Three numbered iterations, each a full cycle: **evaluate** the running game
against every bullet of `PROMPT.md`, **review** the code, **improve**, and
**re-verify** on the machine. Every PASS below is evidence read out of a live
C64 — a memory or register read, a screen-code read, a cycle count, or a
captured frame — never from reading the source.

Everything is driven the way the spec requires: `--warp --headless`, input
injected as the held-key matrix code at `$CB`, and every sample anchored on a
`c64 until mainloop` stop. `tools/evidence.sh` re-runs the whole protocol and
rewrites `evidence/`; `c64 test run test.yaml` is the 101-step regression.

---

## Iteration 1 — first playable build

### Evaluate

| # | Spec bullet | Verdict | Evidence |
|---|---|---|---|
| 1 | Title screen: the name large in PETSCII, bright, "PRESS ANY KEY TO PLAY" | PASS | `@3,8` = `160 160 160 160`; five letters, five colours from `titlecol` |
| 2 | Playfield border in graphics characters | PASS | `@1,0`=130, `@1,1`=128, `@24,39`=133 |
| 3 | Dies on the border | PASS | steered into column 39, `gstate` 1 -> 2 |
| 4 | Dies on its own body | **not yet observed** | never grew long enough to try |
| 5 | Colour RAM: border, snake, food distinct | PASS | border 14, snake 5, food 2, HUD 14/1/7/10 |
| 6 | Continuous movement, W/A/S/D from `$CB` | PASS | `key hold d --frames 12`: `hcol` 10 -> 22 |
| 7 | Grows on eating; food reappears on a random empty cell | PASS | `snlen` 3 -> 6 -> 9; `newfood` re-drew at (20,10) |
| 8 | Custom character set | PASS | `$D018` reads `$1D`; code 139's bytes at `$3458` are the apple, not the ROM glyph |
| 9 | SID blip on eating, crash on dying, every write shadowed | PASS | `sidshadow` = `0 64 0 0 17 9 …`; voice 3 = `$81` on death |
| 10 | SCORE and LEVEL status line | **FAIL** | the first apple scored **100**, not 10 |
| 11 | Level up every few pickups: faster, new colour | PASS | 5 pickups -> `level` 2, `speed` 12 -> 10, `snakecol` 5 -> 13 |
| 12 | Game over with final score and best score, key to replay | PASS | panel drawn, `gstate`=2, SPACE restarts |
| 13 | High score survives into the next game | PASS | game 2 opened with `hidig` = 0070, `scdig` = 0000 |

### Review

1. **The score is ten times too big.** `eat` counted its repetitions in X and
   `add10` uses X for the digit index (`inc scdig,x` has no `,Y` form), so the
   counter came back as 2 every time and the loop ran until a carry changed
   it. Found by reading `scdig` after one apple, not by reading the source.
2. **The title screen never appears when the game is started with `RUN`.**
   The RETURN that typed RUN is still down at `$CB` when the title paints, so
   the first tick dismisses it.
3. **The border's corners do not join.** The horizontal piece rails on rows
   0-1/6-7 and the corners' arms on rows 1-2/5-6 — one pixel out.
4. **The head is indistinguishable from the body** at 1x: both carry the same
   scale-dot pattern and a one-pixel eye.
5. **The game-over panel is too small for its longest line.** "PRESS SPACE TO
   PLAY AGAIN" is 25 characters in a 26-wide panel, so it runs into its own
   border on both sides.
6. **The ring-buffer cap has no margin.** `grow` accumulates in threes and is
   only refused at `snlen >= 250`, so `snlen` could reach 254 against a
   256-entry ring.

### Improve + re-verify

- `eat` counts in `ptsleft`, a memory byte. Re-verified: one apple at level 1
  scores `0 0 1 0`, and `test.yaml` step 50 asserts it.
- `pollkey` gained `keyarm`: entering the title or the game-over panel clears
  it and only a frame with **no** key down sets it, so a key held from before
  a screen appeared cannot dismiss it. Re-verified: `c64 run` now stops on
  the title, and `wait --text "PRESS ANY KEY TO PLAY"` returns in 1.4 s.
- `bordh` moved to rows 1-2/5-6. Re-verified in `play.png`: the corners join.
- The four head glyphs are solid — no scale dots — with a 2x2 eye hole facing
  the way they travel. Re-verified in `levelup.png`.
- Panel widened to rows 8-17 x columns 4-35, with blank spacer rows.
- `MAXLEN` 250 -> 240.

---

## Iteration 2 — the look, and a sound bug the shadow bytes exposed

### Evaluate

Every row of iteration 1 re-checked and PASS, plus the two that were open:

| # | Spec bullet | Verdict | Evidence |
|---|---|---|---|
| 4 | Dies on its own body | PASS | game 2 turned four times into its own trail: `gstate` 1 -> 2 with the head one cell inside the body |
| 10 | SCORE and LEVEL status line | PASS | `SCORE 0010` … `SCORE 0050`, `LEVEL 1` -> `LEVEL 2` in screen RAM |

### Review

1. **The custom glyphs were parked at screen codes 128-139**, which is the
   ROM's reverse-video half — 129-154 are reverse A-Z. Any reverse-video
   text would have drawn snake parts. That rules out the cheapest emphasis
   the machine has, for no reason: the glyphs can live anywhere.
2. **A pickup blip is silent for one apple after every level-up.** The SID
   starts an attack on a 0->1 gate transition only. There is one `sfxlen`
   countdown and one `sfxreg`, and `levelup` runs inside `eat` — so the
   level blip takes the countdown over and voice 1 is left gated on for
   good. The next `sfxeat` writes `$11` over `$11` and nothing attacks.
   Caught by reading `sidshadow` at game over: `sidshadow+4` was `$11` long
   after the blip should have been released.
3. **Glyph codes were bare numbers** in three files.

### Improve + re-verify

- Glyphs moved to screen codes 112-123 (ROM graphics characters the game
  never draws), regenerated with `c64 charset encode --first-code 112`, and
  named: `BORDH`, `BORDV`, `BORDTL/TR/BL/BR`, `HEADUP/DN/LF/RT`, `BODY`,
  `FOODCODE`, plus `BLANK`, `BLOCK` and `REVERSE`. Re-verified: the apple's
  eight bytes now read back at `$3000 + 123*8 = $33D8`.
- Every effect now opens with `jsr sfxoff` (gate down whatever was sounding)
  and a write of 0 to its **own** control register (clear the gate so the
  next write can raise it). Re-verified: `call sfxeat` in isolation leaves
  `sidshadow+4` = `$11`, and after a level-up voice 1 reads `$10` while
  voice 2 reads `$11` — the pickup voice really is released.
- With reverse video freed up, `GAME OVER` became a full-width reverse bar:
  solid red across the panel with the words knocked out of it.
  **Cost, recorded honestly:** reverse text no longer decodes as text, so
  `c64 screen` shows `GAME█OVER` and `wait --text "GAME OVER"` cannot match.
  The spec asserts the nine reverse screen codes at `@10,15` instead, and
  `PRESS SPACE TO PLAY AGAIN` (plain text) is the state's text anchor.

---

## Iteration 3 — cycle counts, and the deterministic proof

### Evaluate

Every spec bullet PASS, on the build that ships. Full walk:

| # | Spec bullet | Verdict | Evidence |
|---|---|---|---|
| 1 | Title: name large in PETSCII, bright colours, "PRESS ANY KEY TO PLAY" | PASS | `@3,8`/`@4,8`/`@7,28` block patterns; `evidence/title.png` |
| 2 | Border in graphics characters | PASS | `@1,0`=114, `@1,39`=115, `@24,0`=116, `@24,39`=117, `@12,0`=113 |
| 3 | Dies on the border | PASS | 20 moves up then one more: `gstate` 1 -> 2 at row 1 |
| 4 | Dies on its own body | PASS | four clockwise turns at length 6: `gstate` 1 -> 2, `evidence/hiscore.png` |
| 5 | Border / snake / food / title / HUD in distinct colours | PASS | `$D800` nybbles: border 14, snake 5, apple 2; HUD labels 14, score 1, level 7, hi 10; five title colours |
| 6 | Continuous movement, W/A/S/D read from `$CB` | PASS | `key hold` moves one cell per tick; a 180 is refused (`hcol` kept climbing, `curdir` stayed 3) |
| 7 | Grows on eating; a fresh apple on a random empty cell | PASS | `snlen` 3 -> 6 with `grow` 3 -> 0; apples at (23,26) then (22,11), each on a cell holding code 32 |
| 8 | Custom character set for snake, food and the rest | PASS | `$D018` & `$FE` = `$1C`; `$33D8` = the apple's eight bytes |
| 9 | SID blip on eating, crash on dying, every write shadowed | PASS | `sidshadow+1/+4/+5` = `$40`/`$10`/`$09` after the blip released; `+11` = `$11` on level-up; `+18` = `$81` on death; `+24` = 15 |
| 10 | SCORE and LEVEL status line during play | PASS | `SCORE 0000` -> `SCORE 0020`, `LEVEL 1` -> `LEVEL 2` |
| 11 | Level up every few pickups: faster, distinct colour | PASS | fifth pickup: `level` 2, `speed` 12 -> 10, `snakecol` 5 -> 13, and the **tail's** colour nybble is 13 too |
| 12 | Game over: final score, best score, a key to replay | PASS | `PRESS SPACE TO PLAY AGAIN` on screen; SPACE -> `gstate` 1 |
| 13 | High score survives into the next game | PASS | game 2 opens `scdig`=0000, `hidig`=0020, and its own game-over panel still shows `HI 0050` |
| 14 | Packaged so stock VICE can play it | PASS | `c64 disk boot snake.d64` in a fresh session reaches the title: `evidence/shipped-d64.png` |

### Review

1. **Per-move cost, measured** (`c64 profile`, IRQs masked):

   | Routine | Cycles |
   |---|---|
   | `plotaddr` | 83 |
   | `steer` | 21 |
   | `movesnake` (includes one `plotaddr`) | 368 |
   | `playtick` (the whole per-move update) | **407** |

   A jiffy is ~17,045 cycles, and the fastest level paces at 2 jiffies, so
   the update is **1.2% of the tightest tick**. Nothing here is worth
   optimising: the game is a pacing loop with a rounding error attached to
   it. The reason it stays flat is the ring buffer — a move rewrites three
   cells whatever the snake's length, so a 240-segment snake costs the same
   as a 3-segment one.
2. **Steering response.** The `$CB` read is the first instruction of the
   tick, and `pace` samples it again every jiffy of the wait, so a key
   pressed anywhere inside a 12-jiffy tick is acted on at the next move —
   never more than 200 ms at level 1 and 33 ms at level 9.
3. **Speed curve.** `12,10,8,7,6,5,4,3,2` jiffies is 5 moves/second at level
   1 and 30 at level 9, five pickups apart. The steps shorten as they get
   faster, which is the right shape: the early ones are barely felt and the
   late ones are the difficulty.
4. **The fairness of a death.** Three things were checked, and all three are
   in the code deliberately: a 180-degree turn is refused against the
   direction actually *last moved* (not the pending one), so a double turn
   inside one tick cannot fold the snake into itself; entering the cell the
   tail vacates **this move** is legal, so a snake at full stretch does not
   die chasing a segment that is no longer there; and the key that started
   the game is discarded rather than steering the first move.
5. **Dead code and slack.** None found: `pcodeor` is the only global that
   can leak, and it is set and cleared in adjacent lines of one routine, so
   the comment on `putcell` states the contract instead.
6. **Headroom.** Code and data end at `$11B2` and BSS at `$13FB`, against a
   character set at `$3000` — 7,173 bytes clear.

Nothing found worth fixing. The loop ends here.

### Re-verify

- `c64 test run test.yaml` — 101 steps, all pass.
- `sh tools/evidence.sh` — runs the whole protocol and rewrites the seven
  frames in `evidence/`.
- `c64 package snake.s -o snake.d64 --title "SNAKE"` and
  `c64 disk boot snake.d64` in a session that has never seen the source.

---

## Notes on driving this game deterministically

Two things about the shape of the program made the proof easier, both worth
copying:

- **`mainloop` is the tick in every state**, not just in play. That makes
  `c64 until mainloop` an anchor that survives the fatal move, so the
  cookbook's "the move that ends the game can never be driven by `key hold`"
  does not apply here — `key hold d --at mainloop --frames 1` drives the
  snake into the wall and comes back stopped, with the game-over panel
  already drawn. (`tools/evidence.sh` still breaks on `died`, because that
  stops the machine *at* the death rather than after it.)
- **`until` stops at the label, before the code under it runs.** A key poked
  into `$CB` while the machine is still free-running is consumed by the tick
  already in flight, not the one being asked for. Every input in `test.yaml`
  therefore anchors first, then pokes, then advances one tick.

One thing worth knowing about the toolset: `call:` (and `c64 profile`) is a
fake JSR that ends on a trap address, so it does not hand the interrupted
program back. Both are fine at the end of a spec and fatal in the middle of
one — `test.yaml`'s `call sfxeat` is the last step for that reason.
