# Snake — implementation plan

Ordered, independently verifiable steps for `demos/snake/PROMPT.md`. Each
task names the *interfaces* it introduces — labels, variables, memory
addresses — and one command that proves it on the running machine. No code
bodies: the source is the code.

Everything is driven `--warp --headless`, input injected as the held-key
matrix code at `$CB`, and every sample anchored on a `c64 until mainloop`
stop.

---

## Architecture

One `.prg` at `$0801` with the standard `10 SYS 2061` stub, assembled from
`snake.s` which `.include`s the rest. Character graphics only — screen RAM
`$0400` + colour RAM `$D800`, hires custom charset at `$3000`. No sprites,
no bitmap, no raster IRQ.

### Files

| File | Holds |
|---|---|
| `snake.s` | load address, BASIC stub, `start`, `mainloop`, state dispatch, `.include`s |
| `vars.s` | every BSS variable and every RODATA table (the tables below) |
| `chars.txt` | ASCII-art glyph sheet, input to `c64 charset encode --hires` |
| `chars.inc` | generated `.byte` rows (`glyphs:` … `glyphs_end:`) — committed |
| `chars.s` | `charsinit`: ROM charset → `$3000`, patch codes 128-139, set `$D018` |
| `screen.s` | `plotaddr`, `putstr`, `putdig`, `clrscr`, `fillcol` — drawing primitives |
| `title.s` | `drawtitle`, `drawover`, big-letter renderer `bigchar` |
| `play.s` | `newgame`, `drawfield`, `drawhud`, `steer`, `movesnake`, `eat`, `died`, `newfood`, `levelup`, `recolor` |
| `sound.s` | `sidzero`, `sidput`, `sfxeat`, `sfxdie`, `sfxoff` |
| `test.yaml` | the deterministic regression spec |
| `tools/evidence.sh` | re-runs the whole evidence protocol into `evidence/` |

`.include`d files each open with an explicit `.segment` (ca65 segment state
leaks across includes).

### Memory map

| Range | Use |
|---|---|
| `$0801-$080C` | BASIC stub (`10 SYS 2061`) |
| `$080D-…` | CODE + RODATA + DATA. Must end below `$3000` — checked every build |
| `$3000-$37FF` | RAM character set (VIC bank 0, `$D018` = `$1C`, reads back `$1D`) |
| BSS | variables + the 512-byte body ring (see table) |
| `$0400 / $D800` | screen / colour RAM |
| `$FB/$FC` | `PTR` — screen pointer (`plotaddr`) |
| `$FD/$FE` | `CPTR` — colour pointer / charset copy destination |

### Screen layout

| Rows | Use |
|---|---|
| 0 | HUD: `SCORE 0000` at col 1, `LEVEL 1` at col 17, `HI 0000` at col 30 |
| 1 | top border (corners at cols 0 and 39) |
| 2-23 | playfield interior, cols 1-38 — 22 × 38 = 836 cells |
| 24 | bottom border |
| cols 0, 39 | side border, rows 1-24 |

### Glyph allocation (custom charset, hires)

Contiguous from screen code 128 so collision dispatch is a range test. Codes
128-255 are the ROM's reverse-video half — nothing the HUD or title uses.

| Code | Glyph | Colour |
|---|---|---|
| 128 | border horizontal | `bordcol` |
| 129 | border vertical | `bordcol` |
| 130 | border corner, top-left | `bordcol` |
| 131 | border corner, top-right | `bordcol` |
| 132 | border corner, bottom-left | `bordcol` |
| 133 | border corner, bottom-right | `bordcol` |
| 134 | snake head facing up | `lvcolor[level]` |
| 135 | snake head facing down | `lvcolor[level]` |
| 136 | snake head facing left | `lvcolor[level]` |
| 137 | snake head facing right | `lvcolor[level]` |
| 138 | snake body segment | `lvcolor[level]` |
| 139 | food (apple) | `FOODCOL` = 2 (red) |

The title's big letters use ROM screen code **160** (reverse space, solid
block) — unpatched, so it stays solid.

**Collision is a three-way test on the screen code of the cell being entered:**
`32` = empty, `139` = food, anything else = death. Nothing else is ever
written into the interior.

### Variables (BSS unless noted)

