from pathlib import Path

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


def test_cli_md_names_every_machine_profile():
    from c64lib.machines import PROFILES
    text = DOC.read_text()
    for name in PROFILES:
        assert f"`{name}`" in text, f"docs/cli.md never names {name}"
