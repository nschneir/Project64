"""MCP server exposing c64-tools to MCP-native AI clients (spec §3.3).

Thin wrappers over the same c64lib operations the CLI uses; CLI and MCP are
interchangeable against the same session registry. Tools return the same
structured data as the CLI's --json. Raised c64lib exceptions surface as MCP
tool errors with their actionable messages intact.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .basic import tokenize
from .basic_lint import lint_source, tokenized_bytes
from .build import build_asm
from .disasm import disassemble
from .disk import create_image, get_file, list_files, put_file
from .machines import get_profile
from .ops import (
    call_routine,
    clear_checkpoints,
    find_bytes,
    key_hold,
    key_type,
    live_screen_base,
    machine_state,
    parse_number,
    parse_ref,
    pc_symbol,
    run_until,
    session_labels,
    staleness,
    wait_for_break,
    wait_for_mem,
    wait_for_text,
)
from .packaging import package_program
from .protocol import CP_EXEC, CP_LOAD, CP_STORE
from .romdoc import identify, rom_labels
from .screen import read_screen_codes, read_screen_text, save_screenshot_png
from .session import Session
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
                      disk: str | None = None) -> dict:
    """Boot a fresh emulated C64 (headless, warp). Models: c64 (NTSC,
    the default) or c64pal. Optionally attach a d64/d71/d81 disk
    image."""
    s = Session.launch(model=model, name=name, headless=True, warp=True,
                       disk8=disk)
    return {"name": s.name, "model": s.model, "pid": s.pid, "port": s.port}


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
                    ansi_reverse: bool = False) -> dict:
    """Read the C64 screen as plain text. This is the PREFERRED way to see
    program output — faster and more reliable than screenshots for AI use.
    Graphics decode to Unicode glyphs; style="ascii" restores the legacy
    conservative mapping."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            text = read_screen_text(mon, s.profile, style, ansi_reverse)
        finally:
            mon.release()
    return {"text": text, "rows": text.splitlines()}


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
def c64_screenshot(path: str, session: str | None = None, scale: int = 1) -> dict:
    """Save a PNG screenshot. Prefer c64_screen_text for reading output;
    use this only when pixel-level appearance matters. scale gives an
    integer nearest-neighbour upscale (small C64 screens read better at 2-3x)."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            w, h = save_screenshot_png(mon, path, scale=scale)
        finally:
            mon.release()
    return {"png": path, "width": w, "height": h}


@srv.tool()
def c64_mem_read(addr: str, length: int = 256, session: str | None = None) -> dict:
    """Read emulated memory. addr accepts $hex, 0xhex, decimal, or a symbol
    from the loaded label file. Returns hex-encoded bytes plus "bytes" as a
    decimal int array."""
    s = _attach(session)
    a = _ref(s, addr)
    with s.monitor() as mon:
        try:
            data = mon.memory_read(a, length)
        finally:
            mon.release()
    return {"addr": a, "length": len(data), "hex": data.hex(),
            "bytes": list(data)}


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
    pattern = bytes(parse_number(v) for v in values)
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
    """Read CPU registers. PC is annotated with the nearest symbol when a
    label file is loaded."""
    s = _attach(session)
    with s.monitor() as mon:
        try:
            regs = mon.registers()
        finally:
            mon.release()
    return {"registers": regs, "pc_symbol": pc_symbol(session_labels(s), regs),
            "state": machine_state(s)}


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
def c64_wait_text(text: str, timeout: float = 30.0,
                  session: str | None = None) -> dict:
    """Block until TEXT appears on the screen. A timeout returns
    {"fired": null, "screen": ...} (not an error) so you can inspect what
    the program actually displayed."""
    return wait_for_text(_attach(session), text, timeout)


@srv.tool()
def c64_wait_mem(addr: str, equals: str, timeout: float = 30.0,
                 session: str | None = None) -> dict:
    """Block until the byte at addr equals the value ($hex/decimal accepted)."""
    s = _attach(session)
    return wait_for_mem(s, _ref(s, addr),
                        parse_number(equals), timeout)


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
                model: str = "c64") -> dict:
    """Package a .s/.bas/.prg into an artifact any VICE user can run: a .prg,
    or (when output ends in .d64/.d71/.d81) a disk image whose first file is
    the program so `x64sc out.d64` autostarts it. Returns the exact run
    command in "run"."""
    return package_program(Path(source), out=output, title=title, model=model)


@srv.tool()
def c64_run(source: str, session: str | None = None) -> dict:
    """Build/tokenize a .bas/.s/.prg as needed, then load and RUN it on the
    running C64. Registers assembly symbols on the session automatically."""
    s = _attach(session)
    src = Path(source).resolve()
    ext = src.suffix.lower()
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
        raise ValueError(f"cannot run {ext!r} files (use .bas, .s, or .prg)")
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
    """Type text into the running C64's keyboard buffer (\\n = RETURN).
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
    STOPPED there. KEY is one character or 'space'."""
    s = _attach(session)
    labels = session_labels(s)
    addr = _ref(s, at, labels)
    out = key_hold(s, key, addr, frames=frames, timeout=timeout)
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
    return {"image": image, "name": put_file(Path(image), Path(file), name)}


@srv.tool()
def c64_disk_get(image: str, name: str, dest: str) -> dict:
    """Copy a file off a disk image to the host."""
    return {"dest": str(get_file(Path(image), name, Path(dest)))}


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
    return {"booted": str(p)}


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
    """Run a declarative YAML test (boots its own fresh C64; see spec §8)."""
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
