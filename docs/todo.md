# TODO

Open items carried out of recent reviews and dogfood runs plus the standing
project backlog. Items are deleted as they land — what was
actually done is recorded in `CHANGELOG.md` and in git history, so this file
stays a list of work still open.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

## From the 2026-08-02 1812 dogfood

Eleven items the 1812 run hit (`demos/1812/`, audit in
`demos/1812/AUDIT.md`). It is the first demo to use a bitmap mode, the first
to need real arithmetic, and the first whose program does not fit comfortably
under its own data — so most of these are gaps that only a graphics-heavy
demo would find. None blocked the run.

**Correctness bugs in shipped docs**

- [ ] **The cookbook's reject-and-retry range trick never yields 0.**
      `skills/c64-development/references/cookbook.md`, "Cheap pseudo-random
      byte (8-bit Galois LFSR)", ends with: "reject-and-retry — `retry: jsr
      random / cmp #40 / bcs retry` — for an **unbiased 0-39**". It is not
      0-39. The LFSR's state is never 0 (0 is its fixed point, which the
      recipe's own text warns about two paragraphs earlier), and the recipe
      returns the state, so the result is uniform over **1-39**. Measured over
      20,000 draws at bounds 4, 8, 16 and 40: every other value within 0.2% of
      uniform, value 0 drawn exactly **zero** times at every bound. A game
      using it to pick a column never uses column 0, which is precisely the
      kind of bug nobody notices. Fix direction: correct the claim to 1-N, or
      change the recipe to `and`/scale. Verify: the arithmetic is checkable by
      hand — `random` returns `seed`, and `seed` is never 0.
- [ ] **Reject-and-retry is also positionally biased, and slow, for small
      bounds.** Separate from the zero bug and worse. Consecutive outputs of a
      right-shifting LFSR differ by one shift, so they are not independent
      draws; rejecting until a value falls below a small bound stops almost
      always on the same bit pattern. In this demo (16-bit LFSR, bound 8, one
      draw among several per shape) two of eight dither patterns never
      appeared across an 889-shape run — `patseen` read `$F3`. It is also
      `256/bound` draws on average, so bounds of 3 and 4 cost 85 and 64 calls;
      that alone blew the demo's frame budget. `demos/1812/spawn.s`'s `rndlt`
      scales instead — `v = (rnd * bound) >> 8`, one draw, reading the freshly
      shifted-in high bits — and the comment there explains why. Fix
      direction: the cookbook should carry the warning and the scaling
      alternative next to the LFSR recipe. Verify: simulate the recipe; no
      emulator needed.

**CLI**

- [ ] **`assert:` does not accept `at_least`/`at_most`, and says so as a bare
      `KeyError`.** They work in `wait:` only. `c64 test run` on a spec using
      them prints `error: 'equals'` — no step number, no key name, no file, no
      line — because `_check_mem` (`src/c64lib/testing.py:587`) falls through
      to `arg["equals"]` and the exception escapes. Contrast the excellent
      symbol error two lines of output earlier, which lists every known
      symbol. Fix direction: validate the comparison key per step kind and
      name the offending step; and either add the two comparisons to `assert`
      or document the split. `docs/cli.md`'s `c64 test run` shows the whole
      comparison list inside a `wait:` example, which reads as if it applies
      to both. Verify: `tests/test_testing.py`.
- [ ] **A `call:` step is terminal for the run, and nothing says so.**
      `c64 call` JSRs with a fake return address and stops at a trap, which
      discards the PC the program was running at — so any `until:`/`wait:`
      after a `call:` in the same spec fails with the machine back at
      `READY.`. It cost a full 120-second test run to find, and the fix is to
      put every routine-level test last (`demos/1812/test.yaml` now says so in
      a header comment). Fix direction: one sentence in `docs/cli.md` under
      both `c64 call` and the `call:` step. Verify: doc-only.
