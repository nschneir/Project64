import re
import shutil

import pytest

from c64lib.disk import (
    BLOCK_PAYLOAD,
    BLOCK_SIZE,
    TOTAL_BLOCKS,
    DiskError,
    block_poke,
    block_read,
    block_write_file,
    blocks_for,
    check_block,
    create_image,
    delete_file,
    dos_status,
    list_files,
    max_track,
    put_file,
    rename_file,
    sectors_per_track,
)

needs_c1541 = pytest.mark.skipif(shutil.which("c1541") is None,
                                 reason="needs VICE's c1541")


def test_block_constants():
    assert BLOCK_SIZE == 256
    # 2 bytes of every sector are the link to the next one.
    assert BLOCK_PAYLOAD == 254


@pytest.mark.parametrize("suffix,tracks,free", [
    (".d64", 35, 664), (".d71", 70, 1328), (".d81", 80, 3160)])
def test_geometry_matches_the_probed_images(suffix, tracks, free):
    assert max_track(f"x{suffix}") == tracks
    assert TOTAL_BLOCKS[suffix] == free


@pytest.mark.parametrize("track,sectors", [
    (1, 21), (17, 21), (18, 19), (24, 19), (25, 18), (30, 18), (31, 17), (35, 17)])
def test_d64_sectors_per_track(track, sectors):
    assert sectors_per_track("x.d64", track) == sectors


@pytest.mark.parametrize("track,sectors", [(36, 21), (53, 19), (65, 18), (70, 17)])
def test_d71_second_side_mirrors_the_first(track, sectors):
    assert sectors_per_track("x.d71", track) == sectors


@pytest.mark.parametrize("track", [1, 40, 80])
def test_d81_is_uniform(track):
    assert sectors_per_track("x.d81", track) == 40


def test_track_out_of_range_names_the_limit():
    with pytest.raises(DiskError, match=r"track 40 out of range \(1-35 for d64\)"):
        check_block("x.d64", 40, 0)
    with pytest.raises(DiskError, match="track 0 out of range"):
        check_block("x.d64", 0, 0)


def test_sector_out_of_range_names_the_track():
    with pytest.raises(DiskError,
                       match=r"sector 19 out of range \(0-18 on track 18\)"):
        check_block("x.d64", 18, 19)
    check_block("x.d64", 18, 18)        # the last legal one


def test_unsupported_image_type_is_rejected():
    with pytest.raises(DiskError, match="unsupported image type"):
        check_block("x.d82", 1, 0)


@pytest.mark.parametrize("size,blocks", [
    (1, 1), (19, 1), (254, 1), (255, 2), (160000, 630), (40000, 158)])
def test_blocks_for_matches_measured_costs(size, blocks):
    """Verified against c1541: a 19-byte file costs 1 block, 160,000 costs 630."""
    assert blocks_for(size) == blocks


def test_blocks_for_an_empty_file_still_costs_one():
    assert blocks_for(0) == 1


def test_dos_status_parses_the_error_line():
    assert dos_status("renaming\nERR = 62, FILE NOT FOUND, 00, 00\n") == (
        62, "FILE NOT FOUND", 0, 0)
    assert dos_status("ERR = 01, FILES SCRATCHED, 03, 00")[2] == 3
    assert dos_status("nothing to see here") is None


@pytest.fixture
def image(tmp_path):
    img = create_image(tmp_path / "game.d64", label="mygame", disk_id="01")
    payload = tmp_path / "f1.prg"
    payload.write_bytes(b"\x01\x08hello world payload")
    put_file(img, payload, "alpha")
    return img


@needs_c1541
def test_rename_changes_the_directory_entry(image):
    assert rename_file(image, "alpha", "beta") == "beta"
    names = [f["name"] for f in list_files(image)["files"]]
    assert names == ["beta"]


@needs_c1541
def test_rename_of_a_missing_file_raises(image):
    # c1541 prints "ERR = 62, FILE NOT FOUND" and still exits 0, so this is
    # also the first real end-to-end check that _run_checked surfaces a DOS
    # failure code rather than trusting the exit status.
    with pytest.raises(DiskError, match="file not found") as exc:
        rename_file(image, "nosuch", "other")
    assert "DOS error 62" in str(exc.value)
    assert "nosuch" in str(exc.value)
    assert [f["name"] for f in list_files(image)["files"]] == ["alpha"]


