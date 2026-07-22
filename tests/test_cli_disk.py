import json
from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main


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
