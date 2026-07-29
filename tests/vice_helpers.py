"""Shared helpers for live-VICE integration tests."""

import os
import sys
import time
from pathlib import Path

import pytest

from c64lib.screen import read_screen_text
from c64lib.testing import is_cart_spec, is_disk_spec

PROGRAMS_DIR = Path(__file__).parent / "programs"

#: The three ways an example program reaches the machine.
PROGRAM_KINDS = ("cart", "disk", "loadable")


def program_kind(demo: Path) -> str:
    """How an example program reaches the machine: "cart", "disk" or
    "loadable".

    A cartridge is mapped at power-on and runs instead of BASIC; a disk is
    attached at power-on and its first file autostarted; everything else is a
    .prg the runner builds and autostarts. This delegates to the shipped
    predicates `c64lib.testing.program_test` itself uses, so the integration
    files that split the library on it cannot drift from the runner — or from
    each other.
    """
    spec = demo / "test.yaml"
    if is_cart_spec(spec):
        return "cart"
    if is_disk_spec(spec):
        return "disk"
    return "loadable"


def example_programs(kind: str) -> list[Path]:
    """Example-program directories of one kind.

    The three kinds are complementary and exhaustive by construction, so a new
    directory is always claimed by exactly one runner — test_integration_build
    autostarts the loadable ones, test_integration_cart boots the cartridges,
    test_integration_runner boots the disks. A hardcoded list here is how a
    fourth cart directory would end up tested by none of them.
    """
    if kind not in PROGRAM_KINDS:
        raise ValueError(f"unknown program kind {kind!r} (of {PROGRAM_KINDS})")
    return sorted(p.parent for p in PROGRAMS_DIR.glob("*/expect.txt")
                  if program_kind(p.parent) == kind)


def timeout_scale() -> float:
    """Live-wait timeout multiplier.

    Three live tests once flaked under coverage load — each a "screen state
    never arrived" against the shared emulator, each green standalone (see
    the `## [Unreleased]` CHANGELOG entry for the investigation: the one
    failure that ever reproduced traced to keystroke contamination from a
    focus-stealing headless-launch bug, not slowness). This multiplier
    stands on reasoning rather than a measured before/after: coverage
    tracing plausibly slows both the host poll loop and VICE itself, so
    waits sized for an unloaded machine get scaled up here. Un-instrumented
    runs are unchanged.
    """
    env = os.environ.get("C64_TOOLS_TEST_TIMEOUT_SCALE")
    if env:
        return float(env)
    instrumented = "coverage" in sys.modules or "COVERAGE_RUN" in os.environ
    return 3.0 if instrumented else 1.0


def wait_for_text(session, needle, timeout=30.0):
    deadline = time.monotonic() + timeout * timeout_scale()
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
