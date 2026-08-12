import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from c64lib.cli import main
from c64lib.testing import StepResult, TestResult


def _result(passed=True, name="t"):
    return TestResult(
        name=name, machine="c64", passed=passed,
        steps=[StepResult(index=1, kind="wait", ok=passed,
                          detail="text 'X' seen" if passed else "text 'X' not seen in 2s")],
        elapsed=1.5, screen="READY.\nX" if passed else "READY.",
        session_name="t123456",
    )


def test_run_pass_exit_zero(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("steps: []\n")
    with patch("c64lib.cli.run_test", return_value=_result(True)) as rt, \
         patch("c64lib.cli.load_test", return_value={"name": "a"}) as lt:
        r = CliRunner().invoke(main, ["--json", "test", "run", str(f)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["passed"] is True and out["tests"][0]["name"] == "t"
    lt.assert_called_once_with(f)
    rt.assert_called_once_with({"name": "a"}, allow_stale=False)


def test_run_fail_exit_one(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("steps: []\n")
    with patch("c64lib.cli.run_test", return_value=_result(False)), \
         patch("c64lib.cli.load_test", return_value={"name": "a"}):
        r = CliRunner().invoke(main, ["--json", "test", "run", str(f)])
    assert r.exit_code == 1
    assert json.loads(r.output)["passed"] is False


def test_run_allow_stale_forwards_the_flag_and_reports_the_waiver(tmp_path):
    """`--allow-stale` is the answer to a staleness stop a copied tree
    provoked, and it has to say what it let through in both voices: the human
    line and the `--json` payload a harness reads."""
    f = tmp_path / "a.yaml"
    f.write_text("steps: []\n")
    result = _result(True)
    result.warnings = ["staleness allowed: game.d64 predates its symbols"]
    with patch("c64lib.cli.run_test", return_value=result) as rt, \
         patch("c64lib.cli.load_test", return_value={"name": "a"}):
        r = CliRunner().invoke(main, ["test", "run", str(f), "--allow-stale"])
        j = CliRunner().invoke(main, ["--json", "test", "run", str(f),
                                      "--allow-stale"])
    assert r.exit_code == 0, r.output
    assert "warning: staleness allowed: game.d64 predates" in r.output
    assert rt.call_args == (({"name": "a"},), {"allow_stale": True})
    assert json.loads(j.output)["tests"][0]["warnings"] == result.warnings


def test_run_load_error(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("program: nosuch.bas\n")
    r = CliRunner().invoke(main, ["--json", "test", "run", str(f)])
    assert r.exit_code == 1
    assert "nosuch" in json.loads(r.output)["error"]


def test_programs_runs_each_directory(tmp_path):
    for d in ("alpha", "beta"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "expect.txt").write_text("X\n")
        (tmp_path / d / "program.bas").write_text("10 rem\n")
    results = {"alpha": _result(True, "alpha"), "beta": _result(False, "beta")}
    with patch("c64lib.cli.program_test", side_effect=lambda p: {"name": Path(p).name}) as dt, \
         patch("c64lib.cli.run_test", side_effect=lambda s: results[s["name"]]):
        r = CliRunner().invoke(main, ["--json", "test", "programs", str(tmp_path)])
    assert r.exit_code == 1          # beta failed
    out = json.loads(r.output)
    assert [t["name"] for t in out["tests"]] == ["alpha", "beta"]
    assert out["passed"] is False
    assert dt.call_count == 2


def test_test_run_bad_yaml_fails(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("- a list\n")
    r = CliRunner().invoke(main, ["--json", "test", "run", str(f)])
    assert r.exit_code == 1
    assert "mapping" in json.loads(r.output)["error"]


def test_test_programs_empty_dir_fails(tmp_path):
    r = CliRunner().invoke(main, ["test", "programs", str(tmp_path)])
    assert r.exit_code == 1 and "no example programs" in r.output


def test_test_programs_empty_dir_json_keeps_the_envelope(tmp_path):
    """The no-programs-found exit is a spec-level error like any other, so it
    owes a parsing harness the same {passed, tests} envelope — reading
    `out["tests"]` must not raise KeyError just because nothing ran."""
    r = CliRunner().invoke(main, ["--json", "test", "programs", str(tmp_path)])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["tests"] == [] and out["passed"] is False
    assert "no example programs" in out["error"]


def test_spec_error_json_keeps_the_envelope(tmp_path):
    """A spec-level failure must still emit the {passed, tests} envelope —
    1812's harness crashed on the missing 'tests' key instead of reporting
    the actual error."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nsteps:\n  - bogus: 1\n")   # unknown step kind
    r = CliRunner().invoke(main, ["--json", "test", "run", str(bad)])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["tests"] == [] and out["passed"] is False
    assert out["error"]


def test_programs_per_program_spec_error_json_keeps_the_envelope(tmp_path):
    """`test programs` bails on the first program whose spec will not load —
    here a directory with an `expect.txt` but no program file, rejected before
    any session launch. That early return owes the envelope too."""
    d = tmp_path / "alpha"
    d.mkdir()
    (d / "expect.txt").write_text("X\n")          # qualifies as a program dir...
    r = CliRunner().invoke(main, ["--json", "test", "programs", str(tmp_path)])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["tests"] == [] and out["passed"] is False
    assert "alpha" in out["error"]
