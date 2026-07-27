"""Shared helpers for live-VICE integration tests."""

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


def is_cart_program(demo: Path) -> bool:
    """True for an example program that ships as a cartridge."""
    return program_kind(demo) == "cart"


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
