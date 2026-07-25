"""The `c64` command-line interface. Thin layer over c64lib; all commands
support --json for machine-readable output."""

from __future__ import annotations

import json as _json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import click

from . import __version__
from .basic import BasicError, detokenize, tokenize
from .basic_lint import lint_source, tokenized_bytes
from .build import BuildError, build_asm
from .disasm import disassemble
from .disk import DiskError, create_image, get_file, list_files, put_file
from .machines import get_profile
from .ops import (
    call_routine,
    clear_checkpoints,
    find_bytes,
    live_screen_base,
    machine_state,
    parse_number,
    parse_ref,
    run_until,
    session_labels,
    staleness,
    wait_for_break,
    wait_for_mem,
    wait_for_text,
)
from .ops import (
    key_hold as ops_key_hold,
)
from .ops import (
    key_type as ops_key_type,
)
from .ops import (
    pc_symbol as _pc_symbol,
)
from .packaging import PackageError, package_program
from .protocol import CP_EXEC, CP_LOAD, CP_STORE
from .romdoc import identify, rom_labels
from .screen import (
    number_screen_text,
    read_screen_codes,
    read_screen_text,
    save_screenshot_png,
    screen_base,
)
from .session import Session, SessionError
from .symbols import format_addr
from .testing import TestError, load_test, program_test, run_test
from .text import ascii_to_petscii


def emit(ctx: click.Context, data: dict, human: str) -> None:
    if ctx.obj["json"]:
        click.echo(_json.dumps(data))
    else:
        click.echo(human)


def fail(ctx: click.Context, message: str, extra: dict | None = None) -> None:
    if ctx.obj["json"]:
        click.echo(_json.dumps({"error": message, **(extra or {})}))
    else:
        click.echo(f"error: {message}", err=True)
    sys.exit(1)


def attach(ctx: click.Context) -> Session:
    try:
        return Session.attach(ctx.obj["session"])
    except SessionError as e:
        fail(ctx, str(e))
        raise AssertionError("unreachable") from None


def resolve_ref(ctx: click.Context, labels: dict[str, int], ref: str,
                session=None) -> int:
    """parse_ref with CLI error reporting; pass the session so @row,col
    resolves against the machine's LIVE screen base (relocation-aware)."""
    kw = {}
    if session is not None:
        p = session.profile
        base = (live_screen_base(session) if "@" in str(ref)
                else p.screen_addr)
        kw = {"screen_base": base, "screen_width": p.screen_cols}
    try:
        return parse_ref(labels, ref, **kw)
    except (KeyError, ValueError) as e:
        fail(ctx, str(e))
        raise AssertionError("unreachable") from None


def _set_json(ctx: click.Context, param: click.Parameter, value: bool) -> bool:
    """Let --json be given after the subcommand as well as before it."""
    if value:
        root = ctx.find_root()
        if root.obj is None:
            root.obj = {"json": False, "session": None}
        root.obj["json"] = True
    return value


def _append_json_option(cmd: click.Command) -> None:
    """Give `cmd` a trailing --json option, unless it already declares one
    (true for `main`, which gets --json via its own group decorator)."""
    existing = {o for p in cmd.params for o in getattr(p, "opts", [])}
    if "--json" not in existing:
        cmd.params.append(click.Option(
            ["--json", "json_out"], is_flag=True, expose_value=False,
            callback=_set_json, help="Machine-readable JSON output."))


