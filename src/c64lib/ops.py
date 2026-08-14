"""Shared high-level operations used by both the CLI and the MCP server.

One implementation of the wait/until primitives, symbol and ref plumbing,
keyboard typing, sprite and EasyFlash state reads, cart reboot and build
dispatch, so the two front ends cannot drift.

Also the handful of message fragments that are findings rather than wording —
`RUNAWAY_ROUTINE`, `profile_hazard`, `key_state_note`,
`stopped_wait_diagnosis`. Each front end still renders its own message around
them and passes in its own spelling of any command it names, per the house
rule; what lives here is the part that would be a divergence if it drifted.
"""

from __future__ import annotations

import operator
import re
import time
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path

from .basic import BasicError, tokenize
from .build import RESERVED_AREA_NAMES, Area, BuildError, build_asm
from .cartridge import EF_MODES
from .daemon_client import DaemonMonitorClient
from .protocol import CP_EXEC
from .romdoc import rom_labels
from .screen import read_screen_text, screen_base
from .session import Session, SessionError
from .sprites import SpriteState, read_sprite_block, read_sprite_states, sprite_image
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

#: the value SCNKEY leaves in $CB when no key is down — what a hold pokes
#: to let the key go again.
KEY_NONE = 64

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


def _area_spelling(a: Area) -> str:
    """The NAME=START:SIZE form, for error messages that quote the area back."""
    return f"{a.name}=${a.start:04X}:${a.size:X}"


def parse_areas(values, basic_start: int) -> list[Area]:
    """Parse `--area NAME=START:SIZE` tokens into sorted, checked `Area`s.

    `basic_start` is required, not defaulted: every caller already has a
    profile and passes `profile.basic_start`, so a C64 literal here would be
    a second, unowned copy of a profile field — one that agrees with every
    shipped profile today and would quietly stop agreeing the first time a
    machine with another load address ships. The load address decides which
    areas are rejected as sitting inside the program, so the wrong one
    rejects a legal area or accepts an overlapping one.

    Every rejection here is one ld65 would either accept and mis-link, or
    reject in terms that name its own generated config rather than the flag
    the user typed. The gap check is the load-bearing one: a `.prg` is a flat
    file, so a hole between two areas would shift everything above it down by
    the size of the hole and land nothing where it was asked for.
    """
    areas: list[Area] = []
    for raw in values:
        token = str(raw).strip()
        name, sep, rest = token.partition("=")
        start_s, colon, size_s = rest.partition(":")
        if not (sep and colon and name):
            raise ValueError(f"--area needs NAME=START:SIZE, got {token!r}")
        try:
            start, size = parse_number(start_s), parse_number(size_s)
        except ValueError:
            raise ValueError(
                f"--area needs NAME=START:SIZE, got {token!r}") from None
        if name.upper() in RESERVED_AREA_NAMES:
            listed = (", ".join(RESERVED_AREA_NAMES[:-1])
                      + f" and {RESERVED_AREA_NAMES[-1]}")
            raise ValueError(
                f"--area name {name!r} is reserved — {listed} cannot be reused")
        area = Area(name, start, size)
        if size == 0:
            raise ValueError(f"--area {_area_spelling(area)} has size 0")
        if start <= basic_start:
            raise ValueError(
                f"--area {name} starts at ${start:04X}, at or below the load "
                f"address ${basic_start:04X} — an area must sit above the program")
        areas.append(area)
    areas.sort(key=lambda a: a.start)
    for below, above in zip(areas, areas[1:], strict=False):
        end = below.start + below.size
        if end > above.start:
            raise ValueError(
                f"--area {above.name} starts at ${above.start:04X}, inside "
                f"--area {_area_spelling(below)} which ends at ${end:04X}")
        if end < above.start:
            raise ValueError(
                f"--area {_area_spelling(below)} leaves a "
                f"${above.start - end:04X}-byte gap before --area "
                f"{above.name} at ${above.start:04X} — a .prg is a flat file, "
                f"so raise {below.name}'s size to "
                f"${above.start - below.start:X} or move {above.name} down")
    return areas


def parse_byte_values(tokens) -> bytes:
    """Coerce CLI byte tokens to bytes, naming the one that is wrong.

    Splits whitespace *inside* each token first: a shell variable holding
    "0 0 1 4 9 0" reaches the CLI as one argument (zsh does not word-split
    unquoted expansions), and that is a byte list, not a parse error.
    The wording mirrors disk.block_bytes for the same reason that helper
    exists: the bare int()/bytes() errors never say WHICH value was bad.
    """
    toks = [t for tok in tokens for t in str(tok).split()]
    if not toks:
        raise ValueError("no byte values given")
    out = bytearray()
    for i, t in enumerate(toks):
        try:
            v = parse_number(t)
        except ValueError:
            raise ValueError(
                f"byte {i} is {t!r}, not a number ($hex/0x/decimal)") from None
        if not 0 <= v <= 255:
            raise ValueError(f"byte {i} is {v}, out of range for a byte (0-255)")
        out.append(v)
    return bytes(out)


