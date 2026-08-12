from itertools import chain, repeat
from unittest.mock import Mock, call, patch

import pytest

from c64lib import ops
from c64lib.monitor import StopInfo
from c64lib.ops import (
    parse_byte_values,
    parse_number,
    parse_ref,
    run_until,
    wait_for_break,
    wait_for_text,
)
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


def test_parse_byte_values_splits_whitespace_inside_tokens():
    # a shell variable expands to one whitespace-joined token under zsh
    assert parse_byte_values(["0 0 1 4 9 0"]) == bytes([0, 0, 1, 4, 9, 0])
    assert parse_byte_values(["$ff", "2 3"]) == bytes([0xFF, 2, 3])


def test_parse_byte_values_names_the_bad_token():
    with pytest.raises(ValueError, match=r"byte 2 is 'x9'"):
        parse_byte_values(["1", "2", "x9"])
    with pytest.raises(ValueError, match=r"byte 1 is 300, out of range"):
        parse_byte_values(["1", "300"])
    with pytest.raises(ValueError, match="no byte values"):
        parse_byte_values([])


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


def test_parse_ref_color_rowcol():
    """@@row,col is the color-RAM twin of @row,col: the same row/col math,
    but a fixed $D800 base — $DD00/$D018 relocate the screen, never the
    color matrix."""
    from c64lib.ops import COLOR_RAM_BASE
    assert COLOR_RAM_BASE == 0xD800
    assert parse_ref({}, "@@0,0",
                     screen_base=0x0400, screen_width=40) == 0xD800
    assert parse_ref({}, "@@23,18",
                     screen_base=0x0400, screen_width=40) == 0xD800 + 23*40 + 18
    # A relocated screen moves @row,col and must NOT move @@row,col.
    assert parse_ref({}, "@@5,0",
                     screen_base=0xC400, screen_width=40) == 0xD800 + 5*40


def test_parse_ref_color_rowcol_shares_the_guards():
    with pytest.raises(ValueError, match="row 25"):
        parse_ref({}, "@@25,0", screen_base=0x0400, screen_width=40)
    with pytest.raises(ValueError, match="col 40"):
        parse_ref({}, "@@0,40", screen_base=0x0400, screen_width=40)
    with pytest.raises(ValueError, match="geometry"):
        parse_ref({}, "@@1,2")
    with pytest.raises(ValueError, match="expected @row,col"):
        parse_ref({}, "@@nonsense", screen_base=0x0400, screen_width=40)


def test_session_ref_reads_the_live_screen_base_only_for_at_refs():
    """The live base costs a monitor round trip, so session_ref reads it
    only for a screen cell — the policy the CLI and the MCP server each
    used to carry a copy of."""
    s, _ = _fake_session()
    s.profile.screen_addr = 0x0400
    with patch("c64lib.ops.live_screen_base",
               side_effect=AssertionError("read the live base for a $hex ref")):
        assert ops.session_ref(s, "$1000", {}) == 0x1000
        assert ops.session_ref(s, "sprite", {"sprite": 0x2000}) == 0x2000
    with patch("c64lib.ops.live_screen_base", return_value=0xC400) as live:
        # a relocated screen: @row,col follows it, @@row,col stays at $D800
        assert ops.session_ref(s, "@0,0", {}) == 0xC400
        assert ops.session_ref(s, "@1,2", {}) == 0xC400 + 42
        assert ops.session_ref(s, "@@1,2", {}) == 0xD800 + 42
    assert live.call_count == 3


def test_session_ref_with_no_labels_reads_the_sessions_own_label_file(tmp_path):
    """`labels=None` is the default, and every caller with no symbol table of
    its own takes it — so the branch that reads the session's `.lbl` was only
    ever exercised through them. Passing `{}` is not the same thing: an
    explicit empty table stays empty, which is what makes the default a
    decision rather than an accident."""
    s, _ = _fake_session()
    lbl = tmp_path / "game.lbl"
    lbl.write_text("al C:1000 .alien\n")
    s.labels = str(lbl)
    assert ops.session_ref(s, "alien") == 0x1000
    assert ops.session_ref(s, "alien+2") == 0x1002
    with pytest.raises(KeyError):
        ops.session_ref(s, "alien", {})
    # No label file at all is the same call with nothing to find.
    s.labels = None
    with pytest.raises(KeyError):
        ops.session_ref(s, "alien")


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


