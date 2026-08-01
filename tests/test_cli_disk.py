import json
from pathlib import Path
from unittest.mock import Mock, patch

import click
import pytest
from click.testing import CliRunner

from c64lib.build import BuildError
from c64lib.cli import main
from c64lib.disk import DiskError

needs_c1541 = pytest.mark.needs_c1541


def make_image(tmp_path, *names):
    """A real d64 with one 1-block file per name (default: 'alpha')."""
    img = tmp_path / "game.d64"
    payload = tmp_path / "f1.prg"
    payload.write_bytes(b"\x01\x08hello world payload")
    r = CliRunner().invoke(main, ["disk", "create", str(img), "--label", "mygame"])
    assert r.exit_code == 0, r.output
    for name in names or ("alpha",):
        r = CliRunner().invoke(main, ["disk", "put", str(img), str(payload), name])
        assert r.exit_code == 0, r.output
    return img


def test_disk_create():
    with patch("c64lib.cli.create_image", return_value=Path("/tmp/x.d64")) as ci:
        r = CliRunner().invoke(main, ["--json", "disk", "create", "/tmp/x.d64", "--label", "work"])
    assert r.exit_code == 0, r.output
    ci.assert_called_once_with(Path("/tmp/x.d64"), label="work", disk_id="00")
    assert json.loads(r.output)["image"].endswith("x.d64")


def test_disk_ls(tmp_path):
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    listing = {"label": "work", "files": [{"blocks": 1, "name": "demo", "type": "prg"}],
               "blocks_free": 663}
    with patch("c64lib.cli.list_files", return_value=listing):
        r = CliRunner().invoke(main, ["--json", "disk", "ls", str(img)])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["files"][0]["name"] == "demo"


def test_disk_put_and_get(tmp_path):
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    f = tmp_path / "prog.prg"
    f.write_bytes(b"\x01\x08")
    with patch("c64lib.cli.put_file", return_value="prog") as pf:
        r = CliRunner().invoke(main, ["disk", "put", str(img), str(f)])
    assert r.exit_code == 0, r.output
    pf.assert_called_once_with(img, f, None)

    with patch("c64lib.cli.get_file", return_value=tmp_path / "demo.prg") as gf:
        r2 = CliRunner().invoke(main, ["disk", "get", str(img), "demo",
                                       str(tmp_path / "demo.prg")])
    assert r2.exit_code == 0, r2.output
    gf.assert_called_once_with(img, "demo", tmp_path / "demo.prg")


def test_disk_boot(tmp_path):
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", None
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["disk", "boot", str(img)])
    assert r.exit_code == 0, r.output
    mon.autostart.assert_called_once_with(img.resolve(), run=True)
    mon.resume.assert_called_once()


def test_disk_boot_registers_a_sibling_label_file(tmp_path):
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    lbl = tmp_path / "t.lbl"
    lbl.write_text("al C:0824 .mainloop\n")
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", None
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "disk", "boot", str(img)])
    assert r.exit_code == 0, r.output
    fake.set_labels_path.assert_called_once_with(str(lbl))
    assert json.loads(r.output)["symbols"] == str(lbl)


def test_disk_boot_without_labels_is_silent(tmp_path):
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", None
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.disk.list_files", side_effect=DiskError("no c1541")):
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "disk", "boot", str(img)])
    assert r.exit_code == 0, r.output
    fake.set_labels_path.assert_not_called()
    assert json.loads(r.output)["symbols"] is None


