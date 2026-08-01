"""Direct tests for MCP tools that previously had no unit coverage.
Harness identical to test_mcp_session.py: in-memory MCP client, mocked Session."""

from unittest.mock import Mock, patch

import pytest

from c64lib.protocol import CP_EXEC, CP_LOAD, CP_STORE, Checkpoint
from c64lib.text import ascii_to_petscii
from tests.test_mcp_scaffold import call_tool


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def _fake_session(labels=None):
    s = Mock()
    s.name, s.model, s.pid, s.port, s.labels = "c64", "c64", 1, 6502, labels
    s.profile.basic_version = "2.0"
    s.profile.basic_start = 0x0801
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def _ck(number=1, start=0x040D, op=CP_EXEC, hits=0):
    return Checkpoint(number=number, hit=False, start=start, end=start, stop=True,
                      enabled=True, op=op, temporary=False, hit_count=hits,
                      ignore_count=0, has_condition=False, memspace=0)


# --- session / screen / registers -------------------------------------------

def test_session_reset_hard_resumes():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_session_reset", {"hard": True})
    assert err is False and out == {"reset": "c64", "hard": True}
    mon.reset.assert_called_once_with(hard=True)
    mon.resume.assert_called_once()


def test_screenshot():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.save_screenshot_png", return_value=(320, 200)):
        S.attach.return_value = s
        err, out = call_tool("c64_screenshot", {"path": "shot.png"})
    assert err is False and out == {"png": "shot.png", "width": 320, "height": 200}
    mon.release.assert_called_once()


@pytest.mark.parametrize("args,want", [({}, False), ({"border": True}, True)])
def test_screenshot_border_threads_through(args, want):
    """border must reach save_screenshot_png(border=...); default is False."""
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.save_screenshot_png",
               return_value=(384, 272)) as save:
        S.attach.return_value = s
        err, out = call_tool("c64_screenshot", {"path": "shot.png", **args})
    assert err is False, out
    save.assert_called_once()
    assert save.call_args.kwargs["border"] is want


def test_reg_set_parses_hex():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_reg_set", {"name": "a", "value": "$2a"})
    assert err is False and out == {"register": "A", "value": 0x2A}
    mon.set_register.assert_called_once_with("a", 0x2A)
    mon.release.assert_called_once()


# --- breakpoints / watchpoints ----------------------------------------------

def test_break_add_with_condition():
    s, mon = _fake_session()
    mon.checkpoint_set.return_value = _ck(number=7)
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_break_add",
                             {"ref": "$040d", "condition": "A == 1"})
    assert err is False and out["id"] == 7
    mon.condition_set.assert_called_once_with(7, "A == 1")


def test_break_list():
    s, mon = _fake_session()
    mon.checkpoint_list.return_value = [_ck(number=2, hits=5)]
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_break_list", {})
    assert err is False
    (bp,) = out["breakpoints"]
    assert bp["id"] == 2 and bp["hits"] == 5 and bp["enabled"] is True
    mon.release.assert_called_once()


def test_break_remove():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_break_remove", {"checkpoint_id": 3})
    assert err is False and out == {"removed": 3}
    mon.checkpoint_delete.assert_called_once_with(3)


def test_watch_add_defaults_to_load_and_store():
    s, mon = _fake_session()
    mon.checkpoint_set.return_value = _ck(number=9, op=CP_LOAD | CP_STORE)
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_watch_add", {"ref": "$0400", "length": 4})
    assert err is False and out["id"] == 9 and out["length"] == 4
    mon.checkpoint_set.assert_called_once_with(0x0400, 0x0403,
                                               op=CP_LOAD | CP_STORE)


# --- execution control --------------------------------------------------------

def test_finish_reports_stopped_regs():
    s, mon = _fake_session()
    mon.finish.return_value = {"PC": 0x1234}
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_finish", {})
    assert err is False
    assert out["stopped"] is True and out["registers"]["PC"] == 0x1234


def test_continue_resumes():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_continue", {})
    assert err is False and out == {"running": True}
    mon.resume.assert_called_once()