- [ ] **No sample-vs-sample equality in the test runner.** `sample:` supports
      `differs`/`greater_than`/`less_than` but not equality, so "this counter
      did **not** change" is inexpressible — which is exactly the assertion a
      hold/pause/game-over state needs. 1812 wanted "`shapes` is unchanged 120
      frames into the hold" and had to fall back to a proxy (`painting == 0`),
      leaving the real claim to the evidence script. Fix direction: an
      `equals:` (or `unchanged:`) branch alongside the three in
      `src/c64lib/testing.py:570`. Verify: `tests/test_testing.py`.
- [ ] **`c64 test run --json` emits no `tests` key when the spec itself is
      bad.** A spec-level error prints `error: …` and a payload without
      `tests`, so a harness parsing the JSON crashes instead of reporting the
      failure. Fix direction: always emit the envelope. Verify:
      `tests/test_cli_test.py`.

**Skills and cookbook**

- [ ] **Equates never reach the label file, so tests cannot name them.** A
      plain `MULA = $24` is invisible to `ld65 -Ln`, so `c64 mem write MULA 5`
      fails with "unknown symbol" while every `label:` in the same file
      resolves. The fix is `.export`/`.exportzp`, and nothing in
      `skills/6502-assembly/SKILL.md` mentions it — the skill's debugging
      section says "`c64 run FILE.s` registers the labels" without the
      qualification. This bites every hardware equate and every zero-page
      alias a test wants to poke. Fix direction: a bullet in the skill's
      "Debugging" section. Verify: build anything with an equate and grep the
      `.lbl`.
- [ ] **`c64 until LABEL --count N` is a frame count only if the loop is
      frame-paced.** The cookbook's frame-stepping recipe is correct for its
      own example because that loop waits on the jiffy clock, but the text
      generalises it to "deterministic frame stepping" with no caveat. A main
      loop that spins — 1812's does, because it drains a queue — makes
      `--count 600` return in microseconds, and the very first probe of this
      run mis-measured because of it. Fix direction: a caveat in the cookbook
      recipe and in `SKILL.md`'s anchoring section — the anchor must be
      executed *once per frame*; if the main loop free-runs, anchor on the IRQ
      handler instead. Verify: doc-only.
- [ ] **No bitmap recipe anywhere.** `references/hardware.md` gives the mode
      bits and the address formula, and `docs/graphics-and-sprites.md` permits
      bitmap modes, but there is no worked example — so this demo derived from
      scratch the row-address table that replaces the multiply, which nybble
      of screen RAM is bit-pair 01 versus 10, and how to fill whole bytes
      along a span with masked end cells. That is the expensive part of any
      bitmap demo. Fix direction: a cookbook recipe — set the mode, clear the
      canvas, plot one span — cross-referenced from the graphics doc. Source
      material: `demos/1812/raster.s`'s `spanfill` and `tables.inc`.
- [ ] **No multiply recipe.** Any demo doing geometry, physics or scaling
      needs a signed 8x8 -> 16 multiply, and there is none in the cookbook.
      1812 shipped two: a shift-add (330 cycles) and then quarter squares,
      `a*b = f(a+b) - f(a-b)` with `f(x) = floor(x*x/4)`, at **141**. The
      table-building trick is worth the recipe on its own — `f` is
      accumulated from its own first difference, so the generator needs no
      multiply either, and it runs at startup into `$C000` so it costs the
      `.prg` nothing. Fix direction: a cookbook recipe. Source:
      `demos/1812/raster.s`'s `smul`/`umul`/`qsgen`.
- [ ] **BSS consumes address space, and nothing warns about the ceiling.**
      `skills/6502-assembly/SKILL.md` warns that BSS is not in the `.prg` (so
      initialise it), but not that it is still *allocated* after DATA — so a
      program with a fixed data region above it (a bitmap at `$2000`, a
      charset at `$3000`) can silently overrun into it as the code grows. The
      symptom is a demo painting over its own data with no build error. The
      idiom that fixes it is a deferred linker assertion, which is not
      documented either:
      `.assert (__BSS_LOAD__ + __BSS_SIZE__) <= $2000, error, "…"`.
      It fired twice during this run and is why the demo still works. Fix
      direction: extend the skill's "Where runtime data lives" section. Verify:
      doc-only.

