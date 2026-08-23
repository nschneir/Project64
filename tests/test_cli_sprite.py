import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from c64lib.cli import main
from c64lib.sprites import encode_sheet_file, encode_sprite, format_bytes


def _vic():
    # See test_sprites.py's twin: the old `**over` hook indexed a bytearray
    # with the keyword name, so it could only ever raise TypeError. Both call
    # sites here pass nothing.
    v = bytearray(0x2F)
    v[0x00], v[0x01] = 100, 120
    v[0x02], v[0x03] = 44, 55
    v[0x10] = 0b00000010                 # sprite 1 x MSB
    v[0x15] = 0b00000011
    v[0x20], v[0x21] = 14, 6
    v[0x25], v[0x26] = 10, 11
    v[0x27], v[0x28] = 7, 2
    return bytes(v)


#: what the fake emulator answers `palette()` with — deliberately nothing like
#: sprites.C64_PALETTE, so a PNG's pixels say which table rendered them.
_LIVE_PALETTE = [(i, 2 * i, 3 * i) for i in range(16)]


def _fake(mem=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", None
    fake.profile.screen_addr = 0x0400
    fake.profile.screen_cols = 40
    mon = Mock()
    mon.palette.return_value = _LIVE_PALETTE
    mem = mem or {}
    mem.setdefault(0xDD00, bytes([0b11]))
    mem.setdefault(0xD018, bytes([0x15]))
    mem.setdefault(0xD000, _vic())
    mem.setdefault(0x07F8, bytes([13, 0x80, 0, 0, 0, 0, 0, 0]))
    mem.setdefault(0x0340, bytes([0b10000000, 0, 0] + [0] * 60))
    mon.memory_read.side_effect = lambda a, n: mem[a][:n]
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_sprite_status_json():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "status"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert len(out["sprites"]) == 8
    assert out["sprites"][1]["x"] == 44 + 256          # MSB folded in
    assert out["sprites"][0]["block_addr"] == 13 * 64
    assert out["shared"]["background"] == 6
    mon.release.assert_called()


def test_sprite_status_human_table():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["sprite", "status"])
    assert r.exit_code == 0, r.output
    assert "x=300" in r.output and "on" in r.output


def test_sprite_show_block():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "show", "0",
                                      "--block", "$0340"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert len(out["rows"]) == 21
    assert out["rows"][0][0] == "█"
    assert out["block_addr"] == 0x0340


def test_sprite_show_uses_pointer():
    fake, _ = _fake({0x0340: bytes(63)})
    fake, mon = _fake()
    mem = {0x0340: bytes([0xFF] * 63)}
    mon.memory_read.side_effect = lambda a, n: {
        0xDD00: bytes([0b11]), 0xD018: bytes([0x15]), 0xD000: _vic(),
        0x07F8: bytes([13, 0, 0, 0, 0, 0, 0, 0]), **mem}[a][:n]
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "show", "0"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["block_addr"] == 13 * 64   # 832 = $0340


def test_sprite_png_writes_file(tmp_path):
    fake, _ = _fake()
    out_png = tmp_path / "s.png"
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "png", "0",
                                      "-o", str(out_png), "--scale", "2",
                                      "--block", "$0340"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["png"] == str(out_png) and (out["width"], out["height"]) == (48, 42)
    from PIL import Image
    assert Image.open(out_png).size == (48, 42)


def test_sprite_png_colors_come_from_the_live_palette(tmp_path):
    """`c64 sprite png` renders with the palette the emulator is running —
    the same `mon.palette()` `c64 screen --png` renders from. It used to use
    sprites.C64_PALETTE, and a reviewer comparing the sprite inspector's PNG
    with the evidence camera's saw two different reds for the same bytes."""
    from PIL import Image

    from c64lib.sprites import C64_PALETTE
    fake, mon = _fake()
    out_png = tmp_path / "s.png"
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "png", "0",
                                      "-o", str(out_png), "--scale", "1",
                                      "--block", "$0340"])
    assert r.exit_code == 0, r.output
    img = Image.open(out_png).convert("RGB")
    assert img.getpixel((0, 0)) == _LIVE_PALETTE[7]     # sprite 0's color
    assert img.getpixel((1, 0)) == _LIVE_PALETTE[6]     # background ($D021)
    assert img.getpixel((0, 0)) != C64_PALETTE[7]       # not the fallback
    mon.palette.assert_called()