def test_until_success_and_timeout():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.run_until",
               return_value={"registers": {"PC": 0x040D}, "reached": 2}):
        S.attach.return_value = s
        err, out = call_tool("c64_until", {"ref": "$040d", "count": 2})
    assert err is False and out["count"] == 2 and out["stopped"] is True

    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.run_until",
               return_value={"registers": None, "reached": 0}):
        S.attach.return_value = s
        err, out = call_tool("c64_until", {"ref": "$040d", "count": 2})
    assert err is True and "timeout" in out["raw"].lower()


def test_profile_reports_cycles_and_timeout_is_an_error():
    s, _ = _fake_session()
    fired = {"fired": True, "cycles": 507, "registers": {"PC": 0x0400},
             "trap": 0x0400}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.profile_routine", return_value=fired) as pr:
        S.attach.return_value = s
        err, out = call_tool("c64_profile", {"routine": "$c000"})
    assert err is False
    assert out["cycles"] == 507 and out["irq_masked"] is True
    assert out["trap"] == 0x0400 and out["called"] == "$c000"
    assert pr.call_args.args[1] == 0xC000

    timed_out = {"fired": False, "cycles": None, "registers": None,
                 "trap": 0x0400}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.profile_routine", return_value=timed_out):
        S.attach.return_value = s
        err, out = call_tool("c64_profile", {"routine": "$c000"})
    assert err is True and "never returned" in out["raw"]


def test_wait_mem_parses_and_passes_through():
    s, _ = _fake_session()
    result = {"fired": "mem", "elapsed": 0.1}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.wait_for_mem", return_value=result) as w:
        S.attach.return_value = s
        err, out = call_tool("c64_wait_mem",
                             {"addr": "$0400", "equals": "42", "timeout": 5.0})
    assert err is False and out == result
    w.assert_called_once_with(s, 0x0400, 42, 5.0, op="=")


def test_wait_mem_passes_the_comparison_through():
    s, _ = _fake_session()
    result = {"fired": "mem", "elapsed": 0.1}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.wait_for_mem", return_value=result) as w:
        S.attach.return_value = s
        err, out = call_tool("c64_wait_mem",
                             {"addr": "$fb", "equals": "20", "op": ">="})
    assert err is False and out == result
    w.assert_called_once_with(s, 0xFB, 20, 30.0, op=">=")


# --- program running ----------------------------------------------------------

def test_run_prg_autostarts(tmp_path):
    prg = tmp_path / "game.prg"
    prg.write_bytes(b"\x01\x08")
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_run", {"source": str(prg)})
    assert err is False and out["symbols"] is None
    mon.autostart.assert_called_once_with(prg.resolve(), run=True)
    mon.resume.assert_called_once()


def test_run_bas_tokenizes(tmp_path):
    bas = tmp_path / "hello.bas"
    bas.write_text('10 print "hi"\n')
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.tokenize",
               return_value=tmp_path / "hello.prg") as tok:
        S.attach.return_value = s
        err, out = call_tool("c64_run", {"source": str(bas)})
    assert err is False
    tok.assert_called_once_with(bas.resolve(), bas.resolve().with_suffix(".prg"), "2.0")


def test_run_unknown_extension_is_error(tmp_path):
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_run", {"source": str(tmp_path / "x.txt")})
    # same wording as the CLI's: both front ends say it one way
    assert err is True and "don't know how to run" in out["raw"]


def test_load_no_run_with_symbols(tmp_path):
    prg = tmp_path / "p.prg"
    prg.write_bytes(b"\x01\x08")
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:040d .start\n")
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_load",
                             {"prg": str(prg), "run": False, "symbols": str(lbl)})
    assert err is False and out["run"] is False
    mon.autostart.assert_called_once_with(prg.resolve(), run=False)
    s.set_labels_path.assert_called_once_with(str(lbl.resolve()))


def test_basic_type_appends_newline_and_run():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_basic_type",
                             {"text": '10 print "hi"', "run": True})
    assert err is False and out["run"] is True
    (petscii,), _ = mon.keyboard_feed.call_args
    assert petscii == ascii_to_petscii('10 print "hi"\nrun\n')
    assert out["typed_chars"] == len(petscii)
    mon.release.assert_called_once()


