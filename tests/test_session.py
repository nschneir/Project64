import json
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest

from c64lib.session import (
    Session,
    SessionError,
    _kill_proc,
    _pid_alive,
    sessions_dir,
)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    return tmp_path


def _write_record(name, pid, port=6502, model="c64"):
    d = sessions_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(
        json.dumps({"name": name, "pid": pid, "port": port, "model": model, "created": 0})
    )


def _live_pid():
    # a real process we control, standing in for x64sc
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    return proc


def test_attach_by_name(home):
    proc = _live_pid()
    try:
        _write_record("alpha", proc.pid)
        s = Session.attach("alpha")
        assert (s.name, s.pid, s.model) == ("alpha", proc.pid, "c64")
        assert s.profile.screen_cols == 40
    finally:
        proc.kill()


def test_attach_prunes_dead_and_errors(home):
    _write_record("ghost", 999999999)  # no such pid
    with pytest.raises(SessionError, match="c64 session start"):
        Session.attach()
    assert not list(sessions_dir().glob("*.json"))  # dead record pruned


def test_attach_default_requires_exactly_one(home):
    p1, p2 = _live_pid(), _live_pid()
    try:
        _write_record("a", p1.pid)
        _write_record("b", p2.pid, port=6503)
        with pytest.raises(SessionError, match="--session"):
            Session.attach()
        assert Session.attach("b").port == 6503
    finally:
        p1.kill()
        p2.kill()


def test_list_all(home):
    proc = _live_pid()
    try:
        _write_record("only", proc.pid)
        assert [s.name for s in Session.list_all()] == ["only"]
    finally:
        proc.kill()


def test_launch_missing_binary_message(home, monkeypatch):
    monkeypatch.delenv("C64_TOOLS_X64SC", raising=False)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(SessionError, match="[Ii]nstall"):
        Session.launch(model="c64")


def test_launch_unknown_model(home):
    with pytest.raises(KeyError):
        Session.launch(model="amiga500")


def test_labels_path_persists(home):
    proc = _live_pid()
    try:
        _write_record("alpha", proc.pid)
        s = Session.attach("alpha")
        assert s.labels is None
        s.set_labels_path("/tmp/prog.lbl")
        again = Session.attach("alpha")
        # set_labels_path resolves; macOS resolves /tmp -> /private/tmp
        assert again.labels is not None      # `s.labels is None` was the before-state
        assert again.labels.endswith("/tmp/prog.lbl")
    finally:
        proc.kill()


def test_launch_disk8_args(home, tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_NO_DAEMON", "1")  # this test is about x64sc args
    captured = {}

    class FakeProc:
        pid = 999_999_990  # never a live pid, so record pruning stays deterministic

        def terminate(self):
            pass

    def fake_popen(args, **kw):
        captured["args"] = args
        return FakeProc()

    monkeypatch.setattr("c64lib.session.subprocess.Popen", fake_popen)
    monkeypatch.setattr("c64lib.session.shutil.which", lambda n: "/usr/bin/x64sc")

    class FakeMon:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): ...
        def connect(self, deadline=0): ...
        def ping(self): ...
        def resume(self): ...

    monkeypatch.setattr("c64lib.session.MonitorClient", FakeMon)

    d81 = tmp_path / "big.d81"
    d81.write_bytes(b"x")
    Session.launch(model="c64", name="dsk", disk8=str(d81))
    args = captured["args"]
    assert "-8" in args and str(d81.resolve()) in args
    i = args.index("-drive8type")
    assert args[i + 1] == "1581"

    d64 = tmp_path / "small.d64"
    d64.write_bytes(b"x")
    Session.launch(model="c64", name="dsk2", disk8=str(d64))
    assert "-drive8type" not in captured["args"]      # 1541 is the default
    assert "-8" in captured["args"]


