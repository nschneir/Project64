import os
import shutil
import stat
from pathlib import Path

import pytest

from c64lib.build import BuildError, BuildResult, build_asm, linker_config


def test_linker_config_contents():
    cfg = linker_config(0x0801)
    assert "$0801" in cfg
    for seg in ("LOADADDR", "EXEHDR", "CODE", "HEADER", "MAIN"):
        assert seg in cfg


def test_zeropage_starts_above_the_6510_port():
    """$0000/$0001 are the 6510's on-chip port registers, and ld65 hands out
    the ZP area from its start — so at $0000 the first two ZEROPAGE bytes an
    author declares land on the data direction register and the banking port,
    and writing the second re-banks the machine under the running code.
    Matches the cart configs (cart_build._ZP)."""
    cfg = linker_config(0x0801)
    assert "ZP:     start = $0002, size = $00FE;" in cfg
    assert "start = $0000, size = $0100" not in cfg


def _stub_tool(dir: Path, name: str, body: str) -> Path:
    p = dir / name
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def test_build_asm_invokes_toolchain(tmp_path, monkeypatch):
    ca65 = _stub_tool(tmp_path, "ca65", (
        "import sys, pathlib\n"
        "a = sys.argv[1:]\n"
        "pathlib.Path(a[a.index('-o')+1]).write_bytes(b'OBJ')\n"
        "pathlib.Path(__file__).with_name('ca65.args').write_text(' '.join(a))\n"
    ))
    ld65 = _stub_tool(tmp_path, "ld65", (
        "import sys, pathlib\n"
        "a = sys.argv[1:]\n"
        "pathlib.Path(a[a.index('-o')+1]).write_bytes(b'\\x01\\x08PRG')\n"
        "pathlib.Path(a[a.index('-Ln')+1]).write_text('al 00040D .start\\n')\n"
        "pathlib.Path(__file__).with_name('ld65.args').write_text(' '.join(a))\n"
    ))
    monkeypatch.setenv("C64_TOOLS_CA65", str(ca65))
    monkeypatch.setenv("C64_TOOLS_LD65", str(ld65))

    src = tmp_path / "prog.s"
    src.write_text("; test\n")
    res = build_asm(src)
    assert isinstance(res, BuildResult)
    assert res.prg == tmp_path / "prog.prg" and res.prg.read_bytes()[:2] == b"\x01\x08"
    assert res.labels == tmp_path / "prog.lbl" and "start" in res.labels.read_text()
    ca65_args = (tmp_path / "ca65.args").read_text()
    assert str(src) in ca65_args
    assert "-g" in ca65_args.split()
    ld_args = (tmp_path / "ld65.args").read_text()
    assert "-C" in ld_args and "-Ln" in ld_args


def test_build_error_includes_stderr(tmp_path, monkeypatch):
    bad = _stub_tool(tmp_path, "ca65",
                     "import sys; sys.stderr.write('prog.s(3): syntax error'); sys.exit(1)\n")
    monkeypatch.setenv("C64_TOOLS_CA65", str(bad))
    monkeypatch.setenv("C64_TOOLS_LD65", str(bad))
    src = tmp_path / "prog.s"
    src.write_text("bogus\n")
    with pytest.raises(BuildError, match="syntax error"):
        build_asm(src)


def test_missing_tool_message(monkeypatch):
    monkeypatch.delenv("C64_TOOLS_CA65", raising=False)
    monkeypatch.setattr("c64lib.build.shutil.which", lambda n: None)
    with pytest.raises(BuildError, match="[Ii]nstall"):
        build_asm(Path("x.s"))


