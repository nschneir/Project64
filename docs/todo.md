# TODO

Open items carried out of recent reviews and dogfood runs. Items are deleted
as they land — what was actually done is recorded in `CHANGELOG.md` and in git
history, so this file stays a list of work still open.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

Recreated 2026-08-12 by the 1812 iteration-3 pass. The first items are that
pass's deferrals; everything from *A capture staged with `c64 call`* onward is
its toolchain post-mortem (`AGENTS.md`, "Dogfood post-mortems"), triaged from a
friction log kept while the work happened rather than remembered after it.
Every proposal below names **both front ends**, because a CLI proposal without
an MCP counterpart is not a proposal (`AGENTS.md`, "Code quality").

Everything from *`c64 sprite png` and `c64 screen --png` disagree about the
palette* onward is what remains of the **amiga_ball dogfood's** post-mortem
(2026-08-14), kept the same way. It filed thirteen; **eight landed on
2026-08-14** and were deleted per the rule above — the uncorrected-raster
caveat and the palette divergence are now in `docs/graphics-and-sprites.md` §3,
the scanline-flush rule is a sixth row of its §5 table, `hardware.md` gained a
frame-budget table and the `$D012` wrap constraint, `docs/cli.md` gained the
`c64 profile`-cannot-price-an-IRQ note and lost its zsh driver example, and the
cookbook gained two live-tested recipes (the per-frame raster high-water mark
and 8.8 fixed-point motion).

The through-line is worth keeping even as the items go: nearly all of them were
about the *instruments* rather than about the C64. The demo's own defects were
caught by the machine within minutes each; what cost time was evidence that
looks conclusive and is not — a PNG that makes a round ball elliptical, a
report that cannot say whether it checked anything, two renderers that disagree
about a colour, and a shipping checklist that exists only as a red suite.

## A plan deliverable was destroyed by the SDD workspace cleanup

**Anchor:** the preamble directly above this item;
`superpowers:subagent-driven-development`'s "Finish" step
(`rm -rf <workspace>`); `.superpowers/sdd/<plan>/`.

**Status:** happened once, on 2026-08-12, and cost a real artifact.

**What's wrong now.** The 1812 baseline plan's Task 1 produced
`baseline-report.md` — every profiled routine with the exact command line
beside it, which *is* that task's deliverable. It was written into the
arrangement plan's SDD workspace because that plan ran it as a prerequisite.
When the arrangement plan finished, the skill's cleanup step deleted the
workspace, and the report with it. The figures survived only because they had
been relayed into the conversation; the per-command detail did not.

This file's own preamble anticipated exactly this and was not heeded — the
ledger is scratch, and anything a plan *owes* must leave it before it is
deleted.

**Fix direction (ruled).** Anything that is a deliverable rather than process
bookkeeping gets written outside `.superpowers/` at the moment it is produced,
and into a path **git actually tracks**: the repo's own docs (`docs/*.md`, a
demo's `AUDIT.md`/`SPEC.md`/`README.md`), `CHANGELOG.md`, or this file for
friction. Treat the workspace as strictly scratch. A prerequisite run for a
*sibling* plan writes into the sibling's workspace, never the caller's.

`docs/superpowers/decisions/` is **not** a durable home and this ruling used to
name it as one: `.gitignore` excludes `docs/superpowers/` wholesale, so a report
filed there escapes the workspace deletion only to die with the checkout —
the same loss one step later. It is a usable shelf for raw measurement data
(`.jsonl`, driver scripts, logs) that a *tracked* document then quotes with its
figures carried over; it is not somewhere a tracked file may cite as if the
reader could follow the reference.

**How to verify.** Before any `rm -rf` of an SDD workspace, list what the plan
owed and confirm each artifact exists somewhere the deletion cannot reach —
`git ls-files <path>` naming the file, not merely `ls` finding it.

## `AUDIT.md`'s register table still reads the pre-texture-arc arrangement

**Anchor:** `demos/1812/AUDIT.md`'s "each section is playing the material it
was written to play" table — the `40 | hymn` and `2600 | Marseillaise` rows.

**Status:** open, and **all that survives of "`main` ships source citing
documents that do not yet say what it claims"**. That item's other three
anchors are closed. `sections.s:103` cites `SPEC.md` §6.4 for the texture arc
and §6.4 now spells it — "The texture arc is the design, not a side effect of
the voice count. The piece opens on one instrument and gains them — 1 → 2 → 3 →
2 + artillery → 3 → 0". `test.yaml:82` cited **A15** "which does not exist";
§12 now has both A15 and A16, and the block underneath it asserts A16's
subject (`sidshadow+6 & $f0 == 0`), so the citation was corrected to A16 rather
than left resolving to the wrong criterion. `SPEC.md` §6.6's "112-frame
intervals" now reads "112 is the duration, not the interval… the shots arrive
113 ticks apart", which is what `music.s:717-727` has said all along.

**What's wrong now.** The table's first two rows are iteration 2's measured
registers. It records the hymn as `E4 triangle | B3 triangle | E2 pulse` and
the Marseillaise's voice 1 as `D5 pulse`, while `SPEC.md` §6.4 now specifies a
pulse piano for the hymn (both hands on a byte-identical instrument row, voice
3 silent) and a sawtooth reed for the Marseillaise, and `test.yaml` asserts the
hymn's shape directly — `sidshadow+4 & $41 == $41` (v1 pulse, gated),
`sidshadow+11 & $41 == $40` (v2 silent), `sidshadow+14 == 0,0` (v3 never
sounded). The audit's own table contradicts the test one file over.

**Why not here.** Every cell is a register read at a named frame on a stopped
machine, so correcting it means re-taking the readings at frames 40 and 2600,
not re-wording them — a VICE run, which is more than a triage pass can verify.

