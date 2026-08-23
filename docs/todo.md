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
lifetime-mark asserts to their windows. The 1.0.0 pre-release review then
added one item of its own (`wait_for_break`, at the end of this file), so
five items remain, all real work.

The 2026-08-23 Debian/Ubuntu-focus review then landed its ten confirmed
findings (`CHANGELOG.md`'s Unreleased section has the inventory) and left the
items below it verified but did not fix — everything from the UTF-8 sweep's
two edges to the five Linux-portability findings that were judged out of the
branch's scope rather than out of the tree's.

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

## `wait_for_break`'s lost-event fallback can never fire on VICE 3.10

**Anchor:** `src/c64lib/ops.py:732` (`wait_for_break`, the `ck.hit` poll);
`src/c64lib/daemon.py` (`_run_until`'s equivalent expression); the corrected
comments at ops.py's three `hit_count > i` sites, which carry the
measurement.

**Status:** filed 2026-08-14 by the 1.0.0 pre-release review's probe of a
*different* (refuted) finding — the probe that cleared `profile_samples_loop`
convicted this site instead.

**What's wrong now.** `wait_for_break` polls CHECKPOINT_LIST's `hit` flag as
its fallback for a lost STOPPED event, and its docstring claimed the flag
stays "visible in CHECKPOINT_LIST even when the STOPPED event was lost".
Measured on VICE 3.10 (direct monitor connection, once-reached checkpoint):
**the `currently hit` byte is never set in a CHECKPOINT_LIST entry — not
even while the machine sits stopped on that exact checkpoint.** VICE sets it
only in the CHECKPOINT_GET response pushed with the stop event. Reproduced
end to end: checkpoint hit with no client attached, fresh connection reads
`hit=False, hit_count=1`, and `wait_for_break(timeout=3)` times out on a
checkpoint that had already been hit. Nothing fails in the field only
because the session daemon's single long-lived connection never loses the
STOPPED event — the fallback is dead code guarding a case it cannot catch.
The docstring was corrected to state the measurement; the behaviour was
deliberately left alone.

**Fix direction (not ruled — it is a redesign, not a patch).** Polling
`hit_count` against a baseline taken at entry would detect a hit that
happened while disconnected, but silently drops the "machine is already
stopped at the breakpoint when the wait starts" case the flag poll was meant
to catch; distinguishing the two needs the machine's stopped/running state
read alongside the count. Whatever lands must keep `c64 wait --break`'s
documented semantics (resumes, stops at the NEXT hit) and land on both front
ends. A regression test now exists to catch the other direction:
`tests/test_ops.py::test_checkpoint_list_hit_flag_is_not_latched` fails
loudly if a future VICE starts filling the flag in.

**How to verify.** With a checkpoint already hit and no event in hand (fresh
connection), `wait_for_break` must report the hit rather than time out — the
measured reproduction above is the test's shape — and the already-stopped
case must still return immediately.

## Demo `tools/` scripts still do locale-dependent text I/O

The UTF-8 sweep that put `encoding="utf-8"` on every text-mode open in
`src/`, `tests/` and `skills/` — and the `PLW1514` ruff rule that keeps it
that way — stopped at the lint gate's edge. Demo `tools/` scripts are
deliberately outside both gates (AGENTS.md says why: they are the demo's own
artifact, tested by the demo), so `ruff check demos --select PLW1514` still
reports 5 sites, with ~14 files doing `read_text`/`write_text`/`open` in all.

**Why it matters.** These are the scripts a person regenerates a demo's
tables, score or sprites with, and several read files containing `♯`/`♭` and
em dashes. On a Debian/Ubuntu box whose locale is not UTF-8 they raise
`UnicodeDecodeError` exactly as `tests/test_docs_cli.py` did before the
sweep.

**Why it was not just done.** Sweeping them is mechanical and safe, but with
`demos/` outside the ruff gate the fix would carry no regression guard, and
bringing `demos/` into the gate is a separate decision: it currently reports
95 ruff errors (79 of them E501), so that is a cleanup of its own, not a
line in a UTF-8 commit.

**Fix direction.** Either sweep `demos/` and accept an unguarded fix, or
clean `demos/` up to the full ruleset and add it to
`ruff check src tests skills`. The second is the one that stays fixed.

**How to verify.** `ruff check demos --select PLW1514` reports nothing, and
`LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0` runs of the demo generators
produce byte-identical output to a UTF-8 run.

## `PLW1514` guards the UTF-8 sweep only where ruff can see a `Path`

The rule fires on a receiver it can prove is a `pathlib.Path` — a literal
`Path(...)` call, or a name annotated as one — and on the builtin `open`.
That is why it reported 129 sites while the sweep actually rewrote 575: the
other ~446 are shapes ruff will not type-infer. Measured:

    (tmp_path / "x").read_text()   # NOT flagged
    p.read_text()                  # NOT flagged (p un-annotated)
    tmp_path.read_text()           # flagged (tmp_path: Path)

So the guard holds `src/` well, where paths are annotated and constructed
explicitly, and holds the common test shape `tmp_path / "name"` not at all.
New test code can reintroduce a locale-dependent read and the gate will stay
green.

**Fix direction.** Annotate the fixture-derived locals, so ruff sees the type
(verbose, and fights the house style); or add a narrow repo check — an AST
pass over `read_text`/`write_text`/`open` like the one that performed this
sweep, run as a test — which needs no inference at all and is the honest
shape of the guard. The second is cheap: the sweep script was ~120 lines and
already distinguishes text from binary and positional from keyword
`encoding`.

**How to verify.** Add `(tmp_path / "x").read_text()` to any test file; the
gate must go red. Today it does not.

## Nine skip guards ask PATH and never ask the env override

**Anchor:** `tests/conftest.py:40-44` (`HAVE_X64SC` / `HAVE_C1541`, the
resolution order every guard should mirror) against the guards in
`tests/test_basic.py:42`, `tests/test_basic_tokens.py:120`,
`tests/test_packaging.py:16`, `tests/test_docs_rom_basic.py:39`,
`tests/test_docs_cookbook.py:79`, `tests/test_sprites.py:321` (all six
`petcat`), plus `tests/test_cli_cart.py:16` (`cartconv`),
`tests/test_integration_cart.py:17` (`ca65`, `ld65`, `cartconv`) and
`tests/test_disk_build.py:20` (`ca65`, `ld65`).

**Status:** filed 2026-08-23 by the Debian/Ubuntu review. Verified by reading
every `shutil.which` in `tests/`: the x64sc guards all spell
`which("x64sc") or os.environ.get("C64_TOOLS_X64SC")`, and one site in
`test_docs_cookbook.py` (`:451`) gets `ca65` right, so the shape is already
house style — these nine are the ones that were not converted.

**What's wrong now.** `src/` resolves every external tool as *env override
first, PATH second* — `C64_TOOLS_PETCAT`, `C64_TOOLS_CA65`, `C64_TOOLS_LD65`,
`C64_TOOLS_CARTCONV`, `C64_TOOLS_C1541`, `C64_TOOLS_X64SC` are all read. The
nine guards above ask `shutil.which` alone. So on the exact host the
overrides exist for — a Debian box with VICE or cc65 installed somewhere
`PATH` does not name, which is the normal shape of a hand-built VICE or a
`/opt` cc65 — the library will happily run the tool and the tests silently
skip. A green run reports coverage it did not have, and the skip reason
("petcat not installed") is false on that machine.

**Fix direction.** Mechanical: give each tool one module-level predicate in
`tests/conftest.py` beside `HAVE_X64SC`/`HAVE_C1541` (`HAVE_PETCAT`,
`HAVE_CA65`, `HAVE_LD65`, `HAVE_CARTCONV`) and have the nine guards import it,
so there is one resolution order in the suite rather than a spelling per file.
Better still, resolve through the same `src/` helper the library uses, which
cannot drift from it at all.

**How to verify.** Move `petcat` out of `PATH`, point `C64_TOOLS_PETCAT` at
it, and run the six petcat files: they must run, not skip. Today they skip.

## Subprocess output is decoded in whatever the host locale says

**Anchor:** `src/c64lib/basic.py:42` (petcat), `src/c64lib/build.py:112`
(ca65/ld65), `src/c64lib/disk.py:171` (c1541), and the three
`errors="replace"` sites in `src/c64lib/session.py` (`:131`, `:182`, `:232`).
The one site already thought about is `src/c64lib/cartridge.py:258`, which
catches `UnicodeDecodeError` and turns it into a `CartError`.

**Status:** filed 2026-08-23. Deliberately out of the UTF-8 sweep's scope —
that commit's rule was "every text-mode `open`/`read_text`/`write_text` names
`utf-8`", guarded by `PLW1514`, and `subprocess.run(text=True)` is neither an
`open` nor a shape `PLW1514` sees. Excluding it kept the sweep mechanical and
reviewable; it did not make these sites right.

**What's wrong now.** `text=True` with no `encoding=` decodes with
`locale.getencoding()`. On a genuinely non-UTF-8 host — `LANG=C` with
C-locale coercion disabled, which is what a cron job, a container or a
stripped systemd unit can leave behind — that is ASCII, and any non-ASCII
byte in an assembler's or `c1541`'s diagnostic raises `UnicodeDecodeError`
from inside `subprocess.run`. Three of the four unguarded sites are on the
error path of a build: the failure a user gets is a traceback about decoding
instead of the compiler error that actually stopped them. The `session.py`
trio cannot raise (they pass `errors="replace"`), but they still decode a
command line under the host locale, so `_pid_is_session`'s substring match is
comparing mojibake against a UTF-8 marker on such a host.

**Fix direction.** `encoding="utf-8", errors="replace"` on all seven — the
same treatment `cartridge.py` reached for, and the same argument the file
sweep made: these are tool diagnostics, and every tool in the set emits
UTF-8 or ASCII. `cartridge.py`'s guard then becomes belt-and-braces rather
than the only seatbelt in the car.

**How to verify.** Under `LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0` — the
same triple the `demos/` item above uses — make `ca65` fail with a non-ASCII
byte in its message (a source path with an em dash does it) and confirm
`c64 build` reports the assembler's error rather than a `UnicodeDecodeError`.

**Which of those three variables actually does the work**, because getting
this wrong yields a green run that proves nothing. Two separate mechanisms
turn a "C" locale back into UTF-8, and they answer to different spellings.
Measured with `python3 -c "import locale; print(locale.getencoding())"` on
the maintainer's Mac, which has a `C.UTF-8` target like Debian does:

    LC_ALL=C PYTHONUTF8=0                        -> US-ASCII
    LANG=C   PYTHONUTF8=0                        -> UTF-8
    LANG=C   PYTHONCOERCECLOCALE=0 PYTHONUTF8=0  -> US-ASCII
    LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0  -> US-ASCII

- **`PYTHONUTF8=0`** turns off PEP 540 UTF-8 mode. Always needed.
- **`LC_ALL=C` beats `LANG=C`.** CPython skips PEP 538 coercion outright
  whenever `LC_ALL` is set and non-empty, so `LC_ALL=C` reaches ASCII on its
  own — on any platform, Debian included. `LANG=C` alone gets coerced to
  `C.UTF-8` and silently stays UTF-8. Under `PYTHONCOERCECLOCALE=warn` the
  interpreter says so: "Python detected LC_CTYPE=C: LC_CTYPE coerced to
  C.UTF-8".
- **`PYTHONCOERCECLOCALE=0`** is therefore redundant beside `LC_ALL=C` and
  load-bearing only in the `LANG=C` spelling. It is kept in the recipe as
  belt-and-braces, and so this item and the `demos/` one stay copy-pasteable
  into each other.

This is not a macOS-versus-Linux difference: the coercion guard is
platform-independent, and both spellings behave here exactly as they do on
Debian.

## "VICE 3.5+" is advertised and nothing checks it

**Anchor:** `README.md:19` ("Requires **Python 3.11+**, **VICE 3.5+**"), and
the four error hints that repeat the figure — `src/c64lib/session.py:578`,
`src/c64lib/cartridge.py:245`, `src/c64lib/disk.py:163`,
`src/c64lib/basic.py:27`.

**Status:** filed 2026-08-23. The number is a documented requirement with no
enforcement anywhere in the tree: nothing runs `x64sc --version`, and no
capability is probed except `-minimized` (`_supports_minimized`, which
probes `--help` for exactly one flag and caches per binary path).

**What's wrong now.** Debian oldstable and Ubuntu LTS both ship VICE builds
older than the binary-monitor era this toolset is built on. On such a host
`x64sc` starts, `-binarymonitor` is either rejected outright or ignored, and
what the user sees is a monitor connect timeout — a failure that names the
socket, not the version. The person who installed VICE from `apt` and read
the README has no way to connect the two.

**Fix direction (not ruled).** The cheapest honest check is the shape
`_supports_minimized` already uses: probe `--help` once per binary path for
`-binarymonitor` and fail the launch with "this VICE has no binary monitor —
Project64 needs VICE 3.5+" when it is absent. Parsing `--version` is the
other option and is worse: the string format has moved across releases and a
distro patchlevel says nothing about the feature. Whichever lands, the
figure in the README and the four hints should be generated from, or at
least verified against, the thing the code actually requires.

**How to verify.** Point `C64_TOOLS_X64SC` at a VICE older than 3.5 (or at a
stub whose `--help` omits `-binarymonitor`) and run `c64 session start`: it
must say the version is too old, not time out on a monitor connection.

## Nothing in the tree manages Xvfb; the preflight only points at it

**Anchor:** `src/c64lib/session.py:572` (the launch refusal naming
`xvfb-run -a c64 session start`), `_display_available()` beside it, and the
suite-side skips at `tests/conftest.py:71` and `:355`.

**Status:** filed 2026-08-23, and **deliberately scoped out** — the review's
finding was "a headless Linux launch fails obscurely", and failing fast with
the remedy in the message closes that. This item is the larger thing the fix
did not attempt.

**What's wrong now.** On a Linux host with no display the toolset now says
what to do, and the user does it: every `c64` invocation, every pytest run,
every MCP server start has to be wrapped in `xvfb-run -a` by hand. Nothing
starts an Xvfb, nothing reuses one across invocations (so a wrapped run pays
a server start per command), and nothing verifies one is actually usable
before the emulator is launched — `_display_available()` only checks that
`DISPLAY` or `WAYLAND_DISPLAY` is non-empty, which a stale value satisfies.

**Fix direction (not ruled, and explicitly conditional).** Revisit if Linux
CI lands: at that point a session-scoped Xvfb — started once, `DISPLAY`
exported into the children, torn down at the end — is worth building, and
the natural home is beside the session record so one display serves the
daemon and every command that talks to it. Until then the wrapper is the
user's move and the fast failure is the whole contract.

**How to verify.** Whatever lands, `c64 session start` on a display-less
Linux box must work with no wrapper and no exported `DISPLAY`, and two
successive commands must share one Xvfb rather than starting two.

## Session identity matches a basename anywhere in a stranger's command line

**Anchor:** `src/c64lib/session.py:98` (`_pid_is_session`), its caller
`SessionRecord.is_alive()` at `:781-786`, and the `-binarymonitoraddress`
argument `launch` writes into argv at `:662`.

**Status:** filed 2026-08-23 by the review that produced the fix this item
narrows. Before it, `is_alive()` asked `_pid_alive` — the pid NUMBER — and a
recycled pid made a dead record immortal. `_pid_is_session` closes the case
that matters (the number now has to belong to a process running the
emulator) and the residue is the case below.

**What's wrong now.** The marker is the emulator's basename — `self.exe`, or
the model's `vice_emulator` for a record written before `exe` existed — and
the test is `m in cmdline` over the whole command line. So the check cannot
tell one x64sc from another: a recycled pid that lands on **another
session's** x64sc (or on any command line that merely mentions the string,
`grep x64sc` included) still reads alive. On a shared build host running
several sessions this is exactly the collision the pid-recycling fix was
about, one level in. `stop()` then aims its SIGTERM at the wrong emulator.

There is a second, smaller residue in the same function's neighbourhood:
`stop()` still identifies the daemon by number alone
(`_pid_alive(self.daemon_pid)` at `:809`), so the daemon half of a session
keeps the original bug.

**Fix direction.** The discriminator is already in argv: `launch` passes
`-binarymonitoraddress ip4://127.0.0.1:{port}` with the session's own port,
and the record stores that port. Require BOTH the exe basename and that
port string to appear in the command line and the check identifies *this*
session's emulator rather than any emulator. Keep the existing
doubt-reads-as-dead bargain — a record from before the port was recorded
falls back to today's behaviour. The daemon pid wants the same treatment
against whatever its own argv carries.

**How to verify.** Start two sessions, take the pid of the first, and hand
it to the second record's `is_alive()`: it must report dead. Today it
reports alive, because both command lines contain `x64sc`.
