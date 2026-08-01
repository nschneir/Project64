import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main
from c64lib.monitor import StopInfo


def _fake(labels=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", labels
    fake.socket = None
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def _labels_file(tmp_path):
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:040d .start\nal C:040f .loop\n")
    return str(lbl)


def test_step_leaves_stopped_and_annotates(tmp_path):
    fake, mon = _fake(labels=_labels_file(tmp_path))
    mon.step.return_value = {"PC": 0x0411, "A": 0}
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "step", "2"])
    assert r.exit_code == 0, r.output
    mon.step.assert_called_once_with(2, over=False)
    out = json.loads(r.output)
    assert out["registers"]["PC"] == 0x0411
    assert out["pc_symbol"] == "loop+2"
    mon.resume.assert_not_called()      # stays stopped


def test_step_over_flag():
    fake, mon = _fake()
    mon.step.return_value = {"PC": 0x0410}
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["step", "--over"])
    assert r.exit_code == 0
    mon.step.assert_called_once_with(1, over=True)


def test_finish():
    fake, mon = _fake()
    mon.finish.return_value = {"PC": 0x1234}
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["finish"])
    assert r.exit_code == 0
    mon.finish.assert_called_once()
    mon.resume.assert_not_called()


def test_continue_resumes():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["continue"])
    assert r.exit_code == 0
    mon.resume.assert_called_once()


def test_until_symbol(tmp_path):
    fake, mon = _fake(labels=_labels_file(tmp_path))
    from c64lib.protocol import CP_EXEC, Checkpoint
    mon.checkpoint_set.return_value = Checkpoint(
        number=9, hit=False, start=0x040F, end=0x040F, stop=True, enabled=True,
        op=CP_EXEC, temporary=False, hit_count=0, ignore_count=0,
        has_condition=False, memspace=0)
    mon.wait_for_stop.return_value = StopInfo(pc=0x040F, checkpoint=9)
    mon.registers.return_value = {"PC": 0x040F}
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "until", "loop"])
    assert r.exit_code == 0, r.output
    mon.checkpoint_set.assert_called_once_with(0x040F, op=CP_EXEC, temporary=False)
    mon.checkpoint_delete.assert_called_once_with(9)
    mon.resume.assert_called_once()     # resumed to run TO the target
    assert json.loads(r.output)["pc_symbol"] == "loop"
    assert json.loads(r.output)["count"] == 1


def test_until_timeout_fails():
    fake, mon = _fake()
    from c64lib.protocol import CP_EXEC, Checkpoint
    mon.checkpoint_set.return_value = Checkpoint(
        number=9, hit=False, start=0x2000, end=0x2000, stop=True, enabled=True,
        op=CP_EXEC, temporary=True, hit_count=0, ignore_count=0,
        has_condition=False, memspace=0)
    mon.wait_for_stop.return_value = None
    mon.checkpoint_list.return_value = []
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "until", "$2000", "--timeout", "1"])
    assert r.exit_code == 1
    assert "timeout" in json.loads(r.output)["error"].lower()


def test_reg_pc_annotation(tmp_path):
    fake, mon = _fake(labels=_labels_file(tmp_path))
    mon.registers.return_value = {"PC": 0x040D, "A": 0x2A}
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "reg"])
    out = json.loads(r.output)
    assert out["pc_symbol"] == "start"


def test_until_count(tmp_path):
    fake, mon = _fake(labels=_labels_file(tmp_path))
    from c64lib.protocol import CP_EXEC, Checkpoint
    mon.checkpoint_set.return_value = Checkpoint(
        number=4, hit=False, start=0x040F, end=0x040F, stop=True, enabled=True,
        op=CP_EXEC, temporary=False, hit_count=0, ignore_count=0,
        has_condition=False, memspace=0)
    mon.wait_for_stop.side_effect = [StopInfo(pc=0x040F, checkpoint=4)] * 3
    mon.registers.return_value = {"PC": 0x040F}
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "until", "loop", "--count", "3"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["count"] == 3 and out["stopped"] is True
    assert mon.resume.call_count == 3          # one per frame
    mon.checkpoint_delete.assert_called_once_with(4)


def test_until_timeout_reports_progress():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.run_until",
               return_value={"registers": None, "reached": 1}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["until", "$040d", "--count", "3",
                                      "--timeout", "0.1"])
    assert r.exit_code == 1 and "1/3" in r.output


def test_until_timeout_is_loud():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.run_until",
               return_value={"registers": None, "reached": 1, "count": 3}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "until", "$040d",
                                      "--count", "3", "--timeout", "0.1"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["machine"] == "running" and out["checkpoint_removed"] is True
    assert out["reached"] == 1 and out["count"] == 3
    assert "left RUNNING" in out["error"] and "branch away" in out["error"]


def test_call_command_invokes_routine(tmp_path):
    import json as _j
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:2000 .sndinit\n")
    fake, mon = _fake(labels=str(lbl))
    fired = {"fired": True, "registers": {"PC": 0x0400, "A": 42, "X": 0},
             "trap": 0x0400}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.call_routine", return_value=fired) as cr:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "call", "sndinit", "--a", "5"])
    assert r.exit_code == 0, r.output
    assert cr.call_args.args[1] == 0x2000
    assert cr.call_args.kwargs["a"] == 5
    out = _j.loads(r.output)
    assert out["registers"]["A"] == 42 and out["stopped"] is True


def test_call_bad_register_value_is_a_clean_error():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["call", "$C000", "--x", "nope"])
    assert r.exit_code == 1, r.output
    assert "Traceback" not in r.output
    assert "nope" in r.output


def test_call_command_timeout_fails():
    fake, mon = _fake()
    out = {"fired": False, "registers": None, "trap": 0x0400}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.call_routine", return_value=out):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["call", "$2000", "--timeout", "1"])
    assert r.exit_code == 1
    assert "never returned" in r.output


def test_profile_reports_cycles():
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine",
               return_value={"fired": True, "cycles": 396,
                             "registers": {"PC": 0x0400}, "trap": 0x0400}) as pr, \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "profile", "$C000"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["cycles"] == 396 and out["irq_masked"] is True
    pr.assert_called_once()


def test_profile_with_irq_flags_the_payload():
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine",
               return_value={"fired": True, "cycles": 1695,
                             "registers": {"PC": 0x0400}, "trap": 0x0400}) as pr, \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "profile", "$C000", "--with-irq"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["irq_masked"] is False and out["cycles"] == 1695
    assert pr.call_args.kwargs["with_irq"] is True


def test_profile_timeout_is_a_clean_failure():
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine",
               return_value={"fired": False, "cycles": None,
                             "registers": None, "trap": 0x0400}), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["profile", "$C000"])
    assert r.exit_code == 1
    assert "never returned" in r.output