@needs_c1541
def test_rename_validates_the_new_name(image):
    with pytest.raises(DiskError, match="17 chars"):
        rename_file(image, "alpha", "x" * 17)
    with pytest.raises(DiskError, match="CBM filename"):
        rename_file(image, "alpha", "no:colons")


@needs_c1541
def test_delete_removes_the_file_and_reports_the_count(image):
    assert delete_file(image, "alpha") == 1
    assert list_files(image)["files"] == []


@needs_c1541
def test_delete_of_a_missing_file_raises(image):
    # The scratch count in "ERR = 01, FILES SCRATCHED, 00, 00" is the signal.
    with pytest.raises(DiskError, match="no file named 'nosuch'"):
        delete_file(image, "nosuch")


@needs_c1541
def test_delete_frees_the_blocks(image):
    before = list_files(image)["blocks_free"]
    delete_file(image, "alpha")
    assert list_files(image)["blocks_free"] > before


@needs_c1541
def test_block_read_returns_the_bam(image):
    block = block_read(image, 18, 0)
    assert len(block) == 256
    # Measured on a fresh d64: link to 18/1, DOS version 'A', then four bytes
    # per track — free count plus a three-byte allocation bitmap.
    assert block[0:4] == bytes([0x12, 0x01, 0x41, 0x00])
    assert block[4] == 21               # track 1 has 21 free sectors


