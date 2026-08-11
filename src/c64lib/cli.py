"""The `c64` command-line interface. Thin layer over c64lib; all commands
support --json for machine-readable output."""

from __future__ import annotations

import json as _json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

import click

from . import __version__
from .audio import (
    capture,
    parse_frame_writes,
    pinned_record_start,
    pinned_record_stop,
    report_timing_from,
    sid_log_detail,
    sid_report,
)
from .basic import BasicError, detokenize, tokenize
from .basic_lint import lint_source, tokenized_bytes
from .build import BuildError, build_asm
from .cart_build import build_easyflash
from .cartridge import CartError, cart_dump, cart_info, cart_verify, run_cartconv
from .disasm import disassemble
from .disk import (
    BLOCK_SIZE,
    DiskError,
    block_poke,
    block_read,
    block_write_file,
    build_disk,
    cbm_lookup_name,
    check_block_write,
    create_image,
    delete_file,
    get_file,
    list_files,
    put_file,
    rename_file,
    validate_image,
)
from .machines import get_profile
from .monitor import MonitorError
from .ops import (
    all_labels,
    attach_boot_labels,
    call_routine,
    clear_checkpoints,
    disk_labels_path,
    easyflash_state,
    find_bytes,
    machine_state,
    parse_areas,
    parse_byte_values,
    parse_number,
    pc_region,
    profile_routine_samples,
    run_until,
    session_labels,
    session_ref,
    split_mem_condition,
    sprite_shape,
    sprite_states,
    staleness,
    wait_for_break,
    wait_for_idle,
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
from .protocol import CP_EXEC, CP_LOAD, CP_STORE, op_name
from .romdoc import identify
from .screen import (
    TEXT_ENCODINGS,
    number_screen_text,
    read_screen_codes,
    read_screen_text,
    resolve_text_encoding,
    save_screenshot_png,
)
from .session import Session, SessionError
from .symbols import format_addr
from .testing import TestError, load_test, program_test, run_test
from .text import GUTTER_LABELS, ascii_to_petscii, gutter_text


def emit(ctx: click.Context, data: dict, human: str) -> None:
    if ctx.obj["json"]:
        click.echo(_json.dumps(data))
    else:
        click.echo(human)


def fail(ctx: click.Context, message: str, extra: dict | None = None) -> NoReturn:
    """Report `message` and exit 1. Never returns — `NoReturn` is what lets a
    caller treat the line after a `fail()` as unreachable (the `help` command
    relies on it to know a resolved subcommand is not None)."""
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
                session) -> int:
    """ops.session_ref with CLI error reporting."""
    try:
        return session_ref(session, ref, labels)
    except (KeyError, ValueError) as e:
        fail(ctx, str(e))
        raise AssertionError("unreachable") from None


def parse_count(ctx: click.Context, value, what: str) -> int:
    """parse_number with CLI error reporting, for LENGTH/COUNT/VALUE args."""
    try:
        return parse_number(value)
    except ValueError:
        fail(ctx, f"bad {what} {value!r}; use decimal, $hex, or 0x hex")
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


def _set_session(ctx: click.Context, param: click.Parameter,
                 value: str | None) -> str | None:
    """Let -s/--session be given after the subcommand as well as before it."""
    if value is not None:
        root = ctx.find_root()
        if root.obj is None:
            root.obj = {"json": False, "session": None}
        root.obj["session"] = value
    return value


def _append_session_option(cmd: click.Command) -> None:
    """Give `cmd` a trailing -s/--session, unless either spelling is taken
    (true for `main`, and for session start/ensure/stop where -s is the
    --name alias — those keep their own meaning)."""
    existing = {o for p in cmd.params for o in getattr(p, "opts", [])}
    if "--session" in existing or "-s" in existing:
        return
    cmd.params.append(click.Option(
        ["--session", "-s", "session_name_trailing"], default=None,
        expose_value=False, callback=_set_session,
        help="Target session name. Accepted here or before the subcommand."))