#: Color RAM is hardwired at $D800 on every C64: the VIC bank ($DD00) and
#: $D018 relocate the screen, never the color matrix. Reads are 4-bit —
#: the high nybble is open bus — so comparisons must mask with $0F.
COLOR_RAM_BASE = 0xD800


def parse_ref(labels: dict[str, int], ref, *, screen_base: int | None = None,
              screen_width: int | None = None) -> int:
    """Address forms: $hex / 0xhex / decimal / symbol, plus:

    - `base+N` / `base-N` — a numeric or symbol base with an offset
      (e.g. `alienX+49`, `$0400+40`). Only applied when the tail parses
      as a number, so hyphenated symbol names still resolve whole.
    - `@row,col` — a screen cell, resolved against the session's screen
      geometry (callers pass it from the machine profile).
    - `@@row,col` — the same cell in color RAM. The base is the hardwired
      $D800 (the screen relocates; the color matrix does not). Color RAM
      reads back 4-bit — mask comparisons with $0F.
    """
    r = str(ref).strip()
    if r.startswith("@"):
        color = r.startswith("@@")
        body = r[2:] if color else r[1:]
        if screen_base is None or screen_width is None:
            raise ValueError(
                f"{r!r}: @row,col/@@row,col needs a session's screen geometry "
                "— use it where a running session provides the model")
        try:
            row_s, col_s = body.split(",", 1)
            row, col = parse_number(row_s), parse_number(col_s)
        except ValueError:
            raise ValueError(
                f"{r!r}: expected @row,col (screen RAM) or @@row,col "
                "(color RAM), e.g. @23,18") from None
        if not 0 <= row <= 24:
            raise ValueError(f"{r!r}: row {row} outside 0-24")
        if not 0 <= col < screen_width:
            raise ValueError(f"{r!r}: col {col} outside 0-{screen_width - 1}")
        base = COLOR_RAM_BASE if color else screen_base
        return base + row * screen_width + col
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


def all_labels(session) -> dict[str, int]:
    """The full symbol table for a session: ROM labels first, session labels
    on top.

    The order is the contract. A PC parked in the KERNAL is named even with no
    label file, which is the case you are in when a run has fallen off the
    rails; and a program's own label for an address it shares with the ROM
    wins, because that is the name its author is reading. This is the lookup
    `reg`/`c64_reg_get` and `rom disasm`/`c64_rom_disasm` build.
    """
    return {**rom_labels(session.profile.basic_version), **session_labels(session)}


def session_ref(session, ref, labels: dict[str, int] | None = None) -> int:
    """parse_ref with the session's screen geometry so @row,col works —
    against the LIVE screen base (relocation-aware). `labels=None` reads
    the session's own label file.

    The live base costs a monitor round trip, so it is read only when the
    ref actually names a cell. Raises KeyError/ValueError exactly as
    parse_ref does: presentation belongs to the front ends."""
    if labels is None:
        labels = session_labels(session)
    p = session.profile
    base = live_screen_base(session) if "@" in str(ref) else p.screen_addr
    return parse_ref(labels, ref, screen_base=base, screen_width=p.screen_cols)


def disk_labels_path(image) -> Path | None:
    """The label file a disk image implies, or None (silently).

    A sibling `IMAGE.lbl` of the same stem wins — the convention `c64 run`
    uses for a .crt. Failing that, the `c64 disk build` convention: the
    image's FIRST directory entry is what autostart LOAD"*",8,1 runs, and
    build keeps its labels as `IMAGE.<cbm-name>.lbl` beside the image.
    Never raises: no c1541, an unreadable image, or an empty directory all
    mean "no symbols", same as no label file at all.
    """
    img = Path(image)
    lbl = img.with_suffix(".lbl")
    if lbl.exists():
        return lbl
    from . import disk
    try:
        files = disk.list_files(img)["files"]
    except (disk.DiskError, OSError, KeyError):
        return None
    if files:
        cand = img.parent / f"{img.stem}.{files[0]['name']}.lbl"
        if cand.exists():
            return cand
    return None


def attach_boot_labels(session, cart: str | Path | None = None,
                       disk: str | Path | None = None) -> Path | None:
    """Register the labels a freshly booted session implies, and return them.

    A cartridge's sibling `.lbl` wins outright, and a cartridge with no label
    file registers nothing: a cartridge owns the boot, so the disk in the
    drive is not what the machine is running. Otherwise the disk image's
    implied labels (see disk_labels_path). None means "no symbols" — nothing
    was registered, and the session keeps whatever it had.
    """
    lbl = None
    if cart:
        c = Path(cart).with_suffix(".lbl")
        lbl = c if c.exists() else None       # a cartridge owns the boot
    elif disk:
        lbl = disk_labels_path(disk)
    if lbl is not None:
        session.set_labels_path(str(lbl))
    return lbl


