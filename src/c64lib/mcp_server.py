"""MCP server exposing c64-tools to MCP-native AI clients (spec §3.3).

Thin wrappers over the same c64lib operations the CLI uses; CLI and MCP are
interchangeable against the same session registry. Tools return the same
structured data as the CLI's --json. Raised c64lib exceptions surface as MCP
tool errors with their actionable messages intact.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .audio import (
    capture,
    pinned_record_start,
    pinned_record_stop,
    report_timing_for,
    sid_log_detail,
    sid_report,
)
from .basic import tokenize
from .basic_lint import lint_source, tokenized_bytes
from .build import build_asm
from .cart_build import build_easyflash
from .cartridge import CartError, cart_dump, cart_info, cart_verify, run_cartconv
from .disasm import disassemble
from .disk import (
    block_bytes,
    block_poke,
    block_read,
    block_write_file,
    build_disk,
    cbm_lookup_name,
    create_image,
    delete_file,
    get_file,
    list_files,
    put_file,
    rename_file,
    validate_image,
)
from .machines import get_profile
from .ops import (
    call_routine,
    clear_checkpoints,
    disk_labels_path,
    find_bytes,
    key_hold,
    key_type,
    live_screen_base,
    machine_state,
    parse_byte_values,
    parse_number,
    parse_ref,
    pc_region,
    pc_symbol,
    profile_routine,
    run_until,
    session_labels,
    staleness,
    wait_for_break,
    wait_for_idle,
    wait_for_mem,
    wait_for_text,
)
from .packaging import package_program
from .protocol import CP_EXEC, CP_LOAD, CP_STORE
from .romdoc import identify, rom_labels
from .screen import (
    number_screen_text,
    read_screen_codes,
    read_screen_text,
    resolve_text_encoding,
    save_screenshot_png,
)
from .session import Session, SessionError
from .symbols import format_addr
from .testing import load_test, program_test, run_test
from .text import ascii_to_petscii

srv = FastMCP("c64-tools")


def _attach(session: str | None = None) -> Session:
    return Session.attach(session)


def _ref(s, ref, labels=None):
    """parse_ref with the session's screen geometry so @row,col works —
    against the LIVE screen base (relocation-aware)."""
    if labels is None:
        labels = session_labels(s)
    base = (live_screen_base(s) if "@" in str(ref)
            else s.profile.screen_addr)
    return parse_ref(labels, ref, screen_base=base,
                     screen_width=s.profile.screen_cols)


@srv.tool()
def c64_session_list() -> dict:
    """List running emulated C64 sessions (name, model, pid, monitor port)."""
    return {"sessions": [
        {"name": s.name, "model": s.model, "pid": s.pid, "port": s.port}
        for s in Session.list_all()
    ]}


@srv.tool()
def c64_session_start(model: str = "c64", name: str | None = None,
                      disk: str | None = None,
                      cart: str | None = None) -> dict:
    """Boot a fresh emulated C64 (headless, warp). Models: c64 (NTSC,
    the default) or c64pal. Optionally attach a d64/d71/d81 disk image, or a
    .crt cartridge that is mapped at power-on and boots itself."""
    s = Session.launch(model=model, name=name, headless=True, warp=True,
                       disk8=disk, cart=cart)
    lbl = None
    if cart:
        c = Path(cart).with_suffix(".lbl")
        lbl = c if c.exists() else None       # a cartridge owns the boot
    elif disk:
        lbl = disk_labels_path(disk)
    if lbl is not None:
        s.set_labels_path(str(lbl))
    return {"name": s.name, "model": s.model, "pid": s.pid, "port": s.port,
            "symbols": str(lbl) if lbl else None}


@srv.tool()
def c64_session_ensure(model: str = "c64", name: str | None = None) -> dict:
    """Attach to a running C64 session, or boot one (headless, warp) if
    none exists. Idempotent; "started" reports which happened."""
    s, started = Session.ensure(model=model, name=name, headless=True, warp=True)
    return {"name": s.name, "model": s.model, "pid": s.pid, "port": s.port,
            "started": started}


@srv.tool()
def c64_session_stop(name: str | None = None) -> dict:
    """Stop a running C64 session (the only one if name is omitted)."""
    s = Session.attach(name)
    s.stop()
    return {"stopped": s.name}


@srv.tool()
def c64_session_reset(hard: bool = False, session: str | None = None) -> dict:
    """Reset the C64 (soft, or hard power-cycle). Leaves the machine running."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            mon.reset(hard=hard)
        finally:
            mon.resume()
    return {"reset": s.name, "hard": hard}


@srv.tool()
def c64_status(session: str | None = None) -> dict:  # noqa: D401
    """The session and whether the machine is running or stopped right now.
    state is answered by the session daemon's own tracking (no emulator
    traffic); "unknown" without a daemon. Also reports the loaded program
    and any source files changed since it was loaded (stale binary!)."""
    s = _attach(session)
    return {"name": s.name, "model": s.model, "pid": s.pid, "port": s.port,
            "state": machine_state(s),
            "program": s.loaded_prg, "loaded_at": s.loaded_at,
            "stale": staleness(s)}


@srv.tool()
def c64_screen_text(session: str | None = None, style: str = "unicode",
                    ansi_reverse: bool = False, numbered: bool = False) -> dict:
    """Read the C64 screen as plain text. This is the PREFERRED way to see
    program output — faster and more reliable than screenshots for AI use.
    Graphics decode to Unicode glyphs; style="ascii" restores the legacy
    conservative mapping. numbered=True prefixes row indices and a column
    ruler, for working out @row,col references."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            text = read_screen_text(mon, s.profile, style, ansi_reverse)
        finally:
            mon.release()
    human = number_screen_text(text, s.profile.screen_cols) if numbered else text
    return {"text": human, "rows": text.splitlines()}


@srv.tool()
def c64_screen_codes(session: str | None = None) -> dict:
    """Read the raw screen-code matrix (rows x cols of ints) — exact
    values for checking glyphs without decoding ambiguity."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            codes = read_screen_codes(mon, s.profile)
        finally:
            mon.release()
    return {"codes": codes}