class JsonAwareCommand(click.Command):
    """A command that also accepts the global --json in trailing position."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _append_json_option(self)
        _append_session_option(self)


class JsonAwareGroup(click.Group):
    """A group that also accepts --json directly, so groups that act as
    leaf commands themselves (e.g. `reg`, declared with
    invoke_without_command=True) support --json in trailing position too."""

    command_class = JsonAwareCommand
    group_class = type          # nested groups inherit this behaviour

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _append_json_option(self)
        _append_session_option(self)


@click.group(cls=JsonAwareGroup)
@click.version_option(__version__, "--version", prog_name="c64",
                      message="%(prog)s %(version)s")
@click.option("--json", "json_out", is_flag=True,
              help="Machine-readable JSON output. Accepted here or after the "
                   "subcommand (`c64 screen --json`).")
@click.option("--session", "-s", "session_name", default=None,
              help="Target session name. Accepted here or after the subcommand.")
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
              help="No window on SDL builds; starts minimized and never "
                   "takes focus on GTK builds.")
@click.option("--warp", is_flag=True,
              help="Run at maximum speed — recommended for automation.")
@click.option("--disk", "disk8", default=None, help="Attach a d64/d71/d81 image to drive 8.")
@click.option("--cart", "cart", default=None,
              help="Attach a .crt cartridge at power-on.")
@click.pass_context
def session_start(ctx, model, name, headless, warp, disk8, cart):
    """Boot a fresh emulated C64 and start its monitor daemon.

    Leaves the machine running; reports the new session's name, model, pid,
    and monitor port. A cartridge is mapped at power-on, so `--cart` boots
    straight into it — there is nothing to load afterwards.

    Says on stderr how many sessions are already up, if any: each one is a
    warped emulator holding a CPU core, and the ones that outlive the work
    are invisible until something counts them.
    """
    try:
        # Inside the try, not above it: reading the registry is exactly as
        # failure-prone as launching from it — a truncated or older-format
        # record fails `_from_record` out of `_load_all()` — and
        # `Session.launch` reads it too, so before this call that failure
        # already exited 1 through `fail()`. Hoisting the read out of the try
        # would have turned one caller's corrupt record into an unhandled
        # traceback with unparseable `--json` stdout. (`_from_record` raises
        # `SessionError` now, and raised `KeyError` when this was written;
        # the `except` below names both, so the move is what matters, not
        # which type arrives.)
        already = Session.list_all()
        if already:
            # stderr, never the payload: `--json` is a script contract, and
            # this is advice for whoever is watching — a start that had to be
            # told about the other three emulators is still a successful start.
            click.echo(f"note: {len(already)} other session(s) already running "
                       f"(c64 session list)", err=True)
        s = Session.launch(model=model, name=name, headless=headless, warp=warp,
                           disk8=disk8, cart=cart)
    except (SessionError, DiskError, KeyError) as e:
        fail(ctx, str(e))
        return
    lbl = attach_boot_labels(s, cart=cart, disk=disk8)
    emit(ctx, {"name": s.name, "model": s.model, "pid": s.pid, "port": s.port,
               "symbols": str(lbl) if lbl else None},
         f"started {s.model} session {s.name!r} (pid {s.pid}, monitor port {s.port})")


@session.command("ensure")
@click.option("--model", default="c64", show_default=True,
              help="Machine model to boot if no session is running.")
@click.option("--name", "-s", default=None,
              help="Session name to look for / start.")
@click.option("--headless", is_flag=True,
              help="No window on SDL builds, minimized on GTK builds "
                   "(only if starting).")
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
@click.option("--all", "all_", is_flag=True,
              help="Stop every session in the registry, including any whose "
                   "emulator is already gone.")
@click.pass_context
def session_stop(ctx, name, name_opt, all_):
    """Stop a session, kill its daemon, and remove its registry record.

    NAME defaults to the current (or only) running session. `--all` stops
    every session instead — the one-command cleanup after a run that left
    emulators behind. A session whose process is already gone is reaped
    rather than reported as a failure; `stopped` is then a list of names. A
    record too corrupt to read is discarded and reported as a failure, since
    nothing can be stopped for it and it would otherwise break every command
    that reads the registry, this one included.
    """
    # Every spelling of "this one session" counts, including the global
    # `c64 -s NAME session stop --all`: --all is the opposite of picking one,
    # and guessing which the caller meant would either spare the sessions
    # they asked to clear or kill the ones they did not.
    target = name or name_opt or ctx.obj["session"]
    if all_ and target:
        fail(ctx, f"--all stops every session; drop the name {target!r}")
        return
    if all_:
        try:
            names = Session.stop_all()
        except SessionError as e:
            # Partial cleanup: the message names what stopped and what is
            # still registered, so the next step is a re-run, not a guess.
            fail(ctx, str(e))
            return
        emit(ctx, {"stopped": names},
             ("stopped " + ", ".join(repr(n) for n in names)) if names
             else "no sessions running")
        return
    if name and name_opt and name != name_opt:
        fail(ctx, f"conflicting session names: positional {name!r} vs --name {name_opt!r}")
        return
    try:
        s = Session.attach(target)
    except SessionError as e:
        fail(ctx, str(e))
        return
    try:
        s.stop()
    except (SessionError, OSError) as e:
        # kill() + unlink() of the record and socket: report a failure as a
        # message naming the session, not a traceback.
        fail(ctx, f"could not stop session {s.name!r}: {e}")
        return
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


def _hexdump(addr: int, data: bytes, encoding: str = "ascii",
             label: str | None = None) -> str:
    """A hex dump whose text column says which decoding it is. The gloss is
    never silent: an unlabeled column invites reading screen codes as ASCII
    (which inverts the truth), so every dump ends with its label."""
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        lines.append(f"{addr + i:04x}: {hexpart:<47}  "
                     f"{gutter_text(chunk, encoding)}")
    lines.append(f"# text column: {label or GUTTER_LABELS[encoding]}")
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
@click.option("--as", "as_", type=click.Choice(TEXT_ENCODINGS),
              default="auto", show_default=True,
              help="Decoding for the text column: auto (screen codes when "
                   "the range is on the live screen, else ascii), screen, "
                   "petscii, or ascii.")
@click.pass_context
def mem_read(ctx, addr, length, decimal, as_):
    """Dump LENGTH bytes of memory from ADDR as a hex dump with a text column.

    ADDR is $hex/0x/decimal, a symbol, symbol+offset (alienX+49), or a
    screen cell @row,col (model-aware); LENGTH (default 256) is decimal
    or $hex. --decimal renders decimal values instead.

    The hex is the truth; the text column is a gloss, and the dump's last
    line names it ("# text column: screen codes"). By default the gloss
    follows the *live* screen (relocation included), so screen RAM reads as
    screen codes instead of ASCII gibberish; --as overrides it anywhere.
    JSON output always includes "hex", "bytes" and "values" (the same
    decimal int array under both keys, so `mem get`-shaped scripts work
    here too), and "text_encoding". Does not disturb run/stop state.
    """
    s = attach(ctx)
    start = resolve_ref(ctx, session_labels(s), addr, session=s)
    n = parse_count(ctx, length, "LENGTH")
    with s.monitor() as mon:
        try:
            data = mon.memory_read(start, n)
            encoding, degraded = resolve_text_encoding(mon, s.profile, start,
                                                       len(data), as_)
        finally:
            mon.release()
    label = GUTTER_LABELS[encoding] + (" (VIC state unreadable)" if degraded
                                       else "")
    emit(ctx, {"addr": start, "length": len(data), "hex": data.hex(),
               "bytes": list(data), "values": list(data),
               "text_encoding": encoding},
         _decdump(start, data) if decimal
         else _hexdump(start, data, encoding, label))


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
    try:
        writes = [(resolve_ref(ctx, labels, ln[0], session=s),
                   parse_byte_values(ln[1:])) for ln in lines]
    except ValueError as e:
        fail(ctx, str(e))
        return
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
    n = parse_count(ctx, length, "LENGTH")
    with s.monitor() as mon:
        try:
            data = mon.memory_read(start, n)
        finally:
            mon.release()
    emit(ctx, {"addr": start, "values": list(data), "bytes": list(data)},
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
    n = parse_count(ctx, length, "--length")
    try:
        pattern = parse_byte_values(values)
    except ValueError as e:
        fail(ctx, str(e))
        return
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
    labels = all_labels(s)
    sym = _pc_symbol(labels, regs)
    region = pc_region(regs.get("PC"))
    human = "  ".join(f"{k}={v:04x}" for k, v in sorted(regs.items()))
    if sym or region:
        human += f"  ({sym or region})"     # a name beats the region it is in
    state = machine_state(s)
    if state != "unknown":
        human += f"  [{state}]"
    emit(ctx, {"registers": regs, "pc_symbol": sym, "pc_region": region,
               "state": state}, human)


@reg.command("set")
@click.argument("name")
@click.argument("value")
@click.pass_context
def reg_set(ctx, name, value):
    """Set register NAME (PC, A, X, Y, or SP) to VALUE ($hex/0x/decimal)."""
    s = attach(ctx)
    v = parse_count(ctx, value, "VALUE")
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
@click.option("--area", "areas", multiple=True, metavar="NAME=START:SIZE",
              help="Link segment NAME at a fixed address (repeatable, "
                   "e.g. 'HIGH=$4000:$2000'). The gap below it ships as zero "
                   "bytes, which is what makes the segment land there.")
@click.pass_context
def build_cmd(ctx, source, output, model, areas):
    """Assemble 6502 SOURCE to a .prg (+ VICE label file) with ca65/ld65.

    Offline; no session required.
    """
    try:
        profile = get_profile(model)
        res = build_asm(source, out_prg=output, basic_start=profile.basic_start,
                        areas=parse_areas(areas, profile.basic_start))
    except (BuildError, ValueError, KeyError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"prg": str(res.prg), "labels": str(res.labels)},
         f"built {res.prg} (labels: {res.labels})")


@main.command("package")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              default=None,
              help="Artifact path; .d64/.d71/.d81 build an autostart-first "
                   "disk image, .crt a bootable cartridge, .prg (or omitted) "
                   "just the program file.")
@click.option("--title", default=None,
              help="CBM file/disk name (uppercased, max 16 chars; defaults "
                   "to the source stem).")
@click.option("--format", "fmt", type=click.Choice(["prg", "crt"]), default=None,
              help="Artifact format; defaults to the output extension "
                   "(.prg, .d64/.d71/.d81, or .crt).")
@click.option("--cart-type", type=click.Choice(["8k", "16k", "ultimax"]),
              default=None,
              help="Cartridge geometry (default 8k); cartridge output only. "
                   "--wrap needs 8k for anything BASIC has to start.")
@click.option("--wrap", is_flag=True,
              help="Force launcher-stub mode: assemble SOURCE to a .prg first, "
                   "then wrap it, instead of building cart-native code.")
@click.option("--model", default="c64", show_default=True,
              help="Target model — selects the BASIC load address and is "
                   "pinned in the reported run command.")
@click.option("--area", "areas", multiple=True, metavar="NAME=START:SIZE",
              help="Link segment NAME at a fixed address (repeatable, "
                   "e.g. 'HIGH=$4000:$2000'). Assembly sources only.")
@click.pass_context
def package_cmd(ctx, source, output, title, fmt, cart_type, wrap, model, areas):
    """Package SOURCE into an artifact any VICE user can run.

    The reported run command pins the model: stock x64sc boots its own
    default (PAL) machine, so both profiles pin their video standard
    (-ntsc / -pal) explicitly.
    """
    # Option validation (a --cart-type outside a cartridge, a --format that
    # disagrees with -o) lives in package_program so the MCP tool rejects the
    # same combinations in the same words; PackageError arrives below.
    try:
        profile = get_profile(model)
        res = package_program(source, out=output, title=title, model=model,
                              fmt=fmt, cart_type=cart_type, wrap=wrap,
                              areas=parse_areas(areas, profile.basic_start))
    except (BuildError, BasicError, DiskError, PackageError, CartError,
            ValueError, KeyError) as e:
        fail(ctx, str(e))
        return
    if res.get("cart_type"):
        emit(ctx, res,
             f"packaged {res['title']!r} -> {res['crt']} "
             f"({res['bytes']:,} bytes used, {res['free']:,} free)\n"
             f"run it with: {res['run']}")
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
@click.option("--area", "areas", multiple=True, metavar="NAME=START:SIZE",
              help="Link segment NAME at a fixed address (repeatable, "
                   "e.g. 'HIGH=$4000:$2000'). Assembly sources only.")
@click.pass_context
def run_cmd(ctx, source, areas):
    """Build/tokenize SOURCE as needed, then load and RUN it.

    `.bas` is tokenized, `.s` is assembled and its labels registered on the
    session (so symbols work in later commands), `.prg` is loaded directly,
    and a `.crt` reboots the session with the cartridge attached.
    Leaves the machine running.

    `--area` is `c64 build`'s, and applies to a `.s` source only — a program
    that needs a fixed-address segment to link at all is otherwise unrunnable
    from here, which is what sent La Galaxia to a two-command build script.

    For a `.crt`, "no session to reboot" and "no session by that name" are the
    same case: a `--session` name that does not exist boots an unnamed default
    `c64` with the cartridge rather than failing. Every other verb errors on an
    unknown name, so check `c64 session list` if a boot lands somewhere
    unexpected.
    """
    src = source.resolve()
    ext = src.suffix.lower()
    # Before the session is touched: --area rewrites the linker config that
    # only an assembled .s goes through, and a cartridge brings its own memory
    # map. Rejected rather than ignored, in `c64 package`'s words.
    if areas and ext != ".s":
        fail(ctx, "--area applies to assembly sources only")
        return
    if ext == ".crt":
        # A cartridge is mapped at power-on, so "running" one means booting a
        # fresh session with it attached rather than loading into this one.
        try:
            old = Session.attach(ctx.obj["session"])
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
                fail(ctx, f"cannot boot {src} on session {name!r}: the old "
                          f"session has to stop first (a cartridge is mapped "
                          f"at power-on) and stopping it failed: {e}")
                return
        try:
            # `name`/`model` are bound on every path that reaches here, and
            # the ignore is a checker limitation, not a papered-over hole:
            # they are unbound only if `if old is not None` was False, and
            # `old` is None only on the `except SessionError` branch — which
            # is the branch that binds them. Pyright does not correlate a
            # variable's *value* with another variable's boundness, so the
            # tuple unpack `old, name, model = None, None, "c64"` widens `old`
            # to `Session | None` and it stops being able to see that.
            new = Session.launch(
                model=model, name=name,  # pyright: ignore[reportPossiblyUnboundVariable]
                headless=False, warp=False, cart=str(src))
        except (SessionError, KeyError) as e:
            fail(ctx, str(e))
            return
        lbl = src.with_suffix(".lbl")
        if lbl.exists():
            new.set_labels_path(str(lbl))
        emit(ctx, {"cart": str(src), "session": new.name, "model": new.model,
                   "symbols": str(lbl) if lbl.exists() else None},
             f"booted {new.name} with {src} attached")
        return
    s = attach(ctx)
    # Parsed against the session's load address (there is no --model here) and
    # before ca65 runs, so an area that cannot link is reported as the flag the
    # user typed rather than as the config the toolset generated behind it. Its
    # own try: a rejected flag is not a failed build, and must not pick up the
    # "still running the PREVIOUS program" note a failed build carries.
    try:
        area_list = parse_areas(areas, s.profile.basic_start)
    except ValueError as e:
        fail(ctx, str(e))
        return
    labels = None
    deps: tuple = ()
    try:
        if ext == ".prg":
            prg = src
        elif ext == ".bas":
            prg = tokenize(src, src.with_suffix(".prg"), s.profile.basic_version)
        elif ext == ".s":
            res = build_asm(src, basic_start=s.profile.basic_start,
                            areas=area_list)
            prg, labels, deps = res.prg, res.labels, res.deps
        else:
            fail(ctx,
                 f"don't know how to run {ext!r} files "
                 "(use .bas, .s, .prg, or .crt)")
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
             "end": ck.end, "op": op_name(ck.op), "enabled": ck.enabled,
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
               "length": length, "op": op_name(op)},
         f"watchpoint #{ck.number} at {format_addr(labels, addr)} len={length} ({op_name(op)})")


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
    n = parse_count(ctx, count, "COUNT")
    with s.monitor() as mon:
        regs = mon.step(n, over=over)
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
    regs_in = {k: parse_count(ctx, v, f"--{k} value") for k, v in
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


@main.command("profile")
@click.argument("ref")
@click.option("--samples", default=1, show_default=True,
              help="Price N consecutive arrivals and report min/max/mean. A "
                   "per-frame cost that is bimodal — ordinary most frames, a "
                   "spike on the repaint ones — reads as fine when it is "
                   "sampled once.")
@click.option("--with-irq", "with_irq", is_flag=True,
              help="Leave interrupts live during the measurement (real-world "
                   "cost; expect variance — rerun a few times).")
@click.option("--timeout", default=30.0, show_default=True,
              help="Give up after this many seconds (the whole run, not each "
                   "sample).")
@click.pass_context
def profile_cmd(ctx, ref, samples, with_irq, timeout):
    """Measure the cycle cost of the routine at REF (entry to its RTS).

    A fake JSR exactly like `c64 call`, with CIA#2 timers A+B cascaded as
    a 32-bit hardware cycle counter across the run. Counts are wall
    cycles — badline DMA included, which is the frame-budget truth. By
    default the I flag is set on entry so the KERNAL IRQ cannot land
    inside the window; --with-irq measures with interrupts live. The
    machine ends STOPPED at the trap, like `c64 call`.

    --samples N runs the routine N times in a row and reports the spread:
    the cost of a game's tick depends on the game's own state, so one
    arrival can be an honest number about an unrepresentative frame.
    """
    if samples < 1:
        fail(ctx, f"profile: --samples must be at least 1 (got {samples})")
        return
    s = attach(ctx)
    labels = session_labels(s)
    addr = resolve_ref(ctx, labels, ref, session=s)
    where = format_addr(labels, addr)
    try:
        out = profile_routine_samples(s, addr, samples, timeout=timeout,
                                      with_irq=with_irq)
    except (RuntimeError, ValueError) as e:
        # ValueError as well as RuntimeError: on the daemon path any
        # ValueError that is NOT the old-daemon handshake is re-raised rather
        # than fallen back on (see ops), and a daemon-side one reaches here
        # through rpc — it has to be a message, not a traceback. Only the
        # zero-raw RuntimeError knows where the machine is (stopped at the
        # trap, cleanup done); an escaped ValueError does not, so it says
        # nothing about the machine rather than guessing.
        extra = {"machine": "stopped"} if isinstance(e, RuntimeError) else None
        fail(ctx, f"profile {where}: {e}", extra=extra)
        return
    if not out["fired"]:
        # Name what the abandoned window left behind: the docs say it, but a
        # caller reading only this line still has to know the jiffy clock and
        # keyboard are dead until the I bit is cleared by hand.
        left = ("CIA#2 timers A/B are left RUNNING" if with_irq else
                "CIA#2 timers A/B are left RUNNING and the I flag is left "
                "masked — the jiffy clock and keyboard stay dead until "
                "`c64 reg set FL ...` clears it (or the session restarts)")
        fail(ctx, f"profile {where}: never returned in {timeout}s after "
                  f"{out['reached']}/{samples} arrival(s) — machine left "
                  "running (runaway routine? check the address is a "
                  f"subroutine ending in RTS). {left}.",
             extra={"machine": "running", "reached": out["reached"],
                    "count": samples, "samples": out["samples"],
                    "timers_running": True, "irq_masked": not with_irq})
        return
    mask = "IRQs masked" if not with_irq else "IRQs live"
    payload = {"called": where, "samples": out["samples"], "min": out["min"],
               "max": out["max"], "mean": out["mean"],
               "irq_masked": not with_irq, "registers": out["registers"],
               "trap": out["trap"], "count": samples}
    if samples == 1:
        payload["cycles"] = out["cycles"]
        human = f"{where}: {out['cycles']} cycles (entry to rts, {mask})"
    else:
        human = (f"{where}: {out['mean']} cycles mean over {samples} arrivals "
                 f"(min {out['min']}, max {out['max']}; entry to rts, {mask})")
    emit(ctx, payload, human)


@main.command("wait")
@click.option("--text", "text_cond", default=None, help="Wait for screen text.")
@click.option("--mem", "mem_cond", default=None,
              help="ADDR<op>VALUE with <op> one of = != > >= < <=, e.g. "
                   "'$1000=42' or '$fb>=20'. Use an inequality for a counter "
                   "the machine can race past between polls.")
@click.option("--break", "break_cond", is_flag=False, flag_value="any",
              default=None,
              help="RESUME the machine (if stopped) and block until the NEXT "
                   "checkpoint hit — do not put `c64 continue` in front of it, "
                   "that consumes a hit. Give an ID to wait for that "
                   "checkpoint only (leftover breakpoints can't intercept).")
@click.option("--idle", "idle_cond", is_flag=True,
              help="Wait until the program has finished or errored: PC in the "
                   "KERNAL direct-mode input loop on three consecutive reads. "
                   "The one wait that needs no prediction about what the "
                   "program prints. A timeout means the machine never got "
                   "there — still running, or wedged.")
@click.option("--since", is_flag=True,
              help="With --text: fire only on an occurrence appearing AFTER "
                   "this command starts. For a gapped appearance; an instant "
                   "reply can print first and be swallowed by the baseline — "
                   "anchor a cell with --mem '@row,col' for turn-by-turn play.")
@click.option("--timeout", default=30.0, show_default=True,
              help="Give up after this many seconds.")
@click.pass_context
def wait_cmd(ctx, text_cond, mem_cond, break_cond, idle_cond, since, timeout):
    """Block until exactly one condition fires; report which one.

    Give exactly one of --text, --mem, --break, or --idle. This is the
    primary synchronization primitive for scripted use. Exit 1 on timeout.
    """
    if sum(bool(x) for x in (text_cond, mem_cond, break_cond, idle_cond)) != 1:
        fail(ctx, "give exactly one of --text, --mem, --break, --idle")
        return
    if since and not text_cond:
        fail(ctx, "--since only applies to --text")
        return
    s = attach(ctx)
    labels = session_labels(s)

    if idle_cond:
        out = wait_for_idle(s, timeout)
        if out["fired"]:
            emit(ctx, {"fired": "idle", "elapsed": out["elapsed"]},
                 "machine idle: the program has finished or errored")
            return
        pcs = " ".join(f"${pc:04x}" for pc in out["last_pcs"])
        fail(ctx, f"timeout after {timeout}s waiting for the machine to go "
                  f"idle — it never reached direct mode, and may be wedged "
                  f"(PC last seen at {pcs}). Take it apart with the wedged-machine "
                  "playbook in the `6502-debugging` skill: sample `c64 reg` "
                  "a second apart, `c64 disasm <PC-8> 24` the loop body, then "
                  "`c64 step` watching for the register that never changes.",
             extra={"machine": "running"})
        return

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
        addr_s, op, val_s = split_mem_condition(mem_cond)
    except ValueError as e:
        fail(ctx, str(e))
        return
    addr = resolve_ref(ctx, labels, addr_s, session=s)   # reports its own errors
    try:
        want = parse_number(val_s)
    except ValueError:
        fail(ctx, f"bad --mem value {val_s!r} in {mem_cond!r}; "
                  "use a decimal or $hex byte")
        return
    # Sampled either side of the wait, because "stopped the whole time" is
    # the diagnosis and one sample cannot support it: a machine stopped only
    # at the end was running for part of the window and the value genuinely
    # never arrived. machine_state never raises and answers from the daemon's
    # own bookkeeping, so this costs no emulator traffic.
    before = machine_state(s)
    out = wait_for_mem(s, addr, want, timeout, op=op)
    if out["fired"]:
        emit(ctx, {"fired": "mem", "elapsed": out["elapsed"]}, "mem condition met")
        return
    stopped = before == "stopped" == machine_state(s)
    detail = ("" if not stopped else
              " — the machine was STOPPED for the whole wait, so the byte "
              "could not change: a wait polls memory, it never resumes the "
              "CPU. Something before this stopped it (`c64 until`, `step`, "
              "`finish`, or a checkpoint hit). Run `c64 continue` first, or "
              "use `c64 wait --break` if you meant to run to a checkpoint.")
    fail(ctx, f"timeout after {timeout}s waiting for --mem {mem_cond}"
              f" (last value {out['last_value']}){detail}",
         extra={"machine": "stopped" if stopped else "running"})


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
    try:
        out = get_file(image, name, dest)   # get_file defaults DEST to NAME.prg
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
    lbl = disk_labels_path(image)
    if lbl is not None:
        s.set_labels_path(str(lbl))
    emit(ctx, {"booted": str(image.resolve()),
               "symbols": str(lbl) if lbl else None},
         f"booting {image}" + (f" (symbols: {lbl})" if lbl else ""))


@disk.command("rename")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("old")
@click.argument("new")
@click.pass_context
def disk_rename(ctx, image, old, new):
    """Rename file OLD to NEW on IMAGE (offline; no session).

    NEW is validated as a CBM filename. c1541 reports a missing OLD without
    failing, so this checks the DOS status and errors instead.
    """
    try:
        # cbm_lookup_name for the echo, not the raw OLD: rename_file looks the
        # file up through it, so echoing the caller's spelling put
        # {"old": "ALPHA", "name": "beta"} — two spellings of one convention —
        # in a single payload.
        old = cbm_lookup_name(old)
        name = rename_file(image, old, new)
    except DiskError as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"image": str(image), "old": old, "name": name},
         f"renamed {old!r} to {name!r}")


@disk.command("rm")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("name")
@click.pass_context
def disk_rm(ctx, image, name):
    """Scratch file NAME from IMAGE (offline; no session).

    NAME may use the CBM wildcards `*` and `?`, which scratch every match at
    once — `c64 disk rm game.d64 "*"` empties the disk. Errors when nothing
    matched: c1541 answers a no-match scratch exactly like a successful one
    apart from the count, so the count is what is reported and checked.
    """
    try:
        # The normalized name, for the same reason as rename: a caller was
        # told its `AL*` matched 1 file when what actually ran was `al*`.
        name = cbm_lookup_name(name)
        count = delete_file(image, name)
    except DiskError as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"image": str(image), "name": name, "deleted": count},
         f"deleted {count} file(s) matching {name!r}")


disk.add_command(disk_rm, "delete")     # CBM-familiar alias


@disk.group("block")
def disk_block() -> None:
    """Read and write raw 256-byte sectors.

    TRACK is 1-based and SECTOR 0-based, the CBM convention. On a 1541 image
    18/0 is the BAM and 18/1 the first directory sector.
    """


@disk_block.command("read")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("track", type=int)
@click.argument("sector", type=int)
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              default=None, help="Write the raw 256 bytes to a host file "
                                 "instead of hex-dumping them.")
@click.pass_context
def disk_block_read(ctx, image, track, sector, output):
    """Read one sector from IMAGE — hex dump, or raw bytes with -o."""
    try:
        data = block_read(image, track, sector)
    except DiskError as e:
        fail(ctx, str(e))
        return
    if output is not None:
        try:
            output.write_bytes(data)
        except OSError as e:
            fail(ctx, f"{output}: {e.strerror or e}")
            return
        emit(ctx, {"image": str(image), "track": track, "sector": sector,
                   "output": str(output), "bytes": len(data)},
             f"wrote {len(data)} bytes of {track}/{sector} to {output}")
        return
    emit(ctx, {"image": str(image), "track": track, "sector": sector,
               "bytes": len(data), "hex": data.hex()},
         _hexdump(0, data))


@disk_block.command("write")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("track", type=int)
@click.argument("sector", type=int)
@click.argument("values", nargs=-1)
@click.option("--from", "src", type=click.Path(exists=True, dir_okay=False,
                                               path_type=Path),
              default=None, help="Host file holding exactly 256 bytes: "
                                 "replaces the whole sector.")
@click.option("--offset", type=int, default=0, show_default=True,
              help="Offset within the sector for the VALUES poke.")
@click.pass_context
def disk_block_write(ctx, image, track, sector, values, src, offset):
    """Write a sector of IMAGE, wholesale (--from) or in part (VALUES).

    Each VALUE is a byte ($hex/0x/decimal), the same tokens `c64 mem write`
    takes; they are poked at --offset and the rest of the sector is left
    alone. c1541 silently truncates a wrong-sized whole-sector write and
    silently accepts a poke running off the end of the sector, so both are
    checked here first.
    """
    # The offset the user actually typed, or None — click's parameter source is
    # the only thing that tells an explicit `--offset 0` from an unset one, and
    # refusing `--from --offset 0` needs exactly that. The rule reads only
    # whether it was given; the poke below still uses the value.
    given_offset = (offset if ctx.get_parameter_source("offset")
                    is not click.core.ParameterSource.DEFAULT else None)
    try:
        check_block_write(src, values, given_offset)
        if src is not None:
            block_write_file(image, track, sector, src)
            written, where = BLOCK_SIZE, "whole sector"
        else:
            data = parse_byte_values(values)
            block_poke(image, track, sector, offset, data)
            written, where = len(data), f"offset {offset}"
    except (DiskError, ValueError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"image": str(image), "track": track, "sector": sector,
               "written": written, "offset": 0 if src else offset},
         f"wrote {written} byte(s) to {track}/{sector} ({where})")


@disk.command("validate")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def disk_validate(ctx, image):
    """Check (and repair) IMAGE's block allocation — the CBM fsck.

    Like the real command this rewrites the BAM in place. c1541 says nothing
    about a BAM it repaired, so a repair is judged by comparing the image
    before and after; the blocks-free figures are the evidence. Structural
    damage it does report, as a DOS error — that is a finding about the image,
    not a failed command, so it comes back in `messages` at exit 0.
    """
    try:
        res = validate_image(image)
    except DiskError as e:
        fail(ctx, str(e))
        return
    # No blanket "image repaired in place" tail: the damage validate *reports*
    # (DOS error 65 on a directory entry pointing off the disk) is damage it
    # leaves alone, so the messages say what happened and nothing more.
    human = "clean" if res["clean"] else "\n".join(res["messages"])
    emit(ctx, res, human)


@disk.command("build")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False,
                                            path_type=Path))
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              default=None, help="Image path; the extension picks the type "
                                 "(.d64 default, .d71, .d81).")
@click.option("--model", default="c64", show_default=True,
              help="Target model — selects the BASIC load address and version "
                   "for .s/.bas entries, and the run hint's video mode.")
@click.pass_context
def disk_build(ctx, manifest, output, model):
    """Build a populated disk image from a .disk.yaml MANIFEST.

    Files are written in listed order, so the first one autostarts. .s entries
    are assembled and .bas tokenized; everything else is copied verbatim. A
    manifest that would overflow the disk is refused before anything is
    written. Offline; no session.
    """
    try:
        res = build_disk(manifest, out=output, model=model)
    except (DiskError, BuildError, BasicError, KeyError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, res,
         f"{res['label']}  {len(res['files'])} files, "
         f"{res['blocks_used']}/{res['blocks_total']} blocks used "
         f"({res['blocks_free']} free)\n"
         f"built {res['image']}\nrun it with: {res['run']}")


@main.group()
def cart() -> None:
    """Build, inspect, and debug .crt cartridge images."""


@cart.command("build")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False,
                                            path_type=Path))
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path),
              default=None, help="Output .crt path (defaults next to MANIFEST).")
@click.pass_context
def cart_build(ctx, manifest, output):
    """Build a multi-bank EasyFlash .crt from an .ef.yaml MANIFEST.

    Every window is exactly 8192 bytes; a window that overflows is a hard
    error naming the bank and the overflow amount. The per-bank fill table is
    always reported. Offline; no session.
    """
    try:
        res = build_easyflash(manifest, out=output)
    except (CartError, BuildError) as e:
        fail(ctx, str(e))
        return
    emit(ctx, res, f"{res['fill']}\nbuilt {res['crt']}\nrun it with: {res['run']}")


@cart.command("info")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def cart_info_cmd(ctx, file):
    """Decode a .crt header and every CHIP packet (offline; no session)."""
    try:
        info = cart_info(file)
    except CartError as e:
        fail(ctx, str(e))
        return
    rows = [f"{info['name']}  {info['hardware_name']} (id {info['hardware']})",
            f"mode {info['mode']}  exrom={info['exrom']} game={info['game']}  "
            f"crt v{info['version']}",
            "bank window addr   size",
            *[f"{c['bank']:>4} {c['window']:>6} {c['load_addr']} {c['size']:>6}"
              for c in info["chips"]],
            f"{len(info['chips'])} packet(s), {info['total_bytes']:,} bytes"]
    emit(ctx, info, "\n".join(rows))


@cart.command("verify")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def cart_verify_cmd(ctx, file):
    """Check that a .crt should actually boot.

    Catches the silent failures: no CBM80 signature (the machine just boots to
    BASIC), a cold or reset vector pointing outside the cartridge, a wrong
    image size, and an EasyFlash image with no bank 0 HIROM window. Exits 1
    with a reason per problem. Offline; no session.
    """
    try:
        reasons = cart_verify(file)
    except CartError as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"path": str(file), "ok": not reasons, "reasons": reasons},
         "ok" if not reasons else "\n".join(reasons))
    if reasons:
        sys.exit(1)


@cart.command("dump")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--bank", type=int, default=0, show_default=True,
              help="Bank number to extract.")
@click.option("--window", type=click.Choice(["lo", "hi"]), default="lo",
              show_default=True, help="lo = $8000, hi = $A000/$E000.")
@click.option("-o", "--output", required=True,
              type=click.Path(dir_okay=False, path_type=Path),
              help="Where to write the raw window bytes.")
@click.pass_context
def cart_dump_cmd(ctx, file, bank, window, output):
    """Extract one bank window's bytes for offline disassembly."""
    try:
        data = cart_dump(file, bank, window)
    except CartError as e:
        fail(ctx, str(e))
        return
    try:
        output.write_bytes(data)
    except OSError as e:
        fail(ctx, f"{output}: {e.strerror or e}")
        return
    emit(ctx, {"path": str(output), "bank": bank, "window": window,
               "bytes": len(data)},
         f"wrote {len(data):,} bytes of bank {bank} {window} to {output}")