def test_sprite_show_does_not_ask_for_the_palette():
    """The ASCII inspector is colorless and must stay that way: no palette
    round trip on a path that cannot spend it."""
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "show", "0",
                                      "--block", "$0340"])
    assert r.exit_code == 0, r.output
    mon.palette.assert_not_called()


def test_sprite_bad_index_fails():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "show", "9"])
    assert r.exit_code == 1
    assert "0-7" in json.loads(r.output)["error"]


def test_bad_index_is_rejected_before_the_machine_is_read():
    """The range check runs before any monitor traffic, so a bad index can
    never cost a round trip or surface as a MonitorError from the read."""
    fake, mon = _fake()
    mon.memory_read.side_effect = AssertionError("read the machine")
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "show", "9"])
    assert mon.memory_read.call_count == 0, "the machine was read first"
    assert r.exit_code == 1, r.output
    assert json.loads(r.output)["error"] == "sprite index 9 outside 0-7"


def test_sprite_from_png_no_session(tmp_path):
    from PIL import Image
    src = tmp_path / "in.png"
    img = Image.new("RGB", (24, 21), (255, 255, 255))
    img.putpixel((0, 0), (0, 0, 0))
    img.save(src)
    r = CliRunner().invoke(main, ["sprite", "from-png", str(src)])
    assert r.exit_code == 0, r.output
    assert ".byte %10000000" in r.output
    out_s = tmp_path / "out.s"
    r = CliRunner().invoke(main, ["--json", "sprite", "from-png", str(src),
                                  "-o", str(out_s)])
    assert r.exit_code == 0, r.output
    assert ".byte %10000000" in out_s.read_text(encoding="utf-8")
    assert len(json.loads(r.output)["bytes"]) == 63


def test_sprite_from_png_missing_file():
    """A missing input path is CLI misuse: exit 2, like every other input
    argument in the CLI, and the offending path is named in the output."""
    r = CliRunner().invoke(main, ["--json", "sprite", "from-png", "/nope.png"])
    assert r.exit_code == 2, r.output
    assert "/nope.png" in r.output


def test_sprite_from_png_corrupt_image(tmp_path):
    """A present-but-unreadable image is a runtime failure, not misuse: 1."""
    bad = tmp_path / "junk.png"
    bad.write_bytes(b"not a png at all\x00\x01\x02")
    r = CliRunner().invoke(main, ["--json", "sprite", "from-png", str(bad)])
    assert r.exit_code == 1, r.output
    assert "cannot read image" in json.loads(r.output)["error"]


# --- c64 sprite encode -------------------------------------------------

_DOT_ROW = "." * 12
_HASH_ROW = "#" * 12
_BLANK_ROW = " " * 12


def test_sprite_encode_multi_sprite_file(tmp_path):
    art_a = [_DOT_ROW] * 21
    art_b = [_HASH_ROW] * 21
    src = tmp_path / "two.txt"
    src.write_text("\n".join(art_a) + "\n\n" + "\n".join(art_b) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert len(out["sprites"]) == 2
    assert out["sprites"][0] == list(encode_sprite(art_a, multicolor=True))
    assert out["sprites"][1] == list(encode_sprite(art_b, multicolor=True))
    assert len(out["sprites"][0]) == 63 and len(out["sprites"][1]) == 63


def test_sprite_encode_all_space_row_is_not_a_separator(tmp_path):
    art = [_DOT_ROW] * 10 + [_BLANK_ROW] + [_HASH_ROW] * 10
    assert len(art) == 21
    src = tmp_path / "one.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert len(out["sprites"]) == 1                 # not split into pieces
    assert len(out["sprites"][0]) == 63
    assert out["sprites"][0] == list(encode_sprite(art, multicolor=True))


def test_sprite_encode_format_basic_emits_data_lines(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src), "--format", "basic"])
    assert r.exit_code == 0, r.output
    # lowercase: uppercase DATA is shifted PETSCII and tokenizes to junk
    assert "data " in r.output and "DATA " not in r.output
    assert ".byte" not in r.output
    expected = format_bytes(encode_sprite(art, multicolor=True), "basic")
    assert expected in r.output


def test_sprite_encode_basic_start_line_numbers_the_rows(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src), "--format",
                                  "basic", "--start-line", "1000"])
    assert r.exit_code == 0, r.output
    lines = [ln for ln in r.output.splitlines() if ln.strip()]
    assert len(lines) == 21
    assert lines[0].startswith("1000 data ")
    assert lines[1].startswith("1010 data ")
    assert lines[-1].startswith("1200 data ")


