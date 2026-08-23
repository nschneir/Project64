"""Charset glyph encoding: ASCII art in, ca65 `.byte` rows out.

The charset twin of sprites.encode_sprite. Multicolor text glyphs
(`$D016` bit 4) are 8 rows of 4 pixel pairs; pair values map to colors as
fixed by the hardware: 00 = background ($D021), 01 = $D022, 10 = $D023,
11 = the low 3 bits of the cell's color-RAM nybble. Hires glyphs are 8
rows of 8 single-bit pixels.

The legend deliberately differs from the sprite one (' .#+', where '.'
is pair 01): charset blocks are name:-delimited so rows cannot contain
spaces, '.' is the natural "background", and the two hardware modes
order their colors differently anyway. Legend: '.123' multicolor,
'.#' hires.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import NamedTuple

_MC_LEGEND = {".": 0b00, "1": 0b01, "2": 0b10, "3": 0b11}
_HIRES_LEGEND = {".": 0, "#": 1}
ROWS_PER_GLYPH = 8

#: what a block header's `:mode` suffix may say. An empty suffix (a bare
#: `name:`) means "whatever the file is", so a sheet that never mentions a
#: mode reads exactly as it always did.
BLOCK_MODES = {"hires": False, "multicolor": True}


class Glyph(NamedTuple):
    """One block: its name, its 8 art rows, and the mode they are drawn in.

    A tuple, so `glyphs[i][0]` and `[1]` still mean name and rows; the mode
    is the third field because a sheet may mix them.
    """

    name: str
    rows: list[str]
    multicolor: bool


class CharsetError(ValueError):
    """A sheet that does not describe 8-row glyphs in the legend."""


def _shape(multicolor: bool) -> tuple[int, dict[str, int]]:
    return (4, _MC_LEGEND) if multicolor else (8, _HIRES_LEGEND)


#: A `:mode` suffix, the only tail a header has that is not part of its name.
_MODE_SUFFIX_RE = re.compile(rf":\s*({'|'.join(BLOCK_MODES)})\s*$", re.IGNORECASE)


def is_block_header(stripped: str, widths: Sequence[int],
                    legend: Iterable[str]) -> bool:
    """Is this non-row line a block header rather than a mis-typed pixel row?

    The three spellings that are a header whatever else they look like: the
    explicit `name:` prefix, a trailing bare `:`, and a known `:mode` suffix.
    Any other colon-bearing line is a header too — `wall:mono` has to reach
    `parse_block_header` to be rejected as a mode typo — *unless* it is
    shaped like a mis-typed row: at one of the block's row `widths` and made
    of nothing but `legend` characters and the stray colon. That carve-out is
    what tells `.1:3` from `wall:mono`, and without it the mis-typed row
    opened a block, so the sheet was reported as the PREVIOUS glyph having
    too few rows rather than as an illegal legend character on the line that
    has one. `widths` and `legend` have no defaults for that reason: both
    sheet parsers know their block's own mode at the line they are reading,
    and a default would quietly restore the rule this exists to replace.
    """
    if (stripped.startswith("name:") or stripped.endswith(":")
            or _MODE_SUFFIX_RE.search(stripped) is not None):
        return True
    if ":" not in stripped:
        return False
    return not (len(stripped) in widths
                and set(stripped) <= set(legend) | {":"})


def parse_block_header(stripped: str, lineno: int, file_multicolor: bool,
                       kind: str = "charset",
                       error: type[ValueError] = CharsetError) -> tuple[str, bool]:
    """Split a header into (name, multicolor), resolving its mode suffix.

    Shared by both sheet encoders: sprite sheets spell their block headers
    exactly the way charset sheets do (`name:`, `wall:multicolor`,
    `fighter:hires`), so there is one parser and one rejection message.
    `kind` and `error` only name the caller in that message and pick the
    exception its own callers already catch.

    A colon is both the mode separator and a character a glyph name may hold
    (`hud:score` encoded fine before modes existed), and the two are told
    apart by the `name:` prefix, not by guessing:

    - `wall:multicolor`, `wall:hires` — mode, in either spelling.
    - `wall:` — bare header, the file's mode.
    - `wall:mono` — no prefix and no known mode, so it is a mode TYPO and is
      rejected. The alternative rule ("anything unknown is name") would take
      a mis-typed mode silently, and the block would encode in the file's
      mode instead of the one the author asked for.
    - `name: hud:score` — the prefix says where the name starts, so the rest
      is the name; the rejection above names this spelling as the way to
      write a colon into a name. A trailing `:mode` still wins after the
      prefix, so a glyph cannot be *called* `hud:hires`.
    """
    explicit = stripped.startswith("name:")
    body = (stripped.removeprefix("name:") if explicit else stripped).strip()
    m = _MODE_SUFFIX_RE.search(body)
    if m:
        return body[:m.start()].strip(), BLOCK_MODES[m.group(1).lower()]
    if body.endswith(":"):
        return body[:-1].strip(), file_multicolor
    if not explicit and ":" in body:
        mode = body.rpartition(":")[2].strip().lower()
        raise error(
            f"{kind} sheet line {lineno}: unknown mode {mode!r} — "
            f"use 'hires' or 'multicolor', or write the header as "
            f"`name: {body}` if the colon is part of the name")
    return body, file_multicolor


def parse_charset(text: str, multicolor: bool = True) -> list[Glyph]:
    """Split a glyph sheet into ordered `Glyph` blocks, validating each.

    A block is a `name: x` (or bare `x:`) header plus exactly 8 rows of
    exactly 4 (multicolor) or 8 (hires) legend characters. Blank lines are
    ignored; so are `#` comment lines — but a comment cannot consist solely
    of legend characters at exactly row width (it would BE a row), which
    only matters in hires mode where '#' is a legend character.
    File order is screen-code order.

    `multicolor` is the *file* mode. A header may override it for its own
    block by naming one — `wall:multicolor`, `letter:hires` — so a game
    whose maze charset is multicolor and whose HUD glyphs are hires is one
    sheet and one invocation. Row width follows the block's own mode.
    A name may itself hold a colon under the `name:` prefix — see
    `parse_block_header`, which is where a header's colons are read.
    """
    glyphs: list[Glyph] = []
    seen: set[str] = set()
    name: str | None = None
    rows: list[str] = []
    block_mc = multicolor

    def close(lineno: int) -> None:
        if name is None:
            return
        if len(rows) != ROWS_PER_GLYPH:
            raise CharsetError(
                f"glyph {name!r} (ending at line {lineno}) has {len(rows)} "
                f"rows, expected {ROWS_PER_GLYPH}")
        glyphs.append(Glyph(name, list(rows), block_mc))

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        width, legend = _shape(block_mc)
        is_row_shaped = len(line) == width and set(line) <= set(legend)
        if not stripped or (stripped.startswith("#") and not is_row_shaped):
            # Blank line or comment. A row of `#` at the wrong width is a
            # comment here too, not a width error: in hires `#` is both the
            # comment marker and a legend glyph, so a mis-typed row of nothing
            # but `#` and a `#####` divider are the same string and no rule
            # could separate them. A mixed mis-typed row (`#..#.#`) is
            # distinguishable in principle and is dropped by this same branch
            # anyway: one rule for every `#`-leading line, rather than a
            # carve-out that reports some width typos and stays silent on the
            # one shape it cannot tell from a divider.
            # `sprites.parse_sprite_sheet` drops it for the same reason;
            # deliberate in both, and the width check below is unreachable
            # for a line that starts with `#`.
            continue
        if not is_row_shaped and is_block_header(stripped, (width,), legend):
            close(lineno)                       # reads the OLD block's mode
            name, block_mc = parse_block_header(stripped, lineno, multicolor)
            if name in seen:
                raise CharsetError(
                    f"duplicate glyph name {name!r} at line {lineno}")
            seen.add(name)
            rows = []
            continue
        if name is None:
            raise CharsetError(
                f"line {lineno}: pixel row before any `name:` line")
        if is_row_shaped:
            rows.append(line)
            continue
        if len(line) != width:
            raise CharsetError(
                f"glyph {name!r} line {lineno}: {len(line)} characters, "
                f"expected exactly {width} ({line!r})")
        bad = sorted(set(line) - set(legend))
        raise CharsetError(
            f"glyph {name!r} line {lineno}: illegal legend characters {bad} "
            f"(legend is {''.join(legend)})")
    close(len(text.splitlines()))
    if not glyphs:
        raise CharsetError("no glyphs found")
    return glyphs


def parse_charset_file(path: str | Path,
                       multicolor: bool = True) -> list[Glyph]:
    """Read an authored sheet from disk and split it into `Glyph` blocks.

    The charset twin of `sprites.encode_sheet_file`: the read, and the naming
    of the file in whatever it raises, happen once — `c64 charset encode` and
    the c64_charset_encode tool had one each, worded identically, and only the
    rendering of a failure is the front ends' own half.

    `read_text` on a .prg or a .png raises UnicodeDecodeError — which IS a
    ValueError and is NOT an OSError, exactly the trap the CLI twin once
    leaked a traceback through — and whose own message is a byte offset and a
    codec: true, and no help in saying which of the paths was the wrong one.
    The emptiness check needs no line here; `parse_charset` already raises
    "no glyphs found" for a sheet that holds none.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read charset sheet {path}: {e}") from None
    return parse_charset(text, multicolor=multicolor)


