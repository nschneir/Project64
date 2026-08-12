# TODO

Open items carried out of recent reviews and dogfood runs. Items are deleted
as they land — what was actually done is recorded in `CHANGELOG.md` and in git
history, so this file stays a list of work still open.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

Recreated 2026-08-12 by the 1812 iteration-3 pass, whose deferrals are the
first four items below; the last is the residue of the 16-bit-sample work that
closed one of them.

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

## `demos/1812`'s evidence PNGs no longer depict the shipped build

**Anchor:** `demos/1812/evidence/sec0.png`…`sec4.png`, `final.png`,
`cannon.png`, `shipped-d64.png`; `demos/1812/tools/evidence.sh`.

**Status:** open, and **deliberately deferred by the maintainer on 2026-08-12**
to a later plan. Recorded here so it is not mistaken for an oversight.

**What's wrong now.** Iteration 3 re-voiced the hymn. The shape RNG is shared,
so the picture diverges from the hymn onward and every committed PNG depicts
the pre-arrangement build.

**How to verify.** Regenerate through `tools/evidence.sh` and confirm each PNG
matches a fresh run at its anchored frame.

## `main` ships source citing documents that do not yet say what it claims

**Anchor:** `demos/1812/sections.s:103` (cites `SPEC.md` §6.4),
`demos/1812/test.yaml:82` (cites acceptance criterion **A15**),
`SPEC.md:397-398`, `AUDIT.md:173-174`.

**Status:** open, and **narrowed**. The amendments are the evidence-and-prose
plan's deliverable; this item exists because the code landed first. Two of the
anchors it was written with are now closed: `SPEC.md:376` (the battle's
"sawtooth through the band-pass") and `AUDIT.md:181` (the same claim in the
audit's prose) were false only while the battle band-passed at a cutoff of 0,
and the `seccut` table on this branch made both true. They are struck; what is
listed above is what is still open.

**What's wrong now.** `sections.s:103` points at `SPEC.md` §6.4 for the texture
arc while `SPEC.md:372-375` still describes the old three-pad hymn.
`test.yaml:82` cites **A15**, which does not exist — `SPEC.md` §12 stops at A14.
`SPEC.md:397-398` still says "112-frame intervals", the exact naive-duration
error corrected in `music.s`. `AUDIT.md:173-174` still carry iteration 2's
measured register rows for the hymn and the Marseillaise, and the texture arc
changed voice 1's waveform in both: the hymn's is a pulse piano now, not a
triangle, and the Marseillaise's is a sawtooth reed, not a pulse.

**How to verify.** Grep every `SPEC.md`/`A<N>` citation in `demos/1812/*.s` and
`test.yaml` and confirm each resolves to text that agrees with it.

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
