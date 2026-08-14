"""Per-session monitor daemon: owns the one VICE binary-monitor connection.

VICE resumes the CPU whenever a monitor connection closes and accepts only
one monitor connection at a time (2026-07-10 transport findings). This
process holds that single connection for the session's lifetime, so the
machine's run/stop state survives across c64/MCP commands — each command
is a short-lived IPC client on the session's unix socket.

Run as:  python -m c64lib.daemon --name NAME --vice-port PORT --socket PATH
Spawned by Session.launch; the client side is c64lib.daemon_client."""

from __future__ import annotations

import argparse
import json
import os
import select
import socket
import time
import traceback

from . import rpc

# `SID_BASE`/`SID_REGISTERS` are `c64lib.audio`'s pinned domain values, and the
# daemon runs that module's sampling loop on its own VICE connection; importing
# them beats a second copy of the address drifting from the first. Not a cycle:
# `audio` reaches the daemon through `daemon_client`, never through this module.
from .audio import SID_BASE, SID_REGISTERS
from .monitor import MonitorClient

# `profile_samples_loop` is the profile bracket itself, shared rather than
# copied: see `_profile_samples`. Not a cycle either — `ops` reaches the
# daemon through `daemon_client`, never through this module.
from .ops import profile_samples_loop
from .protocol import CP_EXEC, Command, ResponseType

RUNNING = "running"
STOPPED = "stopped"

#: every MonitorClient method a client may call, plus the release verb.
ALLOWED = frozenset({
    "ping", "memory_read", "memory_write", "resume", "release", "registers",
    "set_register", "reset", "keyboard_feed", "display", "palette",
    "vice_info", "quit", "resource_get", "resource_set", "autostart",
    "checkpoint_set", "checkpoint_delete", "checkpoint_toggle", "checkpoint_list",
    "condition_set", "step", "finish", "wait_for_stop", "status", "run_until",
    "profile_samples",
    # `sid_log_at` is `sid_log` with writes scheduled inside the window. It is
    # a SEPARATE method name rather than a third argument on purpose: an older
    # daemon ignores extra positional args, so a schedule sent that way would
    # be dropped without a word and the capture would look aimed and not be.
    # An unknown method name is an `rpc.UnknownDaemonMethod` the client can
    # fall back on — the same mechanism `run_until` and `sid_log` were
    # introduced with, and told apart on the wire from the ValueError
    # `_frame_writes` raises for a schedule this daemon refuses.
    "sid_log", "sid_log_at",
})

#: methods that leave the machine halted by their own meaning.
STOPPING = frozenset({"step", "finish"})


def _frame_writes(raw) -> dict[int, list[tuple[int, int]]]:
    """A `sid_log_at` schedule off the wire, re-checked here.

    JSON has no integer keys and no tuples, so `{6: [(0xd404, 0x11)]}`
    arrives as `{"6": [[54276, 17]]}`. Re-validated rather than trusted:
    the range checks `audio.parse_frame_writes` makes belong to the front
    end's error message, but this process holds the session's only VICE
    connection, and a bad byte here would be a `memory_write` raising in
    the middle of somebody's capture window.
    """
    out: dict[int, list[tuple[int, int]]] = {}
    for frame, pairs in dict(raw or {}).items():
        entries = []
        for addr, value in pairs:
            addr, value = int(addr), int(value)
            if not 0 <= addr <= 0xFFFF or not 0 <= value <= 0xFF:
                raise ValueError(f"sid_log_at write ${addr:x}={value} is out "
                                 f"of range (address 0-65535, value 0-255)")
            entries.append((addr, value))
        out[int(frame)] = entries
    return out


