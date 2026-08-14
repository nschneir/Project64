# La Galaxia — the 1981 arcade fixed-shooter, recreated

Using the c64 CLI (see skills/c64-development/SKILL.md, the 6502-assembly
skill, and docs/cli.md), build the closest recreation of the 1981
Midway/Namco arcade game *Galaga* that a Commodore 64 can express — pure
6502 assembly with a BASIC SYS stub. That name appears here so you know
exactly which game's behaviour to study, and nowhere else in this
directory. Everything for this demo lives in `demos/la-galaxia/`.

**This is an homage, not a port — and that distinction is a hard
requirement.** The game is *La Galaxia*, and its cast is the **Drone**,
the **Sentinel**, and the **Flagship** — the arcade's Zako, Goei and boss
class, named here once so you know what to study and never again outside
this file. Every glyph, sprite, and note is yours: original character
art, original sprite art, an original three-voice SID score. What you
recreate from the 1981 arcade original is its *behaviour* — the rules,
the timing, the structure, the feel. Never its assets: no ripped
graphics, no transcribed tunes, and no arcade names on screen or in any
file but this one.

**All in-game text is Spanish.** The game is *La Galaxia*, and every
string the player sees follows it: the HUD labels, the stage
announcements, the challenging-stage result panel, the bonus award, the
game-over line, and the high-score table. Use short arcade-register
Spanish — `PUNTOS` for the score, `RECORD` for the high score, `NAVES`
for the remaining fighters, `ETAPA n` for the stage, `¡PERFECTO!` for
the perfect bonus, `JUEGO TERMINADO` for game over, `JUGADOR UNO`/`DOS`
for the player headers — and pick the rest yourself, consistently. The
custom charset is yours, so `¡` and accented letters are yours to draw;
draw them, or drop accents everywhere, but never mix the two.

**First, write the plan.** Before any code, turn this spec into
`demos/la-galaxia/PLAN.md` — ordered, independently verifiable steps,
each naming the observation that proves it — and build from that plan,
updating it as the running machine corrects you. Everything generated
along the way is committed: the plan, the sources, the audit and its
numbered iterations, the evidence PNGs, and the packaged disk.

---

## 1. What you are building

The arcade original ran on custom Namco hardware — 64 sprites and a
vertical monitor. The C64 gives you eight hardware sprites, no more than
eight on any one scanline, and a horizontal screen. Close that gap with
two techniques, and at every moment know which one is carrying each
object: **raster IRQ sprite multiplexing** for everything in motion, and
**character-RAM rendering** for the settled formation. The target is the
full 40-enemy formation on screen with the entrance waves, dives, capture
and rescue intact, and no frame that overruns its cycle budget (§11).

When something has to give, it is never collision accuracy, timing, or
enemy behaviour — those three are what makes this the arcade game.
Spend the visual detail instead, and record the trade in `PLAN.md`.

---

## 1a. The cold open

Before the title screen there is one more screen, and it is the first thing
anyone sees. It is **the only place in this game where the text is English**,
because it is the narrator speaking rather than the cabinet:

> In the back of a long shuttered Mexico City arcade, behind the broken
> pinball machines, sits a forgotten relic...

Set it **large** — four times the size of ordinary text, each 8×8 glyph
scaled to 32×32 pixels. That does not fit the character grid, so **this
screen is a hires bitmap** (`$D011` bit 5), the one place the game leaves
text mode; you already have the glyph bitmaps in the custom charset, and
scaling them is a blit, not a second font.

Scale them **smoothly**. Quadrupling each source pixel into a solid 4×4
block is the obvious blit and it is the wrong one: at this size every
diagonal and every curve in the font becomes a flight of four-pixel steps,
and the staircase is the first thing the eye finds on the first screen of
the game. **The 4× glyphs must be corner-interpolated, not block-scaled** —
run each one through an EPX/Scale2x pass, where a corner whose two
orthogonal neighbours agree with each other and disagree across the diagonal
is cut, so a diagonal comes out as a joined-up stroke instead of a stack of
blocks. Take the neighbours from the glyph's own 8×8 bitmap and treat
anything off its edge as background. Do the interpolation **at runtime, in
code**: a table of pre-smoothed 32×32 glyphs is 128 bytes each across the
whole alphabet, and §10's memory map has nowhere to put it.

Do the arithmetic before you lay it out. A 320×200 bitmap at 32×32 per glyph
is **10 characters per line and 6 lines per screen**, and the pinned line
below takes the bottom of every page, so the narration band is **four lines
at most**. The line above is 113 characters, and it is 100 drawn glyphs once
it is wrapped to fit — no line longer than ten. It therefore **cannot be one
static screen at that size**. Split it across pages that advance on a timer,
or crawl it; do not silently shrink the text to make it fit, and do not let
a word break across a page. Centre each page horizontally and sit it
**above** the vertical centre, nearer the top than the bottom.

The pages are the story's own pauses, so they are not a uniform length: the
wrap and the page breaks together give **five pages of fourteen lines**, the
first of them four lines and the rest three. Nothing in the layout may
assume a fixed number of lines per page.

