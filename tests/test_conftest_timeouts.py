"""Locks in that the shared-machine helpers in tests/conftest.py actually
apply `timeout_scale()` to their deadlines, not just call it for effect.

No emulator needed: a fake session/monitor stands in, and a fake clock
(monkeypatched `time.monotonic`/`time.sleep`) lets the timeout deadline be
crossed without a real wait.
"""

import pytest

from tests import conftest as ct


class _FakeMonitor:
    """Never reaches READY / never looks rebooted, so both helpers below run
    to their timeout instead of returning early."""

    def checkpoint_list(self):
        return []

    def checkpoint_delete(self, number):
        pass

    def memory_write(self, addr, data):
        pass

    def memory_read(self, addr, length):
        return b"\xff"  # sentinel never overwritten -> _reset_clean sees no reboot

    def reset(self, hard=True):
        pass

    def resume(self):
        pass

    def release(self):
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


@pytest.fixture
def fake_clock(monkeypatch):
    """A controllable stand-in for time.monotonic()/time.sleep() in the
    conftest module, so a timeout deadline can be crossed instantly."""
    clock = {"now": 0.0}
    monkeypatch.setattr(ct.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        ct.time, "sleep", lambda s: clock.__setitem__("now", clock["now"] + s)
    )
    return clock


def test_wait_ready_deadline_scales_with_timeout_scale(monkeypatch, fake_clock):
    monkeypatch.setattr(ct, "timeout_scale", lambda: 5.0)
    monkeypatch.setattr(ct, "read_screen_text", lambda mon, profile: "")

    with pytest.raises(TimeoutError):
        ct._wait_ready(_FakeSession(), timeout=1.0)

    # An unscaled deadline would have given up around clock == 1.0; reaching
    # 5.0 proves the ×5 sentinel scale was applied to the wait itself.
    assert fake_clock["now"] >= 5.0


def test_reset_clean_deadline_scales_with_timeout_scale(monkeypatch, fake_clock):
    monkeypatch.setattr(ct, "timeout_scale", lambda: 5.0)
    monkeypatch.setattr(ct, "read_screen_text", lambda mon, profile: "")

    with pytest.raises(TimeoutError):
        ct._reset_clean(_FakeSession(), timeout=1.0)

    assert fake_clock["now"] >= 5.0