@cart.command("bank")
@click.pass_context
def cart_bank(ctx):
    """Report live EasyFlash state: bank register, mode register, memory mode.

    VICE lets these registers be read back; on real EasyFlash hardware they
    are write-only, so treat this as a debugging aid, not a program interface.
    """
    state = easyflash_state(attach(ctx))
    emit(ctx, state,
         f"bank {state['bank']}  $DE00={state['de00']}  "
         f"$DE02={state['de02']}  mode {state['mode']}")


@cart.command("convert")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--type", "cart_type", default=None,
              help="cartconv type id or name (see `cartconv --types`).")
@click.option("--name", default=None, help="Cartridge name for the .crt header.")
@click.pass_context
def cart_convert(ctx, source, output, cart_type, name):
    """Convert between raw .bin and .crt with VICE's cartconv.

    The escape hatch for cartridge types this tool does not model natively.
    """
    args = ["-i", str(source), "-o", str(output)]
    if cart_type:
        args += ["-t", cart_type]
    if name:
        args += ["-n", name]
    try:
        out = run_cartconv(args)
    except CartError as e:
        fail(ctx, str(e))
        return
    emit(ctx, {"source": str(source), "output": str(output),
               "cartconv": out.strip()},
         f"converted {source} -> {output}")


@main.group()
def rom() -> None:
    """Disassemble live memory and identify the machine's ROMs."""


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
    """Disassemble live memory (RAM or ROM) with label annotations.

    START is an address or symbol (e.g. CHROUT); LENGTH defaults to 32
    bytes. Labels come from the ROM database and the session's label
    file. Does not disturb run/stop state.
    """
    s = attach(ctx)
    labels = all_labels(s)
    addr = resolve_ref(ctx, labels, start, session=s)
    n = parse_count(ctx, length, "LENGTH")
    with s.monitor() as mon:
        try:
            data = mon.memory_read(addr, n)
        finally:
            mon.release()
    lines = disassemble(data, addr, labels)
    emit(ctx, {"start": addr, "length": n, "lines": lines}, "\n".join(lines))


