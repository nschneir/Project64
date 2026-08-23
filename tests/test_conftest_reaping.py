"""The leftover-emulator sweep kills processes, so prove it only kills ours.

A recorded pid is fair game only while it is still running an emulator or a
session daemon; pids get reused, and a developer's own x64sc was never
recorded in the first place.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from c64lib import session as session_mod
from tests import conftest as ct


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(ct, "_RUNS", runs)
    return runs


def _dead_pid() -> int:
    """A pid that is certainly not in use: run something and let it exit."""
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    return proc.pid


def _sleeper(tmp_path, name):
    """A live process whose command line contains `name`."""
    script = tmp_path / name
    script.write_text("#!/bin/sh\nsleep 30\n")
    script.chmod(0o755)
    return subprocess.Popen([str(script)])


def test_emulator_spawns_are_recorded_at_popen(tmp_path, runs_dir):
    """Recorded when the process appears, not when the launch returns: a run
    killed while VICE is still coming up must still be reapable."""
    emu = _sleeper(tmp_path, "x64sc")
    other = _sleeper(tmp_path, "something-else")
    try:
        recorded = ct._run_file().read_text().split()
        assert str(emu.pid) in recorded
        assert str(other.pid) not in recorded
    finally:
        emu.kill()
        other.kill()


def test_is_ours_rejects_unrelated_processes():
    assert ct._is_ours(os.getpid()) is False        # pytest itself


def test_is_ours_accepts_an_emulator(tmp_path):
    proc = _sleeper(tmp_path, "x64sc")
    try:
        assert ct._is_ours(proc.pid) is True
    finally:
        proc.kill()


class _NoProcfs:
    """Stand-in for ``pathlib.Path`` inside the lookup: nothing exists.

    A Linux host answers from ``/proc/<pid>/cmdline`` and never reaches the
    ``ps`` fallback, so the slim-container case (no procfs *and* no ``ps``)
    can only be reproduced by taking procfs away too.
    """

    def __init__(self, *_args):
        pass

    def exists(self) -> bool:
        return False


def test_is_ours_is_false_when_no_lookup_is_available(tmp_path, monkeypatch):
    """A slim image with no ``ps`` on PATH must not error the whole suite —
    and must not let an unidentifiable pid through as killable either."""
    proc = _sleeper(tmp_path, "x64sc")
    try:
        assert ct._is_ours(proc.pid) is True         # identifiable normally

        def no_ps(*_args, **_kwargs):
            raise FileNotFoundError(2, "No such file or directory: 'ps'")

        monkeypatch.setattr(session_mod, "Path", _NoProcfs)
        monkeypatch.setattr(subprocess, "run", no_ps)
        assert ct._is_ours(proc.pid) is False
    finally:
        proc.kill()


def test_ledger_directory_is_per_user():
    """Shared Linux hosts: /tmp is world-writable and the first run to create
    a fixed-name directory owns it, locking every other user out of theirs."""
    assert ct._RUNS.parent == Path(tempfile.gettempdir())
    assert ct._RUNS.name == f"c64-tools-pytest-runs-{os.getuid()}"


def test_ledger_directory_is_private(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "_RUNS", tmp_path / "ledger")
    ct._record_pid(999999)
    assert (ct._RUNS.stat().st_mode & 0o777) == 0o700
    assert ct._run_file().read_text().split() == ["999999"]


def test_reap_survives_a_kill_it_is_not_allowed_to_make(tmp_path, runs_dir,
                                                        monkeypatch):
    """Another user now holds the recorded pid: skip it, keep going, and still
    consume the record instead of erroring the session fixture."""
    proc = _sleeper(tmp_path, "x64sc")
    f = runs_dir / "999997.pids"
    f.write_text(f"{proc.pid}\n")

    def denied(*_args, **_kwargs):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "kill", denied)
    try:
        assert ct._reap(f) == 0
        assert not f.exists()                       # record consumed
    finally:
        monkeypatch.undo()
        proc.kill()


def test_sweep_skips_a_ledger_entry_it_cannot_read(tmp_path, runs_dir):
    """One unreadable leftover must not cost the sweep the entries after it."""
    # Real dead pids, not made-up numbers: Linux's pid_max runs into the
    # millions, so an invented stem can name a live process and be skipped as
    # "a run still going". Lower pid first, so the bad entry sorts first.
    dead = sorted(_dead_pid() for _ in range(2))
    bad = runs_dir / f"{dead[0]}.pids"
    bad.mkdir()                                     # read_text raises OSError
    emu = _sleeper(tmp_path, "x64sc")
    good = runs_dir / f"{dead[1]}.pids"
    good.write_text(f"{emu.pid}\n")
    try:
        ct._reap_dead_runs()
        assert emu.wait(timeout=5) is not None
        assert not good.exists()
    finally:
        emu.kill()


def test_reap_kills_recorded_emulators(tmp_path, runs_dir):
    proc = _sleeper(tmp_path, "x64sc")
    f = runs_dir / "999999.pids"
    f.write_text(f"{proc.pid} 0\n")
    try:
        assert ct._reap(f) == 1
        assert proc.wait(timeout=5) is not None
        assert not f.exists()                       # record consumed
    finally:
        proc.kill()


def test_reap_spares_a_reused_pid(tmp_path, runs_dir):
    """The recorded pid now belongs to something else entirely."""
    proc = _sleeper(tmp_path, "not-an-emulator")
    f = runs_dir / "999998.pids"
    f.write_text(f"{proc.pid} 0\n")
    try:
        assert ct._reap(f) == 0
        time.sleep(0.2)
        assert proc.poll() is None                  # still running
    finally:
        proc.kill()


def test_sweep_skips_runs_that_are_still_alive(tmp_path, runs_dir):
    """A suite running concurrently must not have its emulator reaped."""
    runner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    emu = _sleeper(tmp_path, "x64sc")
    f = runs_dir / f"{runner.pid}.pids"
    f.write_text(f"{emu.pid} 0\n")
    try:
        ct._reap_dead_runs()
        assert f.exists()                           # left for that run to clean
        assert emu.poll() is None
    finally:
        emu.kill()
        runner.kill()


def test_sweep_reaps_a_dead_runs_leftovers(tmp_path, runs_dir):
    dead = subprocess.Popen([sys.executable, "-c", ""])
    dead.wait()
    emu = _sleeper(tmp_path, "x64sc")
    f = runs_dir / f"{dead.pid}.pids"
    f.write_text(f"{emu.pid} 0\n")
    try:
        ct._reap_dead_runs()
        assert emu.wait(timeout=5) is not None
        assert not f.exists()
    finally:
        emu.kill()
