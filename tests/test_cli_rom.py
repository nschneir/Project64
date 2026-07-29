import json
import re
from unittest.mock import Mock, patch

from click.testing import CliRunner

from c64lib.cli import main


def _fake(labels=None):
    fake = Mock()
    fake.name, fake.model, fake.labels = "c64", "c64", labels
    fake.profile.basic_version = "2.0"
    mon = Mock()
    fake.monitor.return_value.__enter__ = Mock(return_value=mon)
    fake.monitor.return_value.__exit__ = Mock(return_value=False)
    return fake, mon


def test_rom_info():
    fake, mon = _fake()
    with patch("c64lib.cli.Session") as S, \
         patch("c64lib.cli.identify", return_value={
             "basic": "basic-901226-01.bin", "kernal": "kernal-901227-03.bin",
             "chargen": "chargen-901225-01.bin", "hashes": {"basic": "abc"}}) as ident:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "rom", "info"])
    assert r.exit_code == 0, r.output
    ident.assert_called_once_with(mon)
    assert json.loads(r.output)["kernal"] == "kernal-901227-03.bin"
    mon.release.assert_called_once()


def test_rom_disasm_symbolic_start():
    fake, mon = _fake()
    mon.memory_read.return_value = b"\x4c\x66\xf2"
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        r = CliRunner().invoke(main, ["--json", "rom", "disasm", "CHROUT", "3"])
    assert r.exit_code == 0, r.output
    mon.memory_read.assert_called_once_with(0xFFD2, 3)
    out = json.loads(r.output)
    assert out["start"] == 0xFFD2
    assert any("jmp $f266" in ln for ln in out["lines"])
    assert out["lines"][0] == "CHROUT:"       # annotated from the curated ROM DB
    mon.release.assert_called_once()


def _invoke_disasm(args):
    fake, mon = _fake()
    mon.memory_read.return_value = b"\xa9\x00\x8d\x20\xd0\x4c\x66\xf2"
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = fake
        return CliRunner().invoke(main, args)


def test_top_level_disasm_alias_matches_rom_disasm():
    """`c64 disasm` is the same command object as `c64 rom disasm`, so the
    output cannot drift between the two spellings."""
    aliased = _invoke_disasm(["--json", "disasm", "828", "8"])
    grouped = _invoke_disasm(["--json", "rom", "disasm", "828", "8"])
    assert aliased.exit_code == 0, aliased.output
    assert grouped.exit_code == 0, grouped.output
    assert aliased.output == grouped.output
    assert json.loads(aliased.output)["start"] == 828


def test_disasm_alias_listed_in_top_level_help():
    """Discoverability is the point of the alias: it has to show up in the
    top-level command list, where someone debugging RAM will look."""
    r = CliRunner().invoke(main, ["--help"])
    assert r.exit_code == 0, r.output
    assert re.search(r"^\s+disasm\s+\S", r.output, re.M), r.output
