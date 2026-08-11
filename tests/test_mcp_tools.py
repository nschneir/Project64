"""Direct tests for MCP tools that previously had no unit coverage.
Harness identical to test_mcp_session.py: in-memory MCP client, mocked Session."""

import json
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


def test_break_enable_toggles_on():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_break_enable", {"checkpoint_id": 4})
    assert err is False and out == {"enabled": 4}
    mon.checkpoint_toggle.assert_called_once_with(4, True)
    mon.release.assert_called_once()


def test_break_disable_toggles_off():
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_break_disable", {"checkpoint_id": 4})
    assert err is False and out == {"disabled": 4}
    mon.checkpoint_toggle.assert_called_once_with(4, False)
    mon.release.assert_called_once()


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


def _profiled(samples, fired=True):
    """A profile_routine_samples payload for `samples` cycle counts."""
    out = {"fired": fired, "samples": samples,
           "min": min(samples) if samples else None,
           "max": max(samples) if samples else None,
           "mean": round(sum(samples) / len(samples), 1) if samples else None,
           "registers": {"PC": 0x0400} if fired else None, "trap": 0x0400,
           "irq_masked": True, "reached": len(samples), "count": len(samples)}
    if len(samples) == 1:
        out["cycles"] = samples[0]
    return out


def test_profile_reports_cycles_and_timeout_is_an_error():
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.profile_routine_samples",
               return_value=_profiled([507])) as pr:
        S.attach.return_value = s
        err, out = call_tool("c64_profile", {"routine": "$c000"})
    assert err is False
    assert out["cycles"] == 507 and out["irq_masked"] is True
    assert out["trap"] == 0x0400 and out["called"] == "$c000"
    assert pr.call_args.args[1] == 0xC000
    assert pr.call_args.args[2] == 1

    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.profile_routine_samples",
               return_value=_profiled([], fired=False)):
        S.attach.return_value = s
        err, out = call_tool("c64_profile", {"routine": "$c000"})
    assert err is True and "never returned" in out["raw"]
    # the hazards the timeout leaves behind, in the only channel MCP has
    assert "timers" in out["raw"] and "I flag" in out["raw"]


def test_profile_samples_reports_min_max_mean_in_lockstep_with_the_cli():
    """CLI/MCP lockstep for `c64 profile --samples`: a bimodal per-frame cost
    (la-galaxia's tick was 10,729 cycles, 31,695 on a repaint) reads as fine
    when sampled once, so the tool has to be able to ask for N."""
    s, _ = _fake_session()
    costs = [10729, 10729, 31695, 10729]
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.profile_routine_samples",
               return_value=_profiled(costs)) as pr:
        S.attach.return_value = s
        err, out = call_tool("c64_profile", {"routine": "$c000", "samples": 4})
    assert err is False
    assert out["samples"] == costs
    assert out["min"] == 10729 and out["max"] == 31695
    assert out["mean"] == round(sum(costs) / 4, 1)
    assert "cycles" not in out          # no single number to mistake for THE cost
    assert pr.call_args.args[2] == 4


def test_profile_valueerror_is_a_tool_error_not_a_crash():
    """The CLI twin of this needed a widened `except`; the tool needs none —
    FastMCP turns any exception into an error result — but that has to be
    pinned, because ops gained a second exception type (the re-raised
    non-handshake ValueError, and the `samples < 1` guard)."""
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.profile_routine_samples",
               side_effect=ValueError("daemon said no")):
        S.attach.return_value = s
        err, out = call_tool("c64_profile", {"routine": "$c000"})
    assert err is True and "daemon said no" in out["raw"]

    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_profile", {"routine": "$c000", "samples": 0})
    assert err is True and "at least 1 sample" in out["raw"]


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


def test_wait_mem_timeout_says_the_machine_was_stopped_throughout():
    """The CLI's `--mem` timeout names this; the tool has to say it too, and
    on the surface agents actually drive. A wait polls memory — it never
    resumes the CPU — so on a machine halted by an earlier c64_until the byte
    cannot change and the full timeout is burned for nothing."""
    s, _ = _fake_session()
    timed_out = {"fired": None, "timeout": 5.0, "last_value": 1}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state", return_value="stopped"), \
         patch("c64lib.mcp_server.wait_for_mem", return_value=dict(timed_out)):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_mem", {"addr": "$0400", "equals": "42"})
    assert err is False, out
    assert out["machine"] == "stopped"
    assert "STOPPED for the whole wait" in out["diagnosis"]
    assert "c64_continue" in out["diagnosis"], "no way out is named"


