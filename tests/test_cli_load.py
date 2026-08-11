import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.build import BuildResult
from c64lib.cli import main


def _fake_attached():
    fake = Mock()
    fake.name, fake.model = "c64", "c64"
    fake.profile.basic_version = "2.0"
    fake.profile.basic_start = 0x0801
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_load_autostarts_and_registers_symbols(tmp_path):
    prg = tmp_path / "p.prg"
    prg.write_bytes(b"\x01\x08")
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:040d .start\n")
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["load", str(prg), "--symbols", str(lbl)])
    assert r.exit_code == 0, r.output
    mon.autostart.assert_called_once_with(prg.resolve(), run=True)
    mon.resume.assert_called_once()
    fake.set_labels_path.assert_called_once_with(str(lbl.resolve()))


def test_load_no_run(tmp_path):
    prg = tmp_path / "p.prg"
    prg.write_bytes(b"\x01\x08")
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["load", str(prg), "--no-run"])
    assert r.exit_code == 0
    mon.autostart.assert_called_once_with(prg.resolve(), run=False)


def test_run_bas_tokenizes_then_autostarts(tmp_path):
    src = tmp_path / "d.bas"
    src.write_text('10 print "hi"\n')
    fake, mon = _fake_attached()
    prg = tmp_path / "d.prg"
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.ops.tokenize", return_value=prg) as tok:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "run", str(src)])
    assert r.exit_code == 0, r.output
    tok.assert_called_once_with(src.resolve(), src.resolve().with_suffix(".prg"), "2.0")
    mon.autostart.assert_called_once_with(prg, run=True)


def test_run_asm_builds_and_registers_labels(tmp_path):
    src = tmp_path / "d.s"
    src.write_text("; x\n")
    res = BuildResult(prg=tmp_path / "d.prg", labels=tmp_path / "d.lbl")
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.ops.build_asm", return_value=res) as ba:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["run", str(src)])
    assert r.exit_code == 0, r.output
    # areas=[] pinned like test_cli_build's: the no---area path must keep
    # linking exactly as it did before the flag existed.
    ba.assert_called_once_with(src.resolve(), basic_start=0x0801, areas=[])
    mon.autostart.assert_called_once_with(res.prg, run=True)
    fake.set_labels_path.assert_called_once_with(str(res.labels))


def test_run_unknown_extension(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("x")
    fake, _ = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "run", str(f)])
    assert r.exit_code == 1
    assert ".txt" in json.loads(r.output)["error"]