class JsonAwareCommand(click.Command):
    """A command that also accepts the global --json in trailing position."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _append_json_option(self)


class JsonAwareGroup(click.Group):
    """A group that also accepts --json directly, so groups that act as
    leaf commands themselves (e.g. `reg`, declared with
    invoke_without_command=True) support --json in trailing position too."""

    command_class = JsonAwareCommand
    group_class = type          # nested groups inherit this behaviour

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _append_json_option(self)


@click.group(cls=JsonAwareGroup)
@click.version_option(__version__, "--version", prog_name="c64",
                      message="%(prog)s %(version)s")
@click.option("--json", "json_out", is_flag=True,
              help="Machine-readable JSON output. Accepted here or after the "
                   "subcommand (`c64 screen --json`).")
@click.option("--session", "-s", "session_name", default=None,
              help="Target session name. Must come before the subcommand.")
@click.pass_context
def main(ctx: click.Context, json_out: bool, session_name: str | None) -> None:
    """c64-tools: develop and debug Commodore 64 software on VICE."""
    ctx.obj = {"json": json_out, "session": session_name}


@main.command(add_help_option=False)
@click.argument("command", nargs=-1)
@click.pass_context
def help(ctx: click.Context, command: tuple[str, ...]) -> None:
    """Show help for c64 or a specific command.

    With no argument, prints the top-level help. Otherwise give a command
    path to describe, e.g. `c64 help session start`.
    """
    node: click.Command = main
    sub_ctx = ctx.find_root()
    for name in command:
        nxt = node.get_command(sub_ctx, name) if isinstance(node, click.Group) else None
        if nxt is None:
            fail(ctx, f"no such command: {' '.join(command)}")
        sub_ctx = click.Context(nxt, info_name=name, parent=sub_ctx)
        node = nxt
    click.echo(node.get_help(sub_ctx))


@main.group()
def session() -> None:
    """Manage emulator sessions."""


@session.command("start")
@click.option("--model", default="c64", show_default=True,
              help="Machine model to boot: c64 (NTSC) or c64pal.")
@click.option("--name", "-s", default=None,
              help="Session name (defaults to the model name).")
@click.option("--headless", is_flag=True,
              help="Run without a VICE window (video/audio dummied).")
@click.option("--warp", is_flag=True,
              help="Run at maximum speed — recommended for automation.")
@click.option("--disk", "disk8", default=None, help="Attach a d64/d71/d81 image to drive 8.")
@click.pass_context
def session_start(ctx, model, name, headless, warp, disk8):
    """Boot a fresh emulated C64 and start its monitor daemon.

    Leaves the machine running; reports the new session's name, model, pid,
    and monitor port.
    """
    try:
        s = Session.launch(model=model, name=name, headless=headless, warp=warp, disk8=disk8)
    except (SessionError, DiskError, KeyError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"name": s.name, "model": s.model, "pid": s.pid, "port": s.port},
         f"started {s.model} session {s.name!r} (pid {s.pid}, monitor port {s.port})")


@session.command("ensure")
@click.option("--model", default="c64", show_default=True,
              help="Machine model to boot if no session is running.")
@click.option("--name", "-s", default=None,
              help="Session name to look for / start.")
@click.option("--headless", is_flag=True,
              help="Run without a VICE window (only if starting).")
@click.option("--warp", is_flag=True,
              help="Run at maximum speed (only if starting).")
@click.pass_context
def session_ensure(ctx, model, name, headless, warp):
    """Attach to a running session, or start one if none exists.

    Idempotent: exits 0 either way and reports which happened. Use it in
    scripts and as the recovery step after a dead daemon.
    """
    try:
        s, started = Session.ensure(model=model, name=name,
                                    headless=headless, warp=warp)
    except (SessionError, KeyError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"name": s.name, "model": s.model, "pid": s.pid, "port": s.port,
               "started": started},
         (f"started {s.model} session {s.name!r} (pid {s.pid}, monitor port {s.port})"
          if started else
          f"already running: {s.model} session {s.name!r} (pid {s.pid})"))


@session.command("list")
@click.pass_context
def session_list(ctx):
    """List the running sessions (dead ones are pruned)."""
    live = Session.list_all()
    emit(ctx,
         {"sessions": [{"name": s.name, "model": s.model, "pid": s.pid, "port": s.port}
                       for s in live]},
         "\n".join(f"{s.name}  {s.model}  pid={s.pid}  port={s.port}" for s in live)
         or "no sessions running")


@session.command("stop")
@click.argument("name", required=False)
@click.option("--name", "-s", "name_opt", default=None,
              help="Session to stop (same as the positional NAME).")
@click.pass_context
def session_stop(ctx, name, name_opt):
    """Stop a session, kill its daemon, and remove its registry record.

    NAME defaults to the current (or only) running session.
    """
    if name and name_opt and name != name_opt:
        fail(ctx, f"conflicting session names: positional {name!r} vs --name {name_opt!r}")
        return
    try:
        s = Session.attach(name or name_opt or ctx.obj["session"])
    except SessionError as e:
        fail(ctx, str(e))
        return
    s.stop()
    emit(ctx, {"stopped": s.name}, f"stopped session {s.name!r}")


@session.command("reset")
@click.option("--hard", is_flag=True, help="Power-cycle instead of soft reset.")
@click.pass_context
def session_reset(ctx, hard):
    """Reset the running machine (BASIC warm start); leaves it running."""
    s = attach(ctx)
    with s.monitor() as mon:
        mon.reset(hard=hard)
        mon.resume()
    emit(ctx, {"reset": s.name, "hard": hard},
         f"{'hard' if hard else 'soft'} reset {s.name!r} (machine running)")


def _hexdump(addr: int, data: bytes) -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{addr + i:04x}: {hexpart:<47}  {asciipart}")
    return "\n".join(lines)


def _decdump(addr: int, data: bytes) -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        lines.append(f"{addr + i:04x}: " + " ".join(str(b) for b in chunk))
    return "\n".join(lines)


@main.command("screen")
@click.option("--png", "png_path", default=None, type=click.Path(dir_okay=False),
              help="Save a PNG screenshot to this path instead of printing text.")
@click.option("--scale", default=1, show_default=True,
              help="Integer upscale factor for --png (nearest-neighbour).")
@click.option("--border", is_flag=True,
              help="Include the border in --png (shows $D020); default is the "
                   "320x200 inner screen only.")
@click.option("--codes", "codes_", is_flag=True,
              help="Print the raw screen-code matrix instead of decoded text.")
@click.option("--style", type=click.Choice(["unicode", "ascii"]),
              default="unicode", show_default=True,
              help="Text decoding: Unicode graphics or the legacy ASCII-safe set.")
@click.option("--ansi-reverse", is_flag=True,
              help="Wrap reverse-video cells in ANSI inverse escapes.")
@click.option("--numbered", is_flag=True,
              help="Prefix each row with its index and print a column ruler "
                   "(so you can read off @row,col references).")
@click.pass_context
def screen_cmd(ctx, png_path, scale, border, codes_, style, ansi_reverse,
                numbered):
    """Show the emulated screen — decoded text by default, a PNG with --png,
    or the raw screen-code matrix with --codes.

    Printing the screen is the preferred way to observe program output.
    Graphics decode to Unicode box/block/shape glyphs (mazes and sprites
    read naturally); --style ascii restores the conservative legacy
    mapping. --numbered adds row indices and a column ruler, so @row,col
    references can be read straight off the output. Does not disturb
    run/stop state.
    """
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            if png_path:
                w, h = save_screenshot_png(mon, png_path, scale=scale,
                                           border=border)
                emit(ctx, {"png": png_path, "width": w, "height": h},
                     f"wrote {w}x{h} screenshot to {png_path}")
            elif codes_:
                m = read_screen_codes(mon, s.profile)
                text = "\n".join(" ".join(f"{v:3d}" for v in row) for row in m)
                emit(ctx, {"codes": m}, text)
            else:
                text = read_screen_text(mon, s.profile, style, ansi_reverse)
                human = number_screen_text(text, s.profile.screen_cols) \
                    if numbered else text
                emit(ctx, {"text": text, "rows": text.splitlines()}, human)
        finally:
            mon.release()


@main.command("status")
@click.pass_context
def status_cmd(ctx):
    """Show the session and whether the machine is running or stopped.

    state comes from the session daemon's own tracking (no emulator
    traffic). Without a daemon it reports "unknown": a direct monitor
    connection stops the CPU, so the question is only answerable via the
    daemon.
    """
    s = attach(ctx)
    state = machine_state(s)
    stale = staleness(s)
    text = f"session {s.name} ({s.model}) state={state} pid={s.pid} port={s.port}"
    if s.loaded_prg:
        text += (f"\nprogram: {s.loaded_prg} (loaded "
                 f"{time.strftime('%H:%M:%S', time.localtime(s.loaded_at))})")
    for f in stale:
        text += f"\nSTALE (source changed since load): {f}"
    emit(ctx, {"name": s.name, "model": s.model, "pid": s.pid,
               "port": s.port, "state": state,
               "program": s.loaded_prg, "loaded_at": s.loaded_at,
               "stale": stale},
         text)


@main.group()
def mem() -> None:
    """Read and write emulated memory."""


@mem.command("read")
@click.argument("addr")
@click.argument("length", default="256")
@click.option("--decimal", "decimal", is_flag=True,
              help="Render values in decimal instead of a hex dump.")
@click.pass_context
def mem_read(ctx, addr, length, decimal):
    """Dump LENGTH bytes of memory from ADDR as a hex + ASCII dump.

    ADDR is $hex/0x/decimal, a symbol, symbol+offset (alienX+49), or a
    screen cell @row,col (model-aware); LENGTH (default 256) is decimal
    or $hex. --decimal renders decimal values instead. JSON output always
    includes both "hex" and "bytes" (a decimal int array). Does not
    disturb run/stop state.
    """
    s = attach(ctx)
    start = resolve_ref(ctx, session_labels(s), addr, session=s)
    n = parse_number(length)
    with s.monitor() as mon:
        try:
            data = mon.memory_read(start, n)
        finally:
            mon.release()
    emit(ctx, {"addr": start, "length": len(data), "hex": data.hex(),
               "bytes": list(data)},
         _decdump(start, data) if decimal else _hexdump(start, data))


@mem.command("write")
@click.argument("addr", required=False)
@click.argument("values", nargs=-1)
@click.option("--stdin", "from_stdin", is_flag=True,
              help="Read 'REF V1 V2 …' lines from stdin (batch writes).")
@click.pass_context
def mem_write(ctx, addr, values, from_stdin):
    """Write one or more byte VALUES to memory starting at ADDR.

    ADDR is $hex/0x/decimal, a symbol, symbol+offset, or @row,col; each
    VALUE is a byte ($hex/0x/decimal). With --stdin, reads one write per
    line ('REF V1 V2 …' — blank lines and #-comments skipped) instead of
    arguments: the heredoc-friendly batch form. Does not disturb run/stop
    state.
    """
    if from_stdin:
        if addr is not None or values:
            fail(ctx, "--stdin takes no ADDR/VALUES arguments")
            return
        lines = [ln.split() for ln in sys.stdin.read().splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]
        if not lines:
            fail(ctx, "--stdin: no writes on stdin")
            return
    elif addr is None or not values:
        fail(ctx, "give ADDR and VALUES, or use --stdin")
        return
    else:
        lines = [[addr, *values]]
    s = attach(ctx)
    labels = session_labels(s)
    writes = [(resolve_ref(ctx, labels, ln[0], session=s),
               bytes(parse_number(v) for v in ln[1:])) for ln in lines]
    with s.monitor() as mon:
        try:
            for start, data in writes:
                mon.memory_write(start, data)
        finally:
            mon.release()
    total = sum(len(d) for _, d in writes)
    emit(ctx, {"writes": [{"addr": a, "written": len(d)} for a, d in writes],
               "written": total},
         "\n".join(f"wrote {len(d)} byte(s) at ${a:04x}" for a, d in writes))


@mem.command("get")
@click.argument("addr")
@click.argument("length", default="1")
@click.pass_context
def mem_get(ctx, addr, length):
    """Print LENGTH byte values at ADDR in decimal (default: one byte).

    Pipe-friendly: the human output is bare space-separated decimal values
    with no address prefix. ADDR is $hex/0x/decimal, a symbol,
    symbol+offset, or @row,col. Does not disturb run/stop state.
    """
    s = attach(ctx)
    start = resolve_ref(ctx, session_labels(s), addr, session=s)
    n = parse_number(length)
    with s.monitor() as mon:
        try:
            data = mon.memory_read(start, n)
        finally:
            mon.release()
    emit(ctx, {"addr": start, "values": list(data)},
         " ".join(str(b) for b in data))


@mem.command("find")
@click.argument("values", nargs=-1, required=True)
@click.option("--start", "start", default="$0000", show_default=True,
              help="Search from this address ($hex/0x/decimal or symbol).")
@click.option("--length", "length", default="$10000", show_default=True,
              help="Number of bytes to search.")
@click.option("--limit", default=256, show_default=True,
              help="Stop after this many matches.")
@click.pass_context
def mem_find(ctx, values, start, length, limit):
    """Search memory for a byte pattern; print every match address.

    VALUES is one or more bytes ($hex/0x/decimal) forming the pattern.
    Searches [--start, --start + --length), clamped to 64 KB; stops at
    --limit matches (JSON "truncated": true when clipped). Does not
    disturb run/stop state.
    """
    s = attach(ctx)
    labels = session_labels(s)
    begin = resolve_ref(ctx, labels, start, session=s)
    n = parse_number(length)
    pattern = bytes(parse_number(v) for v in values)
    with s.monitor() as mon:
        try:
            matches, truncated = find_bytes(mon, begin, n, pattern, limit=limit)
        finally:
            mon.release()
    emit(ctx, {"pattern": list(pattern), "start": begin, "length": n,
               "matches": matches, "count": len(matches),
               "truncated": truncated},
         "\n".join(f"${a:04x}" for a in matches)
         + ("\n(truncated)" if truncated else "")
         if matches else "no matches")


@main.group(invoke_without_command=True)
@click.pass_context
def reg(ctx) -> None:
    """Show CPU registers (or `reg set NAME VALUE`)."""
    if ctx.invoked_subcommand is not None:
        return
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            regs = mon.registers()
        finally:
            mon.release()
    sym = _pc_symbol(session_labels(s), regs)
    human = "  ".join(f"{k}={v:04x}" for k, v in sorted(regs.items()))
    if sym:
        human += f"  ({sym})"
    state = machine_state(s)
    if state != "unknown":
        human += f"  [{state}]"
    emit(ctx, {"registers": regs, "pc_symbol": sym, "state": state}, human)


@reg.command("set")
@click.argument("name")
@click.argument("value")
@click.pass_context
def reg_set(ctx, name, value):
    """Set register NAME (PC, A, X, Y, or SP) to VALUE ($hex/0x/decimal)."""
    s = attach(ctx)
    v = parse_number(value)
    with s.monitor() as mon:
        try:
            mon.set_register(name, v)
        finally:
            mon.release()
    emit(ctx, {"register": name.upper(), "value": v},
         f"{name.upper()} = ${v:04x}")


@main.command("build")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Output .prg path (defaults next to SOURCE).")
@click.option("--model", default="c64", show_default=True,
              help="Target model — selects the BASIC load address.")
@click.pass_context
def build_cmd(ctx, source, output, model):
    """Assemble 6502 SOURCE to a .prg (+ VICE label file) with ca65/ld65.

    Offline; no session required.
    """
    try:
        profile = get_profile(model)
        res = build_asm(source, out_prg=output, basic_start=profile.basic_start)
    except (BuildError, KeyError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"prg": str(res.prg), "labels": str(res.labels)},
         f"built {res.prg} (labels: {res.labels})")


@main.command("package")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              default=None,
              help="Artifact path; .d64/.d71/.d81 build an autostart-first "
                   "disk image, .prg (or omitted) just the program file.")
@click.option("--title", default=None,
              help="CBM file/disk name (uppercased, max 16 chars; defaults "
                   "to the source stem).")
@click.option("--model", default="c64", show_default=True,
              help="Target model — selects the BASIC load address and is "
                   "pinned in the reported run command.")
@click.pass_context
def package_cmd(ctx, source, output, title, model):
    """Package SOURCE into an artifact any VICE user can run.

    The reported run command pins the model: stock x64sc boots its own
    default (PAL) machine, so both profiles pin their video standard
    (-ntsc / -pal) explicitly.
    """
    try:
        res = package_program(source, out=output, title=title, model=model)
    except (BuildError, BasicError, DiskError, PackageError, KeyError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, res,
         f"packaged {res['title']!r} -> {res['image'] or res['prg']}\n"
         f"run it with: {res['run']}")


@main.group()
def basic() -> None:
    """Tokenize, detokenize, and type Commodore BASIC programs."""


@basic.command("tokenize")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Output .prg path (defaults to SOURCE with a .prg suffix).")
@click.option("--model", default="c64", show_default=True,
              help="Model — selects the BASIC version.")
@click.pass_context
def basic_tokenize(ctx, source, output, model):
    """Tokenize a BASIC .bas SOURCE into a .prg (offline; no session)."""
    out = output or source.with_suffix(".prg")
    try:
        profile = get_profile(model)
        prg = tokenize(source, out, profile.basic_version)
    except (BasicError, KeyError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"prg": str(prg)}, f"tokenized to {prg}")


@basic.command("detokenize")
@click.argument("prg", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--model", default="c64", show_default=True,
              help="Model — selects the BASIC version.")
@click.pass_context
def basic_detokenize(ctx, prg, model):
    """Detokenize a .prg back into a BASIC listing (offline; no session)."""
    try:
        profile = get_profile(model)
        listing = detokenize(prg, profile.basic_version)
    except (BasicError, KeyError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"listing": listing}, listing.rstrip("\n"))


@basic.command("check")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def basic_check(ctx, source):
    """Statically check a BASIC V2 SOURCE for errors petcat accepts.

    Catches keyword fusion (`total=5` really tokenizes as `TO TAL=5`), missing
    GOTO/GOSUB targets, out-of-range POKEs, non-V2 keywords and oversize
    programs — before a run cycle. Offline; no session. Exits 1 if any
    error-severity issue is found.
    """
    text = source.read_text()
    issues = lint_source(text)
    errors = sum(1 for i in issues if i.severity == "error")
    lines = [f"{i.severity.upper()} {i.rule}: "
             f"{'line ' + str(i.line) if i.line is not None else 'file'}: {i.message}"
             for i in issues]
    emit(ctx, {"issues": [asdict(i) for i in issues], "errors": errors,
               "warnings": len(issues) - errors,
               "tokenized_bytes": tokenized_bytes(text)},
         "\n".join(lines) if lines else "clean")
    if errors:
        sys.exit(1)


@basic.command("type")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--run", "do_run", is_flag=True, help="Type RUN after the program.")
@click.pass_context
def basic_type(ctx, source, do_run):
    """Type a BASIC program into the running C64 via the keyboard."""
    s = attach(ctx)
    text = source.read_text()
    if not text.endswith("\n"):
        text += "\n"
    if do_run:
        text += "run\n"
    try:
        petscii = ascii_to_petscii(text)
    except ValueError as e:
        fail(ctx, str(e))
        return
    with s.monitor() as mon:
        try:
            mon.keyboard_feed(petscii)
        finally:
            mon.release()
    emit(ctx, {"typed": str(source), "run": do_run},
         f"typed {source}{' and RUN' if do_run else ''}")


@main.command("load")
@click.argument("prg", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--run/--no-run", "do_run", default=True, show_default=True,
              help="Type RUN after loading.")
@click.option("--symbols", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None, help="Register a VICE label file for symbolic debugging.")
@click.pass_context
def load_cmd(ctx, prg, do_run, symbols):
    """Load (and by default RUN) a .prg on the running C64 via autostart."""
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            mon.autostart(prg.resolve(), run=do_run)
        finally:
            mon.resume()
    if symbols:
        s.set_labels_path(str(symbols.resolve()))
    s.record_loaded(prg, [prg])
    emit(ctx, {"loaded": str(prg.resolve()), "run": do_run,
               "symbols": str(symbols.resolve()) if symbols else None},
         f"autostarted {prg}{'' if do_run else ' (no RUN)'}")


@main.command("run")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def run_cmd(ctx, source):
    """Build/tokenize SOURCE as needed, then load and RUN it.

    `.bas` is tokenized, `.s` is assembled and its labels registered on the
    session (so symbols work in later commands), `.prg` is loaded directly.
    Leaves the machine running.
    """
    s = attach(ctx)
    src = source.resolve()
    ext = src.suffix.lower()
    labels = None
    deps: tuple = ()
    try:
        if ext == ".prg":
            prg = src
        elif ext == ".bas":
            prg = tokenize(src, src.with_suffix(".prg"), s.profile.basic_version)
        elif ext == ".s":
            res = build_asm(src, basic_start=s.profile.basic_start)
            prg, labels, deps = res.prg, res.labels, res.deps
        else:
            fail(ctx, f"don't know how to run {ext!r} files (use .bas, .s, or .prg)")
            return
    except (BasicError, BuildError) as e:
        msg = str(e)
        if s.loaded_prg:
            msg += (f"\nemulator still running the PREVIOUS program "
                    f"({s.loaded_prg}, loaded "
                    f"{time.strftime('%H:%M:%S', time.localtime(s.loaded_at))})"
                    " — nothing was reloaded")
        fail(ctx, msg)
        return
    with s.monitor() as mon:
        try:
            mon.autostart(prg, run=True)
        finally:
            mon.resume()
    if labels:
        s.set_labels_path(str(labels))
    s.record_loaded(prg, deps if deps else [src])
    emit(ctx, {"source": str(src), "prg": str(prg),
               "symbols": str(labels) if labels else None},
         f"running {prg}")


@main.group("break")
def break_() -> None:
    """Manage breakpoints (VICE exec checkpoints)."""


@break_.command("add")
@click.argument("ref")
@click.option("--condition", default=None, help="VICE condition, e.g. 'A != 0'.")
@click.option("--temporary", is_flag=True, help="Delete the breakpoint after it fires once.")
@click.option("--once", is_flag=True, help="Alias for --temporary.")
@click.pass_context
def break_add(ctx, ref, condition, temporary, once):
    """Set an execution breakpoint at REF (an address or a symbol)."""
    temporary = temporary or once
    s = attach(ctx)
    labels = session_labels(s)
    addr = resolve_ref(ctx, labels, ref, session=s)
    with s.monitor() as mon:
        try:
            ck = mon.checkpoint_set(addr, op=CP_EXEC, temporary=temporary)
            if condition:
                mon.condition_set(ck.number, condition)
        finally:
            mon.release()
    emit(ctx, {"id": ck.number, "address": format_addr(labels, addr),
               "condition": condition, "temporary": temporary},
         f"breakpoint #{ck.number} at {format_addr(labels, addr)}"
         + (f" when {condition}" if condition else ""))


def _op_name(op: int) -> str:
    parts = []
    if op & CP_EXEC:
        parts.append("exec")
    if op & CP_LOAD:
        parts.append("load")
    if op & CP_STORE:
        parts.append("store")
    return "|".join(parts)


@break_.command("list")
@click.pass_context
def break_list(ctx):
    """List all checkpoints (breakpoints and watchpoints) with hit counts."""
    s = attach(ctx)
    labels = session_labels(s)
    with s.monitor() as mon:
        try:
            cks = mon.checkpoint_list()
        finally:
            mon.release()
    rows = [{"id": ck.number, "address": format_addr(labels, ck.start),
             "end": ck.end, "op": _op_name(ck.op), "enabled": ck.enabled,
             "hits": ck.hit_count, "has_condition": ck.has_condition}
            for ck in cks]
    human = "\n".join(
        f"#{r['id']}  {r['address']}  {r['op']}"
        f"  {'on' if r['enabled'] else 'off'}  hits={r['hits']}"
        + ("  [cond]" if r["has_condition"] else "")
        for r in rows
    ) or "no breakpoints"
    emit(ctx, {"breakpoints": rows}, human)


@break_.command("remove")
@click.argument("ck_id", type=int)
@click.pass_context
def break_remove(ctx, ck_id):
    """Remove checkpoint CK_ID (its number from `c64 break list`)."""
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            mon.checkpoint_delete(ck_id)
        finally:
            mon.release()
    emit(ctx, {"removed": ck_id}, f"removed #{ck_id}")


@break_.command("enable")
@click.argument("ck_id", type=int)
@click.pass_context
def break_enable(ctx, ck_id):
    """Enable checkpoint CK_ID."""
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            mon.checkpoint_toggle(ck_id, True)
        finally:
            mon.release()
    emit(ctx, {"enabled": ck_id}, f"enabled #{ck_id}")


@break_.command("disable")
@click.argument("ck_id", type=int)
@click.pass_context
def break_disable(ctx, ck_id):
    """Disable checkpoint CK_ID without removing it."""
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            mon.checkpoint_toggle(ck_id, False)
        finally:
            mon.release()
    emit(ctx, {"disabled": ck_id}, f"disabled #{ck_id}")


@break_.command("clear")
@click.pass_context
def break_clear(ctx):
    """Remove ALL breakpoints (exec checkpoints). Watchpoints are kept.

    Checkpoints persist across `c64 run`/rebuilds by design — clear stale
    ones or duplicates accumulate.
    """
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            removed = clear_checkpoints(mon, CP_EXEC)
        finally:
            mon.release()
    emit(ctx, {"removed": removed, "count": len(removed)},
         f"removed {len(removed)} breakpoint(s)")


@main.group()
def watch() -> None:
    """Manage watchpoints (VICE load/store checkpoints)."""


@watch.command("add")
@click.argument("ref")
@click.option("--load", "on_load", is_flag=True, help="Break on reads.")
@click.option("--store", "on_store", is_flag=True, help="Break on writes.")
@click.option("--length", default=1, show_default=True, help="Number of bytes to watch.")
@click.pass_context
def watch_add(ctx, ref, on_load, on_store, length):
    """Set a watchpoint on the bytes at REF (default: both load and store)."""
    s = attach(ctx)
    labels = session_labels(s)
    addr = resolve_ref(ctx, labels, ref, session=s)
    op = (CP_LOAD if on_load else 0) | (CP_STORE if on_store else 0)
    if not op:
        op = CP_LOAD | CP_STORE
    with s.monitor() as mon:
        try:
            ck = mon.checkpoint_set(addr, addr + length - 1, op=op)
        finally:
            mon.release()
    emit(ctx, {"id": ck.number, "address": format_addr(labels, addr),
               "length": length, "op": _op_name(op)},
         f"watchpoint #{ck.number} at {format_addr(labels, addr)} len={length} ({_op_name(op)})")


@watch.command("clear")
@click.pass_context
def watch_clear(ctx):
    """Remove ALL watchpoints (load/store checkpoints). Breakpoints are kept."""
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            removed = clear_checkpoints(mon, CP_LOAD | CP_STORE,
                                        exclude_mask=CP_EXEC)
        finally:
            mon.release()
    emit(ctx, {"removed": removed, "count": len(removed)},
         f"removed {len(removed)} watchpoint(s)")


break_.add_command(break_remove, "rm")
watch.add_command(break_remove, "remove")
watch.add_command(break_remove, "rm")


def _emit_stopped_regs(ctx, labels, regs, extra=None):
    sym = _pc_symbol(labels, regs)
    human = "  ".join(f"{k}={v:04x}" for k, v in sorted(regs.items()))
    if sym:
        human += f"  ({sym})"
    data = {"registers": regs, "pc_symbol": sym, "stopped": True}
    if extra:
        data.update(extra)
    emit(ctx, data, human + "  [stopped]")


@main.command("step")
@click.argument("count", default="1")
@click.option("--over", is_flag=True, help="Step over JSR subroutines.")
@click.pass_context
def step_cmd(ctx, count, over):
    """Execute N instructions; the machine stays stopped."""
    s = attach(ctx)
    labels = session_labels(s)
    with s.monitor() as mon:
        regs = mon.step(parse_number(count), over=over)
    _emit_stopped_regs(ctx, labels, regs)


@main.command("finish")
@click.pass_context
def finish_cmd(ctx):
    """Run until the current subroutine returns; stays stopped."""
    s = attach(ctx)
    labels = session_labels(s)
    with s.monitor() as mon:
        regs = mon.finish()
    _emit_stopped_regs(ctx, labels, regs)


@main.command("continue")
@click.pass_context
def continue_cmd(ctx):
    """Resume execution."""
    s = attach(ctx)
    with s.monitor() as mon:
        mon.resume()
    emit(ctx, {"running": True}, "running")


@main.command("until")
@click.argument("ref")
@click.option("--count", default=1, show_default=True,
              help="Stop at the Nth arrival at REF (frame stepping on a loop label).")
@click.option("--timeout", default=30.0, show_default=True,
              help="Give up after this many seconds.")
@click.pass_context
def until_cmd(ctx, ref, count, timeout):
    """Run until REF (address or symbol) is executed; stays stopped there.

    With --count N, REF must be reached N times — deterministic frame
    stepping when REF is the program's main-loop label."""
    s = attach(ctx)
    labels = session_labels(s)
    addr = resolve_ref(ctx, labels, ref, session=s)
    out = run_until(s, addr, timeout, count=count)
    if out["registers"] is None:
        where = format_addr(labels, addr)
        fail(ctx,
             f"timeout: {where} reached {out['reached']}/{count} time(s) in "
             f"{timeout}s — machine left RUNNING, checkpoint removed. If the "
             f"program can branch away from {where} (death, menu, pause), it "
             "may never be reached again; set a breakpoint at a code path "
             "that must still execute and use 'c64 wait --break'.",
             extra={"reached": out["reached"], "count": count,
                    "machine": "running", "checkpoint_removed": True})
        return
    _emit_stopped_regs(ctx, labels, out["registers"], extra={"count": count})


@main.command("call")
@click.argument("ref")
@click.option("--a", "a_", default=None, help="A register on entry ($hex/decimal).")
@click.option("--x", "x_", default=None, help="X register on entry.")
@click.option("--y", "y_", default=None, help="Y register on entry.")
@click.option("--timeout", default=30.0, show_default=True,
              help="Give up after this many seconds.")
@click.pass_context
def call_cmd(ctx, ref, a_, x_, y_, timeout):
    """JSR the routine at REF in isolation and stop when it returns.

    Emulates a JSR: fake return address on the stack, optional A/X/Y on
    entry, runs until the routine's own RTS. The machine ends STOPPED so
    registers and memory hold the routine's results — the unit-test
    primitive (poke inputs first, call, then inspect). On timeout the
    machine is left running.
    """
    s = attach(ctx)
    labels = session_labels(s)
    addr = resolve_ref(ctx, labels, ref, session=s)
    regs_in = {k: parse_number(v) for k, v in
               (("a", a_), ("x", x_), ("y", y_)) if v is not None}
    out = call_routine(s, addr, a=regs_in.get("a"), x=regs_in.get("x"),
                       y=regs_in.get("y"), timeout=timeout)
    if not out["fired"]:
        fail(ctx, f"call {format_addr(labels, addr)}: never returned in "
                  f"{timeout}s — machine left running (runaway routine? "
                  "check the address is a subroutine ending in RTS)",
             extra={"machine": "running"})
        return
    _emit_stopped_regs(ctx, labels, out["registers"],
                       extra={"called": format_addr(labels, addr)})


@main.command("wait")
@click.option("--text", "text_cond", default=None, help="Wait for screen text.")
@click.option("--mem", "mem_cond", default=None, help="ADDR=VALUE, e.g. '$1000=42'.")
@click.option("--break", "break_cond", is_flag=False, flag_value="any",
              default=None,
              help="Wait for a checkpoint hit; give an ID to wait for that "
                   "checkpoint only (leftover breakpoints can't intercept).")
@click.option("--since", is_flag=True,
              help="With --text: fire only on an occurrence appearing AFTER "
                   "this command starts. For a gapped appearance; an instant "
                   "reply can print first and be swallowed by the baseline — "
                   "anchor a cell with --mem '@row,col' for turn-by-turn play.")
@click.option("--timeout", default=30.0, show_default=True,
              help="Give up after this many seconds.")
@click.pass_context
def wait_cmd(ctx, text_cond, mem_cond, break_cond, since, timeout):
    """Block until exactly one condition fires; report which one.

    Give exactly one of --text, --mem, or --break. This is the primary
    synchronization primitive for scripted use. Exit 1 on timeout.
    """
    if sum(bool(x) for x in (text_cond, mem_cond, break_cond)) != 1:
        fail(ctx, "give exactly one of --text, --mem, --break")
        return
    if since and not text_cond:
        fail(ctx, "--since only applies to --text")
        return
    s = attach(ctx)
    labels = session_labels(s)

    if break_cond:
        try:
            number = None if break_cond == "any" else int(break_cond)
        except ValueError:
            fail(ctx, f"--break takes a checkpoint id (integer), got {break_cond!r}")
            return
        out = wait_for_break(s, timeout, number=number)
        if not out.get("fired"):
            fail(ctx, f"timeout: no checkpoint hit within {timeout}s — machine "
                      "left running; your checkpoints remain set.",
                 extra={"machine": "running"})
            return
        sym = _pc_symbol(labels, out.pop("registers"))
        emit(ctx, {"fired": "break", "checkpoint": out["checkpoint"],
                   "pc": out["pc"], "pc_symbol": sym, "elapsed": out["elapsed"]},
             f"breakpoint #{out['checkpoint']} hit at {format_addr(labels, out['pc'])}")
        return

    if text_cond:
        out = wait_for_text(s, text_cond, timeout, since=since)
        if out["fired"]:
            emit(ctx, {"fired": "text", "elapsed": out["elapsed"]}, "text condition met")
            return
        fail(ctx, f"timeout after {timeout}s waiting for --text {text_cond}"
                  f"; last screen:\n{out['screen']}",
             extra={"machine": "running"})
        return

    try:
        addr_s, _, val_s = mem_cond.partition("=")
        addr = resolve_ref(ctx, labels, addr_s.strip(), session=s)
        want = parse_number(val_s.strip())
    except ValueError:
        fail(ctx, f"bad --mem condition {mem_cond!r}; use ADDR=VALUE")
        return
    out = wait_for_mem(s, addr, want, timeout)
    if out["fired"]:
        emit(ctx, {"fired": "mem", "elapsed": out["elapsed"]}, "mem condition met")
        return
    fail(ctx, f"timeout after {timeout}s waiting for --mem {mem_cond}",
         extra={"machine": "running"})


@main.group()
def disk() -> None:
    """Create and manipulate d64/d71/d81 disk images."""


@disk.command("create")
@click.argument("image", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--label", default="disk", show_default=True,
              help="Disk name shown in the directory header.")
@click.option("--id", "disk_id", default="00", show_default=True,
              help="Two-character disk ID.")
@click.pass_context
def disk_create(ctx, image, label, disk_id):
    """Create an empty disk image (d64/d71/d81, inferred from the extension)."""
    try:
        img = create_image(image, label=label, disk_id=disk_id)
    except DiskError as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"image": str(img), "label": label}, f"created {img} (label {label!r})")