# Reading the code you are stepping through is a debugging move, not a ROM
# chore, so it also answers at the top level. Same command object as
# `c64 rom disasm` — the two spellings cannot drift.
main.add_command(rom_disasm, name="disasm")


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
        fail(ctx, str(e), extra={"passed": False, "tests": []})
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
        fail(ctx, f"no example programs found in {directory}",
             extra={"passed": False, "tests": []})
        return
    results = []
    for d in program_dirs:
        try:
            results.append(run_test(program_test(d)))
        except (TestError, KeyError, BasicError, BuildError, SessionError) as e:
            fail(ctx, f"{d.name}: {e}", extra={"passed": False, "tests": []})
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
@click.option("--release/--no-release", default=True, show_default=True,
              help="Let the key go (poke 64 into $CB) after the last frame.")
@click.pass_context
def key_hold(ctx, keyname, at_ref, frames, timeout, release):
    """Hold KEY down for N game ticks by re-poking $CB before each one.

    Drives games that read the live current-key state: writes the key's
    matrix code to $CB, runs to REF, repeats — the machine ends STOPPED
    at REF (continue with `c64 continue`). KEY is one character, or
    `space`. For a deterministic first frame, stop at REF first
    (`c64 until REF`).

    The key is released after the last frame unless `--no-release`: the
    per-frame re-poke assumes the KERNAL keyboard scan is running to clear
    $CB, and a game that owns the interrupt has no scan, so an unreleased
    key stays down for ever.
    """
    s = attach(ctx)
    labels = session_labels(s)
    addr = resolve_ref(ctx, labels, at_ref, session=s)
    try:
        out = ops_key_hold(s, keyname, addr, frames=frames, timeout=timeout,
                           release=release)
    except ValueError as e:
        fail(ctx, str(e))
        return
    if out["requested"] == 0:
        emit(ctx, {"frames": 0, "requested": 0, "machine": "untouched"},
             "0 frames requested — nothing held; machine untouched")
        return
    if out["registers"] is None:
        # The machine is left RUNNING, so the caller cannot look at $CB —
        # say what happened to the key rather than making them guess.
        key_state = ("key released ($CB=64)" if out["released"] else
                     f"$CB still holds {keyname!r} (--no-release) — clear it "
                     "with `c64 mem write '$CB' 64`")
        fail(ctx, f"timeout: only {out['frames']}/{frames} frame(s) reached "
                  f"{format_addr(labels, addr)} — machine left RUNNING, "
                  f"checkpoint removed, {key_state}. "
                  "Is REF really executed every tick?",
             extra={"frames": out["frames"], "requested": frames,
                    "released": out["released"]})
        return
    _emit_stopped_regs(ctx, labels, out["registers"],
                       extra={"frames": out["frames"],
                              "released": out["released"]})


