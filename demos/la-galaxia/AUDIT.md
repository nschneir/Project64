# La Galaxia — fidelity audit

The improvement loop `PROMPT.md` §12 asks for: numbered iterations, each one
evaluate → review → improve → re-verify. Every claim below is marked from
the running machine, never from a reading of the source; where a claim is
marked FAIL or TRADE it says so and says what the measurement was.

**The hidden stage-select keys.** On the title screen only, the digit keys
start a one-player game at a chosen stage — `1` through `9` for stages 1-9
and `0` for stage 10 (`$CB` codes 56, 59, 8, 11, 16, 19, 24, 27, 32, 35).
They grant the stage and nothing else: the score starts at zero, the lives
at three, and the fighter is single. They are undocumented in-game, and
**most of the evidence below was captured through them** — the challenging
stage via `3`, the transforming enemies via `4`, the escort dives via `0`.
§13 requires this section to list them, and this is that list.

---

## Iteration 1 — from "it assembles" to "it runs"

**Evaluate.** The first build linked cleanly and crashed to BASIC. `c64 reg`
put the PC at `$E5CF` (KERNAL `INLOOP`, i.e. the READY prompt), `$D018` still
read `$15` and `$0314` still pointed at `$EA31` — so `start` ran and died
before the VIC setup.

**Improve.** Fifteen defects, all found on the machine:

| Where | What was wrong |
|---|---|
| `la-galaxia.s` `clearvars` | Walked with `sta (PTR),y` but compared `PTR+1` to `>varsend` and `Y` to `<varsend` — two different addresses. Zeroed far past the variables and into the code. **This was the crash.** |
| `screen.s` `cellptr` | `lda rowhi,x / adc #0` consumed the carry out of `rowlo+scrcol`, so colour RAM was written a page low on every cell whose row base plus column crossed a page. The whole playfield was black-on-black: text present in screen RAM, invisible. |
| `formation.s` `gmptr` | Added the column then subtracted `PFCOL`, discarding the add's carry and feeding the subtract's borrow into the high byte — the gridmap was addressed a page high on nearly every cell. |
| `formation.s` `formtick` | The row repaint kept its slot index in `tmp5`, which `eraseslot`/`drawslot` use as their quadrant counter. The loop ran away and wedged the machine. |
| `formation.s` | `drawslot`/`eraseslot` returned X clobbered by `gmptr`'s `tax`, so `enemytick`'s slot loop continued from the wrong slot. |
| `collide.s` | `hitgrid`/`hitdivers` kept the missile index in `tmp4` across `hitenemy`, which reaches `drawslot`, `addscore` and `num2dec` — every scratch byte is gone by then. |
| `collide.s` `hitgrid` | Re-read `(PTR),y` after `hitenemy` had left PTR pointing at screen RAM; a missile that hit the grid was never cleared and kept flying. |
| `formation.s` `buildformation` | Cleared 496 bytes of a 240-byte array, writing 256 bytes past `gridmap` into `bgbuf`. |
| `enemy.s` `transform` | Reset its scan after every spawn and could set `triolive` to 3 having placed fewer. |
| `mux.s` | `playerdraw` was never called, so sprites 0/1 were never programmed and `plena` was always 0. |
| `la-galaxia.s` | `scrollon` was never initialised; the `EV_SCRON` event wrote 0 to `$D016` every frame, putting the formation band in 38-column mode. |
| `formation.s` | The breathe expansion updated `gridexp` before the repaint, so `eraseslot` cleared cells the block had already left and half-blocks stayed on screen. |
| `text.inc`, `title.s`, `hud.s` | Three strings overran the bezel: a 27-character control line into the right rail, `JUGADOR` into the grille, the score digits into column 6. |
| `hud.s` | A dead `putnum` indexed `digbuf+6,y`, past the end of an 8-byte buffer. |

**Re-verify.** Title screen decoded as `LA GALAXIA`; the three starfield
layers each rolled at their own cadence (`$3AC0` sampled 60 ticks apart);
forty enemies settled to `enemy_state` all 1; the formation read back as 2×2
blocks of codes 64-87 in rows 3-12; `plx` moved exactly 90 pixels over 60
ticks of held `A`.

---

## Iteration 2 — the frame budget and the untested mechanics

**Evaluate.** `c64 profile tick` on a formation-repaint frame: **31,695
cycles** against an NTSC frame's 17,030 — nearly two frames. `formtick` was
26,306 of it. Ordinary frames were fine at 10,729, so roughly 5 frames in 32
overran and a single profile had a 27-in-32 chance of reporting "fine".

