"""Directory-driven fixtures: adding a .bas (plus a sidecar for bad/) is all
it takes to cover a new rule — no new test function."""

import json
from pathlib import Path

import pytest

from c64lib.basic_lint import lint_source

DATA = Path("tests/data/basic-lint")
GOOD = sorted((DATA / "good").glob("*.bas"))
BAD = sorted((DATA / "bad").glob("*.bas"))


@pytest.mark.parametrize("path", GOOD, ids=lambda p: p.name)
def test_good_fixtures_are_clean(path):
    issues = lint_source(path.read_text())
    assert issues == [], f"{path.name}: " + "; ".join(
        f"{i.rule}@{i.line}: {i.message}" for i in issues)


@pytest.mark.parametrize("path", BAD, ids=lambda p: p.name)
def test_bad_fixtures_match_their_sidecar(path):
    sidecar = path.with_suffix(".expected.json")
    expected = {(e["line"], e["severity"], e["rule"])
                for e in json.loads(sidecar.read_text())["expect"]}
    actual = {(i.line, i.severity, i.rule) for i in lint_source(path.read_text())}
    assert actual == expected, (          # key=str: file-level issues sort as None
        f"{path.name}\n  missing: {sorted(expected - actual, key=str)}\n"
        f"  unexpected: {sorted(actual - expected, key=str)}")


def test_fixture_directories_are_populated():
    assert len(GOOD) >= 3 and len(BAD) >= 4
