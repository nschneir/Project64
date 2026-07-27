from pathlib import Path

import pytest

from c64lib.machines import get_profile
from c64lib.testing import TestError, _prepare, load_test, program_test


def _write(tmp_path, text, name="t.yaml"):
    f = tmp_path / name
    f.write_text(text)
    return f


def test_defaults_applied(tmp_path):
    f = _write(tmp_path, "steps:\n  - key: \"RUN\\n\"\n")
    spec = load_test(f)
    assert spec["name"] == "t"
    assert spec["machine"] == "c64"
    assert spec["timeout"] == 30
    assert spec["autorun"] is True
    assert spec["steps"] == [{"key": "RUN\n"}]


def test_program_resolved_relative_to_yaml(tmp_path):
    prog = tmp_path / "prog.bas"
    prog.write_text('10 print "hi"\n')
    f = _write(tmp_path, "program: prog.bas\nsteps: []\n")
    spec = load_test(f)
    assert spec["program"] == str(prog.resolve())


def test_missing_program_rejected(tmp_path):
    f = _write(tmp_path, "program: nosuch.bas\n")
    with pytest.raises(TestError, match="nosuch"):
        load_test(f)


def test_bad_machine_rejected(tmp_path):
    f = _write(tmp_path, "machine: amiga500\nsteps: []\n")
    with pytest.raises(KeyError, match="amiga500"):
        load_test(f)


def test_bad_step_rejected(tmp_path):
    f = _write(tmp_path, "steps:\n  - frobnicate: 1\n")
    with pytest.raises(TestError, match="step 1"):
        load_test(f)


def test_load_accepts_poke_and_until_steps(tmp_path):
    f = _write(tmp_path, (
        "steps:\n"
        "  - poke:  { addr: \"$97\", values: [68] }\n"
        "  - poke:  { addr: \"$97\", value: 68 }\n"
        "  - until: { ref: tick, count: 3, timeout: 10 }\n"
        "  - until: { ref: \"$0419\" }\n"
    ))
    spec = load_test(f)
    assert [next(iter(s)) for s in spec["steps"]] == ["poke", "poke",
                                                      "until", "until"]


def test_load_rejects_malformed_poke_and_until(tmp_path):
    f = _write(tmp_path, "steps:\n  - until: { count: 3 }\n")
    with pytest.raises(TestError, match="ref"):
        load_test(f)
    f = _write(tmp_path, "steps:\n  - until: { ref: x, frames: 2 }\n")
    with pytest.raises(TestError, match="frames"):
        load_test(f)
    f = _write(tmp_path, "steps:\n  - poke: { values: [1] }\n")
    with pytest.raises(TestError, match="addr"):
        load_test(f)
    f = _write(tmp_path, "steps:\n  - poke: { addr: \"$97\" }\n")
    with pytest.raises(TestError, match="value"):
        load_test(f)


def test_spec_example_shape(tmp_path):
    prog = tmp_path / "hello.bas"
    prog.write_text('10 print "hello, world"\n')
    f = _write(tmp_path, """\
name: hello-world
machine: c64
program: hello.bas
autorun: false
timeout: 30
steps:
  - wait: { text: "READY." }
  - key: "RUN\\n"
  - wait: { text: "HELLO, WORLD", timeout: 5 }
  - assert: { mem: "$0400", equals_text: "HELLO, WORLD" }
  - assert: { reg: pc, in_range: ["$C000", "$E000"] }
""")
    spec = load_test(f)
    assert spec["autorun"] is False
    assert len(spec["steps"]) == 5


def test_program_test_synthesis():
    spec = program_test(Path("tests/programs/hello-basic"))
    assert spec["name"] == "hello-basic"
    assert spec["autorun"] is True
    assert spec["program"].endswith("tests/programs/hello-basic/program.bas")
    assert spec["steps"] == [
        {"wait": {"text": "HELLO FROM BASIC"}},
        {"wait": {"text": "2+2= 4"}},
    ]


def test_program_test_rejects_non_program_dir(tmp_path):
    with pytest.raises(TestError, match="example-program"):
        program_test(tmp_path)


def test_load_test_rejects_non_mapping(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("- just\n- a list\n")
    with pytest.raises(TestError, match="YAML mapping"):
        load_test(f)


def test_prepare_prg_passthrough(tmp_path):
    prg = tmp_path / "x.prg"
    prg.write_bytes(b"\x01\x08")
    assert _prepare(str(prg), get_profile("c64")) == (prg, None)


def test_prepare_unknown_extension(tmp_path):
    with pytest.raises(TestError, match="cannot run"):
        _prepare(str(tmp_path / "x.txt"), get_profile("c64"))


def test_sample_step_validation(tmp_path):
    f = _write(tmp_path, "steps:\n  - sample: { mem: \"$D000\", as: x0 }\n")
    spec = load_test(f)
    assert spec["steps"][0] == {"sample": {"mem": "$D000", "as": "x0"}}
    bad = _write(tmp_path, "steps:\n  - sample: { mem: \"$D000\" }\n")
    with pytest.raises(TestError, match="missing"):
        load_test(bad)


def test_program_test_prefers_test_yaml(tmp_path):
    from c64lib.testing import program_test
    d = tmp_path / "prog"
    d.mkdir()
    (d / "program.bas").write_text('10 print "hi"\n')
    (d / "expect.txt").write_text("HI\n")
    (d / "test.yaml").write_text(
        "steps:\n  - assert: {mem: '$D015', equals: 0}\n")
    spec = program_test(d)
    kinds = [next(iter(s)) for s in spec["steps"]]
    assert kinds[0] == "wait" and "assert" in kinds     # expect lines prepended
    assert spec["program"].endswith("program.bas")
    assert spec["name"] == "prog"


def test_program_test_accepts_a_disk_only_directory(tmp_path):
    """A disk program ships no program.bas/.s: the image is what runs."""
    d = tmp_path / "prog"
    d.mkdir()
    (d / "game.d64").write_bytes(bytes(174848))
    (d / "expect.txt").write_text("DISK LOAD OK\n")
    (d / "test.yaml").write_text("disk: game.d64\n")
    spec = program_test(d)
    assert spec["disk"] == str((d / "game.d64").resolve())
    assert spec.get("program") is None
    assert spec["steps"] == [{"wait": {"text": "DISK LOAD OK"}}]


def test_program_test_does_not_autostart_a_disk_directorys_source(tmp_path):
    """A `program.s` beside a disk spec is the disk's source, not a second
    thing to autostart — promoting it would boot the wrong artifact."""
    d = tmp_path / "prog"
    d.mkdir()
    (d / "program.s").write_text("nop\n")
    (d / "game.d64").write_bytes(bytes(174848))
    (d / "expect.txt").write_text("HI\n")
    (d / "test.yaml").write_text("disk: game.d64\n")
    spec = program_test(d)
    assert spec.get("program") is None