**Improve.** `drawslot`/`eraseslot` rebuilt four pointers per cell — ~160
cycles before a byte was stored. A 2×2 block is now one `pfptr` plus Y
offsets 0/1/40/41, which took a 10-slot row from 26,306 to ~1,800; the
repaint is additionally a rolling 2-slot cursor. Twelve further defects fell
out of exercising the mechanics:

| Where | What was wrong |
|---|---|
| `screen.s` `pfptr` | `BGC` was built from `bgrowlo` — **bgbuf's** row byte — so every colour-shadow write landed 24 bytes late, and at the bottom of the screen ran off `bgcol` into `mis_on`/`mis_col`/`mis_y`/`mis_prow`. Drawing the starfield put four phantom missiles in flight before the first frame of play. |
| `hud.s` `addscore` | Did not preserve X across `checkextra`, so every kill returned with X=0 and ran the trio tally, the explosion, the block erase and the `enemies_left` decrement against **slot 0**. |
| `hud.s` `checkextra` | Threshold was `first + step*n`, putting the second extra life at 90,000 instead of 70,000. |
| `stage.s` `spawnsweepers` | All 40 sweepers parked with `enemy_y_msb=1` and nothing cleared it — the challenging stage ended instantly with 0 hits. |
| `enemy.s` `etkillstray` | A trio member that flew off never decremented `triolive`, so no trio ever formed again for the rest of the game. |
| `stage.s` `stplay` | `picktransform` gated on `frames & $3F` plus a narrow Y window — 600 frames of stage 4 produced no trio at all. |
| `collide.s` `heboom` | An entrant shot down never decremented `waveleft`, so ST_ENTER waited for it for ever. |
| `formation.s` `eraseslot` | Erased at the global `gridexp`, which during a spread repaint is where the block is *going*, not where it is. |
| `formation.s` `tosprite` | Published the sprite only at the next `enemytick` — the enemy was neither block nor sprite for two frames, which §3.2 forbids. |
| `mux.s` `beamupdate` | The beam object was snapshotted but never appended to the list, so the tractor beam never got a hardware sprite. |
| `la-galaxia.s` `tick` | `cells_drawn` was cumulative and never reset per frame. |
| `screen.s` | The whole screen rebuild ran inside one state-init tick (~110,000 cycles). |

**Re-verify.** Twelve of §13's thirteen mechanics measured PASS — see the
claim table below. The redraw figure recorded at this point was "`cells_drawn`
max 32 over 300 consecutive ticks", which later turned out to be a *sampled*
number and is superseded by the program-tracked ceiling in the claim table.

---

## Iteration 3 — sound

**Evaluate.** The player, the effects and the 60-second title theme had
never been heard. First capture against the generated reference score.

**Improve.**

| Where | What was wrong |
|---|---|
| `sound.s` `musictick` | Reloaded `mus_tick` with `MUS_ROWTICKS` on the frame that *was* the row's first frame, so every row lasted 7 frames instead of 6 — **the tune ran 17% slow**. |
| `sound.s` `musvoice` | The vibrato's 16-bit add inverted its carry on every downward swing: adding a negative byte *sets* carry when no borrow is needed, so a downward swing added 256 to the frequency register — about 60 cents sharp at A4. |
| `sound.s` `sfxtick` | `sfxlen[SFX_BEAM]` is 14 while `BEAM_HOLD` is 110, so the tractor beam was a blip that stopped 96 frames before the beam retracted. |
| `tools/genmusic.py` | `events()` modelled the sheet music rather than the player. `musvoice` spends the first frame of each new note with the gate down — that is the retrigger — and the sampler transcribes it as a 1-frame rest, so every generated duration was one frame too long and every note was missing its leading rest. Now models the player frame-by-frame and run-length encodes, which is the algorithm the log transcriber uses. |
| `tools/genmusic.py` | Scores spelled flats (`Ab4`); the transcription only emits sharps. The first `--ref` run was seven diffs of pure orthography. |

**Re-verify.** Five captures, all **PASS**, each with its five artifacts under
`evidence/audio/`. After the fix the sequencer's 40 rows span exactly 240 log
frames, and `cents_off` across all five reports reads +0.0 to +6.6 with no
detune anomaly raised.

---

## Iteration 4 — the §11 evidence was not evidence