def reboot_with_cart(session_name: str | None, crt: str | Path, *,
                     headless: bool, warp: bool) -> dict:
    """Boot a fresh session with `crt` attached, replacing the running one.

    A cartridge is mapped at power-on, so "running" one means rebooting
    rather than loading into the machine that is already up. The new session
    inherits the old one's name and model and nothing else — the launch flags
    are the caller's, because a `c64 run` is someone watching a window and an
    MCP client is an automation.

    "No session to reboot" and "no session by that name" are the same case:
    both boot an unnamed default `c64` with the cartridge rather than failing.
    Raises `SessionError` when a session IS there and will not stop.

    Returns `{"cart", "session", "model", "symbols"}`; `symbols` is the
    sibling `.lbl` registered on the new session, or None.
    """
    crt = Path(crt)
    # Bound before the attach, so the identity stays out of the stop's error
    # scope: a stop that fails is NOT "there was no session", and relaunching
    # under the no-session defaults would quietly swap a c64pal named 'snake'
    # for an NTSC 'c64' while 'snake' may still be alive. Pre-binding is also
    # what makes the launch below checkable: the front ends each carried a
    # `reportPossiblyUnbound` ignore for the older shape, where these were
    # assigned in two branches pyright could not correlate with `old`'s value.
    name: str | None = None
    model = "c64"
    try:
        old = Session.attach(session_name)
    except SessionError:
        old = None
    if old is not None:
        name, model = old.name, old.model
        try:
            old.stop()
        except (SessionError, OSError) as e:
            # OSError: stopping is kill() + unlink() of the registry record
            # and socket — a permission or filesystem failure there is the
            # same "the old session is still there" situation.
            raise SessionError(
                f"cannot boot {crt} on session {name!r}: the old session "
                f"has to stop first (a cartridge is mapped at power-on) "
                f"and stopping it failed: {e}") from e
    new = Session.launch(model=model, name=name, headless=headless,
                         warp=warp, cart=str(crt))
    lbl = attach_boot_labels(new, cart=crt)
    return {"cart": str(crt), "session": new.name, "model": new.model,
            "symbols": str(lbl) if lbl else None}


def _previous_program_note(session) -> str:
    """The Ms. Muncher trap in one line: a build that failed leaves the
    emulator running the program from BEFORE it, which looks exactly like a
    build that worked. Empty when the session has never loaded anything.
    """
    if not session.loaded_prg:
        return ""
    when = time.strftime("%H:%M:%S", time.localtime(session.loaded_at))
    return (f"\nemulator still running the PREVIOUS program "
            f"({session.loaded_prg}, loaded {when}) — nothing was reloaded")


#: What `c64 run`/`c64_run` accept. `.crt` is here and absent from
#: `build_for_run`'s dispatch below: a cartridge reboots the session with it
#: attached instead of being turned into something loadable.
RUNNABLE_SUFFIXES = (".bas", ".s", ".prg", ".crt")


def _unrunnable(ext: str) -> str:
    """One wording for the front-end pre-check and `build_for_run`'s own
    refusal, so the two cannot drift apart."""
    known = ", ".join(RUNNABLE_SUFFIXES[:-1]) + f", or {RUNNABLE_SUFFIXES[-1]}"
    return f"don't know how to run {ext!r} files (use {known})"


def runnable_ext(src: Path | str) -> str:
    """`src`'s lowercased suffix, or ValueError if `c64 run` cannot run it.

    Both front ends call this before their `--area`/`areas` applicability rule
    and before attaching a session, so `c64 run notes.txt --area FOO=$4000:$100`
    names the file it cannot run rather than the flag it cannot apply — which
    would invite dropping the flag and trying again on a file that will never
    run either way. `build_for_run` refuses the same extensions on its own, so
    nothing depends on a caller having come through here.
    """
    ext = Path(src).suffix.lower()
    if ext not in RUNNABLE_SUFFIXES:
        raise ValueError(_unrunnable(ext))
    return ext


