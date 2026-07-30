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
    LATER_BASIC,
    MAX_LINE_NUMBER,
    MAX_LINE_WORD,
    RESERVED_VARS,
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
    # Always an int: _parse is the only place a Line is built, and it skips
    # any source line with no leading digits (E10, LintIssue.line=None) before
    # reaching the constructor. So every Line in Program.lines is numbered,
    # and the reachability/subroutine graphs can key on `number` directly.
    number: int
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
            # Warning, not error: verified on x64sc 2026-07-24 — petcat
            # silently INVENTS a number (`print "b"` between 10 and 30 became
            # line 12) and the program runs. Wrong program, not a crash.
            issues.append(LintIssue(None, "warning", "E10",
                                    f"missing line number (file line {n}); "
                                    "petcat will invent one"))
            continue
        number = int(digits)
        rest = body[len(digits):]
        toks = tokenize_line(rest)
        merged = merge_tokens(toks)
        line = Line(number, rest, raw, n, merged, _split_statements(merged),
                    text_bytes(rest, toks))     # sizes come from UNMERGED tokens
        sizes.append(line.size)
        # Two different failures, verified on x64sc 2026-07-24: a number above
        # 63999 still LOADs and RUNs (only the screen editor refuses it), but
        # one above 65535 does not fit the 2-byte field and petcat wraps it —
        # `70000 print "hi"` came back as line 4464, a different program.
        if number > MAX_LINE_WORD:
            issues.append(LintIssue(number, "error", "E11",
                                    f"line number {number} exceeds {MAX_LINE_WORD} "
                                    f"and wraps to {number % (MAX_LINE_WORD + 1)}"))
        elif number > MAX_LINE_NUMBER:
            issues.append(LintIssue(number, "warning", "E11",
                                    f"line number {number} is above "
                                    f"{MAX_LINE_NUMBER}; it runs, but the C64 "
                                    "screen editor cannot re-enter the line"))
        if number in prog.by_number:
            # Warning: both copies load and RUN in order; the cost is that
            # goto/gosub can only ever reach the first (verified on x64sc).
            issues.append(LintIssue(number, "warning", "E12",
                                    f"duplicate line number {number}; "
                                    "goto/gosub can only reach the first"))
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
        # WARNING, not error: verified on x64sc 2026-07-24 — a taken `IF ...
        # THEN` with nothing after it does not fault, it falls through to the
        # next line. Always an unfinished edit, never a runtime failure.
        return [LintIssue(line.number, "warning", "E122",
                          "then with no statement or line number "
                          "(falls through — probably unfinished)")]
    return []


def _check_shape(prog: Program) -> list[LintIssue]:
    out = []
    for line in prog.lines:
        out.extend(_check_parens(line))
        out.extend(_check_strings(line))
        for stmt in line.statements:
            out.extend(_check_statement(line, stmt))
    return out


_JUMPS = ("goto", "gosub", "run", "then")
_TERMINATORS = ("end", "stop", "return")


def _targets(stmt: list[Token]) -> list[tuple[Token, int]]:
    """(keyword token, line number) for every literal jump in the statement —
    `goto n`, `gosub n`, `run n`, `then n`, and every entry of an ON list."""
    out = []
    for k, t in enumerate(stmt):
        if t.kind != "KEYWORD" or t.text not in _JUMPS:
            continue
        j = k + 1
        while j < len(stmt) and stmt[j].kind == "NUMBER":
            out.append((t, int(float(stmt[j].text))))
            j += 1
            if j < len(stmt) and stmt[j].kind == "OP" and stmt[j].text == ",":
                j += 1
            else:
                break
    return out


