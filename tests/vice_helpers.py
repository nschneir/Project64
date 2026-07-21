"""Shared helpers for live-VICE integration tests."""

import time

import pytest

from c64lib.screen import read_screen_text


def wait_for_text(session, needle, timeout=30.0):
    deadline = time.monotonic() + timeout
    text = ""
    while time.monotonic() < deadline:
        with session.monitor() as mon:
            try:
                text = read_screen_text(mon, session.profile)
            finally:
                mon.resume()
        if needle in text:
            return text
        time.sleep(0.5)
    pytest.fail(f"{needle!r} never appeared on screen; last screen:\n{text}")
