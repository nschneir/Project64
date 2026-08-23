import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main
from tests.conftest import cli_json


def test_tokenize_default_output(tmp_path):
    src = tmp_path / "a.bas"
    src.write_text('10 print "hi"\n', encoding="utf-8")
    with patch("c64lib.cli.tokenize", return_value=tmp_path / "a.prg") as tok:
        r = CliRunner().invoke(main, ["--json", "basic", "tokenize", str(src)])
    assert r.exit_code == 0, r.output
    tok.assert_called_once_with(src, tmp_path / "a.prg", "2.0")
    assert json.loads(r.output)["prg"].endswith("a.prg")


def test_detokenize_listing(tmp_path):
    prg = tmp_path / "a.prg"
    prg.write_bytes(b"\x01\x08")
    with patch("c64lib.cli.detokenize", return_value='10 print "hi"\n'):
        r = CliRunner().invoke(main, ["basic", "detokenize", str(prg)])
    assert r.exit_code == 0
    assert 'print "hi"' in r.output


def _fake_attached():
    fake = Mock()
    fake.name, fake.model = "c64", "c64"
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_type_feeds_keyboard_and_run(tmp_path):
    src = tmp_path / "a.bas"
    src.write_text('10 print "HI"\n', encoding="utf-8")
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["basic", "type", str(src), "--run"])
    assert r.exit_code == 0, r.output
    fed = b"".join(c.args[0] for c in mon.keyboard_feed.call_args_list)
    assert fed == b'10 PRINT "HI"\rRUN\r'
    mon.release.assert_called_once()


def test_basic_type_json_payload_names_the_source_and_counts_the_run(tmp_path):
    """The `--json` payload of `c64 basic type` was asserted nowhere on this
    side, so `typed_chars` — the key it shares with c64_basic_type — held only
    by the op's own test. `typed` is the half with no MCP twin: this command
    takes a FILE where the tool takes the text inline, so the source path is
    what is worth reporting here.

    The count is of the PETSCII actually fed, RUN included: 13 characters of
    program, the RETURN `type_basic` appends because the last line has to be
    entered rather than displayed, then `RUN` and its own RETURN — 18.
    """
    src = tmp_path / "a.bas"
    src.write_text('10 print "HI"\n', encoding="utf-8")
    fake, mon = _fake_attached()
    out = cli_json(["basic", "type", str(src), "--run"], session=fake)
    assert out == {"typed": str(src), "typed_chars": 18, "run": True}
    fed = b"".join(c.args[0] for c in mon.keyboard_feed.call_args_list)
    assert out["typed_chars"] == len(fed) == len(b'10 PRINT "HI"\rRUN\r')


def test_key_type_feeds_text_directly():
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["key", "type", "50\n"])
    assert r.exit_code == 0, r.output
    mon.keyboard_feed.assert_called_once_with(b"50\r")
    mon.release.assert_called_once()


def _fake(labels=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", labels
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_key_type_rejects_unmappable_text():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["key", "type", "café"])   # é has no PETSCII
    assert r.exit_code == 1
    mon.keyboard_feed.assert_not_called()


def test_key_hold_zero_frames_is_a_no_op_not_a_timeout():
    """`--frames 0` used to fail with "timeout: only 0/0 frame(s) …
    checkpoint removed" — but nothing ran, nothing was armed, and nothing
    was removed. It reports the machine untouched instead."""
    fake, mon = _fake()
    with patch("c64lib.cli.ops_key_hold",
               return_value={"frames": 0, "requested": 0,
                             "registers": None}), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "key", "hold", "d",
                                      "--at", "$0819", "--frames", "0"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out == {"frames": 0, "requested": 0, "machine": "untouched"}
    assert "timeout" not in r.output


def test_key_hold_releases_by_default_and_says_so():
    """No flag = the key is let go. The re-poke only works while the KERNAL
    scan is alive to clear $CB; a game that owns the IRQ has no scan, so a
    hold that did not release would leave the key down for the rest of the
    session. The JSON carries `released` alongside the registers."""
    fake, mon = _fake()
    with patch("c64lib.cli.ops_key_hold",
               return_value={"frames": 2, "requested": 2, "released": True,
                             "registers": {"PC": 0x0819}}) as kh, \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "key", "hold", "d",
                                      "--at", "$0819", "--frames", "2"])
    assert r.exit_code == 0, r.output
    assert kh.call_args.kwargs["release"] is True
    assert json.loads(r.output)["released"] is True


def test_key_hold_timeout_reports_the_key_state():
    """A timeout is where `released` carries real information: the machine
    is left RUNNING, so the caller cannot see $CB for themselves. The
    failure says the key was let go and the JSON carries the flag."""
    fake, mon = _fake()
    with patch("c64lib.cli.ops_key_hold",
               return_value={"frames": 1, "requested": 5, "released": True,
                             "registers": None}), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "key", "hold", "d",
                                      "--at", "$0819", "--frames", "5"])
    assert r.exit_code == 1, r.output
    out = json.loads(r.output)
    assert out["released"] is True and out["frames"] == 1
    assert "left RUNNING" in out["error"] and "key released" in out["error"]


def test_key_hold_timeout_names_the_stuck_key_with_no_release():
    """With `--no-release` the key really is left down on a running
    machine — the failure must name $CB and hand over the poke that clears
    it, not leave the caller to work it out."""
    fake, mon = _fake()
    with patch("c64lib.cli.ops_key_hold",
               return_value={"frames": 0, "requested": 3, "released": False,
                             "registers": None}), \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "key", "hold", "d",
                                      "--at", "$0819", "--frames", "3",
                                      "--no-release"])
    assert r.exit_code == 1, r.output
    out = json.loads(r.output)
    assert out["released"] is False
    assert "$CB" in out["error"] and "mem write" in out["error"]