# --- disk / rom / test runner ---------------------------------------------------

def test_disk_create_put_get(tmp_path):
    img = tmp_path / "work.d64"
    with patch("c64lib.mcp_server.create_image", return_value=img) as ci:
        err, out = call_tool("c64_disk_create", {"image": str(img), "label": "work"})
    assert err is False and out == {"image": str(img)}
    ci.assert_called_once_with(img, label="work", disk_id="00")

    with patch("c64lib.mcp_server.put_file", return_value="game"):
        err, out = call_tool("c64_disk_put",
                             {"image": str(img), "file": str(tmp_path / "g.prg")})
    assert err is False and out == {"image": str(img), "name": "game"}

    with patch("c64lib.mcp_server.get_file",
               return_value=tmp_path / "out.prg"):
        err, out = call_tool("c64_disk_get",
                             {"image": str(img), "name": "game",
                              "dest": str(tmp_path / "out.prg")})
    # `image` and `name` too, matching what `c64 disk get --json` emits —
    # `{"dest"}` alone was the last stale divergence in the disk group.
    assert err is False and out == {"image": str(img), "name": "game",
                                    "dest": str(tmp_path / "out.prg")}


def test_disk_boot(tmp_path):
    img = tmp_path / "work.d64"
    img.write_bytes(b"")
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_disk_boot", {"image": str(img)})
    assert err is False and out == {"booted": str(img.resolve()), "symbols": None}
    mon.autostart.assert_called_once_with(img.resolve(), run=True)
    mon.resume.assert_called_once()


def test_rom_info_releases():
    s, mon = _fake_session()
    info = {"basic": "2.0", "kernal": "901465-22"}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.identify", return_value=info):
        S.attach.return_value = s
        err, out = call_tool("c64_rom_info", {})
    assert err is False and out == info
    mon.release.assert_called_once()


def test_rom_disasm_annotates():
    s, mon = _fake_session()
    mon.memory_read.return_value = b"\xea"          # NOP
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.rom_labels", return_value={"CHROUT": 0xFFD2}):
        S.attach.return_value = s
        err, out = call_tool("c64_rom_disasm", {"start": "CHROUT", "length": 1})
    assert err is False and out["start"] == 0xFFD2
    # a label line ("CHROUT:") precedes the instruction, so scan all lines
    assert any("nop" in ln.lower() for ln in out["lines"])
    mon.release.assert_called_once()


def test_test_run_and_programs(tmp_path):
    result = Mock()
    result.passed = True
    result.to_dict.return_value = {"passed": True}
    with patch("c64lib.mcp_server.load_test", return_value={"name": "t"}), \
         patch("c64lib.mcp_server.run_test", return_value=result):
        err, out = call_tool("c64_test_run", {"yaml_file": "t.yaml"})
    assert err is False and out == {"passed": True}

    d = tmp_path / "prog1"
    d.mkdir()
    (d / "expect.txt").write_text("HI\n")
    with patch("c64lib.mcp_server.program_test", return_value={"name": "prog1"}) as pt, \
         patch("c64lib.mcp_server.run_test", return_value=result):
        err, out = call_tool("c64_test_programs", {"directory": str(tmp_path)})
    assert err is False and out["passed"] is True and len(out["tests"]) == 1
    pt.assert_called_once_with(d)


def test_basic_check_returns_the_cli_payload(tmp_path):
    src = tmp_path / "bad.bas"
    src.write_text("10 goto 999\n")
    is_error, data = call_tool("c64_basic_check", {"source_path": str(src)})
    assert not is_error, data
    assert data["errors"] == 1 and data["warnings"] == 0
    assert data["issues"][0]["rule"] == "E20"
    assert data["tokenized_bytes"] == 12


def test_basic_check_clean_program(tmp_path):
    src = tmp_path / "ok.bas"
    src.write_text('10 print "hi"\n20 goto 10\n')
    is_error, data = call_tool("c64_basic_check", {"source_path": str(src)})
    assert not is_error and data["issues"] == []
