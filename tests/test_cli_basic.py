import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main


def test_tokenize_default_output(tmp_path):
    src = tmp_path / "a.bas"
    src.write_text('10 print "hi"\n')
    with patch("c64lib.cli.tokenize", return_value=tmp_path / "a.prg") as tok:
        r = CliRunner().invoke(main, ["--json", "basic", "tokenize", str(src)])
    assert r.exit_code == 0, r.output
    tok.assert_called_once_with(src, tmp_path / "a.prg", "2.0")
    assert json.loads(r.output)["prg"].endswith("a.prg")


def test_detokenize_listing(tmp_path):
    prg = tmp_path / "a.prg"
    prg.write_bytes(b"\x01\x08")
    with patch("c64lib.cli.detokenize", return_value='10 print "hi"\n'):
        r = CliRunner().invoke(main, ["basic", "detokenize", str(prg)])
    assert r.exit_code == 0
    assert 'print "hi"' in r.output


def _fake_attached():
    fake = Mock()
    fake.name, fake.model = "c64", "c64"
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_type_feeds_keyboard_and_run(tmp_path):
    src = tmp_path / "a.bas"
    src.write_text('10 print "HI"\n')
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["basic", "type", str(src), "--run"])
    assert r.exit_code == 0, r.output
    fed = b"".join(c.args[0] for c in mon.keyboard_feed.call_args_list)
    assert fed == b'10 PRINT "HI"\rRUN\r'
    mon.release.assert_called_once()


def test_key_type_feeds_text_directly():
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["key", "type", "50\n"])
    assert r.exit_code == 0, r.output
    mon.keyboard_feed.assert_called_once_with(b"50\r")
    mon.release.assert_called_once()


def _fake(labels=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", labels
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_key_type_rejects_unmappable_text():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["key", "type", "café"])   # é has no PETSCII
    assert r.exit_code == 1
    mon.keyboard_feed.assert_not_called()


def test_key_hold_zero_frames_is_a_no_op_not_a_timeout():
    """`--frames 0` used to fail with "timeout: only 0/0 frame(s) …
    checkpoint removed" — but nothing ran, nothing was armed, and nothing
    was removed. It reports the machine untouched instead."""
    fake, mon = _fake()
    with patch("c64lib.cli.ops_key_hold",
               return_value={"frames": 0, "requested": 0,
                             "registers": None}), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "key", "hold", "d",
                                      "--at", "$0819", "--frames", "0"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out == {"frames": 0, "requested": 0, "machine": "untouched"}
    assert "timeout" not in r.output


def test_check_clean_program_exits_zero(tmp_path):
    src = tmp_path / "ok.bas"
    src.write_text('10 print "hi"\n20 goto 10\n')
    r = CliRunner().invoke(main, ["basic", "check", str(src)])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == "clean"


def test_check_reports_errors_and_exits_one(tmp_path):
    src = tmp_path / "bad.bas"
    src.write_text("10 goto 999\n")
    r = CliRunner().invoke(main, ["basic", "check", str(src)])
    assert r.exit_code == 1
    assert "ERROR E20: line 10: goto target 999 does not exist" in r.output


def test_check_warnings_alone_exit_zero(tmp_path):
    src = tmp_path / "warn.bas"
    src.write_text('10 print "oops\n20 end\n')
    r = CliRunner().invoke(main, ["basic", "check", str(src)])
    assert r.exit_code == 0, r.output
    assert "WARNING W40: line 10:" in r.output


def test_check_json_payload(tmp_path):
    src = tmp_path / "bad.bas"
    src.write_text("10 goto 999\n")
    r = CliRunner().invoke(main, ["--json", "basic", "check", str(src)])
    assert r.exit_code == 1
    data = json.loads(r.output)
    assert data["errors"] == 1 and data["warnings"] == 0
    assert data["issues"][0]["rule"] == "E20"
    # GOTO=1 + space=1 + "999"=3 -> 5 text bytes, +5 line overhead, +2 trailing.
    assert data["tokenized_bytes"] == 12
