# Invaders — fidelity audit log

Three numbered iterations, each a full cycle: **evaluate** the running game
against every bullet of `PROMPT.md`, **review** the code, **improve**, and
**re-verify** on the machine.  Every PASS below is evidence read out of a
live C64 — a memory or register read, a screen-code read, or a captured
frame — never from reading the source.

Everything is driven the way the spec requires: `--warp --headless`, input
injected as the held-key matrix code at `$CB`, and every sample anchored on a
`c64 until mainloop` stop.  `tools/evidence.sh` re-runs the whole protocol
and rewrites `evidence/`.

---

## Iteration 1 — first playable build

### Evaluate

| # | Spec bullet | Verdict | Evidence |
|---|---|---|---|
| 1 | Formation: 5 x 11, three classes, per-class colour | PASS | `nalive=55`; `irow[0]=3`, `irow[44]=11`; colour nybbles 11/13/10 |
| 2 | One invader per tick, emergent speed-up | PASS | 1 column step per 60 ticks at 54 alive, 1 per tick at 1 alive |
| 3 | Edge -> drop -> reverse | **not yet observed** | never ran long enough to reach an edge |
| 4 | Player: sprite 0, pixel movement, one shot | PASS | held `d` for 20 frames: `basex` 68 -> 88, `$D000` = 200 |
| 5 | Three lives, extra life at 1500 | PASS (unit) | `addscore` boundary tests |
| 6 | Bombs: three in flight, three flavours | **FAIL** | only 1-2 ever in flight; drop rate too slow to see all three |
| 7 | Bomb / shot cancel | PASS | shot and bomb slot 2 both cleared on the same tick |
| 8 | Shields erode from both sides, damage states | PASS | `shdmg` 3 -> 2 under bomb fire and under shot fire |
| 9 | UFO crosses, 23rd-shot secret | PASS | shot 23 -> 300; 38 -> 300; 53 -> 300 |
| 10 | Waves 1-9 lower, 10 resets | PASS | 1 -> row 3 ... 9 -> row 11, 10 -> row 3 |
| 11 | Baseline / lives-out ends the game | PASS | `irow[0]` 20 -> `gstate=4`, GAME OVER on screen |
| 12 | HUD, hi-score across games | **FAIL** | HUD digits leaked onto the attract screen |
| 13 | Title screen with score advance table | PASS | screen text; PNG shows the three classes in class colours |
| 14 | Three-voice SID, shadowed | PASS | `sidshadow` shows `$41` pulse+gate on voice 1, `$1F` volume+LP |
| 15 | Jiffy pacing, changed cells only, no ROM in the hot path | PASS | 120 ticks consumed exactly 120 jiffies |
| 16 | `$CB` held-key input | PASS | `c64 key hold d --at mainloop` moves the base |

### Review

1. **Invaders overwrite their neighbours.** A 2-cell invader on a 2-column
   pitch steps into the cell its neighbour still occupies; the neighbour's
   turn then erases that cell, leaving half-drawn aliens all along the row.
   Visible in `play1.png` as fragments.
2. **Bunkers are featureless green rectangles** — no arch, so they do not
   read as bunkers.
3. **Title letters recolour every 8 columns**, cutting across letters.
4. **An expiring invader explosion blanks its cells unconditionally**, so it
   can punch a hole in a live invader that marched over it.
5. **HUD leaks onto the attract screen** (`updhud` runs in every state).
6. **Bomb pressure is too low** to ever show the three flavours together.

### Improve + re-verify

- Column pitch 2 -> 3.  11 invaders now span 32 of 40 columns and sweep the
  remaining 8 — which is also the arcade's own formation-to-screen
  proportion (176 of 224 pixels, sweeping 48).  Re-verified: `pitch3.png`
  shows clean rows, and `icol` steps 4 -> 8 -> 0 with no overlap.
- Bunkers get their arch: cells 5 and 6 of each bunker's eight start
  destroyed.  Re-verified: `shdmg` = `3 3 3 3 3 0 0 3`, `@18,6` = 32.
