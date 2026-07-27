import os
import shutil
from pathlib import Path

import pytest

from c64lib.disk import (
    DiskError,
    blocks_for,
    build_disk,
    create_image,
    list_files,
    load_disk_manifest,
    put_file,
)
from c64lib.symbols import parse_labels

needs_c1541 = pytest.mark.skipif(shutil.which("c1541") is None,
                                 reason="needs VICE's c1541")
needs_cc65 = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("ca65", "ld65")), reason="needs cc65")


def write_manifest(tmp_path, text, name="game.disk.yaml"):
    (tmp_path / "loader.prg").write_bytes(b"\x01\x08loader payload")
    (tmp_path / "level1.bin").write_bytes(b"\x00" * 300)
    p = tmp_path / name
    p.write_text(text)
    return p


BASIC_MANIFEST = """\
label: MYGAME
id: "01"
files:
  - {src: loader.prg, name: "*"}
  - {src: level1.bin, name: level1}
"""


def test_manifest_parses_label_id_and_order(tmp_path):
    spec = load_disk_manifest(write_manifest(tmp_path, BASIC_MANIFEST))
    assert spec["label"] == "MYGAME"
    assert spec["id"] == "01"
    assert [f["src"].name for f in spec["files"]] == ["loader.prg", "level1.bin"]
    assert spec["files"][0]["name"] == "*"


def test_manifest_defaults_the_disk_id(tmp_path):
    spec = load_disk_manifest(
        write_manifest(tmp_path, "label: G\nfiles:\n  - {src: loader.prg}\n"))
    assert spec["id"] == "00"


def test_manifest_requires_files(tmp_path):
    p = tmp_path / "empty.disk.yaml"
    p.write_text("label: G\nfiles: []\n")
    with pytest.raises(DiskError, match="non-empty `files:`"):
        load_disk_manifest(p)


def test_manifest_names_a_missing_source(tmp_path):
    p = tmp_path / "m.disk.yaml"
    p.write_text("label: G\nfiles:\n  - {src: gone.bin}\n")
    with pytest.raises(DiskError, match="gone.bin"):
        load_disk_manifest(p)


def test_manifest_names_a_missing_manifest(tmp_path):
    with pytest.raises(DiskError, match="no such disk manifest"):
        load_disk_manifest(tmp_path / "absent.disk.yaml")


def test_build_rejects_an_unknown_model_before_writing(tmp_path):
    p = write_manifest(tmp_path, BASIC_MANIFEST)
    out = tmp_path / "m.d64"
    with pytest.raises(KeyError, match="unknown machine profile"):
        build_disk(p, out=out, model="c128")
    assert not out.exists()


def test_manifest_rejects_a_bad_label(tmp_path):
    p = write_manifest(tmp_path, 'label: "way too long a disk label"\n'
                                 "files:\n  - {src: loader.prg}\n")
    with pytest.raises(DiskError, match="16"):
        load_disk_manifest(p)


def test_manifest_rejects_a_bad_disk_id(tmp_path):
    p = write_manifest(tmp_path, 'label: G\nid: "toolong"\n'
                                 "files:\n  - {src: loader.prg}\n")
    with pytest.raises(DiskError, match="two characters"):
        load_disk_manifest(p)


def test_manifest_rejects_a_disk_id_c1541_would_reparse(tmp_path):
    # Measured: `c1541 -format "g,ab,cd"` exits 0 and formats the disk with id
    # `ab`, dropping `cd` — a comma in the id silently changes what is written.
    p = write_manifest(tmp_path, 'label: G\nid: "a,"\n'
                                 "files:\n  - {src: loader.prg}\n")
    with pytest.raises(DiskError, match="disk id"):
        load_disk_manifest(p)


def test_manifest_explains_an_unquoted_disk_id(tmp_path):
    # Measured: PyYAML reads `id: 01` as the int 1, so the bare length error
    # would name a value the manifest never wrote. The message has to say why.
    p = write_manifest(tmp_path, "label: G\nid: 01\n"
                                 "files:\n  - {src: loader.prg}\n")
    with pytest.raises(DiskError, match="quote") as exc:
        load_disk_manifest(p)
    assert 'id: "01"' in str(exc.value)


def test_an_uncoercible_disk_id_is_not_told_to_quote_an_illegal_value(tmp_path):
    # `id: 12345` is an int too, so the YAML explanation still applies — but
    # zfill(2) is a no-op here, so suggesting `id: "12345"` would recommend a
    # value the very next length check rejects.
    p = write_manifest(tmp_path, "label: G\nid: 12345\n"
                                 "files:\n  - {src: loader.prg}\n")
    with pytest.raises(DiskError) as exc:
        load_disk_manifest(p)
    assert "parsed by YAML" in str(exc.value)
    assert "quote it" not in str(exc.value)


