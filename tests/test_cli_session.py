import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main
from c64lib.session import SessionError


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
    lbl.write_text("al C:0824 .mainloop\n")
    s = Mock()
    s.name, s.model, s.pid, s.port = "c64", "c64", 1, 6510
    with patch("c64lib.cli.Session") as S:
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
    lbl.write_text("al C:8009 .cart_main\n")
    s = Mock()
    s.name, s.model, s.pid, s.port = "c64", "c64", 1, 6510
    with patch("c64lib.cli.Session") as S:
        S.launch.return_value = s
        r = CliRunner().invoke(
            main, ["--json", "session", "start", "--cart", str(crt)])
    assert r.exit_code == 0, r.output
    s.set_labels_path.assert_called_once_with(str(lbl))


def test_session_start_failure_is_json_error():
    with patch("c64lib.cli.Session") as S:
        S.launch.side_effect = SessionError("x64sc not found")
        r = CliRunner().invoke(main, ["--json", "session", "start"])
    assert r.exit_code == 1
    assert "x64sc not found" in json.loads(r.output)["error"]


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