def _check_flow(prog: Program) -> list[LintIssue]:
    out = []
    for line in prog.lines:
        for stmt in line.statements:
            for tok, n in _targets(stmt):
                if n not in prog.by_number:
                    out.append(LintIssue(line.number, "error", "E20",
                                         f"{tok.text} target {n} does not exist"))
            for k, t in enumerate(stmt):
                if t.kind == "KEYWORD" and t.text in ("goto", "gosub") \
                        and (k + 1 >= len(stmt) or stmt[k + 1].kind != "NUMBER"):
                    out.append(LintIssue(line.number, "error", "E21",
                                         f"{t.text} without target"))
            if any(t.kind == "KEYWORD" and t.text == "on" for t in stmt):
                out.extend(_check_on(line, stmt))
    return out


def _check_on(line: Line, stmt: list[Token]) -> list[LintIssue]:
    k = next(i for i, t in enumerate(stmt) if t.kind == "KEYWORD" and t.text == "on")
    tail = stmt[k + 1:]
    if not any(t.kind == "KEYWORD" and t.text in ("goto", "gosub") for t in tail):
        return [LintIssue(line.number, "error", "E22", "on without goto/gosub")]
    # Constant selector: `on <literal> goto ...` (a leading '-' is its own OP).
    sel = None
    if len(tail) > 1 and tail[0].kind == "OP" and tail[0].text == "-" \
            and tail[1].kind == "NUMBER":
        sel = -int(float(tail[1].text))
    elif tail and tail[0].kind == "NUMBER":
        sel = int(float(tail[0].text))
    if sel is None:
        return []
    if sel < 0:
        return [LintIssue(line.number, "error", "E23",
                          f"on selector {sel} is negative (?illegal quantity error)")]
    count = len(_targets(stmt))
    if sel > count:
        return [LintIssue(line.number, "warning", "W50",
                          f"on selector {sel} exceeds {count} targets")]
    return []


def _check_loops(prog: Program) -> list[LintIssue]:
    """Program-order heuristics. Only NEXT-with-nothing-open is impossible;
    flow can legitimately leave a loop or a subroutine, so the rest warn."""
    out, stack = [], []                        # stack of (var, line number)
    has_gosub = any(t.kind == "KEYWORD" and t.text == "gosub"
                    for ln in prog.lines for t in ln.tokens)
    for line in prog.lines:
        for stmt in line.statements:
            head = _head(stmt)
            if head == "for":
                var = next((t.text for t in stmt[1:] if t.kind == "IDENT"), "")
                stack.append((var, line.number))
            elif head == "next":
                names = [t.text for t in stmt[1:] if t.kind == "IDENT"] or [""]
                for name in names:              # `next k,j` closes two loops
                    if not stack:
                        out.append(LintIssue(line.number, "error", "E130",
                                             "next without for"))
                        continue
                    var, at = stack.pop()
                    if name and name != var:
                        out.append(LintIssue(line.number, "warning", "W130",
                                             f"next {name} does not match for "
                                             f"{var} (line {at})"))
            elif head == "return" and not has_gosub:
                out.append(LintIssue(line.number, "warning", "W140",
                                     "return with no gosub in program"))
    for var, at in stack:
        out.append(LintIssue(at, "warning", "W131",
                             f"for {var} (line {at}) has no next"))
    out.extend(_check_subroutines(prog))
    return out


def _check_subroutines(prog: Program) -> list[LintIssue]:
    """W141: a GOSUB target with no RETURN at or after it anywhere."""
    out = []
    targets = {n for line in prog.lines for stmt in line.statements
               for tok, n in _targets(stmt) if tok.text == "gosub"}
    for n in sorted(targets & set(prog.by_number)):
        later = [ln for ln in prog.lines if ln.number >= n]
        if not any(t.kind == "KEYWORD" and t.text == "return"
                   for ln in later for t in ln.tokens):
            out.append(LintIssue(n, "warning", "W141",
                                 f"subroutine at {n} has no return"))
    return out