def test_wait_for_text_since_does_not_fire_on_the_stale_occurrence(monkeypatch):
    """Negative control for the --since baseline, pinning the mechanism.

    A baseline that silently broke (stuck at 0, say) would still let the
    happy-path test above fire — just one read early. These three cases
    only pass together if the count really is snapshotted before polling:
    on a screen that never changes, since=True must NOT fire on the stale
    copy while since=False fires on that very same screen; and since=True
    must fire as soon as a NEW occurrence lands.
    """
    monkeypatch.setattr(ops.time, "sleep", lambda _: None)
    monkeypatch.setattr(ops, "_screen", lambda s: "GUESS?\nTOO HIGH")

    stale = ops.wait_for_text(object(), "TOO HIGH", timeout=0.2, since=True)
    assert stale["fired"] is None, "since=True fired on the pre-existing copy"
    assert "TOO HIGH" in stale["screen"]        # it WAS on screen the whole time

    fresh = ops.wait_for_text(object(), "TOO HIGH", timeout=0.2)
    assert fresh["fired"] == "text"             # same screen, no baseline

    screens = iter(["GUESS?\nTOO HIGH",         # baseline read: count 1
                    "GUESS?\nTOO HIGH",         # poll: still 1, keep waiting
                    "GUESS?\nTOO HIGH\nTOO HIGH"])   # a NEW one: count 2
    monkeypatch.setattr(ops, "_screen", lambda s: next(screens))
    out = ops.wait_for_text(object(), "TOO HIGH", timeout=5, since=True)
    assert out["fired"] == "text"


@pytest.mark.parametrize("since,screens", [
    # since=False: no baseline read, so the loop's own first read is the one
    # that must be checked before the deadline can end the wait.
    (False, ["TARGET APPEARS"]),
    # since=True: the baseline read is consumed first ("" -> baseline 0).
    (True, ["", "TARGET APPEARS"]),
])
def test_wait_for_text_checks_the_screen_read_on_the_final_poll(
        monkeypatch, since, screens):
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
    it = iter(screens)
    monkeypatch.setattr(ops, "_screen", lambda s: next(it))
    monkeypatch.setattr(ops.time, "sleep", lambda _: None)
    out = ops.wait_for_text(object(), "TARGET", timeout=0.1, since=since)
    assert out["fired"] == "text"


def test_wait_for_text_without_since_skips_the_baseline_read(monkeypatch):
    """A since=False wait costs no extra monitor round-trip: the pre-loop
    read exists only to snapshot a --since baseline."""
    reads = []
    monkeypatch.setattr(ops, "_screen",
                        lambda s: (reads.append(1), "READY.")[1])
    monkeypatch.setattr(ops.time, "sleep", lambda _: None)
    assert ops.wait_for_text(object(), "READY.", timeout=5)["fired"] == "text"
    assert len(reads) == 1, "since=False took a baseline read it never needed"
    reads.clear()
    assert ops.wait_for_text(object(), "READY.", timeout=0.2,
                             since=True)["fired"] is None    # baseline eats it
    assert len(reads) > 1                                    # baseline + polls


def test_wait_for_text_zero_timeout_still_reports_a_screen(monkeypatch):
    """The loop never runs, but the timeout contract still carries the
    latest screen text — one read, taken only because it is owed."""
    reads = []
    monkeypatch.setattr(ops, "_screen",
                        lambda s: (reads.append(1), "STUCK")[1])
    out = ops.wait_for_text(object(), "NEVER", timeout=0)
    assert out["fired"] is None and out["screen"] == "STUCK"
    assert len(reads) == 1


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
    # `mon` is deliberately a real DaemonMonitorClient (that is what the
    # fallback has to work on), so pyright resolves `mon.checkpoint_set` to
    # the declared bound method and cannot see the Mock that setattr just put
    # there. Unmodellable rather than wrong — the alternative is a Mock(spec=)
    # stand-in, which would stop testing the real class.
    mon.checkpoint_set.return_value = _ck7()  # pyright: ignore[reportAttributeAccessIssue]
    _stopped = StopInfo(pc=0x1000, checkpoint=7)
    mon.wait_for_stop.return_value = _stopped  # pyright: ignore[reportAttributeAccessIssue]
    mon.registers.return_value = {"PC": 0x1000}  # pyright: ignore[reportAttributeAccessIssue]
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


def test_key_type_decodes_literal_backslash_n_as_return():
    """A shell hands `key type "50\\n"` over as '5','0','\\','n' — that must
    press RETURN, exactly as a real newline does."""
    from c64lib.ops import key_type
    s, mon = _fake_session()
    out = key_type(s, "50\\n")
    mon.keyboard_feed.assert_called_once_with(b"50\r")
    assert out == {"typed_chars": 3}


def test_key_type_double_backslash_escapes_the_n():
    r"""`\\n` (backslash backslash n) is the escape hatch: one literal
    backslash followed by the letter n, no RETURN."""
    from c64lib.ops import key_type
    s, mon = _fake_session()
    key_type(s, "\\\\n")
    mon.keyboard_feed.assert_called_once_with(b"\\N")


def test_key_type_double_backslash_pairs_collapse():
    """Four backslashes are two escaped pairs -> two literal backslashes."""
    from c64lib.ops import key_type
    s, mon = _fake_session()
    key_type(s, "\\\\\\\\")
    mon.keyboard_feed.assert_called_once_with(b"\\\\")


