import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from c64lib.cli import main
from c64lib.monitor import StopInfo
from c64lib.protocol import CP_EXEC, Checkpoint


def _fake(labels=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", labels
    fake.profile.screen_cols = 40
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_wait_requires_exactly_one_condition():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait"])
        r2 = CliRunner().invoke(main, ["--json", "wait", "--text", "X", "--break"])
    assert r.exit_code == 1 and r2.exit_code == 1


def test_wait_since_rejected_without_text():
    r = CliRunner().invoke(main, ["wait", "--mem", "$1000=1", "--since"])
    assert r.exit_code == 1
    assert "--since only applies to --text" in r.output


def test_wait_text_fires():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.ops.read_screen_text", side_effect=["LOADING", "READY."]):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--text", "READY.", "--timeout", "5"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["fired"] == "text"
    assert mon.release.call_count == 2   # one per poll


def test_wait_text_timeout_includes_screen():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.ops.read_screen_text", return_value="STUCK"), \
         patch("c64lib.ops.time.sleep"):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--text", "NEVER", "--timeout", "0.5"])
    assert r.exit_code == 1
    assert "STUCK" in json.loads(r.output)["error"]


def test_wait_text_since_forwarded_to_wait_for_text():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.wait_for_text",
               return_value={"fired": "text", "elapsed": 0.1}) as wft:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--text", "TOO HIGH",
                                      "--since", "--timeout", "5"])
    assert r.exit_code == 0, r.output
    wft.assert_called_once_with(fake, "TOO HIGH", 5.0, since=True)


def test_wait_mem_fires():
    fake, mon = _fake()
    mon.memory_read.side_effect = [b"\x00", b"\x2a"]
    with patch("c64lib.cli.Session") as S, patch("c64lib.ops.time.sleep"):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--mem", "$1000=42", "--timeout", "5"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["fired"] == "mem"


def test_wait_break_already_hit_returns_immediately(tmp_path):
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:040d .start\n")
    fake, mon = _fake(labels=str(lbl))
    mon.checkpoint_list.return_value = [Checkpoint(
        number=3, hit=True, start=0x040D, end=0x040D, stop=True, enabled=True,
        op=CP_EXEC, temporary=False, hit_count=1, ignore_count=0,
        has_condition=False, memspace=0)]
    mon.registers.return_value = {"PC": 0x040D}
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--break"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["fired"] == "break" and out["checkpoint"] == 3
    assert out["pc_symbol"] == "start"
    mon.wait_for_stop.assert_not_called()


def test_wait_break_listens_for_stop():
    fake, mon = _fake()
    mon.checkpoint_list.return_value = []
    mon.wait_for_stop.return_value = StopInfo(pc=0x1234, checkpoint=7)
    mon.registers.return_value = {"PC": 0x1234}
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--break", "--timeout", "3"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["fired"] == "break" and out["checkpoint"] == 7
    mon.resume.assert_called_once()


def test_wait_text_timeout_shows_last_screen():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.wait_for_text",
               return_value={"fired": None, "timeout": 0.1, "screen": "READY."}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["wait", "--text", "NEVER", "--timeout", "0.1"])
    assert r.exit_code == 1 and "READY." in r.output


def test_wait_mem_malformed_condition():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        # valid addr, missing <op>VALUE -> the "use ADDR<op>VALUE" branch
        r = CliRunner().invoke(main, ["wait", "--mem", "$0400"])
    assert r.exit_code == 1 and "ADDR<op>VALUE" in r.output


def test_wait_mem_comparison_reported_as_a_condition_not_a_symbol():
    """The condition is split before the address is resolved: an operator
    typo must not surface as 'unknown symbol' naming the whole expression."""
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["wait", "--mem", "$0400=~7"])
    assert r.exit_code == 1
    assert "unknown symbol" not in r.output
    assert "bad --mem value" in r.output


def test_wait_mem_inequality_fires_without_hitting_the_value():
    """'>=' catches a counter that never reads exactly the wanted value."""
    fake, mon = _fake()
    mon.memory_read.side_effect = [b"\x05", b"\x19"]      # 5 then 25, never 20
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(
            main, ["--json", "wait", "--mem", "$fb>=20", "--timeout", "5"])
    assert r.exit_code == 0
    assert json.loads(r.output)["fired"] == "mem"