def test_sprite_encode_basic_numbering_runs_on_across_sprites(tmp_path):
    """Two sprites in one file must come out as ONE ascending listing —
    restarting the numbers would make the second block overwrite the first."""
    art = [_DOT_ROW] * 21
    src = tmp_path / "two.txt"
    src.write_text("\n".join(art) + "\n\n" + "\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src), "--format",
                                  "basic", "--start-line", "100",
                                  "--line-step", "5"])
    assert r.exit_code == 0, r.output
    numbers = [int(ln.split()[0]) for ln in r.output.splitlines() if ln.strip()]
    assert len(numbers) == 42
    assert numbers == sorted(numbers) and len(set(numbers)) == 42
    assert numbers[0] == 100 and numbers[21] == 100 + 21 * 5


def test_sprite_encode_start_line_rejected_for_asm(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src), "--format",
                                  "asm", "--start-line", "10"])
    assert r.exit_code == 1
    assert "only applies to --format basic" in r.output


def test_sprite_encode_start_line_past_the_basic_maximum_is_refused(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src), "--format",
                                  "basic", "--start-line", "63900"])
    assert r.exit_code == 1
    assert "63999" in r.output


def test_sprite_encode_format_asm_emits_byte_rows(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src), "--format", "asm"])
    assert r.exit_code == 0, r.output
    assert ".byte %" in r.output
    assert "DATA " not in r.output
    expected = format_bytes(encode_sprite(art, multicolor=True), "asm")
    assert expected in r.output


def test_sprite_encode_asm_is_row_aligned_binary_with_label(tmp_path):
    # asm output matches c64 sprite from-png's shape: a labeled block of
    # `.byte %binary` rows, one sprite row (3 bytes) per line.
    art = [_HASH_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src)])
    assert r.exit_code == 0, r.output
    assert "sprite0: .byte %" in r.output
    assert "; place in a 64-byte block; pointer = block_address / 64" in r.output
    byte_lines = [ln for ln in r.output.splitlines() if ".byte" in ln]
    assert len(byte_lines) == 21                      # one line per sprite row
    assert all(ln.count("%") == 3 for ln in byte_lines)   # 3 bytes/row


def test_sprite_encode_multi_sprite_asm_labels_are_distinct(tmp_path):
    art_a = [_DOT_ROW] * 21
    art_b = [_HASH_ROW] * 21
    src = tmp_path / "two.txt"
    src.write_text("\n".join(art_a) + "\n\n" + "\n".join(art_b) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src)])
    assert r.exit_code == 0, r.output
    assert "sprite0: .byte %" in r.output       # no colliding labels between
    assert "sprite1: .byte %" in r.output       # the two emitted blocks


def test_sprite_encode_json_emits_raw_bytes(tmp_path):
    art = [_HASH_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["sprites"] == [list(encode_sprite(art, multicolor=True))]


def test_sprite_encode_writes_out_file(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n", encoding="utf-8")
    out_path = tmp_path / "out.s"

    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src),
                                  "-o", str(out_path)])
    assert r.exit_code == 0, r.output
    expected = format_bytes(encode_sprite(art, multicolor=True), "asm")
    assert out_path.read_text(encoding="utf-8").strip() == expected
    out = json.loads(r.output)
    assert out["sprites"] == [list(encode_sprite(art, multicolor=True))]


def test_sprite_encode_missing_file():
    r = CliRunner().invoke(main, ["--json", "sprite", "encode", "/nope.txt"])
    assert r.exit_code == 2, r.output
    assert "/nope.txt" in r.output


# ---- sheet ergonomics: named blocks, comments, a visible background --------

_SHEET_HEAD = ("# La Galaxia -- the shapes, as readable art.\n"
               "#   Legend: . background   # sprite colour\n"
               "\n")


def _named_sheet() -> str:
    return (_SHEET_HEAD
            + "fighter:hires\n" + ("." * 24 + "\n") * 21
            + "\ndrone:multicolor\n" + ("." * 12 + "\n") * 21)