def _check_reach(prog: Program) -> list[LintIssue]:
    """W70. Edges: fallthrough (unless the line ends in an UNCONDITIONAL
    goto/end/stop/return), plus every literal jump target. GOSUB also falls
    through — execution comes back."""
    if not prog.lines:
        return []
    order = [ln.number for ln in prog.lines]
    edges: dict[int, set[int]] = {n: set() for n in order}
    for idx, line in enumerate(prog.lines):
        n = line.number
        last = line.statements[-1] if line.statements else []
        head = _head(last) if last else None
        # An IF anywhere on the line makes everything after it conditional,
        # so `130 if k$="q" then print "bye" : end` still falls through.
        conditional = any(_head(s) == "if" for s in line.statements)
        terminal = not conditional and (head == "goto" or head in _TERMINATORS)
        if not terminal and idx + 1 < len(order):
            edges[n].add(order[idx + 1])
        for stmt in line.statements:
            for _tok, target in _targets(stmt):
                if target in edges:
                    edges[n].add(target)
    seen, stack = set(), [order[0]]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(edges.get(n, ()))
    # DATA/REM-only lines are not code — a DATA block after END is idiomatic.
    inert = {ln.number for ln in prog.lines
             if all(_head(s) in ("data", "rem") for s in ln.statements)}
    return [LintIssue(n, "warning", "W70", "unreachable line")
            for n in order if n not in seen and n not in inert]


_FLOAT_MAX = 1.70141183e38
_RANGES = {"poke": ((0, 65535), (0, 255)), "wait": ((0, 65535), (0, 255)),
           "sys": ((0, 65535),), "peek": ((0, 65535),), "chr$": ((0, 255),),
           "tab(": ((0, 255),), "spc(": ((0, 255),)}
_CALLS = ("peek", "chr$", "tab(", "spc(")


def _literal(toks: list[Token]) -> float | None:
    """A signed numeric literal, or None if this is anything else."""
    if len(toks) == 2 and toks[0].kind == "OP" and toks[0].text == "-" \
            and toks[1].kind == "NUMBER":
        return -float(toks[1].text)
    if len(toks) == 1 and toks[0].kind == "NUMBER":
        return float(toks[0].text)
    return None


def _args(stmt: list[Token], k: int) -> list[list[Token]]:
    """Comma-separated argument groups after stmt[k], stopping at the end of
    the call (matching ')' for a function, end of statement for a command).

    Deliberately stops at the first paren closing back to depth 0, so
    `poke 1024+len(a$),32` yields a malformed group rather than the 32: it
    under-reports, never false-reports."""
    i, depth, groups = k + 1, 0, [[]]
    if stmt[k].text in _CALLS:
        if stmt[k].kind == "KEYWORD" and stmt[k].text in ("tab(", "spc("):
            depth = 1
        elif i < len(stmt) and stmt[i].kind == "OP" and stmt[i].text == "(":
            depth, i = 1, i + 1
        else:
            return []
    while i < len(stmt):
        t = stmt[i]
        if t.kind == "OP" and t.text in ("(", ")"):
            depth += 1 if t.text == "(" else -1
            if depth == 0:
                break
            groups[-1].append(t)
        elif t.kind == "OP" and t.text == "," and depth <= 1:
            groups.append([])
        else:
            groups[-1].append(t)
        i += 1
    return [g for g in groups if g]


def _check_ranges(line: Line, stmt: list[Token]) -> list[LintIssue]:
    out = []
    for k, t in enumerate(stmt):
        if t.kind != "KEYWORD" or t.text not in _RANGES:
            continue
        for arg, (lo, hi) in zip(_args(stmt, k), _RANGES[t.text], strict=False):
            v = _literal(arg)
            if v is not None and not lo <= v <= hi:
                shown = int(v) if v == int(v) else v
                out.append(LintIssue(line.number, "error", "E150",
                                     f"?illegal quantity: {t.text} {shown} "
                                     f"(valid {lo}-{hi})"))
    return out


def _var_type(t: Token) -> str | None:
    """'str' | 'num' for a single operand whose type is known from shape."""
    if t.kind == "STRING":
        return "str"
    if t.kind == "NUMBER":
        return "num"
    if t.kind == "IDENT":
        return "str" if t.text.endswith("$") else "num"
    return None


