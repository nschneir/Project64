import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main
from c64lib.session import SessionError
from tests.conftest import assert_json_error


def _fake_session(name="c64", port=6502):
    s = Mock()
    s.name, s.pid, s.port, s.model = name, 1234, port, "c64"
    s.loaded_prg, s.loaded_at, s.loaded_deps = None, 0.0, None
    return s


def _fake(labels=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", labels
    fake.loaded_prg, fake.loaded_at, fake.loaded_deps = None, 0.0, None
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_session_start_json():
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = []       # nothing else up: no stderr notice
        S.launch.return_value = _fake_session()
        r = CliRunner().invoke(main, ["--json", "session", "start", "--model", "c64"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out == {"name": "c64", "model": "c64", "pid": 1234, "port": 6502,
                   "symbols": None}
    S.launch.assert_called_once_with(
        model="c64", name=None, headless=False, warp=False, disk8=None,
        cart=None
    )


def test_session_list_human():
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = [_fake_session()]
        r = CliRunner().invoke(main, ["session", "list"])
    assert r.exit_code == 0
    assert "c64" in r.output and "6502" in r.output


def test_session_stop_by_name():
    fake = _fake_session()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["session", "stop", "c64"])
    assert r.exit_code == 0
    S.attach.assert_called_once_with("c64")
    fake.stop.assert_called_once()


def test_session_error_json_exit_code():
    with patch("c64lib.cli.Session") as S:
        S.attach.side_effect = SessionError(
            "no C64 session running. Start one with: c64 session start")
        r = CliRunner().invoke(main, ["--json", "session", "stop"])
    assert r.exit_code == 1
    assert "no C64 session" in json.loads(r.output)["error"]


def test_session_reset_resumes():
    fake = _fake_session()
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["session", "reset", "--hard"])
    assert r.exit_code == 0
    mon.reset.assert_called_once_with(hard=True)
    mon.resume.assert_called_once()


def test_session_stop_by_name_option():
    fake = _fake_session()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["session", "stop", "--name", "c64"])
    assert r.exit_code == 0, r.output
    S.attach.assert_called_once_with("c64")
    fake.stop.assert_called_once()


def test_session_stop_dash_s_option():
    fake = _fake_session()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["session", "stop", "-s", "c64"])
    assert r.exit_code == 0, r.output
    S.attach.assert_called_once_with("c64")


def test_session_stop_conflicting_names_error():
    with patch("c64lib.cli.Session") as S:
        r = CliRunner().invoke(main, ["--json", "session", "stop", "a", "--name", "b"])
    assert r.exit_code == 1
    assert "conflicting" in json.loads(r.output)["error"].lower()
    S.attach.assert_not_called()


def test_session_start_dash_s_alias():
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = []
        S.launch.return_value = _fake_session(name="snake")
        r = CliRunner().invoke(main, ["--json", "session", "start", "-s", "snake"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"name": "snake", "model": "c64", "pid": 1234,
                                    "port": 6502, "symbols": None}
    S.launch.assert_called_once_with(
        model="c64", name="snake", headless=False, warp=False, disk8=None,
        cart=None
    )


def test_session_start_with_disk_registers_its_labels(tmp_path):
    img = tmp_path / "game.d64"
    img.write_bytes(b"x")
    lbl = tmp_path / "game.lbl"
    lbl.write_text("al C:0824 .mainloop\n", encoding="utf-8")
    s = Mock()
    s.name, s.model, s.pid, s.port = "c64", "c64", 1, 6510
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = []
        S.launch.return_value = s
        r = CliRunner().invoke(
            main, ["--json", "session", "start", "--disk", str(img)])
    assert r.exit_code == 0, r.output
    s.set_labels_path.assert_called_once_with(str(lbl))
    assert json.loads(r.output)["symbols"] == str(lbl)


def test_session_start_with_cart_registers_its_sibling_lbl(tmp_path):
    crt = tmp_path / "game.crt"
    crt.write_bytes(b"x")
    lbl = tmp_path / "game.lbl"
    lbl.write_text("al C:8009 .cart_main\n", encoding="utf-8")
    s = Mock()
    s.name, s.model, s.pid, s.port = "c64", "c64", 1, 6510
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = []
        S.launch.return_value = s
        r = CliRunner().invoke(
            main, ["--json", "session", "start", "--cart", str(crt)])
    assert r.exit_code == 0, r.output
    s.set_labels_path.assert_called_once_with(str(lbl))


def test_session_start_failure_is_json_error():
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = []
        S.launch.side_effect = SessionError("x64sc not found")
        r = CliRunner().invoke(main, ["--json", "session", "start"])
    assert r.exit_code == 1
    assert "x64sc not found" in json.loads(r.output)["error"]


def test_session_start_monitor_timeout_exits_1():
    """The la-galaxia dogfood (2026-08-08) recorded this as printing its error
    and still exiting 0, which would let `set -e` carry an evidence script on
    against a dead session. It does not: `Session.launch` raises SessionError
    and `session start` reports it through `fail()`. Verified end to end on
    2026-08-09 against the real `.venv/bin/c64` under `/bin/sh -e`, with a fake
    x64sc that accepts the monitor connection and never answers — exit 1, and
    the line after the launch never ran. Pinned here so the claim is not
    re-derived from the demo script's comment.
    """
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = []
        S.launch.side_effect = SessionError(
            "VICE started but its monitor never answered after 2 attempt(s): "
            "timed out")
        r = CliRunner().invoke(
            main, ["session", "start", "--name", "X", "--headless"])
    assert r.exit_code == 1, r.output
    assert "never answered" in r.output


def test_status_command():
    fake, _ = _fake()
    fake.pid, fake.port, fake.socket = 4242, 6510, "/tmp/s.sock"
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="running"):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "status"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out == {"name": "c64", "model": "c64", "pid": 4242,
                   "port": 6510, "state": "running",
                   "program": None, "loaded_at": 0.0, "stale": []}


