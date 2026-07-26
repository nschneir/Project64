"""Disk image operations via VICE's c1541 utility.

All operations act on image files on the host; attaching images to a running
emulator happens in c64lib.session (at launch) or via autostart (mid-session).
c1541 prints a harmless OPENCBM dylib warning on stderr — success is judged
by return code and output files, never by stderr being empty.

c1541 also exits 0 when an operation *fails*, but not predictably, so the exit
code alone is not enough either. The rename/scratch family is where it bites:
renaming a missing file exits 0 with "ERR = 62, FILE NOT FOUND, 00, 00", and
scratching one exits 0 with "ERR = 01, FILES SCRATCHED, 00, 00" — a success
line whose count field is the only sign nothing matched. (Other failures do set
the code: a full-disk write and an out-of-range block both exit 1.) Anything
that can fail therefore goes through _run_checked, which reads the DOS status
line and c1541's own diagnostics rather than trusting the exit code alone.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
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

    c1541 does catch an out-of-range block itself — `Error - Track 18, Sector
    25 out of bounds.`, exit 1 — but only after attaching the image, and its
    message never says what the limit was. Checking here costs no subprocess
    and lets the error name the bound.
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
    """Run c1541 and raise on the failures it reports without an exit code.

    Not a complete guarantee, deliberately: DOS code 01 is whitelisted, because
    it is the normal reply both to a real scratch and to one that matched
    nothing ("ERR = 01, FILES SCRATCHED, 00, 00"). A caller whose operation can
    answer 01 must re-parse the returned stdout with dos_status() and check the
    count field itself — see delete_file. The ERR line is deliberately left in
    the returned stdout for exactly that.
    """
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


# Characters CBM DOS parses inside a filename argument: `"` and `:` end the
# name, `,` starts another one, `=` introduces the type/filter field. Left
# unchecked they silently retarget the operation at a different file.
_DOS_METACHARACTERS = '":,='


def cbm_lookup_name(raw: str) -> str:
    """Validate a name used to FIND files on an image, lowercased to match how
    put_file writes them.

    Deliberately laxer than cbm_filename: the CBM wildcards `*` and `?` are
    legitimate here (see delete_file), so only the metacharacters that would
    retarget the operation are rejected.
    """
    name = str(raw).strip()
    if not name:
        raise DiskError("filename is empty")
    if len(name) > 16:
        raise DiskError(
            f"filename {name!r} is {len(name)} chars; CBM names max out at 16")
    for ch in name:
        if ch in _DOS_METACHARACTERS:
            raise DiskError(
                f"filename {name!r}: {ch!r} is a CBM DOS metacharacter — it "
                "would silently retarget this at a different file"
            )
        if not 0x20 <= ord(ch.upper()) <= 0x5D:
            raise DiskError(
                f"filename {name!r}: {ch!r} won't survive as a CBM filename "
                "(use a-z, 0-9, space, and simple punctuation)"
            )
    return name.lower()


def rename_file(image: str | Path, old: str, new: str) -> str:
    """Rename a file on IMAGE in place. Returns the new CBM name.

    A wildcard in OLD is refused by c1541 itself as DOS error 30, so a rename
    can never act on more than the one file you named.
    """
    old = cbm_lookup_name(old)
    name = cbm_filename(new)
    _run_checked([str(image), "-rename", str(old), name],
                 f"renaming {old!r} to {name!r} on {Path(image).name}")
    return name


def delete_file(image: str | Path, name: str) -> int:
    """Scratch a file from IMAGE. Returns how many entries were removed.

    c1541 answers a scratch with "ERR = 01, FILES SCRATCHED, <n>, 00" whether
    or not anything matched, so the count is the only reliable way to tell a
    successful delete from a typo.

    NAME may use the CBM wildcards `*` (any tail) and `?` (any one character),
    which scratch every match at once — `delete_file(img, "al*")` removes both
    'alpha' and 'album' and returns 2, and `delete_file(img, "*")` wipes the
    disk and returns the true count. The returned count stays honest under
    wildcards (measured), so it is what you check, not the absence of an error.
    """
    name = cbm_lookup_name(name)
    out = _run_checked([str(image), "-delete", str(name)],
                       f"deleting {name!r} from {Path(image).name}")
    status = dos_status(out)
    scratched = status[2] if status else 0
    if scratched == 0:
        raise DiskError(
            f"no file named {name!r} on {Path(image).name} — nothing deleted")
    return scratched


def block_read(image: str | Path, track: int, sector: int) -> bytes:
    """Read one 256-byte sector. Track is 1-based, sector 0-based — the CBM
    convention, and what a directory entry stores.

    On a 1541 image, 18/0 is the BAM and 18/1 the first directory sector.
    """
    check_block(image, track, sector)
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "block.bin"
        _run_checked([str(image), "-bread", str(dest), str(track), str(sector)],
                     f"reading track {track} sector {sector}")
        if not dest.exists():
            raise DiskError(
                f"c1541 reported success but wrote no block for "
                f"track {track} sector {sector}")
        data = dest.read_bytes()
    if len(data) != BLOCK_SIZE:
        raise DiskError(
            f"track {track} sector {sector}: c1541 returned {len(data)} bytes, "
            f"expected {BLOCK_SIZE}")
    return data


def block_write_file(image: str | Path, track: int, sector: int,
                     src: str | Path) -> None:
    """Overwrite a whole sector from a host file.

    The file must be exactly 256 bytes. Measured: c1541 rejects a shorter one
    with an unhelpful "floppy read failed" (exit 1, naming neither the file nor
    its size) and silently truncates a longer one to 256 at exit 0. Checking
    the size here turns both into one message that names the real size.
    """
    check_block(image, track, sector)
    src = Path(src)
    try:
        size = src.stat().st_size
    except OSError as e:
        raise DiskError(f"no such file to write: {src} ({e.strerror})") from None
    if size != BLOCK_SIZE:
        raise DiskError(
            f"{src}: {size} bytes — a sector write needs exactly {BLOCK_SIZE} "
            "bytes (c1541 rejects anything shorter and truncates anything longer)")
    _run_checked([str(image), "-bwrite", str(src), str(track), str(sector)],
                 f"writing track {track} sector {sector}")


def block_poke(image: str | Path, track: int, sector: int, offset: int,
               data: bytes) -> None:
    """Write bytes at an offset inside a sector, leaving the rest alone.

    An out-of-range track or sector is the safe case: c1541 catches it itself
    with `Error - Track 18, Sector 25 out of bounds.` and exit 1 (check_block
    still runs first, only so the message can name the limit). The offset is
    where it goes quiet — both bad-offset cases exit 0 with no diagnostic at
    all, so the guards below are the only thing standing between a caller and
    a write it never learns went wrong.
    """
    check_block(image, track, sector)
    if not data:
        raise DiskError("no bytes to poke")
    if not 0 <= offset < BLOCK_SIZE:
        raise DiskError(
            f"offset {offset} out of range (0-{BLOCK_SIZE - 1}) "
            "(c1541 writes nothing at all and still exits 0)")
    if offset + len(data) > BLOCK_SIZE:
        raise DiskError(
            f"offset {offset} + {len(data)} bytes runs past the end of the "
            f"{BLOCK_SIZE}-byte sector (c1541 exits 0 having written only the "
            "bytes that fit — measured: 2 of 4 at offset 254)")
    _run_checked([str(image), "-bpoke", str(track), str(sector), str(offset),
                  *[str(b) for b in data]],
                 f"poking track {track} sector {sector}")


def validate_image(image: str | Path) -> dict:
    """Run the CBM allocation check (the disk fsck) over IMAGE, in place.

    Measured: beyond c1541's usual attach/detach chatter, `img -validate` says
    only `validating in unit 8 ...` — the same line, exit 0 and no DOS status
    line, whether the BAM was already correct or was silently rewritten. It
    never reports what it repaired. So cleanliness is decided here by comparing
    the image before and after: a clean image comes back byte-identical, a
    repaired one does not.

    Like the real command this rewrites the BAM, so it modifies the image.

    `repaired_blocks` is the size of the change in blocks free, which can be 0
    on an image that was genuinely repaired — the reported free total leaves the
    directory track out, so a repair confined to it is invisible in the count
    (measured). `clean` is the flag to trust; `repaired_blocks` sizes it.
    """
    image = Path(image)
    try:
        before_bytes = image.read_bytes()
    except OSError as e:
        raise DiskError(f"no such image to validate: {image} ({e.strerror})") from None
    before_free = list_files(image)["blocks_free"]
    _run_checked([str(image), "-validate"], f"validating {image.name}")
    after_bytes = image.read_bytes()
    after_free = list_files(image)["blocks_free"]
    clean = before_bytes == after_bytes
    messages: list[str] = []
    if not clean:
        delta = after_free - before_free
        if delta > 0:
            messages.append(
                f"BAM claimed {delta} block(s) that no file owns; validate "
                f"reclaimed them ({before_free} -> {after_free} free)")
        elif delta < 0:
            messages.append(
                f"BAM under-reported allocation by {-delta} block(s); validate "
                f"corrected it ({before_free} -> {after_free} free)")
        else:
            messages.append(
                f"validate rewrote the BAM but the free count did not move "
                f"(still {after_free}); a repair on the directory track, which "
                f"the total leaves out, looks like this")
    return {"image": str(image), "clean": clean,
            "blocks_free_before": before_free, "blocks_free_after": after_free,
            "repaired_blocks": abs(after_free - before_free),
            "messages": messages}