Pinned at the bottom of every page, in Spanish like the rest of the game:

> COMIENZA TU VIAJE...

That is a closing flourish and not an instruction: it names no key, because
any key will do, and its ellipsis answers the narration's. It is twenty
characters, which is **exactly one row at 2×** — a 2× glyph is two columns
wide, so twenty of them fill all forty — so set it smaller than the
narration, give it one row rather than two, and keep it in the same place on
every page so it reads as part of the cabinet rather than part of the story.
A literal instruction was the other way to write this line and it does not
fit: *PULSA CUALQUIER TECLA PARA COMENZAR EL VIAJE* is 43 characters against
the 40 that even two 2× rows hold, and the third row it would need comes up
into the narration band. Do not spend rows of the story telling the player
what any key already does.

**Any key** leaves for the title screen at any point, including part-way
through the first page: a player who has seen it once must never be made to
sit through it again. Nothing on the screen says so — the pinned line is a
flourish now, not an instruction — so the behaviour has to be true of every
key rather than of a documented one. Any key means any key, not only the
keys §2 maps, so the skip is driven by a derived any-key-down signal rather
than by a bit of `input_state`, and it is edge-triggered, because the
attract loop walks back in here from the game over with whatever the player
was holding still held. The attract loop returns here, so this screen is the
top of the cycle, not a one-shot splash.

**Evidence:** `cold-open.png` — a page of the narration at full size with
the Spanish line beneath it, captured from the stopped machine like every
other frame in §13.

---

## 2. Controls & input

The engine reads three input sources every frame and folds them into one
normalized `input_state` byte. Everything downstream — the fighter, the
title screen, the stage select — reads that byte and nothing else.

| Action | Arcade control | Joystick (port 2) | Keyboard | `$CB` code | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Move left** | Joystick left | Left | `A` | 10 | Fighter is fixed to the bottom Y coordinate. |
| **Move right** | Joystick right | Right | `D` | 18 | Bounded by the playfield window (§4). |
| **Fire missile** | Fire button | Fire | `SPACE` | 60 | Two missiles in flight per fighter — four when dual. |
| **Start 1P** | 1P start | — | `SPACE` | 60 | Single-player game, from stage 1. |
| **Start 2P** | 2P start | — | `X` | 23 | Alternating two-player game. |
| **Skip the cold open** | Fire button | Fire | *any key* | any | §1a only, and the one action that is not a mapped key. |

The arcade's arrow controls are not mapped: the C64 has one horizontal
cursor key and reaching left requires SHIFT, so an arrow mapping would be
worse than `A`/`D`, not an alternative to it.

The last row is the exception that proves the rule, and it is deliberately
not an `input_state` bit. Everything else in this table is a *mapped*
control: the fighter, the title screen and the stage select read the
normalized byte and nothing else, and giving every key on the matrix a
meaning in that byte would give it a meaning in all three. The cold open
instead reads a signal derived beside `input_state` from the same three
sources — any key down anywhere on the matrix, any code in `$CB`, or the
joystick's fire button — and it reads the *edge* of it. So the cold open
answers to `Q`, and the title screen still starts a game on `SPACE` and `X`
and nothing else; the two claims do not overlap, because they are reading
two different bytes.

**The start keys are letters, not function keys.** `F1`/`F3` are the
obvious mapping of the arcade's start buttons and they were the first
choice here; they do not survive the trip from a Mac keyboard through
VICE's keymap, so a player cannot reliably start the game at all. `SPACE`
starts one player — it is already the fire key, so it is under the thumb —
and `X` starts two. `SPACE` doing double duty is safe because it only
starts a game from the title state, but the press that starts the game
must not also launch a missile on the first frame of play.

### The three input sources

1. **The keyboard matrix** (`$DC00` row select, `$DC01` column read) — the
   real control path, and the only one that reports two keys at once, so
   a player can move and fire in the same frame. Scan it yourself; no
   KERNAL call.
2. **`$CB`, the current-key byte** — folded in as an additional source,
   never written by the game. This is what makes the game drivable from
   the CLI: `c64 key hold` steers by re-poking `$CB` (§13), and a game
   that only scanned the matrix could not be driven at all. Read it,
   OR its decoded bits into `input_state`, and leave the byte alone.
3. **Joystick port 2** — CIA1 port A. It shares its pins with the
   keyboard row outputs, so sample it with all rows deselected (`$DC00`
   = `$FF`) and after the matrix scan, and treat a frame in which the
   stick reports a direction as authoritative over a phantom key on the
   same lines.

Decode each source in its own subroutine that takes the raw port byte in
`A` and returns normalized bits — the joystick path cannot be exercised
from the CLI (there is no joystick command), so its decoder must be
callable in isolation and proven that way (§13).

### Hidden keys — stage select

On the title screen only, the digit keys choose the stage a new
one-player game starts on: `1` through `9` start at stages 1–9, and `0`
starts at stage 10. Their `$CB` codes are 56, 59, 8, 11, 16, 19, 24, 27,
32, 35 in that order.