def test_key_type_decodes_escape_in_the_middle():
    from c64lib.ops import key_type
    s, mon = _fake_session()
    key_type(s, "abc\\ndef\\n")
    mon.keyboard_feed.assert_called_once_with(b"ABC\rDEF\r")


def test_key_type_leaves_other_backslash_pairs_alone():
    """Only \\n and \\\\ are decoded; \\q stays two typed characters."""
    from c64lib.ops import key_type
    s, mon = _fake_session()
    out = key_type(s, "\\q")
    mon.keyboard_feed.assert_called_once_with(b"\\Q")
    assert out == {"typed_chars": 2}


def test_key_type_trailing_lone_backslash_is_typed():
    from c64lib.ops import key_type
    s, mon = _fake_session()
    key_type(s, "a\\")
    mon.keyboard_feed.assert_called_once_with(b"A\\")


def test_key_type_real_newline_unchanged():
    """The pre-existing path — a real newline — still maps to RETURN."""
    from c64lib.ops import key_type
    s, mon = _fake_session()
    key_type(s, "50\n")
    mon.keyboard_feed.assert_called_once_with(b"50\r")


def test_type_basic_appends_run_and_feeds_petscii():
    """One op behind both front ends' `basic type`: a trailing newline is
    added when the source lacks one, RUN follows when asked, and the whole
    thing goes through the same keyboard feed key_type uses."""
    from c64lib.ops import type_basic
    s, mon = _fake_session()
    out = type_basic(s, '10 print "hi"', run=True)
    mon.keyboard_feed.assert_called_once_with(b'10 PRINT "HI"\rRUN\r')
    mon.release.assert_called_once()
    assert out == {"typed_chars": 18, "run": True}


def test_type_basic_keeps_an_existing_trailing_newline():
    from c64lib.ops import type_basic
    s, mon = _fake_session()
    out = type_basic(s, "10 end\n")
    mon.keyboard_feed.assert_called_once_with(b"10 END\r")
    assert out == {"typed_chars": 7, "run": False}


def test_type_basic_types_backslashes_literally():
    """BASIC source is program text, not a shell argument: a `.bas` file
    already carries real newlines, so `\\n` in it is two characters PRINT
    should type (£N, E, W) and `\\\\` is two £. type_basic shares key_type's
    keyboard feed but must NOT inherit its escape decoding, or a line like
    `10 print "\\new"` would take a RETURN mid-line and split the program."""
    from c64lib.ops import type_basic
    s, mon = _fake_session()
    out = type_basic(s, '10 print "\\new"')
    mon.keyboard_feed.assert_called_once_with(b'10 PRINT "\\NEW"\r')
    assert out == {"typed_chars": 16, "run": False}


def test_type_basic_keeps_a_doubled_backslash_doubled():
    from c64lib.ops import type_basic
    s, mon = _fake_session()
    type_basic(s, "10 a$=\\\\\n")
    mon.keyboard_feed.assert_called_once_with(b"10 A$=\\\\\r")


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
        out = key_hold(s, "d", 0x0819, frames=3, timeout=9.0, release=False)
    assert out["frames"] == 3 and out["registers"] == {"PC": 0x0819}
    assert calls == [("poke", 0xCB, bytes([18])), ("until",)] * 3
    ru.assert_called_with(s, 0x0819, timeout=9.0, count=1)


def test_key_hold_releases_the_key_after_the_last_frame():
    """The default lets go of the key: one poke of 64 (no key) after the
    final tick. Without it the hold outlives the command — a game that
    took the IRQ over has no KERNAL scan left to clear $CB, so the key
    stays down for ever and every caller must hand-write
    `c64 mem write '$CB' 64`. The machine still ends stopped at the
    anchor: the release is a monitor write, not a resume."""
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    calls = []
    mon.memory_write.side_effect = lambda a, d: calls.append(("poke", a, d))

    def fake_until(*a, **k):
        calls.append(("until",))
        return {"registers": {"PC": 0x0819}, "reached": 1, "count": 1}

    with patch("c64lib.ops.run_until", side_effect=fake_until):
        out = key_hold(s, "d", 0x0819, frames=2)
    assert calls == [("poke", 0xCB, bytes([18])), ("until",)] * 2 \
        + [("poke", 0xCB, bytes([64]))]
    assert out["released"] is True
    assert out["frames"] == 2 and out["registers"] == {"PC": 0x0819}
    mon.resume.assert_not_called()


