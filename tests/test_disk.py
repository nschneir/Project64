from pathlib import Path

import pytest

from c64lib.disk import (
    DiskError,
    create_image,
    drive_type_for,
    get_file,
    list_files,
    put_file,
)


def test_drive_type_for():
    assert drive_type_for("a.d64") == 1541
    assert drive_type_for("b.D71") == 1571
    assert drive_type_for("c.d81") == 1581
    with pytest.raises(DiskError, match="d80"):
        drive_type_for("x.d80")


def test_missing_c1541_message(monkeypatch, tmp_path):
    monkeypatch.delenv("C64_TOOLS_C1541", raising=False)
    monkeypatch.setattr("c64lib.disk.shutil.which", lambda n: None)
    with pytest.raises(DiskError, match="[Ii]nstall"):
        create_image(tmp_path / "x.d64")


needs_c1541 = pytest.mark.needs_c1541


@needs_c1541
def test_real_c1541_roundtrip(tmp_path):
    img = create_image(tmp_path / "t.d64", label="testdisk", disk_id="01")
    assert img.exists() and img.stat().st_size > 0

    src = tmp_path / "prog.prg"
    src.write_bytes(b"\x01\x08hello")
    name = put_file(img, src, "demo")
    assert name == "demo"

    d = list_files(img)
    assert d["label"].strip() == "testdisk"
    assert d["files"][0]["name"] == "demo" and d["files"][0]["type"] == "prg"
    assert d["blocks_free"] > 0

    out = get_file(img, "demo", tmp_path / "out.prg")
    assert out.read_bytes() == src.read_bytes()


@needs_c1541
def test_real_c1541_d81(tmp_path):
    img = create_image(tmp_path / "t.d81")
    assert img.stat().st_size > 500_000  # 80-track double-sided image is big


@needs_c1541
def test_get_file_validates_the_name(tmp_path):
    """Measured: `c1541 img -read 'zed,alpha' out` exits 0 and hands back
    *zed* — the comma ends the name and what follows is CBM DOS's type/mode
    field, judged by its first character (`a` is append; `,p`/`,r`/`,w` work
    too, `,s`/`,z`/`,` exit 1, and `alpha,zed` exits 1 even though both files
    exist). It is not a second filename: the read silently returns what
    *precedes* the comma, which is still a file nobody asked for."""
    img = create_image(tmp_path / "t.d64", label="t", disk_id="01")
    for nm, body in (("alpha", b"ALPHA"), ("zed", b"ZED")):
        p = tmp_path / f"{nm}.prg"
        p.write_bytes(b"\x01\x08" + body)
        put_file(img, p, nm)

    dest = tmp_path / "out.prg"
    for lookup in ("zed,alpha", "alpha:zed", "alpha=p", 'alpha"zed'):
        with pytest.raises(DiskError, match="metacharacter"):
            get_file(img, lookup, dest)
    assert not dest.exists(), "a rejected lookup must not have run c1541"

    # Wildcards stay legal: `-read '*'` fetches the first directory entry,
    # which is how a disk's autostart program is pulled back off an image.
    assert get_file(img, "*", dest).read_bytes()[2:] == b"ALPHA"


@needs_c1541
def test_names_round_trip_between_put_and_get(tmp_path):
    # put_file lowercases an explicit name, and every lookup lowercases too,
    # so a name written through the API can always be found through it.
    img = create_image(tmp_path / "r.d64", label="r", disk_id="01")
    src = tmp_path / "p.prg"
    src.write_bytes(b"\x01\x08body")
    assert put_file(img, src, "ALPHA") == "alpha"
    assert get_file(img, "ALPHA", tmp_path / "back.prg").read_bytes() == \
        src.read_bytes()


@needs_c1541
def test_put_file_validates_an_explicit_name(tmp_path):
    img = create_image(tmp_path / "v.d64", label="v", disk_id="01")
    src = tmp_path / "p.prg"
    src.write_bytes(b"\x01\x08body")
    with pytest.raises(DiskError, match="CBM filename"):
        put_file(img, src, "no:colons")
    assert list_files(img)["files"] == []