@needs_c1541
def test_block_read_rejects_a_bad_track_before_calling_c1541(image, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("c1541 was invoked for an out-of-range track")

    monkeypatch.setattr("c64lib.disk._run2", boom)
    with pytest.raises(DiskError, match=r"track 40 out of range"):
        block_read(image, 40, 0)


@needs_c1541
def test_block_write_file_round_trips(image, tmp_path):
    original = block_read(image, 1, 0)
    src = tmp_path / "sector.bin"
    src.write_bytes(bytes(range(256)))
    block_write_file(image, 1, 0, src)
    assert block_read(image, 1, 0) == bytes(range(256))
    src.write_bytes(original)
    block_write_file(image, 1, 0, src)
    assert block_read(image, 1, 0) == original


@needs_c1541
def test_block_write_file_requires_exactly_one_sector(image, tmp_path):
    # Measured: a short file makes c1541 exit 1 with the misleading "floppy
    # read failed"; a long one exits 0 and is silently truncated to 256. The
    # check happens here so both get the same message naming the real size.
    short = tmp_path / "short.bin"
    short.write_bytes(b"short")
    with pytest.raises(DiskError, match="5 bytes.*exactly 256"):
        block_write_file(image, 1, 0, short)
    long = tmp_path / "long.bin"
    long.write_bytes(bytes(400))
    with pytest.raises(DiskError, match="400 bytes.*exactly 256"):
        block_write_file(image, 1, 0, long)


@needs_c1541
def test_block_write_file_reports_a_missing_source_as_a_disk_error(image, tmp_path):
    # Without the wrap this is a bare FileNotFoundError from src.stat(), which
    # would traceback out of the CLI/MCP layer instead of reading as a fault.
    with pytest.raises(DiskError, match="no such file"):
        block_write_file(image, 1, 0, tmp_path / "nope.bin")


@needs_c1541
def test_block_poke_writes_at_the_offset(image):
    block_poke(image, 1, 0, 4, bytes([0xDE, 0xAD]))
    block = block_read(image, 1, 0)
    assert block[4:6] == bytes([0xDE, 0xAD])


@needs_c1541
def test_block_poke_refuses_to_run_past_the_sector(image):
    # Measured, both exit 0 with no diagnostic: poking 4 bytes at 254 lands
    # only 2 of them (a silent PARTIAL write), and an offset past 255 lands
    # nothing at all.
    with pytest.raises(DiskError, match=r"offset 254 \+ 4 bytes"):
        block_poke(image, 1, 0, 254, bytes(4))
    with pytest.raises(DiskError, match="offset 256 out of range"):
        block_poke(image, 1, 0, 256, b"\x00")


@needs_c1541
def test_block_poke_accepts_the_last_byte_of_the_sector(image):
    # The accepting side of the same boundary: offset 255 + 1 byte is exactly
    # 256, so it must go through. Pins `>` against a regression to `>=`.
    before = block_read(image, 1, 0)
    block_poke(image, 1, 0, BLOCK_SIZE - 1, b"\xff")
    after = block_read(image, 1, 0)
    assert after[255] == 0xFF
    assert after[:255] == before[:255]


@needs_c1541
def test_block_poke_rejects_empty_data(image):
    with pytest.raises(DiskError, match="no bytes"):
        block_poke(image, 1, 0, 0, b"")


@pytest.fixture
def stocked_image(tmp_path):
    """Three files, so a wildcard match can be told from a single-file one."""
    img = create_image(tmp_path / "many.d64", label="mygame", disk_id="01")
    payload = tmp_path / "f.prg"
    payload.write_bytes(b"\x01\x08hello world payload")
    for name in ("alpha", "album", "zed"):
        put_file(img, payload, name)
    return img


@needs_c1541
@pytest.mark.parametrize("lookup,char", [
    ("alpha=beta", "="), ("alpha,beta", ","), ("alpha:beta", ":"),
    ('alpha"beta', '"')])
def test_rename_rejects_dos_metacharacters_in_the_old_name(image, lookup, char):
    # Measured: CBM DOS parses these, so `rename_file(img, "alpha=beta", ...)`
    # silently renamed 'alpha' and reported success.
    with pytest.raises(DiskError, match=re.escape(repr(char))):
        rename_file(image, lookup, "zed")
    assert [f["name"] for f in list_files(image)["files"]] == ["alpha"]


@needs_c1541
@pytest.mark.parametrize("lookup,char", [
    ("alpha=beta", "="), ("alpha,album", ","), ("alpha:beta", ":"),
    ('alpha"beta', '"')])
def test_delete_rejects_dos_metacharacters_in_the_name(stocked_image, lookup, char):
    # Measured: "alpha,album" scratched TWO files; "alpha=beta" scratched 'alpha'.
    with pytest.raises(DiskError, match=re.escape(repr(char))):
        delete_file(stocked_image, lookup)
    assert len(list_files(stocked_image)["files"]) == 3


@needs_c1541
def test_delete_permits_wildcards_and_counts_them_honestly(stocked_image):
    assert delete_file(stocked_image, "al*") == 2
    assert [f["name"] for f in list_files(stocked_image)["files"]] == ["zed"]


@needs_c1541
def test_delete_star_wipes_the_disk_and_reports_the_true_count(stocked_image):
    assert delete_file(stocked_image, "*") == 3
    assert list_files(stocked_image)["files"] == []


@needs_c1541
def test_rename_with_a_wildcard_surfaces_c1541s_syntax_error(stocked_image):
    # c1541 itself refuses this with DOS 30, which is why `*` may stay legal
    # in a lookup name: only delete can act on more than one match.
    with pytest.raises(DiskError, match="syntax error") as exc:
        rename_file(stocked_image, "al*", "zzz")
    assert "DOS error 30" in str(exc.value)
    assert len(list_files(stocked_image)["files"]) == 3


@needs_c1541
def test_over_long_lookup_names_report_their_length(image):
    # Not "no file named 'xxxxxxxxxxxxxxxxx'" — the name could never exist.
    with pytest.raises(DiskError, match="17 chars"):
        delete_file(image, "x" * 17)
    with pytest.raises(DiskError, match="17 chars"):
        rename_file(image, "x" * 17, "zed")


@needs_c1541
def test_lookup_names_are_case_insensitive_both_ways(image):
    # The write path lowercases, so the API must round-trip its own output.
    assert rename_file(image, "ALPHA", "BETA") == "beta"
    assert [f["name"] for f in list_files(image)["files"]] == ["beta"]
    assert delete_file(image, "BeTa") == 1
    assert list_files(image)["files"] == []
