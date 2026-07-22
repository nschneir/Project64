import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main, parse_number


def test_parse_number():
    assert parse_number("$0400") == 0x0400
    assert parse_number("0x0400") == 0x0400
    assert parse_number("1024") == 1024


def _patched(mon):
    fake = Mock()
    fake.name, fake.model, fake.socket = "c64", "c64", None
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    p = patch("c64lib.cli.Session")
    return fake, p


def _fake(labels=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", labels
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_screen_text():
    mon = Mock()
    fake, p = _patched(mon)
    with p as S, patch("c64lib.cli.read_screen_text", return_value="READY."):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "screen"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["text"] == "READY."
    mon.release.assert_called_once()


def test_mem_read_hexdump():
    mon = Mock()
    mon.memory_read.return_value = bytes(range(16))
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$0400", "16"])
    assert r.exit_code == 0
    assert r.output.startswith("0400: 00 01 02")
    mon.memory_read.assert_called_once_with(0x0400, 16)
    mon.release.assert_called_once()


def test_mem_write():
    mon = Mock()
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "write", "$0400", "0x01", "2", "$FF"])
    assert r.exit_code == 0
    mon.memory_write.assert_called_once_with(0x0400, bytes([1, 2, 0xFF]))
    mon.release.assert_called_once()


def test_reg_get_and_set():
    mon = Mock()
    mon.registers.return_value = {"PC": 0x0801, "A": 0x2A}
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "reg"])
        assert json.loads(r.output)["registers"]["PC"] == 0x0801
        r2 = CliRunner().invoke(main, ["reg", "set", "PC", "$2000"])
    assert r2.exit_code == 0
    mon.set_register.assert_called_once_with("PC", 0x2000)


def _mem_fake(labels_path=None):
    s = Mock()
    s.labels = labels_path
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def test_mem_read_accepts_symbol(tmp_path):
    lbl = tmp_path / "t.lbl"
    lbl.write_text("al 0006BC .SCORE\n")
    fake, mon = _mem_fake(str(lbl))
    mon.memory_read.return_value = b"\x2a"
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "mem", "read", "SCORE", "1"])
    assert r.exit_code == 0, r.output
    mon.memory_read.assert_called_once_with(0x06BC, 1)
    assert json.loads(r.output)["hex"] == "2a"


def test_mem_write_accepts_symbol(tmp_path):
    lbl = tmp_path / "t.lbl"
    lbl.write_text("al 0006BA .STEPMODE\n")
    fake, mon = _mem_fake(str(lbl))
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "mem", "write", "STEPMODE", "0"])
    assert r.exit_code == 0, r.output
    mon.memory_write.assert_called_once_with(0x06BA, b"\x00")


def test_mem_read_unknown_symbol_fails():
    fake, _ = _mem_fake(None)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "mem", "read", "NOSUCH", "1"])
    assert r.exit_code == 1
    assert "NOSUCH" in json.loads(r.output)["error"]


def test_mem_read_json_has_bytes_array():
    fake, mon = _fake()
    mon.memory_read.return_value = bytes([42, 0, 255])
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "mem", "read", "$0400", "3"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["bytes"] == [42, 0, 255] and out["hex"] == "2a00ff"


def test_mem_read_decimal_human_rendering():
    fake, mon = _fake()
    mon.memory_read.return_value = bytes([42, 0])
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$0400", "2", "--decimal"])
    assert r.exit_code == 0, r.output
    assert "42 0" in r.output and "2a" not in r.output


def test_mem_get_prints_bare_decimal():
    fake, mon = _fake()
    mon.memory_read.return_value = bytes([42])
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "get", "$0400"])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == "42"
    mon.memory_read.assert_called_once_with(0x0400, 1)


def test_mem_get_json_values():
    fake, mon = _fake()
    mon.memory_read.return_value = bytes([1, 2, 3])
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "mem", "get", "$0400", "3"])
    assert json.loads(r.output) == {"addr": 0x0400, "values": [1, 2, 3]}


def test_mem_find_pattern():
    fake, mon = _fake()
    mon.memory_read.return_value = b"\x00\x2a\x00\x2a"
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "mem", "find", "$2a",
                                      "--start", "$0400", "--length", "4"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["matches"] == [0x0401, 0x0403]
    assert out["count"] == 2 and out["truncated"] is False
    assert out["pattern"] == [0x2A]


def test_reg_reports_state():
    fake, mon = _fake()
    mon.registers.return_value = {"PC": 0x1234}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="stopped"):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "reg"])
    assert json.loads(r.output)["state"] == "stopped"


def test_screen_codes_matrix():
    mon = Mock()
    mon.memory_read.return_value = bytes([81, 32, 87]) + bytes([32] * 997)
    fake, p = _patched(mon)
    fake.profile = __import__("c64lib.machines", fromlist=["get_profile"]).get_profile("c64")
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "screen", "--codes"])
    assert r.exit_code == 0, r.output
    codes = json.loads(r.output)["codes"]
    assert len(codes) == 25 and codes[0][:3] == [81, 32, 87]


def test_screen_style_ascii():
    mon = Mock()
    mon.memory_read.return_value = bytes([81, 64, 87]) + bytes([32] * 997)
    fake, p = _patched(mon)
    fake.profile = __import__("c64lib.machines", fromlist=["get_profile"]).get_profile("c64")
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["screen", "--style", "ascii"])
    assert r.exit_code == 0, r.output
    assert r.output.splitlines()[0] == "·-·"


def test_screen_png_scale():
    mon = Mock()
    fake, p = _patched(mon)
    with p as S, patch("c64lib.cli.save_screenshot_png",
                       return_value=(760, 500)) as save:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "screen", "--png", "/tmp/x.png",
                                      "--scale", "2"])
    assert r.exit_code == 0, r.output
    save.assert_called_once()
    assert save.call_args.kwargs["scale"] == 2
    assert json.loads(r.output)["width"] == 760


def test_mem_write_stdin():
    mon = Mock()
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "write", "--stdin"],
                               input="$1000 1 2 3\n$2000 $ff\n")
    assert r.exit_code == 0, r.output
    calls = mon.memory_write.call_args_list
    assert calls[0].args == (0x1000, bytes([1, 2, 3]))
    assert calls[1].args == (0x2000, bytes([0xFF]))
