# Invaders Demo (06) Dogfood Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (inline execution chosen by the user). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Dogfood `demos/06-invaders-asm.md` — build an arcade-faithful
Invaders (a Space Invaders recreation) for a PET 4032 in pure 6502 assembly (BASIC SYS stub), prove
every spec bullet deterministically on the emulator, package
`invaders.d64`, and mark the demo dogfooded.

**Architecture:** One ca65 source (`demos/invaders/invaders.s`),
frame-locked to the jiffy clock with a `tick` label as the deterministic
frame-step anchor. The march uses the authentic one-alien-per-tick engine with
per-alien coordinates so the speed-up is emergent. Collision is
screen-content-based (read the target cell, classify by screen code), with
per-alien coordinate lookup to identify a struck invader. A one-voice
priority sound driver owns the VIA CB2 registers.

**Tech Stack:** `c64` CLI (repo venv `.venv/bin/c64`), ca65/ld65, VICE x64sc
(headless + warp), PET 4032 (40×25, screen at $8000, BASIC 4).

## Global Constraints

- Program loads at $0401 with the standard 12-byte BASIC stub → code at $040D (SYS 1037).
- Fit comfortably in 32K (verify final .prg size; expect < 5K — enormous headroom).
- Redraw only changed cells; never repaint the whole screen mid-play.
- No ROM calls in the hot path (GETIN allowed only on title/game-over screens; in-game input reads $97 directly).
- Pace with the jiffy clock low byte $8F; one game tick per jiffy.
- Read in-game input from $97 (key-down; $FF = none) **immediately after the `tick` label** to minimize the poke-$97 race in deterministic testing.
- Sound only via VIA CB2: ACR $E84B (=$10 on), SR $E84A (pattern), T2 low $E848 (period). Zero $E848 AND $E84B on silence/exit.
- Store **screen codes** to $8000+, never PETSCII.
- Zero page: only $FB-$FE (PTR=$FB/$FC, PTR2=$FD/$FE). Everything else in BSS.
- All work in `demos/invaders/` (gitignored); only docs changes are committed.
- Session: `c64 session start --warp --headless` (model c64, the default). Use the venv: `export PATH="$PWD/.venv/bin:$PATH"  # from the repo root`.

---

## Screen layout (40×25, rows 0-24)

| Rows | Content |
|------|---------|
| 0 | HUD: `SCORE 00000  HI 00000  WAVE 01` |
| 1 | UFO lane (UFO = `<=>`, screen codes 60,61,62) |
| 2-18 | Formation march space. Wave 1 formation top row = 2; wave N top = 2 + ((N-1) mod 9) |
| 19-20 | Shields: 4 bunkers, 4 cells wide × 2 tall, at columns 5-8, 14-17, 23-26, 32-35 |
| 22 | Player shot spawn row (shot glyph = 30, up-arrow) |
| 23 | Player base: 3 chars `108 98 123` (▗▄▖); baseline — invader here = invasion |
| 24 | `LIVES n` + spare-base icons |

Formation: 5 rows × 11 columns, horizontal pitch 2 (invader columns are
2 cells apart → width 21 cells), vertical pitch 1. Left edge limit x=0,
right limit x=39.

## Glyph assignments (screen codes)

| Object | Codes | Notes |
|--------|-------|-------|
| Squid (top row, 30 pts) | 87 (○) ↔ 81 (●) | frames A/B |
| Crab (rows 2-3, 20 pts) | 65 (♠) ↔ 88 (♣) | |
| Octopus (rows 4-5, 10 pts) | 86 (╳) ↔ 90 (♦) | arms out / arms in |
| Player base | 108, 98, 123 | ▗▄▖ on row 23 |
| Player shot | 30 (↑) | decodes as `^` in c64 screen |
| Slow straight bomb | 33 (!) | |
| Fast straight bomb | 93 (thin vertical bar) | |
| Wiggly bomb | 77 (╲) ↔ 78 (╱) | alternates per move — the arcade squiggle |
| UFO | 60,61,62 (`<=>`) | 3 cells, row 1 |
| Shield states | 160 (solid) → 102 (▒ checker) → 32 (gone) | per-cell damage |
| Explosion flash | 42 (*) | one popup slot, few-frame timer |