The chosen stage is the real stage number: the HUD shows it, the
difficulty tier of §6.4 applies to it, and play continues from there as
if the player had arrived normally. Score starts at zero, lives at the
normal starting count, and you begin as a single fighter — the stage
select grants nothing but the stage. `F1` still starts at stage 1.

They exist so a reviewer, and the evidence capture of §13, can reach the
first challenging stage and the transforming enemies without playing
there. They stay undocumented in-game — nothing on the title screen
mentions them — and they must be listed in the fidelity audit's evidence
section.

---

## 3. Render forty enemies on eight sprites

Three mechanisms, and the handoff between the first two is the heart of
the renderer:

1. **The settled grid lives in character RAM.** When enemies settle into
   the top formation they are written into the screen matrix at `$0400`
   as custom animated 2×2 character blocks, coloured per cell in colour
   RAM at `$D800`. Settled enemies cost no sprites.
2. **A diver becomes a hardware sprite.** When an enemy breaks formation,
   erase its 2×2 block in the same frame the sprite appears, and hand the
   object to the raster IRQ multiplexer. Reverse it exactly when the
   enemy settles back. The erase and the spawn must never straddle a
   frame boundary — an enemy that is briefly both, or briefly neither, is
   a bug the evidence will catch.
3. **The starfield is a character layer.** Draw the arcade's multi-layered
   parallax from custom star glyphs whose bitmaps you rotate — different
   layers a different number of rows per frame — which scrolls them for a
   handful of cycles and, unlike a fine-scroll register, leaves `$D011`
   and `$D016` free for the formation (§7). If you do drive the starfield
   from the scroll registers instead, it must own a raster band of its
   own: the formation and the starfield cannot both own the same register
   on the same scanline.

**The multiplexer, specified.** Rebuild a Y-sorted list of active sprite
objects once per frame and reposition the eight hardware sprites from
raster IRQs as the beam descends. It must carry at least **16 sprite
objects per frame** across the eight registers, with never more than
eight live in one raster band. Expose two bytes the audit can read:
`mux_count`, the objects displayed this frame, and `mux_overflow`, the
objects a band could not fit. `mux_overflow` must read zero throughout
normal play, including a stage-11 dive with escorts on screen.

---

## 4. Colour and the playfield window

The VIC-II outputs 16 colours. The arcade monitor is vertical, so centre
the play area in a **24-column window** (columns 8–31) and give the eight
columns on each side to the cabinet bezel and the HUD. The widest
formation row is ten 2×2 blocks — 20 columns — so it fits the window with
two columns of margin each side, and the fighter's travel is bounded by
the same window.

Draw the bezel as charset cells. The border register cannot do it: the
border is a fixed width and cannot mask screen columns.

| Game element | Arcade colour | VIC-II colour |
| :--- | :--- | :--- |
| **Background / space** | True black | `COLOR_BLACK` ($00) |
| **Screen border** | Black | `COLOR_BLACK` ($00) |
| **Player fighter** | White, red, blue | `COLOR_WHITE` ($01) / `COLOR_CYAN` ($03) |
| **Flagship** | Cyan, blue, yellow | `COLOR_CYAN` ($03), `COLOR_BLUE` ($06) |
| **Sentinel** | Red, yellow | `COLOR_RED` ($02), `COLOR_YELLOW` ($07) |
| **Drone** | Yellow, red, blue | `COLOR_YELLOW` ($07), `COLOR_RED` ($02) |
| **Tractor beam** | Translucent cyan | Multicolor sprite / `COLOR_CYAN` ($03) overlay |

`$D020` and `$D021` are only the border and the background. Sprite
colours live in `$D027-$D02E` with the two shared multicolour registers
at `$D025`/`$D026`; per-cell character colours live in colour RAM at
`$D800-$DBFF`. The two shared multicolour values are chosen once for the
whole cast — design the enemy art around that constraint rather than
discovering it later.

---

## 5. Sprites, and the sprite budget

A C64 sprite is 24×21 pixels; the arcade's are 16×16. Centre the 16×16
art inside the C64 sprite box so the sprite coordinate and the art
coordinate never drift apart.

* **Player fighter:** standard hi-res mode (one colour) for sharp edges,
  white, with an optional second hi-res sprite pinned to the same
  coordinates carrying the red/cyan accents. The overlay is a sprite, not
  a free effect — budget it, and drop it while the Dual Fighter is on
  screen.
* **Dual Fighter:** two hardware sprites clamped to identical
  Y-coordinates and spaced exactly 16 pixels apart horizontally.
* **Enemies (Drone, Sentinel, Flagship):** multicolour sprite mode —
  12×21 double-width pixels, three colours plus transparency per alien.
* **Flagship damage state:** starts cyan/blue. On its first hit the
  colour pointer swaps to `COLOR_PURPLE` ($04) and `COLOR_RED` ($02) and
  it stays alive; two hits destroy it.
