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

import yaml

from .basic import tokenize
from .build import build_asm
from .machines import MachineProfile, get_profile


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


# The DOS status line. The track/sector pair is optional and the message may
# itself contain commas ("ERR = 67, ILLEGAL SYSTEM T OR S, 36, 01" — measured),
# so the message is non-greedy and the numeric pair is anchored to the end of
# the line rather than assumed. A line that opens `ERR =` and still does not
# parse is a format change, and dos_status raises rather than reporting "no
# status" — silent degradation is what makes a scratch look like it matched
# nothing.
_ERR_RE = re.compile(
    r"^ERR = (\d+),\s*(.+?)(?:,\s*(\d+),\s*(\d+))?\s*$", re.MULTILINE)
_ERR_LINE_RE = re.compile(r"^ERR =", re.MULTILINE)

# c1541's out-of-bounds complaint. Not anchored to column 0: the surrounding
# attach/detach chatter has moved before, and an indented copy is still the
# same diagnostic.
_ERROR_LINE_RE = re.compile(r"^\s*Error -\s*(.*?)\s*$", re.MULTILINE)

# c1541's own diagnostics. Measured against VICE 3.10, all three arrive WITH a
# non-zero exit: a short -bwrite prints "floppy read failed" (rc 1), a
# duplicate-name -write "floppy write failed" (rc 1), and an overflowing -write
# "no space on image?" (rc 1). _run2 therefore raises before _run_checked ever
# scans for them — see the note on that scan.
_FAILURE_TEXT = ("no space on image?", "floppy write failed",
                 "floppy read failed")

# DOS codes that are not failures: 00 is OK, 01 is the normal reply to a
# scratch (its third field carries how many files were actually removed).
_OK_CODES = (0, 1)


