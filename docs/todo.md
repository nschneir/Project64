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
items below.

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
bookkeeping gets written outside `.superpowers/` at the moment it is produced —
`docs/superpowers/decisions/` for durable records, `docs/todo.md` for
friction, the repo's own docs for anything a reader needs. Treat the workspace
as strictly scratch. A prerequisite run for a *sibling* plan writes into the
sibling's workspace, never the caller's.

**How to verify.** Before any `rm -rf` of an SDD workspace, list what the plan
owed and confirm each artifact exists somewhere the deletion cannot reach.

## `c64 test run`'s `sample`/comparison ops read one byte

**Anchor:** `testing.py` `sample`/`greater_than` handling (`testing.py:842`);
`demos/1812/test.yaml`'s `shapes greater_than s0` step.

**Status:** unfixed, and currently passing on margin rather than on logic.

**What's wrong now.** `sample` captures a single byte, so a `greater_than`
against a 16-bit counter compares low bytes only. In `demos/1812/test.yaml` the
sampled `shapes` low byte runs 179 → 224 — a rise of 45 against a wrap at 77.
It passes, and it would keep passing if the counter's high byte moved instead;
it would spuriously *fail* if the true rise crossed a multiple of 256.

The same class bit twice more in the 1812 pass: `noteidx` is one byte and wraps
at 256 (section 2 runs 300 events → 44), and a `differs` witness had to be
hand-checked against the possibility of two instants coinciding.

**Fix direction (not ruled).** A two-byte sample and comparison in the test
runner. **CLI/MCP lockstep is the cardinal rule** — it has both front ends or
it is not a proposal.

**How to verify.** A spec that samples a 16-bit counter across a boundary where
the low byte falls while the value rises; it must pass with a two-byte
comparator and fail with today's.

## `c64 profile --samples` does not vary what it profiles

**Anchor:** `c64 profile`, `docs/cli.md:551-563` (which recommends `--samples`
for bimodal routines).

**Status:** unfixed; the doc's advice is misleading for most routines.

**What's wrong now.** `profile` re-enters a routine with a synthesised JSR and
whatever inputs are already in memory. For `smul`, `xform`, `spanfill` and
`drawshape`, N samples therefore redraw the *same case* and differ only by
badline DMA — they measure jitter, not the distribution the doc is pointing at.
`spanfill`'s real bimodality lives in `spxa`/`spxb`, which `--samples` never
touches. `seqtick` is the only routine in the 1812 set that advances its own
state between samples.

Consequence during the pass: four routines looked like large regressions at a
single anchor until their inputs were controlled by hand.

**Fix direction (not ruled).** Either document the limitation precisely at
`docs/cli.md:551-563`, or give `profile` a way to vary inputs between samples
(a poke set per sample). Documentation alone is a legitimate outcome.

**How to verify.** Profile `spanfill` with `--samples 32` and confirm the
spread is DMA-width, not span-width; then poke `spxa`/`spxb` to their extremes
and confirm the real range is far wider.

## `c64 mem read` of `$D800` returns open bus in the high nybble

**Anchor:** `c64 mem read` / the `c64_mem_read` MCP tool, against
`$D800-$DBFF`; `demos/1812/test.yaml:30`, the one masked colour-RAM assertion
in that file; `docs/cli.md`'s `mem read` section.

**Status:** open as documentation. The behaviour is the hardware's, not a bug
in the tool; what is missing is any warning that a raw comparison there is not
a valid instrument.

**What's wrong now.** Colour RAM is four bits wide, so a read returns
`(phi1 & $F0) | storage` — the high nybble is whatever was last on the data
bus. It is uniform across a whole dump and varies with where the machine
stopped. Two dumps of the **same** build can therefore differ in all 1000
bytes, and two dumps of *different* builds can agree by luck. This was
independently reproduced twice in the 1812 iteration-3 pass, the first time as
a false "the optimisation changed the palette stamp" alarm: nine dumps showed
high nybbles of 0, 5, 11, 13 and 15, and re-hashing the preserved low nybbles
under each of the sixteen possible high nybbles reproduced the anomalous
checksum exactly, at n = 1. A batch that did compare equal raw did so only
because all three of its runs happened to stop where `phi1` was 0.

**Fix direction (not ruled).** Document it beside `mem read` in `docs/cli.md`,
and say plainly that only a masked comparison is valid at `$D800`. Masking
inside the tool is the wrong answer — the open-bus value is real and someone
may want it — but if any behaviour changes, **CLI/MCP lockstep is the cardinal
rule**.

**How to verify.** Dump `$D800` for 1000 bytes twice from one unchanged build,
stopped at two different points, and compare raw: the dumps differ. Compare the
same two masked with `$0f`: zero bytes differ.

## `c64 until REF --count N` costs a monitor round-trip per arrival

**Anchor:** `c64 until`, `demos/1812/test.yaml`'s `until` anchors.