@disk.command("ls")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def disk_ls(ctx, image):
    """List the directory of a disk IMAGE (offline; no session)."""
    try:
        d = list_files(image)
    except DiskError as e:
        fail(ctx, str(e))
        return
    human = "\n".join(
        [f'"{d["label"]}"']
        + [f"{f['blocks']:>4}  {f['name']:<18} {f['type']}" for f in d["files"]]
        + [f"{d['blocks_free']} blocks free"]
    )
    emit(ctx, d, human)


@disk.command("put")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("name", required=False, default=None)
@click.pass_context
def disk_put(ctx, image, file, name):
    """Copy a host FILE into IMAGE, optionally under CBM NAME.

    NAME defaults to the file's stem. Offline; no session.
    """
    try:
        cbm = put_file(image, file, name)
    except DiskError as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"image": str(image), "name": cbm}, f"wrote {file} as {cbm!r}")


@disk.command("get")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("name")
@click.argument("dest", required=False, default=None,
                type=click.Path(dir_okay=False, path_type=Path))
@click.pass_context
def disk_get(ctx, image, name, dest):
    """Extract file NAME from IMAGE to DEST (defaults to NAME.prg).

    Offline; no session.
    """
    dest = dest or Path(f"{name}.prg")
    try:
        out = get_file(image, name, dest)
    except DiskError as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"image": str(image), "name": name, "dest": str(out)},
         f"read {name!r} to {out}")