@srv.tool()
def c64_screenshot(path: str, session: str | None = None, scale: int = 1,
                   border: bool = False) -> dict:
    """Save a PNG screenshot. Prefer c64_screen_text for reading output;
    use this only when pixel-level appearance matters. scale gives an
    integer nearest-neighbour upscale (small C64 screens read better at
    2-3x). border=True includes the border area, so a POKE 53280 border
    color is visible; the default captures the inner screen only."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            w, h = save_screenshot_png(mon, path, scale=scale, border=border)
        finally:
            mon.release()
    return {"png": path, "width": w, "height": h}


@srv.tool()
def c64_mem_read(addr: str, length: int = 256, session: str | None = None,
                 encoding: str = "auto") -> dict:
    """Read emulated memory. addr accepts $hex, 0xhex, decimal, or a symbol
    from the loaded label file. Returns hex-encoded bytes plus "bytes" as a
    decimal int array, mirrored under "values" (the CLI `mem get` key).
    "text_encoding" names how these bytes decode to text:
    encoding="auto" resolves to "screen" when the range is on the live screen
    (screen RAM holds screen codes, not ASCII) and "ascii" otherwise; pass
    "screen", "petscii", or "ascii" to say so yourself."""
    s = _attach(session)
    a = _ref(s, addr)
    with s.monitor() as mon:
        try:
            data = mon.memory_read(a, length)
            resolved, _ = resolve_text_encoding(mon, s.profile, a, len(data),
                                                encoding)
        finally:
            mon.release()
    return {"addr": a, "length": len(data), "hex": data.hex(),
            "bytes": list(data), "values": list(data),
            "text_encoding": resolved}


@srv.tool()
def c64_mem_find(values: list[str], start: str = "$0000",
                 length: int = 0x10000, limit: int = 256,
                 session: str | None = None) -> dict:
    """Search memory for a byte pattern (values: one or more $hex/decimal
    bytes). Returns match addresses; "truncated" is true when `limit`
    clipped the list. Does not disturb run/stop state."""
    s = _attach(session)
    labels = session_labels(s)
    begin = _ref(s, start, labels)
    # parse_byte_values, not a bare bytes(parse_number(...)) comprehension:
    # lockstep with the CLI's `c64 mem find` — it splits whitespace inside a
    # token, names the offending token, and range-checks 0-255.
    pattern = parse_byte_values(values)
    with s.monitor() as mon:
        try:
            matches, truncated = find_bytes(mon, begin, length, pattern,
                                            limit=limit)
        finally:
            mon.release()
    return {"pattern": list(pattern), "start": begin, "length": length,
            "matches": matches, "count": len(matches), "truncated": truncated}


@srv.tool()
def c64_mem_write(addr: str, values: list[int], session: str | None = None) -> dict:
    """Write bytes to emulated memory. addr accepts $hex/0xhex/decimal/symbol."""
    s = _attach(session)
    a = _ref(s, addr)
    with s.monitor() as mon:
        try:
            mon.memory_write(a, bytes(values))
        finally:
            mon.release()
    return {"addr": a, "written": len(values)}


@srv.tool()
def c64_reg_get(session: str | None = None) -> dict:
    """Read CPU registers. PC is annotated with the nearest symbol from the
    ROM label database plus the session's label file, and with `pc_region` —
    "BASIC ROM"/"I/O"/"KERNAL ROM", or null in RAM. A PC in the KERNAL after
    your program ran usually means it finished or errored."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            regs = mon.registers()
        finally:
            mon.release()
    labels = {**rom_labels(s.profile.basic_version), **session_labels(s)}
    return {"registers": regs, "pc_symbol": pc_symbol(labels, regs),
            "pc_region": pc_region(regs.get("PC")), "state": machine_state(s)}


@srv.tool()
def c64_reg_set(name: str, value: str, session: str | None = None) -> dict:
    """Set a CPU register (e.g. PC, A, X, Y). value accepts $hex/0xhex/decimal."""
    s = _attach(session)
    v = parse_number(value)
    with s.monitor() as mon:
        try:
            mon.set_register(name, v)
        finally:
            mon.release()
    return {"register": name.upper(), "value": v}


@srv.tool()
def c64_break_add(ref: str, condition: str | None = None,
                  temporary: bool = False, session: str | None = None) -> dict:
    """Set a breakpoint at an address or symbol. Machine keeps running;
    use c64_wait_break to block until it fires."""
    s = _attach(session)
    labels = session_labels(s)
    addr = _ref(s, ref, labels)
    with s.monitor() as mon:
        try:
            ck = mon.checkpoint_set(addr, op=CP_EXEC, temporary=temporary)
            if condition:
                mon.condition_set(ck.number, condition)
        finally:
            mon.release()
    return {"id": ck.number, "address": format_addr(labels, addr),
            "condition": condition, "temporary": temporary}


@srv.tool()
def c64_break_list(session: str | None = None) -> dict:
    """List breakpoints/watchpoints with hit counts."""
    s = _attach(session)
    labels = session_labels(s)
    with s.monitor() as mon:
        try:
            cks = mon.checkpoint_list()
        finally:
            mon.release()
    return {"breakpoints": [
        {"id": ck.number, "address": format_addr(labels, ck.start), "end": ck.end,
         "op": ck.op, "enabled": ck.enabled, "hits": ck.hit_count,
         "has_condition": ck.has_condition}
        for ck in cks
    ]}


@srv.tool()
def c64_break_remove(checkpoint_id: int, session: str | None = None) -> dict:
    """Remove a breakpoint/watchpoint by id."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            mon.checkpoint_delete(checkpoint_id)
        finally:
            mon.release()
    return {"removed": checkpoint_id}


@srv.tool()
def c64_break_clear(session: str | None = None) -> dict:
    """Remove ALL breakpoints (exec checkpoints); watchpoints are kept.
    Checkpoints persist across c64_run/rebuilds — clear stale ones or
    duplicates accumulate."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            removed = clear_checkpoints(mon, CP_EXEC)
        finally:
            mon.release()
    return {"removed": removed, "count": len(removed)}