**How to verify.** Stop at each frame the table names, read `sidshadow` back,
and decode; then re-grep every `SPEC.md`/`A<N>` citation in `demos/1812/*.s`
and `test.yaml` and confirm each still resolves to text that agrees with it.

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

**Why not here.** Three of the four need their inputs constructed before they
mean anything, and `drawshape`'s needs a worst case re-established rather than
re-read — a search, with its own criterion to agree first. That is a measurement
pass of its own, and it lands in a row whose surrounding prose the
evidence-and-prose plan owns (see the item above).

**How to verify.** Re-profile from the recorded command line and land inside
the recorded range.

## `demos/1812`'s voice-1 witness passes on margin, not on logic

**Anchor:** `demos/1812/test.yaml`'s `assert: { mem: noteidx, above: 0 }` and
the comment block above it; `noteidx` in `demos/1812/vars.s`.

**Status:** open, and **out of the runner's reach** — which is why it outlived
the two siblings it was filed with. `sample: { width: 2 }` compares a two-byte
counter as a counter, and the same spec's `shapes greater_than s0` and the
hold's byte-for-byte claim both use it now. This one cannot: `noteidx` is a
single byte *in the program*, `inc` wraps at 256, and no sample width widens a
counter the program does not keep.

**What's wrong now.** The step reads "voice 1 sounded in this section" off a
non-zero `noteidx`. `s2v1` fires 300 pitched events, so it reads 44 and passes —
but a stream whose section event count were an exact multiple of 256 would read
0 and fail the step *while sounding*. The comment already says so; the assertion
still cannot tell the two cases apart. The v2 witness (`differs` against a
sampled pitch) has a latent false failure of the same family — the comment says
so too — but it is a coincidence between two bytes, checked by hand against the
data (`$12` there, `$1f` here) and settled. `noteidx`'s recurs every 256 events,
so any edit that lengthens voice 1's section-2 stream walks toward it.

**Fix direction (two, unranked).** Either widen `noteidx` to a `.word` in
`vars.s`, carry the high byte at the `inc` in `music.s`, and sample it at
`width: 2`; or witness voice 1 with something that cannot wrap, the way v2 and
v3 already are. The first costs a byte and one `bne`/`inc` per pitched event
and makes the existing assertion honest; the second changes no code.

**How to verify.** `c64 test run demos/1812/test.yaml --json` stays green, and
the new witness fails on a voice-1 stream that is silent for the section —
check it, do not assume it, since that is the failure the current step already
cannot see.

## `index.html`'s 1812 alt text describes pixels nothing checks

**Anchor:** the three `alt=` strings in `index.html`'s demos section, on
`demos/1812/evidence/sec1.png`, `cannon.png` and `final.png`
(`index.html:399,402,405`).

**Status:** open, and **latent rather than live**. All three strings were
checked against the retaken PNGs on 2026-08-12, by opening the images: the
Marseillaise capture is blue and red polygons over dithered blue, red and
white; the cannon capture has a white border around red, orange, yellow and
blue; the final canvas is blue, yellow, brown and white with a blue star in
it. Every claim held. What is filed here is the missing guard, not a wrong
sentence.

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

## A capture staged with `c64 call` cannot be anchored, and its PNG churns

**Anchor:** `demos/1812/tools/evidence.sh` section 9 (`call drawshape`
immediately followed by `screen --png`), and the three files it writes,
`evidence/rot-a.png`, `rot-b.png`, `rot-c.png`;
`docs/graphics-and-sprites.md` §5 (the rules table and the note after it) and
§6, where the deferral is recorded with its reopen condition.

**Status:** open as a **missing primitive**, and the documentation half is
done. The reference and the script both stated the rule as an absolute
("Every capture is taken with the machine STOPPED at a `c64 until` label";
"the same script produces the same frames every time"); both now carry the
exception and the measurement.

**What's wrong now.** `c64 call` ends at its trap wherever the raster happened
to be, and `c64 screen --png` returns the emulator's rendered display rather
than a re-render of video RAM, so a shot taken straight after a call is torn at
the raster split. Measured 2026-08-12: three replays of section 9's staging —
same session flags, same seven `mem write`s, `sh_angle 0` — produced a
byte-identical bitmap (`lit=6105`, checksum `1c454f03`, vertices
`y=44 44 155 155`) and three different PNGs, whose pixel diffs sit entirely in
rows 356–369 of 526. Three committed artifacts therefore change on every
regeneration for no semantic reason. The obvious fix is not available: an
`until` cannot follow a call, because "the call's fake return address replaces
the program's control flow; that run is over" (`docs/cli.md`, `c64 call`), so
there is no label left to stop on.

**Fix direction (not ruled — this is the open question).** A stop that does not
need a program label. Either a raster-anchored stop — `c64 until --raster N`
with `c64_until(raster=N)` beside it — or a capture that waits for the frame
top itself, `c64 screen --png --at-frame-top` with the same flag on
`c64_screenshot`. Either way the operation goes in `ops.py` and both front ends
surface it, per lockstep. Not built now because the whole cost so far is three
PNGs whose bytes move while their meaning does not, in a demo whose actual
proof for those shots is the litcount and checksum printed beside them.

**How to verify.** Run `demos/1812/tools/evidence.sh` twice and confirm
`rot-a/b/c.png` come back byte-identical — which today they do not, and which
is the whole test.

## `demos/1812`'s proof protocol does not sample every criterion it is cited for

**Anchor:** `demos/1812/tools/evidence.sh` — the determinism block, its cannon
block, and its two `/tmp` intermediates; `demos/1812/SPEC.md` A9 and A7.

**Status:** open. Three defects in one script; the first two are the same
shape — the protocol is cited as evidence for a criterion it does not actually
sample.