def test_manifest_rejects_an_unknown_key_in_a_file_entry(tmp_path):
    p = write_manifest(tmp_path, "label: G\n"
                                 "files:\n  - {src: loader.prg, nmae: boot}\n")
    with pytest.raises(DiskError, match="nmae"):
        load_disk_manifest(p)


def test_manifest_rejects_a_directory_source(tmp_path):
    # Measured: c1541 writes a directory path as a 1-block file at exit 0 —
    # a junk entry on the disk that reports as a successful build.
    (tmp_path / "assets").mkdir()
    p = write_manifest(tmp_path, "label: G\n"
                                 "files:\n  - {src: assets, name: assets}\n")
    out = tmp_path / "junk.d64"
    with pytest.raises(DiskError, match="assets"):
        build_disk(p, out=out)
    assert not out.exists()


def test_manifest_rejects_duplicate_names(tmp_path):
    p = write_manifest(tmp_path, """\
label: G
files:
  - {src: loader.prg, name: same}
  - {src: level1.bin, name: same}
""")
    with pytest.raises(DiskError, match="'same' appears twice"):
        load_disk_manifest(p)


def test_manifest_rejects_a_name_c1541_would_truncate(tmp_path):
    # Measured: c1541 -write with a 20-character name exits 0 and stores the
    # first 16 characters, so two long names can collide into one file.
    (tmp_path / "a_very_long_source_name.bin").write_bytes(b"\x00")
    p = tmp_path / "m.disk.yaml"
    p.write_text("label: G\nfiles:\n  - {src: a_very_long_source_name.bin}\n")
    with pytest.raises(DiskError, match="16"):
        load_disk_manifest(p)


@needs_c1541
def test_build_writes_files_in_order_with_the_first_autostartable(tmp_path):
    res = build_disk(write_manifest(tmp_path, BASIC_MANIFEST))
    d = list_files(res["image"])
    assert [f["name"] for f in d["files"]] == ["mygame", "level1"]
    assert d["label"].strip() == "mygame"
    assert res["blocks_used"] + res["blocks_free"] == res["blocks_total"] == 664
    assert res["run"].endswith(res["image"])
    # The overflow guard budgets with blocks_for; pin that its prediction is
    # what the finished image actually spends (15 bytes -> 1, 300 -> 2).
    assert res["blocks_used"] == blocks_for(15) + blocks_for(300) == 3


@needs_c1541
def test_build_picks_the_image_type_from_the_output_extension(tmp_path):
    out = tmp_path / "big.d81"
    res = build_disk(write_manifest(tmp_path, BASIC_MANIFEST), out=out)
    assert res["blocks_total"] == 3160
    assert res["image"] == str(out)
    assert res["blocks_used"] == blocks_for(15) + blocks_for(300)


@needs_c1541
def test_build_fills_a_d71(tmp_path):
    out = tmp_path / "two_sided.d71"
    res = build_disk(write_manifest(tmp_path, BASIC_MANIFEST), out=out)
    assert res["blocks_total"] == 1328
    assert res["blocks_used"] == blocks_for(15) + blocks_for(300)
    assert res["blocks_used"] + res["blocks_free"] == 1328
    assert [f["name"] for f in list_files(out)["files"]] == ["mygame", "level1"]


def test_build_refuses_to_overflow_before_writing_anything(tmp_path):
    # No c1541 needed: the refusal must land before the image is formatted.
    (tmp_path / "huge.bin").write_bytes(b"\x00" * 200_000)
    p = write_manifest(tmp_path, """\
label: G
files:
  - {src: loader.prg, name: "*"}
  - {src: huge.bin, name: huge}
""")
    out = tmp_path / "over.d64"
    # 200,000 bytes = 788 blocks; a d64 holds 664.
    with pytest.raises(DiskError, match=r"huge.*788 blocks.*664"):
        build_disk(p, out=out)
    assert not out.exists(), "an overflowing build must not leave an image"


def test_build_refuses_more_files_than_the_directory_holds(tmp_path):
    # Measured: a d64 takes 144 directory entries; the 145th c1541 -write fails
    # with "ERR = 72, DISK FULL" after the first 144 have already landed, even
    # with 520 blocks still free. Block cost alone cannot predict that.
    lines = ["label: G", "files:"]
    for i in range(145):
        (tmp_path / f"f{i:03d}.bin").write_bytes(b"\x00")
        lines.append(f"  - {{src: f{i:03d}.bin}}")
    p = tmp_path / "many.disk.yaml"
    p.write_text("\n".join(lines) + "\n")
    out = tmp_path / "many.d64"
    with pytest.raises(DiskError, match=r"145 files.*144"):
        build_disk(p, out=out)
    assert not out.exists()


