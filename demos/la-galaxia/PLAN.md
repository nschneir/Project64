# La Galaxia — implementation plan

The plan `PROMPT.md` asks for, written before any code and updated as the
running machine corrected it. Every task names the observation that proves
it; nothing here is counted done from reading the source.

Conventions: addresses are hex, `$` prefixed. "cell" = one 8×8 character
position. "object" = one thing the sprite multiplexer may have to show.
"slot" = one of the 48 entries in the enemy structure-of-arrays. All verify
commands assume `.venv/bin/c64` from the repository root and a session named
`lg`.

Revision log lives at the bottom: every place the running machine corrected
this plan is recorded there rather than silently edited away.

---

## 0. Memory map, and the one place `PROMPT.md` is wrong

`PROMPT.md` §10 puts the custom character set at `$1800-$1FFF` and argues
that it must go there because "in VIC bank 0 the chip sees character ROM at
`$1000-$1FFF`". The premise is right and the conclusion inverts it: the VIC's
charset base is a 2 KB-aligned pointer, and in bank 0 the bases `$1000` *and*
`$1800` both select the character-ROM image — the chip cannot see RAM at
either. A charset at `$1800` is invisible; the screen draws ROM glyphs.

So the charset goes to `$3800`, the last 2 KB base in bank 0 that is real
RAM. **Task 0 proves this on the machine rather than by argument** — the
correction is only allowed to stand if the machine agrees.

Everything else in §10 survives, with the engine moved above the VIC bank so
the whole of `$2000-$3FFF` can be sprite and charset data.

| Range | Contents | Placed by |
|---|---|---|
| `$0801-$080C` | BASIC stub `10 SYS 2061` | `EXEHDR` |
| `$080D-$1FFF` | startup, IRQ install, trajectory LUTs, music data | `MAIN` (filled) |
| `$2000-$37FF` | sprite shapes — 96 blocks, numbers 128-223 | area `SPRITES` |
| `$3800-$3FFF` | the character set (2 KB, 256 glyphs) | area `CHARS` |
| `$4000-$8FFF` | engine: all game code, variables, SID shadow | area `ENGINE` |
| `$0400-$07E7` | screen matrix — playfield, bezel, HUD | VIC |
| `$07F8-$07FF` | sprite data pointers | VIC |
| `$D800-$DBE7` | colour RAM | VIC |

`$D018` = `$1E` (screen `$0400`, charset `$3800`); it reads back `$1F`
because bit 0 is unused and reads 1.

**KERNAL stays banked in (`$01` = `$37`) and is never called.** `PROMPT.md`
§10 offers `$E000-$FFFF` in exchange for banking it out; the exchange buys
nothing here, because the engine already fits below `$9000` and the audio
engine is code like any other. What the choice really decides is who
maintains `$CB`, and the answer is nobody either way: the game installs a
raster IRQ and **disables the CIA#1 timer IRQ**, so the KERNAL's keyboard
scan never runs. `$CB` is therefore a byte the game only ever reads, and a
value `c64 key hold` pokes there persists until something else pokes it —
which is exactly the property §13 needs, reached without giving up the ROM.
The consequence for the evidence protocol is that nothing in the machine
clears `$CB` — only the tool does. `c64 key hold` releases by default, poking
64 itself after the final tick, so the `c64 mem write '$CB' 64` every capture
still issues is a second poke of the same value: idempotent, and kept so the
protocol reads correctly without knowing the flag's default.

The ceilings are enforced at link time, not by hoping:

```asm
.import __MAIN_LAST__, __SPRITES_LAST__, __CHARS_LAST__, __ENGINE_LAST__
.assert __MAIN_LAST__    <= $2000, error, "MAIN ran into the sprite blocks"
.assert __SPRITES_LAST__ <= $3800, error, "sprites ran into the charset"
.assert __ENGINE_LAST__  <= $9000, error, "engine ran past $9000"
```