**What's wrong now.** *A9* says the repeated seed reproduces "identical `rng`,
**all seven** last-shape bytes, an identical lit-pixel count and an identical
bitmap checksum". The determinism block prints `lstype`, `lsangle` and `lspat`
and stops; `lssize`, `lsx`, `lsy` and `lsink` never appear. The canvas checksum
is strictly stronger evidence so the criterion is still met, but the log does
not show what the spec says it shows. *A7* is `cannons == 16` at the end of
section 3; the cannon block stops at `until cannonfire --count 1` and prints
`cannons=1`, and there is no later sample, so the protocol skips one of the
criteria it exists to evidence. The audio protocol cannot cover for it either —
`tools/audio-evidence.sh` rewinds section 3's streams at log frame 0, which
re-fires shot 1, so `cannons` over-counts there by construction; writing
iteration 3's Evaluate table meant running the full 170-step `c64 test run`
(40.9 s) just to read the value. *And* the script writes `/tmp/1812-early.txt`
and `/tmp/1812-late.json` at fixed paths, so two concurrent runs — or a second
demo that copies the pattern — silently read each other's persistence sample.

**Fix direction (partly ruled).** The `/tmp` collision is a plain bug: mktemp,
or a path under `$EV`, with the heredoc taking it as an argument rather than
hardcoding it. A9 is a choice between adding the four missing `mem get`s and
rewording A9 to name the three it prints — prefer the former, since the
criterion is the stronger claim. A7 wants one more `until secchange --count 4`
plus a `mem read cannons` at the end of the cannon block. The general form,
which is the interesting one and is **not** ruled: a way to ask a protocol
script *which* acceptance criteria it samples, so a criterion no artifact
covers is a build-time complaint rather than something a later prose task
discovers by hand.

**Why not here.** All three change what the script does, and the only check
that can fail on them is a full protocol run against VICE.

**How to verify.** Run the script and confirm the determinism block names seven
bytes, the cannon block reports 16 at the section end, and two concurrent runs
in separate checkouts do not disturb each other.

## What the CLI prints, a document cannot cite

**Anchor:** `c64 test run --json`, `c64 package --json`, `c64 mem get` — all
three in `docs/cli.md`.

**Status:** open. Three independent gaps, all discovered while trying to turn a
command's output into something a tracked document could quote.

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
(`## Known facts`, where the drift period is now recorded).

**Status:** open. The measurement is done and written down; the two tool gaps
it exposes are not.

**What's wrong now.** *No origin.* `c64 audio capture` measures what arming
cost (`lead_in_frames` came back 129 on the probe here) but has no way to aim
frame 0: `c64 until secchange` leaves the machine stopped at the boundary and
the arming that follows spends an unpredictable ~130 frames before the log's
frame 0, while `diff_score` compares event *n* against entry *n* and so needs
the window's opening tick. The workaround was to rewind the sequencer inside
the window with `--at-frame 0` and 22 writes reproducing what `loadstreams`
does — which works, and means every demo wanting a scored capture of a passage
it cannot restart must reimplement its player's state reset as a poke list.
*No tolerance.* `diff_score` compares durations with `int(want_frames) !=
got.frames`, exact equality. A jiffy-paced player and the sid log separate by a
frame every ~341 log frames, so a 15-second window drifts 2–3 frames and a
fully-durationed score fails on entries that are musically correct. Omitting
`frames` is legitimate and is what was done — at the cost of every timing claim
the score might have made, including *when* a voice enters, which is the whole
texture arc.

**Fix direction (proposals, both front ends each).** `--at-label REF` on
`c64 audio capture`, with `at_label` on `c64_audio_capture` — or, better,
letting `c64 until` hand the stopped machine straight to a capture, so the
window opens on a label the program itself defines. And a drift tolerance:
either per entry in the score schema (`frames: 56, tolerance: 2`) or per run
(`--drift N` / a `drift` argument on the MCP tool), so that a duration can be
asserted at all over more than a few hundred frames.

**How to verify.** Score a 15-second passage with every `frames` pinned and
have it pass — which today it cannot, and which is the point.

## The piano roll's pitch axis is unreadable on a wide passage

**Anchor:** `MAX_ROW_LABELS` in `src/c64lib/sid_analysis.py`.

**Status:** open.

**What's wrong now.** The Y labels are thinned to at most twelve, so a passage
with a wide range comes back labelled every second or third semitone — the
1812 hymn's 33-semitone range printed `F#5 D5 A#4 F#4 D4 A#3 F#3 D3 A#2 F#2 D2`
— and a bar sitting between two labels cannot be named from the image. Reading
`hymn/piano-roll.png` against the claim "the rising fourth and the stepwise
descent are still here" meant cross-reading the transcription table in
`report.md` for the pitches and using the roll only for the shape. The roll is
the artifact a reviewer is pointed at; it should be readable alone.

**Fix direction (two, unranked).** Label every row where the range is small
enough to fit them, raising the cap rather than fixing it at twelve; or keep
the cap and draw the unlabelled rows in a second grid tone so the eye can count
semitones off the nearest label. The second is cheaper and works at any range.

**How to verify.** Generate a roll over a 33-semitone passage and name a bar's
pitch from the image alone, without opening `report.md`.

## The demos are proved on Commodore ROMs and shipped on open ones
---

The items below are the browser-play plan's deferrals, filed 2026-08-13 as that
plan finished. Each carries its evidence inline on purpose: the research that
produced them lived in `.superpowers/sdd/2026-08-02-browser-playable-demos/`,
which is deleted with the plan, so an item that merely cited it would resolve to
nothing — the failure this file's own first entry is about.



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

