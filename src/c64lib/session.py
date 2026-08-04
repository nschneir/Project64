"""Session lifecycle: launch/attach/stop VICE processes, tracked in JSON records.

VICE holds all machine and debug state; a session record only holds how to
find the process (pid) and its monitor (port).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .daemon_client import DaemonMonitorClient
from .disk import drive_type_for
from .machines import MachineProfile, get_profile
from .monitor import MonitorClient


def sessions_dir() -> Path:
    home = Path(os.environ.get("C64_TOOLS_HOME", "~/.c64-tools")).expanduser()
    d = home / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def audio_pin_path(name: str) -> Path:
    """Sidecar holding what a pinned audio capture owes the session: what
    `c64lib.audio` must put back when the recording stops.

    Written and read by `c64lib.audio`; named here so `Session.stop()` can
    clear it without importing that module. The extension is NOT `.json`:
    `_load_all()` parses every `*.json` in this directory as a session
    record.
    """
    return sessions_dir() / f"{name}.audio"


class SessionError(Exception):
    pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@functools.cache
def _supports_minimized(exe: str) -> bool:
    """Whether this VICE binary's own --help lists -minimized.

    GTK3 builds of x64sc never read SDL_VIDEODRIVER/SDL_AUDIODRIVER (those
    only affect SDL builds), so on those builds a "headless" launch still
    opens a focused window and steals host keystrokes into the emulated
    keyboard buffer via mon.keyboard_feed(). -minimized fixes that on
    builds that have it, but VICE errors out on unrecognized command-line
    options, so it must never be passed blind. Probing --help and caching
    the answer per binary path is the simplest thing that cannot break a
    user whose VICE lacks the option: worst case here is a wasted probe on
    an unsupported build, never a failed launch. Cached because callers
    (including the test suite, which launches many sessions) call this on
    every headless launch of the same binary.
    """
    try:
        r = subprocess.run(
            [exe, "--help"], capture_output=True, text=True, errors="replace", timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "-minimized" in (r.stdout or "")


RESPAWN_LIMIT = 5
RESPAWN_WINDOW = 30.0


def _default_socket_path(name: str) -> str:
    """Unix-socket path for a session's daemon. macOS caps sun_path at ~104
    bytes; long C64_TOOLS_HOME values (pytest tmp dirs) fall back to a
    hashed name under the system temp dir."""
    p = sessions_dir() / f"{name}.sock"
    if len(str(p).encode()) <= 100:
        return str(p)
    digest = hashlib.sha1(str(p).encode()).hexdigest()[:12]
    return str(Path(tempfile.gettempdir()) / f"c64-{digest}.sock")


def _spawn_daemon(name: str, vice_port: int, sock_path: str) -> int:
    """Start the session's monitor daemon; return its pid once it answers a
    ping. On failure the process is killed and SessionError raised."""
    log_path = sessions_dir() / f"{name}.daemon.log"
    with open(log_path, "ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "c64lib.daemon", "--name", name,
             "--vice-port", str(vice_port), "--socket", sock_path],
            stdout=log, stderr=log, start_new_session=True,
        )
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if Path(sock_path).exists():
            try:
                c = DaemonMonitorClient(sock_path)
                try:
                    c.ping()
                finally:
                    c.close()
                return proc.pid
            except (ConnectionError, TimeoutError, OSError):
                pass
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    _kill_proc(proc)
    raise SessionError(f"session daemon failed to start (see {log_path})")


def _kill_proc(proc: subprocess.Popen) -> None:
    """Terminate a launched emulator and make sure it is actually gone —
    SIGTERM, wait, then SIGKILL — so a failed launch never orphans an x64sc."""
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


@dataclass
class Session:
    name: str
    pid: int
    port: int
    model: str
    labels: str | None = None
    daemon_pid: int | None = None
    socket: str | None = None
    loaded_prg: str | None = None
    loaded_at: float = 0.0
    loaded_deps: list[str] | None = None

    @property
    def profile(self) -> MachineProfile:
        return get_profile(self.model)

    # --- persistence ------------------------------------------------------

    def _record_path(self) -> Path:
        return sessions_dir() / f"{self.name}.json"

    def _save(self) -> None:
        self._record_path().write_text(
            json.dumps(
                {"name": self.name, "pid": self.pid, "port": self.port,
                 "model": self.model, "labels": self.labels,
                 "daemon_pid": self.daemon_pid, "socket": self.socket,
                 "loaded_prg": self.loaded_prg, "loaded_at": self.loaded_at,
                 "loaded_deps": self.loaded_deps,
                 "created": time.time()}
            )
        )

    def set_labels_path(self, path: str) -> None:
        self.labels = str(Path(path).resolve())
        self._save()

    def record_loaded(self, prg, deps=()) -> None:
        """Remember what program the emulator is now running, and which
        source files produced it (for the stale-source warning)."""
        self.loaded_prg = str(Path(prg).resolve())
        self.loaded_at = time.time()
        self.loaded_deps = [str(Path(d).resolve()) for d in deps]
        self._save()

    def _respawns_path(self) -> Path:
        return sessions_dir() / f"{self.name}.respawns"

    def _record_respawn_and_check(self) -> None:
        """Circuit breaker: record a respawn; hard-error when the last
        RESPAWN_LIMIT respawns all fall within RESPAWN_WINDOW seconds."""
        p = self._respawns_path()
        stamps = [float(x) for x in p.read_text().split()] if p.exists() else []
        stamps = (stamps + [time.time()])[-RESPAWN_LIMIT:]
        p.write_text("\n".join(f"{t:.3f}" for t in stamps))
        if len(stamps) == RESPAWN_LIMIT and stamps[-1] - stamps[0] <= RESPAWN_WINDOW:
            raise SessionError(
                f"session daemon for {self.name!r} crashed {RESPAWN_LIMIT} "
                f"times in {RESPAWN_WINDOW:.0f}s; recover with: "
                f"c64 session stop {self.name} && c64 session ensure --model {self.model}"
            )

    @staticmethod
    def _load_all() -> list[Session]:
        out = []
        for f in sorted(sessions_dir().glob("*.json")):
            r = json.loads(f.read_text())
            s = Session(name=r["name"], pid=r["pid"], port=r["port"],
                        model=r["model"], labels=r.get("labels"),
                        daemon_pid=r.get("daemon_pid"), socket=r.get("socket"),
                        loaded_prg=r.get("loaded_prg"),
                        loaded_at=r.get("loaded_at", 0.0),
                        loaded_deps=r.get("loaded_deps"))
            if s.is_alive():
                out.append(s)
            else:
                f.unlink(missing_ok=True)  # prune dead record
        return out

    # --- lifecycle --------------------------------------------------------

    @classmethod
    def launch(
        cls,
        model: str = "c64",
        name: str | None = None,
        headless: bool = False,
        warp: bool = False,
        binary: str | None = None,
        disk8: str | None = None,
        cart: str | None = None,
    ) -> Session:
        profile = get_profile(model)
        exe = binary or os.environ.get("C64_TOOLS_X64SC") or shutil.which(profile.vice_emulator)
        if not exe:
            raise SessionError(
                f"{profile.vice_emulator} not found. Install VICE 3.5+ "
                "(macOS: brew install vice; Debian/Ubuntu: apt install vice) "
                "or set C64_TOOLS_X64SC to the binary path."
            )
        name = name or model
        if any(s.name == name for s in cls._load_all()):
            raise SessionError(
                f"session {name!r} already running; stop it or pass a different --name"
            )
        base_args = [exe, *profile.vice_args]
        if warp:
            base_args.append("-warp")
        if disk8:
            disk_path = Path(disk8).resolve()
            dtype = drive_type_for(disk_path)
            if dtype != 1541:  # 1541 is x64sc's default; d71/d81 need the switch
                base_args += ["-drive8type", str(dtype)]
            base_args += ["-8", str(disk_path)]
        if cart:
            # A cartridge is mapped at power-on, not loaded: every supported
            # type attaches through -cartcrt because the .crt header carries
            # its own hardware type and EXROM/GAME lines.
            base_args += ["-cartcrt", str(Path(cart).resolve())]
        env = dict(os.environ)
        if headless:
            env["SDL_VIDEODRIVER"] = "dummy"
            env["SDL_AUDIODRIVER"] = "dummy"
            # SDL_VIDEODRIVER/SDL_AUDIODRIVER are inert on the GTK3 build of
            # x64sc (it never reads them), so on that build the two lines
            # above alone leave "headless" launches opening a focused window
            # that steals host keystrokes into the emulated keyboard buffer.
            # -minimized (checked via _supports_minimized, see its docstring
            # for why this can't be passed unconditionally) closes that gap.
            if _supports_minimized(exe):
                base_args.append("-minimized")

        # A cold x64sc under heavy system load can be slow to open its binary
        # monitor; retry with a fresh port so a transient slow start self-heals
        # instead of failing the whole operation (and never orphaning a proc).
        attempts = int(os.environ.get("C64_TOOLS_LAUNCH_ATTEMPTS", "2"))
        deadline = float(os.environ.get("C64_TOOLS_LAUNCH_DEADLINE", "20"))
        last_err: Exception | None = None
        for _ in range(max(1, attempts)):
            port = _free_port()
            args = base_args + [
                "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{port}",
            ]
            proc = subprocess.Popen(
                args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            try:
                with MonitorClient(port=port) as mon:
                    mon.connect(deadline=deadline)
                    mon.ping()
                    mon.resume()  # connecting/commands leave the machine stopped
            except (ConnectionError, TimeoutError) as e:
                last_err = e
                _kill_proc(proc)
                continue
            session = cls(name=name, pid=proc.pid, port=port, model=model)
            if os.environ.get("C64_TOOLS_NO_DAEMON") != "1":
                sock_path = _default_socket_path(name)
                try:
                    session.daemon_pid = _spawn_daemon(name, port, sock_path)
                except SessionError:
                    _kill_proc(proc)            # no half-sessions
                    raise
                session.socket = sock_path
            session._respawns_path().unlink(missing_ok=True)  # fresh breaker
            session._save()
            return session
        raise SessionError(
            f"VICE started but its monitor never answered after {max(1, attempts)} "
            f"attempt(s): {last_err}"
        )

    @classmethod
    def ensure(cls, model: str = "c64", name: str | None = None,
               headless: bool = False, warp: bool = False) -> tuple[Session, bool]:
        """Attach to a running session, or launch one if absent.

        Returns (session, started). Idempotent bootstrap for scripts and
        recovery one-liners: safe to run whether or not a session exists.
        """
        try:
            return cls.attach(name), False
        except SessionError:
            return cls.launch(model=model, name=name, headless=headless,
                              warp=warp), True

    @classmethod
    def attach(cls, name: str | None = None) -> Session:
        live = cls._load_all()
        if name is not None:
            for s in live:
                if s.name == name:
                    return s
            raise SessionError(
                f"no session named {name!r}. Start one with: c64 session start"
            )
        if not live:
            raise SessionError(
                "no C64 session running. Start one with: c64 session start"
            )
        if len(live) > 1:
            names = ", ".join(s.name for s in live)
            raise SessionError(f"multiple sessions running ({names}); pick one with --session")
        return live[0]

    @classmethod
    def list_all(cls) -> list[Session]:
        return cls._load_all()

    def monitor(self):
        if self.socket and os.environ.get("C64_TOOLS_NO_DAEMON") != "1":
            try:
                return DaemonMonitorClient(self.socket)
            except (ConnectionError, OSError):
                self._record_respawn_and_check()
                print(f"c64: session daemon for {self.name!r} was down; "
                      f"respawning", file=sys.stderr)
                self.daemon_pid = _spawn_daemon(self.name, self.port, self.socket)
                self._save()
                return DaemonMonitorClient(self.socket)
        mon = MonitorClient(port=self.port)
        mon.connect(deadline=10.0)
        return mon

    def is_alive(self) -> bool:
        return _pid_alive(self.pid)

    def stop(self) -> None:
        if self.is_alive():
            try:
                with self.monitor() as mon:
                    mon.quit()
            except (ConnectionError, TimeoutError, OSError, SessionError):
                pass
            deadline = time.monotonic() + 3.0
            while self.is_alive() and time.monotonic() < deadline:
                time.sleep(0.1)
            if self.is_alive():
                os.kill(self.pid, 15)  # SIGTERM
        if self.daemon_pid and _pid_alive(self.daemon_pid):
            try:
                os.kill(self.daemon_pid, 15)
            except ProcessLookupError:
                pass
        if self.socket:
            Path(self.socket).unlink(missing_ok=True)
        self._respawns_path().unlink(missing_ok=True)
        audio_pin_path(self.name).unlink(missing_ok=True)
        self._record_path().unlink(missing_ok=True)
