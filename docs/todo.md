# TODO

Open items carried out of recent reviews and dogfood runs. Items are deleted
as they land — what was actually done is recorded in `CHANGELOG.md` and in git
history, so this file stays a list of work still open.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

Last triaged 2026-08-14, when a landing pass closed seventeen items in one
change (the fugue dogfood's six, the amiga_ball post-mortem's five that were
still open, and six older ones — `CHANGELOG.md`'s Unreleased section has the
inventory). Everything below survived that pass on a judgement call, and each
item now records the call so it is not re-litigated from scratch: some are
waiting on a maintainer decision, some are feature proposals that want their
own spec, and two were left because the fix costs more than the defect.

## `AUDIT.md`'s A13 cycle row is not reproducible as written

**Anchor:** `demos/1812/AUDIT.md` A13 — now only its last four figures:
`pickshape`, `xform`, `spanfill`, worst-case `drawshape`.

**Status:** open, and **narrowed to the half that was not measured**. `smul` and
`rnd`, the two figures the item was filed about, are **closed**: re-measured
blanked at `until drawshape --count 40`, `smul` is 111–151 over nine poked
operand cases (and `141` belongs to `−5, +7`, not to the both-negative case
previously recorded) and `rnd` is 29 or 38 and nothing between over 96 arrivals.
Both, with their command lines and the `--samples`-eats-its-own-inputs trap on
`smul`, are written into `AUDIT.md` under *A13's first two figures*. What is
struck from this item is that half.

**Triage 2026-08-14: left.** Three of the four figures need their inputs
constructed before they mean anything, and `drawshape`'s needs a worst case
re-established rather than re-read — a search, with its own criterion to agree
first. That is a measurement pass of its own, not a landing-pass edit.

**What's wrong now.** The four remaining figures are still bare single-arrival
numbers with **no recorded anchor**, which is the same defect one step less
obvious: `spanfill` in particular is the worked example in `docs/cli.md` of a
routine whose cost is set by span endpoints its caller writes and that
`--samples` never varies, so `4,384` is a reading of whichever span the program
happened to be holding — it moves when the anchor moves and reads as a
regression that nothing caused. `pickshape` and `xform` are the same shape of
claim. `483,327` is quoted as a *worst case*, which is a search result and not a
measurement: nothing records what was searched or how the worst case was
established.

**Fix direction (ruled, unchanged).** Every A13 figure records min/max/mean with
a sample count and the anchor it was taken at, never a bare number — and where
the routine's inputs come from its caller, the poked cases as well, the way the
`smul` half now does.

**How to verify.** Re-profile from the recorded command line and land inside
the recorded range.

## `demos/la-galaxia`'s `tick_overrun` assertion is a 1-in-8 coin flip

**Anchor:** `demos/la-galaxia/test.yaml:115`, the
`assert: { mem: "tick_overrun", equals: 0 }` step in the ordinary-stage block;
`tick_overrun` in `demos/la-galaxia/vars.s`.

**Status:** filed 2026-08-14 by the pass that fixed the fighter-movement coin
flip in the same spec — this is a **second, independent manifestation of the
same root cause** (the LFSR is seeded from the live raster at startup, so
every run plays a different game), discovered while verifying that fix: one
failure in eight otherwise-green runs, at a step the fix does not touch.

**What's wrong now.** `tick_overrun` is a lifetime counter of ticks that
crossed a frame boundary, asserted `equals: 0` mid-spec. On a
heavier-than-usual game (more objects live, more redraw), one tick can
legitimately cross and the counter reads 1 — measured:
`mem $4159 = 01 != 00`, 1 failure in 8 runs. A failure here reads as a
performance regression that nothing caused, exactly the misdirection the
fighter-movement flake produced before it was staged.