**Task 0 verify.** A probe program that patches one glyph at `$1800` and the
same glyph at `$3800`, run twice: `c64 screen --png` shows the ROM glyph in
the first case and the patched glyph in the second. Then
`c64 build demos/la-galaxia/la-galaxia.s --area 'SPRITES=$2000:$1800'
--area 'CHARS=$3800:$0800' --area 'ENGINE=$4000:$5000'` succeeds and
`c64 mem read '$3800' 8` after a run matches `chars.inc`'s first glyph.

---

## 1. Files

| File | Holds |
|---|---|
| `la-galaxia.s` | load address, stub, equates, startup, the state machine, includes |
| `vars.s` | every mutable byte, one label per test-visible value |
| `screen.s` | row tables, the cell pointer, text without CHROUT, bezel |
| `chars.s` + `chars.inc` | the charset installer and the original glyphs |
| `sprites.s` + `sprites.inc` | shape placement helpers and the stored art |
| `stars.s` | the three-layer parallax starfield, by glyph rotation |
| `mux.s` | the Y-sort, the raster event chain, `mux_count`/`mux_overflow` |
| `formation.s` | the 40-slot grid in character RAM, breathing, the handoff |
| `waves.s` + `traj.inc` | entrance waves and the trajectory LUT player |
| `enemy.s` | the per-frame enemy update, dive AI, escorts, transforms |
| `player.s` | the fighter, the Dual Fighter, capture and rescue |
| `shots.s` | player missiles and enemy bullets, in character space |
| `collide.s` | coordinate collision — grid, sprites, beam |
| `stage.s` | stage flow, difficulty tiers, the challenging stages |
| `hud.s` | `PUNTOS`, `RECORD`, `NAVES`, `ETAPA`, panels, extra lives |
| `title.s` | the attract screen and the hidden stage-select keys |
| `sound.s` | the three-voice player, the shadow block, the effects |
| `text.inc` | every Spanish string, as screen codes |
| `tools/charset.txt` | ASCII art → `chars.inc` via `c64 charset encode` |
| `tools/sprites.txt` | ASCII art → `sprites.inc` via `c64 sprite encode` |
| `tools/gentraj.py` | velocity tables + entrance/dive paths → `traj.inc` |
| `tools/genmusic.py` | the score source → `music.inc` **and** the reference score YAML |
| `tools/evidence.sh` | re-runs the proof protocol, rewrites `evidence/` |
| `tools/audio-evidence.sh` | re-runs the audio captures against their scores |

---

## 2. Input (`player.s`)

Three sources folded into one `input_state` byte, read by everything
downstream and by nothing else.

| Bit | Meaning |
|---|---|
| 0 | left | 1 | right | 2 | fire (edge-detected against `input_prev`) |
| 3 | start 1P | 4 | start 2P | 5-7 | unused |

`stage_select` holds 0, or 1-10 when a digit was seen on the title screen.

Three decoders, each taking the raw port byte in `A` and returning
normalized bits, so each is callable in isolation:

| Routine | Source | Driven from the CLI by |
|---|---|---|
| `keydecode` | `$CB`, the current-key byte | `c64 key hold` |
| `matdecode` | the matrix scan (`$DC00` row select, `$DC01` columns) | not drivable — proved by `c64 call` |
| `joydecode` | joystick port 2, CIA1 port A | not drivable — proved by `c64 call` |

Order in `readinput`: matrix scan first (rows driven), then `$DC00` = `$FF`
and the joystick sample, then `$CB`. A frame in which the stick reports a
direction wins over the matrix on the same lines.

Matrix codes: `A` 10, `D` 18, SPACE 60, `X` 23; digits `1`-`0` are
56, 59, 8, 11, 16, 19, 24, 27, 32, 35. **Starts are SPACE (1P) and `X`
(2P)** — F1/F3 do not reach VICE reliably from a Mac keyboard, so their
matrix row is no longer scanned; their `$CB` codes 4 and 5 are still
decoded so older driving scripts keep working. SPACE doubles as fire,
which is safe: IN_ST1 acts only in the title state and fire is
edge-triggered, so the starting press launches nothing.

