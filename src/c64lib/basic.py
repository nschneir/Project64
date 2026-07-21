"""Commodore BASIC tokenize/detokenize via VICE's petcat.

petcat text convention: keywords AND string text lowercase (lowercase ASCII
-> unshifted PETSCII -> displays as uppercase on the C64's uppercase/graphics screen).
Dialect code verified against petcat (VICE 3.10): 2 (C64 BASIC 2.0).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PETCAT_DIALECTS = {"2.0": "2"}


class BasicError(Exception):
    pass


def _petcat() -> str:
    exe = os.environ.get("C64_TOOLS_PETCAT") or shutil.which("petcat")
    if not exe:
        raise BasicError(
            "petcat not found. It ships with VICE — install VICE 3.5+ "
            "(macOS: brew install vice) or set C64_TOOLS_PETCAT."
        )
    return exe


def _dialect(basic_version: str) -> str:
    try:
        return PETCAT_DIALECTS[basic_version]
    except KeyError:
        raise BasicError(f"no petcat dialect for BASIC {basic_version!r}") from None


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise BasicError(f"petcat failed ({' '.join(cmd)}):\n{r.stderr}")


def tokenize(source: Path, out_prg: Path, basic_version: str) -> Path:
    _run([_petcat(), f"-w{_dialect(basic_version)}", "-o", str(out_prg), "--", str(source)])
    return Path(out_prg)


def detokenize(prg: Path, basic_version: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "listing.bas"
        _run([_petcat(), f"-{_dialect(basic_version)}", "-o", str(out), "--", str(prg)])
        return out.read_text()
