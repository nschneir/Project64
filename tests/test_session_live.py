"""FT4 live checks: `session ensure` idempotence against a real x64sc."""

import os
import shutil

import pytest

from c64lib.session import Session
from tests.vice_helpers import wait_for_text

pytestmark = [
    pytest.mark.vice,
    pytest.mark.skipif(
        not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
        reason="x64sc not installed",
    ),
]


def test_ensure_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    s1, started1 = Session.ensure(model="c64", name="ens",
                                  headless=True, warp=True)
    try:
        assert started1 is True
        wait_for_text(s1, "READY.", timeout=45)
        s2, started2 = Session.ensure(model="c64", name="ens",
                                      headless=True, warp=True)
        assert started2 is False
        assert s2.pid == s1.pid          # attached, didn't boot a second PET
    finally:
        s1.stop()
    assert Session.list_all() == []      # no leaked sessions
