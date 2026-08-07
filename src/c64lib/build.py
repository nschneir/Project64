"""Assemble 6502 source to a C64 .prg with ca65/ld65.

The generated linker config produces: 2-byte load-address header, then
segments EXEHDR (BASIC SYS stub, optional) and CODE/RODATA/DATA at the
BASIC start address. ld65 -Ln emits a VICE label file for symbolic debugging.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple


class BuildError(Exception):
    pass


class Area(NamedTuple):
    """One extra ld65 MEMORY area, and the same-named segment loaded into it.

    A `.prg` is a flat file, so an area only puts a segment at `start` if
    everything below it ships too — see `linker_config`.
    """

    name: str
    start: int
    size: int


#: MEMORY areas and SEGMENTS the generated config already defines; an --area
#: reusing one of these names would redefine it under ld65.
RESERVED_AREA_NAMES = ("ZP", "HEADER", "MAIN", "ZEROPAGE", "LOADADDR",
                       "EXEHDR", "CODE", "RODATA", "DATA", "BSS")


@dataclass(frozen=True)
class BuildResult:
    prg: Path
    labels: Path
    deps: tuple[Path, ...] = field(default=())
    built_at: float = 0.0


def _find_tool(name: str, env_var: str) -> str:
    exe = os.environ.get(env_var) or shutil.which(name)
    if not exe:
        raise BuildError(
            f"{name} not found. Install the cc65 suite "
            f"(macOS: brew install cc65; Debian/Ubuntu: apt install cc65) "
            f"or set {env_var}."
        )
    return exe


def linker_config(basic_start: int, areas: Sequence[Area] = ()) -> str:
    """The ld65 config for one .prg, plus one MEMORY area per `areas` entry.

    With no areas this is byte-identical to what the toolset has always
    emitted — MAIN runs to $97FF and nothing is filled, so the .prg is
    exactly as long as the program.

    With areas, MAIN stops where the lowest area starts and everything below
    the topmost area is filled. That padding is the whole mechanism: a .prg
    is a flat file that the KERNAL loads from its 2-byte header onward, so a
    segment only lands at the address you asked for if every byte below it
    ships too. The last area is not filled — nothing above it needs placing,
    so padding it would only make the file longer.
    """
    areas = sorted(areas, key=lambda a: a.start)
    # ZP starts at $0002: $0000/$0001 are the 6510's on-chip port registers,
    # and ld65 hands out the area from its start — at $0000 the first two
    # ZEROPAGE bytes an author declares land on the data direction register
    # and the banking port, and writing the port re-banks the machine under
    # the running code. Matches cart_build._ZP.
    main_size = areas[0].start - basic_start if areas else 0x97FF
    main_fill = ", fill = yes" if areas else ""
    memory = [
        "    ZP:     start = $0002, size = $00FE;",
        "    HEADER: file = %O, start = $0000, size = $0002;",
        f"    MAIN:   file = %O, start = ${basic_start:04X}, "
        f"size = ${main_size:04X}{main_fill};",
    ]
    segments = [
        "    ZEROPAGE: load = ZP,     type = zp,  optional = yes;",
        "    LOADADDR: load = HEADER, type = ro;",
        "    EXEHDR:   load = MAIN,   type = ro,  optional = yes;",
        "    CODE:     load = MAIN,   type = rw;",
        "    RODATA:   load = MAIN,   type = ro,  optional = yes;",
        "    DATA:     load = MAIN,   type = rw,  optional = yes;",
        "    BSS:      load = MAIN,   type = bss, optional = yes, define = yes;",
    ]
    for i, area in enumerate(areas):
        fill = ", fill = yes" if i < len(areas) - 1 else ""
        memory.append(f"    {area.name + ':':<8}file = %O, "
                      f"start = ${area.start:04X}, size = ${area.size:04X}{fill};")
        # define = yes so the program can .assert against __NAME_LOAD__ and
        # __NAME_SIZE__ rather than repeating the address it passed to --area.
        segments.append(f"    {area.name + ':':<10}load = {area.name + ',':<8}"
                        f"type = ro,  optional = yes, define = yes;")
    return ("MEMORY {\n" + "\n".join(memory) + "\n}\n"
            "SEGMENTS {\n" + "\n".join(segments) + "\n}\n")


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise BuildError(f"{Path(cmd[0]).name} failed:\n{r.stderr or r.stdout}")


def build_asm(
    source: Path, out_prg: Path | None = None, basic_start: int = 0x0801,
    areas: Sequence[Area] = (),
) -> BuildResult:
    ca65 = _find_tool("ca65", "C64_TOOLS_CA65")
    ld65 = _find_tool("ld65", "C64_TOOLS_LD65")
    source = Path(source)
    prg = Path(out_prg) if out_prg else source.with_suffix(".prg")
    labels = prg.with_suffix(".lbl")
    with tempfile.TemporaryDirectory() as td:
        obj = Path(td) / (source.stem + ".o")
        cfg = Path(td) / "c64.cfg"
        dep = Path(td) / "deps.d"
        cfg.write_text(linker_config(basic_start, areas))
        _run([ca65, "-g", str(source), "-o", str(obj),
              "--create-dep", str(dep)])
        _run([ld65, "-o", str(prg), "-C", str(cfg), "-Ln", str(labels), str(obj)])
        deps = _parse_deps(dep, fallback=source)
    return BuildResult(prg=prg, labels=labels, deps=deps, built_at=time.time())


def _parse_deps(dep_file: Path, fallback: Path) -> tuple[Path, ...]:
    """Parse ca65's Makefile-style dependency file: every source file the
    build read (the top file plus everything it .include'd). Used for the
    stale-binary warning (`c64 status`). Falls back to just the top file
    if the dep file is missing (very old ca65).

    Per line, and only the prerequisites: after the rule ca65 emits a bare
    `<source>:` phony target for each one (GNU make's -MP convention).
    Splitting the whole file on its first colon swallows those into the
    prerequisite list as paths with a trailing colon, which never exist —
    and `ops.staleness` counts a vanished source as stale, so every freshly
    built program reported itself out of date."""
    if not dep_file.exists():
        return (fallback.resolve(),)
    deps: list[Path] = []
    for line in dep_file.read_text().replace("\\\n", " ").splitlines():
        _, sep, tail = line.partition(":")
        if not sep:
            continue
        for tok in tail.split():
            p = Path(tok).resolve()
            if p not in deps:
                deps.append(p)
    return tuple(deps) or (fallback.resolve(),)
