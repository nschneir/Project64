# Invaders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A faithful C64 recreation of the 1978 arcade Space Invaders in pure
6502 assembly — custom multicolor charset formation, hardware-sprite base/shot/UFO,
the authentic one-invader-per-tick march engine, eroding shields, three bomb
flavours, the UFO shot-count secret, and three-voice SID — shipped as an
autostarting `.d64`.

**Architecture:** One `.prg` loading at `$0801` with a `10 SYS 2061` stub. All
mutable state lives in explicitly-initialised `DATA`/`BSS` arrays (never assumed
zero). The screen is a 40x25 text screen at `$0400` in **multicolor text mode**
(`$D016` bit 4) with a RAM charset at `$3000` — a copy of the ROM charset with
codes 64-95 patched to custom multicolor glyphs, so HUD letters still render
normally in hires cells (colour nybble < 8) while invaders/shields/bombs render
multicolor (nybble >= 8). Sprites 0/1/2 (base, shot, UFO) use data copied to
`$3800`. The game is a per-frame state machine paced on the jiffy clock; one
`mainloop` label is the single frame anchor every test and evidence capture uses.

**Tech Stack:** ca65/ld65 via `c64 build` / `c64 package`; VICE through the
`c64` CLI and the `c64-tools` MCP server; Python 3 (stdlib only) for the
charset ASCII-art converter in `tools/`.

## Global Constraints

- Everything for this demo lives in `demos/invaders/`.
- Pure 6502 assembly plus a BASIC `SYS` stub. No C, no BASIC gameplay code.
- Graphics: custom **multicolor character set** for invaders/shields/HUD +
  **hardware sprites** for laser base, player shot, mystery UFO.
- Controls: held `A`/`D` read from the live matrix-code byte `$CB`
  (A=10, D=18, space=60). Space fires. No GETIN in the hot path.
- Pacing: the jiffy clock (`$A2`). One game tick = one frame (60 Hz NTSC).
- **One invader moved per tick**, swept in order. Speed-up must be emergent.
- No ROM calls in the hot path (`CHROUT` only during init/title).
- Redraw only changed character cells. Never repaint the whole screen in-game.
- Every SID write is mirrored into a RAM shadow array (`sidshadow`, 25 bytes)
  — the SID is write-only and the shadow is the testable evidence.
- Sprite/charset data authored as commented `.byte` rows in source. No binary
  blobs, no committed source images. `block = address / 64` stated in comments.
- Evidence PNGs go to `demos/invaders/evidence/` at `--scale 2`, captured with
  the machine **stopped**.
- Determinism: `--warp --headless`; anchor every sample on `c64 until mainloop`.
- Ship: `c64 package demos/invaders/invaders.s -o demos/invaders/invaders.d64
  --title "INVADERS"`; report the printed run command verbatim.

---

## Screen and memory map (locked before any code)

```
$0801-$080C  BASIC stub "10 SYS 2061"
$080D-....   CODE + RODATA + DATA + BSS   (must end below $3000)
$3000-$37FF  RAM charset (2 KB, ROM copy + patched codes 64-95)
$3800-$38FF  sprite data, 4 blocks:
             $3800 block 224  laser base
             $3840 block 225  player shot
             $3880 block 226  mystery UFO
             $38C0 block 227  base explosion
$0400-$07E7  screen RAM      $D800-$DBE7 colour RAM
$07F8-$07FA  sprite pointers 0/1/2
```

Screen layout (rows 0-24):

```
row 0   HUD:  "SCORE 000000  HI 000000  WAVE 01"
row 1   blank separator
rows 2-18  play field (formation marches here)
rows 17-18 the four shields
rows 21-23 laser base sprite (y = 218)
row 24  lives: "LIVES 3"  + "PRESS A D SPACE"
```

Formation geometry:

- Invader = **2 character cells wide, 1 cell tall**; pitch 2 cells (adjacent),
  so 11 invaders span **22 columns**. Glyphs leave the outer colour-pixel blank
  on each side, giving a visible gap between neighbours.
- Row pitch **2 text rows**; 5 rows span 9 rows of screen.
- Column limits: leftmost invader column `>= 0`, rightmost invader column
  `<= 39`, i.e. formation left edge sweeps columns 0..18 (18 steps), matching
  the arcade's ~20 % of screen width of travel.
- Wave 1 top row = 2; each wave 2..9 starts one row lower (top row = wave+1);
  wave 10 resets to 2 (`topr = 2 + ((wave-1) mod 9)`).
- Baseline = row 20. Any live invader at row >= 20 ends the game.

Invader indexing: `i = rowidx*11 + colidx`, `rowidx` 0 = top.
Class by `rowidx`: 0 -> squid (30 pts), 1-2 -> crab (20), 3-4 -> octopus (10).

Charset code allocation (patched over the ROM copy at `$3000`):

```
64,65  squid   frame A left/right     70,71  crab    frame B left/right
66,67  squid   frame B left/right     72,73  octopus frame A left/right
68,69  crab    frame A left/right     74,75  octopus frame B left/right
76     shield solid        77 shield cracked      78 shield crumbling
79     bomb: slow straight (zigzag glyph frame A)
80     bomb: slow straight (zigzag glyph frame B)
81     bomb: fast straight (plunger)
82     bomb: wiggly frame A            83 bomb: wiggly frame B
84     invader explosion               85 base-baseline bar
```

Colour nybbles: multicolor cells use `8 + colour` (bit 3 enables multicolor
per cell). `$D021` = 0 black, `$D022` = 1 white (eyes), `$D023` = 8 orange
(damage speckle). Class colours (low 3 bits, so 0-7 only): squid = 3 cyan,
crab = 5 green, octopus = 2 red. Shields = 5 green. Bombs = 7 yellow.

## File structure

| File | Responsibility |
|------|----------------|
| `invaders.s` | Load address, BASIC stub, equates, `init`, `mainloop` state machine, `.include` of the rest |
| `vars.s` | Every mutable byte/array with its documented address label, plus `clearvars` |
| `chars.s` | Charset install (ROM copy + patch) and the patched glyph `.byte` rows |
| `sprites.s` | Sprite `.byte` rows, `spriteinit`, sprite helpers |
| `screen.s` | Row address tables, `plotaddr`, `putstr`, `putdec`, HUD |
| `formation.s` | Formation setup, `marchstep` (one invader per tick), draw/erase |
| `player.s` | Base movement from `$CB`, firing, shot update, shot collisions |
| `bombs.s` | Bomb spawn/update/collision, three flavours |
| `shields.s` | Shield build, erosion, damage-state redraw |
| `ufo.s` | UFO spawn/move/hit, the 23rd-shot / every-15th secret |
| `sound.s` | SID engine: shadow writes, heartbeat, four effects, priorities |
| `tools/charset.py` | ASCII-art -> `.byte` rows generator for `chars.s` glyph block |
| `tools/charset.txt` | The ASCII art source for those glyphs |
| `test.yaml` | Declarative regression test (`c64 test run`) |
| `AUDIT.md` | The numbered improvement-loop log (audits + review findings) |
| `evidence/*.png` | Captured evidence frames |

**ca65 include discipline:** every `.include`d file starts with an explicit
`.segment "CODE"` (segment state carries across includes and silently
assembles code into BSS otherwise).

## Interfaces (names every task depends on)

Zero page (see `references/zero-page.md`; these four are free user bytes):
`PTR = $FB/$FC` (screen pointer), `CPTR = $FD/$FE` (colour pointer).

Variables (in `vars.s`, all explicitly initialised by `clearvars`):