def test_wait_mem_timeout_on_a_running_machine_carries_no_diagnosis():
    """A machine that ran the whole window genuinely never reached the value;
    pointing the client at c64_continue there would be a wrong answer."""
    s, _ = _fake_session()
    timed_out = {"fired": None, "timeout": 5.0, "last_value": 1}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state", return_value="running"), \
         patch("c64lib.mcp_server.wait_for_mem", return_value=dict(timed_out)):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_mem", {"addr": "$0400", "equals": "42"})
    assert err is False and out["machine"] == "running"
    assert "diagnosis" not in out


def test_wait_mem_timeout_needs_both_samples_stopped():
    """One sample cannot support "stopped for the whole wait" — the same rule
    the CLI applies, so the two surfaces cannot disagree about the same run."""
    s, _ = _fake_session()
    states = iter(["running", "stopped"])
    timed_out = {"fired": None, "timeout": 5.0, "last_value": 1}
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.mcp_server.machine_state",
               side_effect=lambda _s: next(states)), \
         patch("c64lib.mcp_server.wait_for_mem", return_value=dict(timed_out)):
        S.attach.return_value = s
        err, out = call_tool("c64_wait_mem", {"addr": "$0400", "equals": "42"})
    assert err is False and out["machine"] == "running"
    assert "diagnosis" not in out


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
         patch("c64lib.ops.tokenize",
               return_value=tmp_path / "hello.prg") as tok:
        S.attach.return_value = s
        err, out = call_tool("c64_run", {"source": str(bas)})
    assert err is False
    tok.assert_called_once_with(bas.resolve(), bas.resolve().with_suffix(".prg"), "2.0")


def test_run_areas_reach_the_linker(tmp_path):
    """CLI parity with test_cli_basic.test_run_area_reaches_the_linker."""
    from c64lib.build import Area, BuildResult

    src = tmp_path / "g.s"
    src.write_text("; x\n")
    res = BuildResult(prg=tmp_path / "g.prg", labels=tmp_path / "g.lbl")
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S, \
         patch("c64lib.ops.build_asm", return_value=res) as ba:
        S.attach.return_value = s
        err, out = call_tool("c64_run", {"source": str(src),
                                         "areas": ["ENGINE=$4000:$6000"]})
    assert err is False, out
    assert ba.call_args.kwargs["areas"] == [Area("ENGINE", 0x4000, 0x6000)]
    mon.autostart.assert_called_once_with(res.prg.resolve(), run=True)


def test_run_areas_outside_assembly_is_an_error(tmp_path):
    prg = tmp_path / "p.prg"
    prg.write_bytes(b"\x01\x08")
    s, mon = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_run", {"source": str(prg),
                                         "areas": ["ENGINE=$4000:$6000"]})
    # same wording as the CLI's: both front ends say it one way
    assert err is True and "--area applies to assembly sources only" in out["raw"]
    mon.autostart.assert_not_called()


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


def test_load_tool_echoes_the_resolved_symbols_path(tmp_path, monkeypatch):
    """The tool registered the RESOLVED label path but echoed the caller's raw
    string, so its payload disagreed both with `c64 load --json` and with what
    the tool had just done."""
    from click.testing import CliRunner

    from c64lib.cli import main
    monkeypatch.chdir(tmp_path)
    prg = tmp_path / "p.prg"
    prg.write_bytes(b"\x01\x08")
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:040d .start\n")
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_load", {"prg": "p.prg", "symbols": "p.lbl"})
    assert err is False
    assert out["symbols"] == str(lbl.resolve())
    s.set_labels_path.assert_called_once_with(str(lbl.resolve()))
    cli_s, _ = _fake_session()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = cli_s
        r = CliRunner().invoke(main, ["--json", "load", "p.prg",
                                      "--symbols", "p.lbl"])
    assert r.exit_code == 0, r.output
    assert out == json.loads(r.output)


def test_load_records_loaded_program(tmp_path):
    # without this the session forgets what it is running, and c64_status
    # cannot warn that the source has moved on since the load
    prg = tmp_path / "p.prg"
    prg.write_bytes(b"\x01\x08")
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_load", {"prg": str(prg)})
    assert err is False
    s.record_loaded.assert_called_once_with(prg.resolve(), [prg.resolve()])


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


def test_disk_boot_registers_a_sibling_label_file(tmp_path):
    """CLI parity with test_cli_disk.test_disk_boot_registers_a_sibling_label_file:
    a `t.lbl` beside `t.d64` is registered on the session and echoed as
    `symbols`, so an MCP client gets symbol lookups without a second call."""
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    lbl = tmp_path / "t.lbl"
    lbl.write_text("al C:0824 .mainloop\n")
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_disk_boot", {"image": str(img)})
    assert err is False and out["symbols"] == str(lbl)
    s.set_labels_path.assert_called_once_with(str(lbl))


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
         patch("c64lib.ops.rom_labels", return_value={"CHROUT": 0xFFD2}):
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