def test_sprite_encode_background_makes_a_named_mixed_sheet_one_invocation(tmp_path):
    src = tmp_path / "sprites.txt"
    src.write_text(_named_sheet(), encoding="utf-8")
    r = CliRunner().invoke(main, ["sprite", "encode", str(src), "--background", "."])
    assert r.exit_code == 0, r.output
    assert "; sprite 0 (fighter), 24x21 hires" in r.output
    assert "; sprite 1 (drone), 24x21 multicolor" in r.output
    assert "sprite0: .byte %" in r.output and "sprite1: .byte %" in r.output


def test_sprite_encode_background_json_has_every_block(tmp_path):
    src = tmp_path / "sprites.txt"
    src.write_text(_named_sheet(), encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src),
                                  "--background", "."])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["sprites"] == [[0] * 63, [0] * 63]
    assert [s["name"] for s in out["blocks"]] == ["fighter", "drone"]
    assert [s["multicolor"] for s in out["blocks"]] == [False, True]


def test_sprite_encode_background_must_be_one_character(tmp_path):
    src = tmp_path / "sprites.txt"
    src.write_text("\n".join([_DOT_ROW] * 21) + "\n", encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src),
                                  "--background", ".."])
    assert r.exit_code == 1, r.output
    assert "one character" in json.loads(r.output)["error"]


def test_sprite_encode_unknown_mode_is_a_clean_error(tmp_path):
    src = tmp_path / "sprites.txt"
    src.write_text("drone:mono\n" + "\n".join([_DOT_ROW] * 21) + "\n", encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src)])
    assert r.exit_code == 1, r.output
    assert "unknown mode 'mono'" in json.loads(r.output)["error"]


def test_sprite_encode_reports_a_file_it_cannot_decode(tmp_path):
    """The sprite twin of the charset case: `read_text` sat outside any try,
    so a binary file where the sheet goes was a traceback over an empty
    `--json` stdout instead of an exit-1 error object."""
    binary = tmp_path / "sprites.bin"
    binary.write_bytes(bytes(range(256)))
    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(binary)])
    assert r.exit_code == 1, r.output
    error = json.loads(r.stdout)["error"]
    assert str(binary) in error and "decode" in error, \
        "the error never names the file it could not read"


# ---- the sheet reader both front ends now share ---------------------------


def test_encode_sheet_file_rejects_an_empty_sheet_both_ways(tmp_path):
    """Two ways to hold no art, one message — pinned on the library function,
    because this is the rule the CLI and the MCP tool used to spell twice
    each. Whitespace never reaches the parser; a file of nothing but comments
    reaches it and parses to no blocks at all, which is the check that only
    the *second* test here can fail.
    """
    blank = tmp_path / "blank.txt"
    blank.write_text("\n   \n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        encode_sheet_file(blank, multicolor=True)
    assert str(e.value) == f"no sprite art found in {blank}"

    legend_only = tmp_path / "legend.txt"
    legend_only.write_text("# La Galaxia -- the shapes\n#   . background\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        encode_sheet_file(legend_only, multicolor=True)
    assert str(e.value) == f"no sprite art found in {legend_only}"


def test_encode_sheet_file_names_the_file_it_cannot_read(tmp_path):
    """A .prg or a .png where the sheet goes raises UnicodeDecodeError, whose
    own message is a byte offset and a codec — true, and no help in saying
    which of the paths in the call was wrong. It is a ValueError and NOT an
    OSError, which is exactly how both front ends once leaked a traceback.
    """
    binary = tmp_path / "sprites.bin"
    binary.write_bytes(bytes(range(256)))
    with pytest.raises(ValueError) as e:
        encode_sheet_file(binary, multicolor=True)
    assert str(e.value).startswith(f"cannot read sprite sheet {binary}: ")
    assert "decode" in str(e.value)

    missing = tmp_path / "nope.txt"
    with pytest.raises(ValueError) as e:
        encode_sheet_file(missing, multicolor=True)
    assert str(e.value).startswith(f"cannot read sprite sheet {missing}: ")


def test_encode_sheet_file_returns_the_parsed_blocks(tmp_path):
    """The happy path: the guards are not the whole function."""
    src = tmp_path / "sprites.txt"
    src.write_text(_named_sheet(), encoding="utf-8")
    blocks = encode_sheet_file(src, multicolor=True, background=".")
    assert [b.name for b in blocks] == ["fighter", "drone"]
    assert [b.multicolor for b in blocks] == [False, True]
    assert [bytes(b.data) for b in blocks] == [bytes(63)] * 2
