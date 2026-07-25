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


# Keywords that can never begin a statement. Each is legal in exactly one
# grammatical context; anywhere else it is a misplacement — and when it is
# glued to identifier characters, it is keyword fusion (`total=5` -> TO TAL).
_CLAUSE_KEYWORDS = ("to", "then", "step", "and", "or", "not", "fn", "tab(", "spc(")
_VAR_LIST_HEADS = ("input", "input#", "read", "get", "next", "dim")
_VALUE_ENDERS = ("IDENT", "NUMBER", "STRING", "ESCAPE")
_OPENERS = ("(", "tab(", "spc(")


def _head(stmt: list[Token]) -> str | None:
    return stmt[0].text if stmt[0].kind == "KEYWORD" else None


def _ends_value(t: Token | None) -> bool:
    if t is None:
        return False
    return t.kind in _VALUE_ENDERS or (t.kind == "OP" and t.text == ")")


def _depths(stmt: list[Token]) -> list[int]:
    """Paren depth BEFORE each token. `tab(`/`spc(` open a paren too."""
    out, depth = [], 0
    for t in stmt:
        out.append(depth)
        if t.text in _OPENERS and t.kind in ("OP", "KEYWORD"):
            depth += 1
        elif t.kind == "OP" and t.text == ")":
            depth -= 1
    return out


def _clause_ok(stmt: list[Token], k: int) -> bool:
    """Does V2's grammar allow this clause keyword here?"""
    if k == 0:
        return False                                  # never starts a statement
    kw, head, prev = stmt[k].text, _head(stmt), stmt[k - 1]
    before = stmt[1:k]
    if kw == "to":
        return head == "for" and any(t.kind == "OP" and t.text == "=" for t in before)
    if kw == "step":
        return head == "for" and any(t.kind == "KEYWORD" and t.text == "to"
                                     for t in before)
    if kw == "then":
        return head == "if"
    if kw in ("and", "or"):
        return _ends_value(prev)
    if kw == "not":
        return not _ends_value(prev)
    if kw in ("tab(", "spc("):
        return head in ("print", "print#", "cmd")
    return True                                       # fn: legal anywhere but 0


def _run_around(line: Line, tok: Token) -> str:
    """The source identifier run the keyword is glued into, e.g. 'total'."""
    text, start, end = line.text, tok.col, tok.col + len(tok.raw)
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "$%"):
        start -= 1
    while end < len(text) and (text[end].isalnum() or text[end] in "$%"):
        end += 1
    return text[start:end]


def _fusion_message(line: Line, tok: Token) -> str:
    run = _run_around(line, tok)
    split = " ".join(t.text.upper() for t in tokenize_line(run))
    return (f"'{run}' tokenizes as {split} on a C64 — rename the variable "
            f"(embedded keyword '{tok.text}')")


def _misplaced(line: Line, tok: Token, rule: str) -> LintIssue:
    """Fusion evidence decides severity: glued means it cannot run."""
    if tok.fused:
        return LintIssue(line.number, "error", rule, _fusion_message(line, tok))
    return LintIssue(line.number, "warning", "W110",
                     f"statement cannot start with '{tok.text}'")


def _variable_positions(stmt: list[Token], depths: list[int]) -> list[int]:
    """Indexes where V2 requires a variable name, so any keyword there is a
    fusion bug (`input total`, `score=1`, `paint 1,2`)."""
    head = _head(stmt)
    eq = next((i for i, t in enumerate(stmt)
               if depths[i] == 0 and t.kind == "OP" and t.text == "="), None)
    if head is None or head == "let":                      # assignment
        start = 1 if head == "let" else 0
        stop = eq if eq is not None else len(stmt)
        if eq is None and stop - start == 1 and stmt[start].kind == "IDENT":
            return []                                      # a lone `10 x`, not fusion
        return [i for i in range(start, stop) if depths[i] == 0]
    if head in _VAR_LIST_HEADS:
        return [i for i in range(1, len(stmt)) if depths[i] == 0]
    if head == "for":
        stop = eq if eq is not None else len(stmt)
        return [i for i in range(1, stop) if depths[i] == 0]
    return []


def _check_statement(line: Line, stmt: list[Token]) -> list[LintIssue]:
    out, flagged = [], set()
    depths = _depths(stmt)
    # E111 first: keywords where the grammar demands a variable name.
    for k in _variable_positions(stmt, depths):
        if stmt[k].kind != "KEYWORD":
            continue
        flagged.add(k)
        out.append(_misplaced(line, stmt[k], "E111"))
    # E110: clause keywords the grammar forbids at this position.
    for k, tok in enumerate(stmt):
        if k in flagged or tok.kind != "KEYWORD" or tok.text not in _CLAUSE_KEYWORDS:
            continue
        if not _clause_ok(stmt, k):
            out.append(_misplaced(line, tok, "E110"))
    out.extend(_check_if(line, stmt))
    return out


def _check_parens(line: Line) -> list[LintIssue]:
    depth = 0
    for t in line.tokens:
        if t.text in _OPENERS and t.kind in ("OP", "KEYWORD"):
            depth += 1
        elif t.kind == "OP" and t.text == ")":
            depth -= 1
    if depth != 0:
        return [LintIssue(line.number, "error", "E121", "unbalanced parentheses")]
    return []


def _check_strings(line: Line) -> list[LintIssue]:
    for t in line.tokens:
        if t.kind == "STRING" and not (len(t.raw) > 1 and t.raw.endswith('"')):
            return [LintIssue(line.number, "warning", "W40",
                              "unterminated string (legal on C64, but check "
                              "it's intended)")]
    return []


def _check_if(line: Line, stmt: list[Token]) -> list[LintIssue]:
    """E120/E122. `if x goto 100` is legal V2 — GOTO may replace THEN."""
    if _head(stmt) != "if":
        return []
    kws = [t.text for t in stmt if t.kind == "KEYWORD"]
    if "then" not in kws and "goto" not in kws:
        return [LintIssue(line.number, "error", "E120", "if without then or goto")]
    branch = "then" if "then" in kws else "goto"
    k = next(i for i, t in enumerate(stmt) if t.kind == "KEYWORD" and t.text == branch)
    if k == len(stmt) - 1:
        return [LintIssue(line.number, "error", "E122",
                          "then with no statement or line number")]
    return []


def _check_shape(prog: Program) -> list[LintIssue]:
    out = []
    for line in prog.lines:
        out.extend(_check_parens(line))
        out.extend(_check_strings(line))
        for stmt in line.statements:
            out.extend(_check_statement(line, stmt))
    return out


_CHECKS = (_check_line_length, _check_size, _check_shape)


def lint_source(text: str) -> list[LintIssue]:
    """Lint BASIC V2 source text. Pure; issues in (line, rule) order."""
    prog, issues = _parse(text)
    for check in _CHECKS:
        issues.extend(check(prog))
    return sorted(issues, key=lambda i: (-1 if i.line is None else i.line, i.rule))


def tokenized_bytes(text: str) -> int:
    """Exact loaded size of the program, excluding the 2-byte load address."""
    return _parse(text)[0].bytes