class PetDaemon:
    """One VICE connection + the session's desired run/stop state."""

    def __init__(self, mon: MonitorClient, listen: socket.socket,
                 session: str):
        self.mon = mon
        self.listen = listen
        self.session = session
        self.state = RUNNING
        self._quitting = False

    # --- main loops -------------------------------------------------------

    def serve_forever(self) -> None:
        while True:
            if not self._idle_wait():
                return                          # x64sc died while idle
            client, _ = self.listen.accept()
            self._handle(client)
            if self._quitting:
                return

    def _idle_wait(self) -> bool:
        """Block until a client connects; meanwhile pump unsolicited VICE
        events. A stop=True checkpoint can fire with nobody waiting — the
        machine parks and the daemon must remember STOPPED, or the next
        inspection command's release() would destroy the parked state.
        Returns False when the VICE connection is gone."""
        while True:
            vice = self.mon._sock
            if vice is None:
                # close() clears the socket outright: there is no connection
                # left to select on, and select() answers None with TypeError,
                # which the guard below does not catch. Same VICE-gone answer.
                return False
            try:
                r, _, _ = select.select([self.listen, vice], [], [])
            except (ValueError, OSError):
                # A socket closed under us (fileno -1) — VICE died, or we're
                # being torn down. Treat as VICE-gone so serve_forever exits
                # cleanly instead of crashing the daemon with a traceback.
                return False
            if vice in r and not self._pump_vice_events():
                return False
            if self.listen in r:
                return True

    def _pump_vice_events(self) -> bool:
        """Idle pump. VICE emits a bare STOPPED for EVERY halt — including
        the momentary halt each monitor command causes — so tenure noise
        delivered late can land here. Process in order, last state wins:
        noise is always followed by the RESUMED of the restore that undid
        it, while a genuine unattended park is a STOPPED with no RESUMED
        after it (false idle parks read as a machine frozen at a random
        loop PC — seen live as the jmp instead of mainloop)."""
        try:
            events = self.mon.poll_events(0.05)
        except (ConnectionError, OSError):
            return False
        pending = None
        for ev in events:
            if ev.response_type == ResponseType.STOPPED:
                pending = STOPPED
            elif ev.response_type == ResponseType.RESUMED:
                pending = RUNNING
            self.mon.events.append(ev)          # keep for a later wait_for_stop
        if pending is not None:
            self.state = pending
        return True

    # --- one client -------------------------------------------------------

    def _handle(self, client: socket.socket) -> None:
        try:
            self._serve_client(client)
        except (OSError, ValueError) as e:
            # A misbehaving command client — one that disconnects mid-hello or
            # mid-response (BrokenPipeError) or sends malformed JSON — must
            # never take down the session daemon. Abandon it and keep serving.
            # VICE death is caught inside _serve_client (it sets _quitting), so
            # reaching here means the IPC peer, not the emulator, is the problem.
            print(f"c64 daemon: client error, dropping connection: {e!r}",
                  flush=True)
        finally:
            client.close()
            if not self._quitting:
                self._restore()

    def _serve_client(self, client: socket.socket) -> None:
        f = client.makefile("rwb")
        rpc.send_line(f, {"hello": "c64-daemon",
                          "version": rpc.PROTOCOL_VERSION,
                          "session": self.session})
        while True:
            line = f.readline()
            if not line:
                return                          # client disconnected
            req = json.loads(line)
            resp = {"id": req.get("id")}
            try:
                result = self._dispatch(client, req["method"],
                                        rpc.decode_value(req.get("args", [])),
                                        rpc.decode_value(req.get("kwargs", {})))
                resp["ok"] = rpc.encode_value(result)
            except Exception as e:              # marshalled to the client
                resp.update(rpc.error_payload(e))
                rpc.send_line(f, resp)
                if isinstance(e, ConnectionError):
                    self._quitting = True       # x64sc died; nothing to restore
                    return
                continue
            rpc.send_line(f, resp)
            if req["method"] == "quit":
                self._quitting = True
                return

    def _dispatch(self, client: socket.socket, method: str,
                  args: list, kwargs: dict):
        if method not in ALLOWED:
            # Its own type, not a bare ValueError: this is the handshake a
            # client's fallback catches, and falling back re-runs the work.
            # `rpc.error_payload` gives it the wire `code` that tells it apart
            # from a ValueError raised by a method we DO have.
            raise rpc.UnknownDaemonMethod(f"unknown daemon method {method!r}")
        if method == "status":
            return {"state": self.state}
        if method == "release":
            self._restore()
            return None
        if method == "resume":
            self.mon.resume()
            self.state = RUNNING
            return None
        if method == "wait_for_stop":
            timeout = float(args[0]) if args else float(kwargs["timeout"])
            return self._wait_for_stop(client, timeout)
        if method == "run_until":
            return self._run_until(client, int(args[0]), float(args[1]),
                                   int(args[2]))
        if method == "profile_samples":
            return self._profile_samples(client, int(args[0]), float(args[1]),
                                         int(args[2]), bool(args[3]),
                                         int(args[4]))
        if method == "sid_log":
            return self._sid_log(client, int(args[0]), float(args[1]))
        if method == "sid_log_at":
            return self._sid_log(client, int(args[0]), float(args[1]),
                                 _frame_writes(args[2]))
        result = getattr(self.mon, method)(*args, **kwargs)
        if method in STOPPING:
            self.state = STOPPED
        return result

    def _wait_for_stop(self, client: socket.socket, timeout: float):
        """wait_for_stop in <=0.5 s slices, aborting if the client vanishes
        (a Ctrl-C'd `c64 wait --break` must not wedge the daemon)."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            info = self.mon.wait_for_stop(min(0.5, remaining))
            if info is not None:
                self.state = STOPPED
                return info
            r, _, _ = select.select([client], [], [], 0)
            if r and client.recv(1, socket.MSG_PEEK) == b"":
                return None                     # client gone; caller restores

    def _run_until(self, client: socket.socket, addr: int, timeout: float,
                   count: int) -> dict:
        """The `c64 until --count` loop, run against the direct VICE
        connection — N arrivals cost one IPC round-trip instead of 2-4 each
        (frame-stepping was ~0.5 s per arrival through per-hit RPCs).

        Same contract as the client-side loop it replaces: a persistent
        checkpoint, the hit_count fallback for lost STOPPED events (see the
        comment on it below), machine STOPPED at the final arrival; on
        timeout (or the client vanishing) the checkpoint is deleted and the
        machine is left RUNNING with registers None."""
        deadline = time.monotonic() + timeout
        ck = self.mon.checkpoint_set(addr, op=CP_EXEC, temporary=False)
        for i in range(count):
            self.mon.resume()
            self.state = RUNNING
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.mon.checkpoint_delete(ck.number)
                    self.mon.resume()
                    self.state = RUNNING
                    return {"registers": None, "reached": i, "count": count}
                info = self.mon.wait_for_stop(min(0.5, remaining))
                if info is not None and info.checkpoint == ck.number:
                    break
                cur = next((c for c in self.mon.checkpoint_list()
                            if c.number == ck.number), None)
                if cur is not None and (cur.hit or cur.hit_count > i):
                    # `hit_count` is the whole working half. CHECKPOINT_LIST's
                    # `currently hit` byte is never set on VICE 3.10 — probed
                    # 2026-08-14 on a direct monitor connection: a checkpoint
                    # the machine was STOPPED on listed `hit=False
                    # hit_count=1`, on two consecutive reads and again after a
                    # resume. VICE fills that flag only in the CHECKPOINT_GET
                    # response it pushes with the STOPPED event, which is the
                    # very thing this branch exists because we lost. `cur.hit`
                    # stays as a free upgrade if some later VICE starts
                    # filling it in; it has never fired here.
                    break
                self.mon.resume()                # the list stopped the machine
                r, _, _ = select.select([client], [], [], 0)
                if r and client.recv(1, socket.MSG_PEEK) == b"":
                    # Client gone (Ctrl-C mid-until): clean up, keep running.
                    self.mon.checkpoint_delete(ck.number)
                    return {"registers": None, "reached": i, "count": count}
        regs = self.mon.registers()
        self.mon.checkpoint_delete(ck.number)
        self.state = STOPPED
        return {"registers": regs, "reached": count, "count": count}

    def _profile_samples(self, client: socket.socket, addr: int,
                         timeout: float, n: int, with_irq: bool,
                         trap: int) -> dict:
        """The `c64 profile --samples` loop, run against the direct VICE
        connection — N arrivals cost one IPC round-trip instead of one
        re-arm-and-measure bracket (~15 monitor commands) each.

        The loop itself is `ops.profile_samples_loop`, called here with the
        two hooks it leaves open: the CIA cascade, the fake-JSR re-arm and
        the I-flag bookkeeping are intricate enough that a second copy would
        drift, and it is the same code a direct connection runs. `run_until`
        and `_sid_log` predate that split and still carry their own copies.

        Contract as documented there: machine STOPPED at the final arrival;
        on timeout (or the client vanishing) the checkpoint is deleted, the
        machine is left RUNNING with registers None — and the CIA#2 timers
        are left running with the I flag still masked, which the front ends
        report, because the machine is running again by then.
        """
        def _gone() -> bool:
            r, _, _ = select.select([client], [], [], 0)
            return bool(r) and client.recv(1, socket.MSG_PEEK) == b""

        def _state(running: bool) -> None:
            self.state = RUNNING if running else STOPPED

        return profile_samples_loop(self.mon, addr, n, timeout, with_irq,
                                    trap, on_state=_state, abort=_gone)

    def _sid_log(self, client: socket.socket, frames: int, timeout: float,
                 writes: dict[int, list[tuple[int, int]]] | None = None
                 ) -> list[bytes]:
        """Sample the SID's whole register block once per video frame, on the
        daemon's own VICE connection — one IPC round-trip for the entire log
        instead of two per frame (see `_run_until` for the same arithmetic:
        per-hit RPCs cost ~0.5 s each).

        One resume is exactly one frame: VICE picks up an asynchronous
        monitor command at the next vsync, so the machine halts at the top of
        a frame and the read that follows a resume samples the frame it just
        finished. No raster polling — `$D012` reads 12 at every halt, so the
        wrap `c64lib.audio` was originally to detect never happens.

        Returns the blocks it captured, which is fewer than `frames` if the
        deadline passes or the client vanishes; the caller reports the
        shortfall. The machine is left RUNNING either way.

        **It owns the daemon for the whole log.** Dispatch is one client at a
        time, so every other command on this session waits here — about 70 s
        for a 1500-frame real-time capture, which is a normal 30 s window.
        `_run_until` has the same shape, but its callers name a timeout they
        are already waiting on; this one is held for a capture window the
        rest of the session knows nothing about. Not a wedge, and not worth
        interleaving for: a capture that shared the machine would no longer be
        capturing what it claims to. Read a stalled session during an audio
        capture as this, and wait for it.

        Which is exactly why `writes` exists. Owning the machine for the whole
        window means nothing outside can act during it, so an effect the
        capture is meant to observe has to be triggered from in here:
        `{frame: [(addr, value), …]}` is performed while the machine is
        halted, immediately before the resume that runs that frame, so frame N
        is the first SAMPLED frame carrying its effect. Writing between the
        read and the resume costs no emulated time at all — the machine is
        already stopped — so an aimed capture and an unaimed one have the same
        frame clock.
        """
        deadline = time.monotonic() + timeout
        scheduled = writes or {}
        out: list[bytes] = []
        while len(out) < frames and time.monotonic() < deadline:
            for addr, value in scheduled.get(len(out), ()):
                self.mon.memory_write(addr, bytes([value]))
            self.mon.resume()
            self.state = RUNNING
            out.append(self.mon.memory_read(SID_BASE, SID_REGISTERS))
            r, _, _ = select.select([client], [], [], 0)
            if r and client.recv(1, socket.MSG_PEEK) == b"":
                break                    # client gone (Ctrl-C mid-log)
        self.mon.resume()
        self.state = RUNNING
        return out

    def _restore(self) -> None:
        """release()/disconnect: put the machine back in its desired state.
        Monitor commands stop the CPU as a side effect; only an explicit
        resume sets RUNNING, so restoring means EXIT iff desired RUNNING.

        First, check pending VICE events for a park that fired DURING this
        client's tenure (release -> hit lands in microseconds while the
        daemon is blocked reading the IPC socket): resuming blindly would
        destroy it. Only checkpoint-hit evidence counts — a bare STOPPED
        here is the noise of the command-stop we are about to undo, NOT a
        park (treating it as one wedges the machine stopped forever). A
        RESUMED after a hit cancels it (stale hit from before an explicit
        resume). Never flips STOPPED->RUNNING: a step/finish park stands."""
        try:
            events = self.mon.poll_events(0.05)
        except (ConnectionError, OSError):
            return                              # VICE gone; loops will notice
        park = False
        for ev in events:
            if (ev.response_type == Command.CHECKPOINT_GET
                    and len(ev.body) > 4 and ev.body[4]):
                park = True
            elif ev.response_type == ResponseType.RESUMED:
                park = False
            self.mon.events.append(ev)          # keep for a later wait_for_stop
        if park:
            self.state = STOPPED
        if self.state == RUNNING:
            try:
                self.mon.resume()
            except (ConnectionError, TimeoutError, OSError):
                pass                            # VICE gone; loops will notice


def _connect_vice(port: int) -> MonitorClient:
    """Open the daemon's single, long-lived VICE connection.

    VICE services one monitor connection at a time and frees the slot only
    once it notices the previous connection's TCP close. Session.launch
    closes its own probe connection immediately before spawning us, so a
    fresh connect+ping can race that cleanup and time out. Retry the whole
    handshake with a short per-attempt timeout (mirroring Session.launch's
    own retry loop) and restore the normal operational timeout on success —
    the retries must fit inside _spawn_daemon's 10 s start deadline."""
    deadline = time.monotonic() + 8.0
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        mon = MonitorClient(port=port, timeout=1.5)
        try:
            mon.connect(deadline=1.5)
            mon.ping()
            mon.resume()                        # connect-stop answered; RUNNING
        except (ConnectionError, TimeoutError, OSError) as e:
            last_err = e
            mon.close()
            time.sleep(0.2)
            continue
        mon.timeout = 5.0                        # normal op/finish() timeout
        if mon._sock is not None:
            mon._sock.settimeout(5.0)
        return mon
    raise ConnectionError(
        f"daemon could not reach VICE monitor on port {port}: {last_err}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="c64lib.daemon")
    ap.add_argument("--name", required=True)
    ap.add_argument("--vice-port", type=int, required=True)
    ap.add_argument("--socket", required=True)
    a = ap.parse_args(argv)

    mon = _connect_vice(a.vice_port)

    try:
        os.unlink(a.socket)
    except FileNotFoundError:
        pass
    listen = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listen.bind(a.socket)
    listen.listen(1)
    print(f"c64 daemon up: session={a.name} vice_port={a.vice_port}", flush=True)
    try:
        PetDaemon(mon, listen, a.name).serve_forever()
    except Exception:
        traceback.print_exc()
        raise
    finally:
        try:
            os.unlink(a.socket)
        except FileNotFoundError:
            pass
        mon.close()


if __name__ == "__main__":
    main()
