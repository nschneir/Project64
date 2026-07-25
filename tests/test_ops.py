from unittest.mock import Mock, patch

import pytest

from c64lib import ops
from c64lib.monitor import StopInfo
from c64lib.ops import parse_number, parse_ref, run_until, wait_for_break, wait_for_text
from c64lib.protocol import CP_EXEC, Checkpoint


def _fake_session():
    s = Mock()
    s.profile.screen_cols = 40
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def test_parse_number_and_ref():
    assert parse_number("$0400") == 0x0400
    assert parse_ref({}, "0x1000") == 0x1000
    assert parse_ref({"start": 0x040D}, "start") == 0x040D
    with pytest.raises(KeyError):
        parse_ref({}, "nosuch")


def test_parse_ref_symbol_plus_offset():
    labels = {"alienx": 0x1000}
    assert parse_ref(labels, "alienX+49") == 0x1031
    assert parse_ref(labels, "alienx+$10") == 0x1010
    assert parse_ref(labels, "alienx-1") == 0x0FFF


def test_parse_ref_number_plus_offset():
    assert parse_ref({}, "$0400+40") == 0x0428
    assert parse_ref({}, "$0400+$28") == 0x0428


def test_parse_ref_hyphenated_symbol_still_resolves():
    # A '-' split must not break symbols that merely contain a dash.
    labels = {"loop-top": 0x2000}
    assert parse_ref(labels, "loop-top") == 0x2000


def test_parse_ref_rowcol():
    assert parse_ref({}, "@23,18", screen_base=0x0400, screen_width=40) == 0x07AA
    assert parse_ref({}, "@0,0", screen_base=0x0400, screen_width=40) == 0x0400
    assert parse_ref({}, "@1,33", screen_base=0x0400, screen_width=80) == 0x0471


def test_parse_ref_rowcol_without_geometry_raises():
    with pytest.raises(ValueError, match="session"):
        parse_ref({}, "@1,2")


def test_parse_ref_rowcol_out_of_range():
    with pytest.raises(ValueError, match="row"):
        parse_ref({}, "@25,0", screen_base=0x0400, screen_width=40)
    with pytest.raises(ValueError, match="col"):
        parse_ref({}, "@0,40", screen_base=0x0400, screen_width=40)


def test_wait_for_text_fires_and_times_out():
    s, mon = _fake_session()
    with patch("c64lib.ops.read_screen_text", side_effect=["A", "B READY."]):
        out = wait_for_text(s, "READY.", timeout=5)
    assert out["fired"] == "text"

    s2, _ = _fake_session()
    with patch("c64lib.ops.read_screen_text", return_value="STUCK"), \
         patch("c64lib.ops.time.sleep"):
        out2 = wait_for_text(s2, "Never", timeout=0.3)
    assert out2["fired"] is None and "STUCK" in out2["screen"]


def test_wait_for_text_since_ignores_the_existing_occurrence(monkeypatch):
    # Discriminates a correct baseline (1, the pre-existing occurrence)
    # from a broken one (e.g. always 0): record which read triggered the
    # fire. The third screen is the first with a NEW occurrence (count 2 >
    # baseline 1); a baseline stuck at 0 would fire on the second read
    # instead (count 1 > 0), consuming only two reads.
    screens = ["TOO HIGH", "TOO HIGH", "TOO HIGH\nTOO HIGH"]
    calls = []

    def fake_screen(s):
        calls.append(screens[len(calls)])
        return calls[-1]

    monkeypatch.setattr(ops, "_screen", fake_screen)
    monkeypatch.setattr(ops.time, "sleep", lambda _: None)
    out = ops.wait_for_text(object(), "TOO HIGH", timeout=5, since=True)
    assert out["fired"] == "text"
    assert len(calls) == 3, f"fired on the wrong read: {calls}"


