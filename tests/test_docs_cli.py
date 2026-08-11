import os
import re
import shutil
from pathlib import Path

import pytest

from tests.doc_helpers import all_command_paths, documented_paths

DOC = Path("docs/cli.md")


def test_every_command_documented_and_vice_versa():
    documented = documented_paths(DOC.read_text())
    actual = all_command_paths()
    missing = actual - documented
    stale = documented - actual
    assert not missing, f"commands lacking a '### `c64 ...`' entry: {sorted(missing)}"
    assert not stale, f"documented commands that do not exist: {sorted(stale)}"


def test_inventory_size_sanity():
    assert len(all_command_paths()) >= 35


def test_session_commands_share_name_option():
    """WS4: one spelling (-s/--name) works on every session-targeting command."""
    import click

    from c64lib.cli import main as cli
    session = cli.commands["session"]
    # click types Group.commands as dict[str, Command]; `session` is a group.
    assert isinstance(session, click.Group)
    for cmd_name in ("start", "stop"):
        cmd = session.commands[cmd_name]
        names = {o for p in cmd.params for o in getattr(p, "opts", [])}
        assert "--name" in names and "-s" in names, \
            f"session {cmd_name} lacks -s/--name (has {sorted(names)})"


def _section(text: str, heading: str) -> str:
    idx = text.index(heading)
    return text[idx:text.index("\n---", idx)]


def test_disk_build_documents_its_labels_key_and_lbl_side_effect():
    """`build_disk` always returns `labels`, and for every `.s` entry it writes
    a `<image-stem>.<cbm-name>.lbl` into the *output* directory. A file
    appearing beside a user's image has to be named where a user would look."""
    section = _section(DOC.read_text(), "### `c64 disk build`")
    assert '"labels"' in section, "the build payload's `labels` key is undocumented"
    assert ".lbl" in section, "the `.lbl` files build writes are undocumented"


def test_mem_get_and_mem_read_document_the_shared_byte_keys():
    """Both payloads carry both `values` and `bytes` since the dogfood filed
    the one-key-each mismatch as a silent KeyError trap."""
    text = DOC.read_text()
    # `_section` runs to the next `---`, and `mem read`'s block contains the
    # `mem get` entry — cut at it, or `mem get`'s `values` answers for both.
    read = _section(text, "### `c64 mem read`").split("### `c64 mem get`")[0]
    assert '"bytes"' in _section(text, "### `c64 mem get`")
    assert '"values"' in read


def test_disk_validate_documents_its_damage_findings():
    """`validate` is the one verb where a DOS status line is a finding about
    the image rather than a failed operation, so it reports rather than
    erroring — the docs' `messages` promise has to say so."""
    section = _section(DOC.read_text(), "### `c64 disk validate`")
    assert "messages" in section
    assert "65" in section, \
        "the docs never mention the DOS error validate reports as a finding"


def test_mem_read_documents_its_text_column_gloss():
    """The gutter is a *gloss*, not the bytes: the docs have to say which
    decoding is in play and how to override it, or the ASCII-on-screen-RAM
    trap comes straight back."""
    section = _section(DOC.read_text(), "### `c64 mem read`")
    assert "--as" in section, "the `--as` encoding override is undocumented"
    assert "screen codes" in section
    assert "text column" in section, "the gutter's label is undocumented"
    assert "text_encoding" in section, "the JSON key is undocumented"


def test_test_run_documents_the_always_present_tests_envelope():
    """A spec-level error emits `{"error", "passed": false, "tests": []}` rather
    than dropping `tests` — 1812's harness crashed on the missing key. A promise
    a harness codes against has to be written down, not just implemented."""
    # These two entries end the file, so there is no trailing `---` for
    # `_section` to cut on: slice between the headings by hand, or the sibling
    # command's envelope answers for `test run`.
    text = DOC.read_text()
    section = text[text.index("### `c64 test run`"):text.index("### `c64 test programs`")]
    assert '"tests": []' in section, "the spec-error envelope is undocumented"
    assert "always present" in section, \
        "the docs never promise `tests` is present whether or not the test ran"