@main.group()
def sprite() -> None:
    """Inspect, render, and convert VIC-II sprites."""


def _sprite_shape(ctx, s, n, block):
    """ops.sprite_shape with CLI error reporting: a bad index (ValueError) and
    an unresolvable --block ref (KeyError/ValueError) both exit 1."""
    try:
        return sprite_shape(s, n, block)
    except (KeyError, ValueError) as e:
        fail(ctx, str(e))
        raise AssertionError("unreachable") from None


@sprite.command("status")
@click.pass_context
def sprite_status(ctx):
    """Decode $D000-$D02E and the sprite pointers into a per-sprite table.

    State-preserving; relocation-aware (pointers read at the live screen
    base + $3F8).
    """
    from dataclasses import asdict
    s = attach(ctx)
    states, shared = sprite_states(s)
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
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
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
    except UnidentifiedImageError as e:
        fail(ctx, f"cannot read image {str(image)!r}: {e}")
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
@click.option("--start-line", type=int, default=None,
              help="With --format basic: number the DATA lines from here so "
                   "they paste straight into a .bas source (unnumbered "
                   "otherwise, and a bare DATA line will not store).")
@click.option("--line-step", type=int, default=10, show_default=True,
              help="With --start-line: gap between generated line numbers.")
@click.option("--background", "background", default=" ", show_default=False,
              metavar="CHAR",
              help="Character that means background (pair 00). Default is a "
                   "space; pass '.' to author with a visible background, so "
                   "a row's width is countable and no editor can strip it.")