def test_wait_for_text_checks_the_screen_read_on_the_final_poll(monkeypatch):
    """Regression: a fresh read taken on the last iteration before the
    deadline expires must be checked before giving up. A prior shape
    stored that read into `last` but exited the loop before testing it,
    so a genuine match appearing only on the final poll was silently
    dropped (returned fired=None with the match sitting in out["screen"]).
    """
    clocks = iter([0.0,   # start
                   0.05,  # while-condition check: True, loop entered
                   0.2])  # OLD shape: re-check after the fresh read ->
                          # False, deadline passed, loop exits without
                          # testing the fresh read.
                          # NEW shape: never reached here — it returns
                          # right after checking the fresh read, using
                          # this same value for the elapsed calculation.
    monkeypatch.setattr(ops.time, "monotonic", lambda: next(clocks))
    screens = iter(["", "TARGET APPEARS"])
    monkeypatch.setattr(ops, "_screen", lambda s: next(screens))
    monkeypatch.setattr(ops.time, "sleep", lambda _: None)
    out = ops.wait_for_text(object(), "TARGET", timeout=0.1)
    assert out["fired"] == "text"


def test_wait_for_text_without_since_matches_stale_text(monkeypatch):
    monkeypatch.setattr(ops, "_screen", lambda s: "TOO HIGH")
    monkeypatch.setattr(ops.time, "sleep", lambda _: None)
    out = ops.wait_for_text(object(), "TOO HIGH", timeout=5)
    assert out["fired"] == "text"


def test_wait_for_break_already_hit():
    s, mon = _fake_session()
    mon.checkpoint_list.return_value = [Checkpoint(
        number=3, hit=True, start=0x040D, end=0x040D, stop=True, enabled=True,
        op=CP_EXEC, temporary=False, hit_count=1, ignore_count=0,
        has_condition=False, memspace=0)]
    mon.registers.return_value = {"PC": 0x040D}
    out = wait_for_break(s, timeout=1)
    assert out["fired"] == "break" and out["checkpoint"] == 3
    mon.wait_for_stop.assert_not_called()


def test_wait_for_break_listens():
    s, mon = _fake_session()
    mon.checkpoint_list.return_value = []
    mon.wait_for_stop.return_value = StopInfo(pc=0x1234, checkpoint=7)
    mon.registers.return_value = {"PC": 0x1234}
    out = wait_for_break(s, timeout=1)
    assert out["checkpoint"] == 7 and out["pc"] == 0x1234
    mon.resume.assert_called_once()


def test_wait_for_break_flag_poll_catches_missed_event():
    """The STOPPED event can be lost to the connect-stop/resume race (demo-04
    flake). The hit flag in CHECKPOINT_LIST is durable — polling it must
    catch the halt even when no event is ever seen."""
    s, mon = _fake_session()
    ck_no = Checkpoint(number=3, hit=False, start=0x040D, end=0x040D, stop=True,
                       enabled=True, op=CP_EXEC, temporary=False, hit_count=0,
                       ignore_count=0, has_condition=False, memspace=0)
    ck_hit = Checkpoint(number=3, hit=True, start=0x040D, end=0x040D, stop=True,
                        enabled=True, op=CP_EXEC, temporary=False, hit_count=1,
                        ignore_count=0, has_condition=False, memspace=0)
    mon.checkpoint_list.side_effect = [[ck_no], [ck_hit]]
    mon.wait_for_stop.return_value = None      # the event was lost
    mon.registers.return_value = {"PC": 0x040D}
    out = wait_for_break(s, timeout=5)
    assert out["fired"] == "break" and out["checkpoint"] == 3


def _ck7(hit=False, hit_count=0):
    return Checkpoint(number=7, hit=hit, start=0x1000, end=0x1000, stop=True,
                      enabled=True, op=CP_EXEC, temporary=False,
                      hit_count=hit_count, ignore_count=0,
                      has_condition=False, memspace=0)


def test_run_until_count_uses_persistent_checkpoint():
    s, mon = _fake_session()
    mon.checkpoint_set.return_value = _ck7()
    mon.wait_for_stop.side_effect = [StopInfo(pc=0x1000, checkpoint=7)] * 2
    mon.registers.return_value = {"PC": 0x1000}
    out = run_until(s, 0x1000, timeout=5, count=2)
    assert out["registers"]["PC"] == 0x1000
    assert out["reached"] == 2 and out["count"] == 2
    mon.checkpoint_set.assert_called_once_with(0x1000, op=CP_EXEC, temporary=False)
    mon.checkpoint_delete.assert_called_once_with(7)
    assert mon.resume.call_count == 2          # exactly one resume per arrival