_RELOPS = ("<", ">", "=", "<=", ">=", "<>")


def _check_comparison(line: Line, stmt: list[Token]) -> list[LintIssue]:
    """E154 for `if <operand> <relop> <operand>` — both sides single tokens."""
    if _head(stmt) != "if" or len(stmt) < 4:
        return []
    a, op, b = stmt[1], stmt[2], stmt[3]
    if op.kind != "OP" or op.text not in _RELOPS:
        return []
    at, bt = _var_type(a), _var_type(b)
    if at and bt and at != bt:
        return [LintIssue(line.number, "error", "E154",
                          f"?type mismatch: {a.text} vs {b.text}")]
    return []


def _check_assignment(line: Line, stmt: list[Token]) -> list[LintIssue]:
    out = []
    head = _head(stmt)
    depths = _depths(stmt)
    eq = next((i for i, t in enumerate(stmt)
               if depths[i] == 0 and t.kind == "OP" and t.text == "="), None)
    if head == "for":
        var = next((t for t in stmt[1:] if t.kind == "IDENT"), None)
        if var is not None and var.text[-1] in "$%":
            out.append(LintIssue(line.number, "error", "E153",
                                 f"for variable {var.text} must be a plain "
                                 "numeric variable"))
    if eq is not None and head in (None, "let"):
        first = 1 if head == "let" else 0
        target = stmt[first]
        if target.kind == "IDENT" and target.text in ("ti", "st"):
            out.append(LintIssue(line.number, "error", "E152",
                                 f"cannot assign to reserved variable {target.text}"))
        rhs = stmt[eq + 1:]
        if eq == first + 1 and len(rhs) == 1:      # both sides a single token
            lt, rt = _var_type(target), _var_type(rhs[0])
            if lt and rt and lt != rt:
                out.append(LintIssue(line.number, "error", "E154",
                                     f"?type mismatch: {target.text} vs {rhs[0].text}"))
    out.extend(_check_comparison(line, stmt))
    return out


def _check_values(prog: Program) -> list[LintIssue]:
    out = []
    for line in prog.lines:
        for t in line.tokens:
            if t.kind == "NUMBER" and float(t.text) > _FLOAT_MAX:
                out.append(LintIssue(line.number, "error", "E151",
                                     f"?overflow: literal {t.text} exceeds "
                                     "C64 float range"))
        for stmt in line.statements:
            out.extend(_check_ranges(line, stmt))
            out.extend(_check_assignment(line, stmt))
    return out


def _check_defs(prog: Program) -> list[LintIssue]:
    out, defined, dimmed, used = [], set(), {}, []
    has_data = any(t.kind == "KEYWORD" and t.text == "data"
                   for ln in prog.lines for t in ln.tokens)
    for line in prog.lines:
        toks = line.tokens
        for k, t in enumerate(toks):
            if t.kind == "KEYWORD" and t.text == "fn" and k + 1 < len(toks) \
                    and toks[k + 1].kind == "IDENT":
                name = toks[k + 1].text[:2]
                if k and toks[k - 1].kind == "KEYWORD" and toks[k - 1].text == "def":
                    defined.add(name)
                else:
                    used.append((line.number, toks[k + 1].text, name))
            if t.kind == "KEYWORD" and t.text == "read" and not has_data:
                out.append(LintIssue(line.number, "warning", "W80",
                                     "read with no data (?out of data error "
                                     "when executed)"))
        for stmt in line.statements:
            if _head(stmt) != "dim":
                continue
            for k, t in enumerate(stmt):
                if k and t.kind == "IDENT" and k + 1 < len(stmt) \
                        and stmt[k + 1].text == "(":
                    if t.text in dimmed:
                        out.append(LintIssue(line.number, "warning", "W81",
                                             f"array {t.text} dimensioned twice "
                                             "(?redim'd array error if both run)"))
                    dimmed[t.text] = line.number
    for at, full, name in used:
        if name not in defined:
            out.append(LintIssue(at, "error", "E140",
                                 f"fn {full} used but never defined"))
    out.extend(_check_subscripts(prog, dimmed))
    return out


