import pytest

import c64lib
from c64lib.packaging import PackageError, package_program


def _pyproject_version() -> str:
    import tomllib
    from pathlib import Path

    return tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]


def test_version_matches_installed_metadata():
    # __version__ is read from the installed package metadata (see
    # c64lib/__init__.py); it must match the pyproject source of truth.
    # A mismatch means a stale editable install — reinstall with
    # `pip install -e '.[dev]'`. CI always installs fresh, so it is green.
    assert c64lib.__version__ == _pyproject_version(), \
        "stale editable install — run `pip install -e '.[dev]'`"


def test_changelog_has_current_version():
    # pyproject is the single version source; the CHANGELOG must carry an
    # entry for it (the release workflow tags exactly this version).
    from pathlib import Path

    version = _pyproject_version()
    changelog = (Path(__file__).parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog, \
        f"CHANGELOG.md has no entry for {version}"


def test_package_prg_copies_source(tmp_path):
    src = tmp_path / "game.prg"
    src.write_bytes(b"\x01\x08\x00\x00")
    package_program(src, out=str(tmp_path / "copy.prg"))
    assert (tmp_path / "copy.prg").read_bytes() == src.read_bytes()


def test_package_unknown_extension(tmp_path):
    with pytest.raises(PackageError, match="cannot package"):
        package_program(tmp_path / "x.txt")