* **Player death:** the fighter's own explosion, animated on its sprite
  at the position it died — not a vanishing fighter and not an unchanged
  one. Reusing the enemies' explosion shapes is fine if they suit, but
  mind the mode: those shapes are multicolour art and sprite 0 is hires
  for the fighter, so whatever draws the blast owns `$D01C` bit 0 for the
  duration and puts it back afterwards. Give the blast a colour of its
  own too — the enemies' explosions are already on screen by the dozen,
  and the player's own has to be told apart from them at a glance.

| Sprite | Assignment |
| :--- | :--- |
| 0 | Player fighter, or the left fighter when dual |
| 1 | Player accent overlay, or the right fighter when dual |
| 2–7 | Multiplexed: divers, transformed enemies, the tractor beam |

**Every state the fighter can be in has to draw something.** It has more
states than "flying": captured, dual, exploding, and whatever else your
design adds. A state whose whole implementation is a countdown looks
exactly like the game hanging, and the player who meets it will report a
freeze rather than a missing animation — they cannot see the difference,
which is the point. So when a state goes into the state byte, its frames
go in with it, and both the state and the shape it draws go into the
observable list (§13) so a test can read which one is on screen rather
than trusting that some frame somewhere shows it.

**Missiles and enemy bullets are character-space objects,** not sprites —
two missiles in flight per fighter and up to eight enemy bullets would
eat the multiplexer alive. Draw them with half-cell glyph phases so they
move in 4-pixel steps on the character grid, and keep all eight sprites
for the fighters, the divers and the beam.

**Collision is coordinate math, not the VIC-II latches.** `$D01E` and
`$D01F` report *which hardware sprite* collided, and under multiplexing
one sprite is a different object on every raster band — so the latches
cannot say which enemy was hit. Test missile cells against the character
grid for settled enemies, and against sprite coordinates for divers.

---

## 6. Rules, stage flow, and progression

### 1. The 40-enemy formation grid

The settled grid is exactly 40 enemies:

* **Row 1 (top):** 4 Flagships
* **Rows 2 & 3:** 16 Sentinels (8 per row)
* **Rows 4 & 5:** 20 Drones (10 per row)

### 2. Entrance waves

Each stage opens with the enemies flying on in 5 groups of 8 — 40 in
all. Drive them from pre-calculated sine/cosine trajectory lookup tables;
no runtime trigonometry, no multiply in the frame.

* **Wave 1:** drops from top centre, loops left and right.
* **Wave 2:** enters top left, loops down and up into formation.
* **Wave 3:** enters top right, mirroring wave 2.
* **Wave 4:** enters bottom left, circles upward.
* **Wave 5:** enters bottom right, circles upward into final position.

Entrants are live targets: an enemy shot during its entrance scores its
diving value (§8) and never reaches the grid. The stage proper begins
when the last surviving entrant settles.

### 3. The tractor beam and the capture

* A Flagship dives, halts above the player, and deploys the **tractor
  beam**.
* **Capture:** if the beam touches the fighter, the player loses control.
  The fighter spins, turns red, is drawn up to the Flagship, and docks
  above it — travelling with it back into the formation. The player loses
  one life. If it was the last life, the game ends there.
* **Rescue:** destroying that Flagship *in mid-flight* while it carries
  the fighter frees it, and the freed fighter docks beside the player's
  as the **Dual Fighter**: two fighters moving as one, firing two
  missiles per volley with up to four in flight.
* Destroying the Flagship while it sits in the static grid instead sets
  the captured fighter loose as an enemy that dives and fires at the
  player.
* A hit while dual destroys one fighter and costs one life; play
  continues with the survivor as a single fighter.

**Shot down.** A bullet or a collision destroys the fighter outright, and
that is the other way a life goes — the capture above is not the only
one, and a spec that details the capture animation while leaving this one
implicit gets a game where dying is the least eventful thing in it. The
fighter explodes where it stood (§5), the game holds while that plays,
and then the next one arrives. State in the spec how many frames the
blast runs, what is drawn in each, and how long the hold after it lasts:
dead time longer than the animation is dead time a player reads as a
freeze, so the two numbers are a design decision and not an accident of
whatever the timer happened to be set to.

### 4. Stage progression and difficulty

Difficulty scales enemy behaviour, speed, and firing rate as the stages
advance. **Challenging stages are stages 3, 7, 11, 15 … — every stage
where `stage mod 4 = 3`** — and the tiers below describe the ordinary
stages between them.

* **Stages 1 & 2:** base speed. Enemies dive singly or in pairs. Enemy
  bullets are sparse and slow (§7).
* **Stage 3 — first challenging stage:** 40 enemies sweep the screen in
  scripted patterns and never fire. Each hit scores 100; hitting all 40
  awards a **10,000 point perfect bonus** — `¡PERFECTO!` on screen. The
  stage ends when the last group has left the screen whether or not all
  40 are dead, and closes with a result panel showing the hit count and
  the bonus awarded.
* **Stages 4 through 6:** **transforming enemies** appear — certain
  Sentinels and Drones morph mid-dive into three distinct mini-enemies.
  Destroying all three of one trio pays a bonus (§8). Dive speeds rise
  15% over the base of §7.