def _stub_pair(tmp_path, monkeypatch, ca65_body=None, deps_line=None):
    """Stub ca65/ld65; ca65 honors --create-dep when deps_line given."""
    default_ca65 = (
        "import sys, pathlib\n"
        "a = sys.argv[1:]\n"
        "pathlib.Path(a[a.index('-o')+1]).write_bytes(b'OBJ')\n"
    )
    if deps_line is not None:
        default_ca65 += (
            "if '--create-dep' in a:\n"
            f"    pathlib.Path(a[a.index('--create-dep')+1]).write_text({deps_line!r})\n"
        )
    ca65 = _stub_tool(tmp_path, "ca65", ca65_body or default_ca65)
    ld65 = _stub_tool(tmp_path, "ld65", (
        "import sys, pathlib\n"
        "a = sys.argv[1:]\n"
        "pathlib.Path(a[a.index('-o')+1]).write_bytes(b'\\x01\\x08PRG')\n"
        "pathlib.Path(a[a.index('-Ln')+1]).write_text('al 00040D .start\\n')\n"
    ))
    monkeypatch.setenv("C64_TOOLS_CA65", str(ca65))
    monkeypatch.setenv("C64_TOOLS_LD65", str(ld65))


def test_build_asm_collects_deps_and_built_at(tmp_path, monkeypatch):
    import time
    src = tmp_path / "prog.s"
    inc = tmp_path / "inc.s"
    src.write_text('; top\n.include "inc.s"\n')
    inc.write_text("; include\n")
    _stub_pair(tmp_path, monkeypatch, deps_line=_real_ca65_deps(src, inc))
    t0 = time.time()
    res = build_asm(src)
    assert src in res.deps and inc in res.deps
    assert res.built_at >= t0


def _real_ca65_deps(src, *includes) -> str:
    """ca65 --create-dep's actual output: the rule, then one bare phony
    target per prerequisite (GNU make's -MP convention), blank-separated."""
    prereqs = " \\\n ".join(str(p) for p in (src, *includes))
    phony = "".join(f"\n{p}:\n" for p in (src, *includes))
    return f"prog.o:\t{prereqs}\n{phony}"


def test_build_asm_deps_ignore_ca65_phony_targets(tmp_path, monkeypatch):
    """The phony `<source>:` lines carry no prerequisites, and a naive
    split-on-the-first-colon turns them into a path with a trailing colon.
    That path never exists, and `ops.staleness` counts a vanished source as
    stale — which reported every freshly built program as out of date."""
    src = tmp_path / "prog.s"
    inc = tmp_path / "inc.s"
    src.write_text('; top\n.include "inc.s"\n')
    inc.write_text("; include\n")
    _stub_pair(tmp_path, monkeypatch, deps_line=_real_ca65_deps(src, inc))
    res = build_asm(src)
    assert set(res.deps) == {src, inc}
    assert all(p.exists() for p in res.deps)


def test_build_failure_never_touches_existing_prg(tmp_path, monkeypatch):
    src = tmp_path / "prog.s"
    src.write_text("; broken\n")
    old = tmp_path / "prog.prg"
    old.write_bytes(b"\x01\x08OLD")
    _stub_pair(tmp_path, monkeypatch,
               ca65_body="import sys\nsys.stderr.write('boom\\n')\nsys.exit(1)\n")
    with pytest.raises(BuildError):
        build_asm(src)
    assert old.read_bytes() == b"\x01\x08OLD"  # stale binary intact, not rebuilt


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_include_resolves_relative_to_the_including_file(tmp_path, monkeypatch):
    """The contract 6502-assembly/SKILL.md documents: a multi-file program
    builds with no -I, wherever the build runs from — the invaders dogfood
    burned a round trip discovering this."""
    src = tmp_path / "src"
    nested = src / "nested"
    nested.mkdir(parents=True)
    (nested / "inc.s").write_text('        lda #1\n')
    (src / "main.s").write_text(
        '        .segment "LOADADDR"\n'
        '        .word $0801\n'
        '        .segment "EXEHDR"\n'
        '        .word nextln\n'
        '        .word 10\n'
        '        .byte $9E, "2061", $00\n'
        'nextln: .word $0000\n'
        '        .segment "CODE"\n'
        'start:  .include "nested/inc.s"\n'
        '        rts\n')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    res = build_asm(src / "main.s", basic_start=0x0801)
    assert Path(res.prg).exists()