@disk.command("boot")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def disk_boot(ctx, image):
    """Attach IMAGE to the running C64 and LOAD+RUN its first file."""
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            mon.autostart(image.resolve(), run=True)
        finally:
            mon.resume()
    emit(ctx, {"booted": str(image.resolve())}, f"booting {image}")


@main.group()
def rom() -> None:
    """Identify and disassemble the machine's ROMs (read from the live machine)."""


@rom.command("info")
@click.pass_context
def rom_info(ctx):
    """Identify the loaded ROM set — BASIC/KERNAL/chargen names and hashes."""
    s = attach(ctx)
    with s.monitor() as mon:
        try:
            info = identify(mon)
        finally:
            mon.release()
    human = "\n".join(
        [f"basic:   {info['basic']}", f"kernal:  {info['kernal']}",
         f"chargen: {info['chargen']}"]
        + [f"hash {k}: {v}" for k, v in info["hashes"].items()]
    )
    emit(ctx, info, human)


@rom.command("disasm")
@click.argument("start")
@click.argument("length", default="32")
@click.pass_context
def rom_disasm(ctx, start, length):
    """Disassemble live memory with ROM + session label annotations.

    START is an address or symbol (e.g. CHROUT); LENGTH defaults to 32
    bytes. Does not disturb run/stop state.
    """
    s = attach(ctx)
    labels = {**rom_labels(s.profile.basic_version), **session_labels(s)}
    addr = resolve_ref(ctx, labels, start, session=s)
    n = parse_number(length)
    with s.monitor() as mon:
        try:
            data = mon.memory_read(addr, n)
        finally:
            mon.release()
    lines = disassemble(data, addr, labels)
    emit(ctx, {"start": addr, "length": n, "lines": lines}, "\n".join(lines))


