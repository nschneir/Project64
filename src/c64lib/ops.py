"""Shared high-level operations used by both the CLI and the MCP server.

One implementation of the wait/until primitives and symbol plumbing so the
two front ends cannot drift.
"""

from __future__ import annotations

import operator
import re
import time
from collections import deque

from .daemon_client import DaemonMonitorClient
from .protocol import CP_EXEC
from .screen import read_screen_text, screen_base
from .symbols import load_labels, nearest, resolve
from .text import ascii_to_petscii

#: comparisons a memory wait accepts, longest spelling first so the regex
#: below prefers '>=' over '>' and '!=' over a bare '='.
MEM_OPS = {
    ">=": operator.ge, "<=": operator.le, "!=": operator.ne,
    "==": operator.eq, "=": operator.eq, ">": operator.gt, "<": operator.lt,
}

_MEM_COND = re.compile(r"^\s*(?P<addr>.+?)\s*(?P<op>>=|<=|!=|==|=|>|<)\s*"
                       r"(?P<value>\S.*?)\s*$")

#: how a YAML `wait: {mem: ...}` step spells each comparison. Symbol-free
#: names, matching the word-key style the `assert` step already uses.
MEM_COND_KEYS = {"equals": "=", "not_equals": "!=", "above": ">",
                 "at_least": ">=", "below": "<", "at_most": "<="}

#: the operator menu, for error messages — one spelling of each comparison.
MEM_OPS_HELP = "= != > >= < <="


def split_mem_condition(cond: str) -> tuple[str, str, str]:
    """Split a memory condition into (address, operator, value), all still
    text — the caller resolves the address and parses the number, because
    only it knows the session and label table.

    Raises ValueError when no comparison operator is present; splitting
    before resolving is what keeps a typo like '251>0' reported as a bad
    condition rather than as an unknown symbol named '251>0'.
    """
    m = _MEM_COND.match(cond)
    if not m:
        raise ValueError(
            f"bad memory condition {cond!r}; use ADDR<op>VALUE where <op> is "
            f"one of {MEM_OPS_HELP} (e.g. '$fb>=20', '@6,0=20')")
    return m.group("addr"), m.group("op"), m.group("value")


#: the current-key byte the IRQ keyboard scanner maintains (SFDX, $CB):
#: the keyboard-matrix code of the key held right now, 64 = no key.
KEYDOWN_ADDR = 0xCB

#: C64 keyboard-matrix codes (the values SCNKEY leaves in $CB), from the
#: published matrix table. Lowercase only — the matrix has no case.
MATRIX_CODES = {
    "\n": 1,
    "3": 8, "w": 9, "a": 10, "4": 11, "z": 12, "s": 13, "e": 14,
    "5": 16, "r": 17, "d": 18, "6": 19, "c": 20, "f": 21, "t": 22, "x": 23,
    "7": 24, "y": 25, "g": 26, "8": 27, "b": 28, "h": 29, "u": 30, "v": 31,
    "9": 32, "i": 33, "j": 34, "0": 35, "m": 36, "k": 37, "o": 38, "n": 39,
    "+": 40, "p": 41, "l": 42, "-": 43, ".": 44, ":": 45, "@": 46, ",": 47,
    "*": 49, ";": 50, "=": 53, "/": 55,
    "1": 56, "2": 59, " ": 60, "q": 62,
}


def parse_number(s) -> int:
    s = str(s).strip()
    if s.startswith("$"):
        return int(s[1:], 16)
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def parse_ref(labels: dict[str, int], ref, *, screen_base: int | None = None,
              screen_width: int | None = None) -> int:
    """Address forms: $hex / 0xhex / decimal / symbol, plus:

    - `base+N` / `base-N` — a numeric or symbol base with an offset
      (e.g. `alienX+49`, `$0400+40`). Only applied when the tail parses
      as a number, so hyphenated symbol names still resolve whole.
    - `@row,col` — a screen cell, resolved against the session's screen
      geometry (callers pass it from the machine profile).
    """
    r = str(ref).strip()
    if r.startswith("@"):
        if screen_base is None or screen_width is None:
            raise ValueError(
                f"{r!r}: @row,col needs a session's screen geometry — use it "
                "where a running session provides the model")
        try:
            row_s, col_s = r[1:].split(",", 1)
            row, col = parse_number(row_s), parse_number(col_s)
        except ValueError:
            raise ValueError(f"{r!r}: expected @row,col, e.g. @23,18") from None
        if not 0 <= row <= 24:
            raise ValueError(f"{r!r}: row {row} outside 0-24")
        if not 0 <= col < screen_width:
            raise ValueError(f"{r!r}: col {col} outside 0-{screen_width - 1}")
        return screen_base + row * screen_width + col
    base_err: KeyError | None = None
    for sign, sep in ((1, "+"), (-1, "-")):
        if sep in r[1:]:
            base_s, off_s = r.rsplit(sep, 1)
            try:
                off = parse_number(off_s)
            except ValueError:
                continue                 # not an offset (hyphenated name etc.)
            try:
                return parse_ref(labels, base_s) + sign * off
            except KeyError as e:
                base_err = e             # remember: report the SYMBOL below
            except ValueError:
                pass                     # whole string may still be a symbol
    if r.startswith(("$", "0x", "0X")) or r.isdigit():
        return parse_number(r)
    try:
        return resolve(labels, r)  # KeyError with candidates on unknown symbol
    except KeyError:
        if base_err is not None:
            raise base_err from None     # 'dots+82' → unknown symbol 'dots'
        raise


