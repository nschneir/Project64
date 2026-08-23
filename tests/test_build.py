import os
import shutil
import stat
from pathlib import Path

import pytest

from c64lib.build import Area, BuildError, BuildResult, build_asm, linker_config
from c64lib.machines import get_profile
from c64lib.ops import parse_areas

#: `parse_areas` takes the load address from its caller's profile instead
#: of defaulting to a C64 literal, so these tests name the profile they are
#: about — the same one every front end passes.
_BASIC_START = get_profile("c64").basic_start


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


_NO_AREAS = """\
MEMORY {
    ZP:     start = $0002, size = $00FE;
    HEADER: file = %O, start = $0000, size = $0002;
    MAIN:   file = %O, start = $0801, size = $97FF;
}
SEGMENTS {
    ZEROPAGE: load = ZP,     type = zp,  optional = yes;
    LOADADDR: load = HEADER, type = ro;
    EXEHDR:   load = MAIN,   type = ro,  optional = yes;
    CODE:     load = MAIN,   type = rw;
    RODATA:   load = MAIN,   type = ro,  optional = yes;
    DATA:     load = MAIN,   type = rw,  optional = yes;
    BSS:      load = MAIN,   type = bss, optional = yes, define = yes;
}
"""

_ONE_AREA = """\
MEMORY {
    ZP:     start = $0002, size = $00FE;
    HEADER: file = %O, start = $0000, size = $0002;
    MAIN:   file = %O, start = $0801, size = $37FF, fill = yes;
    HIGH:   file = %O, start = $4000, size = $2000;
}
SEGMENTS {
    ZEROPAGE: load = ZP,     type = zp,  optional = yes;
    LOADADDR: load = HEADER, type = ro;
    EXEHDR:   load = MAIN,   type = ro,  optional = yes;
    CODE:     load = MAIN,   type = rw;
    RODATA:   load = MAIN,   type = ro,  optional = yes;
    DATA:     load = MAIN,   type = rw,  optional = yes;
    BSS:      load = MAIN,   type = bss, optional = yes, define = yes;
    HIGH:     load = HIGH,   type = ro,  optional = yes, define = yes;
}
"""


def test_linker_config_unchanged_without_areas():
    """Pinned to the literal, so the no-areas path cannot drift when --area
    grows: every program built before this flag existed must still link to
    exactly the same layout."""
    assert linker_config(0x0801) == _NO_AREAS


def test_linker_config_one_area():
    assert linker_config(0x0801, [Area("HIGH", 0x4000, 0x2000)]) == _ONE_AREA


def test_linker_config_two_areas_sorted():
    """A .prg is a flat file: areas are emitted low to high whatever order
    they arrive in, and every one but the last is filled, because a hole
    below an area would shift everything above it."""
    cfg = linker_config(0x0801, [Area("TOP", 0x6000, 0x1000),
                                 Area("HIGH", 0x4000, 0x2000)])
    memory = cfg.split("SEGMENTS")[0]
    assert memory.index("HIGH:") < memory.index("TOP:")
    assert "    MAIN:   file = %O, start = $0801, size = $37FF, fill = yes;" in cfg
    assert "    HIGH:   file = %O, start = $4000, size = $2000, fill = yes;" in cfg
    assert "    TOP:    file = %O, start = $6000, size = $1000;" in cfg
    segments = cfg.split("SEGMENTS")[1]
    assert segments.index("HIGH:") < segments.index("TOP:")


def test_parse_areas_accepts_hex_and_decimal():
    for spelling in ("HIGH=$4000:$2000", "HIGH=0x4000:0x2000", "HIGH=16384:8192"):
        assert parse_areas([spelling], _BASIC_START) == [Area("HIGH", 0x4000, 0x2000)]


def test_parse_areas_rejects_malformed():
    with pytest.raises(ValueError,
                       match=r"^--area needs NAME=START:SIZE, got 'HIGH'$"):
        parse_areas(["HIGH"], _BASIC_START)


def test_parse_areas_rejects_reserved_name():
    with pytest.raises(ValueError, match=(
            r"^--area name 'MAIN' is reserved — ZP, HEADER, MAIN, ZEROPAGE, "
            r"LOADADDR, EXEHDR, CODE, RODATA, DATA and BSS cannot be reused$")):
        parse_areas(["MAIN=$4000:$2000"], _BASIC_START)