def test_status_human_line():
    fake, _ = _fake()
    fake.pid, fake.port = 4242, 6510
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="stopped"):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["status"])
    assert "state=stopped" in r.output and "c64" in r.output


def test_session_ensure_attaches_when_running():
    fake = _fake_session()
    with patch("c64lib.cli.Session") as S:
        S.ensure.return_value = (fake, False)
        r = CliRunner().invoke(main, ["--json", "session", "ensure"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["started"] is False and out["name"] == "c64"
    S.ensure.assert_called_once_with(model="c64", name=None,
                                     headless=False, warp=False)


def test_session_ensure_starts_when_absent():
    fake = _fake_session(name="fresh")
    with patch("c64lib.cli.Session") as S:
        S.ensure.return_value = (fake, True)
        r = CliRunner().invoke(main, ["session", "ensure", "--warp", "--headless"])
    assert r.exit_code == 0, r.output
    assert "started" in r.output.lower()
    S.ensure.assert_called_once_with(model="c64", name=None,
                                     headless=True, warp=True)


def test_session_ensure_reports_running():
    fake = _fake_session()
    with patch("c64lib.cli.Session") as S:
        S.ensure.return_value = (fake, False)
        r = CliRunner().invoke(main, ["session", "ensure"])
    assert r.exit_code == 0
    assert "already running" in r.output.lower()


# --- stop --all, and the "already up" notice ------------------------------
# The la-galaxia dogfood (2026-08-08) ran four x64sc processes at once, two of
# them orphaned by a *previous* conversation, each holding a warped emulator
# on a CPU core. Cleanup is one command, and start says how many are up.


def test_session_stop_all_stops_every_session():
    with patch("c64lib.cli.Session") as S:
        S.stop_all.return_value = ["a", "b"]
        r = CliRunner().invoke(main, ["session", "stop", "--all"])
    assert r.exit_code == 0, r.output
    S.stop_all.assert_called_once_with()
    S.attach.assert_not_called()           # --all never resolves a single one
    assert "a" in r.output and "b" in r.output


def test_session_stop_all_json_lists_every_name():
    with patch("c64lib.cli.Session") as S:
        S.stop_all.return_value = ["a", "b"]
        r = CliRunner().invoke(main, ["--json", "session", "stop", "--all"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == {"stopped": ["a", "b"]}


def test_session_stop_all_with_nothing_running_exits_0():
    with patch("c64lib.cli.Session") as S:
        S.stop_all.return_value = []
        r = CliRunner().invoke(main, ["session", "stop", "--all"])
    assert r.exit_code == 0, r.output
    assert "no sessions running" in r.output


def test_session_stop_all_with_a_positional_name_is_an_error():
    with patch("c64lib.cli.Session") as S:
        r = CliRunner().invoke(main, ["--json", "session", "stop", "boo", "--all"])
    assert r.exit_code == 1
    err = json.loads(r.stdout)["error"]
    assert "--all" in err and "boo" in err
    S.stop_all.assert_not_called()
    S.attach.assert_not_called()


def test_session_stop_all_with_the_name_option_is_an_error():
    with patch("c64lib.cli.Session") as S:
        r = CliRunner().invoke(
            main, ["--json", "session", "stop", "--all", "--name", "boo"])
    assert r.exit_code == 1
    assert "--all" in json.loads(r.stdout)["error"]
    S.stop_all.assert_not_called()


def test_session_stop_all_with_the_global_session_option_is_an_error():
    """`c64 -s foo session stop --all` names one session and asks for every
    session; guessing either way clears the wrong set."""
    with patch("c64lib.cli.Session") as S:
        r = CliRunner().invoke(
            main, ["--json", "-s", "foo", "session", "stop", "--all"])
    assert r.exit_code == 1
    err = json.loads(r.stdout)["error"]
    assert "--all" in err and "foo" in err
    S.stop_all.assert_not_called()
    S.attach.assert_not_called()


def test_session_stop_all_failure_exits_1_and_names_the_leftovers():
    with patch("c64lib.cli.Session") as S:
        S.stop_all.side_effect = SessionError(
            "stopped 'a'; could not stop 'b': Operation not permitted — still "
            "registered, check `c64 session list`")
        r = CliRunner().invoke(main, ["--json", "session", "stop", "--all"])
    assert r.exit_code == 1
    err = json.loads(r.stdout)["error"]
    assert "'a'" in err and "'b'" in err


def test_session_start_notes_the_sessions_already_running_on_stderr():
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = [_fake_session("a"), _fake_session("b")]
        S.launch.return_value = _fake_session()
        r = CliRunner().invoke(main, ["session", "start"])
    assert r.exit_code == 0, r.output
    assert ("note: 2 other session(s) already running (c64 session list)"
            in r.stderr)


def test_session_start_notice_leaves_json_stdout_alone():
    """The notice goes to stderr precisely so `--json` stays a script
    contract: stdout must still parse as exactly the start payload."""
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = [_fake_session("a")]
        S.launch.return_value = _fake_session()
        r = CliRunner().invoke(main, ["--json", "session", "start"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == {"name": "c64", "model": "c64", "pid": 1234,
                                    "port": 6502, "symbols": None}
    assert "note: 1 other session(s) already running" in r.stderr


def test_session_start_reports_a_corrupt_registry_record_as_a_json_error(
        tmp_path, monkeypatch):
    """Counting the running sessions reads the registry, and reading it can
    fail: a truncated or older-format record fails `_from_record` out of
    `_load_all()`. That has always exited 1 through `fail()` (via
    `Session.launch`, which reads the registry too), and adding the notice
    must not move it out of reach — an unhandled traceback would leave
    `--json` stdout unparseable for the script reading it.

    Unmocked on purpose: the real registry is what raises.
    """
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "truncated.json").write_text('{"name": "truncated", "pid": 1}', encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "session", "start"])
    assert r.exit_code == 1, r.output
    error = json.loads(r.stdout)["error"]
    assert "port" in error, \
        "the error never names the key the record is missing"
    assert "truncated.json" in error, \
        "the error never names the record on disk that is wrong"


def test_session_stop_all_reports_a_corrupt_registry_record_as_a_json_error(
        tmp_path, monkeypatch):
    """`stop --all` is the RECOVERY command, and reading a record is as
    failure-prone as stopping what it describes: with the read above the try
    a truncated record escaped as a traceback over an empty `--json` stdout,
    from the one command that could have cleared it.

    So: exit 1 with a parseable payload naming the file, and the record gone
    — a second run has nothing left to trip over. Unmocked on purpose: the
    real registry is what raises.
    """
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "truncated.json").write_text('{"name": "truncated", "pid": 1}', encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "session", "stop", "--all"])
    assert r.exit_code == 1, r.output
    error = json.loads(r.stdout)["error"]
    assert "truncated.json" in error and "port" in error, \
        "the error never says which record on disk is wrong, or how"
    assert not (sessions / "truncated.json").exists(), \
        "the record that broke the only command for removing it is still there"
    again = CliRunner().invoke(main, ["--json", "session", "stop", "--all"])
    assert again.exit_code == 0, again.output
    assert json.loads(again.stdout) == {"stopped": []}


def test_session_list_reports_a_corrupt_record_as_json(tmp_path, monkeypatch):
    """`session list` calls `Session.list_all()` bare, outside any try, so the
    `SessionError` a truncated record raises reaches the CLI with no command
    handling it — the boundary guard on `JsonAwareGroup` is what makes it a
    payload instead of a traceback over empty `--json` stdout.

    Deliberately *not* fixed by wrapping this one call site: patching this
    defect class per command had already been tried six times over, and twice
    the next instance got past review anyway. Unmocked on purpose: the real
    registry is what raises.
    """
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "truncated.json").write_text('{"name": "truncated", "pid": 1}', encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "session", "list"])
    error = assert_json_error(r)["error"]
    assert "truncated.json" in error and "port" in error, \
        "the error never says which record on disk is wrong, or how"


def test_session_start_says_nothing_when_no_other_session_is_running():
    with patch("c64lib.cli.Session") as S:
        S.list_all.return_value = []
        S.launch.return_value = _fake_session()
        r = CliRunner().invoke(main, ["session", "start"])
    assert r.exit_code == 0, r.output
    assert "note:" not in r.stdout and "note:" not in r.stderr
