# AGENTS.md

Instructions for AI coding agents working on this repository's code. (If you
are here to *use* c64-tools to write C64 software, read
`skills/c64-development/SKILL.md` and `docs/cli.md` instead.)

## What this is

Project64 (package `c64lib`, distributed as `c64-tools`): an AI-oriented
toolset for developing and debugging Commodore 64 software on the VICE
emulator. Two front ends — the `c64` CLI and the `c64-tools-mcp` MCP server —
drive the same session machinery.

Where things are documented (don't duplicate them here):

- `README.md` — install, quickstart, supported machine models, per-agent setup.
- `docs/cli.md` — the full CLI reference (man page), one entry per command.
- `skills/c64-development/` + `skills/6502-assembly/` — C64/6502 domain
  knowledge: workflows, memory maps, zero page, ROM routines, cookbook.

## Commands

```sh
pip install -e ".[dev]"        # install with pytest + coverage

pytest                          # full suite (vice-marked tests need x64sc/VICE on PATH)
pytest -m "not vice"            # unit tests only — no emulator required
pytest -m "needs_c1541 and not vice"   # disk subset — needs c1541, never run in CI
pytest tests/test_monitor.py    # one file
pytest tests/test_monitor.py::test_name   # one test

python -m coverage run -m pytest && python -m coverage combine && python -m coverage report
                                # coverage (fail_under=90); subprocesses (daemon, MCP stdio) are measured too

ruff check src tests skills     # lint (config in pyproject.toml); must be clean
                                # `skills` for the scripts shipped in a skill's references/
pyright                         # type check (config in pyproject.toml); must be clean — local-only, CI does not run it
```

Keep shell invocations in the plain form above: one command, executable
first. Wrapping them — `VAR=x .venv/bin/python -m pytest`, `cd dir && …`,
`time …`, `for`/`until` loops — defeats the maintainer's approval allowlist
(it matches on the command prefix) and turns routine commands into approval
prompts. Set environment variables inline only where a test genuinely needs
them, and prefer several simple calls over one chained command.

Tests marked `@pytest.mark.vice` launch a real VICE emulator (`x64sc`);
everything else runs against `tests/fake_vice.py`, an in-process fake of the
VICE binary monitor. `c64 build` needs cc65 (`ca65`/`ld65`); `c64 basic`
needs `petcat`; `c64 disk` needs `c1541` (and `c64 disk build` needs the other
two as well, for its `.s`/`.bas` manifest entries); `c64 cart build`/`convert`
(and any `.crt` output from `c64 package`) needs `cartconv` — all external
subprocesses.

**Everything is validated locally, by decision — CI runs no checks at all.**
The one workflow, `.github/workflows/release.yml`, builds a release dist; no
workflow runs a test or a type check. We don't expect emulators to run on
GitHub, and the pyright gate that briefly lived in
`.github/workflows/checks.yml` was retired by the same local-first ruling: it
pinned the checker but built its venv fresh each run with unpinned
dependencies, so it could turn red on a commit that touched no code. So the
gate is you, on a machine with VICE installed, running the affected subset —
and `pyright` — before you commit; nothing downstream will catch what you
skip. Make that runnable rather than remembered:
guard a test that shells out to `c1541` with `@pytest.mark.needs_c1541` rather
than a local `skipif` (a `skipif` is invisible to `-m`, so the subset can't be
asked for), and `pytest -m "needs_c1541 and not vice"` runs the whole disk
subset — 100 tests, ~6s, no emulator. `tests/conftest.py` turns the marker into
a skip when c1541 is missing, resolving it the way `c64lib.disk` does — PATH or
`C64_TOOLS_C1541` — so the subset skips rather than fails where VICE is absent.

Most live tests share **one** warp+headless emulator, via the session-scoped
fixtures in `tests/conftest.py` — a full run launches ~14 emulators rather than
one per test. Ask for the `session` fixture to get a live C64 at the READY
prompt; it is reset between tests (checkpoints deleted, hard reset, session
record cleared). Only launch your own when sharing would lie: per-model
parameterization, anything attaching a disk image (the binary monitor has no
detach, so an attached image cannot be cleaned up), or a test asserting
launch/daemon-spawn behavior itself.

A run killed before teardown (`kill -9`, CI timeout) still leaks warp-mode
x64sc processes eating a CPU core; the next run reaps them (pids are recorded
at spawn, and only ones that still look like an emulator are killed). To clean
up without running the suite: `pgrep -fl x64sc`. Give live tests generous
timeouts (minutes, not seconds).

## Architecture

Layered, bottom-up in `src/c64lib/`:

1. **`protocol.py`** — pure encode/decode of the VICE binary monitor protocol (API v2). No sockets.
2. **`monitor.py`** — `MonitorClient`, the socket client. Core contract: *processing any monitor command leaves the emulated machine STOPPED*; callers wanting it running must call `resume()`.
3. **The session daemon** (`daemon.py`, `rpc.py`, `daemon_client.py`) — VICE accepts only one monitor connection and resumes the CPU when it closes, so a per-session daemon process holds that single connection for the session's lifetime. Each `c64`/MCP command is a short-lived client on the session's unix socket; `DaemonMonitorClient` is a `MonitorClient` look-alike whose methods are JSON-lines RPC calls (`rpc.py` is the wire codec). This is what makes debug state (a breakpoint halt) persist across commands.
4. **`session.py`** — launch/attach/stop VICE, session records as JSON under `~/.c64-tools` (override with `C64_TOOLS_HOME`). `Session.monitor()` returns the daemon client.
5. **`ops.py`** — shared high-level operations (wait/until primitives, symbol resolution). Exists so the CLI and MCP server cannot drift; put new front-end-facing logic here, not in `cli.py` or `mcp_server.py`.
6. **Front ends** — `cli.py` (click; every command supports `--json`, the intended AI interface) and `mcp_server.py` (FastMCP; returns the same structured data as `--json`).

Supporting modules: `machines.py` (machine model profiles — RAM size, screen geometry, BASIC start), `build.py` (ca65/ld65), `basic.py` (petcat tokenize/detokenize), `disk.py` (c1541-backed d64/d71/d81 images: file CRUD, raw block read/write, `-validate`, and `*.disk.yaml` manifest builds), `screen.py`/`text.py` (screen RAM ↔ text), `symbols.py` (.lbl label files), `disasm.py`, `romdoc.py` (ROM identification/annotation — ships only original label annotations, never Commodore ROM bytes), `packaging.py` (`c64 package` → shareable .d64/.prg/.crt), `cartridge.py` (.crt container parse/verify/dump plus the `cartconv` wrapper), `cart_build.py` (cart-native and wrapped single-region builds, EasyFlash manifest builds, bank-tagged label merging), `testing.py` (declarative YAML test runner).

## Code quality

- **CLI/MCP lockstep is the cardinal rule.** Any new operation goes in
  `ops.py` and is surfaced by both front ends; `cli.py` and `mcp_server.py`
  stay thin. Before adding a command, check `docs/cli.md` for an existing
  one that already covers the need.
- Every CLI command supports `--json`; failures exit 1 via `fail()` with an
  **actionable** message (say what happened *and* what to do next — e.g. a
  timeout says the machine was left running). MCP tools return the same
  structured data as the CLI's `--json` and let exceptions surface with
  their messages intact.
- Lint with `ruff check src tests skills` and keep it clean (rules E/F/W/B/UP/I,
  line length 100 — configured in `pyproject.toml`). `skills` is in the list
  because a skill's `references/` may ship a runnable script — the first is
  `6502-assembly/references/fix-branch-range.py` — and a tool an agent is told
  to pipe a build into is code, not prose. Demo `tools/` scripts stay outside
  both gates (ruff here, pyright below): they are the demo's own artifact,
  tested by the demo.
  There is deliberately **no auto-formatter**: match the surrounding style by
  hand (`from __future__ import annotations`, type hints on public
  signatures, and the aligned struct/profile tables in
  `protocol.py`/`machines.py` are intentional). Comments state contracts,
  hardware quirks, and non-obvious *why* — see `monitor.py`/`daemon.py` for
  the house tone; no narration.
- **A comment is read as a contract, so its claims carry the same evidence
  burden as a finding** — the discipline the dogfood rule below states for
  `docs/todo.md` items ("quote the file before asserting a gap in it") applies
  to every comment, docstring and doc paragraph the tree ships. The shape that
  goes wrong is the absolute about what some *other* command, writer or tool
  does: "nothing here writes X on its own", "every build does Y". Grep it
  before you write it; where the honest statement is narrower ("no writer in
  this tree", plus whichever command is the exception), write the narrower
  one. The next reader reasons from a guard's stated premise as if it had been
  checked, including about what the guard refuses — `git log --grep="unverified
  absolutes"` is a branch's worth of comments walked back for exactly this.
- Type-check with bare `pyright` — no flags, and **the tree must stay
  clean**: the check is local-only, by ruling (the CI gate was retired
  because its venv re-resolved dependencies on every run and could go red
  with no code change), so a new error is yours to fix before you commit,
  not a note for later. 1.1.411 is the known-good version; bump it
  deliberately, with the tree clean before and after, and update this
  number when you do.
  `[tool.pyright]` in
  `pyproject.toml` sets `venvPath`/`venv` so imports resolve against `.venv`
  — that config is what stands between you and ~70 phantom missing-import
  errors, so keep the venv installed and let pyright find the config (it
  looks upward from wherever you run it; the repo root always works).
  A **worktree** has no `.venv`, and running from the main checkout only
  type-checks main's files — worktree-only changes are invisible to it. To
  gate a branch that lives in a worktree: symlink the main checkout's
  `.venv` into the worktree root, run bare `pyright` there, remove the
  symlink. And not every worktree banner is a phantom: first-party
  annotations resolve without the venv, so an error against one of our own
  signatures is real wherever it appears.
  pyright is a developer-local tool, deliberately **not** in `[dev]` — the
  PyPI wrapper downloads a Node toolchain, heavier than anything else this
  project installs. Get it with `brew install pyright` or `npm i -g pyright`.
  Fix a finding at its cause; where one is genuinely a checker limitation,
  the house pattern is a per-site `# pyright: ignore[<rule>]` with a comment
  saying why (`cli.py`'s `Session.launch` call is the model), never a bare
  `# type: ignore` and never a rule switched off in `pyproject.toml`.
- Never vendor Commodore ROM bytes or any copyrighted Commodore code into
  the repo — ROM tooling reads bytes from the user's running emulator and
  ships only original label annotations.

## Testing expectations

- TDD: write the failing test first; every behavior change lands with tests
  in the same commit. Keep `pytest -m "not vice"` green at all times, and
  keep coverage ≥ 90% (`fail_under` is enforced by the coverage config).
- **Match the run to the change — the narrowest run that can actually
  fail.** Docs are tested, so run *something*, just not the emulators:
  an `.md`-only change → just the focused `tests/test_docs_*.py` file(s)
  covering those docs; a single test file changed → run that file; one
  `src/` module changed → its tests plus direct callers' tests, with the
  `-m "not vice"` sweep (~40s) only for widely-called code. Save the full
  suite (~3.5-4 min of live x64sc) for cross-cutting `src/` behavior
  changes and one pre-merge verification — and reuse a green run instead
  of repeating it when nothing has changed since (or only docs and
  test-local files have).
- Use the house harnesses instead of inventing new ones:
  - monitor-level: `tests/fake_vice.py` (`FakeVice` + `resp_frame`);
  - CLI: `CliRunner` + `patch("c64lib.cli.Session")` + a Mock monitor
    (the `_fake()` helper pattern in `tests/test_cli_break.py`);
  - MCP: in-memory client via `tests/test_mcp_scaffold.call_tool`;
  - daemon: `PetDaemon` + a real socketpair (`tests/test_daemon.py`);
  - live: the shared `session` fixture (`tests/conftest.py`), and
    `shared_launch` for specs run through `run_test`, which would otherwise
    boot an emulator per spec.
- Reserve `@pytest.mark.vice` for what genuinely needs a live emulator;
  unit-test everything else against the fakes.
- **Docs are tested.** The `tests/test_docs_*.py` suite verifies docs
  against reality: every command needs a `` ### `c64 …` `` entry in
  `docs/cli.md` (the check is bidirectional), README examples must parse,
  cookbook recipes must assemble AND run correctly on a live C64
  (`LIVE_RECIPES` in `tests/test_docs_cookbook.py`), and factual claims in
  the skills references are asserted live where possible. When you change
  the CLI surface or docs, update both sides in the same change — and give
  new doc claims the same honesty treatment.

## Plans

- A plan an agent executes itself specifies *interfaces*, not code bodies:
  exact label/function names, byte-level variable tables, memory maps and
  allocations, and one verification command per task. Do not transcribe
  program bodies into a plan out of `superpowers:writing-plans` obedience —
  its no-placeholders rule is the skill's bar, not this repo's (maintainer
  ruling, 2026-08-01). A short pinned snippet is fine only when the snippet
  *is* the spec (an exact error message, a test case, a linker line).

## Dogfood post-mortems

A dogfood run ends by writing its friction into `docs/todo.md` in that file's
format — anchor, what's wrong now, fix direction, how to verify. The file is
deleted whenever its last item lands (maintainer ruling, 2026-08-09), so
recreate it, preamble and all, if it is absent — git history has the previous
incarnation. Those items
are claims about this repo, so they get the evidence discipline this repo
applies to everything else: **quote the file before asserting a gap in it.**
Grep the reference, paste the sentence that is or is not there, and let the
quote carry the finding.

The trap is inferring upstream from downstream. A demo's prompt, a generated
artifact, or your own earlier code being wrong about a hardware fact does not
imply the skills references are silent on it — they usually are not, and the
finding you actually have is about the thing that was wrong. (La Galaxia,
2026-08-08: the prompt put the custom charset under the character-ROM image
and argued for it from the right premise. `references/hardware.md` and
`references/memory-maps.md` both state the fact plainly. The post-mortem's
first draft blamed them anyway; the real gap was one clause narrower — the
image's 4 KB *size*, which is what makes two of the eight charset bases
unusable rather than one.)

## Git

- Commit messages follow the existing `type(scope): summary` style
  (`feat(cli): …`, `docs(cookbook): …`, `test(daemon): …`).
- Commit locally; do not push unless the maintainer asks.
- `docs/superpowers/` (design specs/plans in the maintainer's checkout) is
  gitignored and local-only — never commit or push anything under it.

## Releases

**`pyproject.toml`'s `[project].version` is the single source of truth.**
Everything else derives from or is locked to it:

- `c64lib.__version__` reads it from installed package metadata
  (`importlib.metadata`) — never hardcode a version there.
- Two tests fail on drift: `test_version_matches_installed_metadata`
  (`__version__` == pyproject) and `test_changelog_has_current_version`
  (a `## [<version>]` heading exists in `CHANGELOG.md`).
- `.github/workflows/release.yml` runs on every push to `main`: it reads
  the pyproject version and, **only if tag `v<version>` does not yet
  exist**, builds the sdist/wheel and creates the tag + GitHub Release at
  that commit. So a version bump *is* a release; any other push is a no-op.

To cut a release, in one commit:

1. Bump `version` in `pyproject.toml`.
2. Add a `## [<version>] — <date>` section to `CHANGELOG.md`.
3. `pip install -e ".[dev]"` (refresh the editable install so
   `__version__` and its test see the new version), then `pytest -m "not
   vice"` — the two lock tests above must pass.
4. Merge to `main`. CI tags `v<version>` and publishes the release.

Do not create tags or GitHub Releases by hand — the workflow owns them,
so a manual tag would desync the source-of-truth model.