def dos_status(out: str) -> tuple[int, str, int, int] | None:
    """Parse c1541's DOS status line into (code, message, track, sector).

    Returns None when there is no status line at all. A status line that does
    not parse raises instead: every caller treats "no status" as "nothing to
    check", so a silent None on a changed format would turn a failed scratch
    into a reported success. Track and sector default to 0 when c1541 omits
    them.
    """
    m = _ERR_RE.search(out)
    if not m:
        if _ERR_LINE_RE.search(out):
            line = next(ln for ln in out.splitlines() if ln.startswith("ERR ="))
            raise DiskError(
                f"cannot parse c1541's DOS status line {line.strip()!r} — its "
                "format has changed and disk operations can no longer be checked")
        return None
    return (int(m.group(1)), m.group(2).strip(),
            int(m.group(3) or 0), int(m.group(4) or 0))


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
    answer 01 must re-parse the returned text with dos_status() and check the
    count field itself — see delete_file. The ERR line is deliberately left in
    the returned text for exactly that.

    Returns stdout AND stderr, joined. dos_status is parsed here from the same
    combined text, so handing a caller stdout alone would let the two disagree
    the day c1541 moves the ERR line to stderr — delete_file would read a
    scratch count of 0 and call a successful delete a missing file.
    """
    stdout, stderr = _run2(args)
    combined = stdout + stderr
    status = dos_status(combined)
    if status is not None and status[0] not in _OK_CODES:
        code, message, track, sector = status
        detail = f" at track {track} sector {sector}" if track or sector else ""
        raise DiskError(f"{context}: {message.lower()} (DOS error {code}){detail}")
    # Both scans below are unreachable on VICE 3.10 and kept deliberately:
    # every case that prints "Error -" or one of _FAILURE_TEXT also exits
    # non-zero (measured — see _FAILURE_TEXT), so _run2 has already raised.
    # They are the guard against a c1541 that reports one of these at exit 0,
    # which is the exact class of bug this whole function exists for. Do not
    # delete them because coverage calls them dead.
    m = _ERROR_LINE_RE.search(combined)
    if m:
        raise DiskError(f"{context}: {m.group(1)}")
    for needle in _FAILURE_TEXT:
        if needle in combined:
            raise DiskError(f"{context}: c1541 reported {needle!r}")
    return combined


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
    """Write SRC onto IMAGE as NAME (default: the source stem, lowercased).

    Goes through _run_checked rather than _run so a write that c1541 answers
    with a DOS error line at exit 0 cannot pass for success. Measured caveat:
    every write failure reproduced here — full disk, full directory, duplicate
    name, missing image, missing source — already exits 1, so on this c1541
    (VICE 3.10) the check is a guard against the exit-0 class, not a fix for a
    failure seen slipping through.

    An explicit NAME is validated and lowercased through cbm_filename, so a
    name written here can be found again by delete_file/rename_file/get_file,
    which all lowercase their lookup argument. Without it,
    put_file(img, src, "ALPHA") wrote a file delete_file(img, "ALPHA") could
    not match. The NAME=None default keeps the bare source stem: the build
    path already validates its own names in load_disk_manifest, and tightening
    the default would newly reject stems the `disk put` command accepts today
    (an underscore is not PETSCII-printable).
    """
    src = Path(src)
    cbm_name = cbm_filename(name) if name is not None else src.stem.lower()
    _run_checked([str(image), "-write", str(src), cbm_name],
                 f"writing {src.name} as {cbm_name!r} to {Path(image).name}")
    return cbm_name


def get_file(image: str | Path, name: str, dest: str | Path) -> Path:
    """Read NAME off IMAGE into DEST. Returns DEST.

    NAME goes through cbm_lookup_name for the same reason the write paths do.
    Measured: `c1541 img -read 'zed,alpha' out` exits 0 and returns *zed* — the
    comma ends the name, and what follows is CBM DOS's type/mode field, judged
    by its first character alone. `,alpha` is accepted because `a` is append;
    so are `,p`, `,r` and `,w`, while `,s`, `,z` and a bare `,` exit 1. It is
    not a second filename: `alpha,zed` exits 1 even though both files are on
    the disk. So a comma in NAME does not retarget the read at what follows it
    — it silently reads whatever *precedes* the comma, which is still a file
    other than the one asked for.
    The CBM wildcards `*` and `?` stay legal, as they do for delete_file:
    `-read '*'` fetches the first directory entry (measured), which is how a
    disk's autostart program is pulled back off an image.
    """
    name = cbm_lookup_name(name)
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
        # cbm_title is shared with the packaging layer, so all of its messages
        # open with the noun "title". This path is always about a file on a
        # disk, so swap the noun rather than telling someone naming a file that
        # their title is wrong.
        msg = str(e)
        if msg.startswith("title "):
            msg = f"filename {msg[len('title '):]}"
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
    given = str(raw).strip()
    if not given:
        raise DiskError("filename is empty")
    # Case the whole string once and validate THAT, the way cbm_title does,
    # rather than calling ch.upper() per character: 'ß'.upper() is 'SS', so
    # ord(ch.upper()) raises TypeError instead of DiskError, and 'ı'/'ſ'
    # upper-case to 'I'/'S' — in range, so they slipped through into a c1541
    # argument as their original non-ASCII selves. Validating the cased form
    # also means the length check counts the characters c1541 will actually
    # store ('ß' costs two).
    name = given.upper()
    if len(name) > 16:
        raise DiskError(
            f"filename {given!r} is {len(name)} chars; CBM names max out at 16")
    for ch in name:
        if ch in _DOS_METACHARACTERS:
            raise DiskError(
                f"filename {given!r}: {ch!r} is a CBM DOS metacharacter — it "
                "would silently retarget this at a different file"
            )
        if not 0x20 <= ord(ch) <= 0x5D:
            raise DiskError(
                f"filename {given!r}: {ch!r} won't survive as a CBM filename "
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
    # _run_checked returns stdout+stderr, the same text it parsed its own
    # status from, so this second parse cannot disagree with the first.
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
        # Cause-neutral lead-in: this catch is every OSError, not just ENOENT,
        # and "no such file" was a lie for the EACCES case.
        raise DiskError(f"cannot read {src} ({e.strerror})") from None
    if size != BLOCK_SIZE:
        raise DiskError(
            f"{src}: {size} bytes — a sector write needs exactly {BLOCK_SIZE} "
            "bytes (c1541 rejects anything shorter and truncates anything longer)")
    _run_checked([str(image), "-bwrite", str(src), str(track), str(sector)],
                 f"writing track {track} sector {sector}")


def block_bytes(values) -> bytes:
    """Coerce a sequence of byte values to bytes, naming the one that is wrong.

    Python's own bytes() answers a bad element with "bytes must be in range(0,
    256)" — true, but it never says WHICH value, and both front ends
    (`c64 disk block write` and the c64_disk_block_write tool) hand it a whole
    list at once. Living here rather than in either front end is what stops the
    two from wording the same fault differently.
    """
    out = bytearray()
    for i, v in enumerate(values):
        try:
            b = v.__index__()
        except AttributeError:
            raise DiskError(
                f"byte {i} is {v!r}, which is not a whole number") from None
        if not 0 <= b <= 255:
            raise DiskError(
                f"byte {i} is {b}, out of range for a byte (0-255)")
        out.append(b)
    return bytes(out)


def block_poke(image: str | Path, track: int, sector: int, offset: int,
               data) -> None:
    """Write bytes at an offset inside a sector, leaving the rest alone.

    An out-of-range track or sector is the safe case: c1541 catches it itself
    with `Error - Track 18, Sector 25 out of bounds.` and exit 1 (check_block
    still runs first, only so the message can name the limit). The offset is
    where it goes quiet — both bad-offset cases exit 0 with no diagnostic at
    all, so the guards below are the only thing standing between a caller and
    a write it never learns went wrong.

    DATA may be bytes or any sequence of ints; it is coerced through
    block_bytes so an out-of-range value is named rather than surfacing
    Python's bare "bytes must be in range(0, 256)".
    """
    check_block(image, track, sector)
    data = block_bytes(data)
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


def _validate_findings(out: str) -> list[str]:
    """Every DOS status line `-validate` printed, in report form.

    Not dos_status(): validate can print several ("ERR = 65, NO BLOCK" arrives
    twice for one bad directory entry — measured), and dos_status returns only
    the first. Callers of this get all of them.
    """
    findings = []
    for m in _ERR_RE.finditer(out):
        code = int(m.group(1))
        if code in _OK_CODES:
            continue
        track, sector = int(m.group(3) or 0), int(m.group(4) or 0)
        where = f" at track {track} sector {sector}" if track or sector else ""
        findings.append(
            f"{m.group(2).strip().lower()} (DOS error {code}){where}")
    return findings


def validate_image(image: str | Path) -> dict:
    """Run the CBM allocation check (the disk fsck) over IMAGE, in place.

    Measured: on a BAM inconsistency, `img -validate` says only `validating in
    unit 8 ...` beyond c1541's usual attach/detach chatter — the same line,
    exit 0 and no DOS status line, whether the BAM was already correct or was
    silently rewritten. It never reports what it repaired. So *repair* is
    decided here by comparing the image before and after: a byte-identical
    image was not touched.

    Structural damage is the other half, and it is why this one verb does NOT
    go through _run_checked. Measured: pointing a directory entry's data block
    at track 40 of a 35-track d64 makes `-validate` print
    `ERR = 65, NO BLOCK, 00, 40` (twice) at exit 0 — and _run_checked, which
    exists so a DOS status line at exit 0 cannot pass for success, saw code 65
    and raised. That turned `c64 disk validate`'s primary use case, a damaged
    image, into exit 1 with no payload. Here a status line is a *finding about
    the image*, not a failed operation, so each one is folded into `messages`
    and `clean` goes False. (This particular damage c1541 does not repair: the
    image comes back byte-identical and the free count does not move.)

    Like the real command this rewrites the BAM, so it modifies the image.

    Cost, accepted rather than optimised: 2 whole-image read_bytes() and 3
    c1541 spawns per call (two `-list`, one `-validate`). That is the price of
    deciding cleanliness format-agnostically — c1541 reports nothing either
    way, so the only evidence is the image itself, and comparing bytes works
    identically on a d64, d71 and d81 (verified on all three). A
    format-specific BAM walk would be cheaper and would have to be written
    three times.

    `repaired_blocks` is the size of the change in blocks free, which can be 0
    on an image that was genuinely repaired — the reported free total leaves the
    directory track out, so a repair confined to it is invisible in the count
    (measured). `clean` is the flag to trust; `repaired_blocks` sizes it.
    """
    image = Path(image)
    try:
        before_bytes = image.read_bytes()
    except OSError as e:
        # Cause-neutral: a chmod-000 image is not a missing one.
        raise DiskError(f"cannot read image {image} ({e.strerror})") from None
    before_free = list_files(image)["blocks_free"]
    stdout, stderr = _run2([str(image), "-validate"])
    combined = stdout + stderr
    # Not for its return value: dos_status raises on an `ERR =` line whose
    # format it no longer recognises, and losing that guard here would turn a
    # c1541 format change into a silently clean report.
    dos_status(combined)
    findings = _validate_findings(combined)
    after_bytes = image.read_bytes()
    after_free = list_files(image)["blocks_free"]
    repaired = before_bytes != after_bytes
    clean = not repaired and not findings
    messages: list[str] = [f"validate reported {f}" for f in findings]
    if repaired:
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


# Directory entries an image holds, measured by writing 1-block files until
# c1541 refused: the 145th write to a d64 or a d71, and the 297th to a d81,
# exits 1 with "ERR = 72, DISK FULL" — on a d64 with 520 blocks still free.
# A block budget alone cannot predict that, so build_disk checks both.
MAX_DIR_ENTRIES = {".d64": 144, ".d71": 144, ".d81": 296}

# Four dicts, one key set. drive_type_for is the only guarded lookup — it is
# what raises the message naming the supported types — and everything after it
# (GEOMETRY in _geometry_for, TOTAL_BLOCKS and MAX_DIR_ENTRIES in build_disk)
# indexes bare on the strength of that check. Adding a fifth image format to
# one dict and not the others would turn that into a naked KeyError, so the
# coupling is checked here, at import, instead of being discovered by it.
# A real `raise`, not an `assert`: `python -O` strips assert statements, and a
# guard that disappears under the flag a packager reaches for is no guard.
if not (IMAGE_DRIVE_TYPES.keys() == GEOMETRY.keys() == TOTAL_BLOCKS.keys()
        == MAX_DIR_ENTRIES.keys()):
    raise RuntimeError(
        "disk image format tables disagree: "
        f"IMAGE_DRIVE_TYPES={sorted(IMAGE_DRIVE_TYPES)} "
        f"GEOMETRY={sorted(GEOMETRY)} TOTAL_BLOCKS={sorted(TOTAL_BLOCKS)} "
        f"MAX_DIR_ENTRIES={sorted(MAX_DIR_ENTRIES)}")

# c1541 formats with a single `label,id` argument, so a comma inside the id
# starts a third field: measured, `-format "g,ab,cd"` exits 0 and writes id
# `ab`, dropping `cd` without a word. The rest are the CBM DOS metacharacters
# cbm_lookup_name already refuses in filenames.
_ID_METACHARACTERS = '":,='

# Keys a `files:` entry may carry. A typo'd key is refused rather than ignored,
# the way cart_build refuses an unknown bank window: silently dropping `nmae:`
# would write the file under a name the author never asked for.
_FILE_KEYS = {"src", "name"}


def _disk_id(path: Path, raw) -> str:
    disk_id = str(raw)
    if len(disk_id) != 2:
        # Measured: PyYAML reads an unquoted `id: 01` as the integer 1, so the
        # id that arrives here is a character shorter than the one the manifest
        # wrote. Say so, the way the bank-key guard explains YAML's coercions.
        hint = ""
        if not isinstance(raw, str):
            hint = (f" — an unquoted id is parsed by YAML as a "
                    f"{type(raw).__name__} ({raw!r} here, so `01` arrives "
                    f"as `1`)")
            # Only offer the quote-it fix when it produces a legal id. For
            # `id: 12345` zfill(2) is a no-op and the suggestion would be a
            # value the very next length check rejects.
            if len(disk_id.zfill(2)) == 2:
                hint += f'; quote it: id: "{disk_id.zfill(2)}"'
        raise DiskError(
            f"{path}: disk id {disk_id!r} must be exactly two characters{hint}")
    # Case the whole string once and validate THAT, the way cbm_lookup_name
    # does: 'ß'.upper() is 'SS', so the old per-character ord(ch.upper()) raised
    # TypeError — a traceback where AGENTS.md promises exit 1, since disk build
    # catches only DiskError/BuildError/BasicError/KeyError — and 'ı'.upper() is
    # 'I', inside the range, so a dotless i passed the check and reached c1541's
    # `-format label,id` as its own non-ASCII self.
    cased = disk_id.upper()
    if len(cased) != 2:
        raise DiskError(
            f"{path}: disk id {disk_id!r} upper-cases to {cased!r}, "
            f"{len(cased)} characters; a disk id is exactly two")
    # `isascii()` and not just the range check on the cased form: unlike
    # cbm_lookup_name this returns the id the manifest wrote, not the cased
    # one, so 'ı' passing because 'I' is in range would put the dotless i
    # itself on the c1541 command line.
    for ch, up in zip(disk_id, cased, strict=True):
        if ch in _ID_METACHARACTERS or not ch.isascii() \
                or not 0x20 <= ord(up) <= 0x5D:
            raise DiskError(
                f"{path}: disk id {disk_id!r}: {ch!r} does not survive c1541's "
                "`-format label,id` (use a-z, 0-9, or simple punctuation)")
    return disk_id


def load_disk_manifest(path: str | Path) -> dict:
    """Parse a *.disk.yaml manifest, resolving every source against it.

    Returns {"label", "id", "files", "path"}; each file carries its declared
    `src` and `name` plus the `cbm_name` it will be written as — `*` means "the
    disk label", a missing name means the source stem. Every one of those is
    validated here, before anything is built: c1541 stores only the first 16
    characters of a name at exit 0 (measured), so two long names would collide
    into one file with nothing said.
    """
    # Imported here, not at module scope: packaging imports from disk.
    from .packaging import PackageError, cbm_title

    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise DiskError(f"{path}: {e}") from None
    except OSError as e:
        raise DiskError(f"no such disk manifest: {path} ({e.strerror})") from None
    if not isinstance(raw, dict):
        raise DiskError(f"{path}: manifest must be a YAML mapping")
    try:
        label = cbm_title(raw.get("label") or path.stem.replace(".disk", ""))
    except PackageError as e:
        raise DiskError(f"{path}: {e}") from None
    disk_id = _disk_id(path, raw.get("id", "00"))
    entries = raw.get("files")
    if not isinstance(entries, list) or not entries:
        raise DiskError(f"{path}: manifest needs a non-empty `files:` list")
    files: list[dict] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or "src" not in entry:
            raise DiskError(
                f"{path}: file {i} must be a mapping with a `src:` key")
        unknown = sorted(set(entry) - _FILE_KEYS)
        if unknown:
            raise DiskError(
                f"{path}: file {i} has unknown key(s) {unknown} "
                f"(use {' and '.join(sorted(_FILE_KEYS))})")
        src = (path.parent / str(entry["src"])).resolve()
        if not src.exists():
            raise DiskError(
                f"{path}: file {i} references {entry['src']}, which does not exist")
        if not src.is_file():
            # Measured: c1541 -write happily takes a directory path, exits 0 and
            # leaves a 1-block junk file on the disk — a build that reports
            # success and ships a broken image.
            raise DiskError(
                f"{path}: file {i} references {entry['src']}, which is a "
                "directory — a disk file must be a file")
        name = entry.get("name")
        name = None if name is None else str(name)
        try:
            resolved = (label.lower() if name == "*"
                        else cbm_filename(name if name is not None else src.stem))
        except DiskError as e:
            raise DiskError(f"{path}: file {i} ({entry['src']}): {e}") from None
        if resolved in seen:
            raise DiskError(f"{path}: CBM name {resolved!r} appears twice")
        seen.add(resolved)
        files.append({"src": src, "name": name, "cbm_name": resolved})
    return {"label": label, "id": disk_id, "files": files, "path": path}


def _manifest_artifact(src: Path, workdir: Path, profile: MachineProfile) -> Path:
    """Build a manifest entry into the file that is actually written to disk.

    Same build-as-needed dispatch as package_program: .s is assembled, .bas is
    tokenized, everything else (.bin/.prg/.sid/...) is written verbatim.
    """
    ext = src.suffix.lower()
    if ext == ".s":
        return build_asm(src, out_prg=workdir / f"{src.stem}.prg",
                         basic_start=profile.basic_start).prg
    if ext == ".bas":
        return tokenize(src, workdir / f"{src.stem}.prg", profile.basic_version)
    return src


def build_disk(manifest: str | Path, out: str | Path | None = None,
               model: str = "c64") -> dict:
    """Create a disk image and populate it from a manifest, in listed order.

    The first file is written first, so `x64sc image.d64` and `c64 disk boot`
    autostart it (they issue LOAD"*",8,1).

    The build is all-or-nothing. Every image is formatted and populated under a
    temporary name in the output's own directory and renamed over OUT only
    after the last file has landed, so a build that fails partway leaves an
    existing image at OUT byte-identical and no half-written one anywhere. That
    is what makes it safe against the failures c1541 reports mid-write —
    measured: `-write` of an unreadable source exits 1 with "cannot read file
    ... Permission denied" after earlier files are already on the disk.

    Overflow is refused earlier still, before anything is formatted, both for
    blocks and for directory entries: measured, c1541 answers a d64 write that
    does not fit by leaving a truncated 664-block file behind, and answers the
    145th file by failing with the first 144 already written. Predicting the
    cost from the source sizes turns both into an error that names the file.

    Every `.s` entry's `.lbl` is copied beside OUT as
    `<out-stem>.<cbm-name>.lbl` and returned under `labels`, keyed by CBM name,
    so a program loaded off the built disk can still be debugged symbolically.
    One file per entry rather than one merged table: two assembled programs on
    one disk are separate namespaces, and merging them would silently collide
    on every `start`/`loop` they share.

    Known limit, documented rather than fixed: the staging directory lives
    beside OUT (it has to, for os.replace to stay atomic), so a SIGKILL — not
    an ordinary failure, which the context manager cleans up — can orphan a
    `.<stem>-build-*` directory there. Sweeping stale siblings at the start of
    the next build was the alternative and was rejected: it cannot tell a dead
    directory from the live staging area of a build running concurrently
    against the same output, and deleting that one would break a working build
    to tidy up after a dead one. Removing the stray by hand is safe.
    """
    spec = load_disk_manifest(manifest)
    path = spec["path"]
    # Resolved up front: an unknown model must not surface only in the run hint,
    # after an image has already been written.
    profile = get_profile(model)
    image = Path(out) if out is not None else path.with_suffix("").with_suffix(".d64")
    suffix = image.suffix.lower()
    drive_type_for(image)                   # raises for an unsupported type
    total = TOTAL_BLOCKS[suffix]
    max_entries = MAX_DIR_ENTRIES[suffix]
    if len(spec["files"]) > max_entries:
        raise DiskError(
            f"{path}: {len(spec['files'])} files, but a "
            f"{suffix.lstrip('.')} directory holds {max_entries} — "
            "nothing was written")

    if not image.parent.is_dir():
        raise DiskError(f"{path}: no such output directory: {image.parent}")
    if image.exists() and not image.is_file():
        # os.replace onto a directory raises IsADirectoryError; say it here,
        # before a whole image has been built for a destination it cannot use.
        raise DiskError(f"{path}: output {image} is not a file")

    # Two temporary areas, on purpose. Built artifacts can live anywhere, but
    # the staged image is renamed over OUT at the end and os.replace is atomic
    # only within one filesystem — measured, the default temp dir here is a
    # different device from the working tree, so staging it there would demote
    # the swap to a copy that can fail halfway.
    with tempfile.TemporaryDirectory() as td, \
            tempfile.TemporaryDirectory(
                dir=image.parent, prefix=f".{image.stem}-build-") as staging:
        workdir = Path(td)
        planned = []
        for entry in spec["files"]:
            artifact = Path(_manifest_artifact(entry["src"], workdir, profile))
            cost = blocks_for(artifact.stat().st_size)
            planned.append((entry, artifact, cost))

        used = 0
        for entry, artifact, cost in planned:
            if used + cost > total:
                raise DiskError(
                    f"{path}: {entry['cbm_name']!r} ({artifact.name}) needs "
                    f"{cost} blocks but only {total - used} of {total} remain "
                    f"on a {suffix.lstrip('.')} — nothing was written")
            used += cost

        staged = Path(staging) / image.name
        create_image(staged, label=spec["label"].lower(), disk_id=spec["id"])
        for entry, artifact, _ in planned:
            put_file(staged, artifact, entry["cbm_name"])
        # Nothing above this line can touch OUT: the whole image is built in a
        # staging directory and swapped in with one atomic rename, so a build
        # that fails anywhere above leaves an existing OUT exactly as it was.
        # Below the line is a different guarantee — the label copies CAN fail
        # (a full disk, a read-only output directory), and if one does it
        # raises with OUT already replaced. That is the deliberate ordering:
        # the image is the artifact, the .lbl files are a convenience beside
        # it, so a half-written set of labels beats a build that lost the image.
        os.replace(staged, image)

        # After the swap, while workdir still exists: build_asm writes its
        # label file next to the .prg it produced, which is inside workdir and
        # about to be deleted with it.
        #
        # These are only ever written, never swept: a rebuild whose manifest
        # dropped or renamed an entry leaves the previous run's
        # `<stem>.<oldname>.lbl` sitting beside the image. Deliberate — the
        # sweep would have to glob `<stem>.*.lbl`, which is also what a
        # hand-written label file beside the image looks like. Documented in
        # docs/cli.md under `c64 disk build`.
        labels: dict[str, str] = {}
        for entry, artifact, _ in planned:
            lbl = artifact.with_suffix(".lbl")
            if entry["src"].suffix.lower() != ".s" or not lbl.exists():
                continue
            kept = image.parent / f"{image.stem}.{entry['cbm_name']}.lbl"
            shutil.copyfile(lbl, kept)
            labels[entry["cbm_name"]] = str(kept)

    listing = list_files(image)
    return {"image": str(image), "label": spec["label"], "labels": labels,
            "files": [f["name"] for f in listing["files"]],
            "blocks_used": total - listing["blocks_free"],
            "blocks_free": listing["blocks_free"], "blocks_total": total,
            # Same hint the packaging/cart builders emit: a stock x64sc boots
            # its default (PAL) machine, so the profile's video flag travels.
            "run": " ".join([profile.vice_emulator, *profile.vice_args, str(image)])}