def test_key_hold_no_release_keeps_the_key_down():
    """`release=False` is the opt-out for a caller that wants the key still
    held when the next command runs; it reports `released: False` so the
    end state is never a guess."""
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with patch("c64lib.ops.run_until",
               return_value={"registers": {"PC": 1}, "reached": 1, "count": 1}):
        out = key_hold(s, "d", 0x0819, frames=2, release=False)
    assert out["released"] is False
    assert mon.memory_write.call_args_list == [
        call(0xCB, bytes([18])), call(0xCB, bytes([18]))]


def test_key_hold_space_alias_and_validation():
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with patch("c64lib.ops.run_until",
               return_value={"registers": {"PC": 1}, "reached": 1, "count": 1}):
        key_hold(s, "space", 0x1000, frames=1, release=False)
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


def test_key_hold_timeout_still_releases_and_leaves_the_machine_running():
    """The timeout is the case that needs the release most: a mistyped
    anchor on a healthy game jams the key with no scan to clear it and
    nothing stopped for the caller to notice. run_until leaves the machine
    RUNNING on timeout, and a monitor write halts it — so the release must
    poke 64 AND resume, or the "machine left RUNNING" promise in the error
    message and docs/cli.md becomes a lie."""
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with patch("c64lib.ops.run_until",
               side_effect=[{"registers": {"PC": 1}, "reached": 1, "count": 1},
                            {"registers": None, "reached": 0, "count": 1}]):
        out = key_hold(s, "a", 0x1000, frames=5)
    assert out["released"] is True
    assert mon.memory_write.call_args_list == [
        call(0xCB, bytes([10])), call(0xCB, bytes([10])),
        call(0xCB, bytes([64]))]
    mon.resume.assert_called_once_with()


def test_key_hold_timeout_honours_no_release():
    """`release=False` means the key stays down even on the error path —
    the caller asked for it, so nothing is poked and nothing is resumed on
    top of the resume run_until already did."""
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with patch("c64lib.ops.run_until",
               return_value={"registers": None, "reached": 0, "count": 1}):
        out = key_hold(s, "a", 0x1000, frames=5, release=False)
    assert out["released"] is False
    assert mon.memory_write.call_args_list == [call(0xCB, bytes([10]))]
    mon.resume.assert_not_called()


def test_key_hold_zero_frames_is_a_no_op():
    """A computed hold length of 0 is ordinary in a scripted protocol
    (Snake's evidence.sh guarded every call in shell for exactly this). It
    must succeed without touching the machine — no poke, no run_until — and
    without inventing a timeout about a checkpoint that was never armed."""
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with patch("c64lib.ops.run_until") as ru:
        out = key_hold(s, "d", 0x0819, frames=0)
    assert out == {"frames": 0, "requested": 0, "registers": None,
                   "released": False}
    ru.assert_not_called()
    mon.memory_write.assert_not_called()


def test_key_hold_zero_frames_still_validates_the_key():
    """The no-op validates before returning: a bad key with --frames 0 is
    the same error it is with --frames 1, not a silent success."""
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with pytest.raises(ValueError, match="no matrix code"):
        key_hold(s, "~", 0x1000, frames=0)


def test_key_hold_rejects_negative_frames():
    from c64lib.ops import key_hold
    s, mon = _fake_session()
    with pytest.raises(ValueError, match="frames"):
        key_hold(s, "d", 0x0819, frames=-1)
    mon.memory_write.assert_not_called()


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


def test_split_mem_condition_prefers_the_two_character_operators():
    from c64lib.ops import split_mem_condition
    assert split_mem_condition("$fb>=20") == ("$fb", ">=", "20")
    assert split_mem_condition("$fb<=20") == ("$fb", "<=", "20")
    assert split_mem_condition("$fb!=20") == ("$fb", "!=", "20")
    assert split_mem_condition("$fb==20") == ("$fb", "==", "20")
    assert split_mem_condition("  @6,0 = 20  ") == ("@6,0", "=", "20")
    assert split_mem_condition("ballx>128") == ("ballx", ">", "128")


def test_split_mem_condition_rejects_a_bare_address():
    from c64lib.ops import split_mem_condition
    for bad in ("$0400", "", "   ", "$0400="):
        with pytest.raises(ValueError, match="ADDR<op>VALUE"):
            split_mem_condition(bad)


@pytest.mark.parametrize("op,want,reads,fires", [
    ("=", 42, [b"\x05", b"\x2a"], True),
    (">=", 20, [b"\x05", b"\x19"], True),     # 25 >= 20 without ever being 20
    (">", 20, [b"\x14", b"\x15"], True),      # 20 is not > 20; 21 is
    ("!=", 5, [b"\x05", b"\x06"], True),
    ("<", 5, [b"\x05", b"\x05"], False),
])
def test_wait_for_mem_honors_the_operator(op, want, reads, fires):
    from c64lib.ops import wait_for_mem
    s = Mock()
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    # the last read repeats forever: a condition that never holds must poll
    # to the deadline rather than run out of canned responses
    mon.memory_read.side_effect = chain(reads, repeat(reads[-1]))
    with patch("c64lib.ops.time.sleep"):
        out = wait_for_mem(s, 0x0400, want, timeout=0.2, op=op)
    assert (out["fired"] == "mem") is fires