def test_basic_tokenize_defaults_output_beside_source(tmp_path):
    """The MCP twin of `c64 basic tokenize`: same default output path (SOURCE
    with a .prg suffix) and the same model-selected BASIC version."""
    src = tmp_path / "game.bas"
    src.write_text('10 print "hi"\n')
    out = tmp_path / "game.prg"
    with patch("c64lib.mcp_server.tokenize", return_value=out) as tok:
        is_error, data = call_tool("c64_basic_tokenize", {"source": str(src)})
    assert not is_error, data
    assert data == {"prg": str(out)}
    tok.assert_called_once_with(src, out, "2.0")


def test_basic_tokenize_honours_an_explicit_output(tmp_path):
    src = tmp_path / "game.bas"
    src.write_text('10 print "hi"\n')
    out = tmp_path / "elsewhere.prg"
    with patch("c64lib.mcp_server.tokenize", return_value=out) as tok:
        is_error, data = call_tool(
            "c64_basic_tokenize", {"source": str(src), "output": str(out)})
    assert not is_error, data
    assert data == {"prg": str(out)}
    tok.assert_called_once_with(src, out, "2.0")


def test_basic_detokenize_returns_listing(tmp_path):
    """The MCP twin of `c64 basic detokenize` — the inverse, same payload."""
    prg = tmp_path / "game.prg"
    prg.write_bytes(b"\x01\x08")
    with patch("c64lib.mcp_server.detokenize", return_value='10 print "hi"\n') as det:
        is_error, data = call_tool("c64_basic_detokenize", {"prg": str(prg)})
    assert not is_error, data
    assert data == {"listing": '10 print "hi"\n'}
    det.assert_called_once_with(prg, "2.0")


# --- sprite encode ----------------------------------------------------------

def _sheet(n: int = 1) -> str:
    """n blank-line-separated blocks of 21 all-background multicolor rows."""
    return "\n".join([("." * 12 + "\n") * 21] * n)


def test_sprite_encode_returns_bytes_and_rendering(tmp_path):
    """The MCP twin of `c64 sprite encode`: the CLI's --json `sprites` plus
    the rendering the CLI prints, since MCP has no stdout to print it to."""
    from c64lib.sprites import encode_sheet, render_sheet
    src = tmp_path / "two.txt"
    src.write_text(_sheet(2))
    err, out = call_tool("c64_sprite_encode", {"file": str(src)})
    assert err is False, out
    sprites = encode_sheet(src.read_text())
    assert out["sprites"] == [list(data) for data in sprites]
    assert len(out["sprites"]) == 2 and len(out["sprites"][0]) == 63
    assert out["rendered"] == render_sheet(sprites)


def test_sprite_encode_hires_and_basic_numbering(tmp_path):
    """hires flips multicolor off (24-char rows), and start_line numbers the
    basic rows with the same run-on numbering the CLI emits."""
    src = tmp_path / "hires.txt"
    src.write_text(("#" * 24 + "\n") * 21)      # 24 chars/row: hires only
    err, out = call_tool("c64_sprite_encode",
                         {"file": str(src), "hires": True, "fmt": "basic",
                          "start_line": 1000})
    assert err is False, out
    assert out["sprites"] == [[255] * 63]
    assert out["rendered"].splitlines()[0] == "1000 data 255,255,255"


def test_sprite_encode_start_line_needs_basic_format(tmp_path):
    src = tmp_path / "sprite.txt"
    src.write_text(_sheet())
    err, out = call_tool("c64_sprite_encode",
                         {"file": str(src), "start_line": 100})
    assert err is True
    assert "start_line only applies to fmt='basic'" in str(out)


def test_sprite_encode_background_and_named_blocks_reach_mcp(tmp_path):
    """CLI/MCP lockstep: `--background` and the sheet's `name:`/mode headers
    are the CLI's whole new surface, so the twin has to carry both — and
    report the names it parsed, which is what makes the payload a block map."""
    src = tmp_path / "mixed.txt"
    src.write_text("# a sheet\n\nfighter:hires\n" + ("." * 24 + "\n") * 21
                   + "\ndrone:multicolor\n" + (".123" * 3 + "\n") * 21)
    err, out = call_tool("c64_sprite_encode",
                         {"file": str(src), "background": "."})
    assert err is False, out
    assert out["blocks"] == [{"name": "fighter", "multicolor": False},
                             {"name": "drone", "multicolor": True}]
    assert out["sprites"][0] == [0] * 63              # '.' is background now
    assert out["sprites"][1] == [0b00011011] * 63     # digit == pair value
    assert "; sprite 1 (drone), 24x21 multicolor" in out["rendered"]