def staleness(session) -> list[str]:
    """Source files (from the last load's dependency list) modified since
    the load. Non-empty means the emulator is running an out-of-date
    program — the trap the Ms. Muncher dogfood fell into."""
    import os
    if not session.loaded_prg or not session.loaded_deps:
        return []
    out = []
    for d in session.loaded_deps:
        try:
            if os.path.getmtime(d) > session.loaded_at:
                out.append(d)
        except OSError:
            out.append(d)               # vanished source counts as stale
    return out


def live_screen_base(session) -> int:
    """The current screen RAM base read from the running machine's VIC/CIA2
    registers (state-preserving). Callers resolving `@row,col` use this so
    relocated screens keep working."""
    with session.monitor() as mon:
        try:
            return screen_base(mon)
        finally:
            mon.release()


def session_labels(s) -> dict[str, int]:
    if isinstance(s.labels, str) and s.labels:
        try:
            return load_labels(s.labels)
        except OSError:
            return {}
    return {}


def pc_symbol(labels: dict[str, int], regs: dict[str, int]) -> str | None:
    pc = regs.get("PC")
    if pc is None or not labels:
        return None
    hit = nearest(labels, pc)
    if hit is None:
        return None
    name, off = hit
    return f"{name}+{off}" if off else name


#: Static address-space regions, in the order they are tested. Only the
#: banked-ROM/IO windows are named — a PC in RAM says nothing on its own.
_PC_REGIONS = (
    (0xA000, 0xBFFF, "BASIC ROM"),
    (0xD000, 0xDFFF, "I/O"),
    (0xE000, 0xFFFF, "KERNAL ROM"),
)


def pc_region(pc: int | None) -> str | None:
    """Name the ROM/IO region `pc` sits in, or None for RAM.

    The point is a bare `PC=e5d1` reading as "somewhere in the KERNAL"
    without a label file or a memory map to hand. Which bank is actually
    switched in at that address is a separate question ($01) — this is the
    address space, which is what a stopped PC is usually asking about."""
    if pc is None:
        return None
    return next((name for lo, hi, name in _PC_REGIONS if lo <= pc <= hi), None)


def _screen(session) -> str:
    with session.monitor() as mon:
        try:
            return read_screen_text(mon, session.profile)
        finally:
            mon.release()


def wait_for_text(session, text: str, timeout: float = 30.0,
                  since: bool = False) -> dict:
    """Block until `text` is on screen. With since=True, block until it
    appears MORE times than it already does right now — the way to wait for
    a repeated prompt or verdict without matching the stale one above it."""
    start = time.monotonic()
    deadline = start + timeout
    last: str | None = None
    baseline = 0
    if since:
        last = _screen(session)            # only --since needs a baseline read
        baseline = last.count(text)
    while time.monotonic() < deadline:
        # read at the TOP: every read is checked before the loop can exit on
        # the deadline, so a match landing on the final poll is never dropped.
        last = _screen(session)
        if last.count(text) > baseline:
            return {"fired": "text", "elapsed": round(time.monotonic() - start, 3)}
        time.sleep(0.4)
    if last is None:                        # timeout<=0 and no baseline read
        last = _screen(session)             # the contract: report a screen
    return {"fired": None, "timeout": timeout, "screen": last}