**Task 2 verify.** `c64 call joydecode --a '$6F'` (left, no fire) then
`c64 mem read input_state 1` reads bit 0 set and nothing else;
`c64 call joydecode --a '$77'` reads bit 1. `c64 key hold a --at tick
--frames 30` moves `plx` left by 45 (1.5 px × 30) and no other byte.

---

## 3. Rendering forty enemies on eight sprites

### 3.1 The settled grid is character RAM (`formation.s`)

Each settled enemy is a 2×2 block of custom glyphs written into `$0400` and
coloured per cell in `$D800`. Settled enemies cost no sprite. Grid geometry:

| | |
|---|---|
| playfield window | screen columns 8-31 (24 wide), rows 0-24 |
| formation rows | 5, at screen rows 3, 5, 7, 9, 11 (2 cells tall each) |
| row widths | 4, 8, 8, 10, 10 enemies |
| column pitch | 2 cells nominal, redrawn at 2 cells ± the breathe step |

Slot *n* → (row, index-in-row) by a 40-entry table; the row's left edge is
computed so the row stays centred as the pitch changes.

### 3.2 A diver is a hardware sprite

`enemy_state`: 0 dead, 1 grid, 2 entering, 3 diving, 4 returning, 5 docked
(a captured fighter riding a Flagship). States 2-5 are sprite objects,
state 1 is a character block. The transition routine `tosprite`/`togrid`
does the erase and the spawn **in the same call**, so no frame can observe
an enemy as both or neither.

**Task 3.2 verify.** `c64 break add tosprite`, `c64 wait --break`,
`c64 finish`, then `c64 screen --codes` shows the block gone and
`c64 sprite status` shows the sprite enabled — one stop, both observations.

### 3.3 The starfield is a character layer (`stars.s`)

Three star glyphs, each a sparse bitmap. Every frame each glyph's 8 bytes
are rotated down by 1, 1-every-2-frames, and 1-every-3-frames respectively,
which scrolls three parallax layers for ~40 cycles a frame and leaves
`$D011`/`$D016` free for the formation. The star cells are laid into the
playfield window once at stage start and never redrawn.

### 3.4 The multiplexer (`mux.s`)

Objects: the fighter(s), every enemy in states 2-5, the tractor beam, the
explosions. Sprites 0-1 are the fighter pair and never multiplexed; sprites
2-7 carry everything else, six registers deep.

Per frame, inside the tick:

1. Gather active objects into `mux_y[]`, `mux_x[]`, `mux_xh[]`, `mux_shape[]`,
   `mux_col[]` (max 24).
2. Insertion-sort an index array by Y.
3. Walk the sorted list assigning hardware sprite `2 + (i mod 6)`. Object *i*
   is displayable only if `y[i] - y[i-6] >= 21`; otherwise it is dropped and
   `mux_overflow` counts it.
4. Emit the raster event chain: one `MUXEVT` per displayed object at
   `y - 3`, merged with the two `$D016` sway events of §7 and the tick event.

`mux_count` = objects displayed, `mux_overflow` = objects dropped. Both are
exported labels.

**Task 3.4 verify.** During an entrance wave overlap (two groups of 8 in
flight) `c64 until tick --count N; c64 mem read mux_count 2` reads ≥ 16 and
`mux_overflow` = 0; `c64 sprite status` shows `$D015` = `$FF`.

---

## 4. Colour, the window and the bezel (`screen.s`)

Playfield columns 8-31. Columns 0-7 and 32-39 are bezel and HUD, drawn as
charset cells — the border register is a fixed width and cannot mask
columns. `$D020` = `$D021` = black; `$D020` is also the §11 timing band, so
the border is black *between* ticks and coloured *during* them.

| Element | VIC-II |
|---|---|
| background / border | `$00` black |
| fighter | `$01` white, accent overlay `$03` cyan |
| Flagship | `$03` cyan, damaged `$04` purple |
| Sentinel | `$02` red |
| Drone | `$07` yellow |
| tractor beam | multicolour, `$03` cyan |
| shared multicolour `$D025`/`$D026` | `$06` blue / `$02` red — chosen once for the whole cast |