def _check_subscripts(prog: Program, dimmed: dict[str, int]) -> list[LintIssue]:
    """W82: undimensioned arrays only go up to index 10."""
    out = []
    for line in prog.lines:
        toks = line.tokens
        for k, t in enumerate(toks):
            if t.kind != "IDENT" or t.text in dimmed:
                continue
            if k + 3 < len(toks) and toks[k + 1].text == "(" \
                    and toks[k + 2].kind == "NUMBER" and toks[k + 3].text == ")" \
                    and float(toks[k + 2].text) > 10:
                out.append(LintIssue(line.number, "warning", "W82",
                                     f"{t.text}({toks[k + 2].text}) needs dim — "
                                     "undimensioned arrays stop at 10"))
    return out


def _literal_dims(prog: Program) -> dict[str, tuple[int, int]]:
    """name -> (bound, line) for every array whose size is a single integer
    literal. A name dimensioned twice (?redim'd array, W81) or with anything
    computed or multi-dimensional is dropped: its bound is not provable."""
    dims: dict[str, tuple[int, int] | None] = {}
    for line in prog.lines:
        for stmt in line.statements:
            if _head(stmt) != "dim":
                continue
            for k, t in enumerate(stmt):
                if not k or t.kind != "IDENT" or k + 1 >= len(stmt) \
                        or stmt[k + 1].text != "(":
                    continue
                size = None
                if k + 3 < len(stmt) and stmt[k + 2].kind == "NUMBER" \
                        and stmt[k + 3].text == ")":
                    size = float(stmt[k + 2].text)
                dims[t.text] = (
                    (int(size), line.number)
                    if size is not None and size == int(size)
                    and t.text not in dims else None)
    return {n: d for n, d in dims.items() if d is not None}


def _for_bounds(stmt: list[Token]) -> tuple[str, int | None]:
    """(loop variable, provable top value) for a FOR statement. The top is
    None unless both bounds are integer literals, low <= high, and there is no
    STEP — a stepped or computed loop is not something this rule models."""
    var = next((t.text for t in stmt[1:] if t.kind == "IDENT"), "")
    if any(t.kind == "KEYWORD" and t.text == "step" for t in stmt):
        return var, None
    to = next((i for i, t in enumerate(stmt)
               if t.kind == "KEYWORD" and t.text == "to"), None)
    eq = next((i for i, t in enumerate(stmt)
               if t.kind == "OP" and t.text == "="), None)
    if to is None or eq is None or eq > to:
        return var, None
    lo, hi = _literal(stmt[eq + 1:to]), _literal(stmt[to + 1:])
    if lo is None or hi is None or lo != int(lo) or hi != int(hi) or lo > hi:
        return var, None
    return var, int(hi)


def _check_dim_subscripts(prog: Program) -> list[LintIssue]:
    """E131: a statically provable ?BAD SUBSCRIPT. All three pieces must be
    literal — `dim v(N)`, a `for i=<lit> to <lit>`, and a `v(i)` whose
    subscript is *exactly* the loop variable, between that FOR and its NEXT.
    DIM is 0-based, so `dim v(4)` allows v(0)..v(4) and only `to 5` overflows.
    Anything less certain than that stays silent: this rule reports crashes
    that are already proven, never ones that are merely likely."""
    dims = _literal_dims(prog)
    if not dims:
        return []
    out: list[LintIssue] = []
    # (loop variable, provable top, issues found in this body). A loop's
    # findings are only kept when a NEXT closes it — an unterminated FOR
    # (W131) has no bounded body, so nothing inside it is provable.
    stack: list[tuple[str, int | None, list[LintIssue]]] = []
    for line in prog.lines:
        for stmt in line.statements:
            head = _head(stmt)
            if head == "for":
                stack.append((*_for_bounds(stmt), []))
                continue
            if head == "next":
                for _name in [t.text for t in stmt[1:] if t.kind == "IDENT"] or [""]:
                    if stack:                   # `next k,j` closes two loops
                        out.extend(stack.pop()[2])
                continue
            if head == "dim":
                continue
            for k, t in enumerate(stmt):
                if t.kind != "IDENT" or t.text not in dims or k + 3 >= len(stmt):
                    continue
                if stmt[k + 1].text != "(" or stmt[k + 2].kind != "IDENT" \
                        or stmt[k + 3].text != ")":
                    continue                    # v(i+1), v(2), v(i,j): not us
                bound, at = dims[t.text]
                for var, top, found in reversed(stack):
                    if var != stmt[k + 2].text:
                        continue
                    if top is not None and top > bound:
                        found.append(LintIssue(
                            line.number, "error", "E131",
                            f"?bad subscript: {t.text}({top}) at line "
                            f"{line.number} exceeds dim {t.text}({bound}) "
                            f"(line {at})"))
                    break                       # innermost loop owns the name
    return out