**Evaluate.** The committed `raster-time.png` was adjudicated by an
independent reviewer and **rejected**. A pixel scan found red on every
renderable scanline (PNG rows 8-254 = raster 28→262 wrapping to 11; rows 0-7
and 255-262 are blanking). By §11's own criterion — *"if the band ever wraps
past the bottom of the screen, the frame overran"* — that image is a picture
of a tick spanning the entire frame. It documented a FAIL and was presented
as a PASS.

**Three facts about the toolchain came out of that review**, and they are why
the frame misled everyone:

1. `c64 screen --png` is a **rolling scanline buffer, not a frame**. Lines the
   beam has swept show the current partial frame; lines below it show the
   *previous rendered* frame.
2. After a free-running or warp phase, the below-beam lines are **arbitrarily
   stale** — a probe capture showed boot-screen light blue underneath the
   program's own border. One extra `until tick --count 1` immediately before
   the screenshot flushes it, and every capture in `tools/evidence.sh` does.
3. NTSC canvas geometry wraps: **PNG row = (raster − 20) mod 263**. The band's
   first lines (raster 2-11) therefore appear as a red strip at the *bottom*
   of the canvas on a perfectly healthy frame. The overrun tell is no black
   anywhere.

**Improve.** The screenshot is the wrong instrument for this claim: it shows
one arbitrary previous frame, and the frames that violate §11 are episodic, so
a passing capture proves almost nothing about the worst frame. The game now
carries program-readable evidence instead — an IRQ-incremented frame counter
sampled at tick entry and exit, a mismatch incrementing **`tick_overrun`**,
and **`tick_endline`** holding `$D012` at tick exit as a max high-water mark.
Both are plain memory and both are asserted in `test.yaml`. The `$D020` band
survives as illustration behind a `rasterband` flag, default off.

**And the instrumentation immediately earned itself.** It exposed
`tick_overrun` = 2 per ~1,200-tick stage-1 run in the ST_ANNOUNCE→ST_ENTER
region, with ~27,000 cycles unaccounted for by anything visible in the tick.

**Root cause: the cycles were never spent.** When two raster events sit
within ~3 lines, the first event's handler writes the second's line into
`$D012`, finds the beam already past it, and dispatches inline — but the beam
crossing the just-written compare line **re-latches the raster IRQ**. The
`rti` re-enters immediately with `evidx` freshly parked at 0, so `EV_FRAME`
runs *mid-frame*: the frame counter double-counts (the phantom overrun), the
phantom `tickpend` runs the next tick early in the same frame (the cascade
second overrun), and the whole event list replays inline mid-screen — a real
one-frame visual glitch. It needed a reposition event landing 2-4 lines above
`BAND_BOT` = 148, i.e. an entrant crossing the formation band's foot, which is
why it lived only in the stage-1 entrance.

Proof: a store watchpoint on the frame counter fired at **raster line 150**
with SP=243 (inside `enemytick`), on tick `frames`=830, reproduced twice from
a deterministic replay. Fix: re-ack `$D019` at `irqexit` after all inline
dispatches.

**Re-verify.** `tick_overrun` = 0 over a 2,500-tick stage-1 game, a 2,100-tick
stage-8 game, and ~2,800 ticks of challenging-stage sweeps, all with the music
playing.

---

## Iteration 5 — the maintainer played it

**Evaluate.** A play session produced five findings that no automated check
had raised, and two of them were worse than reported.

| Reported | Actually |
|---|---|
| "the player does not die when hit by an enemy ship" | The box check was starved of divers, *and* the 9-bit X equality test meant a fighter at sprite-X ≥ 256 could never be rammed. **Worse: `ptdying` never cleared `plalive`, so a shot-down fighter respawned in place — game over was unreachable except by capture.** |
| "the game feels too easy, enemies are not shooting and are at the top" | `pickdive` sampled a random byte, masked to 0-63, and gave up if that slot was not settled — so the real dive rate was a fraction of `divecad`. Tier-1 `firerate` was 3/256 per diving enemy per frame. |
| "we need the sound effects during the game" | The music was being switched **off** on all three start paths, so §9's ducking never happened and the priority path was dead code in the shipped build. **Also `sfxstart` clobbered X, corrupting `enemytick`'s loop on every tractor-beam deploy.** |
| "tearing in the border top and bottom" | The `$D020` timing band of §11, plus its wrap strip — instrumentation left switched on. |
| "F1/F3 don't map from the Mac keyboard" | Confirmed; the start keys are now SPACE (1P) and `X` (2P). |

