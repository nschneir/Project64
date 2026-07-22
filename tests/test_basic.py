import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from c64lib.basic import PETCAT_DIALECTS, BasicError, detokenize, tokenize


def test_dialect_map():
    assert PETCAT_DIALECTS == {"2.0": "2"}


def test_tokenize_command_line(tmp_path):
    src, out = tmp_path / "a.bas", tmp_path / "a.prg"
    src.write_text('10 print "hi"\n')
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        out.write_bytes(b"\x01\x08")

        class R:
            returncode = 0
            stderr = ""

        return R()

    with patch("c64lib.basic.subprocess.run", side_effect=fake_run), \
         patch("c64lib.basic._petcat", return_value="petcat"):
        tokenize(src, out, "2.0")
    assert captured["cmd"] == ["petcat", "-w2", "-o", str(out), "--", str(src)]


def test_missing_petcat_message(monkeypatch):
    monkeypatch.delenv("C64_TOOLS_PETCAT", raising=False)
    monkeypatch.setattr("c64lib.basic.shutil.which", lambda n: None)
    with pytest.raises(BasicError, match="[Ii]nstall"):
        tokenize(Path("x.bas"), Path("x.prg"), "2.0")


needs_petcat = pytest.mark.skipif(shutil.which("petcat") is None, reason="petcat not installed")


@needs_petcat
def test_real_petcat_roundtrip(tmp_path):
    src = tmp_path / "demo.bas"
    src.write_text('10 print "hello"\n20 print 2+2\n')
    prg = tokenize(src, tmp_path / "demo.prg", "2.0")
    data = prg.read_bytes()
    assert data[:2] == b"\x01\x08"      # load address $0801
    assert b"\x99" in data              # PRINT token
    listing = detokenize(prg, "2.0")
    assert 'print "hello"' in listing
    assert "2+2" in listing


def test_unknown_basic_version_raises():
    from c64lib.basic import BasicError, _dialect
    with pytest.raises(BasicError, match="no petcat dialect"):
        _dialect("9.9")
    with pytest.raises(BasicError, match="no petcat dialect"):
        _dialect("4.0")


def test_petcat_failure_surfaces_stderr(tmp_path, monkeypatch):
    import subprocess

    from c64lib import basic

    def fail(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
    monkeypatch.setattr(basic.subprocess, "run", fail)
    src = tmp_path / "p.bas"
    src.write_text("10 print\n")
    with pytest.raises(basic.BasicError, match="boom"):
        basic.tokenize(src, tmp_path / "p.prg", "2.0")