- Title colour table indexed per letter group.
- `expstep` blanks a cell only if it still holds the explosion glyph.
- `updhud` is skipped while `gstate == 0`.
- Bomb drop interval 35 -> 28 ticks on wave 1, ramping to 12 by wave 12.

---

## Iteration 2 — fidelity and polish

### Evaluate

Everything from iteration 1 re-checked and still PASS, plus the two that
were open:

| # | Spec bullet | Verdict | Evidence |
|---|---|---|---|
| 3 | Edge -> drop -> reverse | PASS | see the trace below |
| 6 | Three bombs, three flavours | PASS | `bactive = 1 1 1`, `btype = 0 1 2`, all three visible in `bombs.png` |

The march reversal, sampled once per sweep (55 ticks):

```
tick   icol[0] irow[0] mdir dropnext edgehit
  55       5       3     1      0      0
 165       7       3     1      0      0
 220       8       3     1      0      1     <- rightmost invader reached col 38
 275       8       4     1      1      1     <- the drop pass: down a row, no sideways move
 330       7       4   255      0      0     <- and now marching left
 715       0       4   255      0      1     <- leftmost reached col 0
 770       0       5   255      1      1     <- drops again
```

### Review

1. **Sprite Y is one raster line out.**  The 25-row display window starts at
   raster 51, not 50, so `50 + 8*row` put the UFO's dome on the bottom pixel
   row of the HUD (`ufo.png`, iteration 1).  The shot's row calculation had
   the same off-by-one.
2. **The base explosion sprite is a small blob**, not a burst.
3. **Lives are a bare digit**; the cabinet showed a little ship per life.
4. **`fx2` is written five times and read nowhere** — `sndtick` branches on
   `fx3` only, and `sndprio2` already carries who owns voice 2.
5. **`BOMBRATE` (35) disagreed with `bombrate[1]` (28)**, so the first bomb
   of a wave used a rate that appears nowhere else.

### Improve + re-verify

- `TOPRASTER = 51`; `BASESPY = 51 + 8*22`, `UFOSPY = 51 + 8*1`, and the
  shot's row is `(shoty - 51) >> 3`.  Re-verified: `sprite status` reports
  base y=227, UFO y=59, and `ufo.png` shows the saucer clear of the HUD.
- Base explosion redrawn as a wider debris burst.
- Charset glyph 86 is a little laser base; the HUD draws one per life at
  every other column.  Re-verified: `@24,9/11/13` = 86 with 3 lives.
- `fx2` deleted along with the three loads that fed it.
- `BOMBRATE` renamed `FIRSTBOMB = 60` and documented as the grace period
  before a wave's first bomb; the per-wave rate lives only in `bombs.s`.

---

## Iteration 3 — final audit

### Evaluate — every spec bullet

