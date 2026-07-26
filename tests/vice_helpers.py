"""Shared helpers for live-VICE integration tests."""

import time
from pathlib import Path

import pytest

from c64lib.screen import read_screen_text
from c64lib.testing import is_cart_spec

PROGRAMS_DIR = Path(__file__).parent / "programs"


def is_cart_program(demo: Path) -> bool:
    """True for an example program that ships as a cartridge.

    A cartridge is attached at power-on and runs instead of BASIC: there is no
    .prg to autostart, so the load-and-run path does not apply to it. This
    delegates to the shipped predicate `c64lib.testing.program_test` itself
    uses, so the two integration files that split the library on it cannot
    drift from the runner — or from each other.
    """
    return is_cart_spec(demo / "test.yaml")


def example_programs(*, cart: bool) -> list[Path]:
    """Example-program directories, split by how they reach the machine.

    The two halves are complementary and exhaustive by construction, so a new
    directory is always claimed by exactly one runner — test_integration_build
    autostarts the loadable ones, test_integration_cart boots the cartridges.
    A hardcoded list here is how a third cart directory would end up tested by
    neither.
    """
    return sorted(p.parent for p in PROGRAMS_DIR.glob("*/expect.txt")
                  if is_cart_program(p.parent) is cart)


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
