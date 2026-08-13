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

## A bare recursive `grep` here cannot be told from one that never ran

**Anchor:** `AGENTS.md`'s "Dogfood post-mortems" section, which is where the
"quote the file before asserting a gap in it" rule lives; the `grep` shell
function in `~/.claude/shell-snapshots/snapshot-zsh-*.sh`.

**Status:** open, and it **already cost a false claim in this repo** — a task
report asserted "nothing in the repo cites `PROMPT.md` by line" and offered the
failed command as its evidence, in a repo whose own rule is to quote the file.

**What's wrong now.** Two mechanisms, both of which produced an empty result
that read as "clean". First, the glob never reaches grep:
`grep -rn "…" --include=*.md .` dies in zsh before the process starts
(`(eval):1: no matches found: --include=*.md`, exit 1) because the unquoted
`*.md` is expanded against the cwd — and in the run that mattered no output was
reported at all, not even the error. Second, the wrapper hides the gitignored
trees: `type grep` shows a shell function that execs `ugrep` with
`--ignore-files`, which honours `.gitignore` — and `.superpowers/` and
`docs/superpowers/` are gitignored, which is exactly where this repo's plans
and constraint files live. Handed explicit paths, the same pattern found eight
hits immediately. Only *tracked* files were genuinely clean, and
`git grep -nI` is the instrument that says so.

**Fix direction (needs a maintainer ruling — it is a house rule).** Add to
`AGENTS.md` beside the existing evidence rule: "does anything reference X?" is
answered with `git grep` for tracked files and an explicitly-pathed `grep` for
the ignored ones, never with a bare recursive `grep` whose empty output cannot
be told from a crash. The tooling alternative — a wrapper that says on stderr
when `--ignore-files` suppressed a tree — lives outside this repo, so the rule
is the part this repo can actually enforce.

**How to verify.** Grep for a string that exists only under `docs/superpowers/`
and confirm the method used reports it.

## No cycles-per-frame budget anywhere in `skills/`

**Anchor:** `skills/c64-development/references/hardware.md` — the VIC-II
sections; `docs/cli.md`'s `c64 profile`, which is currently the only place the
number appears.

**Status:** open. Carried over from the iteration-3 planning notes and verified
against the tree on 2026-08-12 rather than assumed.

**What's wrong now.** `c64 profile` reports cycles, and `docs/cli.md` supplies
the denominator inline in its own prose — "25 badlines × ~43 cycles ÷ 17,095"
and "comfortably inside the 19,656-cycle PAL frame". Nothing in `skills/` does.
The closest `hardware.md` gets is "VIC stealing 6510 cycles — a screen-blanked
compute loop runs ~5% faster", which is the effect without a number, and
`grep -rn 'badline' skills/` returns nothing at all. So an agent working from
the skill alone can measure a routine and has no way to say what fraction of a
frame it spent; `demos/1812/AUDIT.md` had to state 17,095 itself.

**Fix direction (ruled by placement, not by content).** A short timing block in
`hardware.md`'s VIC-II material: cycles per raster line and lines per frame for
both standards (NTSC 65 × 263 = 17,095; PAL 63 × 312 = 19,656), and the badline
steal as a fraction rather than as "~5%". No CLI surface changes, so lockstep
does not apply.

**How to verify.** `grep -rn '17,095\|19,656' skills/` returns the table, and
`tests/test_docs_skills.py` stays green.

---

The items below are the browser-play plan's deferrals, filed 2026-08-13 as that
plan finished. Each carries its evidence inline on purpose: the research that
produced them lived in `.superpowers/sdd/2026-08-02-browser-playable-demos/`,
which is deleted with the plan, so an item that merely cited it would resolve to
nothing — the failure this file's own first entry is about.

## The demos are proved on Commodore ROMs and shipped on open ones

**Anchor:** `demos/{snake,invaders,ms-muncher,la-galaxia}/test.yaml` and
`c64 test run`; `play.html`'s `KERNAL_ROM_URL` / `BASIC_ROM_URL` /
`CHARSET_ROM_URL` constants.

**Status:** open, and never mitigated — the ROM research that cleared the open
ROMs for shipping recorded this as its residual risk with "*mitigation:* none in
place", and nothing since has supplied one.

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

**Fix direction (not ruled).** Two shapes were considered and neither chosen.
The cheap one is a documented note that the play page's ROM set differs, so the
next author at least knows to look. The real one is a smoke check that boots
each `.prg` to its first playable frame on the open ROMs and asserts the same
screen the `test.yaml` first step does — which needs the open ROM images
reachable from a test run, and they deliberately do not live in this repo.

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

## The play page has never been seen running

**Anchor:** `play.html`; `https://nschneir.github.io/Project64/play.html`;
the `nschneir/vc64web.github.io` fork.

**Status:** open, and **blocking any claim that browser play works**. Everything
shipped is verified against the *fallback*, not against a running emulator.

**What's wrong now.** The whole page was built and checked locally against an
emulator that 404s. As of 2026-08-13 the fork is committed but unpushed and has
no GitHub Pages, so `https://nschneir.github.io/vc64web.github.io/` — and every
ROM and script under it — returns 404; and this branch is unpushed, so
`https://nschneir.github.io/Project64/play.html` returns 404 while
`https://nschneir.github.io/Project64/` serves fine. A visitor following a
README play link today gets a 404; a visitor on a local copy gets the graceful
"THE EMULATOR FAILED TO LOAD" panel with working `.prg`/`.d64` downloads. That
fallback is verified. Nothing else on the boot path is.

Specifically unverified: that the emulator loads from the fork at all; that any
demo reaches a playable frame from the published URLs; that a real keyboard
drives them (the demos poll `$CB` once a tick, so synthetic key events are
missed by design — automation cannot substitute); that audio unlocks on the
first gesture and the sound hint then retracts; that a phone works at all —
touch controls reaching the game, the virtual keyboard, sound after tap. The
`touch:` flag is seeded from `(pointer: coarse)`, which is false on every
machine this was tested on, so the touch path has never once been exercised.
Nothing outside Chrome has been tried.

**Fix direction (ruled — it is a sequence, not a design).** Push the fork and
enable Pages on it; push this branch and let Project64 Pages rebuild; then repeat
the local pass against the published URLs, and add the two things only a human
can do — real-keyboard play of all four demos, and one phone check.

**How to verify.** `curl -sI https://nschneir.github.io/vc64web.github.io/js/vc64web_player.js`
returns 200, and each of the four
`https://nschneir.github.io/Project64/play.html?demo=<id>` links boots to its own
title screen with sound after the first click.

**One candidate lapsed rather than deferred.** The design spec asked
implementation to look for "a warp-during-load config flag as a nice-to-have",
premised on its own note that "real 1541 loading takes ~15-25 s". The shipped
page has no 1541: it boots a `.prg` flashed straight into RAM with no drive ROM
installed at all (`play.html`'s `BOOT_MEDIUM`). There is no load to warp
through, so the candidate is moot rather than skipped.

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