def test_wait_for_mem_rejects_an_unknown_operator():
    from c64lib.ops import wait_for_mem
    with pytest.raises(ValueError, match="unknown comparison"):
        wait_for_mem(Mock(), 0x0400, 1, timeout=0.1, op="~")


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


def test_profile_routine_samples_counts_cycles_via_the_cia_cascade():
    """507 emulated cycles: the counter ticks 504 of them ($FFFF-504=$FE07 in
    TA, TB untouched at $FFFF) and _CIA_START_SLACK adds the window's first
    three back — the live-verified correction."""
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.side_effect = [
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},    # entry snapshot
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},    # stopped at the trap
    ]
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)
    mon.memory_read.side_effect = [bytes([0x07, 0xFE]),   # TA lo/hi
                                   bytes([0xFF, 0xFF])]   # TB lo/hi
    out = profile_routine_samples(s, 0xC000)
    assert out["fired"] is True
    assert out["cycles"] == 507
    # timers were programmed through the chip model, then stopped
    writes = {c.args[0]: c for c in mon.memory_write.call_args_list}
    assert writes[0xDD0E].kwargs.get("side_effects") is True
    assert writes[0xDD0F].kwargs.get("side_effects") is True
    # I flag masked on entry (FL 0x20 | 0x04), restored from the entry value
    fl_sets = [c.args for c in mon.set_register.call_args_list
               if c.args[0] == "FL"]
    assert ("FL", 0x24) in fl_sets                  # masked on entry
    assert fl_sets[-1] == ("FL", 0x20)              # I bit restored after
    # ...and the REPORTED registers agree with the machine: the trap snapshot
    # still carried the I bit profile set, so reporting it raw would make
    # `profile --json` disagree with a `reg get` issued one command later.
    assert out["registers"]["FL"] == 0x20


def test_profile_routine_samples_with_irq_leaves_the_flags_alone():
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.side_effect = [
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},   # routine did its own SEI
    ]
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)
    mon.memory_read.side_effect = [bytes([0x07, 0xFE]), bytes([0xFF, 0xFF])]
    out = profile_routine_samples(s, 0xC000, with_irq=True)
    assert out["cycles"] == 507
    assert all(c.args[0] != "FL" for c in mon.set_register.call_args_list)
    # nothing restored, so the reported FL is the trap snapshot verbatim —
    # the routine's own I bit is the caller's result, not profile's bookkeeping
    assert out["registers"]["FL"] == 0x24


def test_profile_routine_samples_cascades_timer_b_for_long_routines():
    """TB counts TA underflows: one underflow plus 0x0100 TA ticks is a
    65792-cycle routine (+ the start slack) — a frame and a half."""
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.side_effect = [
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},
    ]
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)
    mon.memory_read.side_effect = [bytes([0xFF, 0xFE]),   # TA = $FEFF
                                   bytes([0xFE, 0xFF])]   # TB = $FFFE
    out = profile_routine_samples(s, 0xC000)
    assert out["cycles"] == 0x10000 + 0x0100 + 3


def test_profile_routine_samples_timeout_leaves_the_machine_running():
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.return_value = {"SP": 0xF9, "FL": 0x20, "PC": 0x1234}
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = None
    mon.checkpoint_list.return_value = [_call_ck(number=7, hit=False)]
    out = profile_routine_samples(s, 0xC000, timeout=0.3)
    assert out["fired"] is False
    assert out["cycles"] is None and out["registers"] is None
    mon.checkpoint_delete.assert_called_once_with(7)
    mon.resume.assert_called()          # machine left running on timeout


def test_profile_routine_samples_rejects_an_impossible_zero_count():
    """Both timers reading back $FFFF is a raw count of 0, which no routine
    can cost (a bare RTS is 6 cycles): the CIA pokes never reached the chip
    model. _CIA_START_SLACK would dress that up as "cycles": 3 — a silent
    wrong number — so it must be an error naming the likely cause."""
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.side_effect = [
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},    # entry snapshot
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},    # stopped at the trap
    ]
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)
    mon.memory_read.side_effect = [bytes([0xFF, 0xFF]),   # TA untouched
                                   bytes([0xFF, 0xFF])]   # TB untouched
    with pytest.raises(RuntimeError, match="chip model"):
        profile_routine_samples(s, 0xC000)
    # The guard fires after cleanup: timers stopped, checkpoint deleted, and
    # the entry I bit restored, exactly as on success.
    writes = {c.args[0]: c.args[1] for c in mon.memory_write.call_args_list}
    assert writes[0xDD0E] == b"\x00" and writes[0xDD0F] == b"\x00"
    mon.checkpoint_delete.assert_called_once_with(7)
    fl_sets = [c.args for c in mon.set_register.call_args_list
               if c.args[0] == "FL"]
    assert fl_sets[-1] == ("FL", 0x20)