All game glyph codes are disjoint from each other and from HUD letters'
codes in cells the game reads, so screen-content collision classification
is unambiguous (letters/digits live only on rows 0 and 24, which
projectiles never enter: bombs die entering row 24, shots die at row 2 top? —
no: shots die leaving row 2? shots die when moving above row 1's lane —
they may hit the UFO on row 1; a shot reaching row 0 is removed).

## Data structures (BSS)

```
alienA:  .res 55   ; alive flags (0/1), index = frow*11 + fcol, frow 0=top
alienX:  .res 55   ; screen column of each alien
alienY:  .res 55   ; screen row
mcur:    .res 1    ; march cursor 0-54 (next index to consider)
mdx:     .res 1    ; current step: +1 or -1 (two's complement)
mdrop:   .res 1    ; 1 = this sweep is a drop sweep
edgeF:   .res 1    ; set when a moved alien lands on column 0/39
sweepF:  .res 1    ; animation frame bit, toggles at sweep wrap
aliveN:  .res 1    ; live alien count
score:   .res 2    ; 16-bit, units of 10 points
hiscore: .res 2    ; survives across games (init once at cold start)
lives:   .res 1
extraF:  .res 1    ; extra-life-awarded flag
wave:    .res 1    ; 1-based
shotA:   .res 1    ; player shot active
shotX/Y: .res 1 each
shotCnt: .res 1    ; shots fired this game (UFO secret; 8-bit wraps OK — see UFO)
bombA/X/Y/T/P: .res 3 each  ; 3 bomb slots: active, x, y, type(0/1/2), phase
bombTmr: .res 1    ; frames until next drop attempt
ufoA:    .res 1    ; UFO active
ufoX:    .res 1
ufoTmr:  .res 2    ; 16-bit frames until next UFO
popT/X/Y/C: .res 1 each ; explosion/score popup slot (timer, pos, char)
sndPri:  .res 1    ; current effect priority (0 = none)
sndPtr:  .res 1    ; index into current effect's script
sndTmr:  .res 1    ; frames left in current effect
hbIdx:   .res 1    ; heartbeat note index 0-3
hbTmr:   .res 1    ; heartbeat note-on frames remaining
seed:    .res 1    ; LFSR state (nonzero)
```

Class of alien index i: `frow = ROWOF[i]` (55-byte table), class/points/glyph
tables indexed by frow (5 bytes each): `PTS: 3,2,2,1,1` (units of 10),
`GLYA: 87,65,65,86,86`, `GLYB: 81,88,88,90,90`.

## The march engine (heart of the game — cycle-count this in review)

Every frame (one tick), exactly one live alien moves:

```
march:  ldx mcur
find:   cpx #55
        bcs wrap          ; cursor past end → sweep complete
        lda alienA,x
        bne move
        inx
        bne find          ; skip dead aliens FREE (same tick) → emergent speed-up
wrap:   ; sweep complete: latch pending direction/drop for next sweep
        lda #0 → mcur; if edgeF: mdx = -mdx, mdrop=1, edgeF=0 else mdrop=0
        sweepF ^= 1
        heartbeat_note()  ; note per sweep → tempo locked to march
        rts               ; (this tick moved no alien; next tick moves alien 0…
                          ;  costs one tick per sweep — matches arcade's
                          ;  end-of-rack bookkeeping, keep and document)
move:   erase cell (alienX,x / alienY,x)
        if mdrop: alienY,x += 1 ; if alienY >= 23 → invaded=1
        else:     alienX,x += mdx ; if new x == 0 or 39 → edgeF=1
        draw GLY[A|B by sweepF][ROWOF x] at new pos
        mcur = x+1
```

Sweep order is index order = top-left → bottom-right. (Arcade sweeps
bottom-up; order only affects which alien moves first after a reverse —
acceptable, note in audit.)