def test_launch_retries_transient_monitor_failure(home, monkeypatch):
    """A first slow/failed monitor connect should be retried, the failed proc
    killed (no orphan), and a second attempt succeed."""
    monkeypatch.setenv("C64_TOOLS_NO_DAEMON", "1")  # x64sc retry logic, not the daemon
    procs = []

    class FakeProc:
        _n = 0

        def __init__(self):
            FakeProc._n += 1
            self.pid = 900000 + FakeProc._n
            self.killed = False
            procs.append(self)

        def terminate(self):
            self.killed = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed = True

    monkeypatch.setattr("c64lib.session.subprocess.Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr("c64lib.session.shutil.which", lambda n: "/usr/bin/x64sc")

    calls = {"n": 0}

    class FakeMon:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): ...
        def connect(self, deadline=0):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("monitor slow")
        def ping(self): ...
        def resume(self): ...

    monkeypatch.setattr("c64lib.session.MonitorClient", FakeMon)

    s = Session.launch(model="c64", name="retry")
    assert s.pid == procs[1].pid          # the second proc won
    assert procs[0].killed is True        # the first was cleaned up
    assert calls["n"] == 2                # exactly one retry


def test_launch_exhausts_attempts_and_kills_all(home, monkeypatch):
    procs = []

    class FakeProc:
        def __init__(self):
            self.pid = 800000 + len(procs)
            self.killed = False
            procs.append(self)

        def terminate(self):
            self.killed = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed = True

    monkeypatch.setenv("C64_TOOLS_LAUNCH_ATTEMPTS", "2")
    monkeypatch.setattr("c64lib.session.subprocess.Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr("c64lib.session.shutil.which", lambda n: "/usr/bin/x64sc")

    class FakeMon:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): ...
        def connect(self, deadline=0):
            raise ConnectionError("never answers")
        def ping(self): ...
        def resume(self): ...

    monkeypatch.setattr("c64lib.session.MonitorClient", FakeMon)

    with pytest.raises(SessionError, match="never answered after 2"):
        Session.launch(model="c64", name="doomed")
    assert len(procs) == 2 and all(p.killed for p in procs)   # both cleaned up


def test_pid_alive_permission_error_means_alive(monkeypatch):
    def kill(pid, sig):
        raise PermissionError
    monkeypatch.setattr("c64lib.session.os.kill", kill)
    assert _pid_alive(12345) is True


def test_kill_proc_escalates_to_sigkill():
    proc = Mock()
    proc.wait.side_effect = [subprocess.TimeoutExpired("x", 3), None]
    _kill_proc(proc)
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


def test_kill_proc_survives_stubborn_process():
    proc = Mock()
    proc.wait.side_effect = subprocess.TimeoutExpired("x", 3)
    _kill_proc(proc)                      # both waits expire; must not raise
    proc.kill.assert_called_once()