#: la-galaxia's tick, the routine this whole verb exists for: 10,729 cycles
#: on an ordinary frame, 31,695 on a repaint frame, repaints on ~5 frames in
#: 32. One arrival answered "fine" 27 times out of 32.
_TICK, _REPAINT = 10729, 31695


def _timer_bytes(cycles: int) -> tuple[bytes, bytes]:
    """The TA/TB readbacks a fake VICE hands back for a routine of `cycles`:
    both counters run DOWN from $FFFF with TB cascaded off TA underflows, and
    _CIA_START_SLACK is the three cycles the timer misses at the window's
    start, so the chip only ever saw `cycles - 3`."""
    raw = cycles - ops._CIA_START_SLACK
    ta = 0xFFFF - (raw & 0xFFFF)
    tb = 0xFFFF - (raw >> 16)
    return bytes([ta & 0xFF, ta >> 8]), bytes([tb & 0xFF, tb >> 8])


def _bimodal_reads(costs):
    """memory_read side_effect for one TA+TB pair per arrival."""
    return [half for c in costs for half in _timer_bytes(c)]


def test_profile_routine_samples_prices_every_arrival_of_a_bimodal_tick():
    """THE bug: a per-frame cost that spikes on a repaint reads as fine when
    it is sampled once. Four arrivals whose third is a repaint must come back
    as four numbers plus min/max/mean, never as one."""
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    costs = [_TICK, _TICK, _REPAINT, _TICK]
    mon.registers.side_effect = [
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},    # entry snapshot
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},    # stopped at the trap
    ]
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)
    mon.memory_read.side_effect = _bimodal_reads(costs)
    out = profile_routine_samples(s, 0xC000, 4)
    assert out["fired"] is True
    assert out["samples"] == costs
    assert out["min"] == _TICK and out["max"] == _REPAINT
    assert out["mean"] == round(sum(costs) / 4, 1)
    assert out["irq_masked"] is True
    assert out["reached"] == 4 and out["count"] == 4
    # No single "cycles" number above one sample: naming one of a bimodal
    # pair THE cost is exactly the lie this verb exists to stop telling.
    assert "cycles" not in out


def test_profile_routine_samples_rearms_the_bracket_without_extra_round_trips():
    """`until --count`'s shape: ONE persistent checkpoint for the whole run,
    one resume per arrival, and the fake-JSR bracket re-armed in place
    between them — not a fresh profile round trip per sample."""
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.side_effect = [
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},
    ]
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)
    mon.memory_read.side_effect = _bimodal_reads([_TICK] * 3)
    profile_routine_samples(s, 0xC000, 3)
    mon.checkpoint_set.assert_called_once()
    mon.checkpoint_delete.assert_called_once_with(7)
    assert mon.resume.call_count == 3               # one per arrival
    sets = [c.args for c in mon.set_register.call_args_list]
    assert sets.count(("PC", 0xC000)) == 3          # bracket re-armed each time
    assert sets.count(("SP", 0xF7)) == 3            # ...from the ENTRY SP
    assert mon.registers.call_count == 2            # entry + the final snapshot


def test_profile_routine_samples_keeps_the_cycles_key_at_one_sample():
    """The existing CLI/MCP contract: at n == 1 the payload still carries the
    single `cycles` number every caller already reads."""
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.side_effect = [
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},
    ]
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)
    mon.memory_read.side_effect = _bimodal_reads([507])
    out = profile_routine_samples(s, 0xC000, 1)
    assert out["cycles"] == 507 and out["samples"] == [507]
    assert out["min"] == 507 and out["max"] == 507 and out["mean"] == 507.0


def test_profile_routine_samples_timeout_reports_the_arrivals_it_got():
    """A partial run is data: two of three arrivals priced, then nothing.
    The machine is left RUNNING with the checkpoint removed, as on the
    single-sample timeout."""
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.return_value = {"SP": 0xF9, "FL": 0x20, "PC": 0x1234}
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.side_effect = chain(
        [StopInfo(pc=0x0400, checkpoint=7)] * 2, repeat(None))
    mon.checkpoint_list.return_value = [_call_ck(number=7, hit=False)]
    mon.memory_read.side_effect = _bimodal_reads([_TICK, _REPAINT])
    out = profile_routine_samples(s, 0xC000, 3, timeout=0.3)
    assert out["fired"] is False
    assert out["samples"] == [_TICK, _REPAINT]
    assert out["reached"] == 2 and out["count"] == 3
    assert out["registers"] is None
    mon.checkpoint_delete.assert_called_once_with(7)
    mon.resume.assert_called()                  # machine left running