@click.option("--out", "-o", "out_path", default=None,
              help="Write the rendered rows to this file instead of stdout.")
@click.pass_context
def sprite_encode(ctx, file, hires, fmt, start_line, line_step, background,
                  out_path):
    """Encode ASCII-art sprite(s) from FILE into 63 sprite bytes each.

    FILE holds one or more 21-row sprites, separated by a blank line or by a
    `name:` header. A header may set its own mode — `fighter:hires`,
    `drone:multicolor` — so one sheet holds both, exactly as charset sheets
    do; a bare `name:` takes the file's mode (`--hires` or not). `#`
    comments are ignored, except that a `#` line which is a legal row at
    exactly row width is art. Rows use the friendly authoring legend
    (multicolor ' .#+', hires ' #'), the digit legend charset sheets use
    ('.123', digit = pair value), or the glyphs `c64 sprite show` emits
    ('·▒█▓', '█·') — `show` output round-trips straight back through
    `encode`. Needs no session; pairs with `c64 sprite from-png` (image
    input instead of ASCII art) and `c64 sprite show` (the inverse).
    """
    from .sprites import encode_sheet_file, render_sheet
    # Deliberately NOT shared with the MCP twin, unlike the sheet checks below:
    # each front end spells its own flags (--start-line/--format here,
    # start_line/fmt there), so the message IS the rule and moving it into the
    # library would have to pick one spelling and mislead the other's caller.
    if start_line is not None and fmt != "basic":
        fail(ctx, "--start-line only applies to --format basic")
        return
    try:
        blocks = encode_sheet_file(file, multicolor=not hires,
                                   background=background)
        text = render_sheet(blocks, fmt, multicolor=not hires,
                            start_line=start_line, line_step=line_step)
    except ValueError as e:
        fail(ctx, str(e))
        return
    if out_path:
        Path(out_path).write_text(text)
    emit(ctx, {"sprites": [list(b.data) for b in blocks],
               "blocks": [{"name": b.name, "multicolor": b.multicolor}
                          for b in blocks]},
         text if not out_path else f"wrote {out_path}")


@main.group()
def charset() -> None:
    """Author and convert custom character sets."""


@charset.command("encode")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--hires", is_flag=True,
              help="Make hires (1 bit/pixel, 8 chars/row, legend '.#') the "
                   "file's mode instead of multicolor pairs; a `name:hires` "
                   "or `name:multicolor` header overrides it per block.")
@click.option("--first-code", default=0, show_default=True,
              help="Screen code of the first glyph (sets the per-glyph "
                   "comments; the data itself is position-independent).")
@click.option("--label", "label", default="glyphs", show_default=True,
              metavar="NAME",
              help="Name the emitted block: `NAME:` and `NAME_end:`. Several "
                   "sheets then land in one file without being renamed on "
                   "the way out.")
@click.option("--out", "-o", "out_path", default=None,
              help="Write the rendered rows to this file instead of stdout.")
@click.pass_context
def charset_encode(ctx, file, hires, first_code, label, out_path):
    """Encode ASCII-art glyphs from FILE into 8 charset bytes each.

    FILE holds `name:` blocks of exactly 8 rows. Multicolor rows (the
    default) are 4 characters of `.123` — pair values 00/01/10/11 =
    background $D021 / $D022 / $D023 / the cell's own color, the
    multicolor-text order (NOT the sprite legend's). Hires rows are 8
    characters of `.#`. A block may name its own mode — `wall:multicolor`,
    `letter:hires` — so a multicolor playfield and a hires HUD font are one
    sheet; a bare `name:` takes the file's mode (`--hires` or not).
    `#` comment lines and blank lines are ignored;
    block order is screen-code order. Emits one contiguous block under a
    `glyphs:` label with a `glyphs_end:` end label (`--label` renames both),
    8 `.byte` rows per glyph, each glyph introduced by a `; code N: name`
    comment. Needs no session; the charset twin of `c64 sprite encode`.
    """
    import re

    from .charset import CharsetError, encode_row, format_glyphs, parse_charset
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
        fail(ctx, f"--label {label!r} is not an assembler identifier "
                  f"(letters, digits and underscore, not starting with a digit)")
        return
    try:
        text_in = file.read_text()
    except (OSError, ValueError) as e:
        # The read was already inside the try below, but `CharsetError` does
        # not catch it: both it and `UnicodeDecodeError` subclass ValueError
        # and neither subclasses the other, so a binary file handed to the
        # encoder escaped as a traceback. Its own try, so the message can
        # name the file rather than quote a codec.
        fail(ctx, f"cannot read charset sheet {file}: {e}")
        return
    try:
        glyphs = parse_charset(text_in, multicolor=not hires)
    except CharsetError as e:
        fail(ctx, str(e))
        return
    text = format_glyphs(glyphs, first_code=first_code, multicolor=not hires,
                         label=label)
    if out_path:
        Path(out_path).write_text(text)
    emit(ctx, {"glyphs": [{"name": g.name,
                           "multicolor": g.multicolor,
                           "bytes": [encode_row(r, g.multicolor) for r in g.rows]}
                          for g in glyphs]},
         text if not out_path else f"wrote {out_path}")


