import time
from itertools import chain, repeat
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from c64lib.testing import TestError, run_test


def _fake_session():
    s = Mock()
    s.profile.basic_version = "2.0"
    s.profile.basic_start = 0x0801
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def _spec(**kw):
    base = {"name": "t", "machine": "c64", "timeout": 2,
            "autorun": True, "steps": []}
    base.update(kw)
    return base


def test_happy_path_key_wait_assert(tmp_path):
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.registers.return_value = {"PC": 0xC500}
    screens = ["READY.", "READY.", "HELLO", "HELLO", "HELLO"]
    spec = _spec(steps=[
        {"key": "RUN\n"},
        {"wait": {"text": "HELLO"}},
        {"assert": {"reg": "pc", "in_range": ["$C000", "$E000"]}},
    ])
    with patch("c64lib.testing.read_screen_text", side_effect=screens):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert [st.ok for st in result.steps] == [True, True, True]
    launch.assert_called_once_with(model="c64", name=result.session_name,
                                   headless=True, warp=True, cart=None,
                                   disk8=None)
    mon.keyboard_feed.assert_called_once_with(b"RUN\r")
    s.stop.assert_called_once()


def test_wait_text_since_ignores_stale_occurrence():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    screens = ["READY.", "TOO HIGH", "TOO HIGH", "TOO HIGH\nTOO HIGH", "TOO HIGH\nTOO HIGH"]
    spec = _spec(steps=[
        {"wait": {"text": "TOO HIGH", "since": True}},
    ])
    with patch("c64lib.testing.read_screen_text", side_effect=screens):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert [st.ok for st in result.steps] == [True]


def test_wait_accepts_screen_as_alias_for_text():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    screens = ["READY.", "READY.", "HELLO", "HELLO", "HELLO"]
    spec = _spec(steps=[{"wait": {"screen": "HELLO"}}])
    with patch("c64lib.testing.read_screen_text", side_effect=screens):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert [st.ok for st in result.steps] == [True]


def test_wait_screen_since_ignores_stale_occurrence():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    screens = ["READY.", "TOO HIGH", "TOO HIGH", "TOO HIGH\nTOO HIGH", "TOO HIGH\nTOO HIGH"]
    spec = _spec(steps=[
        {"wait": {"screen": "TOO HIGH", "since": True}},
    ])
    with patch("c64lib.testing.read_screen_text", side_effect=screens):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert [st.ok for st in result.steps] == [True]


def test_assert_accepts_text_as_alias_for_screen():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"assert": {"text": "READY."}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert [st.ok for st in result.steps] == [True]


def test_wait_step_with_neither_text_nor_mem_names_both_spellings():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"wait": {"nonsense": 1}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         pytest.raises(TestError, match="screen") as exc:
        run_test(spec, launch=launch)
    assert "text" in str(exc.value)


def test_assert_step_with_no_recognized_key_names_both_spellings():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"assert": {"nonsense": 1}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         pytest.raises(TestError, match="text") as exc:
        run_test(spec, launch=launch)
    assert "screen" in str(exc.value)


def test_poke_and_until_steps():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[
        {"poke": {"addr": "$CB", "values": [68]}},
        {"until": {"ref": "$0419", "count": 3}},
    ])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.run_until",
               return_value={"registers": {"PC": 0x0419}, "reached": 3,
                             "count": 3}) as ru:
        result = run_test(spec, launch=launch)
    assert result.passed is True
    mon.memory_write.assert_called_once_with(0xCB, bytes([68]))
    ru.assert_called_once_with(s, 0x0419, timeout=2, count=3)


def test_until_timeout_fails_step_with_progress():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"until": {"ref": "$0419", "count": 5, "timeout": 1}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.run_until",
               return_value={"registers": None, "reached": 2, "count": 5}):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert "2/5" in result.steps[0].detail


def test_fail_fast_captures_screen():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    # constant screen: boot sees READY. immediately; the failing wait spins
    # (sleep patched to a no-op) without exhausting a side_effect list
    spec = _spec(steps=[
        {"wait": {"text": "NEVER", "timeout": 0.5}},
        {"key": "RUN\n"},          # must not execute
    ])
    with patch("c64lib.testing.read_screen_text", return_value="READY.\nNOPE"), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert len(result.steps) == 1 and result.steps[0].ok is False
    assert "NOPE" in result.screen
    mon.keyboard_feed.assert_not_called()
    s.stop.assert_called_once()


