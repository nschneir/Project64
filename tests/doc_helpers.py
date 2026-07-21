"""Helpers for docs-vs-reality tests."""

import re

import click

from c64lib.cli import main


def _walk_tree() -> tuple[set[str], set[str]]:
    """(invocable command paths, group paths) from the real click tree."""
    commands: set[str] = set()
    groups: set[str] = set()

    def walk(cmd, prefix):
        if isinstance(cmd, click.Group):
            groups.add(prefix)
            if cmd.invoke_without_command:
                commands.add(prefix)
            for name, sub in cmd.commands.items():
                walk(sub, f"{prefix} {name}")
        else:
            commands.add(prefix)

    walk(main, "c64")
    return commands, groups


def all_command_paths() -> set[str]:
    return _walk_tree()[0]


def valid_mention_paths() -> set[str]:
    """Commands plus bare group names — both legitimate in prose."""
    commands, groups = _walk_tree()
    return commands | groups


def code_blocks(text: str, lang: str) -> list[str]:
    """Fenced ```lang code blocks; lang may be a regex alternation."""
    return re.findall(rf"```{lang}\n(.*?)```", text, re.S)


DOC_HEADING = re.compile(r"^### `(c64[^`]*)`(?: \(alias(?:es)?: (.+)\))?", re.M)


def documented_paths(doc_text: str) -> set[str]:
    """Heading paths, including aliases documented inline as
    '### `c64 x remove` (alias: `c64 x rm`)'."""
    out = set()
    for name, aliases in DOC_HEADING.findall(doc_text):
        out.add(name)
        if aliases:
            out.update(re.findall(r"`(c64[^`]*)`", aliases))
    return out


PET_MENTION = re.compile(r"`(c64(?: [a-z]+)+)\b")


def mentioned_commands(doc_text: str) -> set[str]:
    """`c64 xyz ...` mentions in backticks, trimmed to known-prefix depth 3."""
    real = valid_mention_paths()
    out = set()
    for m in PET_MENTION.findall(doc_text):
        words = m.split()
        for depth in (3, 2, 1):
            cand = " ".join(words[:depth])
            if cand in real:
                out.add(cand)
                break
        else:
            out.add(m)  # unknown mention — will fail the subset check
    return out


# Boot-banner free bytes per model, captured from live x64sc (plan Task 9).
# The README table and test_integration_vice both check against this.
BOOT_FREE = {
    "c64": "38911",
    "c64pal": "38911",
}