def test_run_until_timeout_cleans_up_checkpoint():
    s, mon = _fake_session()
    mon.checkpoint_set.return_value = _ck7()
    mon.wait_for_stop.return_value = None
    mon.checkpoint_list.return_value = [_ck7()]      # never hit
    out = run_until(s, 0x1000, timeout=0.3)
    assert out["registers"] is None and out["reached"] == 0 and out["count"] == 1
    mon.checkpoint_delete.assert_called_once_with(7)  # no leaked checkpoint


def test_run_until_delegates_to_daemon_client():
    """With a session daemon the whole count loop is ONE RPC."""
    from c64lib.daemon_client import DaemonMonitorClient
    s = Mock()
    mon = DaemonMonitorClient.__new__(DaemonMonitorClient)  # no socket needed
    mon.run_until = Mock(return_value={"registers": {"PC": 1}, "reached": 4,
                                       "count": 4})
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    out = run_until(s, 0x1000, timeout=9.0, count=4)
    assert out["reached"] == 4
    mon.run_until.assert_called_once_with(0x1000, 9.0, 4)


def test_run_until_falls_back_on_old_daemon():
    """A pre-run_until daemon answers 'unknown daemon method' (ValueError);
    the client-side loop must take over transparently."""
    from c64lib.daemon_client import DaemonMonitorClient
    s = Mock()
    mon = DaemonMonitorClient.__new__(DaemonMonitorClient)
    mon.run_until = Mock(side_effect=ValueError("unknown daemon method 'run_until'"))
    for name in ("checkpoint_set", "wait_for_stop", "registers",
                 "checkpoint_delete", "resume", "checkpoint_list"):
        setattr(mon, name, Mock())
    mon.checkpoint_set.return_value = _ck7()
    mon.wait_for_stop.return_value = StopInfo(pc=0x1000, checkpoint=7)
    mon.registers.return_value = {"PC": 0x1000}
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    out = run_until(s, 0x1000, timeout=5, count=1)
    assert out["reached"] == 1 and out["registers"]["PC"] == 0x1000


def test_key_type_feeds_buffer_and_releases():
    from c64lib.ops import key_type
    s, mon = _fake_session()
    out = key_type(s, "hi\n")
    mon.keyboard_feed.assert_called_once_with(b"HI\r")
    mon.release.assert_called_once()
    assert out == {"typed_chars": 3}


def test_matrix_codes_cover_game_keys():
    from c64lib.ops import MATRIX_CODES
    # spot checks against the published keyboard-matrix table ($CB values)
    assert MATRIX_CODES[" "] == 60
    assert MATRIX_CODES["w"] == 9
    assert MATRIX_CODES["a"] == 10
    assert MATRIX_CODES["\n"] == 1
    for ch in "abcdefghijklmnopqrstuvwxyz0123456789 ":
        assert ch in MATRIX_CODES


def test_key_hold_pokes_cb_before_each_frame():
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    calls = []
    mon.memory_write.side_effect = lambda a, d: calls.append(("poke", a, d))

    def fake_until(*a, **k):
        calls.append(("until",))
        return {"registers": {"PC": 0x0819}, "reached": 1, "count": 1}

    with patch("c64lib.ops.run_until", side_effect=fake_until) as ru:
        out = key_hold(s, "d", 0x0819, frames=3, timeout=9.0)
    assert out["frames"] == 3 and out["registers"] == {"PC": 0x0819}
    assert calls == [("poke", 0xCB, bytes([18])), ("until",)] * 3
    ru.assert_called_with(s, 0x0819, timeout=9.0, count=1)


def test_key_hold_space_alias_and_validation():
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with patch("c64lib.ops.run_until",
               return_value={"registers": {"PC": 1}, "reached": 1, "count": 1}):
        key_hold(s, "space", 0x1000, frames=1)
    mon.memory_write.assert_called_once_with(0xCB, bytes([60]))
    with pytest.raises(ValueError):
        key_hold(s, "dd", 0x1000)
    with pytest.raises(ValueError, match="no matrix code"):
        key_hold(s, "~", 0x1000)


def test_key_hold_timeout_reports_progress():
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with patch("c64lib.ops.run_until",
               side_effect=[{"registers": {"PC": 1}, "reached": 1, "count": 1},
                            {"registers": None, "reached": 0, "count": 1}]):
        out = key_hold(s, "a", 0x1000, frames=5)
    assert out["frames"] == 1 and out["requested"] == 5
    assert out["registers"] is None


