import pytest

import c64lib
from c64lib.packaging import PackageError, package_program


def test_version():
    # compare against pyproject so a release bump can't leave this stale
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert c64lib.__version__ == pyproject["project"]["version"]


def test_changelog_has_current_version():
    # pyproject is the single version source; the CHANGELOG must carry an
    # entry for it (the release workflow tags exactly this version).
    from pathlib import Path

    changelog = (Path(__file__).parents[1] / "CHANGELOG.md").read_text()
    assert f"## [{c64lib.__version__}]" in changelog, \
        f"CHANGELOG.md has no entry for {c64lib.__version__}"


def test_package_prg_copies_source(tmp_path):
    src = tmp_path / "game.prg"
    src.write_bytes(b"\x01\x08\x00\x00")
    package_program(src, out=str(tmp_path / "copy.prg"))
    assert (tmp_path / "copy.prg").read_bytes() == src.read_bytes()


def test_package_unknown_extension(tmp_path):
    with pytest.raises(PackageError, match="cannot package"):
        package_program(tmp_path / "x.txt")