**Status:** unfixed. A performance trap, not a correctness one.

**What's wrong now.** A high `--count` on a frequently-hit reference takes tens
of minutes — a `seqtick --count 10200` anchor where five `secchange` arrivals
take about three. The failure mode is that a slow anchor is indistinguishable
from a wedged VICE, which is a diagnosis this repo has already paid for once.

**Fix direction (not ruled).** Either count arrivals emulator-side, or document
the cost beside `until` so the next reader picks a sparse reference.

**How to verify.** Time `until seqtick --count 1000` against
`until secchange --count 5` on `demos/1812` and record both in `docs/cli.md`.

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

**Anchor:** `demos/1812/AUDIT.md` A13; `smul`, `rnd` in `demos/1812/raster.s`.

**Status:** open.

**What's wrong now.** "`smul` 141" is reproducible only with both operands
negative and the smaller magnitude first. "`rnd` 72" needs a badline inside a
35-cycle window — `rnd`'s real paths are 29 and 38 cycles. A reader who
re-measures gets different numbers and cannot tell whether something regressed.

**Fix direction (ruled).** Iteration 3's audit entry records min/max/mean with
a sample count and the anchor each figure was taken at, not a bare number.

**How to verify.** Re-profile from the recorded command line and land inside
the recorded range.

## The patched-differential profiling method is 6.2% low, and nobody knows why

**Anchor:** `demos/1812/AUDIT.md`'s iteration-3 performance section, candidate
5; the `sfclip` / `cssort` / `sfnext` labels in `demos/1812/raster.s`, which are
the patch points; the method itself, which this repo reaches for whenever a
routine has an entry symbol but no `rts` of its own and so cannot be bracketed
by `c64 profile`.

**Status:** open and **undiagnosed**. Not a correctness problem — the change it
was measuring cleared every gate — and the error runs in the safe direction.

**What's wrong now.** One change measured three ways. The two **unpatched**
worst-case profiles agree with each other to 97 cycles: `c64 profile scanfill`
gives −12,727 and `c64 profile drawshape` gives −12,630, a 0.02% spread on a
`drawshape`. The **patched** L1−L2 differential — the number the commit body
quotes — gives **−11,990**, which is 640–737 cycles lower, **6.2% of its own
value** and about **8× the ±90** band a difference of two single arrivals
carries. So the method that has to be used on un-bracketable routines is the
one that disagrees, and it under-reports.

**Two mechanisms were proposed during the pass and NEITHER was tested.**
(1) *Page crossing.* The change shifts everything after it by 47 bytes, which
moves absolute-indexed operands across page boundaries and changes their cost —
the same 47-byte shift that moved `seqtick` from `$1419` to `$1448`.
(2) *The stripped context.* Both patched legs `jmp` past the row body, so both
run a program with `spanfill`'s 288,302 cycles of fill deleted from between the
scanline rows, and badline steals land differently there than in the real one.

**Fix direction (not ruled).** (1) is testable offline: diff the two `.lbl`
files, find which absolute-indexed operands in the hot path changed page, and
count the added cycles. (2) needs a leg that keeps the fill — bypassing the
sort with `cssort → jmp sfclip` rather than `→ jmp sfnext` leaves the row body
running — with the caveat that unsorted crossings can change what `spanfill`
draws and therefore what it costs, which is precisely why the original method
deleted the fill instead. Whichever is found, the outcome belongs beside the
method in `docs/cli.md`, not only in this demo's audit.

**How to verify.** Three measurements of one change agree inside their stated
bands — or the gap is reported with a mechanism that has been tested rather
than proposed.

## Two stale headroom comments, and one loose duration

**Anchor:** `demos/1812/vars.s:81-82`, `demos/1812/raster.s:272`,
`demos/1812/sections.s:147`.

**Status:** open, all three pre-existing.

**What's wrong now.** `vars.s:81-82` and `raster.s:272` both say "under 100
bytes of headroom"; the real figure was 252 before iteration 3, 184 after the
arrangement work, and is **120** now — the performance pass spent 47 more on
the two-crossing case. (`$2000 − (__BSS_LOAD__ $1F2E + __BSS_SIZE__ $5A)`.)
Both comments are still wrong, but by 20 bytes rather than by 150, and the
figure has now moved three times in one iteration — so whoever fixes them
should consider saying "see `1812.lbl`" instead of quoting a number at all.
`sections.s:147` says "the anacrusis is 16-frame notes" — naive
duration; an event owns `duration + 1`, so it is 17 frames. The last one was
reviewed and judged harmless (nothing depends on the number; the sentence
exists to justify attack 1 over attack 6), but it is the same family as the
onset-count error that *was* load-bearing and got fixed.

**How to verify.** Re-derive free-below-`$2000` from `1812.lbl` and confirm the
comments match; for `sections.s:147`, confirm against `voicetick`'s countdown.