```
gstate    .byte    ; 0 title, 1 play, 2 base dying, 3 wave clear, 4 game over
tick      .byte    ; frame counter, wraps
score     .res 3   ; 6-digit BCD-ish: 3 bytes, 2 decimal digits each
hiscore   .res 3   ; survives across games (NOT cleared by clearvars)
wave      .byte    ; 1-based
lives     .byte
extradone .byte    ; 1 once the 1500-point extra life is awarded
alive     .res 55  ; 1 = invader present
icol      .res 55  ; current left column of each invader
irow      .res 55  ; current text row of each invader
nalive    .byte
sweep     .byte    ; 0..54, index of the invader moved this tick
mdir      .byte    ; $01 right, $FF left
edgehit   .byte    ; set during a sweep, consumed at sweep wrap
dropnext  .byte    ; 1 = next sweep drops a row and reverses
frame     .byte    ; 0/1 animation frame, toggled at sweep wrap
basex     .byte    ; laser base sprite X (pixels, 24..320-24)
shotact   .byte    ; 1 = player shot in flight
shotx     .byte    ; shot sprite X
shoty     .byte    ; shot sprite Y
shots     .byte    ; total shots fired this game (UFO secret counter)
bactive   .res 3   ; bomb slots: 0 = free
btype     .res 3   ; 0 slow, 1 fast, 2 wiggly
bcol      .res 3
brow      .res 3
bdelay    .res 3
ufoact    .byte    ; 0 off, 1 crossing
ufox      .byte    ; UFO X / 2 (0..170) so it fits a byte
ufodir    .byte
ufotimer  .word    ; ticks until next UFO
shdmg     .res 32  ; 4 bunkers x (4 cols x 2 rows) damage 3..0
sidshadow .res 25  ; mirror of $D400-$D418
sndprio2  .byte    ; priority of the effect owning voice 2 (0 = idle)
sndprio3  .byte    ; priority of the effect owning voice 3
```

Routines (exact names later tasks call):

```
init        ; cold start: charset, sprites, vars, title
mainloop    ; THE frame anchor — executed once per tick in every state
newgame     ; reset score/lives/wave, build wave 1
newwave     ; build the formation + shields for `wave`
marchstep   ; move exactly one invader (index `sweep`), advance `sweep`
drawinv  X  ; X = invader index -> draw its 2 cells + colour
erainv   X  ; X = invader index -> blank its 2 cells
plotaddr    ; A = row, Y = col -> PTR = screen cell, CPTR = colour cell
putstr      ; A/Y = lo/hi of a 0-terminated ASCII string, PTR preset
putdec3     ; A = byte -> three screen-code digits at (PTR),y
addscore    ; A = points/10 (so 30 pts is A=3) -> score, extra-life check
sndinit     ; zero SID + shadow, set filter/volume
sndtick     ; per-frame envelope/sweep advance
sndbeat     ; play the next heartbeat note (called at sweep wrap)
sfxshot / sfxhit / sfxboom / sfxufo / sfxufooff
sidput      ; A = value, X = register offset -> $D400,X and sidshadow,X
```

---

### Task 1: Skeleton, build plumbing, and the frame anchor

**Files:**
- Create: `demos/invaders/invaders.s`, `demos/invaders/vars.s`,
  `demos/invaders/screen.s`

**Interfaces:**
- Produces: `init`, `mainloop`, `tick`, `gstate`, `plotaddr`, `putstr`,
  row tables `rowlo`/`rowhi`.

- [ ] **Step 1: Write the skeleton** — `$0801` load address, `10 SYS 2061`
  stub, `cld`, `sei`-free init, a `mainloop` that waits on `$A2`, increments
  `tick`, and jumps back. Include `vars.s` and `screen.s`, each beginning
  `.segment "CODE"`.

- [ ] **Step 2: Prove multi-file assembly works before anything else**

```bash
.venv/bin/c64 build demos/invaders/invaders.s
```
Expected: a `.prg` and `.lbl`. A `.include` path is resolved relative to the
including file; if it is not, flatten to one file and record it as friction.