def test_profile_routine_samples_zero_count_aborts_the_whole_run():
    """The zero-raw guard survives sampling, and it aborts the whole run:
    the pokes are not reaching the chip model, so every later sample would be
    the same silent 3."""
    from c64lib.ops import profile_routine_samples
    s, mon = _fake_session()
    mon.registers.side_effect = [
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},
    ]
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)
    mon.memory_read.side_effect = [bytes([0xFF, 0xFF]), bytes([0xFF, 0xFF])]
    with pytest.raises(RuntimeError, match="chip model"):
        profile_routine_samples(s, 0xC000, 4)
    mon.checkpoint_delete.assert_called_once_with(7)    # cleanup happened first


def test_profile_routine_samples_needs_at_least_one_sample():
    from c64lib.ops import profile_routine_samples
    s, _ = _fake_session()
    with pytest.raises(ValueError, match="at least 1"):
        profile_routine_samples(s, 0xC000, 0)


def test_profile_samples_delegates_to_the_daemon():
    """Like `until --count`: with a session daemon the whole sample loop is
    ONE RPC, not one profile round trip per arrival."""
    from c64lib.daemon_client import DaemonMonitorClient
    from c64lib.ops import CALL_TRAP, profile_routine_samples
    s = Mock()
    mon = DaemonMonitorClient.__new__(DaemonMonitorClient)  # no socket needed
    mon.profile_samples = Mock(return_value={
        "fired": True, "raw": [c - 3 for c in (_TICK, _REPAINT)],
        "reached": 2, "registers": {"PC": 0x0400}})
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    out = profile_routine_samples(s, 0xC000, 2, timeout=9.0)
    assert out["samples"] == [_TICK, _REPAINT]
    mon.profile_samples.assert_called_once_with(0xC000, 9.0, 2, False,
                                                CALL_TRAP)


def test_profile_samples_falls_back_on_an_old_daemon():
    """A pre-profile_samples daemon answers 'unknown daemon method'
    (ValueError); the client-side loop must take over transparently."""
    from c64lib.daemon_client import DaemonMonitorClient
    from c64lib.ops import profile_routine_samples
    s = Mock()
    mon = DaemonMonitorClient.__new__(DaemonMonitorClient)
    mon.profile_samples = Mock(side_effect=ValueError(
        "unknown daemon method 'profile_samples'"))
    for name in ("checkpoint_set", "wait_for_stop", "registers", "memory_read",
                 "memory_write", "set_register", "checkpoint_delete", "resume",
                 "checkpoint_list"):
        setattr(mon, name, Mock())
    # Deliberately a real DaemonMonitorClient — that is what the fallback has
    # to work on — so pyright resolves these to the declared bound methods and
    # cannot see the Mocks setattr just put there (see run_until's twin test).
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)  # pyright: ignore[reportAttributeAccessIssue]
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)  # pyright: ignore[reportAttributeAccessIssue]
    mon.registers.side_effect = [  # pyright: ignore[reportAttributeAccessIssue]
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},
    ]
    mon.memory_read.side_effect = _bimodal_reads([_TICK, _REPAINT])  # pyright: ignore[reportAttributeAccessIssue]
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    out = profile_routine_samples(s, 0xC000, 2)
    assert out["samples"] == [_TICK, _REPAINT]


def test_profile_samples_does_not_fall_back_on_an_unrelated_valueerror():
    """The carve-out's whole point: falling back RUNS THE ROUTINE AGAIN, so
    only the old-daemon handshake ('unknown daemon method') may trigger it.
    Any other ValueError has to propagate — a partial daemon-side run
    silently topped up with a second helping of side effects would be
    unexplainable from the outside. The local loop here is fully stubbed, so
    a fallback WOULD have succeeded and returned numbers."""
    from c64lib.daemon_client import DaemonMonitorClient
    from c64lib.ops import profile_routine_samples
    s = Mock()
    mon = DaemonMonitorClient.__new__(DaemonMonitorClient)
    mon.profile_samples = Mock(side_effect=ValueError("something else"))
    for name in ("checkpoint_set", "wait_for_stop", "registers", "memory_read",
                 "memory_write", "set_register", "checkpoint_delete", "resume",
                 "checkpoint_list"):
        setattr(mon, name, Mock())
    mon.checkpoint_set.return_value = _call_ck(number=7, hit=False)  # pyright: ignore[reportAttributeAccessIssue]
    mon.wait_for_stop.return_value = StopInfo(pc=0x0400, checkpoint=7)  # pyright: ignore[reportAttributeAccessIssue]
    mon.registers.side_effect = [  # pyright: ignore[reportAttributeAccessIssue]
        {"SP": 0xF9, "FL": 0x20, "PC": 0x1234},
        {"SP": 0xFB, "FL": 0x24, "PC": 0x0400},
    ]
    mon.memory_read.side_effect = _bimodal_reads([_TICK, _REPAINT])  # pyright: ignore[reportAttributeAccessIssue]
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    with pytest.raises(ValueError, match="something else"):
        profile_routine_samples(s, 0xC000, 2)
    # the local loop never started: no second run of the routine
    mon.checkpoint_set.assert_not_called()  # pyright: ignore[reportAttributeAccessIssue]
    mon.resume.assert_not_called()  # pyright: ignore[reportAttributeAccessIssue]


