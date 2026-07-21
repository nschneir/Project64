"""VICE label ("moncommands") files: `al C:080d .name` lines.

ld65 -Ln emits the same format without the C: memspace prefix; we accept both.
"""

from __future__ import annotations

import re
from pathlib import Path

_LABEL_RE = re.compile(r"^al\s+(?:C:)?([0-9A-Fa-f]+)\s+\.?(\S+)", re.IGNORECASE)


def parse_labels(text: str) -> dict[str, int]:
    labels: dict[str, int] = {}
    for line in text.splitlines():
        m = _LABEL_RE.match(line.strip())
        if m:
            labels[m.group(2)] = int(m.group(1), 16)
    return labels


def load_labels(path: str | Path) -> dict[str, int]:
    return parse_labels(Path(path).read_text())


def save_labels(path: str | Path, labels: dict[str, int]) -> None:
    lines = [f"al C:{addr:04x} .{name}"
             for name, addr in sorted(labels.items(), key=lambda kv: kv[1])]
    Path(path).write_text("\n".join(lines) + "\n")


def resolve(labels: dict[str, int], ref: str) -> int:
    if ref in labels:
        return labels[ref]
    folded = {n.lower(): a for n, a in labels.items()}
    if ref.lower() in folded:
        return folded[ref.lower()]
    close = [n for n in labels if ref.lower() in n.lower() or n.lower() in ref.lower()]
    hint = f"; did you mean: {', '.join(sorted(close))}" if close else ""
    raise KeyError(f"unknown symbol {ref!r}{hint}; known: {', '.join(sorted(labels))}")


def nearest(labels: dict[str, int], addr: int) -> tuple[str, int] | None:
    best: tuple[str, int] | None = None
    for name, a in labels.items():
        if name.startswith("__") and name.endswith("__"):
            continue
        off = addr - a
        if 0 <= off < 256 and (best is None or off < best[1]):
            best = (name, off)
    return best


def format_addr(labels: dict[str, int], addr: int) -> str:
    hit = nearest(labels, addr)
    if hit is None:
        return f"${addr:04x}"
    name, off = hit
    return f"${addr:04x} ({name}+{off})" if off else f"${addr:04x} ({name})"