def test_wait_mem_timeout_reports_the_last_value_seen():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.wait_for_mem",
               return_value={"fired": None, "timeout": 0.1, "last_value": 7,
                             "op": "!=", "value": 7}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["wait", "--mem", "$0400!=7",
                                      "--timeout", "0.1"])
    assert r.exit_code == 1 and "last value 7" in r.output


def test_wait_mem_timeout():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.wait_for_mem",
               return_value={"fired": None, "timeout": 0.1, "last_value": 7}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["wait", "--mem", "$0400=42", "--timeout", "0.1"])
    assert r.exit_code == 1 and "timeout" in r.output.lower()


def test_wait_mem_timeout_says_the_machine_was_stopped_throughout():
    """The la-galaxia dogfood lost two minutes and filed a false "the game is
    stuck": `wait --mem` after a `c64 until` polls a byte no CPU is writing.
    The timeout is the only place that can say so."""
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="stopped"), \
         patch("c64lib.cli.wait_for_mem",
               return_value={"fired": None, "timeout": 0.1, "last_value": 1}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--mem", "$1000=3",
                                      "--timeout", "0.1"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["machine"] == "stopped"
    assert "STOPPED for the whole wait" in out["error"]
    assert "c64 continue" in out["error"]


def test_wait_mem_timeout_on_a_running_machine_makes_no_such_claim():
    """The other half of the same claim: a machine that ran the whole window
    genuinely never reached the value, and saying "stopped" there would send
    the reader to `c64 continue` for nothing."""
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="running"), \
         patch("c64lib.cli.wait_for_mem",
               return_value={"fired": None, "timeout": 0.1, "last_value": 1}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--mem", "$1000=3",
                                      "--timeout", "0.1"])
    out = json.loads(r.output)
    assert r.exit_code == 1 and out["machine"] == "running"
    assert "STOPPED" not in out["error"]


def test_wait_mem_timeout_needs_both_samples_stopped():
    """One sample cannot support "stopped for the whole wait": a machine
    stopped only at the end was running for part of the window."""
    fake, _ = _fake()
    states = iter(["running", "stopped"])
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", side_effect=lambda _s: next(states)), \
         patch("c64lib.cli.wait_for_mem",
               return_value={"fired": None, "timeout": 0.1, "last_value": 1}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--mem", "$1000=3",
                                      "--timeout", "0.1"])
    out = json.loads(r.output)
    assert r.exit_code == 1 and out["machine"] == "running"
    assert "STOPPED" not in out["error"]


def test_wait_text_timeout_says_the_machine_was_stopped():
    """Same footgun as `--mem`, one flag over: a wait polls the screen and
    never resumes the CPU, so a machine halted for the whole window could
    print nothing. Claiming "running" there sends the reader hunting a bug in
    the program instead of to `c64 continue`."""
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="stopped"), \
         patch("c64lib.cli.wait_for_text",
               return_value={"fired": None, "timeout": 0.1, "screen": "READY."}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--text", "NEVER",
                                      "--timeout", "0.1"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["machine"] == "stopped"
    assert "STOPPED for the whole wait" in out["error"]
    assert "c64 continue" in out["error"]


def test_wait_idle_timeout_says_the_machine_was_stopped():
    """A stopped machine cannot reach direct mode either — and it is not a
    wedge, so the wedged-machine playbook (sample `reg` a second apart, then
    `step`) would have the reader watch a PC that cannot move."""
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="stopped"), \
         patch("c64lib.cli.wait_for_idle",
               return_value={"fired": None, "timeout": 0.1,
                             "last_pcs": [0x033C, 0x0340, 0x033C]}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--idle",
                                      "--timeout", "0.1"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["machine"] == "stopped"
    assert "STOPPED for the whole wait" in out["error"]
    assert "c64 continue" in out["error"]
    assert "6502-debugging" not in out["error"], \
        "a stopped machine is not a wedge; the playbook is the wrong advice"


@pytest.mark.parametrize("states", [["running", "stopped"], ["stopped", "running"]])
def test_wait_idle_timeout_needs_both_samples_stopped(states):
    """One sample cannot support "stopped for the whole wait". Both orderings
    are exercised because only one of them reads the second sample: a machine
    already running at the start short-circuits the comparison, so it is the
    one stopped only at the START, running again by the end, that proves the
    second sample is what decides."""
    fake, _ = _fake()
    seen = iter(states)
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", side_effect=lambda _s: next(seen)), \
         patch("c64lib.cli.wait_for_idle",
               return_value={"fired": None, "timeout": 0.1,
                             "last_pcs": [0x033C]}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--idle",
                                      "--timeout", "0.1"])
    out = json.loads(r.output)
    assert r.exit_code == 1 and out["machine"] == "running"
    assert "STOPPED" not in out["error"]


