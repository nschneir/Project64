import shutil

import pytest

from c64lib.disk import (
    DiskError,
    build_disk,
    create_image,
    list_files,
    load_disk_manifest,
    put_file,
)

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


@needs_c1541
def test_build_picks_the_image_type_from_the_output_extension(tmp_path):
    out = tmp_path / "big.d81"
    res = build_disk(write_manifest(tmp_path, BASIC_MANIFEST), out=out)
    assert res["blocks_total"] == 3160
    assert res["image"] == str(out)


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