@srv.tool()
def c64_watch_clear(session: str | None = None) -> dict:
    """Remove ALL watchpoints (load/store checkpoints); breakpoints are kept."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            removed = clear_checkpoints(mon, CP_LOAD | CP_STORE,
                                        exclude_mask=CP_EXEC)
        finally:
            mon.release()
    return {"removed": removed, "count": len(removed)}


@srv.tool()
def c64_watch_add(ref: str, on_load: bool = False, on_store: bool = False,
                  length: int = 1, session: str | None = None) -> dict:
    """Set a watchpoint on a memory range (default: both load and store)."""
    s = _attach(session)
    labels = session_labels(s)
    addr = _ref(s, ref, labels)
    op = (CP_LOAD if on_load else 0) | (CP_STORE if on_store else 0)
    if not op:
        op = CP_LOAD | CP_STORE
    with s.monitor() as mon:
        try:
            ck = mon.checkpoint_set(addr, addr + length - 1, op=op)
        finally:
            mon.release()
    return {"id": ck.number, "address": format_addr(labels, addr), "length": length}


def _stopped_regs(s, regs: dict) -> dict:
    return {"registers": regs, "pc_symbol": pc_symbol(session_labels(s), regs),
            "stopped": True}


@srv.tool()
def c64_step(count: int = 1, over: bool = False, session: str | None = None) -> dict:
    """Execute N instructions. The machine STAYS STOPPED afterwards; use
    c64_continue to resume."""
    s = _attach(session)
    with s.monitor() as mon:
        regs = mon.step(count, over=over)
    return _stopped_regs(s, regs)


@srv.tool()
def c64_finish(session: str | None = None) -> dict:
    """Run until the current subroutine returns. Machine stays stopped."""
    s = _attach(session)
    with s.monitor() as mon:
        regs = mon.finish()
    return _stopped_regs(s, regs)


@srv.tool()
def c64_continue(session: str | None = None) -> dict:
    """Resume execution after a breakpoint/step."""
    s = _attach(session)
    with s.monitor() as mon:
        mon.resume()
    return {"running": True}


@srv.tool()
def c64_until(ref: str, timeout: float = 30.0, count: int = 1,
              session: str | None = None) -> dict:
    """Run until an address/symbol is executed count times; machine stays
    stopped there. count>1 = deterministic frame stepping on a loop label.
    On timeout: raises with the machine LEFT RUNNING and the checkpoint
    removed."""
    s = _attach(session)
    labels = session_labels(s)
    addr = _ref(s, ref, labels)
    out = run_until(s, addr, timeout, count=count)
    if out["registers"] is None:
        where = format_addr(labels, addr)
        raise RuntimeError(
            f"timeout: {where} reached {out['reached']}/{count} time(s) in "
            f"{timeout}s — machine left RUNNING, checkpoint removed. If the "
            f"program can branch away from {where} (death, menu, pause), it "
            "may never be reached again; set a breakpoint at a code path "
            "that must still execute and use c64_wait_break.")
    return {**_stopped_regs(s, out["registers"]), "count": count}


@srv.tool()
def c64_wait_text(text: str, timeout: float = 30.0, since: bool = False,
                  session: str | None = None) -> dict:
    """Block until TEXT appears on the screen. A timeout returns
    {"fired": null, "screen": ...} (not an error) so you can inspect what
    the program actually displayed.
    since=True fires only on an occurrence appearing after the call starts —
    use it when a real gap separates the trigger from the appearance; an
    instant reply can print before the call samples its baseline, so for
    turn-by-turn prompts anchor a cell with c64_wait_mem instead."""
    return wait_for_text(_attach(session), text, timeout, since=since)


@srv.tool()
def c64_wait_mem(addr: str, equals: str, timeout: float = 30.0,
                 op: str = "=", session: str | None = None) -> dict:
    """Block until the byte at addr compares to the value ($hex/decimal).

    `op` is one of = != > >= < <= and decides how `equals` (the right-hand
    value, named for the equality case) is compared. Use an inequality for
    a counter the machine can race past between polls.
    """
    s = _attach(session)
    return wait_for_mem(s, _ref(s, addr),
                        parse_number(equals), timeout, op=op)


@srv.tool()
def c64_wait_idle(timeout: float = 30.0, session: str | None = None) -> dict:
    """Block until the program has finished or errored — PC in the KERNAL
    direct-mode input loop on three consecutive reads.

    The wait that needs no prediction about what the program prints, so it
    is the one to use after running something whose output you do not know
    (a first run, a debug hunt). Do NOT use c64_wait_text with "READY." for
    this: the reset banner already says READY and matches instantly.

    A timeout is data, not an error: {"fired": null, "machine": "running",
    "last_pcs": [...]} means the machine never reached direct mode in the
    whole window — still running, or wedged, with the PCs naming the loop
    (feed one to c64_rom_disasm). Caveat: a program blocked on INPUT/GET
    sits in the same KERNAL routine and reads as idle."""
    out = wait_for_idle(_attach(session), timeout)
    if not out.get("fired"):
        out["machine"] = "running"
    return out


@srv.tool()
def c64_call(routine: str, a: int | None = None, x: int | None = None,
             y: int | None = None, timeout: float = 30.0,
             session: str | None = None) -> dict:
    """JSR one routine in isolation (fake return address on the stack,
    optional A/X/Y on entry) and stop at its RTS — the unit-test
    primitive: poke inputs, call, then assert registers/memory. Machine
    ends STOPPED on success, RUNNING on timeout."""
    s = _attach(session)
    addr = _ref(s, routine, session_labels(s))
    out = call_routine(s, addr, a=a, x=x, y=y, timeout=timeout)
    if out.get("fired"):
        out["pc_symbol"] = pc_symbol(session_labels(s), dict(out["registers"]))
    return out


@srv.tool()
def c64_profile(routine: str, with_irq: bool = False, timeout: float = 30.0,
                session: str | None = None) -> dict:
    """Measure a routine's cycle cost: fake-JSR it (like c64_call) with
    CIA#2 timers cascaded as a cycle counter. IRQs are masked during the
    window unless with_irq; counts include badline DMA. Machine ends
    STOPPED at the trap; on timeout it is left running."""
    s = _attach(session)
    addr = _ref(s, routine, session_labels(s))
    out = profile_routine(s, addr, timeout=timeout, with_irq=with_irq)
    if not out["fired"]:
        raise RuntimeError(f"profile {routine}: never returned in {timeout}s — "
                           "machine left running")
    return {"called": routine, "cycles": out["cycles"],
            "irq_masked": not with_irq, "registers": out["registers"],
            "trap": out["trap"]}


@srv.tool()
def c64_wait_break(timeout: float = 30.0, session: str | None = None,
                   checkpoint_id: int | None = None) -> dict:
    """Block until a breakpoint/watchpoint fires; reports checkpoint id, PC,
    and registers. Machine is left stopped when it fires. On timeout the
    machine is LEFT RUNNING (your checkpoints remain set) and the result is
    {"fired": null, "machine": "running", ...} — data, not an error."""
    s = _attach(session)
    out = wait_for_break(s, timeout, number=checkpoint_id)
    if out.get("fired"):
        out["pc_symbol"] = pc_symbol(session_labels(s), out.pop("registers"))
    else:
        out["machine"] = "running"
    return out


@srv.tool()
def c64_build(source: str, model: str = "c64") -> dict:
    """Assemble 6502 source (ca65 syntax) to a .prg + VICE label file."""
    profile = get_profile(model)
    res = build_asm(Path(source), basic_start=profile.basic_start)
    return {"prg": str(res.prg), "labels": str(res.labels)}


@srv.tool()
def c64_package(source: str, output: str | None = None, title: str | None = None,
                model: str = "c64", fmt: str | None = None,
                cart_type: str | None = None, wrap: bool = False) -> dict:
    """Package a .s/.bas/.prg into an artifact any VICE user can run: a .prg,
    a disk image whose first file autostarts (output ends in .d64/.d71/.d81),
    or a bootable cartridge (fmt="crt", or output ends in .crt). For a
    cartridge, cart_type is 8k/16k/ultimax (default 8k) and is an error
    outside one; a .s builds cart-native code unless wrap=True, and .bas/.prg
    are always wrapped in a launcher stub — a wrapped .bas needs cart_type 8k,
    since 16k maps ROM over BASIC. An fmt that disagrees with the output
    extension is an error too. Returns the exact run command in "run"."""
    return package_program(Path(source), out=output, title=title, model=model,
                           fmt=fmt, cart_type=cart_type, wrap=wrap)


@srv.tool()
def c64_run(source: str, session: str | None = None) -> dict:
    """Build/tokenize a .bas/.s/.prg as needed, then load and RUN it on the
    running C64. Registers assembly symbols on the session automatically. A
    .crt cannot be loaded into a running machine, so running one stops the
    session and boots a fresh one of the same name and model with the
    cartridge attached (returns {"cart", "session", "model", "symbols"}).

    For a .crt, "no session to reboot" and "no session by that name" are the
    same case: a session name that does not exist boots an unnamed default c64
    with the cartridge rather than failing. Every other tool errors on an
    unknown name, so check c64_session_list if a boot lands somewhere
    unexpected."""
    src = Path(source).resolve()
    ext = src.suffix.lower()
    if ext == ".crt":
        # A cartridge is mapped at power-on, so "running" one means booting a
        # fresh session with it attached rather than loading into this one.
        try:
            old = Session.attach(session)
        except SessionError:
            old, name, model = None, None, "c64"
        if old is not None:
            # Keep the identity out of the stop's error scope: a stop that
            # fails is NOT "there was no session", and relaunching under the
            # no-session defaults would quietly swap a c64pal named 'snake'
            # for an NTSC 'c64' while 'snake' may still be alive.
            name, model = old.name, old.model
            try:
                old.stop()
            except (SessionError, OSError) as e:
                # OSError: stopping is kill() + unlink() of the registry
                # record and socket — a permission or filesystem failure there
                # is the same "the old session is still there" situation.
                raise SessionError(
                    f"cannot boot {src} on session {name!r}: the old session "
                    f"has to stop first (a cartridge is mapped at power-on) "
                    f"and stopping it failed: {e}") from e
        # headless/warp as everywhere in this server (see c64_session_start):
        # an MCP client is an automation, not someone watching a window.
        # `name`/`model`: same shape as cli.py's `run` — bound on every path
        # that reaches here (unbound only if `old is not None` was False, and
        # `old` is None only on the except branch that binds them). Pyright
        # cannot correlate `old`'s value with their boundness.
        new = Session.launch(
            model=model, name=name,  # pyright: ignore[reportPossiblyUnboundVariable]
            headless=True, warp=True, cart=str(src))
        lbl = src.with_suffix(".lbl")
        if lbl.exists():
            new.set_labels_path(str(lbl))
        return {"cart": str(src), "session": new.name, "model": new.model,
                "symbols": str(lbl) if lbl.exists() else None}
    s = _attach(session)
    labels_path = None
    deps: tuple = ()
    if ext == ".prg":
        prg = src
    elif ext == ".bas":
        prg = tokenize(src, src.with_suffix(".prg"), s.profile.basic_version)
    elif ext == ".s":
        res = build_asm(src, basic_start=s.profile.basic_start)
        prg, labels_path, deps = res.prg, res.labels, res.deps
    else:
        raise ValueError(                       # same wording as the CLI's
            f"don't know how to run {ext!r} files "
            "(use .bas, .s, .prg, or .crt)")
    with s.monitor() as mon:
        try:
            mon.autostart(Path(prg).resolve(), run=True)
        finally:
            mon.resume()
    if labels_path:
        s.set_labels_path(str(labels_path))
    s.record_loaded(prg, deps if ext == ".s" else [src])
    return {"source": str(src), "prg": str(prg),
            "symbols": str(labels_path) if labels_path else None}


@srv.tool()
def c64_load(prg: str, run: bool = True, symbols: str | None = None,
             session: str | None = None) -> dict:
    """Load a .prg via autostart (optionally without RUN); optionally
    register a VICE label file for symbolic debugging."""
    s = _attach(session)
    p = Path(prg).resolve()
    with s.monitor() as mon:
        try:
            mon.autostart(p, run=run)
        finally:
            mon.resume()
    if symbols:
        s.set_labels_path(str(Path(symbols).resolve()))
    return {"loaded": str(p), "run": run, "symbols": symbols}


@srv.tool()
def c64_basic_check(source_path: str) -> dict:
    """Statically check a BASIC V2 source file before running it. Run this
    after writing or editing BASIC and BEFORE c64_run / c64_basic_type — it
    catches keyword fusion (`total=5` tokenizes as `TO TAL=5` on a C64),
    missing GOTO/GOSUB targets, out-of-range POKEs, non-V2 keywords and
    oversize programs without an emulator round trip. Needs no session.
    Returns issues with stable rule IDs (E... will not run, W... suspect)
    plus the exact tokenized size (38911 bytes are free)."""
    from dataclasses import asdict

    text = Path(source_path).read_text()
    issues = lint_source(text)
    errors = sum(1 for i in issues if i.severity == "error")
    return {"issues": [asdict(i) for i in issues], "errors": errors,
            "warnings": len(issues) - errors,
            "tokenized_bytes": tokenized_bytes(text)}


@srv.tool()
def c64_basic_type(text: str, run: bool = False,
                   session: str | None = None) -> dict:
    """Type BASIC program text into the running C64 via the keyboard
    (keywords may be upper or lower case; each line ends with \\n).
    Set run=true to type RUN afterwards."""
    s = _attach(session)
    if not text.endswith("\n"):
        text += "\n"
    if run:
        text += "run\n"
    petscii = ascii_to_petscii(text)
    with s.monitor() as mon:
        try:
            mon.keyboard_feed(petscii)
        finally:
            mon.release()
    return {"typed_chars": len(petscii), "run": run}


@srv.tool()
def c64_key_type(text: str, session: str | None = None) -> dict:
    """Type text into the running C64's keyboard buffer (\\n = RETURN,
    literal backslash-n included; \\\\ types one backslash).
    Buffered keys never touch the live current-key state — games reading $CB
    need c64_key_hold."""
    s = _attach(session)
    return key_type(s, text)


@srv.tool()
def c64_key_hold(key: str, at: str, frames: int = 1, timeout: float = 30.0,
                 session: str | None = None) -> dict:
    """Hold KEY down for N game ticks by re-poking its matrix code into
    $CB before each one, running to the frame anchor `at` (label or
    address executed once per tick) between pokes; the machine ends
    STOPPED there. KEY is one character or 'space'. frames=0 is a
    validated no-op: the machine is untouched and the result is
    {"frames": 0, "requested": 0, "machine": "untouched"}."""
    s = _attach(session)
    labels = session_labels(s)
    addr = _ref(s, at, labels)
    out = key_hold(s, key, addr, frames=frames, timeout=timeout)
    if out["requested"] == 0:
        # Nothing poked, nothing armed, nothing to time out — the same
        # honest no-op the CLI reports, not the registers-is-None timeout
        # below (which would blame a checkpoint that never existed).
        return {"frames": 0, "requested": 0, "machine": "untouched"}
    if out["registers"] is None:
        raise RuntimeError(
            f"timeout: only {out['frames']}/{frames} frame(s) reached "
            f"{format_addr(labels, addr)} — machine left RUNNING, checkpoint "
            "removed. Is the anchor really executed every tick?")
    return {**_stopped_regs(s, out["registers"]), "frames": out["frames"]}


@srv.tool()
def c64_disk_create(image: str, label: str = "disk", disk_id: str = "00") -> dict:
    """Create a blank d64/d71/d81 disk image."""
    return {"image": str(create_image(Path(image), label=label, disk_id=disk_id))}


@srv.tool()
def c64_disk_ls(image: str) -> dict:
    """List the directory of a disk image."""
    return list_files(Path(image))


@srv.tool()
def c64_disk_put(image: str, file: str, name: str | None = None) -> dict:
    """Copy a host file onto a disk image."""
    # str(Path(...)) everywhere `image` is echoed: the CLI emits str(image) off
    # a click Path, so "./game.d64" comes back "game.d64" — the payloads have
    # to agree character for character, not just key for key.
    return {"image": str(Path(image)),
            "name": put_file(Path(image), Path(file), name)}


@srv.tool()
def c64_disk_get(image: str, name: str, dest: str) -> dict:
    """Copy a file off a disk image to the host."""
    return {"image": str(Path(image)), "name": name,
            "dest": str(get_file(Path(image), name, Path(dest)))}


@srv.tool()
def c64_disk_boot(image: str, session: str | None = None) -> dict:
    """Attach a disk image to the running C64 and LOAD+RUN its first file."""
    s = _attach(session)
    p = Path(image).resolve()
    with s.monitor() as mon:
        try:
            mon.autostart(p, run=True)
        finally:
            mon.resume()
    lbl = disk_labels_path(Path(image))
    if lbl is not None:
        s.set_labels_path(str(lbl))
    return {"booted": str(p), "symbols": str(lbl) if lbl else None}


@srv.tool()
def c64_disk_rename(image: str, old: str, new: str) -> dict:
    """Rename a file on a disk image. `new` is validated as a CBM filename
    (1-16 chars, no ":,=*?). Errors when `old` is not on the disk — c1541
    reports a missing file without failing. A wildcard in `old` is refused, so
    a rename can never act on more than the one file you named. Needs no
    session."""
    # cbm_lookup_name for the echo, not the raw `old`: rename_file looks the
    # file up through it, so echoing the caller's spelling put {"old": "ALPHA",
    # "name": "beta"} — two spellings of one convention — in a single payload.
    return {"image": str(Path(image)), "old": cbm_lookup_name(old),
            "name": rename_file(Path(image), old, new)}


@srv.tool()
def c64_disk_rm(image: str, name: str) -> dict:
    """Scratch a file from a disk image. `name` may use the CBM wildcards `*`
    and `?`, which scratch every match at once — a name of "*" empties the
    disk — so "deleted" is the count that matters. Errors when nothing matched:
    c1541 answers a no-match scratch exactly like a successful one apart from
    that count. Needs no session."""
    # The normalized name, for the same reason as rename: a caller told its
    # `AL*` matched 1 file when what actually ran was `al*`.
    return {"image": str(Path(image)), "name": cbm_lookup_name(name),
            "deleted": delete_file(Path(image), name)}


@srv.tool()
def c64_disk_block_read(image: str, track: int, sector: int,
                        output: str | None = None) -> dict:
    """Read one 256-byte sector from a disk image. Track is 1-based and sector
    0-based (the CBM convention); on a 1541 image 18/0 is the BAM and 18/1 the
    first directory sector. Returns the sector in "hex", or writes it to
    `output` and reports the path instead — the two payloads differ exactly as
    the CLI's do. Needs no session."""
    data = block_read(Path(image), track, sector)
    if output is not None:
        dest = Path(output)
        try:
            dest.write_bytes(data)
        except OSError as e:
            # Same contract as the CLI's -o: a refused dump names the path.
            # Re-raise the same subclass, so a caller can still tell a
            # PermissionError from a FileNotFoundError.
            raise type(e)(f"{dest}: {e.strerror or e}") from None
        return {"image": str(Path(image)), "track": track, "sector": sector,
                "output": str(dest), "bytes": len(data)}
    return {"image": str(Path(image)), "track": track, "sector": sector,
            "bytes": len(data), "hex": data.hex()}


@srv.tool()
def c64_disk_block_write(image: str, track: int, sector: int,
                         src: str | None = None,
                         values: list[int] | None = None,
                         offset: int | None = None) -> dict:
    """Write a sector of a disk image: pass `src` (a host file of exactly 256
    bytes, the CLI's --from) to replace the whole sector, or `values` (the
    CLI's VALUES) with `offset` to poke bytes inside it, leaving the rest
    alone. Exactly one of the two, and `offset` belongs only to a poke.
    Wrong-sized whole-sector writes and pokes running off the end of a sector
    are rejected — c1541 accepts both silently. `offset` defaults to 0.
    Needs no session."""
    # `not values` (not `values is None`) mirrors the CLI's bool(values) on a
    # click nargs=-1 tuple: an empty VALUES list is no source at all, so
    # values=[] alone is refused and src + values=[] is a plain --from write.
    if (src is None) == (not values):
        raise ValueError("give exactly one of --from FILE or VALUES (bytes to poke)")
    if src is not None and offset is not None:
        # None (not 0) is what tells an explicit --offset 0 from an unset one,
        # the way the CLI's parameter source does.
        raise ValueError("--offset applies to a VALUES poke; --from replaces the "
                         "whole sector, so there is nothing for it to offset")
    if src is not None:
        block_write_file(Path(image), track, sector, Path(src))
        written, at = 256, 0
    else:
        at = offset or 0
        # Size the write from the coerced bytes, not from `values`: the guard
        # above already proves `values` is a non-empty list here (it rejects a
        # None `src` with a falsy `values`), but it says so through
        # `(src is None) == (not values)`, which narrows nothing. block_bytes
        # is 1:1 — one appended byte per element, or it raises — so the count
        # is the same one, taken from a value that cannot be None.
        poke = block_bytes(values)
        block_poke(Path(image), track, sector, at, poke)
        written = len(poke)
    return {"image": str(Path(image)), "track": track, "sector": sector,
            "written": written, "offset": at}


@srv.tool()
def c64_disk_validate(image: str) -> dict:
    """Check and repair a disk image's block allocation — the CBM fsck.
    Rewrites the BAM in place. c1541 reports nothing either way, so
    cleanliness is decided by comparing the image before and after;
    blocks_free_before/after are the evidence and "clean" is the flag to
    trust. Needs no session."""
    return validate_image(Path(image))


@srv.tool()
def c64_disk_build(manifest: str, output: str | None = None,
                   model: str = "c64") -> dict:
    """Build a populated disk image from a .disk.yaml manifest in one step.
    Files are written in listed order, so the first one autostarts; .s entries
    are assembled, .bas tokenized, everything else copied verbatim. A manifest
    that would overflow the disk is refused before anything is written, since
    a full disk otherwise leaves a truncated file and a corrupt BAM behind.
    Reports blocks used/free and a run hint. Needs no session."""
    return build_disk(Path(manifest), out=output, model=model)


@srv.tool()
def c64_cart_build(manifest: str, output: str | None = None) -> dict:
    """Build a multi-bank EasyFlash .crt from an .ef.yaml manifest (up to 64
    banks / 1 MB). Every window is exactly 8192 bytes and an overflow is a
    hard error naming the bank — nothing is ever silently truncated. Returns
    the per-bank fill table in "fill" and bank-tagged symbols in "labels".
    Needs no session."""
    return build_easyflash(Path(manifest), out=output)


@srv.tool()
def c64_cart_info(file: str) -> dict:
    """Decode a .crt: name, hardware type, EXROM/GAME lines, the resulting
    memory mode, and every CHIP packet (bank, window, load address, size).
    Needs no session."""
    return cart_info(Path(file))


@srv.tool()
def c64_cart_verify(file: str) -> dict:
    """Check whether a .crt should boot, before spending an emulator run.
    Catches the silent failures: no CBM80 autostart signature (the machine
    just boots to BASIC), a cold/reset vector pointing outside the cartridge,
    a wrong image size, and an EasyFlash image missing the bank 0 HIROM window
    the reset vector lives in. "ok" is false when "reasons" is non-empty; a
    file that is not a readable .crt at all reports "error" instead."""
    try:
        reasons = cart_verify(Path(file))
    except CartError as e:
        # The CLI reports an unparseable image as {"error": ...}; a verdict
        # tool must hand that back as data, not as a tool error.
        return {"path": str(file), "ok": False, "error": str(e)}
    return {"path": str(file), "ok": not reasons, "reasons": reasons}


@srv.tool()
def c64_cart_dump(file: str, output: str, bank: int = 0,
                  window: str = "lo") -> dict:
    """Extract one bank window from a .crt to a raw .bin for disassembly.
    window is "lo" ($8000) or "hi" ($A000, or $E000 in Ultimax mode)."""
    data = cart_dump(Path(file), bank, window)
    Path(output).write_bytes(data)
    return {"path": output, "bank": bank, "window": window, "bytes": len(data)}


@srv.tool()
def c64_cart_bank(session: str | None = None) -> dict:
    """Report the live EasyFlash paging state of the running machine: the
    bank register ($DE00), the mode register ($DE02), and the decoded memory
    mode. Combine with a store watchpoint on $DE00 to trace paging. VICE lets
    these write-only registers be read back; treat it as a debugging aid."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            regs = mon.memory_read(0xDE00, 3)
        finally:
            mon.release()          # an inspection command: never resume a halt
    bank_reg, mode_reg = regs[0], regs[2]
    return {"bank": bank_reg, "de00": f"${bank_reg:02X}",
            "de02": f"${mode_reg:02X}",
            "mode": {0x87: "16k", 0x86: "8k", 0x84: "ultimax"}.get(
                mode_reg, "unknown"),
            "led": bool(mode_reg & 0x80)}


@srv.tool()
def c64_cart_convert(source: str, output: str, cart_type: str | None = None,
                     name: str | None = None) -> dict:
    """Convert between a raw .bin and a .crt with VICE's cartconv — the escape
    hatch for cartridge types this tool does not model natively."""
    args = ["-i", str(source), "-o", str(output)]
    if cart_type:
        args += ["-t", cart_type]
    if name:
        args += ["-n", name]
    return {"source": source, "output": output,
            "cartconv": run_cartconv(args).strip()}


@srv.tool()
def c64_rom_info(session: str | None = None) -> dict:
    """Identify the loaded ROM set (names + content hashes)."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            return identify(mon)
        finally:
            mon.release()


@srv.tool()
def c64_rom_disasm(start: str, length: int = 32,
                   session: str | None = None) -> dict:
    """Disassemble live memory with ROM + session symbol annotations.
    start accepts $hex/0xhex/decimal or a symbol (e.g. CHROUT)."""
    s = _attach(session)
    labels = {**rom_labels(s.profile.basic_version), **session_labels(s)}
    addr = _ref(s, start, labels)
    with s.monitor() as mon:
        try:
            data = mon.memory_read(addr, length)
        finally:
            mon.release()
    return {"start": addr, "length": length,
            "lines": disassemble(data, addr, labels)}


@srv.tool()
def c64_test_run(yaml_file: str) -> dict:
    """Run a declarative YAML test (boots its own fresh C64; the file
    format is documented in docs/cli.md under `c64 test run`)."""
    return run_test(load_test(Path(yaml_file))).to_dict()


@srv.tool()
def c64_test_programs(directory: str = "tests/programs") -> dict:
    """Run every example-program directory (program + expect.txt) as a test."""
    results = [run_test(program_test(d))
               for d in sorted(Path(directory).iterdir())
               if (d / "expect.txt").exists()]
    return {"passed": all(r.passed for r in results),
            "tests": [r.to_dict() for r in results]}


def main() -> None:
    srv.run()


if __name__ == "__main__":
    main()


def _sprite_states(s):
    from .screen import screen_base
    from .sprites import read_sprite_states
    with s.monitor() as mon:
        try:
            return read_sprite_states(mon, screen_base(mon))
        finally:
            mon.release()


def _sprite_shape(s, index: int, block: str | None):
    from .sprites import read_sprite_block
    if not 0 <= index <= 7:
        raise ValueError(f"sprite index {index} outside 0-7")
    states, shared = _sprite_states(s)
    st = states[index]
    addr = _ref(s, block) if block else st.block_addr
    with s.monitor() as mon:
        try:
            data = read_sprite_block(mon, addr)
        finally:
            mon.release()
    return data, st, shared, addr


@srv.tool()
def c64_sprite_status(session: str | None = None) -> dict:
    """Decode the VIC-II sprite registers and pointers into a per-sprite
    table (enabled, x/y with MSB folded in, pointer/block address, color,
    multicolor/expand/priority flags) plus the shared colors.
    Relocation-aware and state-preserving."""
    from dataclasses import asdict
    s = _attach(session)
    states, shared = _sprite_states(s)
    return {"sprites": [asdict(st) for st in states], "shared": shared}


@srv.tool()
def c64_sprite_show(index: int, block: str | None = None,
                    session: str | None = None) -> dict:
    """Render sprite `index`'s 63-byte shape as ASCII art rows (21 rows,
    24 cells; multicolor pairs double-wide). `block` dumps an explicit
    block address/symbol instead of the sprite's pointer target."""
    from .sprites import sprite_ascii
    s = _attach(session)
    data, st, _, addr = _sprite_shape(s, index, block)
    return {"rows": sprite_ascii(data, st.multicolor),
            "block_addr": addr, "multicolor": st.multicolor}


@srv.tool()
def c64_sprite_png(index: int, path: str, scale: int = 8,
                   block: str | None = None,
                   session: str | None = None) -> dict:
    """Render sprite `index`'s shape to a PNG colored from the live
    registers. Prefer c64_screenshot for whole-frame evidence; this shows
    one sprite's shape exactly."""
    from .sprites import sprite_image
    s = _attach(session)
    data, st, shared, _ = _sprite_shape(s, index, block)
    img = sprite_image(data, st, shared, scale=scale)
    img.save(path, format="PNG")
    return {"png": path, "width": img.width, "height": img.height}


@srv.tool()
def c64_sprite_from_png(image: str, multicolor: bool = False) -> dict:
    """Convert any PNG into ready-to-paste ca65 .byte sprite rows (no
    session needed): resize to sprite resolution, hires 50% luminance
    threshold or multicolor palette quantization (mapping recorded in the
    emitted header). Verify the pasted result with c64_sprite_show."""
    from PIL import Image

    from .sprites import sprite_from_image
    img = Image.open(image)
    data, lines = sprite_from_image(img, multicolor=multicolor)
    return {"rows": lines, "bytes": list(data)}


@srv.tool()
def c64_audio_record(action: str, path: str | None = None,
                     session: str | None = None) -> dict:
    """Record the emulated SID to a WAV file. action="start" arms the
    recorder on `path` (an absolute path is safest — a relative one is
    resolved against this server's working directory); action="stop"
    disarms it and reports the file's size.

    Recording takes the machine off warp and holds it at 100% speed for the
    whole window, then puts both back on stop — so a 3-second capture costs
    3 real seconds, and nothing else should share the session meanwhile.
    That pin is not optional: while warped VICE writes a 0-frame WAV.
    """
    s = _attach(session)
    if action == "start":
        if not path:
            raise ValueError("c64_audio_record start needs a path for the WAV")
        return pinned_record_start(s, path)
    if action == "stop":
        return pinned_record_stop(s)
    raise ValueError(f"unknown action {action!r}; use 'start' or 'stop'")


@srv.tool()
def c64_sid_log(frames: int, path: str, session: str | None = None) -> dict:
    """Log the SID's 25 registers ($D400-$D418) once per video frame to
    `path` as JSONL — `{"frame": n, "regs": [...]}` per line, which is what
    the analysis side (transcription, note diff, piano roll) reads. This is
    how you check what a tune actually played without hearing it.

    The loop runs inside the session daemon, one frame per round trip, so a
    100-frame log costs about 5 seconds at real time and a quarter of a
    second warped. (That is a different log from the 200-frame one the rates
    below come from — the two are separate measurements, not a cost and its
    quotient.) It does not touch the emulator's speed: run it inside a pinned
    recording (or c64_audio_capture) and every frame lands. Run it on a
    warped session and it is far faster, but a frame can slip past between
    records — the returned `warning` says so when the sampling rate gives it
    away. That check is one-sided, so no warning is not proof of an exact
    timeline; pinning real time is what settles it. `sample_rate_hz` is
    samples per wall-clock second, NOT the machine's frame rate and not
    comparable to it (the emulator only runs between round trips, so one
    200-frame log measured ~22/s pinned from a 60 Hz machine against ~425/s
    warped): above the frame rate it proves the session was not at real
    time, below it proves nothing.

    The warning's own threshold is a fixed 63/s — 60 fps, the fastest machine
    here, plus a 5% margin — not the session's frame rate, so a PAL session
    sampling between 50 and 63/s goes unflagged although it already proves
    the machine outran 50 fps. Apply the machine's own rate yourself when the
    timeline matters. Leaves the machine running.
    """
    s = _attach(session)
    return sid_log_detail(s, frames, path)


@srv.tool()
def c64_sid_report(log: str, outdir: str, wav: str | None = None,
                   ref: str | None = None, session: str | None = None) -> dict:
    """Turn a captured SID register log (and its WAV, if there is one) into a
    verdict you can read: `report.md` in `outdir`, beside `piano-roll.png` and
    — with a WAV — `spectrogram.png`. Pure analysis, so it needs no running
    session and can be re-run on old artifacts.

    It transcribes the log to note events, diffs them against the `ref` score
    YAML when you give one, and lists the anomalies no working tune produces
    (stuck gates, notes held audibly out of tune). Without `ref` every
    reference-free check still runs and an empty diff is a legitimate PASS —
    but a score you wrote from your own note data BEFORE capturing is what
    turns this from a description into a test.

    Name a `session` when the capture came from an NTSC machine: a register
    log does not carry its clock, so with no session PAL is assumed (985248
    Hz, 50 fps) and an NTSC log transcribes about 65 cents out — a plausible
    report of the wrong pitches. Returns the artifact paths, the verdict, and
    the findings behind it.
    """
    timing = report_timing_for(_attach(session).model if session else None)
    return sid_report(log, outdir, wav_path=wav, ref_path=ref, timing=timing)


@srv.tool()
def c64_audio_capture(seconds: float, outdir: str, ref: str | None = None,
                      session: str | None = None) -> dict:
    """Record the running program's audio and report on what it played — the
    one call that verifies SID music end to end. Pins real time, records
    `capture.wav`, logs the SID's registers to `sid-log.jsonl`, restores the
    session's speed, and writes `piano-roll.png`, `spectrogram.png`, and
    `report.md` into `outdir`.

    Start the music BEFORE calling this, and give `ref` a score YAML written
    from your own note data rather than from a transcription this produced —
    a reference derived from the output cannot fail. An opening rest the
    score does not list is skipped rather than diffed (the way trailing
    silence is), so a slightly early capture costs window rather than a
    cascade of wrong notes.

    `seconds` is EMULATED time and costs several times that in wall clock: the
    machine advances one frame per monitor round trip while the log samples.
    Measured on an NTSC session, a 2-second capture (120 frames) took 6.19 s
    from pinning to unpinning — the `wall_clock_s` this returns — and 6.32 s
    for the whole call including the report; `src/c64lib/audio.py`'s module
    docstring holds that measurement and the evidence behind it. Budget for
    it, and let nothing else drive the session meanwhile — the capture window
    has to stay at real time, since a warped VICE writes a 0-frame WAV.

    Returns the artifact paths, the verdict, the score diff, the anomalies,
    and what the capture cost (`frames`, `emulated_s`, `wall_clock_s`).

    `unpin_error` is None on a capture that put its session back. When it is
    not, the artifacts and the verdict are still good — they were complete
    before the restore ran — but that session may still be at real time with
    warp off: retry with `c64_audio_record(action="stop")`, or restart it,
    before trusting its timing again. (A recorder that could not be disarmed
    is a different failure and still raises: that one leaves no finalized WAV
    to report on.)
    """
    s = _attach(session)
    return capture(s, seconds, outdir, ref_path=ref)