Erase-then-draw touches exactly 2 cells per tick. Aliens overwrite shield
cells and projectile glyphs as they pass — shields erode under the march
(arcade-faithful).

## Collision rules (screen-content based)

- **Player shot** (moves up 1 row/frame): read destination cell.
  - space → move (erase old, draw new).
  - 160/102 (shield) → degrade that cell one state, remove shot.
  - 33/93/77/78 (bomb) → find bomb slot by (x,y), remove both, popup `*`.
  - alien glyph (87/81/65/88/86/90) → scan 55 aliens for alive & x,y match;
    kill it (alienA=0, aliveN--, erase cell, popup `*`, score += PTS,
    invader-hit sound). If shot y-1 row contains alien but no coord match
    (mid-move raggedness), treat as miss-through (move shot).
  - 60/61/62 (UFO) → UFO kill: score by shot-count secret, popup value,
    UFO sound off, remove shot.
  - row 0 reached → remove shot.
- **Bombs** (each type has a move divisor; wiggly alternates x±1):
  - destination space → move.
  - 160/102 → degrade shield cell, remove bomb.
  - 30 (player shot) → cancel both, popup `*`.
  - row 23 and column within base 3 cells → player death sequence.
  - reaching row 24 → remove bomb (ground).
  - base glyphs (108/98/123) read → player death.
- **Invasion**: any alien reaches row ≥ 23 → game over immediately.

## Bombs

- Max 3 in flight; `bombTmr` gates drop attempts (reload ~ 40 + LFSR&31
  frames; tighten by wave? no — keep constant, arcade pressure comes from
  descent).
- Type cycles 0,1,2 per successful drop (all three flavours appear).
- Column: wiggly aims at the player (nearest live column); straight types
  pick LFSR%11 with live-alien fallback scan.
- Source: lowest live alien in the column (scan frow 4→0); spawn at
  (alienX, alienY+1).
- Divisors: slow straight every 4th frame, fast straight every frame,
  wiggly every 3rd frame (x alternates ±1 within screen bounds).

## UFO

- `ufoTmr` 16-bit countdown (~1500 frames = 25 s); when 0 and formation top
  row > 2? (no — always) and UFO inactive → spawn at x=0 (or x=39 moving
  left, alternate by shotCnt parity like the arcade's direction quirk —
  keep simple: always left→right), move 1 cell every 2 frames, despawn at
  x=37.
- UFO warble: background sound while active (alternating periods).
- **Secret:** `shotCnt` counts every player shot *fired*. UFO kill value:
  300 if shotCnt == 23 or (shotCnt > 23 and (shotCnt-23) mod 15 == 0);
  else table `UFOVAL[shotCnt & 3] = 5,10,15,10` (units of 10 → 50-150).
  shotCnt is 8-bit; wrap at 256 accepted (arcade's is mod-15 anyway after
  23; document in audit). Popup shows the value ×10 in digits.

## Sound driver (one voice, priorities)

Effects are (period-script, length) pairs stepped once per frame; a new
effect starts only if its priority ≥ current. Priorities:
4 player-explosion (long rumble, SR pattern $6E, rising periods ~40 frames)
3 invader-hit (short crunch, pattern $55, ~6 frames)
2 player-shot (zap: descending period sweep 30→80, ~8 frames)
1 UFO warble (loops while UFO active: periods 90/110 alternating 4 frames)
0 heartbeat (4-note descending bass: periods 175,187,198,210, one note per
  sweep wrap, ~5 frames on then off — tempo therefore locked to march)
Driver writes $E84B=$10/$E84A=pattern/$E848=period on effect start/step,
zeros $E848+$E84B when idle. Game-over/exit also silences.

## State machine

COLD START → init hiscore=0 → TITLE (attract) → GAME (lives=3, score=0,
wave=1) → per wave: draw field+shields, formation at wave height → PLAY
loop (`tick`) → events:
- wave cleared (aliveN==0): wave++, brief pause, next wave setup.
- player hit: explosion sound + freeze ~60 frames, lives--, clear
  projectiles, respawn base at column 2; lives<0 → GAME OVER.
