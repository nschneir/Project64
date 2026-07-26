"""The `c64 cart` group, plus the cartridge paths through package/run/session."""

import json
import shutil
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from c64lib.cartridge import CartError
from c64lib.cli import main
from c64lib.session import SessionError
from tests.test_cartridge import chip_packet, make_crt

needs_cartconv = pytest.mark.skipif(
    shutil.which("cartconv") is None, reason="cartconv not installed")


def good_body():
    body = bytearray(b"\xFF" * 0x2000)
    body[0:2] = (0x8009).to_bytes(2, "little")
    body[2:4] = (0x8009).to_bytes(2, "little")
    body[4:9] = bytes([0xC3, 0xC2, 0xCD, 0x38, 0x30])
    return bytes(body)


@pytest.fixture
def crt(tmp_path):
    return make_crt(tmp_path, name="DEMO",
                    chips=[chip_packet(0, 0x8000, good_body())])


def test_cart_info_human_and_json(crt):
    r = CliRunner().invoke(main, ["cart", "info", str(crt)])
    assert r.exit_code == 0
    assert "DEMO" in r.output and "8k" in r.output
    r = CliRunner().invoke(main, ["--json", "cart", "info", str(crt)])
    data = json.loads(r.output)
    assert data["name"] == "DEMO" and data["chips"][0]["load_addr"] == "$8000"


def test_cart_verify_is_quiet_when_clean(crt):
    r = CliRunner().invoke(main, ["cart", "verify", str(crt)])
    assert r.exit_code == 0
    assert "ok" in r.output.lower()


def test_cart_verify_exits_nonzero_with_a_reason(tmp_path):
    body = bytearray(good_body())
    body[4:9] = b"\xFF" * 5
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, bytes(body))],
                    filename="bad.crt")
    r = CliRunner().invoke(main, ["cart", "verify", str(path)])
    assert r.exit_code == 1
    assert "CBM80" in r.output


def test_cart_verify_json_reports_the_reasons(tmp_path):
    body = bytearray(good_body())
    body[4:9] = b"\xFF" * 5
    path = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, bytes(body))],
                    filename="bad.crt")
    r = CliRunner().invoke(main, ["--json", "cart", "verify", str(path)])
    assert r.exit_code == 1
    data = json.loads(r.output)
    assert data["ok"] is False and any("CBM80" in x for x in data["reasons"])


def test_cart_verify_on_a_non_cart_fails_cleanly(tmp_path):
    """cart_verify raises rather than returning reasons for unparseable files."""
    p = tmp_path / "notacart.crt"
    p.write_bytes(b"hello")
    r = CliRunner().invoke(main, ["cart", "verify", str(p)])
    assert r.exit_code == 1
    assert "not a .crt image" in r.output


def test_cart_dump_writes_the_window(tmp_path, crt):
    out = tmp_path / "bank0.bin"
    r = CliRunner().invoke(main,
                           ["cart", "dump", str(crt), "--bank", "0", "-o", str(out)])
    assert r.exit_code == 0
    assert out.read_bytes()[4:9] == bytes([0xC3, 0xC2, 0xCD, 0x38, 0x30])


