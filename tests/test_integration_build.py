"""End-to-end build-pipeline tests: run every demo on a real emulated C64."""

import os
import shutil
from pathlib import Path

import pytest

from c64lib.basic import tokenize
from c64lib.build import build_asm
from c64lib.text import ascii_to_petscii
from tests.vice_helpers import example_programs, wait_for_text

# The loadable share of the example library; test_integration_cart.py takes
# the cartridges and test_integration_runner.py the disks, from the same
# predicate.
PROGRAMS = example_programs("loadable")

pytestmark = [
    pytest.mark.vice,
    pytest.mark.skipif(
        not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
        reason="x64sc not installed",
    ),
]


def _expectations(demo: Path) -> list[str]:
    return [ln for ln in (demo / "expect.txt").read_text().splitlines() if ln.strip()]


def _build_demo(demo: Path, out_dir: Path) -> Path:
    bas = demo / "program.bas"
    if bas.exists():
        return tokenize(bas, out_dir / f"{demo.name}.prg", "2.0")
    if shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"):
        pytest.skip("cc65 not installed")
    return build_asm(demo / "program.s", out_prg=out_dir / f"{demo.name}.prg").prg


@pytest.mark.parametrize("demo", PROGRAMS, ids=[d.name for d in PROGRAMS])
def test_demo(demo, session, tmp_path):
    prg = _build_demo(demo, tmp_path)
    with session.monitor() as mon:
        try:
            mon.autostart(prg.resolve(), run=True)
        finally:
            mon.resume()
    for needle in _expectations(demo):
        wait_for_text(session, needle, timeout=45.0)


def test_basic_type_path(session):
    src = Path("tests/programs/hello-basic/program.bas").read_text() + "run\n"
    with session.monitor() as mon:
        try:
            mon.keyboard_feed(ascii_to_petscii(src))
        finally:
            mon.resume()
    wait_for_text(session, "2+2= 4", timeout=30.0)