The risk landed on 2026-08-13, in the shape this item predicted. All four games
read the held key from `$CB`, a KERNAL scratch byte open-roms never writes, so
every one of them was unplayable in the browser while all four `test.yaml` runs
stayed green under VICE. The games now scan the CIA matrix directly (`keyscan`,
and `keydecode`'s zero clause in `la-galaxia`) and keep `$CB` only as the
fallback the CLI drives them through — but nothing below the games changed, so
the next demo to depend on a Commodore-only ROM detail will fail exactly as
silently. `demos/1812` is that next demo already; see its item.

**What's wrong now.** Every demo's regression suite runs under VICE, which reads
ROM bytes from the emulator the developer installed — Commodore's. `play.html`
boots the same four programs on MEGA65 open-roms instead. Nothing exercises the
second set. open-roms is not cycle-exact with the Commodore KERNAL and its BASIC
is deliberately incomplete (that project's own `STATUS.md` says so), so a change
that starts calling a KERNAL routine these four currently avoid would pass
`c64 test run` and break the play page silently. Today the four use only `RUN` +
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
Re-capturing `evidence/` itself is the one option that is wrong: those PNGs are
cited as evidence by each demo's `AUDIT.md`.

**How to verify.** Open the play page, boot any of the three, and compare the
running title screen with its own tile: same words in the same cells, different
letterforms. That is the whole of the defect, and it is the check.

## `play.html`'s audio-state listener trusts any window that posts to it

**Anchor:** `play.html`, `onPlayerMessage()`.

**Status:** open, hardening only. Deferred during the plan with its impact
measured, not assumed.

**What's wrong now.** The handler checks `e.data.msg` and `e.data.value` and
never checks `e.origin` or `e.source`, so any frame or opener that can post to
this window can spoof `{msg:"render_current_audio_state", value:"running"}`.
The entire consequence is that the yellow "click the screen for sound" hint is
hidden early — a line of advice, no state, no capability. It is filed because an
unchecked `message` listener is a pattern worth not leaving in the tree, not
because this one is exploitable for anything.

**Fix direction (not ruled).** Compare `e.origin` against the origin of
`EMU_BASE` — which is already a constant one scroll up — and drop anything else.
`e.source` is the tighter check but needs a handle on the player's iframe
window, which the player owns rather than this page.

**How to verify.** From the console, `postMessage` that exact payload from the
page itself and confirm the hint stays up; then boot a demo for real and confirm
the hint still retracts when audio starts.

## A shipped docstring cites a path that `.gitignore` excludes

**Anchor:** `src/c64lib/audio.py`, the `warp` readback docstring — its pointer
to `.superpowers/sdd/2026-08-02-sid-audio-verification/wedge-investigation.md`.

**Status:** open. Found 2026-08-13 while sweeping tracked files for citations
into `.superpowers/`; it was the only other hit, and it is not broken *yet* —
that plan's workspace still exists on this checkout.

**What's wrong now.** A tracked source file points a reader at an untracked
path. `.gitignore` excludes `.superpowers/` wholesale and SDD workspaces are
deleted when their plan finishes, so the reference resolves for whoever happens
to still have the directory and for nobody else — this file's first item, one
step later. The docstring is defensive in the right way otherwise: it carries
its own figures inline ("measured 2026-08-04/05", 39 missing replies in 240
pin/unpin cycles, a 30 s timeout that still returned nothing), so what is lost
is the supporting wire traces, not the reason the retry exists.

**Fix direction (not ruled).** Either drop the pointer, since the docstring
already stands without it, or move the wire traces somewhere `git ls-files`
reports and cite that.

**How to verify.** `git grep -n '\.superpowers/' -- src/ docs/ skills/ '*.html'`
returns nothing that a reader outside this checkout could not follow.

## The fork will republish a GPL-3.0 emulator with no licence text

**Anchor:** `LICENSE`'s "Third-party components" section; `play.html`'s
`EMU_BASE`; the `nschneir/vc64web.github.io` fork — `vc64.wasm` (2,062,000 B)
and `vc64.js` (198,736 B) at its root.

**Status:** open, **contestable, and the maintainer's call** — filed so the
call is made rather than inherited. Not introduced by this branch: the fork's
one local commit (`a5cddb6`) adds `roms/` and nothing else, so everything else
is upstream's tree as forked.

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

## Every player mount leaks a `resize` and an `orientationchange` handler

**Anchor:** the fork's `js/vc64web_player.js` — `load_into()` at `:208` and
`:219` against `stop_emu_view()` at `:362-377`; `play.html`'s
`teardownPlayer()`.

**Status:** open, **upstream residue, and outside what this page can fix.** The
plan's "switching must not leak" contract was about iframes and it holds —
measured 0 iframes and 0 `#player_container`s after switching, and the state
poller is stopped on both teardown paths.

**What's wrong now.** `load_into()` runs `$(window).on('resize', …)` and
`$(window).on('orientationchange', …)` on *every* mount, and `stop_emu_view()`
removes only `document`'s `click` listener (`document.removeEventListener
("click", this.grab_focus)`). Neither `resize` handler is ever taken off, so k
boots leave k pairs attached to `window`. Each closes over `load_into`'s scope,
which holds `element` and `emu_container` — the detached preview subtree — so
this retains DOM, not just duplicate work.

The visible symptom is small and bounded, which is why it is filed rather than
worked around: `$vc64web` is assigned inside `load_into` **without `var`**, so
it is one global that each mount overwrites, and all k handlers therefore
resize the same live iframe. Behaviour stays correct; the cost is k height
writes and k 130 ms timeouts per window resize, on a page where k is the number
of games the visitor has tried.

**Fix direction (not ruled).** It belongs in the fork: `$(window).off('resize
orientationchange')` at the top of `stop_emu_view()`, or — better, since the
host page may own handlers of its own — namespaced registration
(`.on('resize.vc64web', …)`) with the matching `.off('.vc64web')`. From
`play.html` the only reach is `window.jQuery(window).off("resize
orientationchange")` after each teardown, which drops handlers this page does
not own; it happens to be safe today because the page registers none through
jQuery, and it would break silently the day that stops being true. Not taken
for that reason.

**How to verify.** With the player live, boot and stop three times, then read
`jQuery._data(window, "events").resize.length` in the console: 3 today, 0 once
`stop_emu_view()` unregisters.

## `la-galaxia`'s fighter-movement assertion is a coin flip

**Anchor:** `demos/la-galaxia/test.yaml`, the block commented "the fighter moves
at exactly 1.5 px/frame (§7)" — `sample plx as x0`, hold `A` for 40 ticks,
`assert: { mem: "plx", less_than: x0 }`; `clv3` in `demos/la-galaxia/la-galaxia.s`.

**Status:** open, and **pre-existing** — measured 2026-08-13 on untouched `main`
at 4 passes and 1 failure in 5 runs, with the failure reading
`mem $4187 = 88 not < sample x0=88` (88 is `PLW_MAX/2`, the spawn position).

**What's wrong now.** The assertion only holds if the fighter is alive and free
when the window opens, and nothing in the spec arranges that. `clv3` seeds the
LFSR from `$D012`, the live raster line, at startup; where the raster is when
VICE finishes loading varies run to run, so every run plays a different game
from the same bytes. A probe run of the same steps caught the state directly:
`plstate` = 1 — captured by a tractor beam, spinning — so `playertick` returned
before the movement code and `plx` had moved 2 px, not 60. The block above it
already knows the fighter is on this edge ("an idle fighter dies inside 200
ticks now that the game is hard"); the movement block sits 400 ticks further in
and does not check.

It costs more than a rerun. A failure here reads as an input regression, and the
2026-08-13 matrix-scan change was suspected on exactly this evidence until the
baseline was run five times.

**Fix direction (not ruled).** Two shapes. Pin the seed — poke `rnd`/`rnd+1` to
a constant before the run, which makes the whole spec reproducible and not just
this step, but changes what the suite is exercising. Or make the precondition
explicit: assert `plalive` = 1 and `plstate` = 0 immediately before the sample,
and put the fighter back there if it is not, so a captured fighter fails as
"the fighter was captured" rather than as "held A does not move it".

**How to verify.** Run `c64 test run demos/la-galaxia/test.yaml` five times on
an unchanged tree and count. Today that is not 5/5; whatever lands must make it
5/5, and must still fail if `keydecode` is broken on purpose (poke a `rts` over
its first byte and confirm the step goes red).

## `c64 sprite png` and `c64 screen --png` disagree about the palette

**Anchor:** `src/c64lib/sprites.py:19-25` (`C64_PALETTE`);
`src/c64lib/screen.py:73` (`palette = mon.palette()`); `protocol.py:46`
(`PALETTE_GET`).

**What's wrong now.** The two commands the graphics policy names as the sprite
inspector and the evidence camera render the same colour number differently.
Measured on two committed artifacts of the *same* sprite data:

```
demos/amiga_ball/evidence/ball-tl.png  (c64 sprite png)    red = (104, 55, 43)
demos/amiga_ball/evidence/rot00.png    (c64 screen --png)  red = (174, 71, 93)
```

A dark brick against a rose — not a rounding difference. The cause is one line
each: `sprites.py` ships a hardcoded table (`# Pepto palette (colodore
lineage)`), while `screen.py` asks the machine over the binary monitor and
renders with whatever palette VICE is actually configured with.

`docs/graphics-and-sprites.md` §3 sends a reviewer to `c64 sprite png` to
"verify a sprite before claiming it works" and to `c64 screen --png` for
evidence. A reviewer comparing the two sees two different colours for the same
three bytes, with nothing to say which is the machine.

**Fix direction (not ruled).** Have `sprites.py` take the palette from
`mon.palette()` the way `screen.py` does — `c64 sprite png INDEX` cannot run
without a session, so the ground truth is always available — and keep
`C64_PALETTE` only as the fallback for any path with no live monitor, saying so
in the docstring. `c64 sprite show`'s ASCII is unaffected.

**How to verify.** A test that renders one sprite through both writers and
asserts the two agree on every colour it uses. That check does not exist today,
which is why the divergence shipped.

## A committed audio `report.md` cannot say whether it checked anything

**Anchor:** `src/c64lib/sid_analysis.py`'s report writer; `c64 audio capture`
/ `audio report` in `docs/cli.md`; any `demos/*/evidence/audio/*/report.md`.

**What's wrong now.** The report is the durable artifact a reviewer reads
months later, and it does not name the reference score, quote its entry counts,
or state whether `--ref` was passed at all. It says so itself —
`demos/amiga_ball/evidence/audio/floor/report.md`, committed as that demo's
audio evidence:

> ## Score diff
>
> No differences against the reference score — an empty diff list is also what
> a run with no reference score produces.

So the strongest audio evidence a demo can commit is, on its face,
indistinguishable from a capture that was never scored. `docs/cli.md` already
carries the rule this undermines — "A score derived from a transcription this
produced cannot fail, and a check that cannot fail is not evidence" — and this
is that failure one level up, in the report rather than in the score.

**Fix direction (not ruled).** Put the reference into the report: the score's
path, its per-voice entry and frame counts (`c64 audio score` already computes
exactly this), and an explicit "no reference score supplied" line when there is
none. The JSON payload already distinguishes the two cases; only the markdown
cannot. Both front ends share the writer, so this lands once.

**How to verify.** Run one capture with `--ref` and one without over the same
log; the two `report.md` files must differ in the Score-diff section, and the
scored one must name the file it diffed against.

## `--at-frame` is the one address argument that refuses a symbol

**Anchor:** `c64 audio capture --at-frame` in `docs/cli.md` (~line 1866); the
global address conventions at the head of the same file; `ops.parse_number`.

**What's wrong now.** Measured:

```
$ c64 audio capture ... --at-frame 12 'freeze=0'
error: audio capture --at-frame: 'freeze=0' is not a number
(invalid literal for int() with base 10: 'freeze'); use decimal, $hex, or 0xhex
```

`docs/cli.md` states the restriction, so it is documented rather than
surprising — but the same file's global convention is that "a symbol name is
accepted anywhere an address is", and `mem read`, `mem write`, `until`,
`break add`, `watch add` and the YAML steps all honour it. This is the
exception, and it is in the one command whose whole job is to poke a running
program's state at a known frame.

The cost is design pressure: `demos/amiga_ball` gave its observable state its
own `--area 'VARS=$4000:$0100'` so that `freeze` would be at a *fixed* address
this flag could name. That is a good layout and it was forced rather than
chosen; a demo without an area has no stable number to write.

**Fix direction (not ruled).** Resolve `--at-frame` addresses through the
session's label file the way every other address argument does, falling back to
the literal parse. `c64_audio_capture`'s `at_frame` needs the same.

**How to verify.** `c64 audio capture 1 out/ --at-frame 12 'somelabel=0'` on a
session with symbols registered performs the write; with no such symbol it
still fails before anything is pinned.

## Shipping a demo has a checklist, and it lives only in the test suite

**Anchor:** `tests/test_docs_demos.py` —
`test_play_page_registry_is_the_runnable_demos_in_the_roster_order`,
`test_every_demo_file_play_html_serves_exists_and_is_tracked`,
`test_play_page_describes_each_game_the_way_the_landing_page_does`,
`test_exactly_one_captured_audio_score_lists_no_sounding_note`,
`test_the_sites_the_failure_message_names_still_say_it`; `play.html`'s `DEMOS`
array and its `<noscript>` fallback; each demo's `PROMPT.md` "Ship it" section.

**What's wrong now.** A demo prompt tells its author to `c64 package` the demo
and write a `README.md`. Committing the `.prg` that step produces then obliges,
with nothing anywhere saying so:

1. a `play.html` `DEMOS` entry — a committed `.prg` is exactly what the roster
   test counts;
2. a second, separately hand-written entry in `play.html`'s `<noscript>`
   fallback (one `.prg` and one `.d64` link per demo);
3. a description **byte-identical** to `index.html`'s for the same demo;
4. tile art under the demo's own `evidence/`;
5. if the demo captures audio: a hardcoded count of scored captures, the prose
   in two docstrings that states the sounding/silent split, and a meta-guard
   that pins the exact phrasing of one of those docstrings.

Every one of those guards is well-built and catching something real. The defect
is discovery: the author meets the list as a red suite, one failure at a time.
The `demos/amiga_ball` dogfood hit all five.

**Partly landed.** `test_la_galaxia_prg_is_a_build_of_the_committed_sources` is
now `test_demo_prg_is_a_build_of_the_committed_sources`, parameterised over
every demo with a `test.yaml` naming an `.s` and a committed `.prg` — six
today, all six byte-identical to a rebuild. Four of them previously had no such
guard, and `amiga_ball.prg` had sat five commits stale (1,986 differing bytes)
because the only guard named a different demo.

**Fix direction (not ruled).** State the checklist where the author will meet
it — a "Shipping a new demo" section in `demos/README.md`, or beside AGENTS.md's
dogfood section — naming all five obligations. The residual gap the pinning
test's own docstring already flags is still open: the `.d64` is not pinned to
the `.prg` it should carry, so a re-packaged image can drift from a rebuilt
program with nothing to notice.

**How to verify.** Add a demo directory with a committed `.prg` and nothing
else, run `pytest tests/test_docs_demos.py -m "not vice"`, and count how many
failures name a file the prompt never mentioned. The checklist is correct when
that count is zero because the author was told first.

## The WAV/log bracket is wider than `docs/cli.md` records

**Anchor:** the capture bracket figures in `docs/cli.md`'s `c64 audio capture`
entry.

**What's wrong now.** Measured on both amiga_ball captures: **1.738 s of WAV for
1.500 s of log — 0.238 s of bracket**, against the 0.086-0.103 s the doc
records, and the impact's WAV onset ran 0.135 s later than log frame 13's
nominal position. Rate alignment is unaffected (pitches and durations agree
between log and recording, and both reports PASS), so this bears only on the
claim that the bracket locates a log frame to within about 0.1 s — anyone lining
a spectrogram feature up with a log frame on this host is out by more than the
stated tolerance.

**Fix direction (not ruled).** Re-measure on a second machine and either widen
the figure or mark it host-dependent. Nothing is broken; the number is just
narrower than it holds.

**How to verify.** `c64 audio capture` on two hosts, comparing `wav_bytes`
against `frames` × the sample rate; the documented figure must bracket both.

## `demos/invaders` places its sprites a raster below flush, unre-judged

**Anchor:** `demos/invaders/invaders.s`'s `TOPRASTER` block and
`sprites.s`'s comment above `BASESPY`/`UFOSPY`; `demos/invaders/test.yaml:47`
(`$D001` = 227); `skills/c64-development/references/hardware.md`, Sprites.

**Status:** narrowed. **The general rule is fixed** — a sprite whose Y register
is `V` shows its first row on raster `V+1`, so flush with text row R is
`50 + 8*R`, and both `hardware.md` and `skills/6502-assembly/SKILL.md` now say
so with the measurement (a solid 24×21 hires sprite at `$D00D` = 100 occupies
rasters 101-121, exactly 21 rows). Both invaders sites that stated the rule
wrongly are corrected and now describe what that demo actually does. Its
constants are untouched and `invaders.prg` is byte-identical, so its tests and
evidence frames are unaffected.

**What's left.** `BASESPY`/`UFOSPY` are `51 + 8*R`, one raster below flush.
That is now *documented* as deliberate — it keeps the UFO clear of the HUD's
bottom pixel row, which is what that demo's audit judged by eye — but nobody
has re-judged it since the rule was corrected. It may be exactly right, and one
raster on a 21-row sprite is at the edge of visible; it is recorded so the next
person to look at those constants knows they are a choice rather than the rule.

**Fix direction (not ruled).** Either confirm the placement by eye against
`demos/invaders/evidence/ufo.png` and delete this item, or move both constants
to `50 + 8*R`, which changes `test.yaml`'s 227 to 226 and re-takes the evidence
frames.

**How to verify.** Whichever way it goes, `demos/invaders/sprites.s`'s comment
and `hardware.md`'s Sprites section must still agree about the general rule,
and `c64 build demos/invaders/invaders.s` must reproduce the committed
`invaders.prg` (`tests/test_docs_demos.py::test_demo_prg_is_a_build_of_the_committed_sources`).

---

Everything from *Two skill files say the screen reader assumes `$0400`* onward
is the **fugue dogfood's** post-mortem (2026-08-14), kept the same way: a
friction log written while the work happened, then triaged, with the file
quoted before any gap in it is asserted. Six items. The through-line this time
is different from amiga_ball's: five of the six are about *what the references
say*, not about the instruments. The demo's own bugs — a sprite constant that
did not follow its geometry, an illegal addressing mode, a branch out of range
— were each caught within one build or one screenshot. What cost hours was a
frame-budget design derived from a rule the references state incompletely.

## Two skill files say the screen reader assumes `$0400`. It does not.

**Anchor:** `skills/c64-development/references/cookbook.md:2523-2524` and
`skills/c64-development/references/hardware.md:214-215`.

**What's wrong now.** Both say the same thing:

> **Leave the screen at `$0400`.** The `$D018` high nybble can move it, but
> the toolset's screen reader assumes `$0400`.

Two other files say the opposite, and they are the ones that are right.
`docs/graphics-and-sprites.md:99-101`: "Screen reads are relocation-aware:
`c64 screen` and `@row,col` follow `$DD00`/`$D018` to wherever the VIC-II put
the screen". `skills/c64-development/SKILL.md:209`: "relocation is followed
automatically by `c64 screen` and `@row,col`."

Measured 2026-08-14 on an NTSC session, marker bytes at both addresses:

```
mem write $1C00 5 ; mem write $0400 9
mem read '@0,0' 1     -> 0400: 09          (default $D018)
mem write $D018 $78                        (screen -> $1C00)
mem read '@0,0' 1     -> 1c00: 05          followed the relocation
c64 screen --codes    -> first cell 5      followed it too
```

Both halves of the claim are false, and the two files carrying the false
version are inside the skill — the half that travels to other repositories,
where `docs/graphics-and-sprites.md` does not exist to contradict it.

**Fix direction.** Correct both skill files to match the measurement and say
what is actually fixed: colour RAM never moves, so `@@row,col` stays `$D800`
whatever `$D018` says. Keep a *reason* to leave the screen at `$0400` if there
is one worth keeping (there is: nothing in the toolset needs it moved, and
moving it costs a KB of bank 0), but stop giving a false one.

**How to verify.** `git grep -n "screen reader assumes"` returns nothing, and
the replacement sentence in each file is asserted by a `tests/test_docs_*.py`
case that performs the two-marker measurement above against a live session.

**Cost here.** `demos/fugue/SPEC.md` §5 costed a double-buffered fallback that
would have relocated the screen, and had to carry a paragraph hedging a
contradiction that a two-minute measurement settles.

## The cookbook has no scrolling recipe and no SID sequencer recipe, and a demo prompt promises both

**Anchor:** `skills/c64-development/references/cookbook.md`;
`demos/fugue/PROMPT.md:51-52`.

**What's wrong now.** The prompt sends the agent to the cookbook for three
things:

> - `skills/c64-development/references/cookbook.md` — working recipes (raster
>   IRQ, SID, smooth scrolling) to start from rather than reinvent.

One of the three is there. Verified:
`git grep -nI 'D016' -- skills/c64-development/references/cookbook.md` returns
**two** hits, both inside "Multicolor bitmap" switching on the multicolour bit;
no heading in the file mentions scrolling (`git grep -nI '^### '` lists 31
headings). The 38-column bit, the column-shift step and its cost appear
nowhere, and the only register description is one line in `hardware.md:212`.

The SID half is thinner than it sounds too. The file's entire assembly SID
vocabulary is "Sound: a beep from machine code" — eight stores and a jiffy
delay — plus its BASIC twin. There is no note table (the formula is in
`hardware.md`), no frame-driven player, no gate handling, and no shadow-block
convention (that is in `audio-verification.md`, which argues *against* trusting
shadows alone).

**Fix direction.** Either add the two recipes or stop promising them. Adding
them is now cheap in source material and expensive in nothing: a horizontal
fine-scroll recipe has `demos/fugue/scroll.s` plus `demos/la-galaxia`'s banded
`$D016` split to draw on, and a frame-driven three-voice player with a shadow
block has `demos/fugue/music.s`, `demos/1812`, `demos/la-galaxia` and
`demos/ms-muncher`. Both would be `LIVE_RECIPES` entries, which is the bar the
cookbook holds its recipes to.

**How to verify.** Two new `### ` headings in the cookbook, both listed in
`LIVE_RECIPES` in `tests/test_docs_cookbook.py`, both assembling and running
correctly on a live C64 in that suite.

## Nothing states the fact a scrolling demo's frame budget actually turns on: a text row is latched at its badline

**Anchor:** `skills/c64-development/references/hardware.md:193-203`
("Badlines"); `skills/c64-development/references/cookbook.md:2176`
("Per-frame raster budget: a high-water mark the program keeps").

**What's wrong now.** Every mention of badlines in the tree is about the
*cycle steal*. `git grep -nIi badline -- skills/ docs/` returns nine hits:
`hardware.md` explains the ~40-43 cycle stall and concludes that "work done in
the **top border** (rasters 0-50) pays no badline steal at all", the cookbook's
budget recipe says "Arm it in the top border", and the rest are `docs/cli.md`
on `c64 profile` counting the steal as wall cycles.

The fact none of them states is the one that decides when a redraw is safe:
**the VIC fetches a text row's whole character matrix and its colour nybbles on
the badline at that row's first raster (`51 + 8*R`), so after that raster,
writes to that row cannot affect the current frame — and before it, they can.**
That single sentence has two consequences a demo needs:

- a row's redraw *deadline* is `51 + 8*R`, not the row's last scanline; and
- a redraw may begin the moment the *last* row it touches has been latched,
  which for a full-screen effect is late in the display, not in the top border.

**Fix direction.** State it in `hardware.md`'s "Badlines" paragraph, and add
the consequence to the cookbook's budget recipe, whose "arm it in the top
border" is good advice for a short tick and actively misleading for a redraw
that spans most of a frame.

**How to verify.** A `tests/test_docs_*.py` case asserting both files carry the
latch rule, in the shape the other reference-fact tests use.

**Cost here.** `demos/fugue` designed its whole scroll around "arm in the top
border", measured `tickend = 227` against a 203 deadline, and costed two
fallbacks (a display list, and double-buffering) before finding that arming at
raster **204** — immediately after the last band row's badline — turns a
215-raster window into a 263-raster one and needs neither. Final measurement:
`tickend` 178. The design that shipped is a *consequence* of the missing
sentence, arrived at the long way.

## `c64 test run` anchors its first `until` deterministically; the CLI does not, and only one of the two is documented

**Anchor:** `skills/c64-development/SKILL.md:302-317` ("Catching the first
frame of a state you just triggered"); `docs/cli.md`, `c64 test run`.

**What's wrong now.** SKILL.md documents the CLI trap well — `c64 until` "sets
its checkpoint only when it runs, and the wall-clock gap since the previous
command is emulated seconds at warp" — and prescribes arming a breakpoint
before the trigger. Measured on this demo, `c64 run` followed immediately by
`c64 until tick --count 30` landed on **frame 3,774**.

Nothing says whether `c64 test run` has the same problem. It does not: the
runner arms its checkpoint before the program gets going, so a spec whose first
step is `until: {ref: tick, count: 1}` stops at the program's **first**
arrival. Measured: that step plus `assert: {mem: frame, equals: 0}` passes, and
every `--count N` after it is an exact frame number.

That is a real guarantee and a useful one — it is the difference between a
spec that can assert absolute frames and one that can only assert relative
ones — and an agent has no way to know it holds without measuring.

**Fix direction.** One sentence under `c64 test run` in `docs/cli.md` saying
the runner arms before the program runs, so the first `until` lands on the
first arrival and counts are absolute; and a pointer to it from SKILL.md's
paragraph, which currently leaves the reader to assume the CLI's behaviour
applies everywhere.

**How to verify.** `tests/test_docs_cli.py` asserts the sentence exists, and a
spec fixture asserting `frame == 0` after a single `until` keeps it true.

## `c64 sprite encode` and `c64 charset encode` disagree about the hires legend

**Anchor:** `docs/cli.md`, `c64 sprite encode` and `c64 charset encode`.

**What's wrong now.** The two are documented as a pair — the charset command's
entry opens "the charset twin of `c64 sprite encode`" — but their hires
legends differ. `c64 charset encode`: "Hires rows are 8 characters of `.#`."
`c64 sprite encode`: "hires rows are 24 characters using `' #'`". So `.` is the
background in one and needs `--background .` in the other. Authoring this
demo's two sheets in one sitting, the sprite sheet written in the legend the
charset command documents failed with

```
{"error": "sprite 1 'glow' (line 22): unknown hires sprite glyph '.'"}
```

The error is actionable and the fix is one flag, so this is small — but the
commands are presented as twins and a demo that authors both hits it.

**Fix direction.** Cheapest is a cross-reference in each entry naming the
other's default. Making `.` legal in sprite hires without the flag is a
behaviour change and would want its own ruling.

**How to verify.** `tests/test_docs_cli.py` asserts each entry mentions the
other's background default.

## `docs/graphics-and-sprites.md`'s evidence helpers are `sh`, offered without a shell named

**Anchor:** `docs/graphics-and-sprites.md:239-243`.

**What's wrong now.** The block is introduced as "worth stealing verbatim":

```sh
C=".venv/bin/c64"; S="-s mmev"
shot()  { $C screen --png "$OUT/$1.png" --scale 2 $S >/dev/null; echo "  $1.png"; }
```

`$S` unquoted relies on word splitting, which **zsh does not do** for
parameter expansions. Pasted into a zsh shell — the shell this environment
runs — `$S` arrives as the single token `-s fugev` and click reads the session
name as `" fugev"`:

```
error: no session named ' fugev'. Start one with: c64 session start
```

Every committed `tools/evidence.sh` is `#!/bin/sh`, where it works, so the
scripts are correct; it is the snippet, presented bare, that has no shell on
it. This is the same class as the zsh driver example `docs/cli.md` lost in the
amiga_ball pass (see the preamble above) — second instance, different file.

**Fix direction.** One clause on the block saying the helpers assume the
`#!/bin/sh` the committed evidence scripts use, and why (`$S` needs word
splitting).

**How to verify.** `tests/test_docs_*.py` asserts the caveat sits with the
snippet.