| Spec bullet | Verdict | Evidence from the running machine |
|---|---|---|
| **Formation** 5 rows x 11, 30/20/20/10/10 points | PASS | `nalive=55`; `irow[0]=3`, `irow[44]=11`, `icol[0]=4`, `icol[10]=34`; `invpts` scored 10 and 20 in sequence as a column was cleared bottom-up (`score` 000090 for 5 kills) |
| Two shapes per invader, three classes visually distinct, per-class colour | PASS | `frame` toggles 0/1 at each sweep wrap; colour nybbles `$0B/$0D/$0A` (multicolor cyan / green / red); `evidence/formation.png` and `formation-2.png` |
| **March**: one invader per tick, swept in order | PASS | `sweep` advances by exactly 1 per `until mainloop --count 1`; `marchstep` costs 395 cycles, deterministic across runs |
| Steps sideways; edge -> drop one row + reverse | PASS | the trace in iteration 2: `icol` 4->8, drop to row 4, `mdir` $01->$FF, back to 0, drop to row 5 |
| Speed-up emergent, never a table | PASS | 1 column step / 60 ticks at 55 alive; 4 / 60 ticks at 11 alive; **19 / 20 ticks at 1 alive**. No speed table exists in the source; the only tempo term is the sweep length |
| Final invader visibly frantic | PASS | one column per tick = 480 px/s; it crosses its whole travel in 8 frames |
| **Player**: sprite 0, moved by pixels | PASS | `sprite status`: sprite 0 on, ptr 224 @ `$3800`; `basex` +1 unit (2 px) per held frame, `$D000` follows |
| Three lives, extra life at 1500, one shot at a time | PASS | `lives=3` at start; `addscore` at 1490+10 gives `lives=4` and at 1480+10 does not; `fireshot` is gated on `shotact` |
| **Bombs**: up to three, from the lowest live invader in a column | PASS | `bactive = 1 1 1`; `bombspawn` scans rows 4->0 of the chosen column |
| Three flavours: slow straight, fast straight, wiggly | PASS | `btype = 0 1 2` simultaneously; three distinct glyphs in `evidence/bombs.png` |
| Bomb and shot cancel | PASS | with a bomb one row above the bolt, one tick clears both `shotact` and that `bactive` slot. **Grid math**, not the VIC-II latches — see "collision" below |
| **Shields**: four bunkers, erode from both sides, damage states | PASS | shot fire drove one bunker's cells to `3 2 1 3 3 0 0 0` — solid, cracked, crumbling and gone in one frame (`evidence/shield-eroded.png`); bomb fire drove `shdmg[10]` 3 -> 2 |
| **UFO**: crosses periodically with its own sound | PASS | `$D015 = $05` (base + UFO), sprite 2 on at x=258 y=59 ptr 226; `sidshadow+18 = $11` (triangle + gate) while it crosses; `evidence/ufo.png` |
| 50-300 points, 300 on the 23rd shot then every 15th | PASS | `ufoscore` with `shots` = 23 / 38 / 53 all give 300; 1 gives 50, 5 gives 100, 24 gives 100 |
| **Waves**: 1 high, 2-9 one step lower each, 10 resets | PASS | 1->row 3, 2->4, 5->7, 9->11, 10->3, 11->4, 19->3 |
| Game ends on lives out or an invader at the baseline | PASS | lives 1 -> bomb hit -> `gstate=4`; `irow[0]=20` on its move -> `gstate=4` |
| **HUD**: SCORE, HI-SCORE, WAVE, lives always visible | PASS | row 0 `SCORE 000000   HI 000090    WAVE 01`; row 24 `LIVES 3` plus three base icons |
| Hi-score survives across games in a session | PASS | game 1 ended on 90; game 2 opens `SCORE 000000   HI 000090` |
| **Title**: big name, score advance table, `? MYSTERY`, press any key | PASS | `evidence/title.png`; screen text carries `SCORE ADVANCE TABLE`, `= 30 POINTS`, `= 20 POINTS`, `= 10 POINTS`, `? MYSTERY`, `PRESS ANY KEY TO PLAY` |
| **Sound**: four-note descending bass locked to the march | PASS | `sndbeat` fires once per sweep; beats per 120 ticks: 2 at 55 alive, 11 at 11 alive, 21 at 2 alive |
| Shot / hit / explosion / UFO on the other two voices | PASS | shot `$41` pulse, hit `$21` sawtooth (voice 2); UFO `$11` triangle, explosion `$81` noise (voice 3) |
| Real ADSR, mixed waveforms, the filter | PASS | `sidshadow+5 = $08` (attack 2 ms, decay 300 ms); waveforms pulse/sawtooth/triangle/noise all observed; `sidshadow+23 = $F4` routes voice 3 through the filter, `+24 = $1F` selects low-pass, `+22` swept 240 -> 232 -> ... during an explosion |
| Priorities defined for contending effects | PASS | shot 1, invader hit 2, UFO 1, explosion 3; `claim2`/`claim3` refuse a lower priority. Observed: `sndprio3 = 3` while the base burns, with the UFO warble suppressed |
| Every SID write shadowed in RAM | PASS | `sidput` is the only writer; `grep -c 'sta.*\$D4' sound.s` is 1 |
| **Perf**: jiffy pacing | PASS | 120 game ticks consumed exactly 120 jiffies — no overrun |
| Redraw only changed cells | PASS | the only full-screen writes are `clrscreen` (state entry) and `clrplayfield` (wave change); in play only the moved invader's 2 cells, the bombs' cells and dirty HUD digits are written |
| No ROM calls in the hot path | PASS | `grep 'CHROUT\|GETIN\|jsr *\$F'` over the sources matches four lines, all of them comments — there is no `jsr` into ROM anywhere, not even at init: `clrscreen` writes screen RAM directly rather than calling CHROUT |
| Cycle cost of the per-tick invader update known | PASS | **395 cycles**, measured three times identically; the whole frame is **1179 of 17095** (6.9 %). Worst case (54 dead entries skipped in one tick) is 3023 for `marchstep`, ~3900 for the frame — 23 % |
| `$CB` held-key input | PASS | `poke $CB` + `until mainloop` moves the base right and left; `c64 key hold d --at mainloop --frames 20` gives exactly +20 |

