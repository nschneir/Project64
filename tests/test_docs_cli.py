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


def test_cli_md_names_every_machine_profile():
    from c64lib.machines import PROFILES
    text = DOC.read_text()
    for name in PROFILES:
        assert f"`{name}`" in text, f"docs/cli.md never names {name}"
