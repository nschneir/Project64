import os
import re
import shutil

import pytest

from c64lib.disk import (
    BLOCK_PAYLOAD,
    BLOCK_SIZE,
    GEOMETRY,
    IMAGE_DRIVE_TYPES,
    MAX_DIR_ENTRIES,
    TOTAL_BLOCKS,
    DiskError,
    block_bytes,
    block_poke,
    block_read,
    block_write_file,
    blocks_for,
    cbm_lookup_name,
    check_block,
    create_image,
    delete_file,
    dos_status,
    list_files,
    max_track,
    put_file,
    rename_file,
    sectors_per_track,
    validate_image,
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


@pytest.mark.parametrize("track,sectors", [
    # Every side-two zone boundary: the last track of each zone and the first
    # of the next, all four probed sector by sector against a real d71.
    (36, 21), (52, 21), (53, 19), (59, 19), (60, 18), (65, 18), (66, 17),
    (70, 17)])
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


def test_the_four_image_format_tables_share_one_key_set():
    """Only drive_type_for guards its lookup; GEOMETRY, TOTAL_BLOCKS and
    MAX_DIR_ENTRIES are all indexed bare on the strength of that check, so a
    fifth format added to one dict and not the others is a naked KeyError."""
    assert (IMAGE_DRIVE_TYPES.keys() == GEOMETRY.keys() == TOTAL_BLOCKS.keys()
            == MAX_DIR_ENTRIES.keys())


@pytest.mark.parametrize("raw,expected", [
    # 'ß'.upper() is 'SS' — two characters, so the old per-character
    # ord(ch.upper()) raised TypeError instead of DiskError.
    ("maße", "masse"),
    # 'ı' and 'ſ' upper-case to 'I' and 'S', so the old check passed them and
    # then handed c1541 the original non-ASCII byte. Now the cased form is
    # what is both checked and returned.
    ("ıce", "ice"),
    ("ſun", "sun"),
])
def test_cbm_lookup_name_cases_the_whole_string(raw, expected):
    assert cbm_lookup_name(raw) == expected


def test_cbm_lookup_name_still_rejects_untranslatable_characters():
    # 'é'.upper() is 'É' — one character, but not PETSCII-printable.
    with pytest.raises(DiskError, match="won't survive"):
        cbm_lookup_name("café")


def test_cbm_lookup_name_counts_the_length_it_will_actually_store():
    # Nine 'ß' become eighteen characters on disk; the limit applies to what
    # c1541 stores, not to what was typed.
    with pytest.raises(DiskError, match="18 chars"):
        cbm_lookup_name("ß" * 9)


@pytest.mark.parametrize("values,match", [
    ([1, 2, 300], r"byte 2 is 300, out of range"),
    ([1, -1], r"byte 1 is -1, out of range"),
    ([1, "x"], r"byte 1 is 'x', which is not a whole number"),
])
def test_block_bytes_names_the_offending_value(values, match):
    # Python's own bytes() says only "bytes must be in range(0, 256)" — true,
    # but it never says which of the values sent was wrong.
    with pytest.raises(DiskError, match=match):
        block_bytes(values)


def test_block_bytes_passes_good_values_through():
    assert block_bytes([0, 65, 255]) == b"\x00A\xff"
    assert block_bytes(b"\x01\x02") == b"\x01\x02"


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


def test_dos_status_parses_a_real_track_and_sector_bearing_line():
    # Measured: an overflowing d64 write answers exactly this.
    assert dos_status("ERR = 67, ILLEGAL SYSTEM T OR S, 36, 01") == (
        67, "ILLEGAL SYSTEM T OR S", 36, 1)


def test_dos_status_keeps_a_message_containing_a_comma():
    """Future-proofing, not a measured line: no DOS message seen from VICE
    3.10 carries an internal comma. The old `[^,]+?` group could not span one
    at all, so such a line would not have parsed and would have degraded
    silently to "no status" rather than merely losing its tail."""
    assert dos_status("ERR = 26, WRITE PROTECT, ON, 18, 00") == (
        26, "WRITE PROTECT, ON", 18, 0)


def test_dos_status_accepts_a_line_without_track_and_sector():
    # The trailing pair is optional rather than required: dropping it used to
    # make the whole line unparseable, which degraded silently to "no status".
    assert dos_status("ERR = 74, DRIVE NOT READY") == (74, "DRIVE NOT READY", 0, 0)


def test_dos_status_raises_on_an_unparseable_status_line():
    # Silent degradation is the danger: a None here tells delete_file "no
    # status", which it reads as a scratch count of 0.
    with pytest.raises(DiskError, match="cannot parse c1541's DOS status line"):
        dos_status("attaching\nERR = but not like this\n")


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
@pytest.mark.parametrize("bad", ["x" * 17, "no:colons", ""])
def test_filename_errors_say_filename_not_title(image, bad):
    # cbm_filename delegates to packaging.cbm_title, whose messages all open
    # with the noun "title" because packaging names disks. Nothing on this
    # path is a title, so the noun is swapped rather than leaked.
    with pytest.raises(DiskError) as exc:
        rename_file(image, "alpha", bad)
    assert not str(exc.value).startswith("title ")
    assert str(exc.value).startswith("filename ")


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
    with pytest.raises(DiskError, match="cannot read") as exc:
        block_write_file(image, 1, 0, tmp_path / "nope.bin")
    # The lead-in is cause-neutral, but strerror still says which cause.
    assert "No such file" in str(exc.value)


@needs_c1541
def test_block_write_file_reports_an_unreachable_source_neutrally(image, tmp_path):
    """The catch is every OSError, not just ENOENT: "no such file to write"
    was a lie for EACCES, where the file is right there.

    Measured while writing this: chmod-000 on the FILE does not reach the
    catch at all — stat() needs no read permission, so the size check passes
    and c1541 fails later with its own "floppy read failed". The parent
    directory is what has to be unsearchable for stat() itself to raise.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    src = vault / "sector.bin"
    src.write_bytes(bytes(BLOCK_SIZE))
    os.chmod(vault, 0o000)
    try:
        try:
            src.stat()
            pytest.skip("cannot make a directory unsearchable here (root?)")
        except PermissionError:
            pass
        with pytest.raises(DiskError) as exc:
            block_write_file(image, 1, 0, src)
    finally:
        os.chmod(vault, 0o755)
    assert "no such file" not in str(exc.value).lower()
    assert "cannot read" in str(exc.value)
    assert "Permission denied" in str(exc.value)


@needs_c1541
def test_validate_reports_an_unreadable_image_neutrally(image):
    # validate_image's catch wraps read_bytes(), which unlike stat() does need
    # read permission — so here a chmod-000 file is the real EACCES case.
    os.chmod(image, 0o000)
    try:
        try:
            image.read_bytes()
            pytest.skip("cannot make a file unreadable here (running as root?)")
        except PermissionError:
            pass
        with pytest.raises(DiskError) as exc:
            validate_image(image)
    finally:
        os.chmod(image, 0o644)
    assert "no such image" not in str(exc.value).lower()
    assert "cannot read image" in str(exc.value)
    assert "Permission denied" in str(exc.value)


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


# Offsets of a track's four-byte BAM entry in sector 18/0 of a d64, measured on
# a fresh image: 4 bytes of header, then (free count, 3-byte bitmap) per track.
def _bam_entry(track: int) -> int:
    return 4 + (track - 1) * 4


@needs_c1541
def test_validate_reports_a_clean_image(image):
    res = validate_image(image)
    assert res["clean"] is True
    assert res["repaired_blocks"] == 0
    assert res["blocks_free_before"] == res["blocks_free_after"]
    assert res["messages"] == []


@needs_c1541
def test_validate_detects_and_repairs_a_corrupted_bam(image):
    """c1541 validate prints no diagnostic for what it repaired, so cleanliness
    is judged by comparing the image before and after.

    Absorbs what was a second near-identical test (`..._reclaims_blocks_no_file
    _owns`): both poked the same BAM entry and ran the same validate, so the
    reclaim direction is asserted here in full instead of twice over.
    """
    before = list_files(image)["blocks_free"]
    # Mark track 1 fully allocated in the BAM: 0 free, no bits set.
    block_poke(image, 18, 0, _bam_entry(1), bytes([0, 0, 0, 0]))
    assert list_files(image)["blocks_free"] < before
    res = validate_image(image)
    assert res["clean"] is False
    assert res["repaired_blocks"] == 21          # track 1 has 21 sectors
    assert res["blocks_free_after"] == before
    # The reclaim direction, in the result's own numbers and its own words:
    # 21 blocks the BAM called allocated come back.
    assert res["blocks_free_after"] - res["blocks_free_before"] == 21
    assert any("BAM" in m for m in res["messages"])
    assert any("no file owns" in m for m in res["messages"])


@needs_c1541
def test_validate_leaves_a_clean_image_byte_identical(image, tmp_path):
    copy = tmp_path / "copy.d64"
    shutil.copyfile(image, copy)
    validate_image(image)
    assert image.read_bytes() == copy.read_bytes()


@needs_c1541
def test_validate_reclaims_a_block_the_bam_wrongly_called_free(image):
    # Measured: 'alpha' lives on track 17 sector 0, so freeing that bit in the
    # BAM makes the image claim 664 free on a disk that has 663. Validate walks
    # the files and takes the block back, which moves the count DOWN.
    block_poke(image, 18, 0, _bam_entry(17), bytes([21, 255, 255, 31]))
    res = validate_image(image)
    assert res["blocks_free_before"] - res["blocks_free_after"] == 1
    assert res["repaired_blocks"] == 1
    assert any("under-reported" in m for m in res["messages"])


@needs_c1541
def test_validate_flags_a_repair_the_free_count_cannot_show(image):
    # Measured: the reported "blocks free" total leaves the directory track out,
    # so zeroing track 18's BAM entry corrupts the image without moving the
    # number. Byte comparison is what catches it; repaired_blocks is honestly 0.
    before = list_files(image)["blocks_free"]
    block_poke(image, 18, 0, _bam_entry(18), bytes([0, 0, 0, 0]))
    assert list_files(image)["blocks_free"] == before
    res = validate_image(image)
    assert res["clean"] is False
    assert res["repaired_blocks"] == 0
    assert res["blocks_free_before"] == res["blocks_free_after"] == before
    assert any("free count did not move" in m for m in res["messages"])


@needs_c1541
def test_validate_reports_a_missing_image_as_a_disk_error(tmp_path):
    # Reading the image to compare it happens before c1541 runs, so without the
    # wrap this is a bare FileNotFoundError rather than a fault the CLI reports.
    # The lead-in is cause-neutral ("cannot read image"), because the same
    # catch also takes EACCES; strerror carries the actual cause.
    with pytest.raises(DiskError, match="cannot read image") as exc:
        validate_image(tmp_path / "nope.d64")
    assert "No such file" in str(exc.value)