- [ ] **Step 3: Prove the frame anchor is drivable**

```bash
.venv/bin/c64 session start --warp --headless
.venv/bin/c64 run demos/invaders/invaders.s
.venv/bin/c64 until mainloop --count 10
.venv/bin/c64 mem get tick 1
```
Expected: `tick` advances by exactly 10 between two `until mainloop --count 10`.

- [ ] **Step 4: Commit** — `git add demos/invaders && git commit -m "feat(invaders): skeleton, frame anchor, screen helpers"`

---

### Task 2: Charset — ASCII art -> glyphs -> installed multicolor mode

**Files:**
- Create: `demos/invaders/tools/charset.py`, `demos/invaders/tools/charset.txt`,
  `demos/invaders/chars.s`

**Interfaces:**
- Consumes: nothing. Produces: `charsinit`, glyph block label `glyphs`,
  charset live at `$3000`, `$D018` = `$1C`, `$D016` multicolor bit set.

- [ ] **Step 1: Write `tools/charset.py`** — reads `charset.txt`: named blocks
  of 8 rows x 4 characters using the legend `.` transparent, `1` = `$D022`,
  `2` = `$D023`, `3` = cell colour; emits `.byte %xxxxxxxx  ; name row n`
  lines. It must reject any block that is not 8 rows of exactly 4 legend
  characters (that check is the invariant worth having a tool for).

- [ ] **Step 2: Author the glyphs in `charset.txt`** — 12 invader halves,
  3 shield damage states, 5 bomb frames, 1 explosion, per the code allocation
  above.

- [ ] **Step 3: Generate and paste**

```bash
.venv/bin/python demos/invaders/tools/charset.py > demos/invaders/chars.inc
```
Commit `chars.inc` (the `.byte` rows are the committed artifact) and
`.include` it from `chars.s`.

- [ ] **Step 4: Write `charsinit`** — `sei`, save `$01`, clear CHAREN bit 2,
  copy 8 pages `$D000` -> `$3000`, restore `$01`, `cli`; then patch 22 glyphs
  from `glyphs` over `$3000 + 64*8`; then `$D018` = `$1C`, `$D016` |= `$10`,
  `$D021` = 0, `$D022` = 1, `$D023` = 8, `$D020` = 0.

- [ ] **Step 5: Verify on the machine, not from the source**

```bash
.venv/bin/c64 run demos/invaders/invaders.s
.venv/bin/c64 until mainloop
.venv/bin/c64 mem read '$D018' 1        # expect $1D ($1C with bit 0 reading 1)
.venv/bin/c64 mem read '$3200' 16       # patched glyph bytes, not ROM bytes
.venv/bin/c64 screen --png /tmp/chars.png --scale 2
```
Expected: the PNG shows the test row of invader glyphs in class colours.
`c64 screen` text will NOT show them — assert with `screen --codes`.

- [ ] **Step 6: Commit**

---

### Task 3: Sprites — base, shot, UFO, explosion

**Files:**
- Create: `demos/invaders/sprites.s`, `demos/invaders/tools/sprites.txt`

- [ ] **Step 1: Author the four shapes as ASCII art** in `tools/sprites.txt`
  (12-char multicolor rows, 21 rows each, blank line between sprites).

- [ ] **Step 2: Convert with the first-class tool**

```bash
.venv/bin/c64 sprite encode demos/invaders/tools/sprites.txt > demos/invaders/sprites.inc
```

- [ ] **Step 3: Write `spriteinit`** — copy the four 63-byte shapes to
  `$3800`/`$3840`/`$3880`/`$38C0`, set pointers `$07F8` = 224, `$07F9` = 225,
  `$07FA` = 226, colours `$D027` = 7 (base yellow-green), `$D028` = 1 (shot
  white), `$D029` = 2 (UFO red), multicolor bits in `$D01C` for base+UFO,
  `$D025`/`$D026` shared colours, `$D015` = %011 (base + shot slots managed
  later).

