import shutil

import pytest

from c64lib.disk import (
    BLOCK_PAYLOAD,
    BLOCK_SIZE,
    TOTAL_BLOCKS,
    DiskError,
    blocks_for,
    check_block,
    dos_status,
    max_track,
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
