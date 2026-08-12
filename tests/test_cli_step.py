import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main
from c64lib.monitor import StopInfo
from c64lib.ops import RUNAWAY_ROUTINE, profile_hazard


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


def test_profile_reports_cycles():
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine_samples",
               return_value=_profiled([396])) as pr, \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "profile", "$C000"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["cycles"] == 396 and out["irq_masked"] is True
    pr.assert_called_once()
    assert pr.call_args.args[2] == 1                # one sample by default


def test_profile_with_irq_flags_the_payload():
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine_samples",
               return_value=_profiled([1695])) as pr, \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "profile", "$C000", "--with-irq"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["irq_masked"] is False and out["cycles"] == 1695
    assert pr.call_args.kwargs["with_irq"] is True


def test_profile_samples_reports_min_max_mean():
    """la-galaxia's tick: 10,729 cycles ordinarily, 31,695 on a repaint. One
    sample called that fine 27 frames in 32 — the spread is the finding, so
    it has to reach both the JSON and the human line."""
    fake, mon = _fake()
    costs = [10729, 10729, 31695, 10729]
    with patch("c64lib.cli.profile_routine_samples",
               return_value=_profiled(costs)) as pr, \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "profile", "$C000",
                                      "--samples", "4"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["samples"] == costs
    assert out["min"] == 10729 and out["max"] == 31695
    assert out["mean"] == round(sum(costs) / 4, 1) and out["count"] == 4
    assert pr.call_args.args[2] == 4

    with patch("c64lib.cli.profile_routine_samples",
               return_value=_profiled(costs)), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["profile", "$C000", "--samples", "4"])
    assert r.exit_code == 0, r.output
    assert "10729" in r.output and "31695" in r.output and "4 arrivals" in r.output


def test_profile_rejects_a_sample_count_below_one():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["profile", "$C000", "--samples", "0"])
    assert r.exit_code == 1
    assert isinstance(r.exception, SystemExit)
    assert "--samples" in r.output


def test_profile_timeout_is_a_clean_failure():
    """The timeout message has to name the state it left behind: the CIA#2
    timers are still running and the I flag is still masked, and neither can
    be undone with the machine running."""
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine_samples",
               return_value=_profiled([], fired=False)), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["profile", "$C000"])
    assert r.exit_code == 1
    assert "never returned" in r.output
    assert "timers" in r.output and "I flag" in r.output
    assert "reg set FL" in r.output


def test_profile_samples_timeout_reports_how_many_it_priced():
    fake, mon = _fake()
    partial = _profiled([10729, 31695], fired=False)
    partial["count"] = 5
    with patch("c64lib.cli.profile_routine_samples", return_value=partial), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "profile", "$C000",
                                      "--samples", "5"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert "2/5" in out["error"]
    assert out["machine"] == "running" and out["timers_running"] is True
    assert out["samples"] == [10729, 31695] and out["reached"] == 2


def test_profile_with_irq_timeout_does_not_blame_the_i_flag():
    """--with-irq never touched the I flag, so a timeout must not send the
    caller off to clear a bit profile did not set."""
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine_samples",
               return_value=_profiled([], fired=False)), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["profile", "$C000", "--with-irq"])
    assert r.exit_code == 1
    assert "timers" in r.output and "I flag" not in r.output


def test_profile_impossible_zero_count_is_a_clean_failure():
    """profile raises RuntimeError when the timers never moved; the CLI must
    turn that into a message, not a traceback."""
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine_samples",
               side_effect=RuntimeError(
                   "measured 0 raw cycles ... never reached the chip model")), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["profile", "$C000"])
    assert r.exit_code == 1
    assert isinstance(r.exception, SystemExit)      # fail(), not a traceback
    assert "chip model" in r.output


def test_profile_daemon_side_valueerror_is_a_message_not_a_traceback():
    """The daemon path re-raises any ValueError that is not the old-daemon
    handshake (falling back would re-run the routine), so `profile` has a
    second exception type to report — and it must not claim to know where
    the machine stopped, the way the zero-raw RuntimeError can."""
    fake, mon = _fake()
    with patch("c64lib.cli.profile_routine_samples",
               side_effect=ValueError("daemon said no")), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "profile", "$C000"])
    assert r.exit_code == 1
    assert isinstance(r.exception, SystemExit)      # fail(), not a traceback
    out = json.loads(r.output)
    assert "daemon said no" in out["error"]
    assert "machine" not in out


def test_call_and_profile_timeouts_share_one_runaway_clause():
    """The clause names no command of its own — unlike the `until` and
    `key hold` timeout prose, each of which names a companion verb the other
    front end spells differently — so the four messages that carry it (both
    commands here, both tools over MCP) read it from one constant.
    """
    fake, _ = _fake()
    never = {"fired": False, "registers": None, "trap": 0x0400}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.call_routine", return_value=never), \
         patch("c64lib.cli.profile_routine_samples",
               return_value=_profiled([], fired=False)):
        S.attach.return_value = fake
        call_r = CliRunner().invoke(main, ["--json", "call", "$2000"])
        profile_r = CliRunner().invoke(main, ["--json", "profile", "$C000"])
    assert call_r.exit_code == 1 and profile_r.exit_code == 1
    # Pinned literally as well as by reference: the point of the extraction is
    # that the words do not change, so a reworded constant is a test failure.
    assert RUNAWAY_ROUTINE == ("(runaway routine? check the address is a "
                               "subroutine ending in RTS)")
    for r in (call_r, profile_r):
        assert RUNAWAY_ROUTINE in json.loads(r.output)["error"]


def test_profile_hazard_is_one_sentence_with_a_per_front_end_remedy():
    """What a timed-out profile leaves behind is a library fact — the CIA#2
    timers still running, and the I flag still masked unless --with-irq — so
    only the way out is each front end's own to spell."""
    assert profile_hazard(True, "ignored") == "CIA#2 timers A/B are left RUNNING"
    assert profile_hazard(False, "X is cleared") == (
        "CIA#2 timers A/B are left RUNNING and the I flag is left masked — "
        "the jiffy clock and keyboard stay dead until X is cleared")

    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.profile_routine_samples",
               return_value=_profiled([], fired=False)):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "profile", "$C000"])
    assert r.exit_code == 1
    assert json.loads(r.output)["error"].endswith(
        profile_hazard(False, "`c64 reg set FL ...` clears it "
                              "(or the session restarts)") + ".")


def test_profile_sample_guard_answers_before_it_needs_a_session(tmp_path,
                                                                monkeypatch):
    """Why the CLI keeps a `--samples` guard that `ops.profile_routine_samples`
    would also raise for: this one fires ahead of `attach`, so an unusable
    argument is reported as an unusable argument instead of as "no session".
    Delete it and the command answers `--samples 0` by demanding an emulator
    first. The ops guard is not redundant either — it is the only one
    `c64_profile` has (tests/test_mcp_tools.py pins that).
    """
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    r = CliRunner().invoke(main, ["--json", "profile", "$C000",
                                  "--samples", "0"])
    assert r.exit_code == 1
    assert json.loads(r.output)["error"] == (
        "profile: --samples must be at least 1 (got 0)")