- [ ] **Step 4: Verify**

```bash
.venv/bin/c64 until mainloop
.venv/bin/c64 sprite status
.venv/bin/c64 sprite png 0 -o /tmp/base.png
```
Expected: sprite 0 enabled, pointer 224 -> `$3800`, X/Y in visible range
(24-343 / 50-249), and the rendered PNG matches the authored art.

- [ ] **Step 5: Commit**

---

### Task 4: Formation build + the one-invader-per-tick march engine

**Files:**
- Create: `demos/invaders/formation.s`

**Interfaces:**
- Produces: `newwave`, `marchstep`, `drawinv`, `erainv`, `nalive`, `sweep`,
  `mdir`, `edgehit`, `dropnext`, `frame`.

- [ ] **Step 1: `newwave`** — for `i` in 0..54: `alive[i]=1`,
  `icol[i] = 9 + 2*(i mod 11)`, `irow[i] = topr + 2*(i div 11)` where
  `topr = 2 + ((wave-1) mod 9)`; `nalive=55`, `sweep=0`, `mdir=1`,
  `edgehit=0`, `dropnext=0`, `frame=0`; draw all 55.

- [ ] **Step 2: `marchstep`** — the heart of the demo. Exactly:

```
X = sweep
if alive[X]:
    erainv X
    if dropnext: irow[X] += 1
    else:        icol[X] += mdir
    drawinv X                        ; uses `frame` and class colour
    if not dropnext:
        if icol[X] == 0 or icol[X] == 38: edgehit = 1
    if irow[X] >= 20: gstate = 4     ; invaders reached the baseline
sweep += 1
if sweep == 55:
    sweep = 0
    frame ^= 1
    if dropnext: dropnext = 0; mdir = -mdir; edgehit = 0
    elif edgehit: dropnext = 1
    sndbeat                          ; heartbeat note, one per sweep
```

The speed-up is emergent: a dead invader costs one branch, so a thinning
formation completes its sweep in fewer *useful* ticks. **Skip-dead
optimisation:** `marchstep` loops forward over dead entries within one tick so
that a tick always moves a live invader — that is what makes the last invader
move every frame. Cap the skip loop at 55 iterations.

- [ ] **Step 3: Verify the engine deterministically**

```bash
.venv/bin/c64 until mainloop --count 1 ; .venv/bin/c64 mem get sweep 1
.venv/bin/c64 until mainloop --count 1 ; .venv/bin/c64 mem get sweep 1
```
Expected: `sweep` advances by 1 per tick. Then poke `alive` to leave a single
invader and confirm its `icol` changes every tick:

```bash
.venv/bin/c64 mem write alive 0 0 ... (54 zeros, keep index 0)
.venv/bin/c64 until mainloop --count 1 ; .venv/bin/c64 mem get icol 1
```

- [ ] **Step 4: Commit**

---

### Task 5: Player base, shot, and shot collisions

**Files:** Create `demos/invaders/player.s`

- [ ] **Step 1: `playerstep`** — read `$CB` **first thing** after the anchor;
  `KEY_A`=10 -> `basex -= 2` (floor 24), `KEY_D`=18 -> `basex += 2`
  (ceiling 320-24-24), `KEY_SPACE`=60 -> fire if `shotact == 0`. Write
  `$D000`/`$D010` bit 0 from `basex`.

- [ ] **Step 2: fire** — `shotact = 1`, `shotx = basex + 8`, `shoty = 210`,
  `shots += 1`, `sfxshot`, enable sprite 1.