def check_label(label: str, flag: str) -> None:
    """Reject a block label ca65 could not assemble, naming the caller's flag.

    Beside `format_glyphs` because that is what emits the label — as `NAME:`
    and `NAME_end:`, so anything the assembler will not take as an identifier
    produces a file that cannot be included rather than an error here. `flag`
    is the only thing either front end passes: the CLI says `--label`, the
    tool says `label`, and each caller is told about the one it used. It has
    no default on purpose — a default is one front end's spelling silently
    lent to the other, which is the drift this helper exists to prevent.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
        raise CharsetError(
            f"{flag} {label!r} is not an assembler identifier (letters, digits "
            f"and underscore, not starting with a digit)")


def encode_row(row: str, multicolor: bool = True) -> int:
    """Pack one art row into one charset byte (MSB = leftmost pixel)."""
    legend, bits = (_MC_LEGEND, 2) if multicolor else (_HIRES_LEGEND, 1)
    value = 0
    for ch in row:
        value = (value << bits) | legend[ch]
    return value


def format_glyphs(glyphs: list[Glyph], first_code: int = 0,
                  multicolor: bool = True, label: str = "glyphs") -> str:
    """Render glyph blocks as one contiguous labeled ca65 block.

    One leading `<label>:` and one `<label>_end:` — the consumer indexes off
    the base and sizes the copy with `glyphs_end - glyphs` (see
    demos/invaders/chars.s), so no per-glyph labels and no count byte.
    `label` names the pair (`glyphs` by default) so a program that installs
    several sheets gets several blocks in one file without renaming them on
    the way out.

    Each glyph is encoded in its own mode; `multicolor` only names the file
    default in the header comment, and a sheet that mixed modes says so
    there — the bytes are the same eight either way, but the reader needs to
    know which of them the VIC will read as pairs.
    """
    modes = {g.multicolor for g in glyphs}
    mode = ("mixed hires/multicolor" if len(modes) > 1
            else "multicolor" if modes == {True} else "hires")
    out = [
        f"; {len(glyphs)} {mode} glyphs, 8 bytes each, screen codes "
        f"{first_code}-{first_code + len(glyphs) - 1} — c64 charset encode",
        "; patch over a RAM charset at CHARSET + code*8",
        "",
        f"{label}:",
    ]
    for offset, glyph in enumerate(glyphs):
        suffix = "" if len(modes) == 1 else (
            "  (multicolor)" if glyph.multicolor else "  (hires)")
        out.append(f"        ; code {first_code + offset}: {glyph.name}{suffix}")
        for row in glyph.rows:
            out.append(f"        .byte   %{encode_row(row, glyph.multicolor):08b}"
                       f"    ; {row}")
    out.append(f"{label}_end:")
    out.append("")
    return "\n".join(out)