- invasion → GAME OVER.
GAME OVER: banner, hiscore = max(hiscore,score), ~3 s pause → TITLE.
TITLE: big SPACE INVADERS (3×5 block font, codes 160/32), SCORE ADVANCE
TABLE with live glyphs (`<=> = ? MYSTERY`, `○ = 30 POINTS`, `♠ = 20
POINTS`, `╳ = 10 POINTS`), `PRESS ANY KEY TO PLAY`, current HI score.
Waits on GETIN (buffered keys fine here).

Extra life: when score ≥ 150 units and !extraF → lives++, extraF=1, redraw
lives HUD.

## Input ($97 key-down)

Key codes for A, D, SPACE on the 4032 graphics keyboard are discovered
live in Task 2 (they are matrix-scan indexes, not PETSCII):
1. Run a probe: tiny loop copying $97 to screen; try `c64 key type "a"` —
   if $97 stays $FF (buffered feed bypasses matrix), read the ROM decode
   table instead: disasm the IRQ scan path from ($90)=$E455 to find the
   table base, then locate offsets of PETSCII 'A','D',' ' in an 80-byte
   `c64 mem read` of the table.
2. Define KEY_A/KEY_D/KEY_SP constants; verify by poking $97 before
   frame-steps and watching the base move/fire.
Held A/D move the base 1 cell every 3rd frame; SPACE fires when shotA==0.

---

## Tasks

Each task ends with the game assembling (`c64 run` clean) and a
deterministic on-emulator verification. Commit nothing until the final
docs task (all game files are gitignored anyway; the plan doc dir is
local-only).

### Task 1: Skeleton, HUD, playfield, shields, player draw
Files: Create `demos/invaders/invaders.s`
- [ ] SYS-stub skeleton, `cld`, cold-start init, clear screen ($93/CHROUT once — allowed, not hot path), draw HUD row 0, LIVES row 24, 4 shields, base; then a `tick` loop that only paces on $8F.
- [ ] Verify: `c64 run`, `c64 wait --text "SCORE"`, `c64 screen`; `c64 mem get` shield cells == 160; base cells 108/98/123 at row 23.

### Task 2: Input — key-code discovery + base movement
- [ ] Discover KEY_A/KEY_D/KEY_SP per Input section (probe program or ROM table).
- [ ] Base movement from $97 (left/right clamp 0..37), fire stub (records shotA).
- [ ] Verify: `c64 until tick`; loop { `c64 mem write '$97' KEY_D`, `c64 until tick --count 3` } → base cells shift right; same for A; space sets shotA.

### Task 3: The march engine
- [ ] Formation init (wave height formula), per-alien X/Y fill, march per the engine spec, animation frames, edge→drop+reverse, invasion detect.
- [ ] Verify by frame-stepping: `c64 until tick --count 55` → every alien moved 1 step; glyphs alternate on next sweep (mem read of a known cell); force edge (run sweeps) → formation drops one row and reverses (compare alienY dump before/after via `c64 mem read alienY 55`).

### Task 4: Player shot, alien kills, scoring, wave advance
- [ ] Shot fire/move/collisions (shield, alien, top), score += PTS, HUD digits, popup `*`, aliveN, wave-clear → wave 2 one row lower.
- [ ] Verify: poke $97 SPACE, step until shot kills a known alien → alienA[i]==0, score delta correct, HUD shows it; kill 54 aliens by harness pokes (alienA=0 + erase cells + aliveN=1), shoot the last → WAVE 02 in HUD, formation top row == 3.

### Task 5: Bombs, shield erosion, player death, lives, game over
- [ ] 3 bomb slots per Bombs spec, all collision rules, death freeze + respawn, lives HUD, invasion + lives-out → GAME OVER → title.
- [ ] Verify: step frames until 3 bombs in flight (mem read bombA/T shows types 0/1/2; screen shows 33, 93, 77-or-78); shield cell under bomb: 160→102→32 over two hits; shot from below erodes own shield; poke lives=1, let a bomb hit base → GAME OVER screen.