def test_launch_rejects_duplicate_name(home, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_X64SC", "/usr/bin/x64sc")  # skip the which() check
    existing = Mock()
    existing.name = "c64"
    with patch.object(Session, "_load_all", return_value=[existing]):
        with pytest.raises(SessionError, match="already running"):
            Session.launch(model="c64")


def test_attach_unknown_name_is_actionable(home):
    with pytest.raises(SessionError, match="c64 session start"):
        Session.attach("nosuch")


def test_stop_cleans_up_dead_session(home):
    # a pid that is already dead (reaped) — stop() takes the not-alive path
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    dead = proc.pid
    sock = home / "sessions" / "z.sock"
    sock.parent.mkdir(parents=True, exist_ok=True)
    s = Session(name="z", pid=dead, port=6502, model="c64",
                daemon_pid=dead, socket=str(sock))
    s._record_path().write_text("{}")
    sock.write_text("")                   # a stale socket file to clean up
    s.stop()                              # must not raise
    assert not s._record_path().exists()
    assert not sock.exists()


def test_launch_passes_cartcrt(home, monkeypatch, tmp_path):
    """A cartridge is attached at boot, like a disk — never autostart-loaded.

    `home` is autouse, but named here because launch reads the registry (the
    duplicate-name check) — this must never see the developer's sessions.
    """
    from c64lib import session as session_mod

    crt = tmp_path / "game.crt"
    crt.write_bytes(b"C64 CARTRIDGE   " + bytes(48))
    seen = {}

    class FakePopen:
        def __init__(self, args, **kw):
            seen["args"] = args
            self.pid = 4242

        def poll(self):
            return None

    monkeypatch.setattr(session_mod.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(session_mod, "_spawn_daemon", lambda *a, **k: 99)
    monkeypatch.setattr(session_mod.Session, "_save", lambda self: None)

    class FakeMon:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def connect(self, deadline=0): pass
        def ping(self): pass
        def resume(self): pass

    monkeypatch.setattr(session_mod, "MonitorClient", lambda **kw: FakeMon())
    session_mod.Session.launch(name="cartsess", cart=str(crt))
    args = seen["args"]
    assert "-cartcrt" in args
    assert args[args.index("-cartcrt") + 1] == str(crt.resolve())


# --- -minimized capability probe and headless argument wiring -------------
#
# GTK3 builds of x64sc never read SDL_VIDEODRIVER/SDL_AUDIODRIVER (those only
# affect SDL builds), so headless=True was inert on this machine: every
# "headless" launch opened a focused window and stole host keystrokes into
# the emulated keyboard buffer. -minimized fixes that on GTK builds, but VICE
# errors out on unrecognized options, so it must only be passed when the
# binary's own --help says it supports it.


@pytest.fixture(autouse=True)
def _clear_minimized_cache():
    """_supports_minimized is process-cached per binary path; without this,
    an earlier test's fake "/usr/bin/x64sc" result would leak into a later
    test that stubs the same path with a different --help output."""
    from c64lib.session import _supports_minimized, _supports_sound_dump
    for probe in (_supports_minimized, _supports_sound_dump):
        probe.cache_clear()
    yield
    for probe in (_supports_minimized, _supports_sound_dump):
        probe.cache_clear()


def test_supports_minimized_true_when_help_lists_it(monkeypatch):
    from c64lib import session as session_mod

    monkeypatch.setattr(
        session_mod.subprocess, "run",
        lambda *a, **k: Mock(stdout="...\n-minimized\n\tStart VICE minimized\n...", returncode=0),
    )
    assert session_mod._supports_minimized("/usr/bin/x64sc") is True


def test_supports_minimized_false_when_help_omits_it(monkeypatch):
    from c64lib import session as session_mod

    help_text = "...\n-console\n\tConsole mode (for music playback)\n..."
    monkeypatch.setattr(
        session_mod.subprocess, "run",
        lambda *a, **k: Mock(stdout=help_text, returncode=0),
    )
    assert session_mod._supports_minimized("/some/other/vice/x64sc") is False


def test_supports_minimized_false_when_probe_fails(monkeypatch):
    """A binary that can't even run --help (missing, wrong permissions,
    times out) must degrade to "no -minimized" rather than raise — a failed
    probe must never turn into a failed launch."""
    from c64lib import session as session_mod

    def boom(*a, **k):
        raise OSError("no such file")

    monkeypatch.setattr(session_mod.subprocess, "run", boom)
    assert session_mod._supports_minimized("/broken/x64sc") is False


def test_supports_minimized_false_when_help_is_not_strictly_decodable(monkeypatch):
    """A --help whose bytes are not valid under the process's locale encoding
    (e.g. an ASCII locale against a VICE build that emits any non-ASCII byte)
    must not raise UnicodeDecodeError out of this probe — the docstring's own
    invariant is that a probe failure never turns into a failed launch, and
    UnicodeDecodeError is not among the caught exceptions. The fix is passing
    errors="replace" to subprocess.run; this fake mirrors what subprocess.run's
    own text-mode decoding does (strict by default, permissive with
    errors="replace") so removing that kwarg fails this test.
    """
    from c64lib import session as session_mod

    def fake_run(*args, **kwargs):
        if kwargs.get("errors") != "replace":
            raise UnicodeDecodeError("ascii", b"\xff", 0, 1, "ordinal not in range(128)")
        return Mock(stdout="-console\n\tConsole mode\n", returncode=0)

    monkeypatch.setattr(session_mod.subprocess, "run", fake_run)
    assert session_mod._supports_minimized("/broken/locale/x64sc") is False


def _stub_launch_deps(monkeypatch, session_mod, seen, help_text):
    class FakePopen:
        def __init__(self, args, env=None, **kw):
            seen["args"] = args
            seen["env"] = env
            self.pid = 4242

        def poll(self):
            return None

    class FakeMon:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def connect(self, deadline=0): pass
        def ping(self): pass
        def resume(self): pass

    monkeypatch.setattr(session_mod.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(
        session_mod.subprocess, "run",
        lambda *a, **k: Mock(stdout=help_text, returncode=0),
    )
    monkeypatch.setattr(session_mod, "_spawn_daemon", lambda *a, **k: 99)
    monkeypatch.setattr(session_mod.Session, "_save", lambda self: None)
    monkeypatch.setattr(session_mod, "MonitorClient", lambda **kw: FakeMon())
    monkeypatch.setenv("C64_TOOLS_X64SC", "/usr/bin/x64sc")


def test_launch_headless_passes_minimized_when_supported(home, monkeypatch):
    from c64lib import session as session_mod

    seen = {}
    _stub_launch_deps(monkeypatch, session_mod, seen, "-minimized\n\tStart VICE minimized\n")
    session_mod.Session.launch(name="headless-sess", headless=True)
    assert "-minimized" in seen["args"]
    assert seen["env"]["SDL_VIDEODRIVER"] == "dummy"
    assert seen["env"]["SDL_AUDIODRIVER"] == "dummy"


def test_launch_headless_omits_minimized_when_unsupported(home, monkeypatch):
    """A VICE build whose --help doesn't mention -minimized must still get a
    working headless launch (SDL vars only) rather than a hard failure from
    an unrecognized option."""
    from c64lib import session as session_mod

    seen = {}
    help_text = "-console\n\tConsole mode (for music playback)\n"
    _stub_launch_deps(monkeypatch, session_mod, seen, help_text)
    session_mod.Session.launch(name="headless-sess-old-vice", headless=True)
    assert "-minimized" not in seen["args"]
    assert seen["env"]["SDL_VIDEODRIVER"] == "dummy"


def test_launch_non_headless_omits_minimized(home, monkeypatch):
    """headless=False must be unchanged: no -minimized, no SDL env vars."""
    from c64lib import session as session_mod

    seen = {}
    _stub_launch_deps(monkeypatch, session_mod, seen, "-minimized\n\tStart VICE minimized\n")
    session_mod.Session.launch(name="windowed-sess", headless=False)
    assert "-minimized" not in seen["args"]
    assert "SDL_VIDEODRIVER" not in seen["env"]
    assert "SDL_AUDIODRIVER" not in seen["env"]


# --- the headless sound sink and its capability probe ----------------------
#
# VICE's sound device is the emulation loop's flow control at real time, so a
# headless session that depends on a host consumer hangs where the host has
# none: coreaudio never drains, and `audio record --start` — the pin-and-arm
# — is the first real-time step a capture reaches. `dump` is a file-backed
# sink that always consumes. The device NAME is probed, not assumed: an
# unrecognized -sounddev value does not fail cleanly on a GTK3 build, it pops
# a modal error dialog that blocks the emulation loop even under -minimized,
# which looks exactly like the wedge this is fixing.

#: A --help whose sound section is this build's: the device list is what the
#: probe reads.
HELP_WITH_DUMP = ("-minimized\n\tStart VICE minimized\n"
                  "-sounddev <Name>\n\tSpecify sound driver. "
                  "(coreaudio/dummy/dump)\n")


def test_supports_sound_dump_true_when_help_lists_it(monkeypatch):
    from c64lib import session as session_mod

    monkeypatch.setattr(
        session_mod.subprocess, "run",
        lambda *a, **k: Mock(stdout=HELP_WITH_DUMP, returncode=0),
    )
    assert session_mod._supports_sound_dump("/usr/bin/x64sc") is True


def test_supports_sound_dump_false_when_the_device_list_omits_it(monkeypatch):
    """A build whose sound drivers do not include `dump` must not be handed
    it: the value would be rejected at runtime with a blocking dialog."""
    from c64lib import session as session_mod

    help_text = ("-sounddev <Name>\n\tSpecify sound driver. "
                 "(alsa/pulse/dummy)\n")
    monkeypatch.setattr(
        session_mod.subprocess, "run",
        lambda *a, **k: Mock(stdout=help_text, returncode=0),
    )
    assert session_mod._supports_sound_dump("/some/other/vice/x64sc") is False


def test_supports_sound_dump_reads_only_the_sounddev_line(monkeypatch):
    """`dump` appears elsewhere in VICE's --help (`-dump`-ish debug options,
    the recording drivers). Matching the bare word anywhere would hand the
    value to a build that has no such *playback* device."""
    from c64lib import session as session_mod

    help_text = ("-soundrecdev <Name>\n\tSpecify recording sound driver. "
                 "(fs/wav/dump)\n"
                 "-sounddev <Name>\n\tSpecify sound driver. (alsa/dummy)\n")
    monkeypatch.setattr(
        session_mod.subprocess, "run",
        lambda *a, **k: Mock(stdout=help_text, returncode=0),
    )
    assert session_mod._supports_sound_dump("/vice/no-dump/x64sc") is False


def test_supports_sound_dump_false_when_probe_fails(monkeypatch):
    """A binary that cannot run --help degrades to the host device rather
    than raising: same rule as the -minimized probe."""
    from c64lib import session as session_mod

    def boom(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(session_mod.subprocess, "run", boom)
    assert session_mod._supports_sound_dump("/broken/x64sc") is False


def test_launch_headless_sinks_sound_to_the_null_device(home, monkeypatch):
    """A headless session must not depend on a host sound consumer.

    `dump` is a file-backed sink that always consumes; pointed at the null
    device it writes nowhere. The `-soundarg` half is not decoration: unset,
    VICE's dump device writes its register dump to `vicesnd.sid` in the
    caller's working directory.
    """
    import os

    from c64lib import session as session_mod

    seen = {}
    _stub_launch_deps(monkeypatch, session_mod, seen, HELP_WITH_DUMP)
    session_mod.Session.launch(name="sink-sess", headless=True)
    args = seen["args"]
    assert "-sounddev" in args
    assert args[args.index("-sounddev") + 1] == "dump"
    assert args[args.index("-soundarg") + 1] == os.devnull


def test_launch_headless_does_not_use_the_dummy_sound_device(home, monkeypatch):
    """`dummy` is the obvious sink and the wrong one, measured 2026-08-10:
    it never consumes, so VICE overflows its own sound buffer ("Sound buffer
    overflow (cycle based)") and discards it — the WAV recorder receives no
    samples and a capture comes back as a bare 44-byte header. Pinned so the
    simplification is not re-attempted from the name alone."""
    from c64lib import session as session_mod

    seen = {}
    _stub_launch_deps(monkeypatch, session_mod, seen, HELP_WITH_DUMP)
    session_mod.Session.launch(name="not-dummy-sess", headless=True)
    args = seen["args"]
    assert args[args.index("-sounddev") + 1] != "dummy"


def test_launch_headless_omits_sounddev_when_the_build_lacks_dump(home,
                                                                 monkeypatch):
    """No sink is better than a rejected device name: an unrecognized
    -sounddev value pops a modal error dialog on a GTK3 build, and a modal
    dialog blocks the emulation loop even under -minimized — the very
    symptom the sink exists to remove. Such a build keeps host audio and
    the launch still works."""
    from c64lib import session as session_mod

    seen = {}
    _stub_launch_deps(
        monkeypatch, session_mod, seen,
        "-minimized\n\tStart VICE minimized\n"
        "-sounddev <Name>\n\tSpecify sound driver. (alsa/dummy)\n")
    session_mod.Session.launch(name="no-dump-sess", headless=True)
    assert "-sounddev" not in seen["args"]
    assert "-soundarg" not in seen["args"]
    assert "-minimized" in seen["args"]          # the rest of headless stands


def test_launch_non_headless_keeps_the_host_sound_device(home, monkeypatch):
    """A windowed session is one somebody is watching, so it keeps host
    audio: the sink is what "headless" already means (the SDL_AUDIODRIVER
    line beside it says the same thing, inertly, on GTK3 builds)."""
    from c64lib import session as session_mod

    seen = {}
    _stub_launch_deps(monkeypatch, session_mod, seen, HELP_WITH_DUMP)
    session_mod.Session.launch(name="windowed-audio-sess", headless=False)
    assert "-sounddev" not in seen["args"]
    assert "-soundarg" not in seen["args"]