@main.group()
def audio() -> None:
    """Record the emulated SID, and log its registers frame by frame."""


@audio.command("record")
@click.option("--start", "start_path", default=None, metavar="PATH",
              help="Arm VICE's WAV recorder on PATH (made absolute) and hold "
                   "the machine at real time until --stop.")
@click.option("--stop", "stop", is_flag=True,
              help="Disarm the recorder, finalizing the WAV, and unpin the "
                   "speed.")
@click.pass_context
def audio_record(ctx, start_path, stop):
    """Record the emulated SID to a WAV file. Give exactly one of --start
    PATH or --stop.

    Recording runs the machine at 100% speed for the whole window and
    restores the session's warp and Speed settings on --stop, so a
    3-second capture costs 3 real seconds. The pin is not optional: while
    warped VICE writes a 0-frame WAV, so an unpinned capture comes back
    empty rather than merely fast. Nothing else should drive the session
    in between.
    """
    if bool(start_path) == bool(stop):
        fail(ctx, "give exactly one of --start PATH or --stop")
    s = attach(ctx)
    try:
        if start_path:
            out = pinned_record_start(s, start_path)
            human = f"recording to {out['wav']} (warp off, speed 100)"
        else:
            out = pinned_record_stop(s)
            human = (f"stopped; {out['wav']} is {out['bytes']} bytes"
                     if out["wav"] else "stopped; no pinned recording was active")
    except (RuntimeError, OSError, MonitorError, SessionError) as e:
        # Wider than AudioError (which is a RuntimeError) on purpose: a
        # capture drives two monitors, and a MonitorError or the TimeoutError
        # a busy daemon raises is a report, not a traceback. SessionError is
        # in the list for the same reason and is NOT covered by RuntimeError
        # (it derives straight from Exception): every `session.monitor()` here
        # can raise it from a failed daemon respawn.
        fail(ctx, f"audio record: {e}")
        return
    emit(ctx, out, human)


@audio.command("sidlog")
@click.argument("frames", type=click.IntRange(min=1))
@click.argument("path", type=click.Path())
@click.pass_context
def audio_sidlog(ctx, frames, path):
    """Log the SID's registers once per video frame to PATH as JSONL.

    One line per frame — `{"frame": n, "regs": [25 ints]}`, `regs[0]` being
    $D400 — which is what the analysis side reads to transcribe what the
    tune actually played. The sampling loop runs inside the session daemon,
    one frame per round trip, and leaves the machine running.

    It does not change the emulator's speed. Inside a pinned recording (or
    a full capture) every frame lands; on a warped session the log comes
    back far faster but a frame can slip past between records, and it says
    so on stderr — the human output flags that there is one and leaves the
    text there, rather than printing the paragraph a second time. That
    check is one-sided — a warped session that sampled
    slowly stays quiet — so no warning is not proof of an exact timeline;
    pinning real time is. `sample_rate_hz` reports samples per wall-clock
    second, which is not the machine's frame rate (one 200-frame log
    measured ~22/s pinned from a 60 Hz machine, ~425/s warped): above the
    frame rate it proves the session was not at real time, below it proves
    nothing.

    The WARNING's threshold is a fixed 63/s — 60 fps, the fastest machine
    here, plus a 5% margin — not the session's own frame rate. On a PAL
    session that leaves 50 to 63/s unflagged even though it already proves
    the machine outran 50 fps, so apply the machine's own rate yourself when
    the timeline matters.
    """
    s = attach(ctx)
    try:
        out = sid_log_detail(s, frames, path)
    except (RuntimeError, OSError, MonitorError, SessionError) as e:
        # As wide as `audio record`, and for the same reason: a busy daemon's
        # TimeoutError — or the SessionError a failed respawn raises — is a
        # report, not a traceback.
        fail(ctx, f"audio sidlog: {e}")
        return
    human = f"wrote {out['frames']} frames to {out['path']}"
    if out["warning"]:
        # A pointer, not a repeat, exactly as `audio capture` does with
        # `unpin_error`: `sid_log_detail` has already printed the whole
        # paragraph to stderr, and printing it again here puts a screenful of
        # the same text on the screen twice. `--json` still carries it whole —
        # a script reads the payload, not a stream it never captured.
        human += ("\nwarning: this log's frame numbers may not be the "
                  "machine's; the reason is on stderr, and in `warning` "
                  "with --json")
    emit(ctx, out, human)


#: Findings listed under a verdict before the rest are summarized. A failing
#: capture can produce one diff per note; the report holds them all.
FINDINGS_SHOWN = 10


def _verdict_report(ctx, out: dict, headline: str) -> None:
    """Emit a report payload, then exit 1 if its verdict is FAIL.

    A FAIL is a finding about the program, not a broken command, so the
    payload is emitted in full first (`--json` callers get the diffs, not an
    `{"error": ...}`) — but it exits non-zero, because an evidence script that
    treats "the report was written" as success proves nothing.
    """
    lines = [f"{out['verdict']}: {out['report']}", headline]
    if out.get("nothing_played"):
        # A PASS over an empty capture is the one verdict that means nothing:
        # no note sounded, so no check had anything to disagree with. It is
        # not a failure — proving a program is quiet is a real claim — but it
        # must not scroll past as "the audio works".
        lines.append("warning: nothing played — no voice sounded in this "
                     "capture, so the verdict above checked nothing. Confirm "
                     "the capture window was where you meant it. (Details "
                     "under the verdict in the report.)")
    findings = list(out["diffs"]) + list(out["anomalies"])
    lines += [f"- {f}" for f in findings[:FINDINGS_SHOWN]]
    if len(findings) > FINDINGS_SHOWN:
        lines.append(f"- ... and {len(findings) - FINDINGS_SHOWN} more, "
                     f"all of them in the report")
    emit(ctx, out, "\n".join(line for line in lines if line))
    if out["verdict"] == "FAIL":
        ctx.exit(1)


@audio.command("report")
@click.argument("log", type=click.Path(exists=True, dir_okay=False))
@click.argument("outdir", type=click.Path(file_okay=False))
@click.option("--wav", "wav_path", default=None, type=click.Path(dir_okay=False),
              help="The WAV captured alongside LOG. Without it the report is "
                   "register-only: no level metrics and no spectrogram.")
@click.option("--ref", "ref_path", default=None, type=click.Path(dir_okay=False),
              help="Reference score YAML to diff the transcription against. "
                   "Without one the report still runs every reference-free "
                   "check, and an empty diff is a legitimate pass.")
@click.option("--peak-hz", "peak_hz", is_flag=True,
              help="Also measure the WAV's loudest frequency, and how precise "
                   "that answer is. Needs --wav.")