| Name | Bytes | Meaning |
|---|---|---|
| `gstate` | 1 | 0 = title, 1 = play, 2 = game over |
| `keycode` | 1 | `$CB` latched at the top of `mainloop` |
| `curdir` | 1 | direction of the last move: 0 up, 1 down, 2 left, 3 right |
| `newdir` | 1 | direction the next move will take (reversal-guarded) |
| `hrow`, `hcol` | 1, 1 | head cell, playfield coordinates |
| `bodylo`, `bodyhi` | 256, 256 | ring buffer of segment **screen addresses** |
| `head`, `tail` | 1, 1 | ring indices; `snlen` = live segment count |
| `snlen` | 1 | segments currently drawn (capped at 250) |
| `grow` | 1 | segments still owed from eating (tail held for this many moves) |
| `level` | 1 | 1-9 |
| `eaten` | 1 | pickups since the last level-up |
| `speed` | 1 | jiffies per move, from `spdtab[level-1]` |
| `scdig` | 4 | score, one decimal digit per byte, most significant first |
| `hidig` | 4 | high score, same encoding — initialised **once**, at `start` |
| `foodr`, `foodc` | 1, 1 | food cell |
| `seed` | 1 | Galois LFSR state, seeded from `$A2`, never zero |
| `sidshadow` | 25 | mirror of `$D400-$D418`; every SID write goes through `sidput` |
| `sfxlen` | 1 | moves until `sfxoff` gates the voice down |

### Tables (RODATA)

| Name | Size | Contents |
|---|---|---|
| `spdtab` | 9 | jiffies per move by level: `12,10,8,7,6,5,4,3,2` |
| `lvcolor` | 9 | snake colour by level: `5,13,7,3,14,10,1,12,15` |
| `rowdelta`, `coldelta` | 4, 4 | `-1/+1/0/0` and `0/0/-1/+1`, indexed by direction |
| `headcode` | 4 | `134,135,136,137`, indexed by direction |
| `bigfont` | 25 | five 5-byte bitmaps (`S N A K E`), bits 3-0 = columns 0-3 |
| `titlemsg`, `overmsg`, … | — | zero-terminated ASCII, folded to screen codes by `putstr` |

### The tick

`mainloop` runs **once per game tick, in every state**, and in state 1 one
tick is exactly one snake move — so `c64 until mainloop --count N` advances
N moves and `c64 key hold KEY --at mainloop --frames N` steers across N of
them. Order inside the tick, which the `$CB` rule fixes: latch `$CB` into
`keycode` **first**, before anything else, then dispatch on `gstate`, then
pace on the jiffy clock (`speed` jiffies in play, 4 in title/game over).

---

## Tasks

Each task ends with the machine stopped and a command whose output is the
proof. `C = .venv/bin/c64`.

### 1. Skeleton: stub, charset, empty tick

`start` zeroes BSS, seeds `seed` from `$A2`, calls `sidzero` and
`charsinit`, sets `gstate` = 0, falls into `mainloop`. `mainloop` latches
`$CB`, dispatches to a stub per state, paces 4 jiffies, loops.

**Verify:** `C run snake.s` then `C until mainloop --count 3` and
`C mem read '$D018' 1` → `1d` (charset live), and `C mem get gstate 1` → `0`.

### 2. Character set

`chars.txt` holds 12 hires glyphs as 8×8 `.#` art in code order 128-139.
`c64 charset encode chars.txt --hires --first-code 128 -o chars.inc`
regenerates `chars.inc`; `charsinit` copies `glyphs`..`glyphs_end` over
`CHARSET + 128*8`.

**Verify:** `C mem read '$3400' 8` — code 128's 8 bytes at `$3000 + 128*8`
are the border-horizontal pattern, not the ROM's reverse-`@`.

### 3. Drawing primitives

`plotaddr` (A = row, Y = col → `PTR` at screen, `CPTR` at colour RAM),
`putstr` (`PTR` set, Y = 0, zero-terminated ASCII folded to screen codes,
colour from `A`), `putdig` (a digit array → screen codes), `clrscr`,
`fillcol`.

**Verify:** a scratch call — `C call putstr` after poking a known string —
or simply the title screen in task 4, which is nothing but these.

### 4. Title screen

`drawtitle` paints `SNAKE` in code-160 blocks from `bigfont` (rows 3-7,
starting col 8, one colour per letter), `PRESS ANY KEY TO PLAY`, the
`W A S D` control hint, and the current `HI` score. Any key with
`keycode != 64` starts a game.