def build_for_run(session, src: str | Path, areas: Sequence[str] | None = ()
                  ) -> tuple[Path, Path | None, tuple[Path, ...]]:
    """Turn a `c64 run` source into a loadable `.prg`: `(prg, labels, deps)`.

    `.prg` is taken as it is, `.bas` is tokenized, `.s` is assembled. `areas`
    is the caller's raw `NAME=START:SIZE` tokens, parsed against this
    session's load address (neither front end takes a `--model`) and before
    ca65 runs, so an area that cannot link is reported as the flag the user
    typed rather than as the config the toolset generated behind it.

    `labels` is the `.lbl` an assembly build produced, or None. `deps` is what
    `record_loaded` wants — every source the build read, or just `src` when
    there was no build to read anything.

    Raises `ValueError` for a malformed area and for an extension that cannot
    be run, and `BasicError`/`BuildError` for a failed tokenize or build. Only
    the latter carry the "still running the PREVIOUS program" note: a rejected
    flag is not a failed build, and nothing was going to be reloaded anyway.
    """
    src = Path(src)
    ext = src.suffix.lower()
    area_list = parse_areas(areas or (), session.profile.basic_start)
    labels: Path | None = None
    deps: tuple[Path, ...] = ()
    try:
        if ext == ".prg":
            prg = src
        elif ext == ".bas":
            prg = tokenize(src, src.with_suffix(".prg"),
                           session.profile.basic_version)
        elif ext == ".s":
            res = build_asm(src, basic_start=session.profile.basic_start,
                            areas=area_list)
            prg, labels, deps = res.prg, res.labels, res.deps
        else:
            # A front end that called `runnable_ext` first never gets here for
            # anything but a `.crt` it declined to handle; kept so nothing in
            # this op depends on the caller having checked.
            raise ValueError(_unrunnable(ext))
    except (BasicError, BuildError) as e:
        # Re-raised as its own class: a caller that tells a failed tokenize
        # from a failed build still can. `type(e)(...)` holds because both are
        # bare `Exception` subclasses taking one message and nothing else — an
        # error class that grew a second constructor argument (the way
        # `PinnedStopError` carries its two underlying exceptions) would have
        # to be re-raised by name here instead, or it would lose that argument.
        raise type(e)(f"{e}{_previous_program_note(session)}") from e
    # `deps` is empty for everything but a `.s`, and `build._parse_deps` can
    # never hand back an empty tuple for one (it falls back to the top
    # source), so "no deps" and "nothing was built" are the same case.
    #
    # Resolved, which neither front end asked for: `MonitorClient.autostart`
    # wants an absolute path (VICE mounts the file as a virtual drive, and a
    # relative one is resolved against the EMULATOR's cwd — not necessarily
    # this process's, since the daemon may have launched it elsewhere). The
    # MCP server already resolved its source before calling; the CLI did not,
    # so doing it here is what puts the two on one path. It is also the path
    # both front ends then echo as `prg`.
    return Path(prg).resolve(), labels, deps or (src,)


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


#: what a routine that never came back most likely was. Four timeout messages
#: end with it — `c64 call`/`c64 profile` and c64_call/c64_profile — and unlike
#: the `until` and `key hold` timeout prose (deliberately left doubled, because
#: each side names a companion verb the other spells differently) this clause
#: names no command at all, so it can be one string. Each front end still
#: writes everything around it.
RUNAWAY_ROUTINE = ("(runaway routine? check the address is a subroutine "
                   "ending in RTS)")


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


#: CIA#2 timer registers for the profile loop's 32-bit cycle cascade.
_CIA2_TA = 0xDD04
_CIA2_TB = 0xDD06
_CIA2_CRA = 0xDD0E
_CIA2_CRB = 0xDD0F
FLAG_I = 0x04
#: measured: CR write takes effect 3 cycles into the resumed window, so the
#: counter misses the window's first 3 cycles and they are added back. Stable
#: across 3 runs at each of three loop counts (hand-computed 507/57/1007 read
#: back 504/54/1004) and from both stop contexts profile can start in.
_CIA_START_SLACK = 3


#: raised when the CIA cascade reads back untouched. One message, used by
#: both the client-side loop and the daemon's (the daemon returns raw counts
#: and lets this side decide, so the text cannot drift between them).
_ZERO_RAW_CYCLES = (
    "measured 0 raw cycles, which no routine can cost (a bare "
    "RTS is 6): the CIA#2 timer pokes never reached the chip "
    "model — I/O may be banked out (writes to $DD04-$DD0F "
    "landing in RAM underneath; check $01), or the emulator "
    "dropped the side-effect writes")