@needs_c1541
def test_cli_rename_and_rm(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["disk", "rename", str(img), "alpha", "beta"])
    assert r.exit_code == 0, r.output
    assert "beta" in r.output
    r = CliRunner().invoke(main, ["--json", "disk", "ls", str(img)])
    assert [f["name"] for f in json.loads(r.output)["files"]] == ["beta"]
    r = CliRunner().invoke(main, ["--json", "disk", "rm", str(img), "beta"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"image": str(img), "name": "beta", "deleted": 1}
    r = CliRunner().invoke(main, ["disk", "rm", str(img), "beta"])
    assert r.exit_code != 0 and "no file named" in r.output


@needs_c1541
def test_cli_rename_json_shape(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["--json", "disk", "rename", str(img), "alpha", "beta"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"image": str(img), "old": "alpha", "name": "beta"}


@needs_c1541
def test_cli_rename_and_rm_echo_the_normalized_name(tmp_path):
    """The payload must say what the operation actually did.

    Every lookup goes through cbm_lookup_name, which lower-cases — so echoing
    the caller's raw argument put `{"old": "ALPHA", "name": "beta"}` in one
    payload, two spellings of the same convention side by side, and told a
    scripted caller its `rm` had matched `AL*` when what ran was `al*`.
    """
    img = make_image(tmp_path, "alpha", "album")
    r = CliRunner().invoke(main, ["--json", "disk", "rename", str(img),
                                  "ALPHA", "BETA"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"image": str(img), "old": "alpha",
                                    "name": "beta"}
    r = CliRunner().invoke(main, ["--json", "disk", "rm", str(img), "AL*"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"image": str(img), "name": "al*",
                                    "deleted": 1}


@needs_c1541
def test_cli_rename_reports_a_missing_source_file(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["disk", "rename", str(img), "nope", "beta"])
    assert r.exit_code != 0 and "file not found" in r.output.lower()


def test_cli_rm_alias_delete_exists():
    disk = main.commands["disk"]
    # click types Group.commands as dict[str, Command], so a nested group
    # comes back as the base class; assert what `disk` actually is.
    assert isinstance(disk, click.Group)
    assert "delete" in disk.commands


@needs_c1541
def test_cli_rm_counts_wildcard_matches(tmp_path):
    img = make_image(tmp_path, "alpha", "album", "other")
    r = CliRunner().invoke(main, ["--json", "disk", "rm", str(img), "al*"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["deleted"] == 2
    r = CliRunner().invoke(main, ["--json", "disk", "ls", str(img)])
    assert [f["name"] for f in json.loads(r.output)["files"]] == ["other"]


@needs_c1541
def test_cli_rm_rejects_a_dos_metacharacter(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["--json", "disk", "delete", str(img), "al,pha"])
    assert r.exit_code != 0
    assert "metacharacter" in json.loads(r.output)["error"]


@needs_c1541
def test_cli_block_read_hexdumps_and_writes_a_file(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["disk", "block", "read", str(img), "18", "0"])
    assert r.exit_code == 0, r.output
    assert "0000: 12 01 41 00" in r.output      # the BAM header
    r = CliRunner().invoke(main, ["--json", "disk", "block", "read", str(img), "18", "0"])
    data = json.loads(r.output)
    # "hex" is the key `c64 mem read` uses for a hex string; block read matches it.
    assert data["bytes"] == 256 and data["hex"].startswith("12014100")
    assert "data" not in data
    assert data["track"] == 18 and data["sector"] == 0
    out = tmp_path / "bam.bin"
    r = CliRunner().invoke(main, ["disk", "block", "read", str(img), "18", "0",
                                  "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert out.stat().st_size == 256


@needs_c1541
def test_cli_block_read_reports_an_unwritable_output(tmp_path):
    """A dump the host refuses must be a message, not a traceback — the same
    contract `c64 cart dump` keeps."""
    img = make_image(tmp_path)
    out = tmp_path / "no-such-dir" / "bam.bin"
    r = CliRunner().invoke(main, ["--json", "disk", "block", "read", str(img),
                                  "18", "0", "-o", str(out)])
    assert r.exit_code == 1
    assert isinstance(r.exception, SystemExit)      # a message, not a traceback
    assert str(out) in json.loads(r.output)["error"]


@needs_c1541
def test_cli_block_read_rejects_a_bad_track(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["disk", "block", "read", str(img), "40", "0"])
    assert r.exit_code != 0 and "track 40 out of range" in r.output


@needs_c1541
def test_cli_block_write_from_a_file_and_by_poke(tmp_path):
    img = make_image(tmp_path)
    src = tmp_path / "sector.bin"
    src.write_bytes(bytes(range(256)))
    r = CliRunner().invoke(main, ["disk", "block", "write", str(img), "1", "0",
                                  "--from", str(src)])
    assert r.exit_code == 0, r.output
    r = CliRunner().invoke(main, ["--json", "disk", "block", "write", str(img), "1", "0",
                                  "$de", "$ad", "--offset", "4"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"image": str(img), "track": 1, "sector": 0,
                                    "written": 2, "offset": 4}
    out = tmp_path / "back.bin"
    CliRunner().invoke(main, ["disk", "block", "read", str(img), "1", "0",
                              "-o", str(out)])
    assert out.read_bytes()[4:6] == bytes([0xDE, 0xAD])
    assert out.read_bytes()[6:8] == bytes([0x06, 0x07])   # the rest is untouched


@needs_c1541
def test_cli_block_write_needs_exactly_one_source(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["disk", "block", "write", str(img), "1", "0"])
    assert r.exit_code != 0 and "--from" in r.output
    src = tmp_path / "s.bin"
    src.write_bytes(bytes(256))
    r = CliRunner().invoke(main, ["disk", "block", "write", str(img), "1", "0",
                                  "--from", str(src), "1"])
    assert r.exit_code != 0 and "--from" in r.output


@needs_c1541
def test_cli_block_write_rejects_offset_with_from(tmp_path):
    """--from replaces the whole sector, so an offset for it is contradictory:
    say so rather than accepting it and writing at 0."""
    img = make_image(tmp_path)
    src = tmp_path / "sector.bin"
    src.write_bytes(bytes(range(256)))
    for offset in ("4", "0"):
        r = CliRunner().invoke(main, ["--json", "disk", "block", "write", str(img),
                                      "1", "0", "--from", str(src),
                                      "--offset", offset])
        assert r.exit_code != 0, r.output
        assert "--offset" in json.loads(r.output)["error"]


@needs_c1541
def test_cli_block_write_reports_a_short_source_file(tmp_path):
    img = make_image(tmp_path)
    src = tmp_path / "short.bin"
    src.write_bytes(bytes(4))
    r = CliRunner().invoke(main, ["--json", "disk", "block", "write", str(img),
                                  "1", "0", "--from", str(src)])
    assert r.exit_code != 0
    assert "exactly 256" in json.loads(r.output)["error"]


@needs_c1541
def test_cli_block_write_rejects_a_poke_past_the_end(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["disk", "block", "write", str(img), "1", "0",
                                  "1", "2", "--offset", "255"])
    assert r.exit_code != 0 and "runs past the end" in r.output


def test_cli_block_write_reports_a_bad_byte_token(tmp_path):
    """The ValueError arm: a token that is not a number fails before any
    c1541 call, as a message naming the token — not a traceback."""
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    r = CliRunner().invoke(main, ["--json", "disk", "block", "write", str(img),
                                  "1", "0", "$de", "zz"])
    assert r.exit_code != 0
    assert isinstance(r.exception, SystemExit)      # a message, not a traceback
    assert "zz" in json.loads(r.output)["error"]


def test_cli_block_write_reports_an_out_of_range_byte(tmp_path):
    """Same arm, other half: 300 is not a byte. The CLI routes VALUES through
    block_bytes, so the message names the offending value and its position
    rather than repeating Python's positionless "bytes must be in range(0,
    256)"."""
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    r = CliRunner().invoke(main, ["--json", "disk", "block", "write", str(img),
                                  "1", "0", "$de", "300"])
    assert r.exit_code != 0
    assert isinstance(r.exception, SystemExit)
    err = json.loads(r.output)["error"]
    assert err == "byte 1 is 300, out of range for a byte (0-255)", err


def test_cli_validate_reports_a_disk_error(tmp_path):
    """`disk validate`'s DiskError arm — untested until now."""
    img = tmp_path / "t.d64"
    img.write_bytes(b"x")
    with patch("c64lib.cli.validate_image",
               side_effect=DiskError(
                   "cannot read image t.d64 (Permission denied)")):
        r = CliRunner().invoke(main, ["--json", "disk", "validate", str(img)])
    assert r.exit_code != 0
    assert isinstance(r.exception, SystemExit)
    assert json.loads(r.output)["error"] == \
        "cannot read image t.d64 (Permission denied)"


@pytest.mark.parametrize("exc", [DiskError("disk full: 3 block(s) over"),
                                 BuildError("ca65 failed on loader.s")])
def test_cli_build_reports_disk_and_build_errors(tmp_path, exc):
    """`disk build` catches four exception types; only the KeyError arm had a
    test. These pin the DiskError and BuildError arms."""
    with patch("c64lib.cli.build_disk", side_effect=exc):
        r = CliRunner().invoke(main, ["--json", "disk", "build",
                                      str(_manifest(tmp_path))])
    assert r.exit_code != 0
    assert isinstance(r.exception, SystemExit)
    assert json.loads(r.output)["error"] == str(exc)


@needs_c1541
def test_cli_validate(tmp_path):
    img = make_image(tmp_path)
    r = CliRunner().invoke(main, ["--json", "disk", "validate", str(img)])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["clean"] is True
    assert set(data) == {"image", "clean", "blocks_free_before", "blocks_free_after",
                         "repaired_blocks", "messages"}
    r = CliRunner().invoke(main, ["disk", "validate", str(img)])
    assert r.exit_code == 0 and "clean" in r.output


# `disk build`'s payload. `labels` is additive — it appears only when a .s
# entry produced a .lbl — so it is allowed but not required; every other key is
# mandatory and no key beyond these two sets may appear.
BUILD_KEYS = {"image", "label", "files", "blocks_used", "blocks_free",
              "blocks_total", "run"}
BUILD_OPTIONAL_KEYS = {"labels"}


def _manifest(tmp_path):
    (tmp_path / "loader.prg").write_bytes(b"\x01\x08payload")
    m = tmp_path / "game.disk.yaml"
    m.write_text('label: MYGAME\nfiles:\n  - {src: loader.prg, name: "*"}\n')
    return m


@needs_c1541
def test_cli_build_reports_blocks(tmp_path):
    r = CliRunner().invoke(main, ["disk", "build", str(_manifest(tmp_path))])
    assert r.exit_code == 0, r.output
    assert "664" in r.output and "MYGAME" in r.output
    assert (tmp_path / "game.d64").exists()
    r = CliRunner().invoke(main, ["--json", "disk", "build", str(_manifest(tmp_path)),
                                  "-o", str(tmp_path / "out.d64")])
    data = json.loads(r.output)
    assert BUILD_KEYS <= set(data) <= BUILD_KEYS | BUILD_OPTIONAL_KEYS
    assert data["files"] == ["mygame"] and data["blocks_total"] == 664


@needs_c1541
def test_cli_build_run_hint_follows_the_model(tmp_path):
    m = _manifest(tmp_path)
    r = CliRunner().invoke(main, ["--json", "disk", "build", str(m),
                                  "--model", "c64pal"])
    assert r.exit_code == 0, r.output
    run = json.loads(r.output)["run"]
    assert run.startswith("x64sc") and "-ntsc" not in run
    r = CliRunner().invoke(main, ["--json", "disk", "build", str(m), "--model", "c64"])
    assert "-ntsc" in json.loads(r.output)["run"]


def test_cli_build_rejects_an_unknown_model(tmp_path):
    r = CliRunner().invoke(main, ["--json", "disk", "build", str(_manifest(tmp_path)),
                                  "--model", "vic20"])
    assert r.exit_code != 0
    assert "unknown machine profile" in json.loads(r.output)["error"]
    assert not (tmp_path / "game.d64").exists()      # nothing written