def test_sprite_encode_documents_named_blocks_and_a_visible_background():
    """The sheet grew headers, comments and `--background`; and the old "count
    columns rather than trusting the rendering" warning only ever existed
    because the background pixel was an invisible space."""
    section = _section(DOC.read_text(), "### `c64 sprite encode`")
    assert "--background" in section, "the visible-background option is undocumented"
    assert "`name:` headers" in section and ":hires" in section, \
        "per-block mode headers are undocumented"
    assert "count columns rather than trusting the rendering" not in section, \
        "the trailing-whitespace warning outlived the space background"


def test_charset_encode_documents_its_label_option():
    section = _section(DOC.read_text(), "### `c64 charset encode`")
    assert "--label" in section, "the block-label option is undocumented"


def test_run_documents_its_area_option():
    """`c64 run --area` is what a program linked above the load address needs
    to be runnable at all — undocumented, it may as well not exist."""
    section = _section(DOC.read_text(), "### `c64 run`")
    assert "--area" in section, "the linker-area option is undocumented"
    assert "assembly sources only" in section, \
        "the docs never say --area is rejected for a .bas/.prg/.crt"


def test_test_run_documents_areas_and_the_prg_label_rule():
    """The spec's `areas:` key and the sibling-`.lbl` rule for `program:` are
    the two things La Galaxia's spec went the long way round for."""
    text = DOC.read_text()
    section = text[text.index("### `c64 test run`"):text.index("### `c64 test programs`")]
    assert "areas:" in section, "the spec's `areas:` key is undocumented"
    assert ".lbl" in section, \
        "the sibling label file a `.prg` program: picks up is undocumented"


def test_profile_documents_samples_and_why_one_arrival_lies():
    """`--samples` is only worth reaching for if the docs say what a single
    arrival gets wrong: a per-frame cost that spikes on a repaint every few
    frames reads as fine 27 times in 32."""
    section = _section(DOC.read_text(), "### `c64 profile`")
    assert "--samples" in section, "the sampling option is undocumented"
    assert "bimodal" in section, \
        "the docs never say WHY one arrival can lie about a per-frame cost"
    for key in ('"samples"', '"min"', '"max"', '"mean"'):
        assert key in section, f"the {key} payload key is undocumented"
    assert '"cycles"' in section, \
        "the docs never pin that `cycles` survives at --samples 1"


def test_session_stop_documents_all_and_start_documents_the_notice():
    """Four x64sc processes ran at once during the la-galaxia dogfood, two
    orphaned from an earlier conversation. The one-command cleanup and the
    "N already up" warning only exist for a reader if they are written down —
    including that the notice is on stderr, so `--json` stays parseable."""
    text = DOC.read_text()
    stop = text[text.index("### `c64 session stop`"):
                text.index("### `c64 session reset`")]
    assert "--all" in stop, "the --all flag is undocumented"
    assert '"stopped": [' in stop, \
        "the --all JSON payload (a list, not a name) is undocumented"
    assert "already gone" in stop, \
        "the docs never say --all reaps a session whose emulator has died"
    start = text[text.index("### `c64 session start`"):
                 text.index("### `c64 session ensure`")]
    assert "note: N other session(s) already running" in start, \
        "the already-running notice is undocumented"
    assert "stderr" in start, \
        "the docs never say the notice bypasses --json (it is on stderr)"


#: The three areas the la-galaxia dogfood measured the fill against, and the
#: only thing about them that matters here: the two below `ENGINE` are filled
#: to their declared size, `ENGINE` is not.
_AREA_TRIO = [("SPRITES", 0x2000, 0x1800), ("CHARS", 0x3800, 0x0800),
              ("ENGINE", 0x4000, 0x5000)]