def test_parse_areas_rejects_area_at_or_below_the_load_address():
    with pytest.raises(ValueError, match=(
            r"^--area HIGH starts at \$0400, at or below the load address "
            r"\$0801 — an area must sit above the program$")):
        parse_areas(["HIGH=$0400:$2000"], _BASIC_START)


def test_parse_areas_rejects_zero_size():
    with pytest.raises(ValueError,
                       match=r"^--area HIGH=\$4000:\$0 has size 0$"):
        parse_areas(["HIGH=$4000:$0"], _BASIC_START)


def test_parse_areas_rejects_negative_size():
    """Size 0 was rejected and -1 was not, though `linker_config` renders it
    as `size = $-001` — `Hex digit expected` from ld65 V2.18, pointing at a
    line in a config the user never sees and cannot open, the failure mode
    this whole function exists to keep off the screen."""
    with pytest.raises(ValueError, match=(
            r"^--area 'HIGH=\$4000:-1' has size -1 — a size must be "
            r"positive$")):
        parse_areas(["HIGH=$4000:-1"], _BASIC_START)


def test_parse_areas_rejects_a_start_outside_the_address_space():
    """The half ld65 does NOT catch: measured against V2.18, `start = $12000`
    links without a word into a 71,679-byte .prg — 7 KB longer than the
    machine's whole address space, because MAIN is filled up to the area —
    and nothing says so until the load fails on a real C64."""
    with pytest.raises(ValueError, match=(
            r"^--area HIGH starts at 73728, outside the 16-bit address space "
            r"\(\$0000-\$FFFF\)$")):
        parse_areas(["HIGH=$12000:$100"], _BASIC_START)
    with pytest.raises(ValueError, match=r"outside the 16-bit address space"):
        parse_areas(["HIGH=-1:$100"], _BASIC_START)


def test_parse_areas_rejects_an_area_running_off_the_top_of_memory():
    """A start inside the machine and a size that leaves it. ld65 V2.18
    accepts this too and emits whatever the segment holds, so a full $2000
    at $F000 is a .prg the KERNAL loads off the top of memory."""
    with pytest.raises(ValueError, match=(
            r"^--area HIGH=\$F000:\$2000 ends at \$10FFF, past the top of "
            r"memory \(\$FFFF\)$")):
        parse_areas(["HIGH=$F000:$2000"], _BASIC_START)


def test_parse_areas_rejects_a_duplicate_name():
    """Each area renders one MEMORY entry AND one same-named segment, so a
    repeated name is two definitions of both. The gap/overlap checks below
    do not catch it — two areas that touch are legal — and ld65 V2.18's own
    `Memory area 'HIGH' defined twice` names a line of the generated config
    rather than either `--area` that collided."""
    with pytest.raises(ValueError, match=(
            r"^--area HIGH=\$6000:\$1000 reuses the name HIGH, already given "
            r"by --area 'HIGH=\$4000:\$2000' — each --area defines one MEMORY "
            r"area and one segment, so the names must differ$")):
        parse_areas(["HIGH=$4000:$2000", "HIGH=$6000:$1000"], _BASIC_START)


def test_parse_areas_rejects_a_name_that_is_not_an_identifier():
    """The name is pasted straight into the config as `MEMORY { <name>: … }`
    and as a segment loading into it: measured against ld65 V2.18, `MY-AREA`,
    `HI SCORE` and `hi.score` are `':' expected` and `2ND` is `'}' expected`
    — syntax errors in a file the user cannot see."""
    for bad in ("MY-AREA", "2ND", "HI SCORE", "hi.score"):
        with pytest.raises(ValueError, match=(
                r"is not usable as a linker identifier")) as e:
            parse_areas([f"{bad}=$4000:$100"], _BASIC_START)
        assert repr(bad) in str(e.value), "the message never quotes the name"


def test_parse_areas_keeps_accepting_the_names_the_toolset_documents():
    """The identifier rule must not narrow what already works: underscores,
    digits after the first character and lowercase all reach ld65 fine."""
    names = ("HIGH", "_hidden", "sprites2", "Level_1")
    assert [a.name for a in
            parse_areas([f"{n}=${0x4000 + i * 0x100:04X}:$100"
                         for i, n in enumerate(names)], _BASIC_START)] == list(names)