**Fix direction (not ruled).** Same two shapes as the fighter item had: pin
the LFSR seed for the whole spec (changes what the suite exercises), or scope
the claim — zero the counter after the staging pokes and assert it stayed
zero over a *known* window, the way `docs/graphics-and-sprites.md` §4 says a
per-frame budget mark must be scoped ("a lifetime mark carries every exempt
frame ever run"). The second matches how the mark is documented to be used.

**How to verify.** Ten consecutive `c64 test run demos/la-galaxia/test.yaml`
runs on an unchanged tree: 10/10, where today's measured rate predicts one
failure. And the scoped assertion must still fail when the tick genuinely
overruns — stage a heavy frame and watch it go red before trusting it.

## `index.html`'s 1812 alt text describes pixels nothing checks

**Anchor:** the three `alt=` strings in `index.html`'s demos section, on
`demos/1812/evidence/sec1.png`, `cannon.png` and `final.png`.

**Status:** open, and **latent rather than live**. All three strings were
checked against the retaken PNGs on 2026-08-12, by opening the images: the
Marseillaise capture is blue and red polygons over dithered blue, red and
white; the cannon capture has a white border around red, orange, yellow and
blue; the final canvas is blue, yellow, brown and white with a blue star in
it. Every claim held. What is filed here is the missing guard, not a wrong
sentence.

**Triage 2026-08-14: left, deliberately.** Both fixes cost more than the
defect today: the palette-pinning test needs a parser over `sections.s`'s
`secpal` plus the every-earlier-palette union rule, and de-colouring the
strings makes the alt text worse for exactly the readers it exists for. The
strings were re-verified against the current PNGs this pass (the evidence
protocol run retook `cannon.png` and `first-shape.png`; the three cited
frames' palettes did not change). Revisit when `secpal` next moves — that is
the trigger this item exists to survive.

**What's wrong now.** The strings make colour and content claims about
particular pixels, and those pixels are generated: `sections.s`'s `secpal`
decides the palette and `tools/evidence.sh` rewrites `evidence/` on every
run. Nothing connects the two ends — `grep -rn 'alt=' tests/` finds nothing,
and `tests/test_docs_demos.py` reads `index.html` only for the demo roster
and the description column, never for an image. A palette edit is not
hypothetical: the finale's has already moved once, and `sections.s:31-37`
records why. The next one retakes the PNGs and leaves the alt text describing
the previous ones, silently — and alt text is read by exactly the people who
cannot look at the image and notice.

**Fix direction (two, unranked).** Either pin the strings to the data — a
test that maps each 1812 `alt` to the section it captures and fails when it
names a colour outside that section's `secpal` row plus the sections before
it, since nothing is ever erased and earlier palettes stay on the canvas; or
take the colours out of the strings and describe structure instead
("overlapping dither-filled polygons filling the frame"), which is weaker alt
text but cannot go stale. The first keeps what makes the current strings
worth reading.

**How to verify.** Whichever is chosen, prove it fails: flip one byte of
`secpal`, re-run the guard, and confirm it goes red — a test that passes
against a palette the page does not describe is the same gap one file over.
Until then, anyone re-running `tools/evidence.sh` re-reads these three
strings against the images by hand.

## No capture can be anchored to the frame top, and every evidence PNG churns

**Anchor:** `docs/graphics-and-sprites.md` §5 (the churn note after the rules
table, which now carries both measurements) and §6 (the deferral);
`demos/1812/tools/evidence.sh` section 9 and its `rot-a/b/c.png`.

**Status:** open as a **missing primitive, and its reopen condition has been
met**. The deferral's own bar was "one instance is an inconvenience, two is a
missing primitive". The second instance arrived 2026-08-14, and it is worse
than the condition anticipated: not a second demo but a second *capture
class*. Three fresh sessions each running `run` → `until shapedone --count 1`
→ `screen --png` produced byte-identical machine state and litcount/checksum
and **three different PNGs** (md5s `196dcc3b…`, `d6ac4b33…`, `89d8c407…`),
differing in a band at y≈454-458 — so the churn §5 used to scope to
`call`-staged shots covers `until`-anchored ones too. The raster phase at a
given program label is not fixed across runs (it depends on where the load
and RUN landed), and `c64 screen --png` returns the rendered display, seam
and all. §5 and §6 were corrected this pass; what remains is the tool.

**What's wrong now.** Every committed evidence PNG in the tree is a moving
byte pattern with a fixed meaning: regenerating any demo's evidence dirties
the working tree with diffs that carry no information, and the discipline
that contains this (restore the churned files, quote litcount/checksum beside
the shot) is convention, re-learned per demo.

**Fix direction (unchanged from the original sketch, now queued rather than
watched).** A stop that needs no program label: `c64 until --raster N` with
`c64_until(raster=N)` beside it, or `c64 screen --png --at-frame-top` with
the same flag on `c64_screenshot`. Either way the operation goes in `ops.py`
and both front ends surface it, per lockstep. This is a CLI/MCP addition
with a spec of its own.

**How to verify.** Run any demo's `tools/evidence.sh` twice and diff the
PNGs: byte-identical, which today none of them are guaranteed to be — the
`until`-anchored measurement above is the regression test's shape.

## What the CLI prints, a document cannot cite

**Anchor:** `c64 test run --json`, `c64 package --json`, `c64 mem get` — all
three in `docs/cli.md`.

**Status:** open. Three independent gaps, all discovered while trying to turn a
command's output into something a tracked document could quote.

**Triage 2026-08-14: left as proposals.** All three change a documented
payload or output surface, and the house rule for that is a spec of its own
per addition (`AGENTS.md`: check `docs/cli.md` for an existing command first;
every addition lands on both front ends with tests and docs in the same
change). None is blocking: the workarounds — quote only asserted values,
stat the `.lbl`, do the byte arithmetic — are all in use and recorded where
they bit.

**What's wrong now.** *`c64 test run --json`* prints its step details to stdout
and nowhere else: there is no `--out FILE`, and the payload
(`{"passed": true, "tests": [{"name", "elapsed", "steps": […]}]}`) carries no
run id, timestamp, build hash or machine, so a redirect saves a file that
cannot say which build it ran against. Two runs of `demos/1812/test.yaml` here
were byte-identical in every `detail` string — the property that made the
numbers safe to quote — and nothing in the output would have told a later
reader that. The audit had to be rewritten to quote only values the tracked
`test.yaml` *asserts*, never one a step merely sampled. *`c64 package --json`*
reports `{"prg", "image", "title", "run"}` and no labels key, while the
assembly path rewrites the output's `.lbl` on every invocation; the gap is now
documented under that command, but the payload still cannot say the file moved,
and `evidence.sh` depends on the `.lbl` being in step with the `.prg`.
*`c64 mem get`* prints a 16-bit observable as space-separated little-endian
decimal — `mem get shapes 2` gives `234 2` — so the headline "746 shapes" that
`README.md` quotes appears nowhere in the evidence log and a reader has to know
the byte order and multiply. Same for `frames` (`216 39`) and `rng`.

**Fix direction (proposals, both front ends each).** `--out FILE` on
`c64 test run` with an `out` argument on `c64_test_run`, plus a header block in
the payload naming the program, its mtime or hash, the machine model and the
timestamp — enough that a saved run is evidence and not a transcript. A
`labels` key in the non-cartridge `c64 package` payload, matching the one the
cartridge payload already has, surfaced identically by `c64_package`. An opt-in
`--word`/`--dec16` on `c64 mem get`; its MCP counterpart is a width argument on
`c64_mem_read`, since `docs/cli.md` records that there is deliberately no
`c64_mem_get` tool.

**How to verify.** Each: run the command, and confirm the artifact it produces
answers "which build, on which machine, when" without a human adding it.

## A scored capture cannot be aimed, and no duration survives past ~341 frames

**Anchor:** `c64 audio capture` and `diff_score` in
`src/c64lib/sid_analysis.py`; `skills/c64-development/references/audio-verification.md`
(`## Known facts`, where the drift period is recorded).

**Status:** open, and **narrowed 2026-08-14 by a working workaround for the
aiming half**. The fugue dogfood aligned four mid-piece capture windows
without any new tool: its program sweeps voice 1's pulse width on a known
256-frame triangle, the log samples `$D402/$D403` every frame, so matching
the log's first sample (plus sweep direction from the second) against the
modelled sweep pins the window's true start exactly —
`demos/fugue/tools/genscore.py --align-log`, and
`demos/fugue/tools/audio-evidence.sh` uses it on every window. It uses no
pitch information, so it cannot launder a wrong note into a passing score.
The technique generalises to any program that publishes a deterministic
per-frame register ramp; it does not remove the wish for `--at-label`, but it
lowers this item's urgency from "every demo must reimplement its player's
reset as a poke list" to "a demo needs one modelled register ramp".

**What's wrong now.** *No origin.* `c64 audio capture` measures what arming
cost (`lead_in_frames`) but has no way to aim frame 0 at a musical moment;
`diff_score` compares event *n* against entry *n* and so needs the window's
opening tick known. *No tolerance.* `diff_score` compares durations with
exact equality. A jiffy-paced player and the sid log separate by a frame
every ~341 log frames, so a 15-second window drifts 2–3 frames and a
fully-durationed score fails on entries that are musically correct. Omitting
`frames` is legitimate and is what 1812 did — at the cost of every timing
claim the score might have made. (A raster-paced player does not drift —
fugue pinned every duration over 900-frame windows — so the tolerance gap
bites jiffy-paced players only.)

**Fix direction (proposals, both front ends each).** `--at-label REF` on
`c64 audio capture`, with `at_label` on `c64_audio_capture` — or, better,
letting `c64 until` hand the stopped machine straight to a capture, so the
window opens on a label the program itself defines. And a drift tolerance:
either per entry in the score schema (`frames: 56, tolerance: 2`) or per run
(`--drift N` / a `drift` argument on the MCP tool), so that a duration can be
asserted at all over more than a few hundred frames of jiffy-paced playback.

**How to verify.** Score a 15-second jiffy-paced passage with every `frames`
pinned and have it pass — which today it cannot, and which is the point.

---

The four items below are the browser-play plan's deferrals, filed 2026-08-13
as that plan finished. Each carries its evidence inline on purpose: the
research that produced them lived in that plan's SDD workspace, which is
deleted with the plan, so an item that merely cited it would resolve to
nothing. All four were re-triaged 2026-08-14 and left: two wait on maintainer
decisions this file cannot make, one is upstream's code, and one is a
recorded dependency with nothing to do while it works.

## The demos are proved on Commodore ROMs and shipped on open ones

**Anchor:** `demos/{snake,invaders,ms-muncher,la-galaxia}/test.yaml` and
`c64 test run`; `play.html`'s `KERNAL_ROM_URL` / `BASIC_ROM_URL` /
`CHARSET_ROM_URL` constants.

**Status:** open, and **narrowed to the general case**. The specific
dependency that bit — input read from `$CB` alone — is now guarded:
`tests/test_docs_demos.py::test_no_demo_takes_its_input_from_the_kernal_alone`
fails any demo on the play page's roster that reads `$CB` without also reading
the keyboard matrix at `$DC01`, which is hardware and answers on any ROM.
Proved by stripping snake's matrix reads and watching it go red. What is left
is the wider risk this item was filed about: some *other* KERNAL routine
open-roms does not implement.

**Triage 2026-08-14: left — blocked on the decision it names.** The smoke
check needs the open ROM images reachable from a test run, and they
deliberately do not live in this repo. That is a maintainer call about
vendoring or fetching third-party ROMs into the dev loop, and no check worth
having exists on this side of it.

**What's wrong now.** Every demo's regression suite runs under VICE, which reads
ROM bytes from the emulator the developer installed — Commodore's. `play.html`
boots the same programs on MEGA65 open-roms instead. Nothing exercises the
second set. open-roms is not cycle-exact with the Commodore KERNAL and its BASIC
is deliberately incomplete (that project's own `STATUS.md` says so), so a change
that starts calling a KERNAL routine these demos currently avoid would pass
`c64 test run` and break the play page silently. Today they use only `RUN` +
`SYS` and then take the machine over, which is the whole reason the open ROMs
work at all; nothing enforces that they keep doing so.

The gap is wider than "CI does not cover it": `.github/workflows/` holds
`release.yml` and nothing else, so the demo suites are not run by CI at all.
Whatever closes this has to be a check a person or a hook actually runs.

**Fix direction (not ruled).** The remaining shape is the real one: a smoke
check that boots each `.prg` to its first playable frame on the open ROMs and
asserts the same screen the `test.yaml` first step does. It needs the open ROM
images reachable from a test run, and they deliberately do not live in this
repo — which is the decision this item is still waiting on. The narrow guard
above is not a substitute: it knows about one byte.

**How to verify.** Whatever is built, the check must fail when a demo starts
depending on the Commodore KERNAL. A cheap proof it works: point it at a demo
patched to `JSR` into a KERNAL entry open-roms does not implement, and confirm
it goes red while `c64 test run` for that demo stays green.

## The play page's system ROMs are an untagged dev build

**Anchor:** `play.html`'s `ROM_BASE` and the three ROM constants; `roms/README.md`
in the `nschneir/vc64web.github.io` fork, which holds the sha256 pins.

**Status:** open, accepted knowingly at ship. Not a defect — a dependency with no
stability guarantee, recorded so it is a decision and not a surprise.
Re-triaged 2026-08-14: unchanged; its own fix direction says there is nothing
to do while the page works.

**What's wrong now.** The KERNAL, BASIC and CHARGEN images come from
<https://github.com/MEGA65/open-roms> `master`, directory `bin/`
(`kernal_generic.rom`, `basic_generic.rom`, `chargen_pxlfont_2.3.rom`). That
repo has **no tagged releases**. The binaries self-identify at boot as
`OPEN ROMS GENERIC BUILD / RELEASE DEV.210823.FC.1` — a development build dated
2021-08-23, while the repo itself is still active. So the play page's system
software is a five-year-old snapshot of a moving branch, and there is no release
cadence to follow when picking up a newer one.

What protects us is the vendoring: the bytes are copied into the fork and pinned
by sha256 there, so upstream rebuilding `bin/` cannot change what a visitor
boots. What is unprotected is the other direction — if that build turns out to
have a bug, there is no upstream release to move to, only another untagged
commit. `bin/README.md` also forbids mixing BASIC and KERNAL from different
builds, so any refresh has to move both together.

**Fix direction (not ruled).** Nothing to do while the page works. The item
exists so that a future "just update the ROMs" is done as a matched pair, with
the sha256 pins and the build string re-recorded in the fork's `roms/README.md`.

**How to verify.** Boot the play page and read the BASIC banner: the build
string on screen must match the one recorded in the fork's `roms/README.md`.
If they ever disagree, the pin was bypassed.

## The tile art was rendered on a character ROM the play page does not use

**Anchor:** `play.html`'s `DEMOS` registry `image:` fields —
`demos/{snake,invaders,ms-muncher}/evidence/title.png`.

**Status:** open as a decision, not as a bug. Cosmetic; layout is identical.
Re-triaged 2026-08-14: left — the choice between accepting the drift and
giving the play page its own tile art is the maintainer's, and re-capturing
`evidence/` itself remains the one option that is wrong (those PNGs are cited
by each demo's `AUDIT.md`).

**What's wrong now.** snake, invaders and ms-muncher each copy the full 2 KB
character ROM into RAM and patch only their own glyphs, so every character they
did *not* redefine — all their prose text — is drawn from whichever CHARGEN is
installed. The committed `evidence/*.png` files were captured under VICE on
Commodore's CHARGEN; the play page runs on open-roms' PXL font. The tile
thumbnail and the preview still frame therefore show a typeface the visitor will
not see once the machine boots. Letterforms differ; character cells, colours and
layout do not, so nothing misleads about the game itself. (la-galaxia is
unaffected — it builds its charset from scratch.)

**Fix direction (not ruled) — this is the decision to make.** Either accept the
drift, on the grounds that `evidence/` is the demos' proof-of-work captured on
the reference machine and should not be re-shot to flatter a web page; or give
the play page its own tile art captured on the shipping ROM set, kept beside
`play.html` rather than inside `evidence/`, so the audit trail stays untouched.

**How to verify.** Open the play page, boot any of the three, and compare the
running title screen with its own tile: same words in the same cells, different
letterforms. That is the whole of the defect, and it is the check.

## Every player mount leaks a `resize` and an `orientationchange` handler

**Anchor:** the fork's `js/vc64web_player.js` — `load_into()` at `:208` and
`:219` against `stop_emu_view()` at `:362-377`; `play.html`'s
`teardownPlayer()`.

**Status:** open, **upstream residue, and outside what this page can fix.** The
plan's "switching must not leak" contract was about iframes and it holds —
measured 0 iframes and 0 `#player_container`s after switching, and the state
poller is stopped on both teardown paths. Re-triaged 2026-08-14: left — the
fix belongs in the fork's player script, and the one reach this page has
(`jQuery(window).off(...)`) would drop handlers the page does not own and
break silently the day the page registers one through jQuery.

**What's wrong now.** `load_into()` runs `$(window).on('resize', …)` and
`$(window).on('orientationchange', …)` on *every* mount, and `stop_emu_view()`
removes only `document`'s `click` listener. Neither `resize` handler is ever
taken off, so k boots leave k pairs attached to `window`. Each closes over
`load_into`'s scope, which holds `element` and `emu_container` — the detached
preview subtree — so this retains DOM, not just duplicate work.

The visible symptom is small and bounded, which is why it is filed rather than
worked around: `$vc64web` is assigned inside `load_into` **without `var`**, so
it is one global that each mount overwrites, and all k handlers therefore
resize the same live iframe. Behaviour stays correct; the cost is k height
writes and k 130 ms timeouts per window resize, on a page where k is the number
of games the visitor has tried.

**Fix direction (not ruled).** It belongs in the fork: `$(window).off('resize
orientationchange')` at the top of `stop_emu_view()`, or — better, since the
host page may own handlers of its own — namespaced registration
(`.on('resize.vc64web', …)`) with the matching `.off('.vc64web')`.

**How to verify.** With the player live, boot and stop three times, then read
`jQuery._data(window, "events").resize.length` in the console: 3 today, 0 once
`stop_emu_view()` unregisters.

## The fork will republish a GPL-3.0 emulator with no licence text

**Anchor:** `LICENSE`'s "Third-party components" section; `play.html`'s
`EMU_BASE`; the `nschneir/vc64web.github.io` fork — `vc64.wasm` (2,062,000 B)
and `vc64.js` (198,736 B) at its root.

**Status:** open, **contestable, and the maintainer's call** — filed so the
call is made rather than inherited. Not introduced by this branch: the fork's
one local commit (`a5cddb6`) adds `roms/` and nothing else, so everything else
is upstream's tree as forked. Re-triaged 2026-08-14: left — the fix lives in
a different repository under the maintainer's account, and options 1-3 below
are precisely the decision this file cannot make. Flagged again in the
landing pass's report.

**What's wrong now.** vc64web is a WebAssembly build of VirtualC64, which is
GPL-3.0 — this repo's own `LICENSE` is where that is written down. The fork
carries no copy of that licence: `git ls-tree -r --name-only 5700ccd` (the
upstream commit the fork sits on) matches **zero** paths against
`licen|copying|gpl`, and the fork's `README.md` — 33 bytes, "# deployment repo
of the vc64web" — and its `index.html` mention neither a licence nor a
copyright holder. The only licence text anywhere in the fork is
`roms/LICENSE-open-roms.txt`, which we added and which covers the ROMs only.
Serving `vc64.wasm` from GitHub Pages under this account is distribution of a
GPL-3.0 binary, and GPL-3.0 §4 asks a distributor to keep the notices intact
and give recipients a copy of the licence.

What is genuinely there, and cuts the other way: the served `index.html` links
`https://github.com/vc64web/virtualc64web` — the corresponding source — though
it does so in a support line ("If you see an issue please contact us at github
issues"), not as a source offer. So a reader can reach the source from the page;
what is missing is the licence text and any statement that this build is
GPL-3.0 and where its source is.

Do not overstate this: the upstream project distributes in exactly this state,
nothing here has been redistributed yet (the fork is unpushed), and no claim is
made about whether the omission is material. What makes it *ours* to decide is
that this branch's `LICENSE` is what points readers at the fork and names the
GPL-3.0 — we describe the arrangement, so we are on the hook for it being
describable.

Adjacent, and probably resolved by whatever is decided here: `play.html`'s
footer says the emulator is "served from its own site — not bundled" and links
`https://vc64web.github.io/`, while `EMU_BASE` actually serves it from *our*
fork. `LICENSE` states the arrangement correctly; the footer's "its own site"
does not. If the ruling below points `EMU_BASE` back at upstream the sentence
becomes true again, so the two are worth deciding together.

**Fix direction (not ruled — three options, cheapest first).**
1. Add the GPL-3.0 text as `LICENSE` at the fork root and three lines to the
   fork's `README.md`: what the binaries are, that they are GPL-3.0, and the
   upstream source repository with the commit they were built from. Fixes it
   where the distribution happens and costs nothing here.
2. Point `EMU_BASE` back at `https://vc64web.github.io/` and keep only `roms/`
   in the fork — removes this account from the redistribution chain, at the
   cost of the version pinning and the same-origin ROM hosting the fork exists
   for. (`play.html`'s ROM constants are already independent of `EMU_BASE`
   only by convention; both derive from it today.)
3. Decide the omission is immaterial for a fork of a project's own deployment
   repo, and record that decision here so it is not re-litigated.

**How to verify.** In the fork, `git ls-tree -r --name-only HEAD | grep -icE
'licen|copying'` returns at least the root licence, and once Pages is live
`curl -sI https://nschneir.github.io/vc64web.github.io/LICENSE` returns 200.
For option 2, `grep -c 'nschneir.github.io/vc64web' play.html` returns 0.