def wait_for_mem(session, addr: int, value: int, timeout: float = 30.0,
                 op: str = "=") -> dict:
    """Block until the byte at `addr` compares to `value` under `op`.

    `op` is one of MEM_OPS. Equality is the common case, but a counter that
    the machine races past between polls cannot be caught with '=' at all —
    wait on '>=' instead. Polling is inherent: a value that holds for only
    a few frames can slip between polls whatever the operator, so for a
    transition use a store watchpoint and wait_for_break.
    """
    try:
        cmp_ = MEM_OPS[op]
    except KeyError:
        raise ValueError(f"unknown comparison {op!r}; use one of "
                         f"{MEM_OPS_HELP}") from None
    start = time.monotonic()
    deadline = start + timeout
    val = None
    while time.monotonic() < deadline:
        with session.monitor() as mon:
            try:
                val = mon.memory_read(addr, 1)[0]
            finally:
                mon.release()
        if cmp_(val, value):
            return {"fired": "mem", "elapsed": round(time.monotonic() - start, 3)}
        time.sleep(0.4)
    return {"fired": None, "timeout": timeout, "last_value": val,
            "op": op, "value": value}


#: The KERNAL direct-mode input loop, MEASURED rather than quoted: 40
#: `c64 reg` samples at a fresh READY. prompt on live x64sc (2026-07-29) all
#: landed in $E5CD-$E5D4 except one at $EA3A (the IRQ handler, caught in
#: transit). Sampling again after a program ran to completion (12/12) and
#: after a ?SYNTAX ERROR (12/12) gave the same span; a wedged `10 GOTO 10`
#: gave 0/12 (it scatters over $A7xx-$A9xx, CHRGET at $0073, $FFE1).
#: The loop head is `INLOOP` in the ROM label DB (data/rom_labels/basic2.lbl),
#: so `c64 disasm INLOOP 8` shows the code this range covers.
IDLE_PC_RANGE = (0xE5CD, 0xE5D4)

#: How many PCs a timeout hands back — enough to show a loop's shape.
_IDLE_PC_WINDOW = 8


def wait_for_idle(session, timeout: float = 30.0, samples: int = 3,
                  interval: float = 0.1) -> dict:
    """Block until the machine is idle: the PC observed inside the KERNAL
    direct-mode input loop (IDLE_PC_RANGE) on `samples` CONSECUTIVE reads.

    That is the machine-level reading of "the program has finished or
    errored; BASIC is back at direct mode" — the thing `--text "READY."`
    cannot ask for, because the reset banner already says READY. Consecutive
    reads are the whole trick: the IRQ handler transits ROM, so a single
    sample landing in the range proves nothing (measured at roughly 1 read
    in 40 at an idle prompt).

    Two things it deliberately cannot distinguish, both because the KERNAL
    routine is literally the same code: a program blocked on INPUT/GET reads
    as idle, and so does a machine sitting at a prompt it reached by never
    starting your program at all. A timeout is the useful complement — the
    machine ran the whole time without ever reaching direct mode, i.e. it is
    still running or wedged — and returns the PCs it saw, which name the
    loop. Machine state is preserved either way."""
    start = time.monotonic()
    deadline = start + timeout
    lo, hi = IDLE_PC_RANGE
    recent: deque[int | None] = deque(maxlen=max(samples, _IDLE_PC_WINDOW))
    run = 0
    while True:
        with session.monitor() as mon:
            try:
                pc = mon.registers().get("PC")
            finally:
                mon.release()          # restore prior run/stop state: a poll
                                       # must not itself move the machine
        recent.append(pc)
        run = run + 1 if pc is not None and lo <= pc <= hi else 0
        if run >= samples:
            return {"fired": "idle", "pc": pc,
                    "elapsed": round(time.monotonic() - start, 3)}
        # checked AFTER the read, so a zero/expired timeout still reports
        # what the machine was actually doing (the wait_for_text contract)
        if time.monotonic() >= deadline:
            return {"fired": None, "timeout": timeout,
                    "last_pcs": [pc for pc in recent if pc is not None]}
        time.sleep(interval)


def wait_for_break(session, timeout: float = 30.0,
                   number: int | None = None) -> dict:
    """Checkpoint-hit wait, robust under warp.

    The hit flag on a stopped checkpoint is the durable source of truth:
    a stop=True checkpoint freezes the machine until a client resumes it,
    and the flag is visible in CHECKPOINT_LIST even when the STOPPED event
    was lost (Plan 03 verified; the connect-stop/resume race destroys queued
    events, which is what made event-only waiting flaky under --warp).
    The STOPPED event is kept as a fast-path only; every loop iteration
    re-polls the flags, so a missed event costs at most one poll slice.
    Timeout leaves the machine RUNNING (the documented contract)."""
    start = time.monotonic()
    deadline = start + timeout

    def _fired(mon, number, pc=None):
        regs = mon.registers()
        return {"fired": "break", "checkpoint": number,
                "pc": pc if pc is not None else regs.get("PC"),
                "registers": regs,
                "elapsed": round(time.monotonic() - start, 3)}

    with session.monitor() as mon:
        while True:
            hit = next((ck for ck in mon.checkpoint_list()
                        if ck.hit and (number is None or ck.number == number)),
                       None)
            if hit is not None:
                return _fired(mon, hit.number)          # machine stays stopped
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                mon.resume()                             # timeout: leave it running
                return {"fired": None, "timeout": timeout}
            mon.resume()                                 # the list stopped the machine
            info = mon.wait_for_stop(min(1.0, remaining))
            if (info is not None and info.checkpoint is not None
                    and (number is None or info.checkpoint == number)):
                return _fired(mon, info.checkpoint, info.pc)
            # Slice elapsed, or a STOPPED with no checkpoint id (e.g. another
            # client's connect-stop): loop — the flag poll decides.


