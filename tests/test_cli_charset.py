import json

import pytest
from click.testing import CliRunner

from c64lib.charset import CharsetError, check_label, parse_charset_file
from c64lib.cli import main

ART = "name: g\n.123\n" + "....\n" * 7


def test_charset_encode_emits_the_labeled_block(tmp_path):
    src = tmp_path / "chars.txt"
    src.write_text(ART)
    r = CliRunner().invoke(main, ["charset", "encode", str(src),
                                  "--first-code", "64"])
    assert r.exit_code == 0, r.output
    assert "glyphs:" in r.output and "glyphs_end:" in r.output
    assert "; code 64: g" in r.output
    assert ".byte   %00011011    ; .123" in r.output


def test_charset_encode_json(tmp_path):
    src = tmp_path / "chars.txt"
    src.write_text(ART)
    r = CliRunner().invoke(main, ["--json", "charset", "encode", str(src)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["glyphs"][0]["name"] == "g"
    assert out["glyphs"][0]["bytes"] == [0b00011011] + [0] * 7


def test_charset_encode_out_writes_the_file(tmp_path):
    src = tmp_path / "chars.txt"
    src.write_text(ART)
    dest = tmp_path / "chars.inc"
    r = CliRunner().invoke(main, ["charset", "encode", str(src),
                                  "-o", str(dest)])
    assert r.exit_code == 0, r.output
    assert "wrote" in r.output
    assert "glyphs_end:" in dest.read_text()


def test_charset_encode_hires(tmp_path):
    src = tmp_path / "chars.txt"
    src.write_text("name: g\n####....\n" + "........\n" * 7)
    r = CliRunner().invoke(main, ["--json", "charset", "encode", str(src),
                                  "--hires"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["glyphs"][0]["bytes"][0] == 0xF0


def test_charset_encode_bad_art_is_a_clean_error(tmp_path):
    src = tmp_path / "chars.txt"
    src.write_text("name: g\n..x.\n" + "....\n" * 7)
    r = CliRunner().invoke(main, ["--json", "charset", "encode", str(src)])
    assert r.exit_code == 1, r.output
    assert "illegal legend" in json.loads(r.output)["error"]


def test_charset_encode_missing_file():
    r = CliRunner().invoke(main, ["--json", "charset", "encode", "/nope.txt"])
    assert r.exit_code == 2, r.output
    assert "/nope.txt" in r.output


def test_charset_encode_label_renames_the_block(tmp_path):
    src = tmp_path / "chars.txt"
    src.write_text(ART)
    r = CliRunner().invoke(main, ["charset", "encode", str(src),
                                  "--label", "fontgly"])
    assert r.exit_code == 0, r.output
    assert "fontgly:" in r.output and "fontgly_end:" in r.output
    assert "glyphs:" not in r.output and "glyphs_end:" not in r.output


def test_charset_encode_label_must_be_an_identifier(tmp_path):
    src = tmp_path / "chars.txt"
    src.write_text(ART)
    r = CliRunner().invoke(main, ["--json", "charset", "encode", str(src),
                                  "--label", "font gly"])
    assert r.exit_code == 1, r.output
    assert "identifier" in json.loads(r.output)["error"]


def test_charset_encode_reports_a_file_it_cannot_decode(tmp_path):
    """A .prg or a .png handed to the encoder is an ordinary slip, and it has
    to come back as this command's exit-1 `--json` payload. `read_text` on
    binary raises UnicodeDecodeError, which `except CharsetError` does not
    catch — both subclass ValueError and neither subclasses the other — so
    it escaped as a traceback over an empty stdout, the same shape `audio
    report` was fixed for."""
    binary = tmp_path / "charset.bin"
    binary.write_bytes(bytes(range(256)))
    r = CliRunner().invoke(main, ["--json", "charset", "encode", str(binary)])
    assert r.exit_code == 1, r.output
    error = json.loads(r.stdout)["error"]
    assert str(binary) in error and "decode" in error, \
        "the error never names the file it could not read"


def test_check_label_is_one_validator_with_two_flag_spellings():
    """`c64 charset encode --label` and `c64_charset_encode label=` reject the
    same strings in the same words. Only the flag's own spelling differs, and
    that is the one thing either front end passes in — the rule itself lives
    beside `format_glyphs`, which is what the label names."""
    check_label("fontgly")                  # an identifier: no complaint
    check_label("_end2")
    with pytest.raises(CharsetError) as e:
        check_label("font gly", "--label")
    assert str(e.value) == (
        "--label 'font gly' is not an assembler identifier (letters, digits "
        "and underscore, not starting with a digit)")
    with pytest.raises(CharsetError) as e:
        check_label("9lives")
    assert str(e.value).startswith(
        "label '9lives' is not an assembler identifier (letters,")


def test_parse_charset_file_names_the_sheet_it_cannot_read(tmp_path):
    """The charset twin of `sprites.encode_sheet_file`: the read, and the
    naming of the file in whatever it raises, happen once in the library, so
    `c64 charset encode` and `c64_charset_encode` cannot drift apart.

    `read_text` on a .prg or a .png raises `UnicodeDecodeError` — which IS a
    ValueError and is NOT an OSError — whose own message is a byte offset and
    a codec: true, and no help in saying which of the paths was wrong.
    """
    binary = tmp_path / "charset.bin"
    binary.write_bytes(bytes(range(256)))
    with pytest.raises(ValueError) as e:
        parse_charset_file(binary)
    assert str(e.value).startswith(f"cannot read charset sheet {binary}: ")

    missing = tmp_path / "nope.txt"
    with pytest.raises(ValueError) as e:
        parse_charset_file(missing)
    assert str(e.value).startswith(f"cannot read charset sheet {missing}: ")

    src = tmp_path / "chars.txt"
    src.write_text(ART)
    assert [g.name for g in parse_charset_file(src)] == ["g"]