def profile_samples_loop(mon, addr: int, n: int, timeout: float,
                         with_irq: bool, trap: int,
                         on_state: Callable[[bool], None] | None = None,
                         abort: Callable[[], bool] | None = None) -> dict:
    """Price `n` consecutive arrivals at `addr` on ONE monitor connection.

    The measurement bracket is call_routine's fake JSR with CIA#2 timers A+B
    cascaded into a 32-bit cycle counter; see `profile_routine_samples` for
    what the numbers mean and what the loop perturbs.

    Re-reaching the routine between samples is `until --count`'s shape: one
    persistent checkpoint at `trap` for the whole run, one resume per
    arrival, the durable hit/hit_count fallback for a lost STOPPED event —
    and the bracket re-armed in place (stack, SP, flags, PC, timers) rather
    than a fresh profile round trip per sample. Each arrival is re-armed from
    the ENTRY SP, so a routine that leaves the stack unbalanced cannot walk
    the pointer down across samples. Flags differ by mode, exactly as they do
    at n == 1: the default rewrites the WHOLE FL byte from the entry snapshot
    before every arrival (`fl | FLAG_I`), so no flag a sample leaves behind
    reaches the next one, while with_irq writes no FL at all, so flags — the
    routine's own I bit included — do carry over between arrivals.
    `timeout` covers the whole run, not each sample.

    Runs unchanged inside the session daemon (`daemon.PetDaemon`), which
    passes the two hooks: `on_state(running: bool)` mirrors the machine's
    run/stop state into the daemon's tracked state, and `abort()` reports
    that the command client vanished (Ctrl-C). Both default to None here.

    Returns {"fired": bool, "raw": [int], "reached": int, "registers":
    regs-or-None} — RAW counter deltas, before `_CIA_START_SLACK`: the caller
    corrects them and decides what a zero means, so the arithmetic and the
    error message exist once no matter which side ran the loop. A zero
    truncates the run (every later sample would be the same wrong number) but
    is still returned as a sample, after the ordinary cleanup.
    """
    def _state(running: bool) -> None:
        if on_state is not None:
            on_state(running)

    deadline = time.monotonic() + timeout
    regs = mon.registers()              # also stops the machine
    _state(False)
    sp, fl = regs["SP"], regs["FL"]
    ret = (trap - 1) & 0xFFFF
    ck = mon.checkpoint_set(trap, op=CP_EXEC, temporary=False)
    raw: list[int] = []
    for i in range(n):
        mon.memory_write(0x0100 + sp, bytes([ret >> 8]))
        mon.memory_write(0x0100 + ((sp - 1) & 0xFF), bytes([ret & 0xFF]))
        mon.set_register("SP", (sp - 2) & 0xFF)
        if not with_irq:
            mon.set_register("FL", fl | FLAG_I)
        mon.set_register("PC", addr)
        # 32-bit cascade: TB counts TA underflows; both latch $FFFF. Start
        # TB first (it only moves on TA underflows), TA last.
        mon.memory_write(_CIA2_TA, b"\xff\xff", side_effects=True)
        mon.memory_write(_CIA2_TB, b"\xff\xff", side_effects=True)
        mon.memory_write(_CIA2_CRB, b"\x51", side_effects=True)
        mon.memory_write(_CIA2_CRA, b"\x11", side_effects=True)
        mon.resume()
        _state(True)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # Deliberately NOT undone here: the timers are still running
                # and the I flag is still masked, and the machine is running
                # again by the time we know, so neither can be touched
                # safely. The callers say so in their failure messages.
                mon.checkpoint_delete(ck.number)
                mon.resume()
                _state(True)
                return {"fired": False, "raw": raw, "reached": len(raw),
                        "registers": None}
            info = mon.wait_for_stop(min(1.0, remaining))
            if info is not None and info.checkpoint == ck.number:
                break
            cur = next((c for c in mon.checkpoint_list()
                        if c.number == ck.number), None)
            if cur is not None and (cur.hit or cur.hit_count > i):
                break                    # durable flag caught a lost event
            mon.resume()                 # the list stopped the machine
            if abort is not None and abort():
                # Client gone (Ctrl-C mid-profile): same half-undone state as
                # the timeout above, and the same reason.
                mon.checkpoint_delete(ck.number)
                return {"fired": False, "raw": raw, "reached": len(raw),
                        "registers": None}
        ta = mon.memory_read(_CIA2_TA, 2)
        tb = mon.memory_read(_CIA2_TB, 2)
        mon.memory_write(_CIA2_CRA, b"\x00", side_effects=True)
        mon.memory_write(_CIA2_CRB, b"\x00", side_effects=True)
        ta_v = ta[0] | (ta[1] << 8)
        tb_v = tb[0] | (tb[1] << 8)
        raw.append((0xFFFF - tb_v) * 0x10000 + (0xFFFF - ta_v))
        if raw[-1] == 0:
            break                        # the caller raises, after cleanup
    out = mon.registers()
    _state(False)
    if not with_irq:
        # The reported registers must match the machine a caller will go on
        # to read: restore the entry I bit in BOTH, or `profile --json` would
        # report I=1 while a following `reg get` shows I=0.
        restored = (out["FL"] & ~FLAG_I) | (fl & FLAG_I)
        mon.set_register("FL", restored)
        out["FL"] = restored
    mon.checkpoint_delete(ck.number)
    return {"fired": True, "raw": raw, "reached": len(raw), "registers": out}


def profile_hazard(with_irq: bool, remedy: str) -> str:
    """What a timed-out profile left behind, ending in the caller's `remedy`.

    The state is a library fact — the CIA#2 timers are still running, and the
    I flag is still masked unless the measurement ran with interrupts live —
    so both front ends report it in the same words. Only the way out is theirs
    to spell: one names `c64 reg set FL`, the other c64_reg_set. With
    `with_irq` there is nothing to clear and `remedy` is unused, which is why
    it is a plain argument rather than something the caller has to guard.
    """
    if with_irq:
        return "CIA#2 timers A/B are left RUNNING"
    return ("CIA#2 timers A/B are left RUNNING and the I flag is left masked "
            "— the jiffy clock and keyboard stay dead until " + remedy)