def test_wait_break_timeout_says_machine_running():
    """`--break` is the one arm that keeps the unconditional claim, and it is
    a true one: it resumes the machine itself and its timeout path resumes it
    again, so there is no window a "stopped the whole time" diagnosis could
    describe. Deliberately excluded from the two-sample treatment."""
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.wait_for_break", return_value={"fired": None}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--break",
                                      "--timeout", "0.1"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["machine"] == "running"
    assert "left running" in out["error"] and "remain set" in out["error"]


def test_wait_text_timeout_carries_machine_field():
    """The other half of the stopped claim: a machine that ran the whole
    window genuinely never printed the text, and pointing the reader at
    `c64 continue` there would be a wrong answer."""
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="running"), \
         patch("c64lib.cli.wait_for_text",
               return_value={"fired": None, "timeout": 0.1, "screen": "READY."}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--text", "X",
                                      "--timeout", "0.1"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["machine"] == "running"
    assert "STOPPED" not in out["error"]


def test_wait_break_with_id_filter():
    fake, _ = _fake()
    fired = {"fired": "break", "checkpoint": 4, "pc": 0x040D,
             "registers": {"PC": 0x040D}, "elapsed": 0.1}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.wait_for_break", return_value=fired) as w:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--break", "4"])
    assert r.exit_code == 0, r.output
    assert w.call_args.kwargs.get("number") == 4
    assert json.loads(r.output)["checkpoint"] == 4


def test_wait_break_bare_still_works():
    fake, _ = _fake()
    fired = {"fired": "break", "checkpoint": 1, "pc": 0x040D,
             "registers": {"PC": 0x040D}, "elapsed": 0.1}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.wait_for_break", return_value=fired) as w:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--break"])
    assert r.exit_code == 0, r.output
    assert w.call_args.kwargs.get("number") is None


def test_wait_break_non_numeric_id_fails_cleanly():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--break", "abc"])
    assert r.exit_code == 1
    assert r.exception is None or isinstance(r.exception, SystemExit)
    assert "checkpoint id" in json.loads(r.output)["error"]


def test_wait_idle_joins_the_exactly_one_check():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--idle",
                                      "--text", "X"])
    assert r.exit_code == 1
    assert "--idle" in json.loads(r.output)["error"]


def test_wait_idle_fires():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.wait_for_idle",
               return_value={"fired": "idle", "elapsed": 0.4}) as wfi:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--idle",
                                      "--timeout", "5"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["fired"] == "idle"
    wfi.assert_called_once_with(fake, 5.0)


def test_wait_idle_timeout_points_at_the_wedge_playbook():
    """On a machine that was RUNNING the timeout IS the wedge detector: it has
    to say the machine may be stuck and name the playbook that takes it
    apart."""
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="running"), \
         patch("c64lib.cli.wait_for_idle",
               return_value={"fired": None, "timeout": 0.1,
                             "last_pcs": [0x033C, 0x0340, 0x033C]}):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "wait", "--idle",
                                      "--timeout", "0.1"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert out["machine"] == "running"
    err = out["error"]
    assert "wedged" in err and "6502-debugging" in err
    assert "$033c" in err            # the PCs it was last seen at