- [ ] **Step 3: `shotstep`** — `shoty -= 6`; off the top (`< 52`) -> despawn.
  Otherwise compute `r = (shoty - 50) / 8`, `c = (shotx - 24) / 8` and read
  the screen cell:
  - code 64-75 -> invader hit: find the invader whose `icol <= c <= icol+1`
    and `irow == r`, clear `alive`, `nalive -= 1`, draw code 84 explosion for
    8 ticks, `addscore` by class, `sfxhit`, despawn shot.
  - code 76-78 -> shield hit: `shdmg` cell decremented, redraw, despawn shot.
  - UFO overlap (pixel compare against `ufox`) -> `ufoscore`, `sfxufooff`.
  This is **grid math, not the VIC-II collision latches** — say so in the
  audit; the latches are read once per frame only as a cross-check.

- [ ] **Step 4: Verify with the real held-key protocol**

```bash
.venv/bin/c64 until mainloop
.venv/bin/c64 mem get basex 1
.venv/bin/c64 key hold d --at mainloop --frames 10
.venv/bin/c64 mem get basex 1          # expect +20
.venv/bin/c64 key hold space --at mainloop --frames 1
.venv/bin/c64 mem get shotact 1        # expect 1
```

- [ ] **Step 5: Commit**

---

### Task 6: Shields with damage states

**Files:** Create `demos/invaders/shields.s`

- [ ] **Step 1: `shieldinit`** — 4 bunkers at columns 4, 13, 22, 31, each
  4 cells wide x 2 rows (rows 17-18); `shdmg[0..31] = 3`; draw code 76 in
  colour nybble `8+5`.

- [ ] **Step 2: `sherode`** — in: A = row, Y = col. Map to a `shdmg` index
  (return carry clear if the cell is not a shield). Decrement; redraw glyph
  `76 + (3 - dmg)`, or space when dmg reaches 0.

- [ ] **Step 3: Verify** — fire into a bunker and read `shdmg` and the screen
  code at that cell after each hit: expect 76 -> 77 -> 78 -> 32.

- [ ] **Step 4: Commit**

---

### Task 7: Bombs — three flavours, cancel-on-shot

**Files:** Create `demos/invaders/bombs.s`

- [ ] **Step 1: `bombspawn`** — every `N` ticks, if a slot is free and
  `nalive > 0`: pick a column with an 8-bit Galois LFSR (`seed`, taps `$B8`,
  never zero), find the **lowest live invader** in that column, spawn a bomb
  one row below it. Type cycles 0/1/2 so all three flavours appear.

- [ ] **Step 2: `bombstep`** — per slot: `bdelay -= 1`; at zero reload from
  the type table (slow 4, fast 2, wiggly 3), erase the old cell, `brow += 1`,
  and draw the type's glyph (wiggly alternates 82/83 by `brow` bit 0; slow
  alternates 79/80). Then test the destination cell:
  - shield glyph -> `sherode`, kill bomb.
  - `brow >= 21` and column within the base's 3 cells -> `gstate = 2`
    (base dying), `sfxboom`.
  - `brow > 22` -> kill bomb.
  - shot occupies the same cell -> **cancel both** (this is the bomb/shot
    collision the spec asks for; grid math, stated in the audit).

- [ ] **Step 3: Verify** — poke `bactive`/`bcol`/`brow` to place a bomb one
  cell above a shield, step 4 ticks, and read the shield's `shdmg`.

- [ ] **Step 4: Commit**

---

### Task 8: Mystery UFO and the shot-count secret

**Files:** Create `demos/invaders/ufo.s`

- [ ] **Step 1: `ufostep`** — `ufotimer` counts down from 1500 ticks (25 s);
  at zero, if `nalive > 8`, spawn: `ufoact = 1`, `ufox = 12` (X = 24) moving
  right, or from the right edge on alternate spawns; enable sprite 2 in
  `$D015`; `sfxufo`. Each tick `ufox += 1` (2 px), write `$D002` and the
  `$D010` bit; off screen -> despawn, `sfxufooff`, reload `ufotimer`.