def test_cart_dump_json_reports_the_written_file(tmp_path, crt):
    """The payload the MCP tool mirrors: `path` is what was WRITTEN (-o), not
    the .crt it was read from."""
    out = tmp_path / "bank0.bin"
    r = CliRunner().invoke(main, ["--json", "cart", "dump", str(crt),
                                  "--bank", "0", "--window", "lo",
                                  "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"path": str(out), "bank": 0,
                                    "window": "lo", "bytes": 8192}


def test_cart_dump_reports_a_missing_bank(tmp_path, crt):
    r = CliRunner().invoke(main, ["cart", "dump", str(crt), "--bank", "9",
                                  "-o", str(tmp_path / "x.bin")])
    assert r.exit_code != 0
    assert "bank 9" in r.output


def test_cart_dump_reports_an_unwritable_output(tmp_path, crt):
    out = tmp_path / "no-such-dir" / "bank0.bin"
    r = CliRunner().invoke(main, ["--json", "cart", "dump", str(crt),
                                  "-o", str(out)])
    assert r.exit_code == 1
    assert isinstance(r.exception, SystemExit)      # a message, not a traceback
    assert str(out) in json.loads(r.output)["error"]


def test_cart_info_on_a_non_cart_fails_cleanly(tmp_path):
    p = tmp_path / "notacart.crt"
    p.write_bytes(b"hello")
    r = CliRunner().invoke(main, ["cart", "info", str(p)])
    assert r.exit_code != 0
    assert "not a .crt image" in r.output


def test_cart_group_is_in_help():
    r = CliRunner().invoke(main, ["--help"])
    assert "cart" in r.output


def test_cart_build_reports_the_fill_table(tmp_path):
    manifest = tmp_path / "game.ef.yaml"
    manifest.write_text("name: GAME\n")
    ret = {"crt": "game.crt", "bin": "game.bin", "labels": "game.lbl",
           "title": "GAME", "cart_type": "easyflash", "run": "x64sc game.crt",
           "banks": [0], "windows": {"0hi": 12}, "fill": "bank 0 hi: 12 bytes",
           "bytes": 12, "free": 100}
    with patch("c64lib.cli.build_easyflash", return_value=ret) as be:
        r = CliRunner().invoke(main, ["cart", "build", str(manifest)])
    assert r.exit_code == 0, r.output
    assert "bank 0 hi: 12 bytes" in r.output and "x64sc game.crt" in r.output
    be.assert_called_once()


def test_cart_build_error_is_actionable(tmp_path):
    manifest = tmp_path / "game.ef.yaml"
    manifest.write_text("name: GAME\n")
    with patch("c64lib.cli.build_easyflash",
               side_effect=CartError("bank 3 lo is 40 bytes over the window")):
        r = CliRunner().invoke(main, ["--json", "cart", "build", str(manifest)])
    assert r.exit_code == 1
    assert "bank 3 lo" in json.loads(r.output)["error"]


def test_cart_bank_decodes_the_easyflash_registers():
    fake = Mock()
    mon = Mock()
    mon.memory_read.return_value = bytes([0x03, 0x00, 0x87])
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "cart", "bank"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["bank"] == 3 and data["mode"] == "16k" and data["de02"] == "$87"
    mon.memory_read.assert_called_once_with(0xDE00, 3)
    # an inspection command: it must never resume a halted machine
    mon.release.assert_called_once()
    mon.resume.assert_not_called()


@needs_cartconv
def test_cart_convert_makes_a_crt_from_a_raw_image(tmp_path):
    raw = tmp_path / "rom.bin"
    raw.write_bytes(good_body())
    out = tmp_path / "rom.crt"
    r = CliRunner().invoke(main, ["cart", "convert", str(raw), str(out),
                                  "--type", "normal", "--name", "RAW"])
    assert r.exit_code == 0, r.output
    info = json.loads(CliRunner().invoke(
        main, ["--json", "cart", "info", str(out)]).output)
    assert info["name"] == "RAW" and info["mode"] == "8k"


def test_cart_convert_surfaces_a_cartconv_failure(tmp_path):
    raw = tmp_path / "rom.bin"
    raw.write_bytes(b"\x00" * 16)
    with patch("c64lib.cli.run_cartconv",
               side_effect=CartError("cartconv failed: bad size")):
        r = CliRunner().invoke(main, ["--json", "cart", "convert", str(raw),
                                      str(tmp_path / "x.crt")])
    assert r.exit_code == 1
    assert "bad size" in json.loads(r.output)["error"]


def _fake_session(name="c64", model="c64"):
    fake = Mock()
    fake.name, fake.model, fake.pid, fake.port = name, model, 4242, 6502
    return fake


def test_session_start_attaches_a_cart(tmp_path, crt):
    with patch("c64lib.cli.Session") as S:
        S.launch.return_value = _fake_session()
        r = CliRunner().invoke(main, ["--json", "session", "start",
                                      "--cart", str(crt)])
    assert r.exit_code == 0, r.output
    S.launch.assert_called_once_with(model="c64", name=None, headless=False,
                                     warp=False, disk8=None, cart=str(crt))


def test_run_a_crt_reboots_the_session_with_it_attached(tmp_path, crt):
    old, new = _fake_session(), _fake_session()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = old
        S.launch.return_value = new
        r = CliRunner().invoke(main, ["--json", "run", str(crt)])
    assert r.exit_code == 0, r.output
    old.stop.assert_called_once()
    S.launch.assert_called_once_with(model="c64", name="c64", headless=False,
                                     warp=False, cart=str(crt.resolve()))
    data = json.loads(r.output)
    assert data["cart"] == str(crt.resolve()) and data["session"] == "c64"


def test_run_a_crt_reports_a_failed_stop_instead_of_downgrading(tmp_path, crt):
    """A stop that fails must not be read as 'there was no session': relaunching
    under the no-session defaults would silently swap a c64pal 'snake' for an
    NTSC 'c64' while the real 'snake' is possibly still alive."""
    old = _fake_session(name="snake", model="c64pal")
    old.stop.side_effect = SessionError("monitor is gone")
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = old
        r = CliRunner().invoke(main, ["--json", "run", str(crt)])
    assert r.exit_code == 1
    err = json.loads(r.output)["error"]
    assert "snake" in err and "monitor is gone" in err
    S.launch.assert_not_called()


def test_run_a_crt_with_no_session_boots_a_default_one(tmp_path, crt):
    with patch("c64lib.cli.Session") as S:
        S.attach.side_effect = SessionError("no session is running")
        S.launch.return_value = _fake_session()
        r = CliRunner().invoke(main, ["--json", "run", str(crt)])
    assert r.exit_code == 0, r.output
    S.launch.assert_called_once_with(model="c64", name=None, headless=False,
                                     warp=False, cart=str(crt.resolve()))


def test_run_a_crt_registers_its_label_file(tmp_path, crt):
    lbl = crt.with_suffix(".lbl")
    lbl.write_text("al C:8009 .cart_main\n")
    new = _fake_session()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = _fake_session()
        S.launch.return_value = new
        r = CliRunner().invoke(main, ["--json", "run", str(crt)])
    assert r.exit_code == 0, r.output
    new.set_labels_path.assert_called_once_with(str(lbl))
    assert json.loads(r.output)["symbols"] == str(lbl)