@main.group("test")
def test_() -> None:
    """Run declarative YAML tests and example programs on a fresh emulated C64."""


def _emit_test_results(ctx, results) -> None:
    all_pass = all(r.passed for r in results)
    lines = []
    for r in results:
        lines.append(f"{'PASS' if r.passed else 'FAIL'}  {r.name}  "
                     f"({r.machine}, {r.elapsed}s)")
        for st in r.steps:
            lines.append(f"  {'ok  ' if st.ok else 'FAIL'} step {st.index} "
                         f"{st.kind}: {st.detail}")
        if not r.passed:
            lines.append("  --- screen at failure ---")
            lines.extend(f"  | {ln}" for ln in r.screen.splitlines())
    emit(ctx, {"passed": all_pass, "tests": [r.to_dict() for r in results]},
         "\n".join(lines))
    if not all_pass:
        sys.exit(1)


@test_.command("run")
@click.argument("yaml_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def test_run(ctx, yaml_file):
    """Run one YAML test file (format documented in docs/cli.md).

    Boots its own fresh headless+warp session, loads the program, then runs
    the wait/key/poke/until/call/assert steps fail-fast. Exit 1 if it fails.
    """
    try:
        spec = load_test(yaml_file)
        result = run_test(spec)
    except (TestError, KeyError, BasicError, BuildError, SessionError) as e:
        fail(ctx, str(e))
        return
    _emit_test_results(ctx, [result])


@test_.command("programs")
@click.argument("directory", default="tests/programs",
                type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.pass_context
def test_programs(ctx, directory):
    """Run every example program in DIRECTORY as a generated test.

    DIRECTORY defaults to `tests/programs`; an example program is any
    subdirectory holding an `expect.txt`. Exit 1 if any program fails.
    """
    program_dirs = sorted(d for d in directory.iterdir() if (d / "expect.txt").exists())
    if not program_dirs:
        fail(ctx, f"no example programs found in {directory}")
        return
    results = []
    for d in program_dirs:
        try:
            results.append(run_test(program_test(d)))
        except (TestError, KeyError, BasicError, BuildError, SessionError) as e:
            fail(ctx, f"{d.name}: {e}")
            return
    _emit_test_results(ctx, results)


@main.group()
def key() -> None:
    """Feed keyboard input to the running C64."""


@key.command("type")
@click.argument("text")
@click.pass_context
def key_type(ctx, text):
    """Type TEXT into the running C64 (\\n = RETURN, whether it reaches the
    CLI as a real newline or as the two characters backslash-n; write \\\\
    for a literal backslash). For whole programs
    prefer `c64 basic type`; this is for interactive input and menus.
    Buffered keys never touch the live current-key state — games reading $CB
    need `c64 key hold`."""
    s = attach(ctx)
    try:
        out = ops_key_type(s, text)
    except ValueError as e:
        fail(ctx, str(e))
        return
    emit(ctx, out, f"typed {text!r}")


@key.command("hold")
@click.argument("keyname", metavar="KEY")
@click.option("--at", "at_ref", required=True, metavar="REF",
              help="Frame anchor: a label or address executed once per game "
                   "tick (your main-loop label).")
@click.option("--frames", default=1, show_default=True,
              help="How many ticks to hold the key across.")
@click.option("--timeout", default=30.0, show_default=True,
              help="Per-frame wait limit, seconds.")
@click.pass_context
def key_hold(ctx, keyname, at_ref, frames, timeout):
    """Hold KEY down for N game ticks by re-poking $CB before each one.

    Drives games that read the live current-key state: writes the key's
    matrix code to $CB, runs to REF, repeats — the machine ends STOPPED
    at REF (continue with `c64 continue`). KEY is one character, or
    `space`. For a deterministic first frame, stop at REF first
    (`c64 until REF`).
    """
    s = attach(ctx)
    labels = session_labels(s)
    addr = resolve_ref(ctx, labels, at_ref, session=s)
    try:
        out = ops_key_hold(s, keyname, addr, frames=frames, timeout=timeout)
    except ValueError as e:
        fail(ctx, str(e))
        return
    if out["registers"] is None:
        fail(ctx, f"timeout: only {out['frames']}/{frames} frame(s) reached "
                  f"{format_addr(labels, addr)} — machine left RUNNING, "
                  "checkpoint removed. Is REF really executed every tick?",
             extra={"frames": out["frames"], "requested": frames})
        return
    _emit_stopped_regs(ctx, labels, out["registers"],
                       extra={"frames": out["frames"]})


@main.group()
def sprite() -> None:
    """Inspect, render, and convert VIC-II sprites."""


def _parse_sprite_art(text: str) -> list[list[str]]:
    """Split FILE contents into blank-line-separated groups of rows.

    A separator is a truly EMPTY line (no characters at all) — a row of
    all-background pixels is a legitimate 12/24-char row of spaces, and
    must not be confused with the blank line between sprites. Rows are
    kept exactly as written (no stripping); trailing spaces are
    significant (background pixels).
    """
    sprites: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line == "":
            if current:
                sprites.append(current)
                current = []
        else:
            current.append(line)
    if current:
        sprites.append(current)
    return sprites


def _sprite_states(s):
    from .sprites import read_sprite_states
    with s.monitor() as mon:
        try:
            base = screen_base(mon)
            return read_sprite_states(mon, base)
        finally:
            mon.release()


def _sprite_index(ctx, n) -> int:
    if not 0 <= n <= 7:
        fail(ctx, f"sprite index {n} outside 0-7")
    return n


def _sprite_shape(ctx, s, n, block):
    """(data, state, shared, block_addr) for sprite N (or an explicit block)."""
    from .sprites import read_sprite_block
    states, shared = _sprite_states(s)
    st = states[_sprite_index(ctx, n)]
    addr = resolve_ref(ctx, session_labels(s), block, session=s) \
        if block else st.block_addr
    with s.monitor() as mon:
        try:
            data = read_sprite_block(mon, addr)
        finally:
            mon.release()
    return data, st, shared, addr


@sprite.command("status")
@click.pass_context
def sprite_status(ctx):
    """Decode $D000-$D02E and the sprite pointers into a per-sprite table.

    State-preserving; relocation-aware (pointers read at the live screen
    base + $3F8).
    """
    from dataclasses import asdict
    s = attach(ctx)
    states, shared = _sprite_states(s)
    lines = []
    for st in states:
        flags = "".join((
            " MC" if st.multicolor else "",
            " XX" if st.expand_x else "",
            " XY" if st.expand_y else "",
            " BG" if st.behind_text else "",
        ))
        lines.append(
            f"{st.index}  {'on ' if st.enabled else 'off'}  "
            f"x={st.x:<3} y={st.y:<3}  ptr={st.pointer:<3} @${st.block_addr:04x}"
            f"  color={st.color}{flags}")
    lines.append(f"shared: bg={shared['background']} border={shared['border']}"
                 f" mc1={shared['mc_color1']} mc2={shared['mc_color2']}")
    emit(ctx, {"sprites": [asdict(st) for st in states], "shared": shared},
         "\n".join(lines))


@sprite.command("show")
@click.argument("index", type=int)
@click.option("--block", default=None,
              help="Dump an explicit 63-byte block (address/symbol) instead "
                   "of the sprite's current pointer target.")
@click.pass_context
def sprite_show(ctx, index, block):
    """Render a sprite's shape as ASCII art (multicolor pairs double-wide)."""
    from .sprites import sprite_ascii
    s = attach(ctx)
    data, st, _, addr = _sprite_shape(ctx, s, index, block)
    rows = sprite_ascii(data, st.multicolor)
    emit(ctx, {"rows": rows, "block_addr": addr, "multicolor": st.multicolor},
         f"sprite {index} @${addr:04x}" + (" (multicolor)" if st.multicolor else "")
         + "\n" + "\n".join(rows))


@sprite.command("png")
@click.argument("index", type=int)
@click.option("--out", "-o", "out_path", required=True,
              help="Output PNG path.")
@click.option("--scale", default=8, show_default=True,
              help="Integer nearest-neighbour upscale.")
@click.option("--block", default=None,
              help="Render an explicit 63-byte block instead of the "
                   "sprite's current pointer target.")
@click.pass_context
def sprite_png(ctx, index, out_path, scale, block):
    """Render a sprite's shape to a PNG (colors from the live registers)."""
    from .sprites import sprite_image
    s = attach(ctx)
    data, st, shared, _ = _sprite_shape(ctx, s, index, block)
    img = sprite_image(data, st, shared, scale=scale)
    img.save(out_path, format="PNG")
    emit(ctx, {"png": out_path, "width": img.width, "height": img.height},
         f"wrote {out_path} ({img.width}x{img.height})")


@sprite.command("from-png")
@click.argument("image", type=click.Path())
@click.option("--out", "-o", "out_path", default=None,
              help="Write the ca65 .byte rows to this file instead of stdout.")
@click.option("--multicolor", is_flag=True,
              help="Quantize to multicolor pairs instead of hires 1-bit.")
@click.pass_context
def sprite_from_png(ctx, image, out_path, multicolor):
    """Convert any PNG into ready-to-paste sprite .byte rows.

    Needs no session. The image is resized to sprite resolution; hires
    sets pixels darker than 50% luminance, multicolor quantizes to the
    C64 palette (mapping recorded in the emitted header). Verify the
    result against intent with `c64 sprite show`/`c64 sprite png`.
    """
    from PIL import Image, UnidentifiedImageError

    from .sprites import sprite_from_image
    try:
        img = Image.open(image)
    except (FileNotFoundError, UnidentifiedImageError) as e:
        fail(ctx, f"cannot read image {image!r}: {e}")
        return
    data, lines = sprite_from_image(img, multicolor=multicolor)
    text = "\n".join(lines) + "\n"
    if out_path:
        Path(out_path).write_text(text)
    emit(ctx, {"rows": lines, "bytes": list(data), "out": out_path},
         text if not out_path else f"wrote {out_path}")


@sprite.command("encode")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--hires", is_flag=True,
              help="Encode as hires (1 bit/pixel) instead of the default multicolor pairs.")
@click.option("--format", "fmt", type=click.Choice(["asm", "basic"]), default="asm",
              show_default=True, help="Rendering for the human/text output.")
@click.option("--out", "-o", "out_path", default=None,
              help="Write the rendered rows to this file instead of stdout.")
@click.pass_context
def sprite_encode(ctx, file, hires, fmt, out_path):
    """Encode ASCII-art sprite(s) from FILE into 63 sprite bytes each.

    FILE holds one or more 21-row sprites, separated by a blank line. Rows
    use the friendly authoring legend (multicolor ' .#+', hires ' #') or
    the glyphs `c64 sprite show` emits ('·▒█▓', '█·') — `show` output
    round-trips straight back through `encode`. Needs no session; pairs
    with `c64 sprite from-png` (image input instead of ASCII art) and
    `c64 sprite show` (the inverse: bytes back to ASCII).
    """
    from .sprites import encode_sprite, format_bytes
    blocks = _parse_sprite_art(file.read_text())
    if not blocks:
        fail(ctx, f"no sprite art found in {file}")
        return
    try:
        sprites = [encode_sprite(rows, multicolor=not hires) for rows in blocks]
    except ValueError as e:
        fail(ctx, str(e))
        return
    text = "\n\n".join(
        format_bytes(data, fmt, index=i, multicolor=not hires)
        for i, data in enumerate(sprites)) + "\n"
    if out_path:
        Path(out_path).write_text(text)
    emit(ctx, {"sprites": [list(data) for data in sprites]},
         text if not out_path else f"wrote {out_path}")