- [ ] **Step 2: `ufoscore`** — the arcade secret, exactly:
  - `shots == 23` -> 300 points.
  - `shots > 23` and `(shots - 23) mod 15 == 0` -> 300 points.
  - otherwise a 15-entry table indexed by `shots mod 15`:
    `50,50,50,100,150,100,100,50,300,100,100,100,50,150,100`.

- [ ] **Step 3: Verify** — poke `shots` to 22, fire once (making it 23), poke
  the UFO under the shot, step, and read `score`: expect +300.

- [ ] **Step 4: Commit**

---

### Task 9: SID — three voices, shadowed, priority-arbitrated

**Files:** Create `demos/invaders/sound.s`

- [ ] **Step 1: `sidput`** — `sta $D400,x` + `sta sidshadow,x`. **Every** SID
  write in the program goes through it; no bare `sta $D4xx` anywhere else.

- [ ] **Step 2: `sndinit`** — zero all 25 registers through `sidput`; volume
  `$D418` = `$1F` (volume 15 + low-pass), resonance/routing `$D417` = `$74`
  (resonance 7, voice 3 routed through the filter), cutoff `$D416` = `$FF`.

- [ ] **Step 3: Voice 1 — the heartbeat.** Pulse waveform, PW swept from
  `$0400` to `$0C00` across the four notes, ADSR `$00`/`$F8` (attack 2 ms,
  decay 100 ms, sustain 15... use `$A5`/`$8A` tuned by ear-equivalent), four
  descending frequencies (`$0480, $0400, $0390, $0320`). `sndbeat` advances
  the note index and gates. Because `sndbeat` is called once per **sweep**,
  the tempo accelerates automatically as invaders die — no speed table.

- [ ] **Step 4: Voices 2 and 3 — effects with priorities.**

| Effect | Voice | Prio | Waveform | Character |
|--------|-------|------|----------|-----------|
| `sfxshot` | 2 | 1 | pulse, PW `$0200`, fast down-sweep | short bright pulse |
| `sfxhit`  | 2 | 2 | sawtooth, fast down-sweep | invader pop |
| `sfxufo`  | 3 | 1 | triangle, fast up/down warble, loops while UFO lives | warble |
| `sfxboom` | 3 | 3 | **noise through the low-pass filter**, cutoff swept down | player explosion |

  A request is refused when `sndprio` for that voice is higher; equal or lower
  retriggers. `sndtick` advances each active sweep and clears the priority when
  the effect's duration expires.

- [ ] **Step 5: Verify from the shadow, never from SID readback**

```bash
.venv/bin/c64 until mainloop
.venv/bin/c64 mem get sidshadow 25       # mid-heartbeat capture
.venv/bin/c64 mem get sndprio2 1
```
Expected: voice 1 control byte (`sidshadow+4`) has the pulse+gate bits set,
`$D418` shadow shows volume 15 + low-pass, and firing a shot changes
`sidshadow+11` (voice 2 control).

- [ ] **Step 6: Commit**

---

### Task 10: HUD, title screen, waves, game over, hi-score

**Files:** Modify `demos/invaders/screen.s`, `demos/invaders/invaders.s`

- [ ] **Step 1: HUD** — draw the static labels once per state entry; update
  only the digit cells when `score`/`hiscore`/`wave`/`lives` change (a dirty
  flag per field, so no per-frame repaint).

- [ ] **Step 2: Title screen** — the word `INVADERS` drawn large from
  graphics characters, a SCORE ADVANCE TABLE listing `=30 POINTS`,
  `=20 POINTS`, `=10 POINTS`, `? MYSTERY`, and `PRESS ANY KEY TO PLAY`.
  Any key (via `$CB != 64`) starts a game.

- [ ] **Step 3: State machine in `mainloop`** — title -> play -> (base dying:
  8-tick explosion sprite, decrement `lives`, respawn or game over) ->
  wave clear (all invaders dead: `wave += 1`, `newwave`) -> game over
  (3 s of `GAME OVER`, then back to title with `hiscore` preserved).