**Improve.** `pickdive` now always finds a settled slot (random start,
wrapping scan); half of dives send a pair; `difftab` retuned to cadence
70/52/38/26 and firerate 10/14/20/26 with §7's bullet ceilings unchanged. The
music plays through the game and is ducked by the effects — measured cost
`soundtick` 947 cycles/frame, of which `musictick` is 861.

**Re-verify.** An idle player now loses three lives in ~40 s and reaches
`JUEGO TERMINADO`. Explosion seizes voice 3 (`$81`, priority 3) and the laser
voice 1 (`$11`, `$4000` sweep, priority 2) while the sequencer keeps the
others, with `mus_on` = 1. `tick_overrun` = 0 throughout.

---

## Iteration 6 — the death nobody could see or hear

**Evaluate.** A second play session, one finding: *"when my ship was killed
there was no explosion visual or sound. It felt like the game froze for a
couple of seconds, although it probably did not."* Both halves were right, and
the parenthesis was right too — nothing was frozen.

Read off the running machine, stopped at `playerhit` and stepped a frame at a
time (pre-fix): sprite 0's pointer read **128** — `SPR_FIGHTER`, the ordinary
white fighter — on every one of the 40 frames of `plstate` 2, with `$D015` bit
0 still set. `playerdraw` had a case for `plstate` 1 (the capture spin) and
none for 2, so the fighter that had just been shot sat there intact and
unmoving until the state expired. Then `plalive` cleared, `ST_DEAD` held for
70 more frames with no fighter on screen at all, and the next one arrived:
**110 frames, 1.8 s, in which the only thing that changed was a counter.**

The sound was real but might as well not have been. `vprio[2]` = 3,
`vfx[2]` = 3, voice 3's shadow `$81`/`$09` for 24 frames — `SFX_EXPLODE`,
byte for byte the effect every enemy fires, several of which are usually going
off at the same moment. So the one event that costs a life sounded exactly
like the fifty that do not.

Neither is a coding slip. §6.3 of `PROMPT.md` specified the *capture*
animation in detail — spin, turn red, draw up to the Flagship — and said
nothing whatever about being shot down, and §9's effect table had one row
called "Explosion". The build implemented what it was asked for.

**Improve.** The fighter now burns. `plstate` 2 draws the enemies' four
explosion shapes (`SPR_EXP0..3`, blocks 145-148), eight frames each, over a
colour ramp that cools white → yellow → orange → red; `PLBOOM_FRAMES` is 32,
so `pltimer >> 3` indexes both tables and the state ends on the tick that
would have wanted a fifth shape. Those shapes are multicolour art and sprite 0
is hires for the fighter's edges, so `playerdraw` now owns `$D01C` bit 0:
it sets the bit for the blast and clears it for every other state, including
the no-fighter early return, so the mode register never describes a sprite
that is not there. The dead time is 32 + 70 = **102 frames**, and 32 of them
are now an explosion instead of a photograph.

The sound is its own effect. `SFX_PLDEATH` (7) runs 32 frames on voice 3 at
**priority 4** — above everything else in the game, so an enemy blowing up in
the same frame cannot take the voice off the player's death. It sweeps the
noise frequency high byte `$30` → `$11` (a rumble collapsing) where the
enemies' explosion moves `$4F` → `$4A`, and it decays over 1.5 s and releases
over ~170 ms instead of being cut off.

**Re-verify.** On the machine, stepping the blast frame by frame: sprite 0's
pointer walks 145 → 146 → 147 → 148 at pltimer 2/11/19/27, `$D027` walks
`$F1`/`$F7`/`$F8`/`$F2` (white/yellow/orange/red under the 4-bit mask),
`$D01C` reads `$FD` for the blast and `$FC` on both sides of it, and
`vprio[2]`/`vfx[2]` read 4/7 for all 32 frames with voice 3's shadow at `$81`,
AD `$0A`, SR `$05`. `c64 sprite show 0` mid-blast renders the fireball itself,
which is the one instrument that shows the shape the VIC is really reading.

Two `c64 audio capture` windows settle the ear half, the player's death
against an enemy's, both fired inside the window with `--at-frame` (a cue
armed before the command counts down during arming, and a one-shot effect is
then over before log frame 0 — the trap `--at-frame` exists for):

| | gated noise frames | freq hi across the burst | AD / SR |
|---|---|---|---|
| enemy explosion | 23 | 79 → 74 | `$09` / `$00` |
| the fighter's death | 31 | 48 → 18 | `$0A` / `$05` |