* **Stage 7 — second challenging stage:** faster sweeps and different
  flight paths from stage 3, same scoring.
* **Stages 8 through 10:** enemies fire multiple shots during a dive, and
  escorts — two Drones flanking a Flagship — dive more often.
* **Stage 11 and up:** speed and bullet frequency sit at their maximum
  thresholds and stop rising; surviving leans heavily on holding the Dual
  Fighter. The stage counter is one byte and **clamps at 255** rather
  than rolling over — stage 255 must still play, with a formation, not an
  empty screen.

---

## 7. Timings and the frame budget

Everything is locked to a raster interrupt at `$D012`, one game tick per
frame, so updates are tear-free. **All the figures below are NTSC (60 Hz);
on PAL, scale every per-frame delta by 6/5** or the game plays 17% slow.
The evidence run (§13) and the shipped disk (§14) use the same standard.

| Quantity | Value |
| :--- | :--- |
| Player speed | 1.5 px/frame |
| Player missile speed | 4.0 px/frame |
| Enemy dive base speed | 2.0 px/frame (×1.15 from stage 4) |
| Enemy bullet speed | 2.0 px/frame at stages 1–2, rising to 3.0 by stage 11 |
| Enemy bullets in flight | 2 at stages 1–2, up to 8 from stage 8 |
| Formation breathe cycle | 128 frames, one full expand-and-contract |

Fractional speeds mean sub-pixel positions: keep each moving object's
position in 8.8 fixed point and derive the integer coordinate for the VIC
each frame. A 1.5 px/frame fighter that alternates 1 and 2 pixels is not
the same thing and will read as a stutter.

**Grid breathing.** The formation expands and contracts as a whole. The
rigid part of that sway — up to ±7 pixels — comes free from the fine
scroll registers `$D011`/`$D016` under a raster split confined to the
formation band, so the HUD and the bezel do not move with it. The
expansion and contraction proper cannot come from a scroll register,
which only translates: it is a redraw of the grid's character blocks at
new cell spacing, on the slow cadence above, and it is budgeted against
the redraw ceiling in §11.

---

## 8. Scoring

| Target | In the grid | Diving / mid-flight |
| :--- | :--- | :--- |
| **Drone** | 50 pts | 100 pts |
| **Sentinel** | 80 pts | 160 pts |
| **Flagship** | 150 pts | 400 pts |
| **Flagship carrying a captured fighter** | 150 pts | 800 pts |
| **Transformed enemy** | n/a | 160 pts each; 1,000 for a whole trio |
| **Captured fighter turned enemy** | n/a | 1,000 pts |
| **Challenging-stage enemy** | n/a | 100 pts; 10,000 for all 40 |

Every value above is fixed, not a range — each one is an assertion the
audit checks by reading the score before and after a kill.

**Extra lives** are awarded at 20,000 points, at 70,000, and every 70,000
thereafter. The thresholds live in a named table with a `dip_extra_life`
selector byte, the equivalent of the arcade's DIP switches; the audit
proves an award by writing the score to just below a threshold with
`c64 mem write`, stepping one frame, and reading the life count.

---

## 9. Sound — SID (MOS 6581/8580)

Push the SID to its **full potential** across all three voices (see the
c64-development hardware reference). A custom player, called once per
frame from the raster tick, runs the music and ducks it under the effects.

### The title theme

The attract screen carries a **theme song**, and it is the first thing
anyone hears, so treat it as a piece of music rather than a jingle.

**What it should sound like: 1960s sci-fi scoring played by a mariachi band
on acid.** Take the era's space-music vocabulary — the wandering theremin
lead, whole-tone and chromatic slides, tritones, the ominous held low
drone — and play it on a mariachi ensemble's instincts: bright trumpet
lead in parallel thirds or sixths, a *guitarrón* bass walking in twos, an
off-beat *vihuela* chop on the upbeats, the 6/8-against-3/4 *sesquiáltera*
lilt, and the *grito*-style rip up into a held note. Then bend it: let the
tuning drift and slide where a real band would land clean, let the pulse
width breathe until the trumpets sound seasick, let a phrase repeat one
beat too many, wander into a key nobody asked for and find its way back.
It should be recognisably festive and recognisably wrong at the same
time — a mariachi band scoring a flying saucer. Vibrato, portamento,
ring modulation and hard sync are the tools; use them.

Two hard requirements:

* **At least one minute long** before it repeats. Not a four-bar loop with
  variations — a minute of actual written music, with sections that go
  somewhere and come back.
* **It must loop seamlessly.** The end has to lead back into the beginning
  so that a listener who has not been counting cannot tell where the seam
  is. That is a compositional requirement, not a playback one: the last
  bar's harmony must resolve *into* the first bar's, the melodic line must
  hand over without a jump, and every voice's gate, envelope and pulse
  width must be in the state the opening expects — a note left sounding, a
  filter left swept, or a drifting index that has not been reset all
  announce the loop point as loudly as a gap would.

The theme owns all three voices while the title screen is up; nothing
ducks it there, because no effects play on the attract screen.

### Channel allocation