MIDWRITE_MANIFEST = """\
label: KEEPER
files:
  - {src: loader.prg, name: "*"}
  - {src: locked.bin, name: locked}
"""


def _make_unreadable(path):
    """chmod a file unreadable, skipping where that has no effect (root)."""
    os.chmod(path, 0o000)
    try:
        path.read_bytes()
    except OSError:
        return
    pytest.skip("cannot make a file unreadable here (running as root?)")


@needs_c1541
def test_build_keeps_the_previous_image_when_a_write_fails(tmp_path):
    # Measured: c1541 -write of a chmod-000 source exits 1 with "cannot read
    # file ... Permission denied". That lands mid-loop, after the first file
    # has been written — the case that must not cost the previous image.
    locked = tmp_path / "locked.bin"
    locked.write_bytes(b"\x00" * 300)
    p = write_manifest(tmp_path, MIDWRITE_MANIFEST)
    out = tmp_path / "keeper.d64"
    build_disk(p, out=out)
    before = out.read_bytes()

    _make_unreadable(locked)
    try:
        with pytest.raises(DiskError):
            build_disk(p, out=out)
    finally:
        os.chmod(locked, 0o644)

    assert out.read_bytes() == before, "a failed build must not touch the old image"
    assert [f["name"] for f in list_files(out)["files"]] == ["keeper", "locked"]
    strays = [q.name for q in tmp_path.rglob("*")
              if q.suffix == ".d64" and q != out]
    assert not strays, f"a failed build left {strays} behind"
    assert not [q.name for q in tmp_path.iterdir() if q.name.startswith(".")], \
        "the staging directory must be cleaned up"


@needs_c1541
def test_build_leaves_no_image_when_the_first_write_fails(tmp_path):
    locked = tmp_path / "locked.bin"
    locked.write_bytes(b"\x00" * 300)
    p = write_manifest(tmp_path, MIDWRITE_MANIFEST)
    out = tmp_path / "fresh.d64"
    _make_unreadable(locked)
    try:
        with pytest.raises(DiskError):
            build_disk(p, out=out)
    finally:
        os.chmod(locked, 0o644)
    assert not out.exists()
    assert not list(tmp_path.rglob("*.d64"))
    assert not [q.name for q in tmp_path.iterdir() if q.name.startswith(".")]


@needs_c1541
def test_put_file_reports_a_write_c1541_refused(tmp_path):
    # Measured: the second write of the same name answers
    # "ERR = 63, FILE EXISTS" — put_file must not report that as success.
    img = create_image(tmp_path / "dup.d64", label="dup")
    src = tmp_path / "t.prg"
    src.write_bytes(b"\x01\x08hi")
    put_file(img, src, "dup")
    with pytest.raises(DiskError):
        put_file(img, src, "dup")


@needs_c1541
@needs_cc65
def test_build_assembles_and_tokenizes_sources(tmp_path):
    (tmp_path / "boot.bas").write_text('10 print "hi"\n')
    (tmp_path / "code.s").write_text(
        '.segment "LOADADDR"\n        .word $0801\n'
        '.segment "CODE"\nstart: rts\n')
    (tmp_path / "level1.bin").write_bytes(b"\x00" * 300)
    p = tmp_path / "m.disk.yaml"
    p.write_text("""\
label: MIXED
files:
  - {src: boot.bas, name: "*"}
  - {src: code.s, name: code}
  - {src: level1.bin, name: level1}
""")
    res = build_disk(p)
    assert [f["name"] for f in list_files(res["image"])["files"]] == [
        "mixed", "code", "level1"]

    # The .lbl build_asm produced lives in a temp workdir that dies with the
    # build, so it is copied beside the image: without it a program loaded off
    # the disk has no symbol table for `until`/`poke` steps.
    assert set(res["labels"]) == {"code"}, "only the .s entry has symbols"
    lbl = Path(res["labels"]["code"])
    assert lbl.exists() and lbl.parent == Path(res["image"]).parent
    assert lbl.name == "m.code.lbl"
    assert "start" in parse_labels(lbl.read_text())


@needs_c1541
def test_build_reports_no_labels_when_nothing_was_assembled(tmp_path):
    res = build_disk(write_manifest(tmp_path, BASIC_MANIFEST))
    assert res["labels"] == {}