Enemy character blocks are multicolour text (`$D016` bit 4), sharing
`$D022`/`$D023` with the same blue/red pair so a settled enemy and a diving
one are the same three colours.

**Task 4 verify.** `c64 mem read '$D020' 2` masked to 4 bits reads 0/0 with
the machine stopped outside the tick; `c64 screen --png --border` shows the
bezel columns and a 24-column playfield.

---

## 5. Sprites and the budget (`sprites.s`)

16×16 art centred in the 24×21 box, so the sprite coordinate and the art
coordinate never drift. Hires for the fighter, multicolour for everything
else.

| Blocks | Shape |
|---|---|
| 128-129 | fighter, fighter accent overlay (hires) |
| 130-133 | fighter capture spin, 4 frames |
| 134-137 | Drone, 2 frames; Sentinel, 2 frames |
| 138-141 | Flagship, 2 frames; Flagship with beam, 2 frames |
| 142-145 | tractor beam cone, 4 frames |
| 146-148 | the three transformed mini-enemies |
| 149-152 | explosion, 4 frames |
| 153 | captured fighter turned enemy |

Sprite 0 = fighter (or left fighter when dual); sprite 1 = accent overlay,
**dropped while dual** and reused as the right fighter; sprites 2-7
multiplexed.

Missiles and enemy bullets are **character-space objects**, never sprites
(§6.5). Collision is coordinate math, never `$D01E`/`$D01F` — under
multiplexing one hardware sprite is a different object per band, so the
latches cannot name the enemy that was hit.

**Task 5 verify.** `c64 sprite png 0 -o /tmp/f.png` shows the fighter;
during a Dual Fighter, `c64 sprite status` shows sprites 0 and 1 at equal Y
and X differing by exactly 16.

---

## 6. Rules and stage flow

### 6.1 The grid
40 enemies: row 1 = 4 Flagships, rows 2-3 = 16 Sentinels, rows 4-5 = 20
Drones. `MAX_ENEMIES` = 48; slots 40-47 hold transform trios and the
captured fighter.

### 6.2 Entrance waves (`waves.s`)
Five groups of eight. A group launches on a timer and the next launches
before the previous settles, so up to 16 objects are in flight — which is
also what proves §3.4's 16-object requirement in ordinary play.

Trajectories come off `traj.inc`, generated by `tools/gentraj.py`:

| Table | Shape |
|---|---|
| `vx0/vy0`, `vx1/vy1`, `vx2/vy2` | 64-entry signed 16-bit velocity pairs, at 2.0, 2.3 and 3.0 px/frame |
| `path0`-`path4` | `(angle, frames)` run-length pairs, `$FF`-terminated |
| `divepath0`-`divepathN` | the same shape for dives |

Position integration is a 16-bit add of a table entry — no multiply, no
divide, no trigonometry in the frame. When a path ends the enemy homes to
its slot at fixed speed, snapping inside a 2-pixel tolerance.

Entrants are live targets and score their diving value; the stage proper
begins when the last surviving entrant settles.

### 6.3 Tractor beam, capture, rescue (`player.s`, `enemy.s`)
A Flagship dives, halts above the fighter, and deploys the beam (a
multicolour sprite pinned below it, 4 animation frames). Beam ∩ fighter →
capture: control lost, spin animation, fighter drawn up and docked above the
Flagship in slot 47, one life lost, game over if it was the last.

- Flagship destroyed **in flight** while carrying → rescue → Dual Fighter
  (two sprites, equal Y, 16 px apart, two missiles per volley, four in
  flight).
- Flagship destroyed **in the grid** while carrying → the captured fighter
  becomes an enemy that dives and fires.
- A hit while dual costs one fighter and one life; play continues single.

### 6.4 Progression (`stage.s`)
Challenging stage ⟺ `stage mod 4 == 3`. `stage` is one byte and **clamps at
255**.