def test_session_labels_unreadable_file_returns_empty(tmp_path):
    from c64lib.ops import session_labels
    s = Mock()
    s.labels = str(tmp_path / "gone.lbl")     # a path that does not exist
    assert session_labels(s) == {}


def test_pc_symbol_none_without_labels():
    from c64lib.ops import pc_symbol
    assert pc_symbol({}, {"PC": 0x1234}) is None


def test_wait_for_mem_timeout_returns_last_value():
    from c64lib.ops import wait_for_mem
    s = Mock()
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    mon.memory_read.return_value = b"\x05"
    with patch("c64lib.ops.time.sleep"):
        out = wait_for_mem(s, 0x0400, 0x2A, timeout=0.1)
    assert out["fired"] is None and out["last_value"] == 5


def test_find_bytes_single_and_pattern():
    from c64lib.ops import find_bytes
    mon = Mock()
    mon.memory_read.return_value = b"\x00\x2a\x00\x2a\x2a"
    matches, truncated = find_bytes(mon, 0x0400, 5, b"\x2a")
    assert matches == [0x0401, 0x0403, 0x0404] and truncated is False
    matches, _ = find_bytes(mon, 0x0400, 5, b"\x2a\x2a")
    assert matches == [0x0403]
    mon.memory_read.assert_called_with(0x0400, 5)


def test_find_bytes_limit_truncates():
    from c64lib.ops import find_bytes
    mon = Mock()
    mon.memory_read.return_value = b"\x00" * 10
    matches, truncated = find_bytes(mon, 0, 10, b"\x00", limit=3)
    assert len(matches) == 3 and truncated is True


def test_find_bytes_clamps_to_64k():
    from c64lib.ops import find_bytes
    mon = Mock()
    mon.memory_read.return_value = b"\x01"
    find_bytes(mon, 0xFFFF, 0x100, b"\x01")
    mon.memory_read.assert_called_with(0xFFFF, 1)


def test_clear_checkpoints_filters_by_op():
    from c64lib.ops import clear_checkpoints
    from c64lib.protocol import CP_EXEC, CP_LOAD, CP_STORE
    exec_ck, watch_ck = Mock(number=1, op=CP_EXEC), Mock(number=2, op=CP_LOAD | CP_STORE)
    mon = Mock()
    mon.checkpoint_list.return_value = [exec_ck, watch_ck]
    assert clear_checkpoints(mon, CP_EXEC) == [1]
    mon.checkpoint_delete.assert_called_once_with(1)
    mon.reset_mock()
    mon.checkpoint_list.return_value = [exec_ck, watch_ck]
    assert clear_checkpoints(mon, CP_LOAD | CP_STORE, exclude_mask=CP_EXEC) == [2]
    mon.checkpoint_delete.assert_called_once_with(2)


def test_machine_state_without_daemon_is_unknown():
    from c64lib.ops import machine_state
    s = Mock()
    s.socket = None
    assert machine_state(s) == "unknown"


def test_machine_state_via_daemon():
    from c64lib.ops import machine_state
    s = Mock()
    s.socket = "/tmp/x.sock"
    mon = Mock()
    mon.status.return_value = "stopped"
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    assert machine_state(s) == "stopped"


def test_machine_state_swallows_dead_daemon():
    from c64lib.ops import machine_state
    s = Mock()
    s.socket = "/tmp/x.sock"
    s.monitor.side_effect = ConnectionError("gone")
    assert machine_state(s) == "unknown"


def test_parse_ref_arithmetic_reports_base_symbol():
    # FT3: unknown symbol inside arithmetic names the SYMBOL, not the string
    with pytest.raises(KeyError) as e:
        parse_ref({"tick": 0x33}, "dots+82")
    assert "dots" in str(e.value) and "dots+82" not in str(e.value)
    with pytest.raises(KeyError) as e:
        parse_ref({"tick": 0x33}, "hs_sc+$3")
    assert "hs_sc" in str(e.value) and "hs_sc+$3" not in str(e.value)


def test_parse_ref_whole_string_symbol_still_wins():
    # a label literally named with a hyphen resolves whole when no
    # arithmetic interpretation exists
    assert parse_ref({"self-test": 0x2000}, "self-test") == 0x2000


