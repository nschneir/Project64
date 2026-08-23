"""Session lifecycle: launch/attach/stop VICE processes, tracked in JSON records.

VICE holds all machine and debug state; a session record only holds how to
find the process (pid) and its monitor (port).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
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


class RegistryError(SessionError):
    """The registry could not be read whole — at least one `*.json` record in
    the sessions directory did not parse.

    A subclass, so every existing `except SessionError` keeps reporting it
    unchanged; a distinct type because "the registry is unreadable" and "no
    session by that name" are opposite instructions to a caller that reacts
    to absence by starting something. `ops.reboot_with_cart` boots a fresh
    unnamed default when there is nothing to reboot, and `Session.ensure`
    launches: one unreadable record used to send both down that path with
    the named session still running.
    """


def _unreadable_registry(bad: Sequence[SessionError],
                         wanted: str | None = None) -> str:
    """The `RegistryError` message: what could not be read, and the one
    command that clears it.

    `stop --all` is named rather than "delete the file" because it is the
    command that discards an unreadable record *and* reports it — and an
    unreadable record is exactly where an orphaned emulator hides, so the
    caller is being sent to the command that goes looking.
    """
    detail = "; ".join(str(e) for e in bad)
    lead = (f"no session named {wanted!r}, and {len(bad)} session record(s) "
            f"could not be read — one of them may be it"
            if wanted is not None else
            f"{len(bad)} session record(s) could not be read, so what is "
            f"running cannot be determined")
    return (f"{lead}: {detail}. Clear the unreadable record(s) with: "
            f"c64 session stop --all")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_is_session(pid: int, markers: Sequence[str]) -> bool:
    """Whether `pid` is still the process a session started, rather than
    merely a pid that is in use.

    `_pid_alive` answers for the NUMBER, and pid numbers get recycled — on a
    busy Linux box the counter can wrap past a session's pid well within the
    life of its record. It also reports PermissionError, i.e. somebody else's
    process, as alive. So a record whose pid had been inherited by an
    unrelated process read as alive forever: `_scan_records` never pruned it,
    its name could never be relaunched, and `stop()` aimed a SIGTERM at the
    stranger holding the number. Checking the command line for the binary the
    session launched is what tells the two apart — the same test
    `tests/conftest.py`'s reaper (`_is_ours`) has always applied before it
    kills anything.

    Doubt reads as DEAD, deliberately: a wrong "dead" costs a pruned record
    for a session that can be launched again, a wrong "alive" costs a session
    no command can clear.
    """
    if not _pid_alive(pid):
        return False
    try:
        # /proc first where it exists: free, and no subprocess per record.
        # `ps` is the portable fallback (macOS has no procfs) and the exact
        # lookup conftest's reaper uses.
        procfs = Path(f"/proc/{pid}/cmdline")
        if procfs.exists():
            # NUL-separated argv; markers never span two arguments, so the
            # separators can stay as they are for a substring match.
            cmdline = procfs.read_bytes().decode("utf-8", "replace")
        else:
            cmdline = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True, text=True, errors="replace",
            ).stdout
    except OSError:
        # No ps on PATH, /proc unreadable, the process gone between the two
        # calls: all of them are "cannot confirm", which is dead.
        return False
    return any(m and m in cmdline for m in markers)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _display_available() -> bool:
    """Whether this host can open a window at all.

    Only Linux can answer no. x64sc there is a GTK3 build (what Debian and
    Ubuntu package), and GTK3 needs an X11 or Wayland server to start even
    for a `--headless` launch: SDL_VIDEODRIVER is inert on that build (see
    `_supports_minimized`). Without a server x64sc prints "cannot open
    display" and exits, which reaches a caller as a monitor timeout unless
    someone checks first. Not cached: a caller may set DISPLAY between
    launches.
    """
    if sys.platform != "linux":
        return True
    # Exported-but-empty is no display: that is what a stripped systemd or
    # cron environment leaves behind, and X11 treats it as unset too.
    return any(os.environ.get(var) for var in ("DISPLAY", "WAYLAND_DISPLAY"))


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


#: The `-sounddev` block of VICE's own --help: its option line plus the indented
#: description lines under it. Scoped to that block because `dump` shows up
#: elsewhere in --help as an unrelated option or plain prose (`-dumpconfig`, the
#: core-dump switches, the printer text device's "dump file"), and `-soundrecdev`
#: is a different resource whose list could name a device the same way.
_SOUNDDEV_HELP = re.compile(r"^-sounddev\b.*\n(?:[ \t].*\n?)*", re.M)

#: The parenthesised device list inside that block, e.g.
#: `(coreaudio/dummy/dump)`. Membership in this list — not the word appearing in
#: the block — is what says a device exists: the block's own prose may name a
#: device the build does not have, and a build offering `dumpfile` would satisfy
#: a substring match while rejecting `dump`.
_SOUNDDEV_DEVICES = re.compile(r"\(([^)]*)\)")


@functools.cache
def _supports_sound_dump(exe: str) -> bool:
    """Whether this VICE binary offers `dump` as a *playback* sound device.

    Probed rather than assumed, and the failure it avoids is worse than the
    one `_supports_minimized` avoids. VICE rejects an unknown command-line
    OPTION by exiting, which is loud; it rejects an unknown `-sounddev`
    VALUE by logging `device '<name>' not found or not supported` and
    popping a modal error dialog. A modal dialog blocks the emulation loop
    even on a `-minimized` headless launch, so the process stays up with its
    monitor unanswered — which is indistinguishable from the wedge this
    device is here to remove (observed 2026-08-10 on this GTK3 build, from a
    deliberately bogus value; it took a human looking at the screen to see
    what the runner could not). So this answers False on any doubt, which is
    the cheaper wrong answer rather than a safe one: a false positive wedges
    every headless session on this build, while a false negative only restores
    the pre-probe status quo — the host device, which is itself what a
    headless session can hang waiting on where nothing drains it (docs/cli.md,
    `c64 session start --headless`).

    True means the whole launch pair is available, `-soundarg` included:
    `dump` without it writes its register dump to `vicesnd.sid` in the
    caller's working directory, and `-soundarg` handed to a build that lacks
    the option exits VICE the way any unrecognized option does. Half the pair
    is never worth launching with, so one boolean answers for both.
    """
    try:
        r = subprocess.run(
            [exe, "--help"], capture_output=True, text=True, errors="replace",
            timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    help_text = r.stdout or ""
    block = _SOUNDDEV_HELP.search(help_text)
    if not block:
        return False
    devices = _SOUNDDEV_DEVICES.search(block.group(0))
    if not devices:
        return False
    # This build separates the names with `/`; `,` and stray whitespace are
    # tolerated so a build that lists them differently still parses.
    names = {n.strip() for n in re.split(r"[/,]", devices.group(1))}
    # `-soundarg` is its own non-indented option line, so it is checked against
    # the whole help output rather than the block — but anchored to a line
    # start, not matched as a substring: this option's absence has to cost the
    # sink, and a stray mention inside some other option's description would
    # instead hand `-soundarg` to a build that exits on it, costing the launch.
    return "dump" in names and re.search(r"^-soundarg\b", help_text, re.M) is not None


RESPAWN_LIMIT = 5
RESPAWN_WINDOW = 30.0

# How long a launch waits for the monitor before checking whether the emulator
# is still alive. Short enough that a child which exits immediately is noticed
# at once, long enough that the connect retry does not become a busy loop.
_LAUNCH_POLL_INTERVAL = 0.5


def _default_socket_path(name: str) -> str:
    """Unix-socket path for a session's daemon. macOS caps sun_path at ~104
    bytes; long C64_TOOLS_HOME values (pytest tmp dirs) fall back to a
    hashed name under a per-user dir in the system temp dir."""
    p = sessions_dir() / f"{name}.sock"
    if len(str(p).encode()) <= 100:
        return str(p)
    digest = hashlib.sha1(str(p).encode()).hexdigest()[:12]
    # The temp dir is shared and world-writable on Linux (/tmp), and this name
    # is derived, not secret: bare in /tmp another user could pre-create the
    # socket the daemon then binds. So own the parent instead — 0700 and proven
    # ours. Budget: tempdir (~50 bytes) + "c64-tools-<uid>/" + "c64-<12 hex>.sock"
    # is ~85, inside the ~100-byte sun_path limit this fallback exists to respect.
    uid = os.getuid()
    d = Path(tempfile.gettempdir()) / f"c64-tools-{uid}"
    try:
        d.mkdir(mode=0o700, exist_ok=True)
    except FileExistsError:             # exist_ok covers a dir, not a planted file
        raise SessionError(
            f"the daemon socket dir {d} exists but is not a directory — remove "
            f"whatever is squatting there: ls -ld {d}"
        ) from None
    st = d.lstat()                      # lstat: a symlink here is the attack
    if stat.S_ISLNK(st.st_mode) or st.st_uid != uid:
        raise SessionError(
            f"the daemon socket dir {d} is a symlink or belongs to another user "
            f"(uid {st.st_uid}, not {uid}) — someone else's; inspect and remove "
            f"it as its owner: ls -ld {d}"
        )
    os.chmod(d, 0o700)                  # mkdir's mode is umask-masked, and an
                                        # exist_ok dir keeps whatever it had
    return str(d / f"c64-{digest}.sock")


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


def _connect_while_alive(
    mon: MonitorClient, proc: subprocess.Popen, deadline: float
) -> None:
    """`mon.connect(deadline)`, but give up as soon as `proc` has exited.

    `MonitorClient.connect` watches only the socket, so an emulator that died
    on a missing ROM or an unusable display would otherwise cost the full
    deadline on every attempt before anyone looked at why.
    """
    end = time.monotonic() + deadline
    while True:
        remaining = end - time.monotonic()
        try:
            mon.connect(deadline=min(_LAUNCH_POLL_INTERVAL, remaining))
            return
        except ConnectionError:
            if proc.poll() is not None or remaining <= _LAUNCH_POLL_INTERVAL:
                raise


def _log_tail(path: Path, since: int = 0, lines: int = 5) -> str:
    """The last `lines` a launch log grew past byte `since`, for quoting in an
    error message.

    The offset is what keeps the quote honest: the log is append-only and
    shared by every launch of this session name, so reading from byte 0 would
    let a mute emulator be reported in the words of the run before it.
    """
    try:
        with open(path, "rb") as f:
            f.seek(since)
            text = f.read().decode(errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:]).strip()


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
    # Basename of the emulator binary `launch` started. A pid alone cannot
    # say whether the session is still there once pids get recycled, and the
    # model name cannot say which binary ran (`--binary` and C64_TOOLS_X64SC
    # both override it) — see `_pid_is_session`, which matches this against
    # the pid's command line. Optional so records written before sessions had
    # a process identity keep loading.
    exe: str | None = None

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
                 "loaded_deps": self.loaded_deps, "exe": self.exe,
                 "created": time.time()}
            ), encoding="utf-8"
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
        stamps = [float(x) for x in p.read_text(encoding="utf-8").split()] if p.exists() else []
        stamps = (stamps + [time.time()])[-RESPAWN_LIMIT:]
        p.write_text("\n".join(f"{t:.3f}" for t in stamps), encoding="utf-8")
        if len(stamps) == RESPAWN_LIMIT and stamps[-1] - stamps[0] <= RESPAWN_WINDOW:
            raise SessionError(
                f"session daemon for {self.name!r} crashed {RESPAWN_LIMIT} "
                f"times in {RESPAWN_WINDOW:.0f}s; recover with: "
                f"c64 session stop {self.name} && c64 session ensure --model {self.model}"
            )

    @staticmethod
    def _from_record(path: Path) -> Session:
        """One session record, whether or not its process is still alive.

        A record this cannot read raises `SessionError` naming the file, not
        the raw `KeyError('port')` the lookup produces. Two reasons, and the
        message is the smaller one: `str(KeyError)` is the bare quoted key,
        so a caller reading `{"error": "'port'"}` learns neither which of the
        records on disk is wrong nor that the registry is what broke.

        The type is the larger one. Every registry read goes through here —
        `attach`, `list_all` and `launch`'s duplicate-name check all do — and
        MOST of their callers already handle `SessionError` by reporting it,
        so one truncated or older-format record now exits 1 with a message
        from them instead of escaping as a traceback. What that record must
        NOT do is answer for the records next to it: `attach` reads through
        `_scan_records`, which keeps this error per file, and reports a
        `RegistryError` only where the answer would have depended on it.

        Not all of them: `cli.py`'s `session list` calls `Session.list_all()`
        bare, outside any try. Widening the type never reached that, and
        neither should a per-command patch — `JsonAwareGroup.invoke` in
        `cli.py` now catches `SessionError` at the CLI boundary, so a record no
        command guards against is still a `{"error": ...}` payload and not a
        traceback over empty `--json` stdout.
        """
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
            return Session(name=r["name"], pid=r["pid"], port=r["port"],
                           model=r["model"], labels=r.get("labels"),
                           daemon_pid=r.get("daemon_pid"), socket=r.get("socket"),
                           loaded_prg=r.get("loaded_prg"),
                           loaded_at=r.get("loaded_at", 0.0),
                           loaded_deps=r.get("loaded_deps"),
                           # .get, not [...]: a record written before sessions
                           # carried a process identity must keep loading, and
                           # `is_alive` has a fallback for the missing name.
                           exe=r.get("exe"))
        except KeyError as e:
            raise SessionError(
                f"session record {path} is unreadable: missing {e.args[0]!r}"
            ) from None
        except (ValueError, OSError) as e:
            # ValueError covers both halves of the read: JSONDecodeError for
            # a truncated write, and UnicodeDecodeError (a ValueError, NOT an
            # OSError) for a record that is not text at all.
            raise SessionError(
                f"session record {path} is unreadable: {e}"
            ) from None

    @staticmethod
    def _scan_records() -> tuple[list[Session], list[SessionError]]:
        """Every live session record, plus one error per record that would
        not parse — the registry read that does not let one bad file stand
        for the whole directory.

        Dead records are pruned as they are read, exactly as `_load_all`
        does; an unreadable one is left on disk, because nothing here knows
        whether it describes a running emulator. `stop_all` is what discards
        it, and it is the command the errors point the caller at.
        """
        out: list[Session] = []
        bad: list[SessionError] = []
        for f in sorted(sessions_dir().glob("*.json")):
            try:
                s = Session._from_record(f)
            except SessionError as e:
                bad.append(e)
                continue
            if s.is_alive():
                out.append(s)
            else:
                f.unlink(missing_ok=True)  # prune dead record
                # ...and its audio pin. `stop()` clears it, but a session
                # that was killed or crashed never reaches `stop()`, which is
                # the common way a record ends up here. The audio pin is inert
                # once its pid is gone (`audio._read_pin` refuses a foreign
                # one), so this is housekeeping, not correctness: without it a
                # `<name>.audio` outlives every session whose name is never
                # reused.
                audio_pin_path(s.name).unlink(missing_ok=True)
        return out, bad

    @staticmethod
    def _load_all() -> list[Session]:
        """The live sessions, or the first unreadable record's error.

        The strict read, and what `list_all` and `launch`'s duplicate-name
        check want: a listing that silently dropped a record it could not
        parse would hide the file from `session list`, one of the three
        commands that report it (`session start` and `stop --all` are the
        others), and a duplicate-name check cannot clear a name it could not
        read.
        Lookups that must not read "unreadable" as "absent" go through
        `_scan_records` — see `attach` and `RegistryError`.
        """
        out, bad = Session._scan_records()
        if bad:
            raise bad[0]
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
        # Before anything is spawned or logged: a display-less Linux host
        # cannot run x64sc at all, and the failure it produces on its own
        # (x64sc exits at startup, the monitor never answers) reads as a
        # timeout and sends the caller hunting the wrong thing.
        if not _display_available():
            raise SessionError(
                f"no display: {profile.vice_emulator} is a GTK3 build here, "
                "so it needs an X11 or Wayland server even with --headless "
                "(SDL_VIDEODRIVER does not apply to it). Run the command "
                "under a virtual display — xvfb-run -a c64 session start — "
                "or set DISPLAY to a server you already have."
            )
        exe = binary or os.environ.get("C64_TOOLS_X64SC") or shutil.which(profile.vice_emulator)
        if not exe:
            raise SessionError(
                f"{profile.vice_emulator} not found. Install VICE 3.5+ "
                "(macOS: brew install vice; Debian/Ubuntu: apt install vice, "
                "from contrib/multiverse — that package ships no C64 ROMs, so "
                "also install them per /usr/share/doc/vice/README.Debian) "
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
            # Nobody is listening to a headless session, and depending on a
            # host that is has been measured to hang it: VICE's sound device
            # is the emulation loop's flow control at real time (see
            # `c64lib.audio`), so where the host reports no output device
            # coreaudio never drains VICE's buffer and every real-time
            # operation wedges — `pinned_record_start`'s pin-and-arm first.
            # `dump` is a file-backed sink that always consumes, so the
            # dependency is gone rather than raced around, and WAV recording
            # is unaffected (measured: the live arpeggio capture passes, WAV
            # growing at real time's 96 kB/s).
            #
            # NOT `dummy`, the obvious name: it never consumes, so VICE
            # overflows its own sound buffer ("Sound buffer overflow (cycle
            # based)") and discards it — `SoundRecordDeviceName` then sees no
            # samples and a capture comes back as a bare 44-byte header
            # (measured 2026-08-10, same fixture that verifies `dump`).
            #
            # -soundarg is mandatory, not decoration: unset, the dump device
            # writes its register dump to `vicesnd.sid` in the *caller's*
            # working directory. os.devnull cannot grow and cannot litter.
            #
            # The pair is probed, never assumed — an unrecognized -sounddev
            # value pops a modal dialog that blocks the emulation loop, which
            # is this bug wearing a different hat, and an unrecognized
            # -soundarg exits outright. One probe answers for both, so a build
            # missing either keeps host audio rather than getting half of it.
            # See _supports_sound_dump.
            if _supports_sound_dump(exe):
                base_args += ["-sounddev", "dump", "-soundarg", os.devnull]

        # A cold x64sc under heavy system load can be slow to open its binary
        # monitor; retry with a fresh port so a transient slow start self-heals
        # instead of failing the whole operation (and never orphaning a proc).
        attempts = int(os.environ.get("C64_TOOLS_LAUNCH_ATTEMPTS", "2"))
        deadline = float(os.environ.get("C64_TOOLS_LAUNCH_DEADLINE", "20"))
        last_err: Exception | None = None
        last_exit: int | None = None
        # Both streams go to a log rather than DEVNULL: when x64sc refuses to
        # start (no ROMs, no usable display, a flag this build rejects) it says
        # so on stderr and exits, and that sentence is the whole diagnosis. The
        # log is append-only and outlives the launch, so where it already ends
        # is remembered: only what THIS launch adds may be quoted back.
        log_path = sessions_dir() / f"{name}.launch.log"
        log_start = log_path.stat().st_size if log_path.exists() else 0
        for _ in range(max(1, attempts)):
            port = _free_port()
            args = base_args + [
                "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{port}",
            ]
            with open(log_path, "ab") as log:
                proc = subprocess.Popen(args, env=env, stdout=log, stderr=log)
            try:
                with MonitorClient(port=port) as mon:
                    _connect_while_alive(mon, proc, deadline)
                    mon.ping()
                    mon.resume()  # connecting/commands leave the machine stopped
            except (ConnectionError, TimeoutError) as e:
                last_err = e
                last_exit = proc.poll()
                if last_exit is None:
                    _kill_proc(proc)
                continue
            session = cls(name=name, pid=proc.pid, port=port, model=model,
                          exe=Path(exe).name)
            if os.environ.get("C64_TOOLS_NO_DAEMON") != "1":
                try:
                    # Inside the guard, not above it: _default_socket_path
                    # touches the filesystem (per-user socket dir) and raises
                    # SessionError on a squatted one. Raising out here would
                    # leave the emulator already started above running and
                    # unrecorded — the very orphan the kill below prevents.
                    sock_path = _default_socket_path(name)
                    session.daemon_pid = _spawn_daemon(name, port, sock_path)
                except SessionError:
                    _kill_proc(proc)            # no half-sessions
                    raise
                session.socket = sock_path
            session._respawns_path().unlink(missing_ok=True)  # fresh breaker
            session._save()
            return session
        if last_exit is not None:
            tail = _log_tail(log_path, since=log_start)
            said = f", saying:\n{tail}\nFull output" if tail else ", printing nothing. Log"
            raise SessionError(
                f"{Path(exe).name} exited with code {last_exit} before its monitor "
                f"answered ({max(1, attempts)} attempt(s))"
                f"{said}: {log_path}"
            )
        raise SessionError(
            f"VICE started but its monitor never answered after {max(1, attempts)} "
            f"attempt(s): {last_err}. Its output is in {log_path}"
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
        except RegistryError:
            # Not an absent session: launching here would put a second
            # emulator behind a name that may already be up, and the
            # duplicate-name check in `launch` reads the same registry, so it
            # cannot catch what it could not parse either.
            raise
        except SessionError:
            return cls.launch(model=model, name=name, headless=headless,
                              warp=warp), True

    @classmethod
    def attach(cls, name: str | None = None) -> Session:
        """The session `name` names, or the only one running.

        Reads through `_scan_records`, so a record this cannot parse costs
        only itself: the session asked for is returned if ITS record is
        readable. Where the answer would depend on the unreadable file — the
        name was not found among the rest, or the no-name shortcut is
        counting sessions — the failure is a `RegistryError` rather than the
        absence report, because a caller that starts something on absence
        would start it alongside a session that may be running.
        """
        live, bad = cls._scan_records()
        if name is not None:
            for s in live:
                if s.name == name:
                    return s
            if bad:
                raise RegistryError(_unreadable_registry(bad, wanted=name))
            raise SessionError(
                f"no session named {name!r}. Start one with: c64 session start"
            )
        if bad:
            raise RegistryError(_unreadable_registry(bad))
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
        # Not `_pid_alive`: the session is alive only while its pid is still
        # running the binary it launched (see `_pid_is_session`). A record
        # from before `exe` existed falls back to the emulator its model
        # launches, which is what it would have stored.
        markers = [self.exe] if self.exe else [self.profile.vice_emulator]
        return _pid_is_session(self.pid, markers)

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
                try:
                    os.kill(self.pid, 15)  # SIGTERM
                except (ProcessLookupError, PermissionError):
                    # Whether the process died in the gap above or belongs to
                    # somebody else, the signal is not what this call owes the
                    # caller: the cleanup below is. Letting either escape here
                    # left the record — and the socket, respawn counter and
                    # audio pin — on disk, so the session stayed listed and
                    # its name could never be used again.
                    pass
        if self.daemon_pid and _pid_alive(self.daemon_pid):
            try:
                os.kill(self.daemon_pid, 15)
            except (ProcessLookupError, PermissionError):
                pass  # same bargain as the SIGTERM above
        if self.socket:
            Path(self.socket).unlink(missing_ok=True)
        self._respawns_path().unlink(missing_ok=True)
        audio_pin_path(self.name).unlink(missing_ok=True)
        self._record_path().unlink(missing_ok=True)

    @classmethod
    def stop_all(cls) -> list[str]:
        """Stop every session in the registry; return the names stopped.

        Records are read straight off disk rather than through `_load_all()`,
        which drops a dead one as it goes: a session whose emulator is already
        gone is exactly what this is for — the la-galaxia dogfood (2026-08-08)
        found two x64sc processes orphaned by a *previous* conversation — and
        pruning it there would leave its socket and respawn counter behind
        instead of letting `stop()` (already safe on a dead pid) clear them.
        So a dead session is reaped and counted as stopped, never an error.

        A failure does not abandon the rest: one session that refuses to die
        must not strand the others, so the errors are collected and raised
        once, naming both halves of the state left behind — what went down,
        and what is still registered.

        A record that cannot be READ is discarded and reported, which is the
        one place this parts company with the reaping above. Reading is
        inside the same try as stopping because it is exactly as
        failure-prone: it ran above the try once, and a single truncated
        record turned this whole command into a traceback — on the ONE
        command that could have cleared it, since every other registry read
        goes through `_from_record` too. So the file goes: a record this
        cannot parse is a record it cannot stop, with no pid to signal and
        no socket to close, and leaving it would keep `session list`,
        `session stop NAME` and `session start` broken as well.

        But it is counted as a failure rather than reaped like a dead
        session, because the two are not the same claim. A dead session is
        KNOWN dead — its pid was checked. An unparseable record is precisely
        where an orphaned emulator hides, which is what this command exists
        to find, so `stopped` must not claim a stop nobody made and the
        caller has to be told to go look.
        """
        stopped: list[str] = []
        failures: list[str] = []
        discarded: list[str] = []
        for f in sorted(sessions_dir().glob("*.json")):
            try:
                s = cls._from_record(f)
            except SessionError as e:
                # `_from_record` normalizes every way a record can fail to
                # read — missing key, bad JSON, undecodable bytes — into this
                # one type, with the file named in the message.
                f.unlink(missing_ok=True)
                discarded.append(str(e))
                continue
            try:
                s.stop()
            except (SessionError, OSError) as e:
                failures.append(f"{s.name!r}: {e}")
            else:
                stopped.append(s.name)
        if failures or discarded:
            parts = [f"stopped {', '.join(repr(n) for n in stopped) or 'nothing'}"]
            if failures:
                parts.append(f"could not stop {'; '.join(failures)} — still "
                             f"registered, check `c64 session list`")
            if discarded:
                parts.append(f"discarded {'; '.join(discarded)} — nothing "
                             f"could be stopped for it, so check `ps` for an "
                             f"emulator it may have left behind")
            raise SessionError("; ".join(parts))
        return stopped
