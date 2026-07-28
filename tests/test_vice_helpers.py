"""Unit tests for tests/vice_helpers.py's timeout scaling — no VICE needed."""

import sys

import pytest

from tests.vice_helpers import timeout_scale


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip both triggers before every test in this file.

    ``"coverage" in sys.modules`` is real whenever *this* suite itself runs
    under `.venv/bin/coverage run -m pytest` (Task 6), even though a plain
    `.venv/bin/pytest` run never imports it — so a bare `delenv` leaves the
    clean-env case failing under coverage. Deleting the module from
    `sys.modules` too makes the decision logic deterministic under both
    invocations.
    """
    monkeypatch.delenv("COVERAGE_RUN", raising=False)
    monkeypatch.delenv("C64_TOOLS_TEST_TIMEOUT_SCALE", raising=False)
    monkeypatch.delitem(sys.modules, "coverage", raising=False)


def test_clean_env_is_unscaled():
    assert timeout_scale() == 1.0


def test_coverage_run_env_scales(monkeypatch):
    monkeypatch.setenv("COVERAGE_RUN", "1")
    assert timeout_scale() == 3.0


def test_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("COVERAGE_RUN", "1")
    monkeypatch.setenv("C64_TOOLS_TEST_TIMEOUT_SCALE", "5")
    assert timeout_scale() == 5.0