#: default trap for call_routine's fake return address — the BASIC link
#: bytes at the start of program text, never machine-executed.
CALL_TRAP = 0x0400


def call_routine(session, addr: int, a: int | None = None, x: int | None = None,
                 y: int | None = None, timeout: float = 30.0,
                 trap: int = CALL_TRAP) -> dict:
    """JSR one routine in isolation and stop when it returns.

    Emulates `JSR addr`: pushes a fake return address (trap-1, matching
    real JSR semantics) on the 6502 stack, optionally sets A/X/Y, sets PC
    to the routine, and runs until an exec checkpoint at the trap fires —
    i.e. until the routine's own RTS. The machine is left STOPPED at the
    trap so registers and memory can be asserted; on timeout the
    checkpoint is removed and the machine left running.

    Returns {"fired": bool, "registers": regs-or-None, "trap": trap}.
    This is the unit-test primitive: poke inputs, call, assert outputs.
    """
    deadline = time.monotonic() + timeout
    with session.monitor() as mon:
        regs = mon.registers()          # also stops the machine
        sp = regs["SP"]
        ret = (trap - 1) & 0xFFFF
        mon.memory_write(0x0100 + sp, bytes([ret >> 8]))
        mon.memory_write(0x0100 + ((sp - 1) & 0xFF), bytes([ret & 0xFF]))
        mon.set_register("SP", (sp - 2) & 0xFF)
        for name, val in (("A", a), ("X", x), ("Y", y)):
            if val is not None:
                mon.set_register(name, val)
        mon.set_register("PC", addr)
        ck = mon.checkpoint_set(trap, op=CP_EXEC, temporary=False)
        mon.resume()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                mon.checkpoint_delete(ck.number)
                mon.resume()
                return {"fired": False, "registers": None, "trap": trap}
            info = mon.wait_for_stop(min(1.0, remaining))
            if info is not None and info.checkpoint == ck.number:
                break
            cur = next((c for c in mon.checkpoint_list()
                        if c.number == ck.number), None)
            if cur is not None and (cur.hit or cur.hit_count > 0):
                break                    # durable flag caught a lost event
            mon.resume()                 # the list stopped the machine
        out = mon.registers()
        mon.checkpoint_delete(ck.number)
        return {"fired": True, "registers": out, "trap": trap}


def run_until(session, addr: int, timeout: float = 30.0, count: int = 1) -> dict:
    """Run until addr is executed `count` times; the machine stays stopped at
    the final arrival ("frame stepping" when addr is a main-loop label).

    With a session daemon the whole count loop runs daemon-side in a single
    RPC (per-hit round-trips made large counts ~0.5 s per arrival); a
    pre-run_until daemon or a direct connection takes the client-side loop.
    Returns {"registers": regs-or-None, "reached": k, "count": count};
    registers is None on timeout, in which case the checkpoint is removed
    and the machine is left running."""
    with session.monitor() as mon:
        if isinstance(mon, DaemonMonitorClient):
            try:
                return mon.run_until(addr, timeout, count)
            except ValueError:
                pass          # old daemon: unknown method — do it client-side
        return _run_until_client(mon, addr, timeout, count)


def _run_until_client(mon, addr: int, timeout: float, count: int) -> dict:
    """The pre-daemon-verb loop: one resume + wait round-trip per arrival,
    with the same durable hit/hit_count fallback as wait_for_break."""
    deadline = time.monotonic() + timeout
    ck = mon.checkpoint_set(addr, op=CP_EXEC, temporary=False)
    for i in range(count):
        mon.resume()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                mon.checkpoint_delete(ck.number)
                mon.resume()
                return {"registers": None, "reached": i, "count": count}
            info = mon.wait_for_stop(min(1.0, remaining))
            if info is not None and info.checkpoint == ck.number:
                break
            cur = next((c for c in mon.checkpoint_list()
                        if c.number == ck.number), None)
            if cur is not None and (cur.hit or cur.hit_count > i):
                break                        # durable flag caught it
            mon.resume()                     # the list stopped the machine
    regs = mon.registers()
    mon.checkpoint_delete(ck.number)
    return {"registers": regs, "reached": count, "count": count}