_W90_CONSEQUENCE = {"new": "wipes the running program",
                    "list": "stops the program", "cont": "cannot continue"}


def _check_vocab(prog: Program) -> list[LintIssue]:
    out = []
    for line in prog.lines:
        for t in line.tokens:
            if t.kind == "KEYWORD" and t.text in _W90_CONSEQUENCE:
                out.append(LintIssue(line.number, "warning", "W90",
                                     f"{t.text} inside a program "
                                     f"{_W90_CONSEQUENCE[t.text]}"))
            if t.kind == "IDENT" and t.text in LATER_BASIC:
                out.append(LintIssue(line.number, "warning", "W60",
                                     f"'{t.text}' is not BASIC V2; it will not "
                                     "run on a C64"))
    out.extend(_check_aliases(prog))
    return out


def _check_aliases(prog: Program) -> list[LintIssue]:
    """W61: only the first two characters are significant on a C64. Scalars,
    `$`, `%` and arrays live in separate namespaces, so only collide in kind."""
    seen: dict[tuple[str, str], str] = {}
    out = []
    for line in prog.lines:
        toks = line.tokens
        for k, t in enumerate(toks):
            if t.kind != "IDENT" or t.text in RESERVED_VARS:
                continue
            base = t.text.rstrip("$%")
            if len(base) < 3:
                continue                          # already 2 significant chars
            kind = ("array" if k + 1 < len(toks) and toks[k + 1].text == "("
                    else "scalar")
            suffix = t.text[-1] if t.text[-1] in "$%" else ""
            key = (base[:2] + suffix, kind)
            other = seen.setdefault(key, t.text)
            if other != t.text:
                out.append(LintIssue(line.number, "warning", "W61",
                                     f"variables {other} and {t.text} are the "
                                     "same variable on a C64 (only 2 chars "
                                     "significant)"))
                seen[key] = t.text                # report each pair once
    return out


def _drop_redundant(issues: list[LintIssue]) -> list[LintIssue]:
    """A name that already tripped a fusion rule is reported; don't also
    report it as an alias (spec §5, W61)."""
    fused = {i.line for i in issues if i.rule in ("E110", "E111")}
    return [i for i in issues if not (i.rule == "W61" and i.line in fused)]


_CHECKS = (_check_line_length, _check_size, _check_shape, _check_flow,
           _check_loops, _check_reach, _check_values, _check_defs,
           _check_dim_subscripts, _check_vocab)


def lint_source(text: str) -> list[LintIssue]:
    """Lint BASIC V2 source text. Pure; issues in (line, rule) order."""
    prog, issues = _parse(text)
    for check in _CHECKS:
        issues.extend(check(prog))
    return sorted(_drop_redundant(issues),
                  key=lambda i: (-1 if i.line is None else i.line, i.rule))


def tokenized_bytes(text: str) -> int:
    """Exact loaded size of the program, excluding the 2-byte load address."""
    return _parse(text)[0].bytes
