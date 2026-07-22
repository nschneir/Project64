import pytest

from c64lib.symbols import format_addr, load_labels, nearest, resolve, save_labels


def test_load_ld65_and_vice_forms(tmp_path):
    f = tmp_path / "prog.lbl"
    f.write_text(
        "al 00040D .start\n"
        "al C:0420 .loop\n"
        "al C:FFD2 .CHROUT\n"
        "; a comment line to ignore\n"
        "\n"
    )
    labels = load_labels(f)
    assert labels == {"start": 0x040D, "loop": 0x0420, "CHROUT": 0xFFD2}


def test_save_and_reload_roundtrip(tmp_path):
    f = tmp_path / "out.lbl"
    save_labels(f, {"main": 0x040D, "msg": 0x0430})
    text = f.read_text()
    assert "al C:040d .main" in text
    assert load_labels(f) == {"main": 0x040D, "msg": 0x0430}


LABELS = {"start": 0x040D, "loop": 0x040F, "msg": 0x041B, "__BSS_RUN__": 0x042B}


def test_resolve_exact_and_case_insensitive():
    assert resolve(LABELS, "start") == 0x040D
    assert resolve(LABELS, "MSG") == 0x041B
    with pytest.raises(KeyError, match="start"):
        resolve(LABELS, "strat")


def test_nearest_skips_internals_and_respects_range():
    assert nearest(LABELS, 0x040D) == ("start", 0)
    assert nearest(LABELS, 0x0411) == ("loop", 2)
    # __BSS_RUN__ at 0x042B is skipped (internal); msg (0x041B) is the nearest
    # real label, 16 bytes back and inside the 256-byte window
    assert nearest(LABELS, 0x042B) == ("msg", 16)
    assert nearest(LABELS, 0x9000) is None      # nothing within 256 bytes


def test_format_addr():
    assert format_addr(LABELS, 0x040D) == "$040d (start)"
    assert format_addr(LABELS, 0x0411) == "$0411 (loop+2)"
    assert format_addr(LABELS, 0x9000) == "$9000"
    assert format_addr({}, 0x040D) == "$040d"
