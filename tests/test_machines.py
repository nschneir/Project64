import pytest

from c64lib.machines import PROFILES, get_profile


def test_all_models_present():
    assert set(PROFILES) == {"c64", "c64pal"}


def test_profiles_have_ram_kb():
    ram = {name: p.ram_kb for name, p in PROFILES.items()}
    assert ram == {"c64": 64, "c64pal": 64}


def test_c64_profile():
    p = get_profile("c64")
    assert p.vice_emulator == "x64sc"
    assert p.vice_args == ("-ntsc",)
    assert p.basic_version == "2.0"
    assert p.basic_start == 0x0801
    assert p.screen_addr == 0x0400
    assert (p.screen_cols, p.screen_rows) == (40, 25)


def test_c64pal_profile_args():
    p = get_profile("c64pal")
    assert p.vice_args == ("-pal",)
    assert p.basic_version == "2.0" and p.screen_cols == 40


def test_unknown_profile_lists_available():
    with pytest.raises(KeyError, match="c64pal"):
        get_profile("c128")
