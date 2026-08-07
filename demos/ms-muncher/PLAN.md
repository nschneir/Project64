# Ms. Muncher — implementation plan

The plan `PROMPT.md` asks for, written before any code and updated as the
running machine corrected it. Every task names the observation that proves
it; nothing here is counted done from reading the source.

Conventions: addresses are hex, `$` prefixed. "tile" = one 8×8 character
cell of the playfield. "actor" = one of the six moving things (Ms. Muncher,
Bruiser, Pixie, Ivy, Sable, fruit). All verification commands assume
`.venv/bin/c64` from the repository root and a session named `mm`.

---

## 0. Memory map and the hard ceiling

The VIC-II only sees bank 0 (`$0000-$3FFF`), and the toolset requires the
screen to stay at `$0400`, so **every byte of charset and sprite data must
live below `$4000`** and the program must end below the first of them.

| Range | Contents |
|---|---|
| `$0801-$080C` | BASIC stub `10 SYS 2061` |
| `$080D-$2FFF` | CODE / RODATA / DATA / BSS — **hard ceiling `$3000`** |
| `$3000-$37FF` | sprite shapes, blocks 192-223 (32 × 64 bytes) |
| `$3800-$3FFF` | character set (ROM copy, glyphs patched) |
| `$0400-$07E7` | screen RAM; `$07F8-$07FF` sprite pointers |
| `$D800-$DBE7` | colour RAM |

`$D018` = `$1E` (screen `$0400`, charset `$3800`); reads back `$1F`
(bit 0 unused, reads 1). `$D016` bit 4 set — multicolor text mode.

The ceiling is enforced at link time, not by hoping:

```asm
.import __BSS_LOAD__, __BSS_SIZE__
.assert (__BSS_LOAD__ + __BSS_SIZE__) <= $3000, error, "program ran into the sprite blocks"
```

**Task 0 verify:** `c64 build demos/ms-muncher/ms-muncher.s` succeeds and
`ls -l` on the `.prg` shows a length < `$27F3`.

---

## 1. Files

| File | Holds |
|---|---|
| `ms-muncher.s` | load address, stub, equates, state machine, `.include` list |
| `vars.s` | every mutable byte, one label per test-visible value |
| `chars.s` + `chars.inc` | charset installer; the patched glyphs |
| `sprites.s` + `sprites.inc` | shape blitter/compositor; the stored art |
| `maze.s` + `mazes.inc` | maze tables, auto-tiler, draw, dot bitmap |
| `actor.s` | the shared movement engine (8.8 accumulators, half-cell grid) |
| `player.s` | `$CB` steering, turn buffer, eating, death |
| `ghosts.s` | targeting, phases, house schedule, frightened, eyes |
| `fruit.s` | the travelling fruit and its route |
| `hud.s` | score/hi-score/board/lives, digit rendering |
| `attract.s` | title screen, cast intro, score table, the demo player |
| `acts.s` | the three intermission scenes |
| `hiscore.s` | top-5 table and initials entry |
| `sound.s` | SID sequencer, shadow bytes, effects |
| `tools/genmaze.py` | `tools/mazes.txt` (ASCII art) → `mazes.inc`, with validation |
| `tools/evidence.sh` | re-runs the proof protocol, rewrites `evidence/` |

---

## 2. Playfield geometry

- Playfield is **28 tiles wide × 22 tall**, drawn at screen column 6,
  screen row 2 (`MCOL0 = 6`, `MROW0 = 2`). Rows 0-1 are the HUD, row 24 the
  lives/fruit strip.
- Mazes are left-right symmetric, so only 14 columns are stored per row and
  the right half is the mirror. Tiles are nibble-packed: 7 bytes per row,
  154 bytes per maze, 616 for all four.
- Logical tile codes (`mazes.inc` nibbles):

  | Code | Meaning |
  |---|---|
  | 0 | empty passage |
  | 1 | dot |
  | 2 | energizer |
  | 3 | wall |
  | 4 | ghost-house door |
  | 5 | ghost-house interior |
  | 6 | passage, no-up-turn (the restricted cells) |
  | 7 | tunnel passage (slow zone) |

- **Auto-tiled walls.** No wall art is stored per maze. A wall tile's glyph
  is chosen from a 16-entry table indexed by which of its four neighbours
  are also wall, so the maze draws as connected pipework with rounded
  corners. Glyph codes `WALLBASE`..`WALLBASE+15`.

**Task 2 verify:** `python3 demos/ms-muncher/tools/genmaze.py --check`
passes its own connectivity/symmetry/energizer-count assertions for all
four mazes.

---

## 3. Character set (`chars.s`)

ROM charset copied to `$3800` with `$01` bit 2 cleared and IRQs off, then
these codes patched. Custom glyphs are parked at **96-127**, clear of the
reverse-video range 128-154.

