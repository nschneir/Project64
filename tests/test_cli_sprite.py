import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main
from c64lib.sprites import encode_sprite, format_bytes


def _vic(**over):
    v = bytearray(0x2F)
    v[0x00], v[0x01] = 100, 120
    v[0x02], v[0x03] = 44, 55
    v[0x10] = 0b00000010                 # sprite 1 x MSB
    v[0x15] = 0b00000011
    v[0x20], v[0x21] = 14, 6
    v[0x25], v[0x26] = 10, 11
    v[0x27], v[0x28] = 7, 2
    for k, val in over.items():
        v[k] = val
    return bytes(v)


def _fake(mem=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", None
    fake.profile.screen_addr = 0x0400
    fake.profile.screen_cols = 40
    mon = Mock()
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


def test_sprite_bad_index_fails():
    fake, _ = _fake()
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "sprite", "show", "9"])
    assert r.exit_code == 1
    assert "0-7" in json.loads(r.output)["error"]


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
    assert ".byte %10000000" in out_s.read_text()
    assert len(json.loads(r.output)["bytes"]) == 63


def test_sprite_from_png_missing_file():
    r = CliRunner().invoke(main, ["--json", "sprite", "from-png", "/nope.png"])
    assert r.exit_code == 1


# --- c64 sprite encode -------------------------------------------------

_DOT_ROW = "." * 12
_HASH_ROW = "#" * 12
_BLANK_ROW = " " * 12


def test_sprite_encode_multi_sprite_file(tmp_path):
    art_a = [_DOT_ROW] * 21
    art_b = [_HASH_ROW] * 21
    src = tmp_path / "two.txt"
    src.write_text("\n".join(art_a) + "\n\n" + "\n".join(art_b) + "\n")

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
    src.write_text("\n".join(art) + "\n")

    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert len(out["sprites"]) == 1                 # not split into pieces
    assert len(out["sprites"][0]) == 63
    assert out["sprites"][0] == list(encode_sprite(art, multicolor=True))


def test_sprite_encode_format_basic_emits_data_lines(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src), "--format", "basic"])
    assert r.exit_code == 0, r.output
    assert "DATA " in r.output
    assert ".byte" not in r.output
    expected = format_bytes(encode_sprite(art, multicolor=True), "basic")
    assert expected in r.output


def test_sprite_encode_format_asm_emits_byte_rows(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n")

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
    src.write_text("\n".join(art) + "\n")

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
    src.write_text("\n".join(art_a) + "\n\n" + "\n".join(art_b) + "\n")

    r = CliRunner().invoke(main, ["sprite", "encode", str(src)])
    assert r.exit_code == 0, r.output
    assert "sprite0: .byte %" in r.output       # no colliding labels between
    assert "sprite1: .byte %" in r.output       # the two emitted blocks


def test_sprite_encode_json_emits_raw_bytes(tmp_path):
    art = [_HASH_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n")

    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["sprites"] == [list(encode_sprite(art, multicolor=True))]


def test_sprite_encode_writes_out_file(tmp_path):
    art = [_DOT_ROW] * 21
    src = tmp_path / "sprite.txt"
    src.write_text("\n".join(art) + "\n")
    out_path = tmp_path / "out.s"

    r = CliRunner().invoke(main, ["--json", "sprite", "encode", str(src),
                                  "-o", str(out_path)])
    assert r.exit_code == 0, r.output
    expected = format_bytes(encode_sprite(art, multicolor=True), "asm")
    assert out_path.read_text().strip() == expected
    out = json.loads(r.output)
    assert out["sprites"] == [list(encode_sprite(art, multicolor=True))]


def test_sprite_encode_missing_file():
    r = CliRunner().invoke(main, ["--json", "sprite", "encode", "/nope.txt"])
    assert r.exit_code != 0