def test_assert_mem_equals_text():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    # screen codes for "HI" are 8, 9
    mon.memory_read.return_value = bytes([8, 9])
    spec = _spec(steps=[{"assert": {"mem": "$0400", "equals_text": "HI"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    mon.memory_read.assert_called_with(0x0400, 2)


def test_program_bas_tokenized_and_autostarted(tmp_path):
    prog = tmp_path / "p.bas"
    prog.write_text('10 print "hi"\n')
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(program=str(prog))
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.tokenize", return_value=tmp_path / "p.prg") as tok:
        result = run_test(spec, launch=launch)
    assert result.passed is True
    tok.assert_called_once_with(prog, prog.with_suffix(".prg"), "2.0")
    mon.autostart.assert_called_once_with((tmp_path / "p.prg").resolve(), run=True)


def test_autorun_false_waits_for_load(tmp_path):
    prog = tmp_path / "p.prg"
    prog.write_bytes(b"\x01\x08")
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    screens = ["READY.",                                  # boot
               "LOAD\"*\",8\n\nSEARCHING",                # loading...
               "LOAD\"*\",8\n\nSEARCHING\nLOADING\nREADY.",  # loaded
               "DONE", "DONE"]
    spec = _spec(program=str(prog), autorun=False,
                 steps=[{"wait": {"text": "DONE"}}])
    with patch("c64lib.testing.read_screen_text", side_effect=screens), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    mon.autostart.assert_called_once_with(prog.resolve(), run=False)


def test_boot_timeout_is_error():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    with patch("c64lib.testing.read_screen_text", return_value="GARBAGE"), \
         patch("c64lib.testing.time.sleep"), \
         patch("c64lib.testing.time.monotonic", side_effect=[i * 10.0 for i in range(100)]):
        with pytest.raises(TestError, match="READY"):
            run_test(_spec(), launch=launch)
    s.stop.assert_called_once()


def test_wait_mem_polls_until_value():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.side_effect = [b"\x00", b"\x00", b"\x2a"]
    spec = _spec(steps=[{"wait": {"mem": "$0400", "equals": "$2a"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert mon.memory_read.call_count == 3


def test_wait_mem_screen_cell_reresolves_each_poll():
    """`@row,col` resolves against the machine's LIVE screen base, and the
    reset `autostart` performs leaves the VIC registers unreadable for a
    moment — `$D018` reads 0, so the cell lands in zero page. Resolved once,
    that bad address is polled for the whole timeout and the wait can never
    fire. Re-resolving each poll self-heals (and follows a screen the
    program relocates mid-wait)."""
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    s.profile.screen_cols = 40
    s.profile.screen_addr = 0x0400
    mon.memory_read.side_effect = \
        lambda addr, n: bytes([96 if addr == 0x04C8 else 3])
    spec = _spec(steps=[{"wait": {"mem": "@5,0", "equals": 96, "timeout": 2}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.time.sleep"), \
         patch("c64lib.ops.live_screen_base",
               side_effect=chain([0], repeat(0x0400))):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert result.steps[0].detail.startswith("mem $04c8")


def test_assert_mem_color_cell_reads_color_ram():
    """`@@row,col` in a mem step lands on $D800+offset even with the screen
    relocated, so specs stop hand-computing color addresses — the stale
    constant that produced Snake's false FAIL. The mask handles the 4-bit
    readback ($FD & $0F == 13)."""
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    s.profile.screen_cols = 40
    s.profile.screen_addr = 0x0400
    seen = []

    def read(addr, n):
        seen.append(addr)
        return bytes([0xFD] * n)

    mon.memory_read.side_effect = read
    spec = _spec(steps=[{"assert": {"mem": "@@5,0",
                                    "mask": {"and": "$0f", "equals": [13]}}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.ops.live_screen_base", return_value=0xC400):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert 0xD800 + 5 * 40 in seen


def test_wait_mem_timeout_reports_last_value():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.return_value = b"\x07"
    spec = _spec(steps=[{"wait": {"mem": "$0400", "equals": "$2a", "timeout": 0.2}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    detail = result.steps[0].detail
    assert "was 7" in detail and "wanted = 42" in detail


def test_wait_mem_at_least_fires_without_an_exact_match():
    """A counter the machine steps past between polls is only catchable
    with an inequality — `equals` would hang out for a value never read."""
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.side_effect = chain([b"\x05", b"\x19"], repeat(b"\x19"))
    spec = _spec(steps=[{"wait": {"mem": "$fb", "at_least": 20, "timeout": 1}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is True


def test_wait_mem_rejects_two_comparisons_in_one_step():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.return_value = b"\x07"
    spec = _spec(steps=[{"wait": {"mem": "$fb", "equals": 7, "at_least": 3}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         pytest.raises(TestError, match="exactly one of"):
        run_test(spec, launch=launch)


def test_assert_reg_unknown_register_fails_cleanly():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.registers.return_value = {"PC": 0x1234, "A": 0}
    spec = _spec(steps=[{"assert": {"reg": "q", "equals": 1}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is False and "no register" in result.steps[0].detail


def test_assert_reg_in_range_fail_branch():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.registers.return_value = {"PC": 0xC500}
    spec = _spec(steps=[{"assert": {"reg": "pc", "in_range": ["$0400", "$0500"]}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is False and "not in" in result.steps[0].detail


def test_autorun_false_load_never_finishes():
    s, _ = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(autorun=False, timeout=0.2, program="whatever.prg", steps=[])
    # First _wait_screen (READY gate) passes; second (load gate) never does.
    # Patching _wait_screen directly avoids the 45s/15s real-time deadlines.
    with patch("c64lib.testing._wait_screen",
               side_effect=[(True, "READY."), (False, "LOADING")]), \
         patch("c64lib.testing._prepare", return_value=(Path("x.prg"), None)), \
         pytest.raises(TestError, match="never finished loading"):
        run_test(spec, launch=launch)


def test_run_test_isolates_from_user_sessions():
    """FT4(a): documents the isolation contract — each run launches its own
    uniquely-named throwaway session and never attaches to (or stops) a
    user's session."""
    names = []

    def launch(model, name, headless, warp, cart=None, disk8=None):
        names.append(name)
        s, _ = _fake_session()
        return s

    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.Session") as S:
        r1 = run_test(_spec(), launch=launch)
        r2 = run_test(_spec(), launch=launch)
    S.attach.assert_not_called()
    assert names == [r1.session_name, r2.session_name]
    assert len(set(names)) == 2 and all(n.startswith("t") for n in names)


def _assert_step(mem_bytes, assert_arg):
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.return_value = mem_bytes
    spec = _spec(steps=[{"assert": assert_arg}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        return run_test(spec, launch=launch)


def test_assert_mem_equals_any():
    # FT6: either alternative passes
    r = _assert_step(bytes([81]), {"mem": "$0400", "equals_any": [[81], [98]]})
    assert r.passed is True
    r = _assert_step(bytes([98]), {"mem": "$0400", "equals_any": [[81], [98]]})
    assert r.passed is True
    r = _assert_step(bytes([32]), {"mem": "$0400", "equals_any": [[81], [98]]})
    assert r.passed is False
    # failure message shows actual and every accepted alternative
    assert "20" in r.steps[0].detail        # actual, hex
    assert "51" in r.steps[0].detail and "62" in r.steps[0].detail


def test_assert_mem_mask():
    # FT6: masked compare — e.g. ignore the reverse-video bit
    arg = {"mem": "$0400", "mask": {"and": 0x7F, "equals": [81]}}
    assert _assert_step(bytes([81]), arg).passed is True
    assert _assert_step(bytes([81 | 0x80]), arg).passed is True
    r = _assert_step(bytes([87]), arg)
    assert r.passed is False


def test_assert_mem_mask_multibyte():
    arg = {"mem": "$0400", "mask": {"and": "$7f", "equals": [81, 87]}}
    assert _assert_step(bytes([0xD1, 0x57]), arg).passed is True


def test_assert_mem_between():
    # FT6: single-byte range check
    arg = {"mem": "$0400", "between": {"min": 50, "max": 54}}
    assert _assert_step(bytes([50]), arg).passed is True
    assert _assert_step(bytes([54]), arg).passed is True
    r = _assert_step(bytes([55]), arg)
    assert r.passed is False
    assert "55" in r.steps[0].detail


def test_assert_mem_between_hex_bounds():
    arg = {"mem": "$0400", "between": {"min": "$30", "max": "$39"}}
    assert _assert_step(bytes([0x35]), arg).passed is True


def test_assert_mem_takes_the_wait_word_comparisons():
    """The docs show equals/not_equals/above/at_least/below/at_most in a
    wait: example that reads as if it applies to assert: too — 1812 used
    at_least in an assert and got a bare KeyError 'equals'."""
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.return_value = b"\x30"                # 48
    spec = _spec(steps=[{"assert": {"mem": "$1000", "at_least": 40}},
                        {"assert": {"mem": "$1000", "at_most": 48}},
                        {"assert": {"mem": "$1000", "above": 47}},
                        {"assert": {"mem": "$1000", "below": 49}},
                        {"assert": {"mem": "$1000", "not_equals": 0}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is True, [st.detail for st in result.steps]


def test_assert_mem_missing_comparison_names_the_step():
    """The failure names the step number, the kind, and the comparison
    menu — not a bare KeyError 'equals'."""
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"assert": {"mem": "$1000"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         pytest.raises(TestError, match=r"step 1 \(assert\).*at_least"):
        run_test(spec, launch=launch)


def test_call_step_resolves_symbol_and_passes_registers(tmp_path):
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:2000 .sndinit\n")
    prog = tmp_path / "p.prg"
    prog.write_bytes(b"\x01\x08")
    spec = _spec(program=str(prog), autorun=True,
                 steps=[{"call": {"routine": "sndinit", "a": 5, "x": 1}}])
    fired = {"fired": True, "registers": {"PC": 0x0400, "A": 5}, "trap": 0x0400}
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._prepare", return_value=(prog, lbl)), \
         patch("c64lib.testing.call_routine", return_value=fired) as cr:
        result = run_test(spec, launch=launch)
    assert result.passed is True, result.steps
    assert cr.call_args.args[1] == 0x2000
    assert cr.call_args.kwargs["a"] == 5 and cr.call_args.kwargs["x"] == 1


def test_call_step_timeout_fails_with_detail():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"call": {"routine": "$2000", "timeout": 1}}])
    out = {"fired": False, "registers": None, "trap": 0x0400}
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.call_routine", return_value=out):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert "never returned" in result.steps[0].detail


def test_sample_then_differs_passes():
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10]), bytes([12])]
    spec = _spec(steps=[{"sample": {"mem": "$D000", "as": "x0"}},
                        {"assert": {"mem": "$D000", "differs": "x0"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True, [st.detail for st in result.steps]
    assert "x0" in result.steps[0].detail


def test_sample_then_differs_fails_on_equal():
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10]), bytes([10])]
    spec = _spec(steps=[{"sample": {"mem": "$D000", "as": "x0"}},
                        {"assert": {"mem": "$D000", "differs": "x0"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is False
    assert "10" in result.steps[1].detail


def test_greater_and_less_than_samples():
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10]), bytes([12]), bytes([12])]
    spec = _spec(steps=[{"sample": {"mem": "$D000", "as": "x0"}},
                        {"assert": {"mem": "$D000", "greater_than": "x0"}},
                        {"assert": {"mem": "$D000", "less_than": "x0"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is False
    assert result.steps[1].ok is True and result.steps[2].ok is False


def test_sample_then_assert_unchanged():
    """Sample-vs-sample equality: 'shapes is unchanged 120 frames into the
    hold' was 1812's real claim, faked with a proxy byte until now."""
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.return_value = b"\x07"
    spec = _spec(steps=[{"sample": {"mem": "$1000", "as": "n0"}},
                        {"assert": {"mem": "$1000", "unchanged": "n0"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is True, [st.detail for st in result.steps]
    assert "sample n0" in result.steps[1].detail


def test_assert_unchanged_fails_when_the_value_moved():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.side_effect = [b"\x07", b"\x08"]
    spec = _spec(steps=[{"sample": {"mem": "$1000", "as": "n0"}},
                        {"assert": {"mem": "$1000", "unchanged": "n0"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert "not ==" in result.steps[1].detail


def test_unknown_sample_name_fails_actionably():
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10])]
    spec = _spec(steps=[{"assert": {"mem": "$D000", "differs": "nope"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is False
    assert "no sample named" in result.steps[0].detail


def test_comparator_literal_operand_hints_at_sample():
    """`differs: 0` and `less_than: 234` read like comparisons against a
    number and are not; the dogfood wrote three broken steps in a row before
    working that out. The hint fires only when the operand parses as one."""
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10]), bytes([10])]
    spec = _spec(steps=[{"sample": {"mem": "$D000", "as": "x0"}},
                        {"assert": {"mem": "$FB", "differs": 234}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is False
    assert result.steps[1].detail == (
        "no sample named '234' (have: x0) — differs/greater_than/less_than "
        "compare against a sample, not a literal: record one first with "
        '`- sample: { mem: "dotsleft", as: d0 }`')


def test_comparator_unknown_name_has_no_hint():
    """A genuine typo in a sample name must still read as one, or the hint
    masks the commoner mistake."""
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10])]
    spec = _spec(steps=[{"assert": {"mem": "$D000", "differs": "nope"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is False
    assert result.steps[0].detail == "no sample named 'nope' (have: none)"


@pytest.mark.parametrize("cmp_key", ["differs", "greater_than", "less_than", "unchanged"])
def test_assert_mem_between_with_a_sample_key_is_judged_not_crashed(cmp_key):
    """An assert step naming both `between` and a sample comparison used to
    size its read from `between` and then judge it with the sample branch,
    which read three names the sizing branch never bound — `NameError` in the
    middle of a test run instead of a pass/fail. One chain now decides both,
    and `between` wins because it is what the read was sized for.
    """
    arg = {"mem": "$0400", "between": {"min": 50, "max": 54}, cmp_key: "x0"}
    r = _assert_step(bytes([52]), arg)
    assert r.passed is True
    assert "in [50, 54]" in r.steps[0].detail
    r = _assert_step(bytes([55]), arg)
    assert r.passed is False
    assert "not in [50, 54]" in r.steps[0].detail


def test_assert_mem_between_with_a_sample_key_reads_one_byte_once():
    """The ambiguous step is still sized by `between` — one byte, one read —
    so the fix cannot have quietly moved the machine access."""
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([52])
    spec = _spec(steps=[{"assert": {"mem": "$0400", "differs": "x0",
                                    "between": {"min": 50, "max": 54}}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    mon.memory_read.assert_called_once_with(0x0400, 1)


def test_cart_spec_resolves_and_leaves_program_unset(tmp_path):
    """`cart:` resolves against the spec's own directory and never becomes a
    program (the runner's skip of the READY./autostart path is asserted by
    test_run_test_forwards_cart_and_skips_the_ready_gate)."""
    from c64lib.testing import load_test

    crt = tmp_path / "game.crt"
    crt.write_bytes(b"C64 CARTRIDGE   " + bytes(48))
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("cart: game.crt\nsteps:\n  - wait: {text: HI}\n")
    spec = load_test(spec_file)
    assert spec["cart"] == str(crt.resolve())
    assert spec.get("program") is None


def test_cart_and_program_are_mutually_exclusive(tmp_path):
    from c64lib.testing import TestError, load_test

    (tmp_path / "game.crt").write_bytes(b"C64 CARTRIDGE   " + bytes(48))
    (tmp_path / "program.s").write_text("nop\n")
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("cart: game.crt\nprogram: program.s\nsteps: []\n")
    with pytest.raises(TestError, match="cart.*program"):
        load_test(spec_file)


def test_missing_cart_file_is_named(tmp_path):
    from c64lib.testing import TestError, load_test

    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("cart: gone.crt\nsteps: []\n")
    with pytest.raises(TestError, match="gone.crt"):
        load_test(spec_file)


# --- the cart execution path -------------------------------------------------

def _crt(path: Path) -> Path:
    path.write_bytes(b"C64 CARTRIDGE   " + bytes(48))
    return path


def test_run_test_forwards_cart_and_skips_the_ready_gate(tmp_path):
    """A cart is mapped at power-on and boots straight into its own code: the
    runner hands it to launch(), never gates on READY., and autostarts nothing."""
    crt = _crt(tmp_path / "game.crt")
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(cart=str(crt), dir=str(tmp_path))
    with patch("c64lib.testing.read_screen_text", return_value="GAME OVER"), \
         patch("c64lib.testing._wait_screen") as waited:
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert launch.call_args.kwargs["cart"] == str(crt)
    waited.assert_not_called()          # no READY. gate for a cartridge
    mon.autostart.assert_not_called()   # and nothing to autostart


def test_run_test_without_cart_still_gates_on_ready(tmp_path):
    """The counterpart: a cart-less spec keeps the READY. gate it always had."""
    s, _ = _fake_session()
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen",
               return_value=(True, "READY.")) as waited:
        launch = Mock(return_value=s)
        run_test(_spec(), launch=launch)
    assert launch.call_args.kwargs["cart"] is None
    assert waited.called


def test_run_test_loads_cart_labels_when_present(tmp_path):
    """A cart's .lbl feeds symbols to until/poke steps, exactly as a program's does."""
    crt = _crt(tmp_path / "game.crt")
    (tmp_path / "game.lbl").write_text("al 00C000 .entry\n")
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(cart=str(crt), dir=str(tmp_path),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="X"):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    assert mon.memory_read.call_args.args[0] == 0xC000   # symbol resolved


def test_run_test_loads_disk_labels_when_present(tmp_path):
    """A disk spec's symbols follow the same sibling/.lbl rule as the CLI."""
    import os

    img = _d64(tmp_path / "game.d64")
    (tmp_path / "game.lbl").write_text("al 00C000 .entry\n")
    # The real order: `c64 package -o game.d64` writes the .lbl (beside the
    # .prg it built) and then the image. Writing them the other way round here
    # would trip the staleness guard on an image that is perfectly current.
    os.utime(img, (1_700_000_060, 1_700_000_060))
    os.utime(tmp_path / "game.lbl", (1_700_000_000, 1_700_000_000))
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(disk=str(img), dir=str(tmp_path),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen", return_value=(True, "READY.")):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    assert mon.memory_read.call_args.args[0] == 0xC000


def test_run_test_rejects_a_spec_with_both_cart_and_program(tmp_path):
    """load_test rejects the pair, but a hand-built spec skips that layer: the
    runner must refuse it too rather than silently ignoring `program`."""
    crt = _crt(tmp_path / "game.crt")
    launch = Mock()
    spec = _spec(cart=str(crt), program="hello.prg", dir=str(tmp_path))
    with pytest.raises(TestError, match="cart.*program"):
        run_test(spec, launch=launch)
    launch.assert_not_called()          # refused before anything booted


def test_shared_launch_bypass_predicate_covers_cart_and_disk():
    """conftest's shared machine can serve neither a cart nor a disk (both are
    attached at power-on), nor another model."""
    from tests.conftest import _needs_own_emulator as own

    assert own("c64", "c64", {}) is False
    assert own("c64", "c64pal", {}) is True
    assert own("c64", "c64", {"cart": "g.crt"}) is True
    assert own("c64", "c64", {"disk8": "g.d64"}) is True


def test_prepare_cart_passes_a_crt_through_with_its_sibling_labels(tmp_path):
    from c64lib.testing import prepare_cart

    crt = _crt(tmp_path / "game.crt")
    assert prepare_cart(tmp_path, "game.crt") == (crt.resolve(), None)
    lbl = tmp_path / "game.lbl"
    lbl.write_text("al 000801 .start\n")
    assert prepare_cart(tmp_path, "game.crt") == (crt.resolve(), lbl.resolve())


def test_prepare_cart_resolves_relative_to_the_spec_dir(tmp_path, monkeypatch):
    """A spec is portable: `cart:` follows the spec's directory, not the cwd."""
    from c64lib.testing import prepare_cart

    specs = tmp_path / "specs"
    specs.mkdir()
    crt = _crt(specs / "game.crt")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert prepare_cart(specs, "game.crt")[0] == crt.resolve()
    # an already-absolute cart is not re-resolved against the spec dir
    assert prepare_cart(elsewhere, str(crt))[0] == crt.resolve()


# A builder reports `labels: None` when it assembled nothing (an all-binary
# EasyFlash manifest has no symbols, and an empty .lbl is a file that looks
# like a symbol table and is not one). Every fake here carries that case, so
# `prepare_cart` cannot go back to calling Path() on it.
@pytest.mark.parametrize("labels", ["out.lbl", None])
def test_prepare_cart_builds_a_source_cart(tmp_path, monkeypatch, labels):
    from c64lib import testing as testing_mod

    (tmp_path / "game.s").write_text("nop\n")
    seen = {}

    def fake_build_cart(source, cart_type="8k"):
        seen["source"], seen["cart_type"] = Path(source), cart_type
        return {"crt": str(tmp_path / "out.crt"),
                "labels": str(tmp_path / labels) if labels else None}

    monkeypatch.setattr(testing_mod, "build_cart", fake_build_cart)
    crt, lbl = testing_mod.prepare_cart(tmp_path, "game.s", "16k")
    assert seen["source"] == (tmp_path / "game.s").resolve()
    assert seen["cart_type"] == "16k"
    assert crt == tmp_path / "out.crt"
    assert lbl == (tmp_path / labels if labels else None)


@pytest.mark.parametrize("name", ["game.ef.yaml", "game.ef.yml"])
@pytest.mark.parametrize("labels", ["ef.lbl", None])
def test_prepare_cart_builds_an_easyflash_manifest(tmp_path, monkeypatch, name,
                                                   labels):
    from c64lib import testing as testing_mod

    (tmp_path / name).write_text("name: game\n")
    seen = {}

    def fake_build_easyflash(manifest):
        seen["manifest"] = Path(manifest)
        return {"crt": str(tmp_path / "ef.crt"),
                "labels": str(tmp_path / labels) if labels else None}

    monkeypatch.setattr(testing_mod, "build_easyflash", fake_build_easyflash)
    crt, lbl = testing_mod.prepare_cart(tmp_path, name)
    assert seen["manifest"] == (tmp_path / name).resolve()
    assert crt == tmp_path / "ef.crt"
    # An all-binary manifest merges no labels: the None has to survive the
    # hand-off, not become Path(None) — a TypeError mid-test-run.
    assert lbl == (tmp_path / labels if labels else None)


def test_prepare_cart_rejects_an_unknown_extension(tmp_path):
    from c64lib.testing import prepare_cart

    (tmp_path / "game.prg").write_bytes(b"\x01\x08")
    with pytest.raises(TestError, match=r"must be a \.crt"):
        prepare_cart(tmp_path, "game.prg")


# --- the disk execution path -------------------------------------------------

def _d64(path: Path) -> Path:
    """A stand-in image. Nothing on this path reads the bytes: prepare_disk
    dispatches on the suffix and the runner only forwards the path."""
    path.write_bytes(bytes(174848))
    return path


def test_disk_spec_resolves_and_leaves_program_unset(tmp_path):
    """`disk:` resolves against the spec's own directory, like `cart:`."""
    from c64lib.testing import load_test

    img = _d64(tmp_path / "game.d64")
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("disk: game.d64\nsteps:\n  - wait: {text: HI}\n")
    spec = load_test(spec_file)
    assert spec["disk"] == str(img.resolve())
    assert spec.get("program") is None


def test_disk_and_program_are_mutually_exclusive(tmp_path):
    """Both want the one autostart slot; a spec that sets both would have the
    disk win silently and the program never load."""
    from c64lib.testing import load_test

    _d64(tmp_path / "game.d64")
    (tmp_path / "program.s").write_text("nop\n")
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("disk: game.d64\nprogram: program.s\nsteps: []\n")
    with pytest.raises(TestError, match="disk.*program"):
        load_test(spec_file)


def test_disk_and_cart_are_mutually_exclusive(tmp_path):
    """A cartridge boots itself and nothing is autostarted, so a disk named
    alongside one would be attached and never started."""
    from c64lib.testing import load_test

    _d64(tmp_path / "game.d64")
    _crt(tmp_path / "game.crt")
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("disk: game.d64\ncart: game.crt\nsteps: []\n")
    with pytest.raises(TestError, match="disk.*cart"):
        load_test(spec_file)


def test_missing_disk_file_is_named(tmp_path):
    from c64lib.testing import load_test

    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("disk: gone.d64\nsteps: []\n")
    with pytest.raises(TestError, match="gone.d64"):
        load_test(spec_file)


def test_a_contradictory_spec_is_reported_as_contradictory_not_as_a_missing_file(
        tmp_path):
    """Ordering rule: every mutual-exclusion check runs before any per-key
    existence check. A spec that names two of `program`/`cart`/`disk` is
    contradictory whether or not both paths exist, and reporting the missing one
    first sends the reader off to create a file the spec should not have named."""
    from c64lib.testing import load_test

    _d64(tmp_path / "game.d64")
    _crt(tmp_path / "game.crt")
    (tmp_path / "program.s").write_text("nop\n")
    spec_file = tmp_path / "test.yaml"
    for text, expected in [
        ("disk: game.d64\ncart: gone.crt\nsteps: []\n", "disk.*cart"),
        ("disk: gone.d64\ncart: game.crt\nsteps: []\n", "disk.*cart"),
        ("disk: game.d64\nprogram: gone.s\nsteps: []\n", "disk.*program"),
        ("disk: gone.d64\nprogram: program.s\nsteps: []\n", "disk.*program"),
        ("cart: game.crt\nprogram: gone.s\nsteps: []\n", "cart.*program"),
        ("cart: gone.crt\nprogram: program.s\nsteps: []\n", "cart.*program"),
    ]:
        spec_file.write_text(text)
        with pytest.raises(TestError, match=expected) as exc:
            load_test(spec_file)
        assert "not found" not in str(exc.value), text


def test_a_single_key_spec_still_names_the_missing_file(tmp_path):
    """The counterpart to the ordering above: with nothing to contradict, a
    missing path is still the answer — the reorder trades no message away."""
    from c64lib.testing import load_test

    spec_file = tmp_path / "test.yaml"
    for text, expected in [("cart: gone.crt\nsteps: []\n", "gone.crt"),
                           ("disk: gone.d64\nsteps: []\n", "gone.d64"),
                           ("program: gone.s\nsteps: []\n", "gone.s")]:
        spec_file.write_text(text)
        with pytest.raises(TestError, match=f"{expected} not found"):
            load_test(spec_file)


def test_is_disk_spec_parses_yaml_rather_than_sniffing_text(tmp_path):
    from c64lib.testing import is_disk_spec

    yes = tmp_path / "yes.yaml"
    yes.write_text("disk: game.d64\n")
    no = tmp_path / "no.yaml"
    no.write_text("# disk: game.d64\nsteps:\n  - key: \"disk:\"\n")
    assert is_disk_spec(yes) is True
    assert is_disk_spec(no) is False
    assert is_disk_spec(tmp_path / "nope.yaml") is False


def test_run_test_attaches_the_disk_and_autostarts_the_image(tmp_path):
    """A disk-booted program is autostarted like any other: the runner gates on
    READY., then autostarts the image itself (which issues LOAD"*",8,1)."""
    img = _d64(tmp_path / "game.d64")
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(disk=str(img), dir=str(tmp_path))
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen", return_value=(True, "READY.")):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert launch.call_args.kwargs["disk8"] == str(img.resolve())
    assert mon.autostart.call_args.args[0] == img.resolve()


def test_run_test_rejects_a_spec_with_both_disk_and_program(tmp_path):
    """load_test rejects the pair, but a hand-built spec skips that layer."""
    img = _d64(tmp_path / "game.d64")
    launch = Mock()
    spec = _spec(disk=str(img), program="hello.prg", dir=str(tmp_path))
    with pytest.raises(TestError, match="disk.*program"):
        run_test(spec, launch=launch)
    launch.assert_not_called()          # refused before anything booted


def test_run_test_rejects_a_spec_with_both_disk_and_cart(tmp_path):
    img = _d64(tmp_path / "game.d64")
    crt = _crt(tmp_path / "game.crt")
    launch = Mock()
    spec = _spec(disk=str(img), cart=str(crt), dir=str(tmp_path))
    with pytest.raises(TestError, match="disk.*cart"):
        run_test(spec, launch=launch)
    launch.assert_not_called()


def test_prepare_disk_passes_an_image_through(tmp_path):
    from c64lib.testing import prepare_disk

    for name in ("game.d64", "game.d71", "game.d81"):
        img = _d64(tmp_path / name)
        assert prepare_disk(tmp_path, name) == img.resolve()


def test_prepare_disk_resolves_relative_to_the_spec_dir(tmp_path, monkeypatch):
    """A spec is portable: `disk:` follows the spec's directory, not the cwd."""
    from c64lib.testing import prepare_disk

    specs = tmp_path / "specs"
    specs.mkdir()
    img = _d64(specs / "game.d64")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert prepare_disk(specs, "game.d64") == img.resolve()
    # an already-absolute image is not re-resolved against the spec dir
    assert prepare_disk(elsewhere, str(img)) == img.resolve()


@pytest.mark.parametrize("name", ["game.disk.yaml", "game.disk.yml"])
def test_prepare_disk_builds_a_manifest(tmp_path, monkeypatch, name):
    from c64lib import testing as testing_mod

    (tmp_path / name).write_text("label: game\n")
    seen = {}

    def fake_build_disk(manifest, model="c64"):
        seen["manifest"], seen["model"] = Path(manifest), model
        return {"image": str(tmp_path / "game.d64")}

    monkeypatch.setattr(testing_mod, "build_disk", fake_build_disk)
    img = testing_mod.prepare_disk(tmp_path, name, model="c64pal")
    assert seen["manifest"] == (tmp_path / name).resolve()
    assert seen["model"] == "c64pal"
    assert img == tmp_path / "game.d64"


def test_prepare_disk_rejects_an_unknown_extension(tmp_path):
    from c64lib.testing import prepare_disk

    (tmp_path / "game.prg").write_bytes(b"\x01\x08")
    with pytest.raises(TestError, match=r"must be a \.d64"):
        prepare_disk(tmp_path, "game.prg")


def test_disk_autorun_false_waits_for_the_load_to_finish(tmp_path):
    """`autorun: false` means "load, don't RUN" for a disk exactly as it does
    for a program — and the load gate has to apply too, or the first `key`
    step types into a machine still pulling bytes off the serial bus."""
    from c64lib.testing import _loaded

    img = _d64(tmp_path / "game.d64")
    s, mon = _fake_session()
    spec = _spec(disk=str(img), dir=str(tmp_path), autorun=False)
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen",
               return_value=(True, "READY.")) as waited:
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    mon.autostart.assert_called_once_with(img.resolve(), run=False)
    # Two gates: the READY. prompt, then the load itself.
    assert len(waited.call_args_list) == 2
    assert waited.call_args_list[1].args[1] is _loaded


def test_disk_autorun_false_load_never_finishes(tmp_path):
    img = _d64(tmp_path / "game.d64")
    s, _ = _fake_session()
    spec = _spec(disk=str(img), dir=str(tmp_path), autorun=False, timeout=0.2)
    with patch("c64lib.testing._wait_screen",
               side_effect=[(True, "READY."), (False, "LOADING")]), \
         pytest.raises(TestError, match="never finished loading"):
        run_test(spec, launch=Mock(return_value=s))


def test_wait_idle_step_fires_when_basic_returns_to_direct_mode():
    """`wait: {idle: true}` is the DSL's "the program has stopped" step —
    the shape demo 05 had to hand-roll as an in_range assert on PC."""
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.registers.side_effect = chain(
        [{"PC": 0xA7C9}], repeat({"PC": 0xE5D1}))
    spec = _spec(steps=[{"wait": {"idle": True, "timeout": 2}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is True, [st.detail for st in result.steps]
    assert "idle" in result.steps[0].detail


def test_wait_idle_step_fails_on_a_wedged_machine():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.registers.return_value = {"PC": 0x033C}
    spec = _spec(steps=[{"wait": {"idle": True, "timeout": 0.3}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert "$033c" in result.steps[0].detail


def test_wait_step_with_no_recognized_key_names_idle_too():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"wait": {}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         pytest.raises(TestError, match="idle"):
        run_test(spec, launch=launch)


def test_prg_program_resolves_a_sibling_label_file(tmp_path):
    """A `.prg` `program:` takes its symbols from a sibling `.lbl` of the same
    stem — the rule `cart:` and `disk:` already follow. Before, a `.prg`
    resolved *nothing*: the tell was `unknown symbol 'entry'; known: ` with an
    empty known-list, which sent La Galaxia's spec to the packaged image (and
    13 s of serial load) for the only route to symbols there was."""
    prog = tmp_path / "p.prg"
    prog.write_bytes(b"\x01\x08")
    (tmp_path / "p.lbl").write_text("al C:c000 .entry\n")
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(program=str(prog),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    assert mon.memory_read.call_args.args[0] == 0xC000


def test_prg_program_without_a_sibling_label_file_still_runs(tmp_path):
    """No `.lbl` beside the `.prg` is not an error — silently symbolless, the
    same as a ready-made `.crt` without one."""
    prog = tmp_path / "p.prg"
    prog.write_bytes(b"\x01\x08")
    s, mon = _fake_session()
    spec = _spec(program=str(prog))
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    mon.autostart.assert_called_once_with(prog.resolve(), run=True)


def test_areas_reach_the_assembler_for_an_s_program(tmp_path):
    """`areas:` is the spec's `--area`: La Galaxia links its engine at $4000
    and had nowhere in a spec to say so, which is why it tested the packaged
    image instead of the program."""
    from c64lib.build import Area, BuildResult

    src = tmp_path / "g.s"
    src.write_text("; x\n")
    prg = tmp_path / "g.prg"
    prg.write_bytes(b"\x01\x08")
    res = BuildResult(prg=prg, labels=tmp_path / "g.lbl")
    s, mon = _fake_session()
    spec = _spec(program=str(src), areas=["ENGINE=$4000:$6000"])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.build_asm", return_value=res) as ba:
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    ba.assert_called_once_with(src, basic_start=0x0801,
                               areas=[Area("ENGINE", 0x4000, 0x6000)])
    mon.autostart.assert_called_once_with(prg.resolve(), run=True)


def test_areas_with_a_non_assembly_program_names_the_conflict(tmp_path):
    """`areas:` rewrites the linker config a `.prg` never goes through. Loud,
    for the same reason `c64 package --area` is."""
    prog = tmp_path / "p.prg"
    prog.write_bytes(b"\x01\x08")
    spec = _spec(program=str(prog), areas=["ENGINE=$4000:$6000"])
    launch = Mock()
    with pytest.raises(TestError, match=r"areas:.*assembly"):
        run_test(spec, launch=launch)
    launch.assert_not_called()          # refused before anything booted


def test_a_bad_area_token_is_a_spec_error_not_a_traceback(tmp_path):
    """`parse_areas` raises ValueError, which no front end catches — a typo in
    a spec has to arrive as the same TestError every other spec mistake does."""
    src = tmp_path / "g.s"
    src.write_text("; x\n")
    spec = _spec(program=str(src), areas=["ENGINE"])
    with pytest.raises(TestError, match=r"--area needs NAME=START:SIZE"):
        run_test(spec, launch=Mock())


def test_areas_without_a_program_names_the_conflict(tmp_path):
    """A `cart:`/`disk:` spec brings its own memory map (or a built image), so
    `areas:` beside one would be silently ignored — the failure mode this plan
    exists to stamp out."""
    img = _d64(tmp_path / "game.d64")
    spec = _spec(disk=str(img), dir=str(tmp_path), areas=["ENGINE=$4000:$6000"])
    launch = Mock()
    with pytest.raises(TestError, match=r"areas:.*program:"):
        run_test(spec, launch=launch)
    launch.assert_not_called()


def _stale_disk(tmp_path: Path, img_at: int, lbl_at: int) -> Path:
    """A `disk:` image and its sibling `.lbl`, stamped to order."""
    import os

    img = _d64(tmp_path / "game.d64")
    lbl = tmp_path / "game.lbl"
    lbl.write_text("al 00C000 .entry\n")
    os.utime(img, (img_at, img_at))
    os.utime(lbl, (lbl_at, lbl_at))
    return img


def test_stale_disk_labels_are_refused_before_the_emulator_starts(tmp_path):
    """S3: rebuilding the program without repackaging the image leaves the
    runner resolving fresh symbols against stale bytes, which used to surface
    as `mem $414b = 4a != 00` — a plausible wrong value with no hint that the
    artifact, not the program, was at fault.

    Two mtimes and a path are all the comparison reads, so the refusal owes the
    caller no emulator boot and no 45-second READY. gate to say no."""
    img = _stale_disk(tmp_path, 1_700_000_000, 1_700_000_060)
    launch = Mock()
    spec = _spec(disk=str(img), dir=str(tmp_path),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with pytest.raises(TestError, match="predates"):
        run_test(spec, launch=launch)
    launch.assert_not_called()


def test_allow_stale_runs_the_spec_and_warns(tmp_path):
    """mtimes are not always the truth: `cp -r` without `-p` restamps a whole
    working tree, so an ordinary copy can look stale with nothing wrong in it.
    The override runs the spec and names what it let through — a guard waived in
    silence is one nobody notices they waived."""
    img = _stale_disk(tmp_path, 1_700_000_000, 1_700_000_060)
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(disk=str(img), dir=str(tmp_path),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen", return_value=(True, "READY.")):
        result = run_test(spec, launch=Mock(return_value=s), allow_stale=True)
    assert result.passed is True
    assert len(result.warnings) == 1
    assert "game.d64" in result.warnings[0] and "game.lbl" in result.warnings[0]
    # the same warning a --json/MCP caller reads, not a CLI-only console line
    assert result.to_dict()["warnings"] == result.warnings


def test_equal_mtimes_are_not_stale(tmp_path):
    """The `lbl_at <= img_at` boundary: only a label file strictly later than
    the image says the program was rebuilt after being packaged, so a tie —
    two writes inside one clock tick, a copy that carried both stamps over —
    runs rather than being refused."""
    img = _stale_disk(tmp_path, 1_700_000_000, 1_700_000_000)
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(disk=str(img), dir=str(tmp_path),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen", return_value=(True, "READY.")):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True and result.warnings == []


def test_stale_message_names_both_timestamps_and_the_remedy(tmp_path):
    """The actionable half of the message. `predates` alone satisfies every
    other staleness test here, so without this an edit can drop the timestamps
    that show which artifact is behind and the command that rebuilds it."""
    img = _stale_disk(tmp_path, 1_700_000_000, 1_700_000_060)
    spec = _spec(disk=str(img), dir=str(tmp_path))
    with pytest.raises(TestError) as exc:
        run_test(spec, launch=Mock())
    msg = str(exc.value)
    when = "%Y-%m-%d %H:%M:%S"
    assert time.strftime(when, time.localtime(1_700_000_000)) in msg
    assert time.strftime(when, time.localtime(1_700_000_060)) in msg
    assert "c64 package <source> -o game.d64" in msg
    assert "c64 disk build" in msg
    # and the override, or the only way past a false positive is guesswork
    assert "--allow-stale" in msg and "allow_stale" in msg


def test_a_disk_build_label_copy_is_never_called_stale(tmp_path):
    """`c64 disk build` writes its `<stem>.<cbm-name>.lbl` copies *after* the
    image it copied them for, so that route is newer by milliseconds on every
    successful build and can never be independently stale. Only the sibling
    `<stem>.lbl` — which a separate command writes — is checked."""
    import os

    img = _d64(tmp_path / "game.d64")
    kept = tmp_path / "game.hello.lbl"
    kept.write_text("al 00C000 .entry\n")
    os.utime(img, (1_700_000_000, 1_700_000_000))
    os.utime(kept, (1_700_000_060, 1_700_000_060))
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(disk=str(img), dir=str(tmp_path),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen", return_value=(True, "READY.")), \
         patch("c64lib.testing.disk_labels_path", return_value=kept):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    assert mon.memory_read.call_args.args[0] == 0xC000


def _prg_pair(tmp_path: Path, prg_at: float, lbl_at: float) -> Path:
    """A ready-made `program:` `.prg` and its sibling `.lbl`, stamped to order."""
    import os

    prg = tmp_path / "p.prg"
    prg.write_bytes(b"\x01\x08")
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:c000 .entry\n")
    os.utime(prg, (prg_at, prg_at))
    os.utime(lbl, (lbl_at, lbl_at))
    return prg


#: The largest gap the `.prg` guard tolerates and the smallest it refuses, as
#: literals rather than as `_PRG_LABELS_GRACE ± ε`: the point of the pair is
#: that editing the constant has to turn the suite red.
_WITHIN_GRACE, _BEYOND_GRACE = 59.5, 60.5


@pytest.mark.parametrize("gap", [600.0, _BEYOND_GRACE])
def test_prg_program_newer_than_its_labels_is_refused(tmp_path, gap):
    """A `.prg` copied in or rebuilt beside a `.lbl` nobody regenerated resolves
    every symbol against the program the label file used to describe, and used
    to do it silently. Pre-launch, like the disk guard: it reads two mtimes."""
    prg = _prg_pair(tmp_path, 1_700_000_000.0 + gap, 1_700_000_000.0)
    launch = Mock()
    spec = _spec(program=str(prg),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with pytest.raises(TestError, match="p.prg is newer than its symbols"):
        run_test(spec, launch=launch)
    launch.assert_not_called()


@pytest.mark.parametrize("gap", [600.0, _BEYOND_GRACE])
def test_prg_program_older_than_its_labels_is_refused(tmp_path, gap):
    """The mirror, and the same failure: a `.lbl` regenerated or copied in on
    its own — from a build in a scratch directory, or over a committed `.prg` —
    describes a program this spec is not about to load. Judged on the same
    evidence as the other direction, a gap no single command could produce."""
    prg = _prg_pair(tmp_path, 1_700_000_000.0, 1_700_000_000.0 + gap)
    launch = Mock()
    spec = _spec(program=str(prg),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with pytest.raises(TestError, match="p.prg predates its symbols"):
        run_test(spec, launch=launch)
    launch.assert_not_called()


@pytest.mark.parametrize("prg_at, lbl_at", [
    (1_700_000_000.0, 1_700_000_000.00006),      # ld65 -Ln: labels land last
    (1_700_000_000.00006, 1_700_000_000.0),      # `cp p.lbl p.prg dest/`
    (1_700_000_000.0 + _WITHIN_GRACE, 1_700_000_000.0),   # a slow tree copy…
    (1_700_000_000.0, 1_700_000_000.0 + _WITHIN_GRACE),   # …either way round
])
def test_a_prg_and_its_labels_written_together_are_not_stale(
        tmp_path, prg_at, lbl_at):
    """Why the guard needs a window at all: `ld65 -Ln` emits the `.lbl` ~60 µs
    *after* the `.prg` it describes, so judging bare order would refuse every
    built program in the repo — and order the other way is just as meaningless,
    because one command wrote both files whichever landed first. Only a gap no
    single command could produce is evidence, which is what makes the
    comparison safe to run in both directions."""
    prg = _prg_pair(tmp_path, prg_at, lbl_at)
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(program=str(prg),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True and result.warnings == []
    assert mon.memory_read.call_args.args[0] == 0xC000


def test_allow_stale_covers_the_prg_guard_too(tmp_path):
    """One override for both artifacts: a caller who has decided the mtimes are
    lying should not have to discover which of the two guards spoke."""
    prg = _prg_pair(tmp_path, 1_700_000_600, 1_700_000_000)
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(program=str(prg),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s), allow_stale=True)
    assert result.passed is True
    assert "p.prg" in result.warnings[0] and "p.lbl" in result.warnings[0]


def test_a_built_program_is_never_judged_stale(tmp_path):
    """A `.bas`/`.s` `program:` is built by the run itself, so its label file is
    always the newer of the pair and there is nothing to compare — the guard
    stays off that path rather than tolerating it with a fudge factor."""
    import os

    from c64lib.build import BuildResult

    src = tmp_path / "g.s"
    src.write_text("; x\n")
    prg = tmp_path / "g.prg"
    prg.write_bytes(b"\x01\x08")
    lbl = tmp_path / "g.lbl"
    lbl.write_text("al C:c000 .entry\n")
    # stamps the `.prg` guard would refuse outright, and the source newest of
    # the three: the spec is asking for a rebuild
    os.utime(prg, (1_700_000_000, 1_700_000_000))
    os.utime(lbl, (1_700_000_600, 1_700_000_600))
    os.utime(src, (1_700_001_200, 1_700_001_200))
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(program=str(src),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.build_asm",
               return_value=BuildResult(prg=prg, labels=lbl)):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True and result.warnings == []


def test_load_test_keeps_an_areas_list(tmp_path):
    from c64lib.testing import load_test

    (tmp_path / "p.s").write_text("; x\n")
    spec_file = tmp_path / "t.yaml"
    spec_file.write_text("program: p.s\nareas:\n  - ENGINE=$4000:$6000\n")
    spec = load_test(spec_file)
    assert spec["areas"] == ["ENGINE=$4000:$6000"]
    # every other spec defaults to an empty list, never a missing key
    (tmp_path / "u.yaml").write_text("program: p.s\n")
    assert load_test(tmp_path / "u.yaml")["areas"] == []


def test_load_test_rejects_a_bare_string_areas(tmp_path):
    """Forgetting the `- ` makes `areas:` a string, and parse_areas would read
    it one character at a time ("got 'E'")."""
    from c64lib.testing import load_test

    (tmp_path / "p.s").write_text("; x\n")
    spec_file = tmp_path / "t.yaml"
    spec_file.write_text("program: p.s\nareas: ENGINE=$4000:$6000\n")
    with pytest.raises(TestError, match=r"list of NAME=START:SIZE"):
        load_test(spec_file)


def test_load_test_rejects_areas_beside_a_cart(tmp_path):
    from c64lib.testing import load_test

    (tmp_path / "g.crt").write_bytes(b"C64 CARTRIDGE   ")
    spec_file = tmp_path / "t.yaml"
    spec_file.write_text("cart: g.crt\nareas:\n  - ENGINE=$4000:$6000\n")
    with pytest.raises(TestError, match=r"areas:.*program:"):
        load_test(spec_file)