def test_key_hold_no_release_keeps_the_key_down():
    """`--no-release` is the opt-out, forwarded to the op and reported."""
    fake, mon = _fake()
    with patch("c64lib.cli.ops_key_hold",
               return_value={"frames": 1, "requested": 1, "released": False,
                             "registers": {"PC": 0x0819}}) as kh, \
         patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "key", "hold", "d",
                                      "--at", "$0819", "--no-release"])
    assert r.exit_code == 0, r.output
    assert kh.call_args.kwargs["release"] is False
    assert json.loads(r.output)["released"] is False


def test_key_hold_negative_frames_fails_before_touching_the_machine():
    """A negative hold length is a caller bug, not a no-op: the op refuses
    it before poking anything, and the CLI reports it as a clean failure
    naming `frames`. (Written `--frames=-1` because click reads a bare
    `-1` as an option, not as a value.)"""
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["key", "hold", "d",
                                      "--at", "$0819", "--frames=-1"])
    assert r.exit_code == 1, r.output
    assert "frames" in r.output and "Traceback" not in r.output
    mon.memory_write.assert_not_called()


def test_check_clean_program_exits_zero(tmp_path):
    src = tmp_path / "ok.bas"
    src.write_text('10 print "hi"\n20 goto 10\n', encoding="utf-8")
    r = CliRunner().invoke(main, ["basic", "check", str(src)])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == "clean"


def test_check_reports_errors_and_exits_one(tmp_path):
    src = tmp_path / "bad.bas"
    src.write_text("10 goto 999\n", encoding="utf-8")
    r = CliRunner().invoke(main, ["basic", "check", str(src)])
    assert r.exit_code == 1
    assert "ERROR E20: line 10: goto target 999 does not exist" in r.output


def test_check_warnings_alone_exit_zero(tmp_path):
    src = tmp_path / "warn.bas"
    src.write_text('10 print "oops\n20 end\n', encoding="utf-8")
    r = CliRunner().invoke(main, ["basic", "check", str(src)])
    assert r.exit_code == 0, r.output
    assert "WARNING W40: line 10:" in r.output


def test_run_area_reaches_the_linker(tmp_path):
    """`c64 run --area` is `c64 build --area`: La Galaxia needed the flag to
    link at all, so it could not use `c64 run` and shipped a two-command
    build.sh instead."""
    from c64lib.build import Area, BuildResult

    src = tmp_path / "g.s"
    src.write_text("; x\n", encoding="utf-8")
    res = BuildResult(prg=tmp_path / "g.prg", labels=tmp_path / "g.lbl")
    fake, mon = _fake_attached()
    fake.profile.basic_start = 0x0801
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.ops.build_asm", return_value=res) as ba:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "run", str(src),
                                      "--area", "ENGINE=$4000:$6000"])
    assert r.exit_code == 0, r.output
    assert ba.call_args.kwargs["areas"] == [Area("ENGINE", 0x4000, 0x6000)]
    mon.autostart.assert_called_once_with(res.prg, run=True)


def test_run_rejects_area_where_it_cannot_apply(tmp_path):
    """A `.prg` is loaded as it is and a `.bas` is tokenized; neither goes
    through the linker `--area` rewrites. Loud rather than ignored, in the
    words `c64 package` already uses."""
    prg = tmp_path / "p.prg"
    prg.write_bytes(b"\x01\x08")
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "run", str(prg),
                                      "--area", "ENGINE=$4000:$6000"])
    assert r.exit_code == 1
    assert json.loads(r.output)["error"] == (
        "--area applies to assembly sources only")
    mon.autostart.assert_not_called()


def test_run_reports_the_unsupported_extension_before_the_area_rule(tmp_path):
    """Two things are wrong with `c64 run notes.txt --area FOO=$4000:$100`, and
    only one of them can be fixed: reporting the flag invites dropping it and
    trying again on a file that will never run either way."""
    txt = tmp_path / "notes.txt"
    txt.write_text("not a program\n", encoding="utf-8")
    fake, mon = _fake_attached()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "run", str(txt),
                                      "--area", "FOO=$4000:$100"])
    assert r.exit_code == 1
    err = json.loads(r.output)["error"]
    assert "don't know how to run '.txt'" in err
    assert "--area" not in err
    S.attach.assert_not_called()        # and before the session, like --area
    mon.autostart.assert_not_called()


def test_run_bad_area_exits_one_before_assembling(tmp_path):
    src = tmp_path / "g.s"
    src.write_text("; x\n", encoding="utf-8")
    fake, _ = _fake_attached()
    fake.profile.basic_start = 0x0801
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.ops.build_asm") as ba:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "run", str(src),
                                      "--area", "ENGINE"])
    assert r.exit_code == 1
    assert json.loads(r.output)["error"] == (
        "--area needs NAME=START:SIZE, got 'ENGINE'")
    ba.assert_not_called()


def test_check_json_payload(tmp_path):
    src = tmp_path / "bad.bas"
    src.write_text("10 goto 999\n", encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "basic", "check", str(src)])
    assert r.exit_code == 1
    data = json.loads(r.output)
    assert data["errors"] == 1 and data["warnings"] == 0
    assert data["issues"][0]["rule"] == "E20"
    # GOTO=1 + space=1 + "999"=3 -> 5 text bytes, +5 line overhead, +2 trailing.
    assert data["tokenized_bytes"] == 12
