"""The leftover-emulator sweep kills processes, so prove it only kills ours.

A recorded pid is fair game only while it is still running an emulator or a
session daemon; pids get reused, and a developer's own x64sc was never
recorded in the first place.
"""

import os
import subprocess
import sys
import time

import pytest

from tests import conftest as ct


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(ct, "_RUNS", runs)
    return runs


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
