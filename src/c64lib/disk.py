"""Disk image operations via VICE's c1541 utility.

All operations act on image files on the host; attaching images to a running
emulator happens in c64lib.session (at launch) or via autostart (mid-session).
c1541 prints a harmless OPENCBM dylib warning on stderr — success is judged
by return code and output files, never by stderr being empty.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


class DiskError(Exception):
    pass


IMAGE_DRIVE_TYPES = {".d64": 1541, ".d71": 1571, ".d81": 1581}


def drive_type_for(path: str | Path) -> int:
    suffix = Path(path).suffix.lower()
    try:
        return IMAGE_DRIVE_TYPES[suffix]
    except KeyError:
        raise DiskError(
            f"unsupported image type {suffix or Path(path).name!r} "
            f"(supported: {', '.join(IMAGE_DRIVE_TYPES)})"
        ) from None


def _c1541() -> str:
    exe = os.environ.get("C64_TOOLS_C1541") or shutil.which("c1541")
    if not exe:
        raise DiskError(
            "c1541 not found. It ships with VICE — install VICE 3.5+ "
            "(macOS: brew install vice) or set C64_TOOLS_C1541."
        )
    return exe


def _run(args: list[str]) -> str:
    r = subprocess.run([_c1541(), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise DiskError(f"c1541 failed ({' '.join(args)}):\n{r.stderr or r.stdout}")
    return r.stdout


def create_image(path: str | Path, label: str = "disk", disk_id: str = "00") -> Path:
    path = Path(path)
    image_type = path.suffix.lower().lstrip(".")
    drive_type_for(path)  # validate suffix
    _run(["-format", f"{label},{disk_id}", image_type, str(path)])
    return path


_DIR_LINE = re.compile(r'^(\d+)\s+"([^"]*)"\s+(\S+)')


def list_files(image: str | Path) -> dict:
    out = _run([str(image), "-list"])
    label, files, blocks_free = "", [], 0
    for line in out.splitlines():
        line = line.strip()
        if line.endswith("blocks free."):
            blocks_free = int(line.split()[0])
            continue
        m = _DIR_LINE.match(line)
        if not m:
            continue
        if not label and line.startswith("0 "):
            label = m.group(2)
            continue
        files.append({"blocks": int(m.group(1)), "name": m.group(2), "type": m.group(3)})
    return {"label": label, "files": files, "blocks_free": blocks_free}


def put_file(image: str | Path, src: str | Path, name: str | None = None) -> str:
    src = Path(src)
    cbm_name = name or src.stem.lower()
    _run([str(image), "-write", str(src), cbm_name])
    return cbm_name


def get_file(image: str | Path, name: str, dest: str | Path) -> Path:
    dest = Path(dest)
    _run([str(image), "-read", name, str(dest)])
    if not dest.exists():
        raise DiskError(f"c1541 reported success but {dest} was not written")
    return dest
