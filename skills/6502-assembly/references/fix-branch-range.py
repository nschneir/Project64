"""Turn ca65 "Range error" failures into `jmp` trampolines, mechanically.

A 6502 branch reaches ±127 bytes. Growing a routine pushes existing
branches past that and ca65 fails with

    enemy.s(210): Error: Range error (204 not in [-128..127])

The fix never varies: invert the branch over a `jmp` to the real target,

    bne far            ->      beq :+
                               jmp far
                               :

so pipe the failing build's output straight in (this file ships
non-executable, like every other .py here, so name the interpreter):

    c64 build game.s 2>&1 | python3 fix-branch-range.py
    c64 build game.s 2>&1 | python3 fix-branch-range.py --dry-run

Exit 0 when every reported branch was rewritten (or there was nothing to
do), 1 when at least one was left for you — read the report, it says which
and why. Rewrites are in place; the build that follows is the check.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: `<file>(<line>): Error: Range error (...)` — ca65's own wording, and the
#: only line worth reading out of a failed build.
RANGE_ERROR = re.compile(r"^(?P<file>.+?)\((?P<line>\d+)\):\s*Error:\s*Range error")

#: A conditional branch, with an optional label in front and an optional
#: trailing comment. `bra` is deliberately absent: the NMOS 6502 has none.
BRANCH = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<label>(?:[A-Za-z_@][\w@]*)?:[ \t]+)?"
    r"(?P<op>b(?:eq|ne|cc|cs|mi|pl|vc|vs))[ \t]+"
    r"(?P<target>[^;\s]+)"
    r"(?P<trailer>[ \t]*(?:;.*)?)$",
    re.IGNORECASE,
)

#: An anonymous label DEFINITION: a `:` opening the line, not the `:+`/`:-`
#: of a reference (which only ever appears as an operand).
ANON_DEF = re.compile(r"^[ \t]*:(?![+-])")

#: An anonymous label REFERENCE in an operand: `:+`, `:++`, `:-`, …
ANON_REF = re.compile(r"(?<![\w.]):(?P<dirs>[+-]+)")

INVERSE = {"beq": "bne", "bne": "beq", "bcc": "bcs", "bcs": "bcc",
           "bmi": "bpl", "bpl": "bmi", "bvc": "bvs", "bvs": "bvc"}


def _anon_defs(lines: list[str]) -> list[int]:
    return [i for i, text in enumerate(lines) if ANON_DEF.match(text)]


def _resolve(defs: list[int], line: int, dirs: str) -> int | None:
    """The line an anonymous reference on `line` resolves to, or None if it
    dangles (a source that would not assemble anyway)."""
    if dirs[0] == "+":
        after = [d for d in defs if d > line]
        return after[len(dirs) - 1] if len(after) >= len(dirs) else None
    before = [d for d in defs if d < line]
    return before[-len(dirs)] if len(before) >= len(dirs) else None


def crossed_anon_refs(lines: list[str], branch: int) -> int:
    """How many anonymous references would change meaning if a new `:` were
    inserted just below `branch`.

    WHY this gate exists — and why the fix is refused rather than applied
    when it trips: an anonymous label has no name, only a position. `:+`
    means "the next `:` below me", so a `:` inserted between a reference and
    the label it resolves to silently retargets it — the reference still
    assembles, and now branches somewhere else. The trampoline's own `:` is
    exactly such an insertion. Nothing downstream can catch it (the build
    stays green), so the only safe answer is to hand the branch back to a
    human, which is what the caller does with a non-zero count.
    """
    defs = _anon_defs(lines)
    crossed = 0
    for i, text in enumerate(lines):
        for m in ANON_REF.finditer(text):
            target = _resolve(defs, i, m.group("dirs"))
            if target is None:
                continue
            forward = m.group("dirs")[0] == "+"
            # The new label lands between old lines `branch` and `branch`+1.
            if (forward and i <= branch < target) or \
                    (not forward and target <= branch < i):
                crossed += 1
    return crossed


class Skipped(Exception):
    """A branch this script must not touch; the message says why."""


def rewrite(lines: list[str], branch: int) -> list[str]:
    """The three lines that replace the branch on `lines[branch]`.

    Raises `Skipped` for anything the mechanical fix would get wrong.
    """
    if lines[branch].endswith(("\r\n", "\r")):
        # Named rather than fixed: the trampoline's three lines would go in
        # with LF and leave the file mixed, and `\r` is not in BRANCH's
        # trailer either, so without this the skip would blame the
        # instruction ("not a conditional branch") for the file's encoding.
        ending = "CRLF" if lines[branch].endswith("\r\n") else "CR"
        raise Skipped(f"{ending} line endings — convert the file to LF "
                      "(dos2unix) and re-run the build")
    m = BRANCH.match(lines[branch].rstrip("\n"))
    if not m:
        raise Skipped(f"not a conditional branch: {lines[branch].strip()!r}")
    target = m.group("target")
    if ANON_REF.match(target):
        # Same WHY as crossed_anon_refs: the trampoline's `:` would be
        # inserted right below this line, so a `jmp :+` here would resolve
        # to the new label instead of the one the author meant.
        raise Skipped(f"target {target} is an anonymous label — inverting it "
                      "would renumber its neighbours")
    crossed = crossed_anon_refs(lines, branch)
    if crossed:
        raise Skipped(f"a `:` here would renumber {crossed} anonymous reference(s)")
    op = m.group("op")
    inverse = INVERSE[op.lower()]
    if op.isupper():
        inverse = inverse.upper()
    indent, label = m.group("indent"), m.group("label") or ""
    pad = " " * len(label)
    return [f"{indent}{label}{inverse} :+\n",
            f"{indent}{pad}jmp {target}{m.group('trailer')}\n",
            ":\n"]                          # labels live at column 0, as ca65 expects


def parse_errors(text: str) -> dict[Path, list[int]]:
    """Every Range error in a build log, as 0-based line numbers per file."""
    out: dict[Path, list[int]] = {}
    for raw in text.splitlines():
        m = RANGE_ERROR.match(raw.strip())
        if m:
            out.setdefault(Path(m.group("file")), []).append(int(m.group("line")) - 1)
    return out


def fix_file(path: Path, branches: list[int], dry_run: bool) -> tuple[list[str], int]:
    """Rewrite `path`'s out-of-range branches; return the report and how many
    were left alone.

    Descending line order is not cosmetic: each fix adds two lines, so fixing
    upward first would invalidate every line number below it.
    """
    # newline="" on both ends keeps the file's own line endings inside the
    # strings instead of translating them to "\n". Without it a CRLF source
    # reads as LF, every branch matches, and the write-back reformats every
    # line in the file — a whole-file diff for a three-line fix. `rewrite`
    # refuses those lines, and this is the only place it can see them.
    with path.open(newline="", encoding="utf-8") as fh:
        lines = fh.read().splitlines(keepends=True)
    report, left = [], 0
    for branch in sorted(set(branches), reverse=True):
        if branch >= len(lines):
            report.append(f"{path}:{branch + 1}  SKIPPED  past the end of the file")
            left += 1
            continue
        try:
            new = rewrite(lines, branch)
        except Skipped as e:
            report.append(f"{path}:{branch + 1}  SKIPPED  "
                          f"{lines[branch].strip()}  ({e})")
            left += 1
            continue
        report.append(f"{path}:{branch + 1}  {lines[branch].strip()}  ->  "
                      f"{' / '.join(s.strip() for s in new)}")
        lines[branch:branch + 1] = new
    if not dry_run and left < len(set(branches)):
        with path.open("w", newline="", encoding="utf-8") as fh:
            fh.write("".join(lines))
    return report, left


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Invert out-of-range ca65 branches over a jmp trampoline. "
                    "Reads a failed `c64 build`'s output on stdin.")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="report the rewrites without writing any file")
    args = ap.parse_args(argv)

    errors = parse_errors(sys.stdin.read())
    if not errors:
        print("no ca65 Range errors on stdin — nothing to do")
        return 0
    fixed = left = 0
    for path, branches in errors.items():
        if not path.exists():
            print(f"{path}: no such file (run this from the build's directory)")
            left += len(branches)
            continue
        report, skipped = fix_file(path, branches, args.dry_run)
        print("\n".join(report))
        fixed += len(report) - skipped
        left += skipped
    verb = "would fix" if args.dry_run else "fixed"
    print(f"\n{verb} {fixed}, left {left} for you")
    return 1 if left else 0


if __name__ == "__main__":
    raise SystemExit(main())