`evidence/death-1..4.png` and `evidence/death.txt` are the frames and the
bytes beside them; `test.yaml` asserts the whole sequence — pointer, colour,
mode bit, `vprio`/`vfx`, the gated noise register, and the pitch falling
against a sample — so a future build cannot quietly go back to a fighter that
sits there.

**Two things the spec learned in the process.** Waiting for the death rather
than staging it was a coin flip: a life goes two ways, and the Flagship's
tractor beam takes the fighter through `capture`, which never calls
`playerhit` — so a run whose lives all went to captures reached the game over
and then sat out the whole 120 s timeout on a label the attract loop never
executes. Measured twice in eight runs. The hit is now staged with a bullet
poked into `hitplayer`'s own window, which runs the real collision path. And
the §7 movement test was failing about one run in three on `88 not < 88`,
because a fighter shot down inside its 40-tick window respawns at the centre;
it now clears the formation first, the way `tools/audio-evidence.sh` already
did for the same reason.

---

## The claim table

| § | Claim | Verdict | Evidence |
|---|---|---|---|
| 2 | three input sources folded into one `input_state` | PASS | `joydecode` unit-tested at `$fb`/`$f7`/`$ef` → bits 1/2/4 |
| 2 | hidden stage select, digits 1-9 and 0 | PASS | `3` → `stage` = 3, score 0, lives 3 |
| 3.1 | settled formation lives in character RAM | PASS | rows 3-12 read codes 64-87 in `screen --codes` |
| 3.2 | diver becomes a sprite, erase and spawn in one call | PASS | break on `tosprite`, finish: block cells read star glyphs and `sprite status` shows the sprite, one stop |
| 3.3 | starfield is a character layer, glyphs rotated | PASS | `$3AC0` sampled 60 ticks apart: all three layers roll at their own cadence |
| 3.4 | **≥16 sprite objects per frame** | **TRADE** | peak `mux_count` **9** measured over 300 entrance ticks; `mux_overflow` **0** throughout. See below. |
| 4 | 24-column window, bezel as charset cells | PASS | `screen --png --border` |
| 5 | Dual Fighter: equal Y, exactly 16px apart | PASS | sprites 0/1 at y=218/218, x=164/180 |
| 5 | collision is coordinate maths, never `$D01E`/`$D01F` | PASS | neither register is read anywhere in the source |
| 5 | the fighter's death is drawn, not waited out | PASS | sprite 0 walks blocks 145-148 with `$D027` white→yellow→orange→red over 32 frames, `$D01C` bit 0 set for the blast and clear either side; `evidence/death-1..4.png`, `evidence/death.txt` |
| 6.2 | entrance waves off trajectory LUTs, no runtime trig | PASS | `traj.inc` generated; entrants settle to `enemy_state` = 1 |
| 6.3 | tractor beam, capture, rescue, freed captive | PASS | `plstate`=1, slot 47 EST_DOCKED, lives 3→2; rescue → `pldual`=1 |
| 6.4 | challenging stage: 40 sweep, never fire | PASS | `bullets_live` 0 for the whole sweep; `¡PERFECTO!` and the 10,000 bonus |
| 6.4 | transforming enemies, trio bonus | PASS | slots 40-42 EST_DIVE, shapes `$8E/$8F/$90`, 160 each and 1,000 for the trio |
| 6.4 | stage counter clamps at 255 and still plays | PASS | stage `$FF`, HUD reads 255, sweepers cross |
| 7 | 1.5 px/frame in 8.8, no 1-and-2 alternation | PASS | 60 ticks of held `A` moves `plx` exactly 90 |
| 8 | every score value fixed | PASS | all eleven exact: 50/100, 80/160, 150/400, carrier 150/800, transformed 160 (1,000/trio), captive 1,000, sweeper 100 |
| 8 | extra lives at 20,000 then every 70,000 | PASS | 20,000→4, 70,000→5, 140,000→6, 210,000→7 |
| 9 | every SID write shadowed | PASS | `evidence/sid-shadow.txt`, three moments, each byte named |
| 9 | the fighter's death does not sound like an enemy's | PASS | `SFX_PLDEATH`, priority 4, 32 gated noise frames sweeping freq hi `$30`→`$11` with AD `$0A`/SR `$05`, against the enemy's 24 frames at `$4F`→`$4A` with `$09`/`$00`; captured side by side (iteration 6) |
| 9 | effect priority: seize if ≥, drop never queue, music resumes | PASS | `evidence/audio/priority/` — voice 1 resumes at the position the sequencer would have reached; a priority-1 effect offered against a priority-2 holder leaves `vprio`/`vfx` untouched |
| 9 | theme ≥60s and loops seamlessly | PASS | 100 bars, 600 rows, 3,600 frames = 60.0 s; `evidence/audio/seam/` passes as one continuous phrase across the seam |
| 11 | no frame overruns its budget | PASS | `tick_overrun` = 0 across stage 1, stage 8 and two challenging sweeps (~7,400 ticks) |
| 11 | ≤64 changed cells per frame, outside a stage transition | PASS | `cells_peak` (a high-water mark the program keeps) **22** in steady play with a settled grid, **5** during the entrance. The stage-announcement screen rebuild reaches **72-88**, which is the case §11 exempts. |