**Verify:** `C wait --text "PRESS ANY KEY TO PLAY"`, then
`C mem get '@3,8' 4` → `160 160 160 160` (the S's top bar), and
`C screen --png evidence/title.png --scale 2`.

### 5. Playfield, HUD, first food

`newgame` resets score/level/length/direction, draws the border box with
codes 128-133, draws the HUD, seats a 3-segment snake at row 12 col 10
heading right, and calls `newfood`. `newfood` rejects until it lands on a
cell holding code 32.

**Verify:** after starting a game, `C mem get '@1,0' 1` → `130`,
`C mem get '@12,10' 1` → `137`, `C mem get snlen 1` → `3`, and
`C mem get foodr 2` inside the interior bounds.

### 6. Movement and steering

`steer` maps `keycode` (W=9, A=10, S=13, D=18) to `newdir`, rejecting the
direct reversal of `curdir`. `movesnake` computes the new head cell, reads
its screen code, dispatches empty/food/death, draws the head glyph, demotes
the previous head to a body glyph, and erases the tail unless `grow` is
owed.

**Verify:** `C key hold d --at mainloop --frames 5` then `C mem get hcol 1`
→ 15; `C key hold w --at mainloop --frames 3` then `C mem get hrow 1` → 9.

### 7. Eating, growth, score

`eat` adds `level` × 10 points to `scdig` with carry propagation, sets
`grow` = 3, bumps `eaten`, plays `sfxeat`, and calls `newfood`.

**Verify:** poke `foodr`/`foodc` directly in front of the head, advance one
move, then `C mem get scdig 4` → `0 0 1 0` and `C mem get snlen 1` → 4.

### 8. Levels

Every 5 pickups `levelup` increments `level` (max 9), reloads `speed` from
`spdtab`, and `recolor` walks the body ring rewriting colour RAM to
`lvcolor[level-1]`.

**Verify:** poke `eaten` to 4 and feed one more pickup —
`C mem get level 1` → 2, `C mem get speed 1` → 10, and the head's colour
nybble at `$D800 + 40*hrow + hcol` → 13.

### 9. Death, game over, high score

`died` sets `gstate` = 2, plays `sfxdie`, and `drawover` paints
`GAME OVER`, `SCORE nnnn`, `HI nnnn` and `PRESS SPACE TO PLAY AGAIN`. If
`scdig` > `hidig` lexicographically, `hidig` is overwritten. Space returns
to `newgame`; `hidig` is never touched by `newgame`.

**Verify:** `C break add died`, `C mem write '$CB' 9` (or steer into the
border), `C wait --break`, then `C mem get gstate 1` → 2 and
`C wait --text "GAME OVER"`.

### 10. Sound with shadows

`sidput` (X = register offset 0-24, A = value) writes `$D400,x` **and**
`sidshadow,x`. `sidzero` clears all 25. `sfxeat` gates a short triangle
blip on voice 1; `sfxdie` gates a noise burst with a long release on voice
3. `sfxoff` runs from the tick when `sfxlen` reaches zero.

**Verify:** on the move that eats, `C mem get sidshadow+4 1` → 17
(triangle + gate) and `C mem get sidshadow+24 1` → 15 (volume).

### 11. Evidence

`tools/evidence.sh` drives the whole protocol headless+warp and writes
`evidence/title.png`, `play.png`, `levelup.png`, `gameover.png`,
`hiscore.png`, `sid.png` — each captured from a **stopped** machine.

**Verify:** `tools/evidence.sh` exits 0 and the six PNGs are non-empty.

### 12. Regression spec

`test.yaml`: title text and the block letters in screen RAM, the border and
snake codes, `SCORE`/`LEVEL` in the HUD, a scored pickup, a death, the
surviving high score across a second game, and non-zero `sidshadow`.

**Verify:** `C test run test.yaml` passes.

### 13. Package

`C package snake.s -o snake.d64 --title "SNAKE"`, and report the exact run
command it prints.

**Verify:** `C test run` a spec whose `disk:` is `snake.d64`, or boot it:
`C disk boot snake.d64` then `C wait --text "PRESS ANY KEY TO PLAY"`.

### 14. The improvement loop

Iterations logged in `AUDIT.md`: evaluate every spec bullet on the running
game, review the code (cycle-count the per-move path, judge steering
response and the speed curve), improve, re-verify. Loop until an iteration
ends all-PASS with nothing left worth fixing.