def test_parse_areas_rejects_overlap():
    with pytest.raises(ValueError, match=(
            r"^--area TOP starts at \$5000, inside --area HIGH=\$4000:\$2000 "
            r"which ends at \$6000$")):
        parse_areas(["HIGH=$4000:$2000", "TOP=$5000:$1000"], _BASIC_START)


def test_parse_areas_rejects_gap_before_the_next_area():
    with pytest.raises(ValueError, match=(
            r"^--area HIGH=\$4000:\$1000 leaves a \$1000-byte gap before "
            r"--area TOP at \$6000 — a \.prg is a flat file, so raise HIGH's "
            r"size to \$2000 or move TOP down$")):
        parse_areas(["HIGH=$4000:$1000", "TOP=$6000:$1000"], _BASIC_START)


def _stub_tool(dir: Path, name: str, body: str) -> Path:
    p = dir / name
    p.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
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
    src.write_text("; test\n", encoding="utf-8")
    res = build_asm(src)
    assert isinstance(res, BuildResult)
    assert res.prg == tmp_path / "prog.prg" and res.prg.read_bytes()[:2] == b"\x01\x08"
    assert res.labels == tmp_path / "prog.lbl" and "start" in res.labels.read_text(encoding="utf-8")
    ca65_args = (tmp_path / "ca65.args").read_text(encoding="utf-8")
    assert str(src) in ca65_args
    assert "-g" in ca65_args.split()
    ld_args = (tmp_path / "ld65.args").read_text(encoding="utf-8")
    assert "-C" in ld_args and "-Ln" in ld_args


def test_build_error_includes_stderr(tmp_path, monkeypatch):
    bad = _stub_tool(tmp_path, "ca65",
                     "import sys; sys.stderr.write('prog.s(3): syntax error'); sys.exit(1)\n")
    monkeypatch.setenv("C64_TOOLS_CA65", str(bad))
    monkeypatch.setenv("C64_TOOLS_LD65", str(bad))
    src = tmp_path / "prog.s"
    src.write_text("bogus\n", encoding="utf-8")
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
    src.write_text('; top\n.include "inc.s"\n', encoding="utf-8")
    inc.write_text("; include\n", encoding="utf-8")
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
    src.write_text('; top\n.include "inc.s"\n', encoding="utf-8")
    inc.write_text("; include\n", encoding="utf-8")
    _stub_pair(tmp_path, monkeypatch, deps_line=_real_ca65_deps(src, inc))
    res = build_asm(src)
    assert set(res.deps) == {src, inc}
    assert all(p.exists() for p in res.deps)


def test_build_failure_never_touches_existing_prg(tmp_path, monkeypatch):
    src = tmp_path / "prog.s"
    src.write_text("; broken\n", encoding="utf-8")
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
    (nested / "inc.s").write_text('        lda #1\n', encoding="utf-8")
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
        '        rts\n', encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    res = build_asm(src / "main.s", basic_start=0x0801)
    assert Path(res.prg).exists()


_STUB = (
    '        .segment "LOADADDR"\n'
    '        .word $0801\n'
    '        .segment "EXEHDR"\n'
    '        .word nextln\n'
    '        .word 10\n'
    '        .byte $9E, "2061", $00\n'
    'nextln: .word $0000\n'
)
#: EXEHDR is 12 bytes (two words, the SYS token + "2061" + terminator, and
#: the zero link word); CODE below adds one `rts`.
_STUB_BYTES = 13


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_build_area_places_segment_live(tmp_path):
    """The whole point of --area: a segment lands at the address you asked
    for. A .prg is a flat file, so that only works if the gap below the area
    ships as zero bytes — which is what `fill = yes` on MAIN buys."""
    src = tmp_path / "prog.s"
    src.write_text(_STUB
                   + '        .segment "CODE"\n'
                     'start:  rts\n'
                     '        .segment "HIGH"\n'
                     '        .byte $DE, $AD, $BE, $EF\n', encoding="utf-8")
    res = build_asm(src, areas=[Area("HIGH", 0x4000, 0x0100)])
    data = Path(res.prg).read_bytes()
    assert data[:2] == b"\x01\x08"
    area_off = 2 + (0x4000 - 0x0801)
    assert data[area_off:area_off + 4] == b"\xde\xad\xbe\xef"
    assert set(data[2 + _STUB_BYTES:area_off]) == {0}, "the gap was not filled"
    assert len(data) == area_off + 4, "the last area must not be padded"
    assert "__HIGH_LOAD__" in Path(res.labels).read_text(encoding="utf-8")