### The one trade, stated plainly

§3 asks the multiplexer to carry **at least 16 sprite objects per frame**. It
carries **9** at peak, with ~10 entrants airborne and `mux_overflow` = 0.

The honest history matters here. The entrance was first thinned to
`ENTRY_STAGGER` 18 / `WAVE_GAP` 144 on the strength of overrun measurements
that were **invalid** — they were taken while the phantom-frame bug of
iteration 4 was live. With that fixed the density went back up to 12/120. The
full arcade 6/90, which is what reaches 16 concurrent objects, still does not
fit: that build profiles ~15.2k and runs ~20k with interrupts live, against
17,030.

§1 says *"when something has to give, it is never collision accuracy, timing,
or enemy behaviour — spend the visual detail instead"*, and entrance density
is behaviour, so this trade is against the spirit of the spec as well as the
letter. It stands on a maintainer ruling after play: the density reads well,
and gameplay busyness was judged the thing worth having over the raw count.
Closing it needs roughly 200 cycles per object out of `muxassign` (270/object),
`enemytick` (490/object) and the IRQ reposition path (~150/reposition).

### A measurement that nearly shipped wrong

The first `evidence/mux.txt` recorded a single sample of `mux_count` — 5 — while
this table claimed a peak of 8. A spot value cannot support a peak claim, so
the protocol now steps 300 ticks and records high-water marks. Doing that
exposed a second, worse instance of the same error: `cells_drawn` was being
sampled every tenth tick and reported **4**, because the counter spikes *only*
on the frames that repaint a formation row and a coarse sampler steps straight
over them. The program now max-tracks it into `cells_peak`, and the real
figures are the ones in the table above — including the 72-88 that turned out
to be the exempt stage rebuild rather than a violation. The lesson is the
prompt's own: a number is evidence only if the way it was measured could have
produced a failing value.

### The audio artifacts predate the shipped binary, deliberately

`evidence/audio/`'s five captures were taken at 12:13-12:16; the shipped
`la-galaxia.prg` is later. A re-capture against the final binary was attempted
four times and **could not be performed** — `c64 audio capture` times out on
this machine, which is `docs/todo.md`'s first open item ("VICE wedges at real
time with no recorder armed"). The mechanism is documented there:
`pinned_record_start` unwarps *before* arming the recorder, leaving a
real-time-no-recorder gap that wedges the monitor. Starting the session warped
avoids the wedge at session start but not inside the capture's own pin/arm
sequence.

The artifacts are nonetheless valid for this build, and the reason is
checkable rather than hopeful. Two changes have reached `sound.s` since they
were taken, and neither alters a byte of what the five windows recorded.
The first: `sfxstart` gained `stx sfxsavex` at entry and `ldx sfxsavex` at
exit, preserving the X register across the call. It writes no SID register and
alters no value written to `$D400-$D418`; what it fixes is which enemy slot
`enemytick` resumes from after a tractor-beam deploy. The second, in iteration
6: `SFX_PLDEATH` and its `fx_pldeath` routine, which are purely additive — one
entry appended to each of the four effect tables and a new routine after
`fx_explode`. Every existing effect routine and `music.inc` are
byte-identical, and none of the five windows fires effect 7. So the recording
the shipped program would produce is the recording that is committed.

Re-running `tools/audio-evidence.sh` when the capture path is healthy is the
way to refresh them, and the script now starts its session warped for the
reason above.

### Watch item

Challenging-stage sweeps are the tightest frames in the game: `tick_endline`
saturates at 255, i.e. the tick ends inside the frame's last ~8 lines. Zero
overruns across ~2,800 sweep ticks, but it is the state with the least margin
if anything grows.