def test_build_documents_which_areas_are_filled():
    """`--area` said "fill" and "contiguous" and never said *which* areas get
    filled — which is what decides how big the file is, and (the trap) that a
    `.res` in an area is content rather than a hole."""
    # Prose wraps; the claim is a sentence, not a line.
    section = " ".join(_section(DOC.read_text(), "### `c64 build`").split())
    assert "Every area below the last one is filled to its declared size" in section, \
        "the docs never say every area but the last is filled to its size"
    assert "the last one is not" in section, \
        "the docs never say the topmost area is left at its real length"
    assert "content, not a hole" in section, \
        "the docs never warn that a `.res` inside an area ships as zeros"


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_the_documented_area_padding_is_the_measured_one(tmp_path):
    """The number in the docs, built — a figure nobody can reproduce is the
    kind that drifts by five bytes and reaches a task brief.

    The fixture is deliberately an *uninitialized* `.res` behind one real
    byte, because that is where the tempting version of the claim ("the last
    area's `.res` costs nothing") is false: the area's segment is `type = ro`,
    so 4,096 reserved bytes ship as zeros. What the last area really saves is
    the tail beyond what it holds — declared `$5000`, and nothing padded out
    to it.
    """
    from c64lib.build import Area, build_asm
    section = " ".join(_section(DOC.read_text(), "### `c64 build`").split())
    m = re.search(r"flat \*\*([\d,]+) bytes\*\*", section)
    assert m, "docs/cli.md no longer states the flat padding cost"
    claimed = int(m.group(1).replace(",", ""))
    # The skill repeats the figure; an unverified second copy is how 14,342
    # survived in demos/la-galaxia/PLAN.md and reached this task's brief.
    skill = Path("skills/6502-assembly/SKILL.md").read_text()
    for stray in re.findall(r"flat ([\d,]{6,}) bytes", skill):
        assert int(stray.replace(",", "")) == claimed, \
            f"SKILL.md says {stray} where docs/cli.md says {m.group(1)}"

    src = tmp_path / "trio.s"
    src.write_text('        .segment "LOADADDR"\n        .word $0801\n'
                   '        .segment "CODE"\nstart:  rts\n'
                   '        .segment "SPRITES"\n        .byte $01\n'
                   '        .segment "CHARS"\n        .byte $02\n'
                   '        .segment "ENGINE"\n        .byte $03\n'
                   '        .res 4096\n')
    res = build_asm(src, areas=[Area(*a) for a in _AREA_TRIO])
    data = res.prg.read_bytes()
    engine_off = 2 + (0x4000 - 0x0801)
    assert engine_off == claimed, (
        f"docs claim {claimed} flat bytes below the last area; the build puts "
        f"ENGINE at file offset {engine_off}")
    # Filled below: CHARS is at its declared address, not packed after CODE.
    assert data[2 + (0x3800 - 0x0801)] == 0x02, "CHARS did not land at $3800"
    # Not filled on top: the declared $5000 tail never ships...
    assert len(data) < claimed + 0x5000, \
        "the last area was padded to its declared size after all"
    # ...but `.res` inside it is content, and does.
    assert data[engine_off:] == bytes([0x03]) + bytes(4096), \
        "an uninitialized .res in the last area did not ship as zero bytes"


def test_wait_documents_the_stopped_machine_timeout():
    """`wait --mem` after a `c64 until` burned 120 s and reported `last value
    1` — the repo's most-repeated footgun. The docs have to say the timeout
    names it, or the reader still reaches for the wrong diagnosis."""
    section = " ".join(_section(DOC.read_text(), "### `c64 wait`").split())
    assert '"machine": "stopped"' in section, \
        "the stopped-machine JSON field is undocumented"
    assert "c64 continue" in section, "the docs never give the way out"
    assert "either side of the wait" in section, \
        ("the docs never say the state is sampled twice (one sample cannot "
         "support 'stopped for the whole wait')")


def test_cli_md_names_every_machine_profile():
    from c64lib.machines import PROFILES
    text = DOC.read_text()
    for name in PROFILES:
        assert f"`{name}`" in text, f"docs/cli.md never names {name}"