def test_sprite_encode_empty_file_is_an_error(tmp_path):
    src = tmp_path / "empty.txt"
    src.write_text("\n   \n")
    err, out = call_tool("c64_sprite_encode", {"file": str(src)})
    assert err is True
    assert f"no sprite art found in {src}" in str(out)


# --- charset encode ---------------------------------------------------------

# One sheet, both modes: the mixed-mode case is the one a per-block override
# exists for, so it is what the tool is tested on.
_MIXED_SHEET = ("wall:multicolor\n" + ".123\n" * 8 +
                "\nletter:hires\n" + "##......\n" * 8)


def test_charset_encode_returns_glyphs_and_rendering(tmp_path):
    """The MCP twin of `c64 charset encode`: the CLI's --json `glyphs` plus
    the rendering the CLI prints, since MCP has no stdout to print it to."""
    from c64lib.charset import format_glyphs, parse_charset
    src = tmp_path / "chars.txt"
    src.write_text(_MIXED_SHEET)
    err, out = call_tool("c64_charset_encode", {"file": str(src)})
    assert err is False, out
    assert out["glyphs"] == [
        {"name": "wall", "multicolor": True, "bytes": [0b00011011] * 8},
        {"name": "letter", "multicolor": False, "bytes": [0b11000000] * 8},
    ]
    assert out["rendered"] == format_glyphs(parse_charset(_MIXED_SHEET))


def test_charset_encode_label_reaches_mcp(tmp_path):
    """CLI/MCP lockstep for `--label`, including the identifier check — an
    unusable label has to fail here the way it fails there, not assemble
    into a broken include."""
    src = tmp_path / "chars.txt"
    src.write_text(_MIXED_SHEET)
    err, out = call_tool("c64_charset_encode",
                         {"file": str(src), "label": "fontgly"})
    assert err is False, out
    assert "fontgly:" in out["rendered"] and "fontgly_end:" in out["rendered"]
    err, out = call_tool("c64_charset_encode",
                         {"file": str(src), "label": "font gly"})
    assert err is True
    assert "not an assembler identifier" in str(out)


def test_charset_encode_bad_sheet_is_an_error(tmp_path):
    """CharsetError reaches the caller with its message intact — a short
    block names itself and its row count, which is the whole diagnosis."""
    src = tmp_path / "short.txt"
    src.write_text("wall:\n" + ".123\n" * 7)
    err, out = call_tool("c64_charset_encode", {"file": str(src)})
    assert err is True
    assert "glyph 'wall' (ending at line 8) has 7 rows, expected 8" in str(out)


# --- audio score ------------------------------------------------------------

def test_audio_score_summarises_a_score_without_a_session(tmp_path):
    """The MCP twin of `c64 audio score`. It must need no session at all —
    a score is a file, and reading it is what makes it the cheap half of the
    loop."""
    path = tmp_path / "score.yaml"
    path.write_text("voices:\n  1:\n    - {note: E4}\n"
                    "    - {note: A4, frames: 9}\n  3: []\n")
    err, out = call_tool("c64_audio_score", {"file": str(path)})
    assert err is False
    assert out == {
        "voices": {
            # first entry has no `frames`, so it counts as an entry and adds
            # nothing to the frame total — the two numbers disagreeing is
            # information, not an error
            "1": {"entries": 2, "frames": 9, "first": "E4", "last": "A4"},
            "3": {"entries": 0, "frames": 0, "first": None, "last": None},
        },
        "entries": 2,
        "frames": 9,
    }


def test_audio_score_reports_a_voice_the_sid_does_not_have(tmp_path):
    path = tmp_path / "score.yaml"
    path.write_text("voices:\n  4: []\n")
    err, out = call_tool("c64_audio_score", {"file": str(path)})
    assert err is True
    assert "voice 4" in str(out)


@pytest.mark.parametrize("tool,what", [("c64_sprite_encode", "sprite sheet"),
                                       ("c64_charset_encode", "charset sheet")])
def test_encoders_report_a_file_they_cannot_decode(tmp_path, tool, what):
    """CLI/MCP lockstep on the message. FastMCP already turns any raise into
    a tool error, so this side never had the CLI's traceback — but a raw
    `UnicodeDecodeError` says only which byte offset failed, and a caller
    that handed a .prg to an ASCII-art encoder needs to be told which of the
    paths it passed was the wrong one."""
    binary = tmp_path / "blob.bin"
    binary.write_bytes(bytes(range(256)))
    err, out = call_tool(tool, {"file": str(binary)})
    assert err is True
    assert f"cannot read {what} {binary}" in str(out)
