"""Static lint for Commodore BASIC V2 source (`c64 basic check`).

Every check runs over the token model in `basic_tokens`, which crunches
exactly as the C64 ROM does — so crunched code (`fori=1to10`) parses without
false positives and keyword fusion (`total=5` -> `TO TAL = 5`) falls out of
the statement-shape rules instead of needing special cases.

Contract: an `error` means the program cannot run correctly on a stock C64.
A program that RUNs clean must produce zero errors — when a rule and a
working program disagree, the rule is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .basic_tokens import (
    BASIC_FREE_BYTES,
    MAX_LINE_NUMBER,
    Token,
    merge_tokens,
    petscii_len,
    program_bytes,
    text_bytes,
    tokenize_line,
)


@dataclass(frozen=True)
class LintIssue:
    line: int | None        # BASIC line number (None = file-level)
    severity: str           # "error" | "warning"
    rule: str               # stable ID, e.g. "E20"
    message: str


@dataclass
class Line:
    number: int | None
    text: str                       # source after the line number
    raw: str                        # the whole source line, right-stripped
    file_line: int                  # 1-based position in the file
    tokens: list[Token]             # merged (analysis) tokens
    statements: list[list[Token]]
    size: int                       # tokenized text bytes


@dataclass
class Program:
    lines: list[Line] = field(default_factory=list)
    by_number: dict[int, Line] = field(default_factory=dict)
    bytes: int = 0


def _split_statements(toks: list[Token]) -> list[list[Token]]:
    out: list[list[Token]] = [[]]
    for t in toks:
        if t.kind == "OP" and t.text == ":":
            out.append([])
        else:
            out[-1].append(t)
    return [s for s in out if s]


def _parse(text: str) -> tuple[Program, list[LintIssue]]:
    prog, issues, sizes, prev = Program(), [], [], None
    for n, raw_line in enumerate(text.splitlines(), start=1):
        raw = raw_line.rstrip()
        if not raw.strip():
            continue
        body = raw.lstrip()
        digits = ""
        while body[len(digits):len(digits) + 1].isdigit():
            digits += body[len(digits)]
        if not digits:
            issues.append(LintIssue(None, "error", "E10",
                                    f"missing line number (file line {n})"))
            continue
        number = int(digits)
        rest = body[len(digits):]
        toks = tokenize_line(rest)
        merged = merge_tokens(toks)
        line = Line(number, rest, raw, n, merged, _split_statements(merged),
                    text_bytes(rest, toks))     # sizes come from UNMERGED tokens
        sizes.append(line.size)
        if number > MAX_LINE_NUMBER:
            issues.append(LintIssue(number, "error", "E11",
                                    f"line number {number} out of range "
                                    f"(0-{MAX_LINE_NUMBER})"))
        if number in prog.by_number:
            issues.append(LintIssue(number, "error", "E12",
                                    f"duplicate line number {number}"))
        else:
            prog.by_number[number] = line
        # Strictly-decreasing only: an equal number is a duplicate, already E12.
        if prev is not None and number < prev:
            issues.append(LintIssue(number, "warning", "W20",
                                    f"line {number} out of order (after {prev}); "
                                    "petcat keeps file order"))
        prev = number
        prog.lines.append(line)
    prog.bytes = program_bytes(sizes)
    return prog, issues


def _check_line_length(prog: Program) -> list[LintIssue]:
    """W30: >80 characters as typed on a C64 — petcat tokenizes it, but the
    screen editor cannot re-enter it and >255 tokenized bytes break.

    Counts what the user TYPES, so every `{escape}` is one character —
    including inside REM, where petcat instead stores the literal `[NAME]`
    text. Byte sizing and this length check answer different questions."""
    out = []
    for line in prog.lines:
        length = petscii_len(line.raw.strip())
        if length > 80:
            out.append(LintIssue(line.number, "warning", "W30",
                                 f"logical line is {length} chars "
                                 "(max 80 on the C64 screen editor)"))
    return out


def _check_size(prog: Program) -> list[LintIssue]:
    if prog.bytes > BASIC_FREE_BYTES:
        return [LintIssue(None, "error", "E160",
                          f"program tokenizes to {prog.bytes} bytes; "
                          f"C64 BASIC has {BASIC_FREE_BYTES} free")]
    return []


_CHECKS = (_check_line_length, _check_size)


def lint_source(text: str) -> list[LintIssue]:
    """Lint BASIC V2 source text. Pure; issues in (line, rule) order."""
    prog, issues = _parse(text)
    for check in _CHECKS:
        issues.extend(check(prog))
    return sorted(issues, key=lambda i: (-1 if i.line is None else i.line, i.rule))


def tokenized_bytes(text: str) -> int:
    """Exact loaded size of the program, excluding the 2-byte load address."""
    return _parse(text)[0].bytes