| Tier | Behaviour |
|---|---|
| 1-2 | base speed, singles and pairs, 2 slow bullets |
| 3 | challenging: 40 scripted sweeps, never fire, 100/hit, 10 000 for all 40, `¡PERFECTO!`, result panel |
| 4-6 | transforming enemies, dive speed ×1.15 |
| 7 | challenging, faster sweeps, different paths |
| 8-10 | multi-shot dives, escorts (two Drones flanking a Flagship) more often |
| 11+ | speed and bullet rate clamp at maximum |

`difftab` is a table indexed by tier, not a chain of comparisons, so stage
255 reads the same row as stage 11.

### 6.5 Shots (`shots.s`)
Player missiles: 2 in flight (4 dual), 4.0 px/frame = half a cell, two glyph
phases. Enemy bullets: 2 at stages 1-2 rising to 8 from stage 8, 2.0 px/frame
rising to 3.0, same two phases. Both live in character RAM inside the
playfield window; both are erased and redrawn against a per-cell background
table so a shot crossing the starfield does not eat a star.

**Task 6 verify.** With the stage select, `c64 key hold 3 --at tick` from the
title starts stage 3; `c64 mem read stage 1` = 3, `c64 mem read enemy_state
40` shows 40 live entries and `bullets_live` stays 0 for the whole sweep.

---

## 7. Timing (NTSC, 60 Hz)

One game tick per frame from the `$D012` interrupt; nothing outside the tick
moves the world. All positions are 8.8 fixed point; the integer coordinate is
derived for the VIC each frame.

| Quantity | 8.8 value |
|---|---|
| player speed 1.5 px/f | `$0180` |
| player missile 4.0 px/f | `$0400` |
| enemy dive base 2.0 px/f | `$0200` (×1.15 → `$024C`) |
| enemy bullet 2.0 → 3.0 px/f | `$0200` → `$0300` |
| formation breathe | 128 frames, full expand-and-contract |

Breathing has two halves, and they use different mechanisms on purpose:

- the **rigid sway**, ±7 px, is `$D016`'s fine-scroll bits under a raster
  split confined to the formation band (rasters 74-146), so the HUD and the
  bezel do not move;
- the **expansion**, ±1 cell of column pitch, is a redraw of the grid at a
  new pitch, one formation row per frame, so it costs ≤ 40 cells against the
  64-cell budget of §11.

**Task 7 verify.** `c64 until tick --count 60` with `A` held moves `plx_hi`
by exactly 90 (1.5 × 60), never alternating 1 and 2. `c64 mem read
breathe_phase 1` cycles 0→127→0 over 128 ticks.

---

## 8. Scoring (`hud.s`)

`score` is 24-bit binary, rendered to decimal by `hud.s`. Values are a table
indexed by `(type, in-grid?)`, not scattered constants:

| Target | grid | flight |
|---|---|---|
| Drone | 50 | 100 |
| Sentinel | 80 | 160 |
| Flagship | 150 | 400 |
| Flagship carrying a fighter | 150 | 800 |
| transformed enemy | — | 160 (1 000 per trio) |
| captured fighter turned enemy | — | 1 000 |
| challenging-stage enemy | — | 100 (10 000 for all 40) |

Extra lives at 20 000, 70 000, and every 70 000 after, from `extratab` with
a `dip_extra_life` selector byte.

**Task 8 verify.** `c64 mem write score` to just under a threshold,
`c64 until tick --count 1`, `c64 mem read lives 1` shows the award. Each
score value is proved by reading `score` before and after a staged kill.

---

## 9. Sound (`sound.s`, `tools/genmusic.py`)

25-byte shadow block at `sidshad`; **every** SID write goes through
`sidput` (A = value, X = register offset) so the shadow cannot drift.

Voice 1 lead / laser (priority 2), voice 2 harmony / dive whine / beam hum
(priority 1), voice 3 bass-noise / explosion / grid march (priority 3). An
effect seizes a voice when its priority ≥ the current holder's; a lower one
is dropped, never queued. The music sequencer keeps running silently under a
seized voice and resumes at the position it would have reached.

