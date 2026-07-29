"""Unit tests for tests/vice_helpers.py's timeout scaling — no VICE needed."""

import sys

import pytest

import tests.vice_helpers as vice_helpers
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


class _FakeMonitor:
    def resume(self):
        pass


class _FakeMonitorCtx:
    def __enter__(self):
        return _FakeMonitor()

    def __exit__(self, *exc_info):
        return False


class _FakeSession:
    profile = None

    def monitor(self):
        return _FakeMonitorCtx()


def test_wait_for_text_deadline_scales_with_timeout_scale(monkeypatch):
    """Locks in that `wait_for_text` actually multiplies its deadline by
    `timeout_scale()` rather than just calling it for effect — deleting the
    `* timeout_scale()` from the source would leave this suite green
    otherwise, since the pure-function tests above never touch the wiring.
    """
    clock = {"now": 0.0}
    monkeypatch.setattr(vice_helpers.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        vice_helpers.time, "sleep", lambda s: clock.__setitem__("now", clock["now"] + s)
    )
    monkeypatch.setattr(vice_helpers, "timeout_scale", lambda: 5.0)
    monkeypatch.setattr(vice_helpers, "read_screen_text", lambda mon, profile: "")

    with pytest.raises(pytest.fail.Exception):
        vice_helpers.wait_for_text(_FakeSession(), "READY.", timeout=1.0)

    # An unscaled deadline would have given up around clock == 1.0; reaching
    # 5.0 proves the ×5 sentinel scale was applied to the wait itself.
    assert clock["now"] >= 5.0
