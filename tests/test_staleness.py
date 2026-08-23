"""FT1: load provenance on the session + staleness reporting.

Born from the Ms. Muncher dogfood: a broken build left the emulator
running an old binary and nothing said so. The session now records what
was loaded (and from which source files), `ops.staleness` reports source
files changed since the load, and `c64 run`'s failure message names the
program the emulator is still running.
"""
import json
import time

import pytest
from click.testing import CliRunner

import c64lib.cli as cli

# Imported here, not inside the test: conftest's autouse fixture swaps
# subprocess.Popen for a plain function, and `mcp`'s own import chain
# annotates with `subprocess.Popen[bytes]` at class-body time.
from c64lib import mcp_server
from c64lib.build import BuildError
from c64lib.ops import staleness
from c64lib.session import Session


def _mk_session(tmp_path, monkeypatch, **kw):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "sessions").mkdir(parents=True, exist_ok=True)
    return Session(name="t", pid=1, port=1, model="c64", **kw)


def test_record_loaded_persists_and_reloads(tmp_path, monkeypatch):
    s = _mk_session(tmp_path, monkeypatch)
    prg = tmp_path / "a.prg"
    dep = tmp_path / "a.s"
    prg.write_bytes(b"\x01\x08")
    dep.write_text(";", encoding="utf-8")
    s.record_loaded(prg, [dep])
    rec = json.loads((tmp_path / "home" / "sessions" / "t.json").read_text(encoding="utf-8"))
    assert rec["loaded_prg"].endswith("a.prg")
    assert rec["loaded_deps"][0].endswith("a.s")
    assert rec["loaded_at"] > 0


def test_staleness_lists_deps_changed_since_load(tmp_path, monkeypatch):
    s = _mk_session(tmp_path, monkeypatch)
    dep = tmp_path / "inc.s"
    dep.write_text(";", encoding="utf-8")
    prg = tmp_path / "a.prg"
    prg.write_bytes(b"\x01\x08")
    s.record_loaded(prg, [dep])
    assert staleness(s) == []
    s.loaded_at = time.time() - 60          # pretend the load was a minute ago
    dep.write_text("; edited\n", encoding="utf-8")
    stale = staleness(s)
    assert len(stale) == 1 and str(stale[0]).endswith("inc.s")


def test_status_reports_program_and_stale_sources(tmp_path, monkeypatch):
    s = _mk_session(tmp_path, monkeypatch)
    dep = tmp_path / "inc.s"
    dep.write_text(";", encoding="utf-8")
    prg = tmp_path / "a.prg"
    prg.write_bytes(b"\x01\x08")
    s.record_loaded(prg, [dep])
    s.loaded_at = time.time() - 60
    dep.write_text("; edited\n", encoding="utf-8")
    monkeypatch.setattr(cli, "attach", lambda ctx: s)
    monkeypatch.setattr(cli, "machine_state", lambda s_: "running")
    r = CliRunner().invoke(cli.main, ["--json", "status"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["program"].endswith("a.prg")
    assert out["stale"] and out["stale"][0].endswith("inc.s")
    r2 = CliRunner().invoke(cli.main, ["status"])
    assert "STALE" in r2.output and "inc.s" in r2.output


def _a_build_that_fails(tmp_path, monkeypatch):
    """A session running `old.prg`, and a `prog.s` whose ca65 always fails."""
    import stat
    s = _mk_session(tmp_path, monkeypatch)
    prg = tmp_path / "old.prg"
    prg.write_bytes(b"\x01\x08")
    s.record_loaded(prg, [])
    bad = tmp_path / "ca65"
    bad.write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.stderr.write('boom')\nsys.exit(1)\n",
        encoding="utf-8",
    )
    bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("C64_TOOLS_CA65", str(bad))
    src = tmp_path / "prog.s"
    src.write_text(";", encoding="utf-8")
    return s, src


def test_run_build_failure_names_the_running_program(tmp_path, monkeypatch):
    s, src = _a_build_that_fails(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "attach", lambda ctx: s)
    r = CliRunner().invoke(cli.main, ["run", str(src)])
    assert r.exit_code != 0
    assert "PREVIOUS program" in r.output and "old.prg" in r.output


def test_mcp_run_build_failure_names_the_running_program_too(tmp_path,
                                                             monkeypatch):
    """The Ms. Muncher trap is an MCP client's too, and more so — nothing on
    that side is watching the window to notice the old program still on it.
    The note is part of what `ops.build_for_run` raises, so it cannot be a
    CLI-only courtesy again."""
    s, src = _a_build_that_fails(tmp_path, monkeypatch)
    monkeypatch.setattr(mcp_server, "_attach", lambda name=None: s)
    with pytest.raises(BuildError) as e:
        mcp_server.c64_run(str(src))
    assert "PREVIOUS program" in str(e.value) and "old.prg" in str(e.value)
