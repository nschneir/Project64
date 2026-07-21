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
- `skills/c64-development/` + `skills/6502-assembly/` — PET-heritage/6502 domain
  knowledge: workflows, memory maps, zero page, ROM routines, cookbook.

## Commands

```sh
pip install -e ".[dev]"        # install with pytest + coverage

pytest                          # full suite (vice-marked tests need x64sc/VICE on PATH)
pytest -m "not vice"            # unit tests only — no emulator required
pytest tests/test_monitor.py    # one file
pytest tests/test_monitor.py::test_name   # one test

python -m coverage run -m pytest && python -m coverage combine && python -m coverage report
                                # coverage (fail_under=90); subprocesses (daemon, MCP stdio) are measured too

ruff check src tests            # lint (config in pyproject.toml); must be clean
```

Tests marked `@pytest.mark.vice` launch a real VICE emulator (`x64sc`);
everything else runs against `tests/fake_vice.py`, an in-process fake of the
VICE binary monitor. `c64 build` needs cc65 (`ca65`/`ld65`); `c64 basic`
needs `petcat`; `c64 disk` needs `c1541` — all external subprocesses.

Live-test caution: a setup failure inside a vice-marked test can skip
teardown and leak a warp-mode x64sc eating a CPU core. Check
`pgrep -fl x64sc` between live runs and kill leftovers. Give live tests
generous timeouts (minutes, not seconds).

## Architecture

Layered, bottom-up in `src/c64lib/`:

1. **`protocol.py`** — pure encode/decode of the VICE binary monitor protocol (API v2). No sockets.
2. **`monitor.py`** — `MonitorClient`, the socket client. Core contract: *processing any monitor command leaves the emulated machine STOPPED*; callers wanting it running must call `resume()`.
3. **The session daemon** (`daemon.py`, `rpc.py`, `daemon_client.py`) — VICE accepts only one monitor connection and resumes the CPU when it closes, so a per-session daemon process holds that single connection for the session's lifetime. Each `c64`/MCP command is a short-lived client on the session's unix socket; `DaemonMonitorClient` is a `MonitorClient` look-alike whose methods are JSON-lines RPC calls (`rpc.py` is the wire codec). This is what makes debug state (a breakpoint halt) persist across commands.
4. **`session.py`** — launch/attach/stop VICE, session records as JSON under `~/.c64-tools` (override with `C64_TOOLS_HOME`). `Session.monitor()` returns the daemon client.
5. **`ops.py`** — shared high-level operations (wait/until primitives, symbol resolution). Exists so the CLI and MCP server cannot drift; put new front-end-facing logic here, not in `cli.py` or `mcp_server.py`.
6. **Front ends** — `cli.py` (click; every command supports `--json`, the intended AI interface) and `mcp_server.py` (FastMCP; returns the same structured data as `--json`).

Supporting modules: `machines.py` (machine model profiles — RAM size, screen geometry, BASIC start), `build.py` (ca65/ld65), `basic.py` (petcat tokenize/detokenize), `disk.py` (c1541 d64 images), `screen.py`/`text.py` (screen RAM ↔ text), `symbols.py` (.lbl label files), `disasm.py`, `romdoc.py` (ROM identification/annotation — ships only original label annotations, never Commodore ROM bytes), `packaging.py` (`c64 package` → shareable .d64/.prg), `testing.py` (declarative YAML test runner).

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
- Lint with `ruff check src tests` and keep it clean (rules E/F/W/B/UP/I,
  line length 100 — configured in `pyproject.toml`). There is deliberately
  **no auto-formatter**: match the surrounding style by hand
  (`from __future__ import annotations`, type hints on public signatures,
  and the aligned struct/profile tables in `protocol.py`/`machines.py` are
  intentional). Comments state contracts, hardware quirks, and non-obvious
  *why* — see `monitor.py`/`daemon.py` for the house tone; no narration.
- Never vendor Commodore ROM bytes or any copyrighted Commodore code into
  the repo — ROM tooling reads bytes from the user's running emulator and
  ships only original label annotations.

## Testing expectations

- TDD: write the failing test first; every behavior change lands with tests
  in the same commit. Keep `pytest -m "not vice"` green at all times, and
  keep coverage ≥ 90% (`fail_under` is enforced by the coverage config).
- Use the house harnesses instead of inventing new ones:
  - monitor-level: `tests/fake_vice.py` (`FakeVice` + `resp_frame`);
  - CLI: `CliRunner` + `patch("c64lib.cli.Session")` + a Mock monitor
    (the `_fake()` helper pattern in `tests/test_cli_break.py`);
  - MCP: in-memory client via `tests/test_mcp_scaffold.call_tool`;
  - daemon: `PetDaemon` + a real socketpair (`tests/test_daemon.py`).
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

## Git

- Commit messages follow the existing `type(scope): summary` style
  (`feat(cli): …`, `docs(cookbook): …`, `test(daemon): …`).
- Commit locally; do not push unless the maintainer asks.
- `docs/superpowers/` (design specs/plans in the maintainer's checkout) is
  gitignored and local-only — never commit or push anything under it.