- [ ] **Step 4: Extra life** — at 1500 points, once (`extradone`), `lives += 1`.

- [ ] **Step 5: Verify the hi-score survives a second game**

```bash
# play game 1 to a game over, note `score`; wait for the title; start game 2
.venv/bin/c64 mem get hiscore 3
```
Expected: game 2's `hiscore` equals game 1's final `score`.

- [ ] **Step 6: Commit**

---

### Task 11: The improvement loop (repeat until clean)

**Files:** Create `demos/invaders/AUDIT.md`, `demos/invaders/test.yaml`,
`demos/invaders/evidence/`

Each numbered iteration is a full cycle, logged in `AUDIT.md`:

- [ ] **Evaluate** — drive the running game deterministically and mark every
  spec bullet PASS/FAIL **with evidence from the machine** (register/memory
  reads, screen codes, PNGs) — never from reading the source.
- [ ] **Review** — cycle-count `marchstep` and the per-frame path; hunt dead
  code; compare march rhythm, bomb pressure and the speed-up curve against
  the arcade.
- [ ] **Improve** — fix every FAIL and every review finding.
- [ ] **Re-verify** — prove each fix in the running game.

Stop only when an iteration ends with every bullet PASS and a review that
finds nothing worth fixing.

- [ ] **Write `test.yaml`** asserting: `$D015` sprite enables, `$07F8` = 224,
  `$D018` = `$1D`, `$D016` multicolor bit, HUD text in screen RAM, `sweep`
  advancing under `until mainloop`, `nalive` decreasing after a scripted kill,
  and `sidshadow` non-zero. Run with `c64 test run`.

- [ ] **Capture evidence** (machine stopped, `--scale 2`) to `evidence/`:
  `title.png`, `formation.png`, `shield-eroded.png`, `bombs.png`,
  `ufo.png`, `wave2-lower.png`, `game-over.png`, `hiscore.png`.

---

### Task 12: Ship

- [ ] **Step 1: Package**

```bash
.venv/bin/c64 package demos/invaders/invaders.s \
  -o demos/invaders/invaders.d64 --title "INVADERS" --json
```

- [ ] **Step 2: Boot the artifact from cold** in a fresh session
  (`c64 session start --disk demos/invaders/invaders.d64` + `c64 disk boot`)
  and confirm the title screen appears — proving the shipped image, not the
  source tree.

- [ ] **Step 3: Report the exact `run` command** the tool prints.

- [ ] **Step 4: Flip demo 06 to dogfooded in `demos/README.md`; commit.**

---

## Self-review

**Spec coverage.** Formation (T4), march engine + emergent speed-up (T4),
player/lives/extra life/one shot (T5, T10), bombs incl. three flavours and
shot-cancel (T7), shields with damage states eroding from both sides (T6, T7),
UFO + 23rd-shot secret (T8), waves 1-10 heights + baseline loss (T4, T10),
HUD + persistent hi-score (T10), title screen + score advance table (T10),
sound across three voices with ADSR/waveform mix/filter/priorities/shadow (T9),
performance rules (jiffy pacing T1, changed-cells-only T4/T10, no ROM in hot
path T1, cycle count T11), `$CB` input (T5), improvement loop (T11),
deterministic proof + evidence (T11), packaging (T12).

**Placeholders.** None: every task names exact labels, addresses, glyph codes,
score table values and verification commands. The ADSR nybbles in T9 step 3 are
the one judgement call left to tuning — the constraint (real envelopes, mixed
waveforms, filtered explosion) is fixed, the exact nybbles are not.

**Type consistency.** `sweep`, `mdir`, `edgehit`, `dropnext`, `frame`,
`nalive`, `shots`, `shdmg`, `sidshadow`, `sndprio2/3` are spelled identically
in the variable table and in every task that reads them. `sherode` takes
A = row, Y = col in both T6 and T7. `addscore` takes points/10 in T5 and T8.