* **Voice 1 (lead / high-priority FX):** main melody, player laser fire.
* **Voice 2 (bass / mid-priority FX):** harmony, enemy dive whine,
  tractor beam hum.
* **Voice 3 (noise / low-priority FX):** explosions, the background grid
  march.

### Effect synthesis

* **Laser fire:** voice 1, triangle waveform, pitch swept from `$4000`
  down to `$1000` over 5 frames.
* **Explosion (an enemy):** voice 3, noise waveform (control register
  `$80`), sharp attack and exponential decay, the volume envelope
  carrying the fade.
* **Explosion (the fighter's own):** voice 3 as well, and it needs its
  own row in the effect table rather than a second use of the enemies'.
  The one event that costs the player something cannot sound like the
  event they have already heard fifty times in the same minute — so make
  it longer, lower, and give it a pitch sweep the enemies' explosion does
  not have, at the highest priority in the game so nothing can take the
  voice off it half way through. Say in the spec which of those the ear
  is meant to use, and prove it against the enemies' explosion rather
  than on its own: two captures side by side, or the register log of each.
* **Tractor beam:** voice 2, pulse waveform with dynamic pulse-width
  modulation and an arpeggio alternating two high notes every frame.

### Priority, stated as a rule

An effect seizes its voice only if its priority is greater than or equal
to that of whatever holds the voice now; a lower-priority effect is
dropped, never queued. When the effect's gate releases, the music resumes
on that voice at the position it would have reached had it never stopped
— the player keeps running silently, it does not pause.

### Shadow registers

The SID is write-only: `$D400-$D418` cannot be read back, so audio leaves
no trace a debugger can inspect. Every SID write MUST therefore be
mirrored into a 25-byte shadow block in RAM at the moment it is issued.
Those shadow bytes are the testable evidence for sound (§13) — without
them no claim about a waveform, an envelope, or a channel priority can be
proven.

---

## 10. Memory map and 6502 data structures

Forty enemies on a 1 MHz 6502 means **structure of arrays**, so every
per-enemy field is an `LDA absolute,X` away, never a pointer chase.

### Object pool

```assembly
; 40 formation slots plus headroom for transform trios and the
; captured fighter, which are live objects the formation never held.
FORMATION_SIZE  = 40
MAX_ENEMIES     = 48

enemy_state:    .res MAX_ENEMIES  ; 0=Dead, 1=Grid, 2=Diving, 3=Returning
enemy_type:     .res MAX_ENEMIES  ; 0=Drone, 1=Sentinel, 2=Flagship
enemy_x_lsb:    .res MAX_ENEMIES  ; X position (low 8 bits)
enemy_x_msb:    .res MAX_ENEMIES  ; X position (9th bit for VIC-II)
enemy_y:        .res MAX_ENEMIES  ; Y position
enemy_path_idx: .res MAX_ENEMIES  ; index into the trajectory LUT
enemy_hp:       .res MAX_ENEMIES  ; 2 for an undamaged Flagship, else 1
enemy_flags:    .res MAX_ENEMIES  ; b7 carries a captured fighter,
                                  ; b6 transformed, b5 escort of a Flagship
```

### Memory map

| Address range | Function / allocation |
| :--- | :--- |
| `$0000 - $00FF` | **Zero page:** game loop counters, pointers, multiplexer state. `$CB` is the current-key byte the input layer reads (§2) — do not reuse it. |
| `$0100 - $01FF` | **Stack.** |
| `$0200 - $03FF` | KERNAL workspace and vectors; the raster IRQ vector at `$0314` if the KERNAL stays banked in. |
| `$0400 - $07E7` | **Video RAM:** screen matrix — playfield grid, bezel, HUD. |
| `$07F8 - $07FF` | Sprite data pointers for the current screen base. |
| `$0801 - $08xx` | **BASIC SYS stub** — the program's entry point. |
| `$0900 - $17FF` | Game variables, trajectory LUT working set, SID shadow block. |
| `$1800 - $1FFF` | **Custom character set** (2 KB, 256 glyphs): font, static enemy blocks, starfield, bezel. It must sit here, not at `$0800`: the stub owns `$0801`, and in VIC bank 0 the chip sees character ROM at `$1000-$1FFF`, so nothing VIC-visible may live in that window. |
| `$2000 - $3FFF` | **Sprite data:** animation frames for the fighter, divers, transformed enemies, explosions. |
| `$4000 - $9FFF` | **Main engine RAM:** game logic, IRQ handlers, trajectory LUTs. |
| `$C000 - $CFFF` | Free RAM under no ROM — the safest home for the audio engine. |
| `$D000 - $D3FF` | **VIC-II registers.** |
| `$D400 - $D7FF` | **SID registers** (`$D400-$D418` written, and shadowed). |
| `$D800 - $DBFF` | **Colour RAM** — per-cell colour for the grid, HUD and bezel. |
| `$E000 - $FFFF` | **Audio engine** — SID playback and SFX data, *if* you bank the KERNAL out. |

**If you take `$E000-$FFFF`,** set `$01` to `$35`, install your own
hardware IRQ vector at `$FFFE/$FFFF`, and accept that the KERNAL's
keyboard scan stops maintaining `$CB`. The input layer still reads `$CB`
(§2) and still must not write it — with the KERNAL out, a value poked
there by `c64 key hold` simply persists, so the game stays drivable.
Otherwise put the audio engine at `$C000-$CFFF` and leave the KERNAL in.
Say in `PLAN.md` which you chose.

---

## 11. Performance rules

**Pace the game with the raster tick,** one game tick per frame, entered
from the `$D012` interrupt. Nothing outside the tick moves the world.

**Redraw only the character cells that changed** — never repaint the
playfield. Cap it: at most 64 cells per frame outside a stage transition,
which the breathing redraw of §7 and the settle/dive handoff of §3 both
have to fit inside.

**No ROM calls in the hot path,** and no runtime multiply, divide, or
trigonometry in the frame: trajectories come off the LUTs of §6.2, the
enemy fields off the SoA of §10.

**Know your budget.** An NTSC frame is 17,095 cycles (65 × 263); a PAL
frame is 19,656 (63 × 312). The multiplexer's reposition IRQs are taken
out of that before your tick sees a cycle. Know the measured cost of the
per-frame enemy update — it is the heart of the game — and record it in
the audit.

**Resolve collision before the multiplexer's first reposition IRQ of the
next frame** — not "inside VBLANK", which on a C64 is far too short to
hold a 40-enemy collision pass and would be an untestable requirement.

**Make the cost visible.** Write a distinctive colour to `$D020` at the
top of the tick and black at the end. The coloured band down the border
*is* the CPU cost of the frame, and `c64 screen --png --border` captures
it — that image is the evidence for this section. If the band ever wraps
past the bottom of the screen, the frame overran.

---

## 12. The improvement loop

A first playable build is the *start* of this demo, not the end. From
there, work in explicit numbered iterations, each one a full cycle:

1. **Evaluate** — drive the game deterministically (§13) and run a
   fidelity audit: walk every claim in this document and mark it PASS or
   FAIL with evidence from the running game, never from a reading of the
   source.
2. **Review** — do a detailed code review of the current build: inner
   loops cycle-counted, the per-frame enemy update and the multiplexer
   scrutinized, dead code and slack removed, and the feel compared
   against the arcade (entrance timing, dive pressure, how a capture
   reads, how the Dual Fighter handles).
3. **Improve** — fix every FAIL and act on every review finding.
4. **Re-verify** — prove each fix in the running game, re-capturing the
   affected evidence, before counting it done.

Log each iteration in `demos/la-galaxia/AUDIT.md` so progress is visible,
and keep looping until an iteration ends with every claim PASS and a
review that finds nothing worth fixing. Expect several cycles — "it runs"
and "it's the arcade game" are different claims.

---

## 13. Prove it deterministically

The emulator runs far faster than real time, so **La Galaxia** is never
verified by watching it. Drive it from the c64 CLI (`docs/cli.md`) and
sample it while the machine is stopped.

**Driving the machine.**

* **Input:** `c64 key hold <key> --at <tick_label>` for held controls —
  it re-pokes the matrix code into `$CB` before each tick, which is
  exactly why the input layer of §2 reads that byte. `c64 key type` is
  useless here: buffered keys never touch `$CB`, and this game calls no
  KERNAL input routine. Everything, including the start keys and the
  stage-select digits, goes through `c64 key hold`. Note that this game
  switches the KERNAL's keyboard scan off, so nothing in the machine ever
  writes 64 back to `$CB` — only the tool does: `c64 key hold` releases by
  default, poking 64 after its final tick. The `c64 mem write '$CB' 64`
  that follows every hold in the evidence protocol is a second poke of the
  same value, kept for readability rather than required.
* **The joystick path** has no CLI driver, so prove it in isolation:
  `c64 call <joy_decode> --a $6F` with the port byte you want, then read
  the normalized bits back out of `input_state` with `c64 mem read`.
* **Stepping:** expose a label at the top of the per-frame raster tick
  (§7) and advance with `c64 until <tick_label> --count N`, so every
  observation lands at a known point in the loop. Anchor rarer events
  with `c64 break add` on the routine that raises them, or `c64 watch
  add` on a state byte the game pokes, then `c64 wait --break`.
* **Sampling:** `c64 screen` for the HUD text, `c64 screen --codes` for
  exact glyph identity in the grid, `c64 mem read` for the enemy SoA
  arrays and the SID shadow block, `c64 sprite status` for the
  multiplexer's live sprites (`$D015`) and their coordinates. Text output
  cannot see hardware sprites — never claim a sprite works from
  `c64 screen` text alone.

**Required evidence.** Capture each checkpoint with `c64 screen --png
demos/la-galaxia/evidence/<name>.png --scale 2` while the machine is
**stopped** — a screenshot taken while it runs is a race — per
docs/graphics-and-sprites.md. These PNGs are committed
with the demo.

| File | What it must prove |
| :--- | :--- |
| `cold-open.png` | The cold open (§1a) — a page of the English narration at 4x in the hires bitmap, corner-interpolated rather than block-scaled, with `COMIENZA TU VIAJE...` pinned beneath it. |
| `title.png` | The attract/title screen, with `LA GALAXIA` on screen and the starfield running. Add `--border` so the bezel and border read correctly. |
| `entrance.png` | An entrance wave mid-flight (§6.2) — a group of 8 tracing its LUT trajectory before it reaches the grid. |
| `formation.png` | The 40-enemy grid fully assembled: 4 Flagships, 16 Sentinels, 20 Drones. Pair it with a `c64 screen --codes` dump showing the settled enemies really live in character RAM (§3.1). |
| `dive.png` | An enemy broken out of formation mid-dive, with `$D015` and `c64 sprite status` showing the hardware sprite that replaced its character block (§3.2). |
| `tractor-beam.png` | A Flagship hovering with the tractor beam deployed above the player (§6.3). |
| `dual-fighter.png` | The Dual Fighter after a mid-flight rescue — two sprites at identical Y, 16 pixels apart (§5). |
| `flagship-damaged.png` | A Flagship after one hit, its colour pointer swapped to purple/red, still alive (§5). |
| `stage-select.png` | The first frame of a game started by holding `4` on the title screen, HUD reading stage 4 — the hidden keys (§2) working. |
| `transform.png` | A transforming enemy's three mini-enemies in flight (§6.4) — reached with the stage select, `4`. |
| `challenging-stage.png` | Stage 3 mid-sweep, 40 enemies crossing without firing (§6.4) — reached with the stage select, `3`. |
| `perfect-bonus.png` | The 10,000 point `¡PERFECTO!` award after all 40 are hit on that stage. |
| `raster-time.png` | A `--border` capture mid-frame showing the `$D020` timing band of §11 well clear of the bottom of the screen. |
| `death-1..4.png` | The fighter's death blast (§5), one frame per shape of the animation, with `death.txt` beside them carrying the state bytes, the sprite pointer and colour, and the SID shadow that produced them. A lost life has to be visible in the frames and audible in the shadow — and the hit is worth staging rather than waiting for, since a life can also go to a capture, which is a different code path entirely. |
| `game-over.png` | The game over state after the last life is lost — `JUEGO TERMINADO` on screen. |

Alongside them, record the **SID shadow block** (§9) read with `c64 mem
read` at four moments — a laser shot, an enemy explosion, the fighter's
own death, and the tractor beam hum — showing the waveform and envelope
bytes this spec calls for on the voices it assigns them to, and, for the
two explosions, showing that they are not the same bytes. Record `mux_count` and `mux_overflow` (§3)
during the busiest dive you can stage.

**Audio evidence.** The shadow block (§9) proves a write was issued; it
cannot prove the melody is in tune or that a seized voice ever came back.
Capture the sound itself with `c64_audio_capture` (`c64 audio capture` from
the shell) and commit its five artifacts — `capture.wav`, `sid-log.jsonl`,
`piano-roll.png`, `spectrogram.png`, `report.md` — under
`demos/la-galaxia/evidence/audio/`: the title theme's opening, a capture
across a laser volley and an explosion, and one over the tractor beam. Write
a reference score (YAML) from your own music data and capture against it;
the report must pass.

The theme's **loop seam** (§9) needs its own capture, and it is the one
place where you must aim the window rather than just start recording.
A minute of music is two to three minutes of wall clock to capture, and
would prove nothing about the seam anyway — so drive the player to a few
seconds before the loop point (poke its row/pattern index, or `c64 until`
your tick label the right number of times), and capture a short window that
straddles it. Score that window as one continuous phrase across the seam:
if the score passes, the notes really do hand over, and the piano roll will
show whether any voice gated off or re-attacked where the music says it
should have sustained. Then read your piano roll the way you read the
screenshots above — a wrong contour, a missing voice, or bars that drift off
the rhythm are bugs — and read it specifically against the priority rule of
§9: an effect that takes a voice and never returns it shows up as a color
that stops and never resumes. Captures run with warp off, so keep each one
to the few seconds that carry the claim. The maintainer's listen of
`capture.wav` is the final gate;
skills/c64-development/references/audio-verification.md has the method.

The audit's evidence section must list the hidden stage-select keys
explicitly, so the next reader knows they exist and that the evidence
above used them.

Then write `demos/la-galaxia/test.yaml` — a deterministic regression spec
runnable with `c64 test run` — asserting the sprite enables at `$D015`,
the settled formation in screen RAM, the score and life counters, the
stage byte after a stage-select start, and non-zero SID shadows.

---

## 14. Ship it

When every claim passes, package the game so anyone with stock VICE can
play it: `c64 package` the source into `demos/la-galaxia/la-galaxia.d64`
with `--title "LA GALAXIA"` (the `.prg` lands beside it), and report the
exact run command `c64 package` prints — including the video-standard
flag, so the player gets the timing the evidence was captured under.

Nothing here is borrowed but the rules — and the rules are borrowed
exactly.
