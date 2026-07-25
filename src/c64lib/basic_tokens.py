"""Cruncher-faithful tokenizer for Commodore BASIC V2 source text.

Models the C64 BASIC ROM's crunch pass: at every character position the
longest keyword in the V2 table wins — *even in the middle of an identifier
run*, which is why `total=5` really stores as `TO TAL = 5` and fails at RUN.
Strings, REM comments and DATA items are opaque, exactly as the ROM treats
them. Token sizes are the real tokenized byte counts (verified against
petcat), so a program's loaded size is computable without running petcat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BASIC_FREE_BYTES = 38911        # free BASIC RAM on a stock C64
MAX_LINE_NUMBER = 63999     # highest the screen editor will accept
MAX_LINE_WORD = 65535       # highest the 2-byte line-number field can hold

_STATEMENTS = (
    "end for next data input# input dim read let goto run if restore gosub return "
    "rem stop on wait load save verify def poke print# print cont list clr cmd sys "
    "open close get new"
).split()
_CLAUSES = "tab( to fn spc( then not step and or go".split()
_FUNCTIONS = (
    "sgn int abs usr fre pos sqr rnd log exp cos sin tan atn peek len str$ val asc "
    "chr$ left$ right$ mid$"
).split()

# Longest first: `gosub` must beat `go`, `print#` must beat `print`.
KEYWORDS: tuple[str, ...] = tuple(
    sorted(_STATEMENTS + _CLAUSES + _FUNCTIONS, key=len, reverse=True))

# Not keywords — the ROM's three reserved variables. Never fusion-matched
# (no keyword is a prefix of them), but rules treat them specially.
RESERVED_VARS = ("ti$", "ti", "st")

# BASIC 3.5/7.0 words. On a C64 these are plain identifiers (often fused),
# so they tokenize but never run — see W60.
LATER_BASIC = frozenset(
    "else instr do loop until while sound graphic joy volume circle box draw paint "
    "scnclr color auto renumber key trap resume delete pudef sprite movspr collision "
    "char".split())

_OPS = ":;,()=<>+-*/^"
_ESCAPE_RE = re.compile(r"\{[^{}]*\}")
_IDENT_CH = re.compile(r"[0-9a-z]", re.I)


@dataclass(frozen=True)
class Token:
    kind: str        # KEYWORD IDENT NUMBER STRING OP REM DATA ESCAPE
    text: str        # normalized: lowercase for KEYWORD/IDENT, raw otherwise
    col: int         # 0-based offset into the line text
    raw: str         # exactly the source characters consumed
    size: int        # bytes this token occupies in the tokenized program
    fused: bool      # KEYWORD only: glued to identifier characters in the source


def petscii_len(raw: str) -> int:
    """Length in PETSCII characters — each `{name}` escape counts as one."""
    return len(_ESCAPE_RE.sub("\x00", raw))


def _match_keyword(low: str, i: int) -> str | None:
    for kw in KEYWORDS:
        if low.startswith(kw, i):
            return kw
    return None


def _fused(text: str, start: int, end: int) -> bool:
    """True when the keyword is glued to identifier characters — the evidence
    that the author wrote one name and the ROM saw a keyword."""
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    return bool(_IDENT_CH.match(before) or before in "$%" or _IDENT_CH.match(after))


def tokenize_line(text: str) -> list[Token]:
    """Tokenize one logical line's text (the part after the line number)."""
    low, out, i, n = text.lower(), [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == '"':                                   # strings swallow everything
            j = text.find('"', i + 1)
            end = n if j < 0 else j + 1
            raw = text[i:end]
            out.append(Token("STRING", raw, i, raw, petscii_len(raw), False))
            i = end
            continue
        if ch == "{" and "}" in text[i:]:               # petcat escape, 1 PETSCII char
            end = text.index("}", i) + 1
            raw = text[i:end]
            out.append(Token("ESCAPE", raw, i, raw, 1, False))
            i = end
            continue
        if ch == "π":                              # bare pi
            out.append(Token("ESCAPE", "{pi}", i, ch, 1, False))
            i += 1
            continue
        if ch == "?":
            out.append(Token("KEYWORD", "print", i, ch, 1, _fused(text, i, i + 1)))
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            j = _scan_number(text, i)
            out.append(Token("NUMBER", text[i:j].lower(), i, text[i:j], j - i, False))
            i = j
            continue
        kw = _match_keyword(low, i)
        if kw:
            end = i + len(kw)
            out.append(Token("KEYWORD", kw, i, text[i:end], 1, _fused(text, i, end)))
            i = end
            if kw == "rem":                             # rest of the line is a comment
                rest = text[i:]
                out.append(Token("REM", rest, i, rest, len(rest), False))
                break
            if kw == "data":                            # items opaque to the next ':'
                end = _scan_data(text, i)
                item = text[i:end]
                out.append(Token("DATA", item, i, item, petscii_len(item), False))
                i = end
            continue
        if ch.isalpha():
            j, name = i, ""
            while j < n and _IDENT_CH.match(text[j]):
                if j > i and _match_keyword(low, j):     # keyword fuses into the run
                    break
                name += text[j]
                j += 1
            if j < n and text[j] in "$%" and not _match_keyword(low, j):
                name += text[j]
                j += 1
            out.append(Token("IDENT", name.lower(), i, text[i:j], j - i, False))
            i = j
            continue
        out.append(Token("OP", ch, i, ch, 1, False))     # incl. anything unrecognized
        i += 1
    return out


def _scan_number(text: str, i: int) -> int:
    j, n, seen_dot, seen_e = i, len(text), False, False
    while j < n:
        c = text[j].lower()
        if c.isdigit():
            j += 1
        elif c == "." and not seen_dot and not seen_e:
            seen_dot, j = True, j + 1
        elif c == "e" and not seen_e and j + 1 < n and (
                text[j + 1].isdigit() or (text[j + 1] in "+-" and j + 2 < n
                                          and text[j + 2].isdigit())):
            seen_e, j = True, j + (2 if text[j + 1] in "+-" else 1)
        else:
            break
    return j


def _scan_data(text: str, i: int) -> int:
    """DATA runs to the next colon that is not inside a quoted item."""
    n, in_str = len(text), False
    while i < n:
        if text[i] == '"':
            in_str = not in_str
        elif text[i] == ":" and not in_str:
            break
        i += 1
    return i


_MERGE_OPS = {("<", "="): "<=", (">", "="): ">=", ("<", ">"): "<>"}


def merge_tokens(toks: list[Token]) -> list[Token]:
    """`go to` -> `goto`, `<`+`=` -> `<=`. ANALYSIS ONLY — the ROM stores
    these as two tokens each, so never size a program from merged tokens."""
    out: list[Token] = []
    i = 0
    while i < len(toks):
        a = toks[i]
        b = toks[i + 1] if i + 1 < len(toks) else None
        if b is not None and a.kind == "KEYWORD" and a.text == "go" \
                and b.kind == "KEYWORD" and b.text == "to":
            out.append(Token("KEYWORD", "goto", a.col, a.raw + b.raw, 2, a.fused))
            i += 2
            continue
        if b is not None and a.kind == b.kind == "OP" \
                and (a.text, b.text) in _MERGE_OPS:
            out.append(Token("OP", _MERGE_OPS[(a.text, b.text)], a.col,
                             a.raw + b.raw, 2, False))
            i += 2
            continue
        out.append(a)
        i += 1
    return out


def text_bytes(text: str, toks: list[Token]) -> int:
    """Bytes the line's text occupies, excluding the 4-byte header and the
    1-byte terminator. Whitespace the scanner skipped is stored by the ROM
    (1 byte each) EXCEPT the run before the first token, which the crunch
    pass drops — both measured against petcat."""
    if not toks:
        return 0
    gaps = len(text) - toks[0].col - sum(len(t.raw) for t in toks)
    return sum(t.size for t in toks) + gaps


def program_bytes(sizes: list[int]) -> int:
    """Loaded size for a program whose lines have these text-byte counts.
    5 bytes/line overhead (2 link + 2 line number + 1 terminator) and 2
    trailing zero bytes; the 2-byte load address is NOT counted."""
    return sum(s + 5 for s in sizes) + 2
