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
from dataclasses import dataclass, field
from pathlib import Path


class BuildError(Exception):
    pass


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


def linker_config(basic_start: int) -> str:
    return f"""\
MEMORY {{
    ZP:     start = $0000, size = $0100;
    HEADER: file = %O, start = $0000, size = $0002;
    MAIN:   file = %O, start = ${basic_start:04X}, size = $97FF;
}}
SEGMENTS {{
    ZEROPAGE: load = ZP,     type = zp,  optional = yes;
    LOADADDR: load = HEADER, type = ro;
    EXEHDR:   load = MAIN,   type = ro,  optional = yes;
    CODE:     load = MAIN,   type = rw;
    RODATA:   load = MAIN,   type = ro,  optional = yes;
    DATA:     load = MAIN,   type = rw,  optional = yes;
    BSS:      load = MAIN,   type = bss, optional = yes, define = yes;
}}
"""


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise BuildError(f"{Path(cmd[0]).name} failed:\n{r.stderr or r.stdout}")


def build_asm(
    source: Path, out_prg: Path | None = None, basic_start: int = 0x0801
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
        cfg.write_text(linker_config(basic_start))
        _run([ca65, "-g", str(source), "-o", str(obj),
              "--create-dep", str(dep)])
        _run([ld65, "-o", str(prg), "-C", str(cfg), "-Ln", str(labels), str(obj)])
        deps = _parse_deps(dep, fallback=source)
    return BuildResult(prg=prg, labels=labels, deps=deps, built_at=time.time())


def _parse_deps(dep_file: Path, fallback: Path) -> tuple[Path, ...]:
    """Parse ca65's Makefile-style dependency file: every source file the
    build read (the top file plus everything it .include'd). Used for the
    stale-binary warning (`c64 status`). Falls back to just the top file
    if the dep file is missing (very old ca65)."""
    if not dep_file.exists():
        return (fallback.resolve(),)
    text = dep_file.read_text().replace("\\\n", " ")
    _, _, tail = text.partition(":")
    deps = tuple(Path(tok).resolve() for tok in tail.split() if tok)
    return deps or (fallback.resolve(),)