def profile_routine_samples(session, addr: int, n: int = 1,
                            timeout: float = 30.0, with_irq: bool = False,
                            trap: int = CALL_TRAP) -> dict:
    """Measure a routine's cycle cost over `n` consecutive arrivals.

    Each arrival is call_routine's fake-JSR bracket with CIA#2 timers A+B
    cascaded into a 32-bit cycle counter. The emulation is frozen while the
    monitor programs the timers, so a count spans exactly the resumed window:
    the routine's first instruction through its own RTS. Counts are wall
    cycles — badline DMA (and, with with_irq=True, any interrupt handlers)
    land in the number, which is the frame-budget truth. By default the I
    flag is set on entry so the KERNAL IRQ cannot land inside the window (the
    flag's entry value is restored afterwards, on success).
    _CIA_START_SLACK is added back because the timer only starts a few cycles
    into the window; with it the count is exact against hand-computed
    routines (verified live in tests/test_integration_profile.py).

    **Why n > 1 exists:** the arrivals are consecutive *runs of the routine*,
    so a cost that depends on the program's own state comes back as a spread
    rather than as one number. La Galaxia's tick cost 10,729 cycles on an
    ordinary frame and 31,695 on a repaint frame, with repaints on roughly 5
    frames in 32 — a single arrival reported "fine" 27 times out of 32.

    With a session daemon the whole sample loop runs daemon-side in a single
    RPC, the way `run_until` does (re-reaching the routine costs ~15 monitor
    commands, so per-sample round trips would dominate); a pre-profile_samples
    daemon or a direct connection takes the client-side loop.

    Perturbs CIA#2 timers A/B: they are left stopped on success, but a
    timed-out profile leaves them running — and leaves the I flag as this
    function set it (masked, unless with_irq) — because the machine is
    running by then, so neither can be undone safely. A timed-out profile
    therefore leaves the jiffy clock frozen and the keyboard dead until a
    `c64 reg set FL ...` clears I, or the session is restarted.

    Returns {"fired", "samples", "min", "max", "mean", "registers", "trap",
    "irq_masked", "reached", "count"}, plus "cycles" when n == 1 — the single
    number every existing caller reads. Above one sample there is
    deliberately no "cycles" key: naming one arrival of a bimodal cost THE
    cost is the mistake this exists to stop. On timeout `fired` is False,
    `registers` is None and `samples` holds the arrivals that were priced
    before the deadline (checkpoint removed, machine left running), exactly
    like call_routine. Raises RuntimeError if the timers read back untouched
    — a raw count of 0, which no routine can cost — instead of reporting the
    start slack as a measurement; the machine is left stopped at the trap, as
    on success.
    """
    if n < 1:
        raise ValueError(f"profile needs at least 1 sample, got {n}")
    with session.monitor() as mon:
        loop = None
        if isinstance(mon, DaemonMonitorClient):
            try:
                loop = mon.profile_samples(addr, timeout, n, with_irq, trap)
            except ValueError as e:
                # Narrower than run_until's blanket `except ValueError`, on
                # purpose: falling back RUNS THE ROUTINE AGAIN, so a ValueError
                # that is not the old-daemon handshake must not silently buy a
                # second helping of side effects on top of a partial run.
                if "unknown daemon method" not in str(e):
                    raise
                loop = None       # old daemon: do the loop on this side
        if loop is None:
            loop = profile_samples_loop(mon, addr, n, timeout, with_irq, trap)
    if 0 in loop["raw"]:
        # No routine costs 0 raw cycles (a bare RTS is 6), so both timers
        # reading back $FFFF means the pokes never reached the chip model.
        # Adding the slack would report "cycles": 3 — a silent wrong number.
        # Raised after the loop's cleanup: the machine is stopped at the trap
        # with the timers stopped, exactly as on success.
        raise RuntimeError(_ZERO_RAW_CYCLES)
    samples = [r + _CIA_START_SLACK for r in loop["raw"]]
    out = {"fired": loop["fired"], "samples": samples,
           "min": min(samples) if samples else None,
           "max": max(samples) if samples else None,
           "mean": round(sum(samples) / len(samples), 1) if samples else None,
           "registers": loop["registers"], "trap": trap,
           "irq_masked": not with_irq,
           "reached": loop["reached"], "count": n}
    if n == 1:
        out["cycles"] = samples[0] if samples else None
    return out


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


def key_type(session, text: str, decode_escapes: bool = True) -> dict:
    """Type TEXT into the keyboard buffer. A literal `\\n` in TEXT is
    decoded to RETURN (as a real newline already is) and `\\\\` to one
    backslash; no other escape is interpreted. ValueError from unmappable
    characters propagates to the caller.

    decode_escapes=False types TEXT exactly as given — for callers whose
    text is a file's contents rather than a hand-typed argument."""
    if decode_escapes:
        text = _decode_type_escapes(text)
    petscii = ascii_to_petscii(text)
    with session.monitor() as mon:
        try:
            mon.keyboard_feed(petscii)
        finally:
            mon.release()
    return {"typed_chars": len(petscii)}


