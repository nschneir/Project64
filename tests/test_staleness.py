"""FT1: load provenance on the session + staleness reporting.

Born from the Ms. Muncher dogfood: a broken build left the emulator
running an old binary and nothing said so. The session now records what
was loaded (and from which source files), `ops.staleness` reports source
files changed since the load, and `c64 run`'s failure message names the
program the emulator is still running.
"""
import json
import time

from click.testing import CliRunner

import c64lib.cli as cli
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
    prg.write_bytes(b"\x01\x04")
    dep.write_text(";")
    s.record_loaded(prg, [dep])
    rec = json.loads((tmp_path / "home" / "sessions" / "t.json").read_text())
    assert rec["loaded_prg"].endswith("a.prg")
    assert rec["loaded_deps"][0].endswith("a.s")
    assert rec["loaded_at"] > 0


def test_staleness_lists_deps_changed_since_load(tmp_path, monkeypatch):
    s = _mk_session(tmp_path, monkeypatch)
    dep = tmp_path / "inc.s"
    dep.write_text(";")
    prg = tmp_path / "a.prg"
    prg.write_bytes(b"\x01\x04")
    s.record_loaded(prg, [dep])
    assert staleness(s) == []
    s.loaded_at = time.time() - 60          # pretend the load was a minute ago
    dep.write_text("; edited\n")
    stale = staleness(s)
    assert len(stale) == 1 and str(stale[0]).endswith("inc.s")


def test_status_reports_program_and_stale_sources(tmp_path, monkeypatch):
    s = _mk_session(tmp_path, monkeypatch)
    dep = tmp_path / "inc.s"
    dep.write_text(";")
    prg = tmp_path / "a.prg"
    prg.write_bytes(b"\x01\x04")
    s.record_loaded(prg, [dep])
    s.loaded_at = time.time() - 60
    dep.write_text("; edited\n")
    monkeypatch.setattr(cli, "attach", lambda ctx: s)
    monkeypatch.setattr(cli, "machine_state", lambda s_: "running")
    r = CliRunner().invoke(cli.main, ["--json", "status"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["program"].endswith("a.prg")
    assert out["stale"] and out["stale"][0].endswith("inc.s")
    r2 = CliRunner().invoke(cli.main, ["status"])
    assert "STALE" in r2.output and "inc.s" in r2.output


def test_run_build_failure_names_the_running_program(tmp_path, monkeypatch):
    import stat
    s = _mk_session(tmp_path, monkeypatch)
    prg = tmp_path / "old.prg"
    prg.write_bytes(b"\x01\x04")
    s.record_loaded(prg, [])
    monkeypatch.setattr(cli, "attach", lambda ctx: s)
    bad = tmp_path / "ca65"
    bad.write_text("#!/usr/bin/env python3\nimport sys\nsys.stderr.write('boom')\nsys.exit(1)\n")
    bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("C64_TOOLS_CA65", str(bad))
    src = tmp_path / "prog.s"
    src.write_text(";")
    r = CliRunner().invoke(cli.main, ["run", str(src)])
    assert r.exit_code != 0
    assert "PREVIOUS program" in r.output and "old.prg" in r.output
