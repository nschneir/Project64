"""Directory-driven fixtures: adding a .bas (plus a sidecar for bad/) is all
it takes to cover a new rule — no new test function."""

import json
import re
from pathlib import Path

import pytest

from c64lib.basic_lint import lint_source

DATA = Path("tests/data/basic-lint")
GOOD = sorted((DATA / "good").glob("*.bas"))
BAD = sorted((DATA / "bad").glob("*.bas"))


@pytest.mark.parametrize("path", GOOD, ids=lambda p: p.name)
def test_good_fixtures_are_clean(path):
    issues = lint_source(path.read_text(encoding="utf-8"))
    assert issues == [], f"{path.name}: " + "; ".join(
        f"{i.rule}@{i.line}: {i.message}" for i in issues)


@pytest.mark.parametrize("path", BAD, ids=lambda p: p.name)
def test_bad_fixtures_match_their_sidecar(path):
    sidecar = path.with_suffix(".expected.json")
    expected = {(e["line"], e["severity"], e["rule"])
                for e in json.loads(sidecar.read_text(encoding="utf-8"))["expect"]}
    actual = {(i.line, i.severity, i.rule) for i in lint_source(path.read_text(encoding="utf-8"))}
    assert actual == expected, (          # key=str: file-level issues sort as None
        f"{path.name}\n  missing: {sorted(expected - actual, key=str)}\n"
        f"  unexpected: {sorted(actual - expected, key=str)}")


def test_fixture_directories_are_populated():
    assert len(GOOD) >= 3 and len(BAD) >= 4


CORPUS_DIRS = [Path("tests/programs"), Path("demos")]
COOKBOOK = Path("skills/c64-development/references/cookbook.md")


def _corpus() -> list[tuple[str, str]]:
    """(label, source) for every known-good BASIC program in the repo."""
    out = [(str(p), p.read_text(encoding="utf-8"))
           for d in CORPUS_DIRS if d.exists() for p in sorted(d.rglob("*.bas"))]
    cookbook = COOKBOOK.read_text(encoding="utf-8")
    out += [(f"{COOKBOOK}#basic[{i}]", b) for i, b in
            enumerate(re.findall(r"```basic\n(.*?)```", cookbook, re.S))]
    return out


CORPUS = _corpus()


@pytest.mark.parametrize("label,source", CORPUS, ids=[c[0] for c in CORPUS])
def test_known_good_programs_have_no_errors(label, source):
    """Spec §8.1: these run on a real C64 (the cookbook recipes are
    live-verified by test_docs_cookbook). An error here means the RULE is
    wrong — never 'fix' the program."""
    errors = [i for i in lint_source(source) if i.severity == "error"]
    assert not errors, f"{label}: " + "; ".join(
        f"{i.rule}@{i.line}: {i.message}" for i in errors)


def test_corpus_is_not_empty():
    assert len(CORPUS) >= 7