| Code | Glyph |
|---|---|
| 96-111 | `WALLBASE`: the 16 wall connectivity shapes (multicolor) |
| 112 | dot |
| 113 | energizer |
| 114 | ghost-house door |
| 115-118 | the four quadrants of the large title logo letters |
| 119-126 | HUD/fruit pips and the life icon |

`c64 screen` decodes these through their ROM meanings, so **all maze
assertions are on `--codes` or `mem read`, never decoded text**; HUD text
stays on ordinary letter codes so `wait --text` still works.

**Task 3 verify:** `c64 mem read '$3800+112*8' 8` matches the dot glyph
bytes in `chars.inc`, and `c64 screen --png` shows the maze drawn.

---

## 4. The actor engine (`actor.s`)

Six actors in parallel arrays indexed 0-5 (0 = Ms. Muncher, 1-4 = Bruiser,
Pixie, Ivy, Sable, 5 = fruit).

| Array | Bytes | Meaning |
|---|---|---|
| `axlo`, `axhi` | 6+6 | X position, 8.8 fixed point, **pixels**, hotspot = actor centre |
| `aylo`, `ayhi` | 6+6 | Y position, same |
| `adir` | 6 | 0 up, 1 left, 2 down, 3 right |
| `awant` | 6 | buffered/next direction |
| `aspd` | 12 | speed, 16-bit, added to the position accumulator each tick |
| `astate` | 6 | per-actor mode (see `ghosts.s`) |

- **Speed units.** 100 % ≡ `$0140` (1.25 px/frame). A percentage that is a
  multiple of 5 is exactly `pct * 16 / 5`: 80 % = `$0100`, 75 % = `$00F0`,
  95 % = `$0130`, 40 % = `$0080`, 60 % = `$00C0`. This is what makes the
  speed classes *measurable* rather than approximate.
- **One-pixel steps.** Each tick the accumulator advances and the integer
  carry (0, 1 or 2 pixels) is walked one pixel at a time by `stepone`, so
  collision and tile transitions can never be skipped.
- **Turning happens at tile centres only** — `(px & 7) == 4 && (py & 7) == 4`
  — except a 180° reversal, which is legal anywhere.
- **Tunnels** wrap X at the playfield edges on the tunnel row; tile code 7
  selects the tunnel speed class.
- Sprite placement: `$D000+2n` = `24 + MCOL0*8 + px - 12`,
  `$D001+2n` = `51 + MROW0*8 + py - 11`; X bit 8 into `$D010`.

**Task 4 verify:** `c64 until tick` × 60 with the player held on `D` moves
`axhi` by exactly 75 pixels at 100 % (`$0140` × 60 = 75.0), and by 60 at
80 %.

---

## 5. Player (`player.s`)

- Steering reads `$CB` **once at the top of `tick`**, before any pacing, so
  `c64 key hold --at tick` is deterministic. W/A/S/D → `awant`.
- A turn in `awant` is taken at the next centre where it is legal; a
  reversal is applied immediately.
- Eating: at a tile centre, test the dot bitmap; clear the bit, blank the
  cell, add 10 (dot) or 50 (energizer), decrement `dotsleft`.
- Death: collision with a non-frightened ghost when both occupy the same
  tile → death spiral animation, `lives` decrement, respawn or game over.

**Task 5 verify:** hold `D` from the start position, `until tick` until
`score` reads 30, and `dotsleft` has dropped by exactly 3.

---

## 6. Ghosts (`ghosts.s`)

`astate` values: 0 house, 1 leaving, 2 scatter, 3 chase, 4 frightened,
5 eyes, 6 re-entering.

- **Targeting** at each tile centre, choosing the legal direction (never the
  reverse of `adir`) that minimises the squared distance to `gtx`/`gty`,
  ties broken **up > left > down > right**:
  - Bruiser: target = player tile.
  - Pixie: player tile + 4 tiles along the player's direction.
  - Ivy: `2 * (pivot - bruiser)` where `pivot` = player tile + 2 ahead.
  - Sable: player tile while ≥ 8 tiles away (squared ≥ 64), else its corner.
  - **Up-quirk**: when the player faces up, "ahead" is also displaced 4
    (Pixie) / 2 (Ivy) tiles to the **left** — the arcade's signed-overflow
    behaviour, reproduced deliberately.
- **Squares table** `sqtab` (0-31, 16-bit) built at startup; distances are
  16-bit compares, never `bmi`.
- **Phase table** `phtab`: seven scatter/chase spans per level group
  (1, 2-4, 5+), in ticks. Every phase change forces a reversal.
- **Randomised scatter openings.** During the *first* scatter phase of each
  board, ghosts choose randomly among legal directions instead of by target
  — the property that kills pattern play. Seeded from `rndstate`, which is
  stirred by the player's key timing.
- **No upward turn** on tile code 6.
- **Cruise elroy**: `dotsleft <= elroy1` → Bruiser +5 %, `<= elroy2` → +10 %.
- **House schedule**: per-ghost dot counters and a global release timer, so
  they leave staggered, never together.