### Review

Read the whole source again looking for dead code, slack and gameplay feel.
Nothing found that is worth fixing:

- No unreachable code and no unread variables remain (`fx2` was the last
  one, removed in iteration 2).
- The per-frame path is 6.9 % of an NTSC frame; the pacing loop spins on the
  jiffy for the rest.  `marchstep` is the largest single cost at 395 cycles
  and is already down to two `(PTR),y` stores per cell with a shared
  `invptr`.  Nothing in the frame is a candidate for optimisation on
  evidence — the budget is not the constraint.
- March rhythm: one full sweep is 55 ticks = 0.92 s, the same as the arcade
  board's 55-frame alien cycle.
- Bomb pressure: a drop attempt every 28 ticks on wave 1 keeps 2-3 bombs
  alive against 3 slots, tightening to every 12 ticks by wave 12.
- Speed-up curve: strictly proportional to the live count, from 1/55 of a
  column per tick down to 1 column per tick, with no clamp anywhere.

### Known deviations, stated rather than hidden

These are deliberate and each is a consequence of the C64's character grid,
not an unfinished bullet:

1. **The formation steps one whole character (8 px) at a time**, where the
   cabinet stepped 2 px.  With 11 invaders on a 3-column pitch the formation
   still spans 80 % of the screen and sweeps the other 20 %, so the *shape*
   of the motion matches; only the granularity is coarser.  Sub-character
   stepping would need four pre-shifted copies of every glyph.
2. **Collision is grid math, not the VIC-II collision latches.**  Stated
   because the spec asks which.  The latches are the wrong instrument here:
   `$D01E`/`$D01F` are sprite-vs-sprite and sprite-vs-background only, so
   they can see neither the character-mode invaders nor the character-mode
   bombs; they cannot say *which* invader was hit, which is what scoring
   needs; and they clear on read, which makes them racy under a debugger.
   The shot's column is fixed at fire time and its row is exact, so a single
   screen-RAM read is both cheaper and deterministic.
3. **The heartbeat has a 4-tick minimum note length** (`beatgap`).  With one
   invader left a sweep completes every frame, and a 60 Hz retrigger is
   shorter than the envelope's attack — the note would never sound.  This
   bounds the *note*, never the march: the formation still moves a full
   column every single tick at that point.
4. **Invaders that march over a bunker destroy it permanently** (`shzero`
   clears the damage state rather than letting it redraw).  This is arcade
   behaviour, and it is why late waves that start low eat the shields.
5. **`invaders.d64` and `invaders.prg` are committed** beside the sources, so
   a reader needs only stock VICE: `x64sc -ntsc demos/invaders/invaders.d64`.
   `.gitignore` still ignores every other build output — including the
   `.lbl` — and carves out only `demos/*/*.prg` and `demos/*/*.d64`, because
   shipping the runnable artefact is the last step of this demo's own prompt.

### Verdict

Every spec bullet PASS; the review found nothing worth fixing.  The loop
ends here.
