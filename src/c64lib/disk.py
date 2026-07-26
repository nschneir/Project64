"""Disk image operations via VICE's c1541 utility.

All operations act on image files on the host; attaching images to a running
emulator happens in c64lib.session (at launch) or via autostart (mid-session).
c1541 prints a harmless OPENCBM dylib warning on stderr — success is judged
by return code and output files, never by stderr being empty.

c1541 also exits 0 when an operation *fails*: renaming a missing file, writing
onto a full disk and reading an out-of-range block all return 0. Anything that
can fail therefore goes through _run_checked, which reads the DOS status line
("ERR = 62, FILE NOT FOUND, 00, 00") and c1541's own diagnostics instead.
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


BLOCK_SIZE = 256
BLOCK_PAYLOAD = 254      # 2 bytes of every sector link to the next one

# Blocks free on a freshly formatted image, measured with c1541.
TOTAL_BLOCKS = {".d64": 664, ".d71": 1328, ".d81": 3160}

# (first track, last track, sectors per track), probed sector by sector.
_D64_ZONES = ((1, 17, 21), (18, 24, 19), (25, 30, 18), (31, 35, 17))
GEOMETRY: dict[str, tuple[tuple[int, int, int], ...]] = {
    ".d64": _D64_ZONES,
    # The 1571 is two 1541 sides: tracks 36-70 repeat the same zone pattern.
    ".d71": _D64_ZONES + ((36, 52, 21), (53, 59, 19), (60, 65, 18), (66, 70, 17)),
    ".d81": ((1, 80, 40),),
}


def _geometry_for(path: str | Path) -> tuple[str, tuple[tuple[int, int, int], ...]]:
    suffix = Path(path).suffix.lower()
    drive_type_for(path)                    # raises naming the supported types
    return suffix, GEOMETRY[suffix]


def max_track(image: str | Path) -> int:
    _, zones = _geometry_for(image)
    return zones[-1][1]


def sectors_per_track(image: str | Path, track: int) -> int:
    suffix, zones = _geometry_for(image)
    for first, last, sectors in zones:
        if first <= track <= last:
            return sectors
    raise DiskError(
        f"track {track} out of range (1-{zones[-1][1]} for {suffix.lstrip('.')})")


def check_block(image: str | Path, track: int, sector: int) -> None:
    """Validate a track/sector pair before handing it to c1541.

    c1541 reports an out-of-range block as `Error - ...` and still exits 0,
    so the geometry check happens here where the message can name the limit.
    """
    sectors = sectors_per_track(image, track)      # raises for a bad track
    if not 0 <= sector < sectors:
        raise DiskError(
            f"sector {sector} out of range (0-{sectors - 1} on track {track})")


def blocks_for(size: int) -> int:
    """Blocks a file of `size` bytes occupies. Verified against c1541: a
    19-byte file costs 1 block and a 160,000-byte file costs 630."""
    return max(1, -(-size // BLOCK_PAYLOAD))


_ERR_RE = re.compile(
    r"^ERR = (\d+),\s*([^,]+?),\s*(\d+),\s*(\d+)", re.MULTILINE)

# c1541's own diagnostics, none of which change the exit code.
_FAILURE_TEXT = ("no space on image?", "floppy write failed",
                 "floppy read failed")

# DOS codes that are not failures: 00 is OK, 01 is the normal reply to a
# scratch (its third field carries how many files were actually removed).
_OK_CODES = (0, 1)


def dos_status(out: str) -> tuple[int, str, int, int] | None:
    """Parse c1541's DOS status line into (code, message, track, sector)."""
    m = _ERR_RE.search(out)
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip(), int(m.group(3)), int(m.group(4))


def _c1541() -> str:
    exe = os.environ.get("C64_TOOLS_C1541") or shutil.which("c1541")
    if not exe:
        raise DiskError(
            "c1541 not found. It ships with VICE — install VICE 3.5+ "
            "(macOS: brew install vice) or set C64_TOOLS_C1541."
        )
    return exe


def _run2(args: list[str]) -> tuple[str, str]:
    r = subprocess.run([_c1541(), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise DiskError(f"c1541 failed ({' '.join(args)}):\n{r.stderr or r.stdout}")
    return r.stdout, r.stderr


def _run(args: list[str]) -> str:
    return _run2(args)[0]


def _run_checked(args: list[str], context: str) -> str:
    """Run c1541 and raise on any failure it reports without an exit code."""
    stdout, stderr = _run2(args)
    combined = stdout + stderr
    status = dos_status(combined)
    if status is not None and status[0] not in _OK_CODES:
        code, message, track, sector = status
        detail = f" at track {track} sector {sector}" if track or sector else ""
        raise DiskError(f"{context}: {message.lower()} (DOS error {code}){detail}")
    for line in combined.splitlines():
        if line.startswith("Error -"):
            raise DiskError(f"{context}: {line[len('Error -'):].strip()}")
    for needle in _FAILURE_TEXT:
        if needle in combined:
            raise DiskError(f"{context}: c1541 reported {needle!r}")
    return stdout


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


def cbm_filename(raw: str) -> str:
    """Validate a CBM filename (lowercased on disk, 1-16 chars, no DOS
    metacharacters). Shares packaging.cbm_title's rules."""
    # Imported here, not at module scope: packaging imports from disk.
    from .packaging import PackageError, cbm_title

    try:
        return cbm_title(raw).lower()
    except PackageError as e:
        msg = str(e)
        if "CBM filename" not in msg:
            msg = f"{msg} — not a legal CBM filename"
        raise DiskError(msg) from None


def rename_file(image: str | Path, old: str, new: str) -> str:
    """Rename a file on IMAGE in place. Returns the new CBM name."""
    name = cbm_filename(new)
    _run_checked([str(image), "-rename", str(old), name],
                 f"renaming {old!r} to {name!r} on {Path(image).name}")
    return name


def delete_file(image: str | Path, name: str) -> int:
    """Scratch a file from IMAGE. Returns how many entries were removed.

    c1541 answers a scratch with "ERR = 01, FILES SCRATCHED, <n>, 00" whether
    or not anything matched, so the count is the only reliable way to tell a
    successful delete from a typo.
    """
    out = _run_checked([str(image), "-delete", str(name)],
                       f"deleting {name!r} from {Path(image).name}")
    status = dos_status(out)
    scratched = status[2] if status else 0
    if scratched == 0:
        raise DiskError(
            f"no file named {name!r} on {Path(image).name} — nothing deleted")
    return scratched