def _ck_hit(number):
    return Checkpoint(
        number=number, hit=True, start=0x040D, end=0x040D, stop=True,
        enabled=True, op=CP_EXEC, temporary=False, hit_count=1,
        ignore_count=0, has_condition=False, memspace=0)


def test_wait_for_break_number_filter_ignores_other_checkpoints():
    # FT5: a leftover breakpoint (#1) must not satisfy a wait for #4
    s, mon = _fake_session()
    mon.checkpoint_list.side_effect = [[_ck_hit(1)], [_ck_hit(1), _ck_hit(4)]]
    mon.wait_for_stop.return_value = None
    mon.registers.return_value = {"PC": 0x040D}
    out = wait_for_break(s, timeout=2, number=4)
    assert out["fired"] == "break" and out["checkpoint"] == 4


def test_wait_for_break_number_filter_on_event_fast_path():
    s, mon = _fake_session()
    mon.checkpoint_list.side_effect = [[], [], [_ck_hit(4)]]
    mon.wait_for_stop.return_value = StopInfo(pc=0x1234, checkpoint=1)
    mon.registers.return_value = {"PC": 0x040D}
    out = wait_for_break(s, timeout=2, number=4)
    assert out["checkpoint"] == 4      # event for #1 didn't short-circuit


def _call_ck(number=9, addr=0x0400, hit=True):
    return Checkpoint(
        number=number, hit=hit, start=addr, end=addr, stop=True, enabled=True,
        op=CP_EXEC, temporary=False, hit_count=1 if hit else 0,
        ignore_count=0, has_condition=False, memspace=0)


def test_call_routine_pushes_return_and_sets_registers():
    from c64lib.ops import call_routine
    s, mon = _fake_session()
    mon.registers.return_value = {"PC": 0x1234, "SP": 0xFB, "A": 0, "X": 0, "Y": 0}
    mon.checkpoint_set.return_value = _call_ck(hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=9)
    out = call_routine(s, 0x2000, a=5, x=1, y=2, timeout=2)
    # JSR emulation: hi(trap-1) at $0100+SP, lo at $0100+SP-1, SP -= 2
    mon.memory_write.assert_any_call(0x0100 + 0xFB, bytes([0x03]))
    mon.memory_write.assert_any_call(0x0100 + 0xFA, bytes([0xFF]))
    reg_calls = {c.args[0]: c.args[1] for c in mon.set_register.call_args_list}
    assert reg_calls["SP"] == 0xF9
    assert reg_calls["PC"] == 0x2000
    assert reg_calls["A"] == 5 and reg_calls["X"] == 1 and reg_calls["Y"] == 2
    assert out["fired"] is True and out["registers"]["PC"] == 0x1234
    mon.checkpoint_delete.assert_called_once_with(9)


def test_call_routine_registers_optional():
    from c64lib.ops import call_routine
    s, mon = _fake_session()
    mon.registers.return_value = {"PC": 0x1234, "SP": 0xFB, "A": 7}
    mon.checkpoint_set.return_value = _call_ck(hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=9)
    call_routine(s, 0x2000, timeout=2)
    names = [c.args[0] for c in mon.set_register.call_args_list]
    assert "A" not in names and "X" not in names and "Y" not in names


def test_call_routine_timeout_cleans_up():
    from c64lib.ops import call_routine
    s, mon = _fake_session()
    mon.registers.return_value = {"PC": 0x1234, "SP": 0xFB}
    mon.checkpoint_set.return_value = _call_ck(hit=False)
    mon.wait_for_stop.return_value = None
    mon.checkpoint_list.return_value = [_call_ck(hit=False)]
    out = call_routine(s, 0x2000, timeout=0.3)
    assert out["fired"] is False and out["registers"] is None
    mon.checkpoint_delete.assert_called_once_with(9)
    mon.resume.assert_called()          # machine left running on timeout


def test_call_routine_durable_flag_fallback():
    # STOPPED event lost (warp race): the hit flag on the checkpoint decides
    from c64lib.ops import call_routine
    s, mon = _fake_session()
    mon.registers.return_value = {"PC": 0x0400, "SP": 0xF9}
    mon.checkpoint_set.return_value = _call_ck(hit=False)
    mon.wait_for_stop.return_value = None
    mon.checkpoint_list.return_value = [_call_ck(hit=True)]
    out = call_routine(s, 0x2000, timeout=2)
    assert out["fired"] is True