#: The only backslash sequences `key type` decodes. Deliberately tiny: a
#: shell single-quotes or double-quotes the argument, so `"\n"` arrives as
#: the two characters '\' and 'n' and would otherwise be typed literally.
_TYPE_ESCAPES = {"n": "\n", "\\": "\\"}


def _decode_type_escapes(text: str) -> str:
    """Decode `\\n` to a newline and `\\\\` to one backslash; leave every
    other backslash pair alone (`\\q` stays two characters). Real newlines
    pass through untouched."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in _TYPE_ESCAPES:
            out.append(_TYPE_ESCAPES[text[i + 1]])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def key_type(session, text: str) -> dict:
    """Type TEXT into the keyboard buffer. A literal `\\n` in TEXT is
    decoded to RETURN (as a real newline already is) and `\\\\` to one
    backslash; no other escape is interpreted. ValueError from unmappable
    characters propagates to the caller."""
    petscii = ascii_to_petscii(_decode_type_escapes(text))
    with session.monitor() as mon:
        try:
            mon.keyboard_feed(petscii)
        finally:
            mon.release()
    return {"typed_chars": len(petscii)}


def key_hold(session, key: str, at_addr: int, frames: int = 1,
             timeout: float = 30.0) -> dict:
    """Hold KEY down for `frames` game ticks: write its keyboard-matrix
    code to $CB, run to at_addr, repeat — the machine ends STOPPED at
    at_addr.

    This is the poke-$CB debugger protocol as one operation: the IRQ
    keyboard scan (SCNKEY) rewrites $CB every tick (64 = no key), so the
    code must be re-poked before each frame. Programs reading the held
    key from $CB (or via GETIN after the scan decodes it) see the key.
    For a fully deterministic first frame, be stopped at at_addr already
    (run_until once); mid-flight the first poke can race the next IRQ.

    Returns {"frames": done, "requested": frames, "registers": regs};
    registers is None if a frame timed out (machine left RUNNING, same
    contract as run_until)."""
    k = " " if key.lower() == "space" else key
    if len(k) != 1:
        raise ValueError(f"key must be one character or 'space', got {key!r}")
    try:
        code = bytes([MATRIX_CODES[k.lower()]])
    except KeyError:
        raise ValueError(f"no matrix code for key {key!r}") from None
    out = {"registers": None}
    for i in range(frames):
        with session.monitor() as mon:
            mon.memory_write(KEYDOWN_ADDR, code)
        out = run_until(session, at_addr, timeout=timeout, count=1)
        if out["registers"] is None:
            return {"frames": i, "requested": frames, "registers": None}
    return {"frames": frames, "requested": frames, "registers": out["registers"]}


def find_bytes(mon, start: int, length: int, pattern: bytes,
               limit: int = 256) -> tuple[list[int], bool]:
    """Addresses of every occurrence of `pattern` in [start, start+length),
    clamped to the 64 KB space. Returns (matches, truncated); truncated is
    True when `limit` clipped the list. One bulk read; does not resume."""
    n = max(0, min(length, 0x10000 - start))
    data = mon.memory_read(start, n)
    matches: list[int] = []
    truncated = False
    i = data.find(pattern)
    while i != -1:
        if len(matches) >= limit:
            truncated = True
            break
        matches.append(start + i)
        i = data.find(pattern, i + 1)
    return matches, truncated


def clear_checkpoints(mon, include_mask: int, exclude_mask: int = 0) -> list[int]:
    """Delete every checkpoint whose op matches include_mask (and none of
    exclude_mask); returns the removed checkpoint ids."""
    removed = []
    for ck in mon.checkpoint_list():
        if (ck.op & include_mask) and not (ck.op & exclude_mask):
            mon.checkpoint_delete(ck.number)
            removed.append(ck.number)
    return removed


def machine_state(session) -> str:
    """'running' / 'stopped' via the session daemon; 'unknown' without one
    (a direct monitor connection stops the CPU, so the question is only
    answerable via the daemon). Never raises."""
    if not getattr(session, "socket", None):
        return "unknown"
    try:
        with session.monitor() as mon:
            status = getattr(mon, "status", None)
            return status() if status else "unknown"
    except (ConnectionError, TimeoutError, OSError):
        return "unknown"