def _idle_session(pcs):
    """A session whose registers() walks `pcs` and then repeats the last."""
    s, mon = _fake_session()
    pcs = list(pcs)
    mon.registers.side_effect = chain(
        ({"PC": pc} for pc in pcs), repeat({"PC": pcs[-1]}))
    return s, mon


def test_wait_for_idle_fires_on_consecutive_samples_in_the_input_loop():
    from c64lib.ops import wait_for_idle
    s, mon = _idle_session([0x0810, 0xE5CD, 0xE5D1, 0xE5D4])
    with patch("c64lib.ops.time.sleep"):
        out = wait_for_idle(s, timeout=5, samples=3, interval=0)
    assert out["fired"] == "idle" and "elapsed" in out
    assert mon.release.call_count == 4          # state-preserving, one per read


def test_wait_for_idle_does_not_fire_on_one_sample_in_range():
    """The IRQ handler transits ROM: a single sample landing in the loop is
    not proof the machine is idle, which is why samples must be CONSECUTIVE."""
    from c64lib.ops import wait_for_idle
    s, _ = _fake_session()
    # a running program that happens to call through the loop every third read
    s.monitor.return_value.__enter__.return_value.registers.side_effect = \
        chain([{"PC": 0xA7C9}, {"PC": 0xE5D1}, {"PC": 0x0073}] * 4,
              repeat({"PC": 0xA7C9}))
    with patch("c64lib.ops.time.sleep"):
        out = wait_for_idle(s, timeout=0.5, samples=3, interval=0)
    assert out["fired"] is None


def test_wait_for_idle_timeout_reports_the_last_pcs_seen():
    from c64lib.ops import wait_for_idle
    s, mon = _idle_session([0xA7C9])
    with patch("c64lib.ops.time.sleep"):
        out = wait_for_idle(s, timeout=0.3, samples=3, interval=0)
    assert out["fired"] is None and out["timeout"] == 0.3
    assert out["last_pcs"] and all(pc == 0xA7C9 for pc in out["last_pcs"])
    assert len(out["last_pcs"]) <= 8            # a window, not the whole run


def test_wait_for_idle_reads_at_least_once_with_a_zero_timeout():
    """Contract shared with wait_for_text: the result always reports what was
    actually seen, even when the deadline has already passed."""
    from c64lib.ops import wait_for_idle
    s, mon = _idle_session([0xA7C9])
    out = wait_for_idle(s, timeout=0, samples=3, interval=0)
    assert out["fired"] is None and out["last_pcs"] == [0xA7C9]


def test_idle_pc_range_starts_at_the_inloop_label():
    """The constant and the ROM label DB name one address; neither may drift."""
    from c64lib import romdoc
    assert romdoc.rom_labels("2.0")["INLOOP"] == ops.IDLE_PC_RANGE[0]


def test_disk_labels_path_prefers_the_sibling_lbl(tmp_path):
    from c64lib.ops import disk_labels_path
    img = tmp_path / "game.d64"
    img.write_bytes(b"x")
    assert disk_labels_path(img) is None          # nothing there: silent
    lbl = tmp_path / "game.lbl"
    lbl.write_text("al C:0824 .mainloop\n")
    assert disk_labels_path(img) == lbl


def test_disk_labels_path_falls_back_to_the_disk_build_convention(tmp_path):
    """disk build writes IMAGE.<cbm-name>.lbl, not IMAGE.lbl; the autostarted
    file is the FIRST directory entry, so its label file is the right one."""
    from c64lib.ops import disk_labels_path
    img = tmp_path / "game.d64"
    img.write_bytes(b"x")
    kept = tmp_path / "game.boot.lbl"
    kept.write_text("al C:0810 .start\n")
    listing = {"label": "g", "blocks_free": 660,
               "files": [{"blocks": 1, "name": "boot", "type": "prg"}]}
    with patch("c64lib.disk.list_files", return_value=listing):
        assert disk_labels_path(img) == kept


def test_disk_labels_path_is_silent_when_c1541_is_unusable(tmp_path):
    from c64lib.disk import DiskError
    from c64lib.ops import disk_labels_path
    img = tmp_path / "game.d64"
    img.write_bytes(b"x")
    with patch("c64lib.disk.list_files", side_effect=DiskError("no c1541")):
        assert disk_labels_path(img) is None