### The title theme
A written piece, not a loop: 1960s sci-fi scoring played by a mariachi band
on acid. Trumpet lead in parallel thirds and sixths, *guitarrón* bass in
twos, off-beat *vihuela* chop, 6/8-against-3/4 *sesquiáltera*, *grito* rips,
theremin-ish portamento and whole-tone slides, tritone turns, pulse-width
drift, ring modulation and hard sync on the seasick bars.

| | |
|---|---|
| row | one eighth note, 6 frames — 10 rows/s |
| bar | 6 rows (6/8), or 6 rows read as 3/4 for the *sesquiáltera* bars |
| length | ≥ 600 rows ⇒ ≥ 60 s before it repeats |
| form | intro · A · A′ · B (whole-tone drift) · C (*sesquiáltera*) · A″ · coda-into-intro |

**Seamlessness is compositional.** The coda's last bar is the dominant of
the intro's first, the lead hands the line over across the seam without a
leap, and the loop resets every voice's gate, envelope, pulse width and
vibrato index to the state bar 1 expects. `tools/genmusic.py` emits both
`music.inc` and the reference score YAML from one source, so the score
cannot drift from the data — and it refuses to emit a piece whose seam bar
does not resolve into bar 1.

**Task 9 verify.** `c64 audio capture` at the title against the generated
score passes; the seam capture (poke `mus_order`/`mus_row` to a few rows
before the end, capture across it) passes as one continuous phrase, and the
piano roll shows no voice gating off at the seam. Effects: `c64 mem read
sidshad 25` at a laser shot, an explosion and a beam hum shows the waveform
and envelope bytes §9 names on the voices it names.

---

## 10. Data structures

Structure of arrays, `MAX_ENEMIES` = 48, so every field is an `LDA abs,X`:

```
enemy_state  enemy_type   enemy_x_lsb  enemy_x_msb  enemy_y
enemy_path   enemy_pathix enemy_pathct enemy_hp     enemy_flags
enemy_slot   enemy_frac_x enemy_frac_y enemy_shape  enemy_col
```

`enemy_flags`: b7 carries a captured fighter, b6 transformed, b5 escort of a
Flagship, b4 challenging-stage sweeper.

---

## 11. Performance

- One tick per frame, from `$D012`.
- ≤ 64 changed cells redrawn per frame outside a stage transition;
  `cells_drawn` is a counter the audit reads.
- No ROM calls in the tick; no multiply, divide or trigonometry.
- Collision resolves inside the tick, before the multiplexer's first
  reposition IRQ of the next frame — the tick runs at the bottom of the
  frame and the first mux event is above it.
- `$D020` gets `COLOR_RED` at the top of the tick and black at the end. The
  band's length *is* the tick's cost; `c64 screen --png --border` is the
  evidence.
- `c64 profile enemyupdate` records the measured cost of the per-frame
  enemy update in `AUDIT.md`.

**Task 11 verify.** `c64 profile enemyupdate` with 16 objects live returns a
cycle count recorded in the audit; `evidence/raster-time.png` shows the band
ending well above the bottom of the screen.

---

## 12. Evidence, tests, packaging

`evidence/`: `title`, `entrance`, `formation`, `dive`, `tractor-beam`,
`dual-fighter`, `flagship-damaged`, `stage-select`, `transform`,
`challenging-stage`, `perfect-bonus`, `raster-time`, `game-over` — plus
`formation.codes.txt`, `sid-shadow.txt` and `mux.txt`.
`evidence/audio/`: title opening, laser + explosion, tractor beam, and the
loop seam — five artifacts each, every report passing.

`test.yaml` asserts `$D015`, the settled formation in screen RAM, `score`,
`lives`, `stage` after a stage-select start, and non-zero SID shadows.