def type_basic(session, text: str, run: bool = False) -> dict:
    """Type BASIC program TEXT into the running machine through the keyboard.
    A trailing newline is added when TEXT lacks one (the last line has to be
    entered, not just displayed) and `run\\n` follows it when run=True.

    Typing shares key_type's keyboard feed but NOT its escape decoding
    (decode_escapes=False): program text is typed literally. A .bas file
    already carries real newlines, so a `\\n` in it is program text — two
    characters the C64 types as £N — not an escape, and decoding it would
    take a RETURN mid-line and split the program in two.
    ValueError from unmappable characters propagates to the caller."""
    if not text.endswith("\n"):
        text += "\n"
    if run:
        text += "run\n"
    return {**key_type(session, text, decode_escapes=False), "run": run}


def key_state_note(key: str, released: bool, *, flag: str,
                   clear_with: str) -> str:
    """Where a timed-out hold left the key, and how to undo it.

    The machine is left RUNNING by then, so the caller cannot look at $CB for
    itself and the message has to say it. Both front ends say the same thing;
    `flag` is the option that asked for the state (`--no-release` vs
    `release=false`) and `clear_with` the poke that ends it, because a caller
    reading one front end must not be sent to the other's commands.
    """
    if released:
        return "key released ($CB=64)"
    return f"$CB still holds {key!r} ({flag}) — clear it with {clear_with}"


def key_hold(session, key: str, at_addr: int, frames: int = 1,
             timeout: float = 30.0, release: bool = True) -> dict:
    """Hold KEY down for `frames` game ticks: write its keyboard-matrix
    code to $CB, run to at_addr, repeat — the machine ends STOPPED at
    at_addr.

    This is the poke-$CB debugger protocol as one operation: the IRQ
    keyboard scan (SCNKEY) rewrites $CB every tick (64 = no key), so the
    code must be re-poked before each frame. Programs reading the held
    key from $CB (or via GETIN after the scan decodes it) see the key.
    For a fully deterministic first frame, be stopped at at_addr already
    (run_until once); mid-flight the first poke can race the next IRQ.

    `release` (default True) pokes KEY_NONE after the final tick, letting
    the key go; the machine is left stopped at at_addr either way (on this
    path the release is a monitor write and nothing else — no resume). The
    timeout path below is the exception: it pokes *and* resumes, because
    run_until has already left the machine running. It defaults on because the
    other end state is never what a caller wants: the per-frame re-poke
    above assumes the KERNAL scan is running to clear $CB, and a game that
    takes the interrupt over — as every raster-multiplexed game must — has
    no scan left, so the key stays down for the rest of the session and
    every hold has to be chased with a hand-written poke of 64. Where the
    scan *is* alive it overwrites the byte next tick anyway, so releasing
    costs nothing there. Pass release=False for a hold that must still be
    down when the next command runs.

    Returns {"frames": done, "requested": frames, "registers": regs,
    "released": bool}; registers is None if a frame timed out (machine
    left RUNNING, same contract as run_until). A timed-out hold still
    releases when `release` is set — a wrong anchor is the commonest cause
    and jams the key exactly as above — and resumes afterwards so the
    machine really is left RUNNING. frames=0 is a validated no-op: the
    machine is untouched and the result is {"frames": 0, "requested": 0,
    "registers": None, "released": False}. frames < 0 raises ValueError."""
    k = " " if key.lower() == "space" else key
    if len(k) != 1:
        raise ValueError(f"key must be one character or 'space', got {key!r}")
    try:
        code = bytes([MATRIX_CODES[k.lower()]])
    except KeyError:
        raise ValueError(f"no matrix code for key {key!r}") from None
    if frames < 0:
        raise ValueError(f"frames must be >= 0, got {frames}")
    if frames == 0:
        # A computed hold length of 0 is ordinary in a scripted protocol.
        # Nothing is poked, nothing armed, nothing to time out — the caller
        # gets requested == frames == 0, distinct from a timeout, where
        # frames < requested and registers is None.
        return {"frames": 0, "requested": 0, "registers": None,
                "released": False}
    out = {"registers": None}
    for i in range(frames):
        with session.monitor() as mon:
            mon.memory_write(KEYDOWN_ADDR, code)
        out = run_until(session, at_addr, timeout=timeout, count=1)
        if out["registers"] is None:
            # Timed out — and this is the case that needs the release most:
            # the usual cause is a wrong anchor on a perfectly healthy game,
            # which leaves the key jammed down with no scan to clear it and
            # nothing stopped for the caller to notice. So let the key go
            # here too, then resume: run_until deliberately leaves the
            # machine RUNNING on timeout (it deletes the checkpoint and
            # resumes), and a monitor write halts it, so without the resume
            # the "machine left RUNNING" promise in the error message and in
            # docs/cli.md would be a lie.
            if release:
                with session.monitor() as mon:
                    mon.memory_write(KEYDOWN_ADDR, bytes([KEY_NONE]))
                    mon.resume()
            return {"frames": i, "requested": frames, "registers": None,
                    "released": release}
    if release:
        with session.monitor() as mon:
            mon.memory_write(KEYDOWN_ADDR, bytes([KEY_NONE]))
    return {"frames": frames, "requested": frames,
            "registers": out["registers"], "released": release}


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