def test_c1541_failure_raises_disk_error(tmp_path, monkeypatch):
    import subprocess

    from c64lib import disk

    def fail(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="bad image")
    # `_c1541()` resolves the binary before `subprocess.run` is reached, so
    # without this the test fails with "install VICE" on a machine that has
    # no c1541 instead of exercising the error path it is about. The name is
    # never executed: `subprocess.run` is patched out.
    monkeypatch.setenv("C64_TOOLS_C1541", "c1541")
    monkeypatch.setattr(disk.subprocess, "run", fail)
    with pytest.raises(disk.DiskError, match="bad image"):
        disk.list_files(tmp_path / "x.d64")


def test_default_dest_cannot_escape_the_cwd(tmp_path, monkeypatch):
    """`/` is legal in a CBM name — cbm_lookup_name bars only `":,=` and
    sub-$20 — so a directory entry called `../../x` steered the *default*
    host destination two levels above the cwd, and MCP's c64_disk_get passes
    NAME straight through from the caller.

    Driven through a fake c1541 that writes whatever path it is handed: the
    point is which path get_file computes, not whether a disk holds that
    entry."""
    import subprocess

    from c64lib import disk

    def writes_its_dest(cmd, capture_output, text):
        Path(cmd[-1]).write_bytes(b"\x01\x08")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setenv("C64_TOOLS_C1541", "c1541")
    monkeypatch.setattr(disk.subprocess, "run", writes_its_dest)
    work = tmp_path / "a" / "b"
    work.mkdir(parents=True)
    monkeypatch.chdir(work)

    out = disk.get_file(tmp_path / "x.d64", "../../x")
    assert out == Path(".._.._x.prg")
    assert (work / ".._.._x.prg").exists()
    assert not (tmp_path / "x.prg").exists(), "wrote outside the cwd"


def test_default_dest_survives_a_wildcard_name(tmp_path, monkeypatch):
    """`c64 disk get game.d64 '*'` is the autostart-extraction workflow
    get_file's own docstring documents, and the wildcard has no business in
    the host path: c1541 answers `cannot create output file '*.prg'`."""
    import subprocess

    from c64lib import disk

    def writes_its_dest(cmd, capture_output, text):
        Path(cmd[-1]).write_bytes(b"\x01\x08")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setenv("C64_TOOLS_C1541", "c1541")
    monkeypatch.setattr(disk.subprocess, "run", writes_its_dest)
    monkeypatch.chdir(tmp_path)

    assert disk.get_file(tmp_path / "x.d64", "*") == Path("_.prg")
    assert disk.get_file(tmp_path / "x.d64", "al?") == Path("al_.prg")


@needs_c1541
def test_get_file_reads_a_wildcard_with_no_dest(tmp_path, monkeypatch):
    """The documented autostart extraction, end to end on a real c1541."""
    img = create_image(tmp_path / "w.d64", label="w", disk_id="01")
    src = tmp_path / "p.prg"
    src.write_bytes(b"\x01\x08ALPHA")
    put_file(img, src, "alpha")
    monkeypatch.chdir(tmp_path)
    assert get_file(img, "*").read_bytes() == src.read_bytes()


@needs_c1541
def test_default_dest_still_spells_an_ordinary_name_as_typed(
        tmp_path, monkeypatch):
    """Sanitizing must not touch a name that is already a plain basename."""
    img = create_image(tmp_path / "s.d64", label="s", disk_id="01")
    src = tmp_path / "p.prg"
    src.write_bytes(b"\x01\x08body")
    put_file(img, src, "alpha")
    monkeypatch.chdir(tmp_path)
    assert get_file(img, "ALPHA") == Path("ALPHA.prg")


def test_get_file_missing_output_raises(tmp_path, monkeypatch):
    import subprocess

    from c64lib import disk

    def ok_but_writes_nothing(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    # See above: resolve the binary by name so this runs without VICE. The
    # patched `subprocess.run` means nothing is executed.
    monkeypatch.setenv("C64_TOOLS_C1541", "c1541")
    monkeypatch.setattr(disk.subprocess, "run", ok_but_writes_nothing)
    with pytest.raises(disk.DiskError, match="was not written"):
        disk.get_file(tmp_path / "x.d64", "game", tmp_path / "out.prg")
