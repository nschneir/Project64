"""Live test-runner integration: YAML tests and example programs on real x64sc."""

import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from c64lib.cli import main
from c64lib.testing import load_test, program_test, run_test

pytestmark = [
    pytest.mark.vice,
    pytest.mark.skipif(
        not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
        reason="x64sc not installed",
    ),
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Only the CLI path needs its own home: it attaches by name through the
    session records, while the rest run on the shared session directly."""
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def test_yaml_autorun_passes(shared_launch):
    result = run_test(load_test(Path("tests/data/hello-autorun.yaml")),
                      launch=shared_launch)
    assert result.passed, [s.detail for s in result.steps]
    assert len(result.steps) == 4


def test_yaml_loadrun_passes(shared_launch):
    result = run_test(load_test(Path("tests/data/hello-loadrun.yaml")),
                      launch=shared_launch)
    assert result.passed, [s.detail for s in result.steps]


def test_failing_wait_reports_screen(shared_launch):
    spec = load_test(Path("tests/data/hello-autorun.yaml"))
    spec["steps"] = [{"wait": {"text": "THIS NEVER APPEARS", "timeout": 3}}]
    result = run_test(spec, launch=shared_launch)
    assert result.passed is False
    assert "READY." in result.screen          # failure screen captured


def test_program_as_test_hello_basic(shared_launch):
    result = run_test(program_test(Path("tests/programs/hello-basic")),
                      launch=shared_launch)
    assert result.passed, [s.detail for s in result.steps]


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_program_as_test_hello_asm(shared_launch):
    result = run_test(program_test(Path("tests/programs/hello-asm")),
                      launch=shared_launch)
    assert result.passed, [s.detail for s in result.steps]


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_program_as_test_sprite_ball(shared_launch):
    """The graphics reference program: expect.txt gate plus its test.yaml
    (sprite registers, until/sample/differs motion assertions)."""
    spec = program_test(Path("tests/programs/sprite-ball"))
    kinds = [next(iter(s)) for s in spec["steps"]]
    assert "sample" in kinds            # test.yaml was merged in
    result = run_test(spec, launch=shared_launch)
    assert result.passed, [s.detail for s in result.steps]


def test_cli_end_to_end(home):
    r = CliRunner().invoke(main, ["--json", "test", "run",
                                  "tests/data/hello-autorun.yaml"])
    assert r.exit_code == 0, r.output
