import json
from unittest.mock import Mock, call, patch

from click.testing import CliRunner

from c64lib.cli import main, parse_number


def test_parse_number():
    assert parse_number("$0400") == 0x0400
    assert parse_number("0x0400") == 0x0400
    assert parse_number("1024") == 1024


def _patched(mon):
    fake = Mock()
    fake.name, fake.model, fake.socket = "c64", "c64", None
    fake.profile.screen_cols, fake.profile.screen_rows = 40, 25
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    p = patch("c64lib.cli.Session")
    return fake, p


def _fake(labels=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", labels
    fake.profile.screen_cols, fake.profile.screen_rows = 40, 25
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def _vic_reads(data: bytes, screen: int = 0x0400):
    """A memory_read side effect that answers the $DD00/$D018 reads
    screen_base() makes (so `mem read`'s auto gloss can locate the live
    screen) and returns `data` for every other read."""
    bank, rest = divmod(screen, 0x4000)
    slot = rest // 0x0400

    def read(a, n):
        if a == 0xDD00:
            return bytes([(~bank) & 3])
        if a == 0xD018:
            return bytes([slot << 4])
        return data

    return read


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
    # screen relocated to $c000, so $0400 is plain memory: ASCII gutter.
    mon.memory_read.side_effect = _vic_reads(bytes(range(16)), screen=0xC000)
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$0400", "16"])
    assert r.exit_code == 0
    assert r.output.startswith("0400: 00 01 02")
    assert "# text column: ascii" in r.output
    assert call(0x0400, 16) in mon.memory_read.call_args_list
    mon.release.assert_called_once()


def test_mem_read_glosses_screen_ram_as_screen_codes():
    """The gutter's whole job: bytes that *are* screen codes read as text.
    13 01 0c 05 13 is SALES on screen; ASCII would print `.....`."""
    mon = Mock()
    mon.memory_read.side_effect = _vic_reads(b"\x13\x01\x0c\x05\x13")
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$0400", "5"])
    assert r.exit_code == 0, r.output
    assert "SALES" in r.output
    assert "# text column: screen codes" in r.output


def test_mem_read_follows_a_relocated_screen():
    """screen_base() reads $DD00/$D018, so a program that moved the screen
    to $c000 gets the screen gloss there and ASCII at $0400."""
    mon = Mock()
    mon.memory_read.side_effect = _vic_reads(b"\x13\x01\x0c\x05\x13",
                                             screen=0xC000)
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$c000", "5"])
    assert r.exit_code == 0, r.output
    assert "SALES" in r.output and "# text column: screen codes" in r.output


def test_mem_read_outside_the_screen_keeps_the_ascii_gutter():
    mon = Mock()
    mon.memory_read.side_effect = _vic_reads(b"SALES")
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$c000", "5"])
    assert r.exit_code == 0, r.output
    assert "SALES" in r.output
    assert "# text column: ascii" in r.output


def test_mem_read_as_ascii_forces_the_old_gloss_on_screen_ram():
    mon = Mock()
    mon.memory_read.side_effect = _vic_reads(b"SALES")
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$0400", "5", "--as", "ascii"])
    assert r.exit_code == 0, r.output
    assert "SALES" in r.output and "# text column: ascii" in r.output
    # an explicit --as needs no VIC state: one read, the one asked for
    mon.memory_read.assert_called_once_with(0x0400, 5)


def test_mem_read_as_screen_forces_screen_codes_anywhere():
    mon = Mock()
    mon.memory_read.side_effect = _vic_reads(b"\x13\x01\x0c\x05\x13")
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$2000", "5", "--as", "screen"])
    assert r.exit_code == 0, r.output
    assert "SALES" in r.output and "# text column: screen codes" in r.output
    mon.memory_read.assert_called_once_with(0x2000, 5)


def test_mem_read_as_petscii_glosses_keyboard_bound_bytes():
    mon = Mock()
    mon.memory_read.side_effect = _vic_reads(b"\x53\x41\x4c\x45\x53")
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$0400", "5", "--as", "petscii"])
    assert r.exit_code == 0, r.output
    assert "SALES" in r.output and "# text column: petscii" in r.output


def test_mem_read_json_reports_the_resolved_text_encoding():
    mon = Mock()
    mon.memory_read.side_effect = _vic_reads(b"\x13\x01\x0c\x05\x13")
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "mem", "read", "$0400", "5"])
        assert json.loads(r.output)["text_encoding"] == "screen"
        r2 = CliRunner().invoke(main, ["--json", "mem", "read", "$0400", "5",
                                       "--as", "ascii"])
    assert json.loads(r2.output)["text_encoding"] == "ascii"


def test_mem_read_labels_the_fallback_when_vic_state_is_unreadable():
    """Never guess silently: if the VIC/CIA read fails we cannot know where
    the screen is, so we say ASCII *and* say why."""
    mon = Mock()

    def read(a, n):
        if a in (0xDD00, 0xD018):
            raise TimeoutError("no response to MEMORY_GET")
        return b"\x13\x01\x0c\x05\x13"

    mon.memory_read.side_effect = read
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$0400", "5"])
    assert r.exit_code == 0, r.output
    assert "# text column: ascii (VIC state unreadable)" in r.output


def test_mem_write():
    mon = Mock()
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "write", "$0400", "0x01", "2", "$FF"])
    assert r.exit_code == 0
    mon.memory_write.assert_called_once_with(0x0400, bytes([1, 2, 0xFF]))
    mon.release.assert_called_once()