### Task 6: UFO + shot-count secret
- [ ] UFO spawn/move/despawn, warble flag, kill scoring per secret, popup value.
- [ ] Verify: poke ufoTmr=small, step → `<=>` marches on row 1; poke shotCnt=22, align base under UFO, fire (23rd shot) → score += 30 units (300 pts) exactly.

### Task 7: Sound driver
- [ ] Driver + all 5 effects wired: heartbeat on sweep wrap, shot on fire, crunch on kill, rumble on death, warble while UFO.
- [ ] Verify mid-heartbeat: `c64 until tick` at a sweep boundary (step 55+ frames), then `c64 mem read '$E848' 1` != 0, `$E84A` == pattern, `$E84B` == $10; after note ends $E848 == 0. Fire → different period visible. Death → pattern $6E while frozen.

### Task 8: Title screen + attract loop + hi-score persistence
- [ ] Big-font title, advance table, PRESS ANY KEY (GETIN), game-over → title loop, hiscore survives (never re-zeroed after cold start), extra life at 1500.
- [ ] Verify: title text via `c64 wait --text "PRESS ANY KEY"` + `--png`; play game 1 to game over with score S>0 (harness-assisted), back on title/HUD `HI` shows S; game 2 HUD `HI` == S; poke score=149, kill a 10-pointer → lives++ on HUD.

### Task 9: Iteration loop (spec's Evaluate → Review → Improve → Re-verify)
- [ ] Iteration 1 audit: walk EVERY spec bullet, PASS/FAIL from the running game only; log to `demos/invaders/AUDIT.md`.
- [ ] Iteration 1 review: cycle-count `march` worst case + frame budget table, .prg size vs 32K, dead code, gameplay feel (march rhythm, bomb pressure, final-invader franticness, player/bomb speed ratios) — log findings.
- [ ] Fix every FAIL + finding; re-verify each in the running game; repeat cycles until an iteration is all-PASS with an empty review. Document any hardware-impossibility FAILs (expected: two-frame sprite art → single chars, one voice → priority ducking, 4-digit score granularity).

### Task 10: Package + evidence bundle + docs + commit
- [ ] `c64 package invaders.s -o invaders.d64 --title "INVADERS"`; `c64 disk ls` shows autostart file; boot the .d64 in a fresh session (`c64 session start --warp --headless --disk` or `c64 disk boot`) → title appears (final proof).
- [ ] Save evidence PNGs (title, march, shields eroding, 3 bombs, UFO, wave 2, game over, hi-score game 2) under `demos/invaders/evidence/`.
- [ ] Update `demos/06-invaders-asm.md` header → `*(dogfooded 2026-07-11 — first-try pass)*` (only if true) and `demos/README.md` row 06 → ✅ passed; commit docs only.
- [ ] `c64 session stop`; check `pgrep -fl x64sc` for leaks.

## Self-review notes

- Spec bullets ↔ tasks: Formation/march → T3; player/lives/extra life → T2/T5/T8; bombs → T5; shields → T1/T4/T5; UFO+secret → T6; waves → T4/T8 (wave-10 reset is the height formula, audit by poking wave=9 pre-clear); HUD → T1/T4; title → T8; sound → T7; performance rules → T1 (pacing), T9 (cycle counts); proof protocol → T9 evidence; packaging → T10. No gaps.
- The one-tick-per-sweep-wrap bookkeeping (no alien moves on the wrap tick) is intentional and documented; with 1 alien alive the alien still moves every other tick → frantic. Audit will judge feel; if too slow at 55 or absurd at 1, tune only global tempo (constant divisor), never a per-count speed table.
- c64 screen text hides blocks (160→blank, graphics→`·`): all graphics verification asserts screen CODES via `c64 mem get`/`read`, PNGs for humans.
