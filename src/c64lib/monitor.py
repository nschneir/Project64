"""Socket client for the VICE binary monitor.

Connection-behavior contract (see spec §5 'stopped-state discipline'):
processing any monitor command leaves the emulated machine STOPPED. Callers
that want the machine running afterwards must call resume().
"""

from __future__ import annotations

import collections
import itertools
import socket
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .protocol import (
    CP_EXEC,
    Checkpoint,
    Command,
    ErrorCode,
    FrameDecoder,
    Response,
    ResponseType,
    advance_body,
    checkpoint_delete_body,
    checkpoint_set_body,
    checkpoint_toggle_body,
    condition_set_body,
    encode_command,
    memory_get_body,
    memory_set_body,
    parse_checkpoint,
    parse_display_get,
    parse_memory_get,
    parse_palette_get,
    parse_registers_available,
    parse_registers_get,
    parse_resource,
    registers_set_body,
    resource_get_body,
    resource_set_body,
)


@dataclass(frozen=True)
class StopInfo:
    pc: int | None
    checkpoint: int | None


class MonitorError(Exception):
    def __init__(self, command: int, error_code: int):
        try:
            name = ErrorCode(error_code).name
        except ValueError:
            name = f"{error_code:#04x}"
        super().__init__(f"VICE monitor error {name} for command {Command(command).name}")
        self.error_code = error_code


@runtime_checkable
class MonitorLike(Protocol):
    """What both monitor clients implement.

    `MonitorClient` (below) talks to VICE's binary monitor directly;
    `DaemonMonitorClient` forwards the same calls over the session daemon's
    RPC socket. Everything that takes a `mon` accepts either, and annotating
    the concrete class instead of this Protocol is what made the type checker
    reject every daemon-backed call site.

    It lives here, beside `MonitorClient`, because that class is the
    authoritative signature for every method below (the daemon client's
    equivalents are mostly unannotated) and `Checkpoint`/`StopInfo` are
    already in scope. Nothing imports it back into `daemon_client`, so no
    import cycle: Protocol conformance is structural, not declared.

    Deliberately excluded, because only one side has them: `connect`,
    `request` and `poll_events` are transport-level and meaningless over RPC;
    `run_until` and `status` are daemon-side shortcuts (callers reach them
    behind an `isinstance(mon, DaemonMonitorClient)` check).
    """

    def close(self) -> None: ...
    def ping(self) -> None: ...
    def memory_read(
        self, start: int, length: int, *, memspace: int = 0, bank: int = 0
    ) -> bytes: ...
    def memory_write(
        self, start: int, data: bytes, *, memspace: int = 0, bank: int = 0,
        side_effects: bool = False,
    ) -> None: ...
    def resume(self) -> None: ...
    def release(self) -> None: ...
    def registers(self) -> dict[str, int]: ...
    def set_register(self, name: str, value: int) -> None: ...
    def reset(self, hard: bool = False) -> None: ...
    def keyboard_feed(self, petscii: bytes) -> None: ...
    def display(self, full: bool = False) -> tuple[int, int, bytes]: ...
    def palette(self) -> list[tuple[int, int, int]]: ...
    def vice_info(self) -> str: ...
    def quit(self) -> None: ...
    def resource_get(self, name: str) -> str | int: ...
    def resource_set(self, name: str, value: str | int) -> None: ...
    def autostart(self, path: str | Path, run: bool = True) -> None: ...
    def checkpoint_set(
        self, start: int, end: int | None = None, *,
        op: int = CP_EXEC, stop: bool = True, temporary: bool = False,
    ) -> Checkpoint: ...
    def checkpoint_delete(self, number: int) -> None: ...
    def checkpoint_toggle(self, number: int, enabled: bool) -> None: ...
    def checkpoint_list(self) -> list[Checkpoint]: ...
    def condition_set(self, number: int, expr: str) -> None: ...
    def step(self, count: int = 1, over: bool = False) -> dict[str, int]: ...
    def finish(self) -> dict[str, int]: ...
    def wait_for_stop(self, timeout: float) -> StopInfo | None: ...


class MonitorClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 6502, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.events: collections.deque[Response] = collections.deque(maxlen=256)
        self._sock: socket.socket | None = None
        self._decoder = FrameDecoder()
        self._ids = itertools.count(1)
        self._pending: list[Response] = []

    def connect(self, deadline: float = 15.0) -> None:
        end = time.monotonic() + deadline
        last_err: Exception | None = None
        while time.monotonic() < end:
            try:
                self._sock = socket.create_connection(
                    (self.host, self.port), timeout=self.timeout
                )
                return
            except OSError as e:
                last_err = e
                time.sleep(0.1)
        raise ConnectionError(
            f"could not connect to VICE monitor at {self.host}:{self.port}: {last_err}"
        )

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def __enter__(self) -> MonitorClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _transact(
        self, command: int, body: bytes = b"", collect_type: int | None = None
    ) -> tuple[Response, list[Response]]:
        """Send a command; return (final response, same-rid intermediates).

        CHECKPOINT_LIST-style commands send intermediate responses (e.g. 0x11
        checkpoint infos) carrying the SAME request id before the final
        response whose type matches the command. collect_type gathers those.
        """
        assert self._sock is not None, "not connected"
        rid = next(self._ids)
        self._sock.sendall(encode_command(command, body, request_id=rid))
        collected: list[Response] = []
        deadline = time.monotonic() + self.timeout
        while True:
            for resp in list(self._pending):
                if resp.request_id != rid:
                    continue
                self._pending.remove(resp)
                if collect_type is not None and resp.response_type == collect_type \
                        and resp.response_type != command:
                    collected.append(resp)
                    continue
                if resp.error_code != ErrorCode.OK:
                    raise MonitorError(command, resp.error_code)
                return resp, collected
            if time.monotonic() > deadline:
                raise TimeoutError(f"no response to {Command(command).name}")
            data = self._sock.recv(65536)
            if not data:
                raise ConnectionError("VICE closed the monitor connection")
            for resp in self._decoder.feed(data):
                if resp.is_event:
                    self.events.append(resp)
                else:
                    self._pending.append(resp)

    def request(self, command: int, body: bytes = b"") -> Response:
        return self._transact(command, body)[0]

    # --- high-level operations -------------------------------------------

    def ping(self) -> None:
        self.request(Command.PING)

    def memory_read(
        self, start: int, length: int, *, memspace: int = 0, bank: int = 0
    ) -> bytes:
        body = memory_get_body(start, start + length - 1, memspace, bank)
        return parse_memory_get(self.request(Command.MEMORY_GET, body).body)

    def memory_write(
        self, start: int, data: bytes, *, memspace: int = 0, bank: int = 0,
        side_effects: bool = False,
    ) -> None:
        self.request(Command.MEMORY_SET,
                     memory_set_body(start, data, memspace, bank,
                                     side_effects=side_effects))

    def resume(self) -> None:
        # Once running, any queued stop-state event (e.g. the unsolicited
        # STOPPED VICE emits when a client connects) is stale; drop it so a
        # subsequent wait_for_stop() only sees events from this resume onward.
        self.events.clear()
        self.request(Command.EXIT)

    def release(self) -> None:
        """Restore-prior-state verb. On a direct connection there is no held
        state to restore, so it simply resumes (pre-daemon behavior); the
        session daemon's proxy overrides this with real state restoration."""
        self.resume()

    def _register_map(self) -> dict[int, str]:
        if not hasattr(self, "_regmap"):
            body = self.request(Command.REGISTERS_AVAILABLE, b"\x00").body
            self._regmap = parse_registers_available(body)
        return self._regmap

    def registers(self) -> dict[str, int]:
        regmap = self._register_map()
        raw = parse_registers_get(self.request(Command.REGISTERS_GET, b"\x00").body)
        return {regmap[i].upper(): v for i, v in raw.items() if i in regmap}

    def set_register(self, name: str, value: int) -> None:
        regmap = self._register_map()
        by_name = {n.upper(): i for i, n in regmap.items()}
        reg_id = by_name[name.upper()]  # KeyError on unknown name is the contract
        self.request(Command.REGISTERS_SET, registers_set_body({reg_id: value}))

    def reset(self, hard: bool = False) -> None:
        self.request(Command.RESET, b"\x01" if hard else b"\x00")

    def keyboard_feed(self, petscii: bytes) -> None:
        for i in range(0, len(petscii), 200):
            chunk = petscii[i : i + 200]
            self.request(Command.KEYBOARD_FEED, bytes([len(chunk)]) + chunk)

    def display(self, full: bool = False) -> tuple[int, int, bytes]:
        # body: use_vic flag (ignored for the C64), format 0 = indexed 8bpp
        return parse_display_get(
            self.request(Command.DISPLAY_GET, b"\x00\x00").body, full=full)

    def palette(self) -> list[tuple[int, int, int]]:
        return parse_palette_get(self.request(Command.PALETTE_GET, b"\x00").body)

    def vice_info(self) -> str:
        body = self.request(Command.VICE_INFO).body
        n = body[0]
        return ".".join(str(b) for b in body[1 : 1 + n]).rstrip(".0") or "0"

    def quit(self) -> None:
        try:
            self.request(Command.QUIT)
        except (ConnectionError, TimeoutError, OSError):
            pass  # VICE may exit before replying

    def resource_get(self, name: str) -> str | int:
        return parse_resource(
            self.request(Command.RESOURCE_GET, resource_get_body(name)).body
        )

    def resource_set(self, name: str, value: str | int) -> None:
        self.request(Command.RESOURCE_SET, resource_set_body(name, value))

    def autostart(self, path, run: bool = True) -> None:
        """Load-and-optionally-RUN a program file via VICE's autostart.

        VICE mounts the file as a virtual drive and types LOAD/RUN itself;
        pass an absolute path. Loading takes a few emulated seconds.
        """
        name = str(path).encode()
        body = struct.pack("<BHB", int(run), 0, len(name)) + name
        self.request(Command.AUTOSTART, body)

    # --- checkpoints and stepping -----------------------------------------

    def checkpoint_set(
        self, start: int, end: int | None = None, *,
        op: int = CP_EXEC, stop: bool = True, temporary: bool = False,
    ) -> Checkpoint:
        body = checkpoint_set_body(
            start, end if end is not None else start,
            op=op, stop=stop, temporary=temporary,
        )
        return parse_checkpoint(self.request(Command.CHECKPOINT_SET, body).body)

    def checkpoint_delete(self, number: int) -> None:
        self.request(Command.CHECKPOINT_DELETE, checkpoint_delete_body(number))

    def checkpoint_toggle(self, number: int, enabled: bool) -> None:
        self.request(Command.CHECKPOINT_TOGGLE, checkpoint_toggle_body(number, enabled))

    def checkpoint_list(self) -> list[Checkpoint]:
        _final, infos = self._transact(
            Command.CHECKPOINT_LIST, collect_type=Command.CHECKPOINT_GET
        )
        return [parse_checkpoint(r.body) for r in infos]

    def condition_set(self, number: int, expr: str) -> None:
        self.request(Command.CONDITION_SET, condition_set_body(number, expr))

    def step(self, count: int = 1, over: bool = False) -> dict[str, int]:
        """Advance N instructions (synchronous); machine stays stopped."""
        self.request(Command.ADVANCE_INSTRUCTIONS, advance_body(count, over))
        return self.registers()

    def finish(self) -> dict[str, int]:
        """Run until the current subroutine returns; machine stays stopped."""
        self.request(Command.EXECUTE_UNTIL_RETURN)
        self.wait_for_stop(timeout=self.timeout)
        return self.registers()

    # --- events -------------------------------------------------------------

    def poll_events(self, timeout: float, *, first: bool = False) -> list[Response]:
        """Return queued events plus any that arrive within timeout.

        first=True returns as soon as at least one event is in hand instead
        of listening out the whole window — the wait-for-stop fast path.
        Without it every checkpoint arrival costs a full timeout slice even
        though the event is often already queued (a hit fires while the
        RESUME transaction is still reading, so _transact stashes it in
        self.events before wait_for_stop ever runs)."""
        seen = list(self.events)
        self.events.clear()
        assert self._sock is not None, "not connected"
        deadline = time.monotonic() + timeout
        while not (first and seen) and time.monotonic() < deadline:
            self._sock.settimeout(max(0.05, deadline - time.monotonic()))
            try:
                data = self._sock.recv(65536)
            except TimeoutError:
                break
            if not data:
                raise ConnectionError("VICE closed the monitor connection")
            for resp in self._decoder.feed(data):
                if resp.is_event:
                    seen.append(resp)
                else:
                    self._pending.append(resp)
        self._sock.settimeout(self.timeout)
        return seen

    def wait_for_stop(self, timeout: float) -> StopInfo | None:
        """Wait for a STOPPED event; report the hit checkpoint if one fired."""
        deadline = time.monotonic() + timeout
        checkpoint = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            for ev in self.poll_events(min(remaining, 0.5), first=True):
                if ev.response_type == Command.CHECKPOINT_GET and ev.body[4]:
                    checkpoint = int.from_bytes(ev.body[0:4], "little")
                if ev.response_type == ResponseType.STOPPED:
                    (pc,) = struct.unpack_from("<H", ev.body)
                    return StopInfo(pc=pc, checkpoint=checkpoint)