@click.pass_context
def audio_report(ctx, log, outdir, wav_path, ref_path, peak_hz):
    """Analyse a captured SID log (and its WAV) into a verdict.

    Writes `report.md` into OUTDIR next to `piano-roll.png` and, with a WAV,
    `spectrogram.png`. Transcribes the log to note events, diffs them against
    --ref, and lists the anomalies no working tune produces. Exits 1 when the
    verdict is FAIL — the payload is still printed.

    The transcription needs the machine's clock. A log captured by these
    tools STAMPS it on line 1, so a re-score needs nothing: `-s NAME` is an
    override, taking the clock from that session's model instead, and only a
    log written before the stamp existed (or by hand) falls back to PAL
    (985248 Hz, 50 fps). `clock_source` in the payload says which of the
    three it was. Reading an NTSC capture as PAL transcribes every note about
    65 cents out, which looks like a badly tuned program rather than a
    mistake here — that silent fallback is what the stamp closes.

    --peak-hz adds the recording's loudest frequency to the payload, measured
    by one rFFT over the whole file with DC excluded. It is a bin centre, not
    a sub-bin estimate, so `resolution_cents` is what half a bin is worth at
    that pitch and is the tightest agreement the number can claim. Use it to
    check a WAV against what the registers predict — `hz = reg16 * clock /
    2**24` — which is the measurement `src/c64lib/audio.py`'s module docstring
    rests its emulated-time alignment on.
    """
    name = ctx.obj["session"]
    # Deliberately NOT shared with the MCP twin, unlike the measurement itself:
    # each front end names its own flags (--peak-hz/--wav here, peak_hz/wav
    # there), so the message IS the rule and one shared spelling would mislead
    # the other's caller. Refused before the analysis runs, so a bad call costs
    # nothing.
    if peak_hz and not wav_path:
        fail(ctx, "audio report --peak-hz needs --wav: a dominant partial is "
                  "a property of the recording, not of the register log")
        return
    try:
        # Inside the try, not above it. An unreadable log already falls back
        # to the default clock here, but a NAMED model is an override and
        # must not: `get_profile` raises KeyError on a machine this build
        # does not have, and a session record carrying one — an older or
        # hand-edited record is all it takes — escaped as a traceback over
        # an empty `--json` stdout while this line sat outside the handler.
        timing = report_timing_from(log, attach(ctx).model if name else None)
        out = sid_report(log, outdir, wav_path=wav_path, ref_path=ref_path,
                         timing=timing, peak_hz=peak_hz)
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        fail(ctx, f"audio report: {e}")
        return
    notes = f"{out['notes']} note" + ("" if out["notes"] == 1 else "s")
    # Where the clock came from, not just which one it was: "assumed PAL"
    # and "the log says PAL" produce identical transcriptions and only one
    # of them is evidence.
    source = {"session": "from the named session",
              "log": "stamped on the log",
              "default": "ASSUMED — the log carries no clock and no session "
                         "was named"}.get(timing["clock_source"], "")
    headline = (f"transcribed {notes} as a {out['machine']} "
                f"machine ({out['clock_hz']} Hz, {out['fps']} fps, {source})")
    if peak_hz:
        peak = out["peak"]
        cents = ("" if peak["resolution_cents"] is None
                 else f" (+-{peak['resolution_cents']:.2f} cents)")
        headline += (f"\npeak {peak['peak_hz']:.2f} Hz, bin {peak['bin']} of "
                     f"{peak['bin_hz']:.4f} Hz{cents}")
    _verdict_report(ctx, out, headline)


@audio.command("score")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def audio_score(ctx, file):
    """Read a reference score and say what it claims. No machine needed.

    The cheap half of the audio loop. A capture costs several times its
    emulated length in wall clock, so check the arithmetic in a hand-written
    score here first — that every voice has the number of events the window
    holds, and that the durations add up to the passage you meant — and spend
    the capture window once.

    Prints one line per voice: how many entries it lists, how many frames
    those entries account for, and the first and last note. Only the voices
    the score lists appear. An empty list is the claim "this voice sits out"
    and shows as silent; a voice the score omits claims nothing and is not
    reported at all.

    `frames` is optional per entry — the window's first and last notes are
    normally scored without one — so the frame total counts only the durations
    that are there. Exits 1 on anything malformed, with the same message the
    capture would have given you after spending its window.
    """
    # Imported here for the reason `audio report` imports its own: numpy and
    # Pillow come with the module and double the startup of every command.
    from .sid_analysis import score_summary
    try:
        out = score_summary(file)
    except (OSError, ValueError) as e:
        fail(ctx, f"audio score: {e}")
        return
    lines = []
    for voice, info in out["voices"].items():
        count = info["entries"]
        span = ("silent" if not count
                else f"first {info['first']}, last {info['last']}")
        lines.append(f"voice {voice}: {count} "
                     f"{'entry' if count == 1 else 'entries'}, "
                     f"{info['frames']} frames, {span}")
    voices = len(out["voices"])
    lines.append(f"total: {out['entries']} entries, {out['frames']} frames "
                 f"across {voices} {'voice' if voices == 1 else 'voices'}")
    emit(ctx, out, "\n".join(lines))


@audio.command("capture")
@click.argument("seconds", type=float)
@click.argument("outdir", type=click.Path(file_okay=False))
@click.option("--ref", "ref_path", default=None, type=click.Path(dir_okay=False),
              help="Reference score YAML to diff the transcription against — "
                   "write it from your own note data BEFORE capturing, never "
                   "from a transcription this produced.")
@click.option("--at-frame", "at_frames", nargs=2, multiple=True,
              metavar="N ADDR=VAL[,ADDR=VAL...]",
              help="Perform these memory writes at frame N of the capture "
                   "window — the only way to trigger something inside it, "
                   "since nothing else may drive the session while it is "
                   "open. Repeatable; repeats of one frame merge in order.")
@click.pass_context
def audio_capture(ctx, seconds, outdir, ref_path, at_frames):
    """Record SECONDS of the running program and report on what it played.

    One call for the whole loop: pin real time, record `capture.wav`, log the
    SID's registers to `sid-log.jsonl`, restore the session's speed, and write
    `piano-roll.png`, `spectrogram.png`, and `report.md` into OUTDIR. Exits 1
    when the verdict is FAIL.

    SECONDS is EMULATED time, and it costs several times that in wall clock:
    the machine advances one frame per monitor round trip while the log is
    sampling. Measured on an NTSC session, a 2-second capture (120 frames)
    took 6.19 s from pinning to unpinning and 6.32 s for the whole command
    (`src/c64lib/audio.py`'s module docstring holds that measurement and the
    evidence behind it). Budget for that and keep the session to yourself for
    the duration.

    Start the music before you call this. An opening rest the score does not
    list is tolerated — it is skipped, the way trailing silence is — but a
    capture that opens on silence still spends part of its window recording
    nothing.

    A BASIC program you just RUN has nothing to be driven to, so give it a
    silent lead-in of its own and start it a few seconds before you call this:
    arming takes about 0.75 s and the opening notes are lost without one.
    Count that lead-in with warp OFF. This command clears warp when it arms,
    but the program's delay runs before that, and under warp an eight-second
    jiffy delay is over in a fraction of a real second.

    A short effect cannot be triggered from outside: arming costs emulated
    frames before frame 0 (the payload's `lead_in_frames` measures how many
    on this capture), and once the window is open the sampling loop owns the
    session, so a poke from another command is queued behind it. Use
    `--at-frame N 'ADDR=VAL'` — the writes happen while the machine is halted
    just before frame N runs, so frame N is the first logged frame that shows
    them: `--at-frame 30 '$d404=$81'` gates a voice 30 frames in.

    Check the score with `c64 audio score` before you get here. A typo'd voice
    key costs nothing to find there and the whole window to find here.
    """
    try:
        writes = parse_frame_writes(at_frames)
    except ValueError as e:
        fail(ctx, f"audio capture --at-frame: {e}")
        return
    s = attach(ctx)
    try:
        out = capture(s, seconds, outdir, ref_path=ref_path, writes=writes)
    except (RuntimeError, OSError, ValueError, MonitorError, SessionError) as e:
        # As wide as `audio record`: a capture drives two monitors, and a
        # MonitorError, a busy daemon's TimeoutError, or a failed respawn's
        # SessionError is a report.
        fail(ctx, f"audio capture: {e}")
        return
    headline = (f"{out['frames']} frames — {out['emulated_s']:.1f} s "
                f"emulated in {out['wall_clock_s']:.1f} s of wall clock")
    if out.get("lead_in_frames") is not None:
        # The frames the arming spent before frame 0. Worth a line rather
        # than only a JSON field: it is the answer to "why did my effect not
        # appear", and the number an agent needs to aim --at-frame.
        headline += (f"; lead-in {out['lead_in_frames']} frames before "
                     f"frame 0")
    if out.get("unpin_error"):
        # A pointer, not a repeat: `capture` has already printed the whole
        # sentence to stderr. The verdict is about the audio, and this is about
        # the machine it came from — which outlives the command — so the line
        # under the verdict says that much and where the rest is.
        headline += ("\nwarning: this session could not be unpinned; the "
                     "reason is on stderr, and in `unpin_error` with --json")
    _verdict_report(ctx, out, headline)
