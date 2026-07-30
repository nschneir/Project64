"""Suite-wide fixtures.

Live tests are expensive: every ``Session.launch`` boots a fresh x64sc, and on
macOS each launch steals window focus. Most of them only need "a C64 sitting at
the READY prompt", so they share one long-lived warp+headless emulator and get
a clean machine between tests instead of a fresh process.

Tests that must own their emulator keep a local ``session`` fixture, which
shadows the one defined here: per-model parameterization, anything that
attaches a disk image (the binary monitor has no detach command, so an attached
image cannot be cleaned up), and anything asserting launch or daemon-spawn
behavior itself.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from c64lib.screen import read_screen_text
from c64lib.session import Session, _pid_alive
from tests.vice_helpers import timeout_scale

HAVE_X64SC = bool(shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC"))

#: Same resolution order as ``c64lib.disk._c1541``, so a test skips exactly
#: when the library it exercises would fail to find the binary.
HAVE_C1541 = bool(os.environ.get("C64_TOOLS_C1541") or shutil.which("c1541"))


def pytest_collection_modifyitems(config, items):
    """Skip ``needs_c1541`` tests when c1541 is absent.

    A real marker rather than a per-file ``skipif`` because these tests are
    validated locally and nowhere else (see AGENTS.md): a ``skipif`` is
    invisible to ``-m``, so the subset could not be *asked* for — only run by
    naming whole files. ``pytest -m "needs_c1541 and not vice"`` selects it.
    """
    if HAVE_C1541:
        return
    skip = pytest.mark.skip(reason="c1541 (VICE) not installed")
    for item in items:
        if "needs_c1541" in item.keywords:
            item.add_marker(skip)

#: Top-left screen cell. The boot screen clear overwrites it, which is how the
#: reset below proves the machine really rebooted instead of us reading the
#: previous test's stale screen.
SENTINEL = 0x0400


# --- emulators left behind by an earlier run ------------------------------

_RUNS = Path(tempfile.gettempdir()) / "c64-tools-pytest-runs"


def _run_file() -> Path:
    return _RUNS / f"{os.getpid()}.pids"


def _record_pid(pid: int) -> None:
    """Remember what this run started, so a suite killed before teardown can
    be cleaned up by the next one."""
    _RUNS.mkdir(parents=True, exist_ok=True)
    with open(_run_file(), "a") as fh:
        fh.write(f"{pid}\n")


def _is_ours(pid: int) -> bool:
    """pids get reused: only ever kill one still running an emulator or its
    daemon. Anything else that inherited the number is left alone."""
    out = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                         capture_output=True, text=True).stdout
    return "x64sc" in out or "c64lib.daemon" in out


def _reap(path: Path) -> int:
    killed = 0
    for pid in (int(word) for word in path.read_text().split()):
        if pid and _pid_alive(pid) and _is_ours(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                killed += 1
            except ProcessLookupError:
                pass
    path.unlink(missing_ok=True)
    return killed


def _reap_dead_runs() -> None:
    """Kill emulators orphaned by a pytest run that never reached teardown.
    Runs still alive (a suite running concurrently) are left untouched."""
    for f in sorted(_RUNS.glob("*.pids")):
        if f == _run_file() or _pid_alive(int(f.stem)):
            continue
        n = _reap(f)
        if n:
            print(f"\ntests: reaped {n} leftover emulator process(es) "
                  f"from pytest run {f.stem}")


# --- suite-wide environment -----------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _c64_home(tmp_path_factory):
    """One throwaway C64_TOOLS_HOME for the whole run, so the suite never sees
    — or prunes — the developer's real sessions. Tests that set their own home
    still override this per test."""
    home = tmp_path_factory.mktemp("c64home")
    old = os.environ.get("C64_TOOLS_HOME")
    os.environ["C64_TOOLS_HOME"] = str(home)
    yield home
    if old is None:
        os.environ.pop("C64_TOOLS_HOME", None)
    else:
        os.environ["C64_TOOLS_HOME"] = old


@pytest.fixture(scope="session", autouse=True)
def _track_launches(_c64_home):
    """Reap leftovers from earlier runs, then record every emulator and daemon
    this run spawns so the next run can reap ours if we are killed.

    The hook is ``Popen`` itself rather than ``Session.launch``: recording
    after a launch returns leaves a window — a few seconds, while VICE comes
    up — in which a killed run orphans an emulator nobody wrote down. It also
    catches every launch path, including the sessions ``run_test`` owns.
    """
    _reap_dead_runs()
    real_popen = subprocess.Popen

    def popen(args, *rest, **kwargs):
        proc = real_popen(args, *rest, **kwargs)
        cmd = " ".join(str(a) for a in args) if isinstance(args, (list, tuple)) \
            else str(args)
        if "x64sc" in cmd or "c64lib.daemon" in cmd:
            _record_pid(proc.pid)
        return proc

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(subprocess, "Popen", popen)
        yield
    _run_file().unlink(missing_ok=True)


# --- the shared machine ---------------------------------------------------

def _screen(s: Session) -> str:
    with s.monitor() as mon:
        try:
            return read_screen_text(mon, s.profile)
        finally:
            mon.release()


def _wait_ready(s: Session, timeout: float) -> None:
    deadline = time.monotonic() + timeout * timeout_scale()
    while "READY." not in (text := _screen(s)):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"no READY prompt; screen:\n{text}")
        time.sleep(0.3)


def _reset_clean(s: Session, timeout: float = 30.0) -> None:
    """Restore the shared machine to a fresh-boot READY prompt.

    Covers what a test can leave behind: checkpoints (breakpoints and
    watchpoints are monitor state and survive both autostart and reset, and a
    stray non-stopping one crawls the emulator), loaded programs, BASIC text,
    zero-page and VIC state such as a relocated screen, a machine parked at a
    breakpoint, and the session record's label/loaded-program bookkeeping.
    """
    with s.monitor() as mon:
        try:
            for cp in mon.checkpoint_list():
                mon.checkpoint_delete(cp.number)
            mon.memory_write(SENTINEL, b"\xff")
            mon.reset(hard=True)
        finally:
            mon.resume()                    # also un-parks a halted machine

    deadline = time.monotonic() + timeout * timeout_scale()
    while True:
        with s.monitor() as mon:
            try:
                rebooted = mon.memory_read(SENTINEL, 1) != b"\xff"
                text = read_screen_text(mon, s.profile) if rebooted else ""
            finally:
                mon.release()
        if rebooted and "READY." in text:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"machine never returned to READY after reset; screen:\n{text}")
        time.sleep(0.2)

    s.labels = None
    s.loaded_prg = None
    s.loaded_at = 0.0
    s.loaded_deps = None
    s._save()


class SharedC64:
    """Owns the one emulator the live tests share."""

    def __init__(self, name: str = "shared"):
        self.name = name
        self.session: Session | None = None

    def start(self) -> Session:
        self.session = Session.launch(model="c64", name=self.name,
                                      headless=True, warp=True)
        _wait_ready(self.session, timeout=60.0)
        return self.session

    def clean(self) -> Session:
        """A clean machine, whatever the last test did to it. One too wedged
        to come back (a JAM, a dead daemon) is replaced rather than left to
        fail every later test."""
        if self.session is None:
            return self.start()
        try:
            _reset_clean(self.session)
        except Exception as e:              # noqa: BLE001 - recovery path
            print(f"\ntests: shared C64 unusable ({e}); relaunching")
            self.stop()
            return self.start()
        return self.session

    def stop(self) -> None:
        if self.session is not None:
            try:
                self.session.stop()
            finally:
                self.session = None


@pytest.fixture(scope="session")
def _shared_c64(_c64_home, _track_launches):
    if not HAVE_X64SC:
        pytest.skip("x64sc not installed")
    shared = SharedC64()
    try:
        shared.start()
        yield shared
    finally:
        shared.stop()                       # runs on failure and on Ctrl-C


@pytest.fixture
def session(_shared_c64) -> Iterator[Session]:
    """A live C64 at the READY prompt, shared across the run.

    Cleaned before the test — the actual protection — and after it, so a leak
    is attributed to the test that caused it.
    """
    s = _shared_c64.clean()
    yield s
    _shared_c64.clean()


class _KeepAlive(Session):
    """The shared session, handed to code that owns its session's lifetime."""

    def stop(self) -> None:
        pass                                # it outlives this one test


def _needs_own_emulator(shared_model: str, model: str, kwargs: dict) -> bool:
    """Whether a spec's launch has to boot its own emulator.

    Named (and unit-tested in tests/test_testing_run.py) because getting it
    wrong is silent: a cart or disk spec handed the shared machine would run
    against a C64 with nothing attached and report the wrong reason for its
    pass or fail.
    """
    return model != shared_model or bool(kwargs.get("disk8") or kwargs.get("cart"))


@pytest.fixture
def shared_launch(session):
    """A ``launch`` for ``run_test``, which otherwise boots — and stops — an
    emulator per spec. Specs the shared machine cannot serve (another model,
    a disk image, a cartridge) still get one of their own.

    A cartridge is mapped at power-on, so it can never be attached to the
    already-running shared machine: reusing it would silently run the spec
    against a cartridge-less C64 and report the wrong reason for pass or fail.
    """
    def launch(model="c64", name=None, headless=False, warp=False, **kwargs):
        if _needs_own_emulator(session.model, model, kwargs):
            return Session.launch(model=model, name=name, headless=headless,
                                  warp=warp, **kwargs)
        return _KeepAlive(**vars(session))

    return launch