def sprite_states(session) -> tuple[list[SpriteState], dict]:
    """Every sprite's decoded state plus the shared colors, read from the
    live registers and the pointers at the LIVE screen base + $3F8
    (relocation-aware, state-preserving)."""
    with session.monitor() as mon:
        try:
            return read_sprite_states(mon, screen_base(mon))
        finally:
            mon.release()


def sprite_shape(session, index: int, block: str | None = None
                 ) -> tuple[bytes, SpriteState, dict, int]:
    """(data, state, shared colors, block address) for sprite `index`, or for
    an explicit `block` ref in place of its pointer target.

    The range check runs BEFORE any monitor traffic, so a bad index costs no
    round trip and cannot surface as a MonitorError. Raises ValueError on an
    out-of-range index, and KeyError/ValueError from an unresolvable `block`:
    presentation belongs to the front ends."""
    if not 0 <= index <= 7:
        raise ValueError(f"sprite index {index} outside 0-7")
    states, shared = sprite_states(session)
    st = states[index]
    addr = session_ref(session, block) if block else st.block_addr
    with session.monitor() as mon:
        try:
            data = read_sprite_block(mon, addr)
        finally:
            mon.release()
    return data, st, shared, addr


def render_sprite_png(session, index: int, path: str | Path, scale: int = 1,
                      block: str | None = None) -> dict:
    """Write sprite `index`'s shape to `path` as a PNG; the `{png, width,
    height}` both front ends report.

    Colored from the palette the emulator is actually running, read over the
    monitor exactly as `save_screenshot_png` reads it. That is the point of
    this function existing rather than each front end calling `sprite_image`:
    `c64 sprite png` is the sprite inspector and `c64 screen --png` is the
    evidence camera, a reviewer is told to look at both, and while this path
    used the hardcoded `sprites.C64_PALETTE` the two rendered the same color
    number as two different colors.

    Costs one palette round trip, which is why `c64 sprite show` does not
    come through here — its ASCII has no color to get wrong.

    Raises what `sprite_shape` raises; presentation belongs to the front ends.
    """
    data, st, shared, _ = sprite_shape(session, index, block)
    with session.monitor() as mon:
        try:
            palette = mon.palette()
        finally:
            mon.release()          # an inspection read: never resume a halt
    img = sprite_image(data, st, shared, scale=scale, palette=palette)
    img.save(path, format="PNG")
    return {"png": str(path), "width": img.width, "height": img.height}


def easyflash_state(session) -> dict:
    """The live EasyFlash paging state: bank register ($DE00), mode register
    ($DE02) and the decoded memory mode, plus the LED bit.

    VICE lets these registers be read back; on real EasyFlash hardware they
    are write-only, so this is a debugging aid, not a program interface.
    """
    with session.monitor() as mon:
        try:
            regs = mon.memory_read(0xDE00, 3)
        finally:
            mon.release()          # an inspection read: never resume a halt
    bank_reg, mode_reg = regs[0], regs[2]
    return {"bank": bank_reg, "de00": f"${bank_reg:02X}",
            "de02": f"${mode_reg:02X}",
            "mode": EF_MODES.get(mode_reg, "unknown"),
            "led": bool(mode_reg & 0x80)}


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


def stopped_wait_diagnosis(effect: str, polls: str, *, stopped_by: str,
                           remedy: str) -> str:
    """Why a wait timed out on a machine that was halted for the whole window.

    The one diagnosis behind six messages: three polling waits on each front
    end, none of which resumes the CPU, so a halted machine could not have
    produced what the wait was looking for. `effect` is what could not happen
    ("the byte could not change") and `polls` what the wait watches instead of
    the CPU — the only two things that differ between the three waits.

    `stopped_by` and `remedy` are the front end's own: it names the commands
    that could have stopped the machine and the one that resumes it, because
    a CLI caller told to call `c64_continue` — or an MCP caller told to run
    `c64 continue` — has been handed the other front end's manual. That is the
    wrinkle that kept this pair doubled; naming it twice is cheaper than
    doubling forty words.
    """
    return (f"the machine was STOPPED for the whole wait, so {effect}: a wait "
            f"polls {polls}, it never resumes the CPU. Something before this "
            f"stopped it ({stopped_by}, or a checkpoint hit). {remedy}")
