# TODO

Open items carried out of recent reviews and dogfood runs. Items are deleted
as they land — what was actually done is recorded in `CHANGELOG.md` and in git
history, so this file stays a list of work still open.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

Last triaged 2026-08-14, twice. A landing pass closed seventeen items in one
change (`CHANGELOG.md`'s Unreleased section has the inventory), and a
maintainer-approved sweep then closed six more of the survivors by moving
each one's surviving knowledge to a tracked home instead of keeping the item:
1812's four unanchored A13 figures are annotated as non-baselines in its
`AUDIT.md`; the alt-text re-read reminder sits beside `secpal` in
`demos/1812/sections.s`; the ROM-refresh matched-pair rule and the tile-art
acceptance are in `play.html`'s constants comment; the capture-aiming item
was dropped as defused (fugue's `--align-log`, and `audio-verification.md`
already records pin-or-omit as the standing duration tradeoff); and
la-galaxia's `tick_overrun` flake was fixed outright by scoping both
lifetime-mark asserts to their windows. Four items remain, all real work.

## No capture can be anchored to the frame top, and every evidence PNG churns

**Anchor:** `docs/graphics-and-sprites.md` §5 (the churn note after the rules
table, which carries both measurements) and §6 (the deferral);
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
and all. §5 and §6 were corrected in the landing pass; what remains is the
tool.

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

**Anchor:** `c64 test run --json` and `c64 package --json` in `docs/cli.md`.

**Status:** open. Two gaps, both discovered while trying to turn a command's
output into something a tracked document could quote. (A third — `c64 mem
get` printing a 16-bit observable as two little-endian decimal bytes — was
triaged out 2026-08-14 as a nicety: the byte arithmetic is documented under
the command and the cost is a multiplication, not a wrong citation.)

**Triage 2026-08-14: left as proposals.** Both change a documented payload
surface, and the house rule for that is a spec of its own per addition
(`AGENTS.md`: every addition lands on both front ends with tests and docs in
the same change). Neither is blocking: the workarounds — quote only asserted
values, stat the `.lbl` — are in use and recorded where they bit.

**What's wrong now.** *`c64 test run --json`* prints its step details to
stdout and nowhere else: there is no `--out FILE`, and the payload
(`{"passed": true, "tests": [{"name", "elapsed", "steps": […]}]}`) carries no
run id, timestamp, build hash or machine, so a redirect saves a file that
cannot say which build it ran against. Two runs of `demos/1812/test.yaml`
were byte-identical in every `detail` string — the property that made the
numbers safe to quote — and nothing in the output would have told a later
reader that; the 1812 audit had to be rewritten to quote only values the
tracked `test.yaml` *asserts*. *`c64 package --json`* reports
`{"prg", "image", "title", "run"}` and no labels key, while the assembly path
rewrites the output's `.lbl` on every invocation; the gap is documented under
that command, but the payload still cannot say the file moved, and evidence
scripts depend on the `.lbl` being in step with the `.prg`.

**Fix direction (proposals, both front ends each).** `--out FILE` on
`c64 test run` with an `out` argument on `c64_test_run`, plus a header block
in the payload naming the program, its mtime or hash, the machine model and
the timestamp — enough that a saved run is evidence and not a transcript. A
`labels` key in the non-cartridge `c64 package` payload, matching the one the
cartridge payload already has, surfaced identically by `c64_package`.

**How to verify.** Each: run the command, and confirm the artifact it
produces answers "which build, on which machine, when" without a human
adding it.

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

**Triage 2026-08-14: left — blocked on the decision it names, but the
decision may be cheaper than this item first assumed.** The ROM images are
already vendored and sha256-pinned in the maintainer's own
`vc64web.github.io` fork under `roms/`, so "reachable from a test run" can
mean fetching from that fork (or a sibling checkout) rather than adding ROM
bytes to this repository. That reframes the open question from "do we vendor
third-party ROMs" to "is a test that fetches from the fork acceptable" —
still the maintainer's call.

**What's wrong now.** Every demo's regression suite runs under VICE, which
reads ROM bytes from the emulator the developer installed — Commodore's.
`play.html` boots the same programs on MEGA65 open-roms instead. Nothing
exercises the second set. open-roms is not cycle-exact with the Commodore
KERNAL and its BASIC is deliberately incomplete (that project's own
`STATUS.md` says so), so a change that starts calling a KERNAL routine these
demos currently avoid would pass `c64 test run` and break the play page
silently. Today they use only `RUN` + `SYS` and then take the machine over,
which is the whole reason the open ROMs work at all; nothing enforces that
they keep doing so.

The gap is wider than "CI does not cover it": `.github/workflows/` holds
`release.yml` and nothing else, so the demo suites are not run by CI at all.
Whatever closes this has to be a check a person or a hook actually runs.

**Fix direction (not ruled).** A smoke check that boots each `.prg` to its
first playable frame on the open ROMs and asserts the same screen the
`test.yaml` first step does. The narrow `$CB` guard is not a substitute: it
knows about one byte.

**How to verify.** Whatever is built, the check must fail when a demo starts
depending on the Commodore KERNAL. A cheap proof it works: point it at a demo
patched to `JSR` into a KERNAL entry open-roms does not implement, and confirm
it goes red while `c64 test run` for that demo stays green.

## Fork maintenance: the GPL licence, the handler leak, and the footer

**Anchor:** the `nschneir/vc64web.github.io` fork — `vc64.wasm` and `vc64.js`
at its root, `js/vc64web_player.js` (`load_into()` at `:208`/`:219` against
`stop_emu_view()` at `:362-377`); this repo's `LICENSE` "Third-party
components" section and `play.html`'s `EMU_BASE` and footer.

**Status:** open, **the maintainer's call, and all of it lives in the fork**
— merged 2026-08-14 from two items into one because it is one sitting of
work in one repository this checkout cannot edit. Three parts, in order of
weight:

**1. The licence (contestable, filed so the call is made rather than
inherited).** vc64web is a WebAssembly build of VirtualC64, which is GPL-3.0
— this repo's own `LICENSE` says so. The fork carries no copy of that
licence: `git ls-tree -r --name-only 5700ccd` (the upstream commit the fork
sits on) matches **zero** paths against `licen|copying|gpl`, and the fork's
33-byte `README.md` and its `index.html` name neither a licence nor a
copyright holder; the only licence text in the fork is
`roms/LICENSE-open-roms.txt`, ours, covering the ROMs only. Serving
`vc64.wasm` from Pages under this account is distribution of a GPL-3.0
binary, and GPL-3.0 §4 asks a distributor to keep notices intact and give
recipients the licence. Cutting the other way: the served `index.html` links
the corresponding source (`github.com/vc64web/virtualc64web`), upstream
distributes in exactly this state, and nothing has been redistributed yet
(the fork is unpushed). What makes it ours to decide is that this repo's
`LICENSE` describes the arrangement. Options, cheapest first: (a) add the
GPL-3.0 text as `LICENSE` at the fork root plus three `README.md` lines
naming the binaries, the licence, and the upstream source with the build
commit; (b) point `EMU_BASE` back at `https://vc64web.github.io/` and keep
only `roms/` in the fork, giving up version pinning and same-origin ROM
hosting; (c) decide the omission is immaterial for a fork of a project's own
deployment repo, and record that here.

**2. The handler leak (upstream residue, two lines, same sitting).**
`load_into()` runs `$(window).on('resize', …)` and
`$(window).on('orientationchange', …)` on every mount; `stop_emu_view()`
removes only `document`'s `click` listener, so k boots leave k handler pairs
attached to `window`, each retaining the detached preview subtree it closes
over. Behaviour stays correct (`$vc64web` is one accidental global all k
handlers resize); the cost is k height writes and k 130 ms timeouts per
resize. Fix in the fork: `$(window).off('resize orientationchange')` at the
top of `stop_emu_view()` — or namespaced registration
(`.on('resize.vc64web', …)` / `.off('.vc64web')`), which is safer if a host
page ever registers its own jQuery handlers. Fixing it from `play.html` was
considered and declined: `jQuery(window).off(...)` there would drop handlers
this page does not own.

**3. The footer wording (falls out of whichever way 1 goes).** `play.html`'s
footer says the emulator is "served from its own site — not bundled" and
links `https://vc64web.github.io/`, while `EMU_BASE` serves it from our
fork. Option (b) above makes the sentence true again; options (a) and (c)
mean rewording the footer here.

**How to verify.** Licence: in the fork,
`git ls-tree -r --name-only HEAD | grep -icE 'licen|copying'` returns at
least the root licence, and once Pages is live
`curl -sI https://nschneir.github.io/vc64web.github.io/LICENSE` returns 200
(for option (b): `grep -c 'nschneir.github.io/vc64web' play.html` returns 0).
Leak: with the player live, boot and stop three times, then read
`jQuery._data(window, "events").resize.length` in the console — 3 today, 0
once `stop_emu_view()` unregisters. Footer: the sentence names where
`EMU_BASE` actually points.