`c64 package demos/la-galaxia/la-galaxia.s -o demos/la-galaxia/la-galaxia.d64
--title "LA GALAXIA"` with the three `--area` flags.

**Task 12 verify.** `c64 test run demos/la-galaxia/test.yaml` passes and the
run command `c64 package` prints autostarts in stock VICE.

---

## 13. The improvement loop

`AUDIT.md` logs numbered iterations: **evaluate** (walk every claim in
`PROMPT.md`, PASS/FAIL with evidence from the running game), **review**
(cycle counts on the tick and the multiplexer, dead code, feel), **improve**,
**re-verify**. Loop until an iteration ends with every claim PASS and a
review that finds nothing worth fixing.

The audit's evidence section lists the hidden stage-select digits
explicitly, and says which captures used them.

---

## Revision log

Entries are added as the running machine corrects the plan.

**R1 — the charset base (Task 0, confirmed).** A probe copied the ROM
charset to *both* `$1800` and `$3800`, patched screen code 1 to a solid
`$FF` block in both copies, and put four code-1 cells on row 0. With
`$D018` = `$16` (base `$1800`) the machine drew four lowercase **a**'s —
the character ROM's second half, which is what the VIC sees at `$1800` in
bank 0. With `$D018` = `$1E` (base `$3800`) it drew the solid block. The
RAM at `$1800` is invisible to the chip, exactly as §0 predicted and
opposite to `PROMPT.md` §10. The charset lives at `$3800`.

**R2 — area fill (Task 0, confirmed).** `c64 build --area` fills every
region *below* the last one, and leaves the last one at its real length.
`SPRITES=$2000:$1800 CHARS=$3800:$0800 ENGINE=$4000:$5000` therefore costs
a flat 14,342 bytes of padding plus the engine's own size — *corrected
2026-08-10: rebuilt at 14,337 (2 + `$4000`-`$0801`); the figure recorded here
was wrong and reached task-10's brief* — and the labels
land where they say (`__SPRITES_LOAD__` = `$2000`, `__CHARS_LOAD__` =
`$3800`, `__ENGINE_LOAD__` = `$4000`). MAIN's `$0801-$1FFF` would be
padding either way, so the trajectory LUTs and the music data are placed
there and the padding does real work.

**R3 — the raster chain could fire EV_FRAME mid-frame.** When two events
sat within ~3 raster lines, the first event's handler wrote the second's
line into `$D012` and then found the beam already past it, so it dispatched
the second inline — but the beam crossing the just-written compare line had
re-latched the raster IRQ. The RTI re-entered immediately with `evidx`
parked at 0, and EV_FRAME ran mid-frame: `vblcount` double-counted (a
phantom `tick_overrun` of ~27,000 cycles that were never spent), `tickpend`
ran the next tick early in the same frame, and the whole event list was
replayed inline mid-screen. Caught with a store watchpoint on `vblcount`
firing at raster line 150. Fix: ack `$D019` again at `irqexit`, after all
inline dispatches — the final `$D012` write is guaranteed ≥ 2 lines ahead
by the guard, so nothing legitimate can have latched. Every overrun
measurement taken before this fix is suspect, including the one that said
a 16-object entrance cannot fit.

**R4 — the timing band is a toggle.** `$D020` red-at-tick-top read as
tearing at the top and bottom of the border on a real display, so the band
is gated on an exported `rasterband` byte, default 0. The evidence capture
for `raster-time.png` pokes it to 1 first.

**R5 — sfxstart clobbered X.** It indexed its tables with `tax`, and two
callers keep their slot in X across the call: the tractor-beam deploy
inside enemytick's loop (the walk restarted at slot 2 and double-moved
everything after it for a frame) and pickdive's escort branch (it read
slot 1's type whatever dived). sfxstart now preserves X.

**R6 — a shot-down fighter never ended the game.** `ptdying` cleared
`plstate` but not `plalive`, so the play state never saw the death and the
fighter respawned in place — at zero lives a bullet or a ram could never
reach JUEGO TERMINADO; only a capture could. `ptdying` now clears both.