- **Frightened**: reverse, blue palette, random direction at junctions,
  frightened speed class; flashing over the last 2 seconds; per-board
  durations from `frtab`, with late boards at zero (score only).
- **Eaten**: `astate` = 5, eyes-only shape, direct route home at high speed,
  revive in the house, re-enter.

**Task 6 verify:** `c64 mem read gtx 8` after `c64 until ghostai` shows the
four targets differ from each other in chase; forcing `phase` to a scatter
index makes all four head for distinct corners.

---

## 7. Fruit (`fruit.s`)

Actor 5. Enters from a randomly chosen tunnel mouth, seeks a waypoint list
(`frroute`: tunnel → house lap → the other tunnel) with the same
direction-choose routine the ghosts use, then leaves and disappears.
Two fruits per board, at `dotsleft` thresholds. Value ladder
100/200/500/700/1000/2000/5000; boards 1-7 fixed, board 8+ random pick.

**Task 7 verify:** `c64 until tick` sampling `axhi+5` shows the fruit
crossing the playfield and `sprena` bit 5 clearing when it exits.

---

## 8. Scoring, lives, progression (`hud.s`)

- `score` — 6 decimal digits, one per byte, most significant first.
- Dot 10, energizer 50, ghosts 200/400/800/1600 within one frightened
  period (`ghcombo` resets on each energizer).
- Extra life at 10 000, once (`extradone`).
- Board advances when `dotsleft` hits 0; `board` increments; maze rotation
  1,1,2,2,2,3,3,3,3,4,4,4,4 then 3,4 alternating every four boards.
- `lives` = 3 at start; game over → high-score check → attract.

**Task 8 verify:** `c64 test run` steps asserting `score` digits after a
scripted eat sequence, and `lives` decrementing on a scripted death.

---

## 9. Attract mode and the demo player (`attract.s`)

- Title screen: the game name in large glyphs (2×2 cells per letter), the
  cast introduced by name with their sprites, the top-5 score table.
- **Self-playing demo** runs the *real* engine with `demoai` substituted for
  the `$CB` read: at each centre it scores the legal directions by
  dot proximity and ghost danger and writes `awant`. Any key returns to the
  title.
- Hidden keys `1`/`2`/`3` on the title only → acts 1/2/3, then back.

**Task 9 verify:** `c64 until tick --count 600` from the title with no keys
held shows `score` non-zero — the demo is really playing.

---

## 10. Intermission acts (`acts.s`)

Three scripted scenes, each a table of `(tick, actor, field, value)` steps
plus per-scene music. After boards 2, 5 and 9; act 3 repeats every fourth
board after that. SPACE skips.

**Task 10 verify:** from the title, `c64 key type 1`, then `until tick` and
watch `$D000`/`$D002` diverge and converge; capture `evidence/act1.png`.

---

## 11. Sound (`sound.s`)

- 25 shadow bytes at `sidshad` mirroring `$D400-$D418`; **every** SID write
  goes through `sidput` (A = value, X = register offset) so the shadow can
  never drift.
- Music: three voice tracks, each a list of `(note, duration)` with a
  pattern/order layer. `mustick` advances one row per N ticks.
- Effects claim a voice by priority (`vprio` per voice): death > ghost-eaten
  > fruit > energizer siren > munch > music. A claim records the owner and
  releases it on expiry — the bug this guards against is a voice an effect
  takes and never gives back.
- Waveforms: pulse with swept PW (lead), triangle (bass), sawtooth
  (harmony), noise (munch/death); filter used on the siren and the death
  spiral.

**Task 11 verify:** `c64 audio capture` against `evidence/audio/*.score.yaml`
written from the sequencer tables; the report must pass, and the piano roll
must show three voices with no voice stuck on.

---

## 12. Evidence, tests, packaging

- `evidence/`: title, maze1-4, scatter, chase, frightened, eyes, fruit
  mid-lap, act1-3, death, game over, hi-score entry, SID shadow mid-tune.
- `evidence/audio/`: title tune, act 1-3, and a play capture holding the
  siren against the munch alternation — five artifacts each.
- `test.yaml`: deterministic regression spec — `$D015` enables, maze/dot
  state in screen RAM, score, lives, non-zero SID shadows.
- `c64 package demos/ms-muncher/ms-muncher.s -o demos/ms-muncher/ms-muncher.d64 --title "MS MUNCHER"`.

**Task 12 verify:** `c64 test run demos/ms-muncher/test.yaml` passes, and
`x64sc -ntsc demos/ms-muncher/ms-muncher.d64` autostarts.

---

## 13. The improvement loop

`AUDIT.md` logs numbered iterations: evaluate (every spec bullet PASS/FAIL
with evidence from the running game), review (cycle counts on the per-tick
update, dead code, feel), improve, re-verify. Loop until an iteration ends
with every bullet PASS and nothing worth fixing.
