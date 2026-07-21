# Invaders in 6502 assembly *(dogfooded 2026-07-11; the first attempt passed its audit but shipped a model-dependent keyboard bug — fixed after one follow-up prompt, see demos/invaders/AUDIT.md iteration 3)*

Paste this prompt into your agent:

> Using the c64 CLI (see skills/pet-development/SKILL.md, the 6502-assembly
> skill, and docs/cli.md), build the closest recreation of the 1978 arcade
> Space Invaders that a PET 4032 can express — pure 6502 assembly with a
> BASIC SYS stub, fitting comfortably in 32K, drawing directly to screen
> memory at $8000 (40×25). The PET has no bitmap mode and one square-wave
> voice; where the arcade does something the hardware can't, pick the
> nearest character-set approximation and say so. The keyboard replaces the
> arcade controls: A/D held down move the laser base, space fires.
>
> **The arcade spec — recreate each of these faithfully:**
>
> - **Formation** — 5 rows of 11 invaders in three classes: top row worth
>   30 points, next two rows 20, bottom two rows 10 (990 points per wave).
>   Every invader alternates between two shapes as it marches — choose PET
>   graphics-character pairs that make the three classes visually distinct.
> - **The march** — use the authentic engine: move ONE invader per tick,
>   sweeping the formation in order (the arcade updated one alien per
>   frame). The formation steps sideways; when any live invader touches an
>   edge it drops one row and reverses. The famous speed-up as invaders die
>   must be *emergent* from the one-per-tick engine — fewer invaders means
>   the sweep completes sooner — never a scripted speed table. The final
>   invader should be visibly frantic.
> - **Player** — one laser base on the baseline, three lives, an extra
>   life at 1500 points, and only one player shot on screen at a time.
> - **Bombs** — up to three invader bombs in flight, dropped from the
>   lowest live invader in a column, in the three classic flavours: slow
>   straight, fast straight, and the wiggly one. A bomb and the player
>   shot cancel each other when they collide.
> - **Shields** — four bunkers between the base and the formation that
>   erode piecemeal under fire from BOTH sides. Character-granular erosion
>   is fine; better still give each cell damage states (solid →
>   checkerboard → gone) so bunkers crumble rather than vanish.
> - **Mystery UFO** — crosses the top of the screen periodically with its
>   own warbling sound, worth 50–300 points — and implement the real
>   arcade secret: it pays 300 when hit by the player's 23rd shot, then by
>   every 15th shot after that. Count the shots.
> - **Waves** — wave 1 starts high; waves 2 through 9 start one step
>   lower each time; wave 10 resets to wave-1 height. The game ends when
>   the lives run out or any invader reaches the baseline.
> - **HUD** — SCORE, HI-SCORE, WAVE, and remaining lives always visible.
>   The high score must survive across games in the same session.
> - **Title screen** — the game's name drawn large with PET graphics
>   characters, a SCORE ADVANCE TABLE listing the point values of the
>   three invader classes and the UFO's `? MYSTERY`, and "PRESS ANY KEY
>   TO PLAY".
> - **Sound** — the VIA CB2 voice (ACR $E84B, shift register $E84A, T2
>   $E848; see the pet-development hardware reference). The four-note
>   descending bass heartbeat must be locked to the march tempo so it
>   accelerates naturally as the formation thins; add distinct shot,
>   invader-hit, player-explosion, and UFO effects. One voice, so define
>   priorities: effects interrupt the heartbeat, and the player's own
>   explosion outranks everything.
>
> **Performance rules.** Pace the game with the jiffy clock. Redraw only
> the cells that changed — never repaint the whole screen. No ROM calls in
> the hot path (keyboard read excepted). Know the cycle cost of your
> per-tick invader update; it is the heart of the game. For input, read
> the live key-down state at $97 (the IRQ scanner maintains it) so a held
> A or D moves continuously while space fires — GETIN's buffered keys
> would stall movement during fire.
>
> **The improvement loop.** A first playable build is the *start* of this
> demo, not the end. From there, work in explicit numbered iterations,
> each one a full cycle:
>
> 1. **Evaluate** — play the game deterministically (see the proof
>    protocol below) and run a fidelity audit: walk every bullet of the
>    spec above and mark it PASS or FAIL with evidence from the running
>    game, never from reading the source.
> 2. **Review** — do a detailed code review of the current build: inner
>    loops cycle-counted, the per-tick invader update scrutinized, dead
>    code and slack removed, footprint checked against 32K, and gameplay
>    feel compared against the arcade (march rhythm, bomb pressure,
>    speed-up curve).
> 3. **Improve** — fix every FAIL and act on every review finding.
> 4. **Re-verify** — prove each fix in the running game before counting
>    it done.
>
> Log each iteration's audit results so progress is visible, and keep
> looping until an iteration ends with every spec bullet PASS and a
> review that finds nothing worth fixing. The only acceptable permanent
> FAIL is a documented PET hardware impossibility (say what the arcade
> does, why the PET can't, and what you approximated instead). Expect
> this to take several cycles — "it runs" and "it's Space Invaders" are
> different claims.
>
> **Prove it deterministically.** The machine runs far faster than real
> time, so drive it like the debugger demo: inject buffered keys with
> `c64 key type`, hold a key by writing its key code to $97 with
> `c64 mem write` before each step (the IRQ scanner rewrites $97 every
> tick, so re-poke it each frame), and step the game with `c64 until` on
> your per-tick label, reading the screen between frames. Show me: the title
> screen; the formation marching and animating; a shield eroding; bombs
> of different flavours in flight; the UFO crossing; the CB2 registers
> ($E848/$E84A/$E84B) captured mid-heartbeat, since you can't hear; wave
> 2 starting lower than wave 1; a game over; and a second game whose
> HI-SCORE is the first game's final score.
>
> **Ship it.** When everything passes, package the game so anyone with
> stock VICE can play it: `c64 package` your source into
> `invaders.d64` with `--title "INVADERS"` (the `.prg` lands
> beside it), and tell the user to run `x64sc -model 4032 invaders.d64` —
> the model flag matters: $97 holds decoded PETSCII on the BASIC 4
> machines, but a raw matrix index on BASIC 2, so a stock-default model
> can leave the controls dead. On a real keyboard, the $97 scan then
> gives them exactly the held-key controls you tested.

**What success looks like:** an assembled program with a BASIC SYS stub
and the full arcade loop — attract screen → waves → game over → attract —
plus the one-invader-per-tick march engine (so the speed-up is emergent),
eroding shields, three bomb types, the UFO shot-count secret, and a CB2
heartbeat that audibly quickens; then a written fidelity audit with every
spec bullet marked pass (or argued impossible on PET hardware), the
deterministic evidence trail above, and finally an `invaders.d64` the
user can autostart in stock VICE and play with A/D and space. This is the
toughest demo in the set — expect the agent to live in the debugger and to
spend several review cycles closing the gap between "it runs" and "it's
Space Invaders."
