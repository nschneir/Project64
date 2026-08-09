from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from c64lib.build import BuildResult
from c64lib.testing import StepResult, TestResult
from tests.test_mcp_scaffold import call_tool


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def _fake():
    s = Mock()
    s.name, s.model, s.labels = "c64", "c64", None
    s.profile.basic_version = "2.0"
    s.profile.basic_start = 0x0801
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def test_build(tmp_path):
    src = tmp_path / "p.s"
    src.write_text("; x\n")
    res = BuildResult(prg=tmp_path / "p.prg", labels=tmp_path / "p.lbl")
    with patch("c64lib.mcp_server.build_asm", return_value=res) as ba:
        err, out = call_tool("c64_build", {"source": str(src)})
    assert err is False and out["prg"].endswith("p.prg")
    ba.assert_called_once_with(Path(str(src)), out_prg=None,
                               basic_start=0x0801, areas=[])


def test_build_output_threads_through(tmp_path):
    src = tmp_path / "p.s"
    src.write_text("; x\n")
    out_prg = tmp_path / "elsewhere" / "game.prg"
    res = BuildResult(prg=out_prg, labels=out_prg.with_suffix(".lbl"))
    with patch("c64lib.mcp_server.build_asm", return_value=res) as ba:
        err, out = call_tool("c64_build",
                             {"source": str(src), "output": str(out_prg)})
    assert err is False and out["prg"] == str(out_prg)
    ba.assert_called_once_with(Path(str(src)), out_prg=Path(out_prg),
                               basic_start=0x0801, areas=[])


def test_run_dispatch_bas(tmp_path):
    src = tmp_path / "d.bas"
    src.write_text('10 print "hi"\n')
    s, mon = _fake()
    prg = tmp_path / "d.prg"
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.tokenize", return_value=prg) as tok:
        S.attach.return_value = s
        err, out = call_tool("c64_run", {"source": str(src)})
    assert err is False
    tok.assert_called_once()
    mon.autostart.assert_called_once_with(prg.resolve(), run=True)


def test_basic_type_text():
    s, mon = _fake()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_basic_type",
                             {"text": '10 print "HI"', "run": True})
    assert err is False
    fed = b"".join(c.args[0] for c in mon.keyboard_feed.call_args_list)
    assert fed == b'10 PRINT "HI"\rRUN\r'


def test_disk_and_rom_tools(tmp_path):
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    listing = {"label": "work", "files": [], "blocks_free": 663}
    with patch("c64lib.mcp_server.list_files", return_value=listing):
        err, out = call_tool("c64_disk_ls", {"image": str(img)})
    assert err is False and out["blocks_free"] == 663

    s, mon = _fake()
    mon.memory_read.return_value = b"\x4c\x66\xf2"
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_rom_disasm", {"start": "CHROUT", "length": 3})
    assert err is False
    assert out["lines"][0] == "CHROUT:"


def test_test_run_tool(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("steps: []\n")
    result = TestResult(name="a", machine="c64", passed=True,
                        steps=[StepResult(1, "wait", True, "ok")],
                        elapsed=1.0, screen="READY.", session_name="t1")
    with patch("c64lib.mcp_server.run_test", return_value=result), \
         patch("c64lib.mcp_server.load_test", return_value={"name": "a"}):
        err, out = call_tool("c64_test_run", {"yaml_file": str(f)})
    assert err is False and out["passed"] is True