def test_mem_write_accepts_a_whitespace_separated_string():
    """A shell variable expands to one token under zsh; that's a byte list."""
    mon = Mock()
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "write", "$0400", "0 0 1 4 9 0"])
    assert r.exit_code == 0, r.output
    mon.memory_write.assert_called_once_with(0x0400, bytes([0, 0, 1, 4, 9, 0]))


def test_mem_write_bad_byte_is_a_clean_error_not_a_traceback():
    mon = Mock()
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "write", "$0400", "1", "x9"])
    assert r.exit_code == 1, r.output
    assert "Traceback" not in r.output
    assert "x9" in r.output


def test_mem_write_out_of_range_byte_is_a_clean_error():
    mon = Mock()
    fake, p = _patched(mon)
    with p as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "mem", "write", "$0400", "300"])
    assert r.exit_code == 1, r.output
    assert "out of range" in json.loads(r.output)["error"]


def test_mem_read_bad_length_is_a_clean_error():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "read", "$0400", "bogus"])
    assert r.exit_code == 1, r.output
    assert "Traceback" not in r.output
    assert "bogus" in r.output


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
    s.profile.screen_cols, s.profile.screen_rows = 40, 25
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
    # auto encoding adds the $DD00/$D018 reads screen_base() makes
    assert call(0x06BC, 1) in mon.memory_read.call_args_list
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
    assert json.loads(r.output) == {
        "addr": 0x0400, "values": [1, 2, 3], "bytes": [1, 2, 3]}


def test_mem_get_color_cell_resolves_to_d800():
    """`mem get @@row,col` lands on the color matrix regardless of where
    the screen sits — the arithmetic Snake's evidence.sh did by hand."""
    fake, mon = _fake()
    mon.memory_read.return_value = bytes([0xFD])      # 13 + open-bus nybble
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.ops.live_screen_base", return_value=0xC400):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["mem", "get", "@@5,0"])
    assert r.exit_code == 0, r.output
    mon.memory_read.assert_called_once_with(0xD800 + 5 * 40, 1)


def test_mem_read_and_mem_get_share_byte_array_keys():
    """A script written against either command's key works against both —
    the dogfood filed the silent KeyError as a tool bug."""
    fake, mon = _fake()
    mon.memory_read.return_value = bytes([42])
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        rd = CliRunner().invoke(
            main, ["--json", "mem", "read", "$0400", "1", "--as", "ascii"])
    out = json.loads(rd.output)
    assert out["values"] == out["bytes"] == [42]


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


def test_reg_names_the_rom_region_when_no_symbol_matches():
    """A PC in the KERNAL means something ($E5D1 is the direct-mode input
    loop) even with no label file loaded — the bare hex does not say so."""
    fake, mon = _fake()
    mon.registers.return_value = {"PC": 0xE5D1}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="running"):
        S.attach.return_value = fake
        human = CliRunner().invoke(main, ["reg"])
        r = CliRunner().invoke(main, ["--json", "reg"])
    assert human.exit_code == 0, human.output
    assert "(KERNAL ROM)" in human.output
    assert json.loads(r.output)["pc_region"] == "KERNAL ROM"


def test_reg_adds_no_region_noise_for_a_ram_pc():
    fake, mon = _fake()
    mon.registers.return_value = {"PC": 0x0810}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="running"):
        S.attach.return_value = fake
        human = CliRunner().invoke(main, ["reg"])
        r = CliRunner().invoke(main, ["--json", "reg"])
    assert human.exit_code == 0, human.output
    assert "(" not in human.output
    assert json.loads(r.output)["pc_region"] is None


def test_reg_prefers_the_symbol_but_still_reports_the_region(tmp_path):
    """A named symbol wins the human line; `pc_region` is in JSON either
    way, so a consumer never has to re-derive it from the address."""
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:E5D1 .keyloop\n")
    fake, mon = _fake(labels=str(lbl))
    mon.registers.return_value = {"PC": 0xE5D1}
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="running"):
        S.attach.return_value = fake
        human = CliRunner().invoke(main, ["reg"])
        r = CliRunner().invoke(main, ["--json", "reg"])
    assert "(keyloop)" in human.output and "KERNAL ROM" not in human.output
    out = json.loads(r.output)
    assert out["pc_symbol"] == "keyloop" and out["pc_region"] == "KERNAL ROM"


def test_reg_resolves_rom_labels_not_only_session_labels():
    """`reg` builds its lookup the way `rom disasm` does, so a PC sitting on
    a KERNAL routine is named even with no session label file."""
    fake, mon = _fake()
    fake.profile.basic_version = "2.0"
    mon.registers.return_value = {"PC": 0xFFD2}      # CHROUT, in the seed DB
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.machine_state", return_value="running"):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "reg"])
    assert json.loads(r.output)["pc_symbol"] == "CHROUT"


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


def test_screen_png_border_flag_threads_through():
    """--border must reach save_screenshot_png(border=...); absent it is False."""
    for argv, want in ((["--border"], True), ([], False)):
        mon = Mock()
        fake, p = _patched(mon)
        with p as S, patch("c64lib.cli.save_screenshot_png",
                           return_value=(320, 200)) as save:
            S.attach.return_value = fake
            r = CliRunner().invoke(main, ["--json", "screen", "--png",
                                          "/tmp/x.png", *argv])
        assert r.exit_code == 0, r.output
        save.assert_called_once()
        assert save.call_args.kwargs["border"] is want


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
