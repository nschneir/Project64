"""MCP parity for the disk file & block verbs.

The repo's cardinal rule: every verb reachable from `c64 disk ...` is reachable
as an MCP tool with the same payload. These tests pin the payloads against the
CLI's (commits 48fadd7 + 27ea8d5) and sweep the whole `disk` group for missing
tools.
"""

import inspect
import json
import shutil

import pytest

from c64lib import mcp_server
from c64lib.disk import DiskError
from tests.test_mcp_scaffold import call_tool, list_tools

needs_c1541 = pytest.mark.skipif(shutil.which("c1541") is None,
                                 reason="needs VICE's c1541")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


@pytest.fixture
def image(tmp_path):
    """A real d64 with one 1-block file, built through the MCP tools."""
    img = tmp_path / "game.d64"
    payload = tmp_path / "f1.prg"
    payload.write_bytes(b"\x01\x08hello world payload")
    mcp_server.c64_disk_create(str(img), label="mygame")
    mcp_server.c64_disk_put(str(img), str(payload), "alpha")
    return img


def make_image(tmp_path, *names):
    """A real d64 with one 1-block file per name."""
    img = tmp_path / "many.d64"
    payload = tmp_path / "f1.prg"
    payload.write_bytes(b"\x01\x08hello world payload")
    mcp_server.c64_disk_create(str(img), label="mygame")
    for name in names:
        mcp_server.c64_disk_put(str(img), str(payload), name)
    return img


def _registered_tool_names() -> list[str]:
    return [t.name for t in list_tools().tools]


def _cli(argv: list[str]) -> dict:
    """Run one --json CLI command, returning its payload."""
    from click.testing import CliRunner

    from c64lib.cli import main
    r = CliRunner().invoke(main, ["--json", *argv])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)


def _manifest(tmp_path):
    (tmp_path / "loader.prg").write_bytes(b"\x01\x08payload")
    m = tmp_path / "game.disk.yaml"
    m.write_text('label: MYGAME\nfiles:\n  - {src: loader.prg, name: "*"}\n')
    return m


# --- rename / rm ------------------------------------------------------------

@needs_c1541
def test_rename_tool_payload_matches_the_cli(image):
    assert mcp_server.c64_disk_rename(str(image), "alpha", "beta") == {
        "image": str(image), "old": "alpha", "name": "beta"}
    assert [f["name"] for f in mcp_server.c64_disk_ls(str(image))["files"]] == ["beta"]


@needs_c1541
def test_rename_tool_reports_a_missing_source_file(image):
    with pytest.raises(DiskError, match="(?i)file not found"):
        mcp_server.c64_disk_rename(str(image), "nope", "beta")


@needs_c1541
def test_rename_tool_validates_the_new_name(image):
    with pytest.raises(DiskError):
        mcp_server.c64_disk_rename(str(image), "alpha", "be:ta")


@needs_c1541
def test_rm_tool_payload_matches_the_cli(image):
    assert mcp_server.c64_disk_rm(str(image), "alpha") == {
        "image": str(image), "name": "alpha", "deleted": 1}
    with pytest.raises(DiskError, match="no file named"):
        mcp_server.c64_disk_rm(str(image), "alpha")


@needs_c1541
def test_rm_tool_counts_wildcard_matches(tmp_path):
    img = make_image(tmp_path, "alpha", "album", "other")
    assert mcp_server.c64_disk_rm(str(img), "al*")["deleted"] == 2
    assert [f["name"] for f in mcp_server.c64_disk_ls(str(img))["files"]] == ["other"]


@needs_c1541
def test_rm_tool_rejects_a_dos_metacharacter(image):
    """The guard lives in the library, so both front ends refuse it alike."""
    with pytest.raises(DiskError, match="metacharacter"):
        mcp_server.c64_disk_rm(str(image), "al,pha")


@needs_c1541
def test_rm_tool_surfaces_a_missing_file_as_a_tool_error(image):
    err, out = call_tool("c64_disk_rm", {"image": str(image), "name": "nope"})
    assert err is True and "no file named" in out["raw"]


# --- block read -------------------------------------------------------------

@needs_c1541
def test_block_read_tool_returns_hex_not_data(image):
    res = mcp_server.c64_disk_block_read(str(image), 18, 0)
    assert res["bytes"] == 256 and res["hex"].startswith("12014100")
    assert "data" not in res and "output" not in res
    assert res == {"image": str(image), "track": 18, "sector": 0,
                   "bytes": 256, "hex": res["hex"]}


@needs_c1541
def test_block_read_tool_writes_a_file_and_drops_the_hex(image, tmp_path):
    out = tmp_path / "bam.bin"
    res = mcp_server.c64_disk_block_read(str(image), 18, 0, output=str(out))
    assert res == {"image": str(image), "track": 18, "sector": 0,
                   "output": str(out), "bytes": 256}
    assert out.stat().st_size == 256


@needs_c1541
def test_block_read_tool_payloads_match_the_cli(image, tmp_path):
    """Lockstep: the same scenario through both front ends, both shapes."""
    assert mcp_server.c64_disk_block_read(str(image), 18, 0) == _cli(
        ["disk", "block", "read", str(image), "18", "0"])
    out = tmp_path / "bam.bin"
    assert mcp_server.c64_disk_block_read(str(image), 18, 0,
                                          output=str(out)) == _cli(
        ["disk", "block", "read", str(image), "18", "0", "-o", str(out)])


@needs_c1541
def test_block_read_tool_rejects_a_bad_track(image):
    with pytest.raises(DiskError, match="track 40 out of range"):
        mcp_server.c64_disk_block_read(str(image), 40, 0)


@needs_c1541
def test_block_read_tool_reports_an_unwritable_output(image, tmp_path):
    """A dump the host refuses is a message naming the path, as in the CLI."""
    out = tmp_path / "no-such-dir" / "bam.bin"
    with pytest.raises(OSError, match=str(out)):
        mcp_server.c64_disk_block_read(str(image), 18, 0, output=str(out))


# --- block write ------------------------------------------------------------

def test_block_write_tool_takes_an_int_list_like_mem_write():
    """values follows the established c64_mem_write convention, not the CLI's
    string tokens."""
    for tool in (mcp_server.c64_disk_block_write, mcp_server.c64_mem_write):
        assert inspect.signature(tool).parameters["values"].annotation in (
            "list[int]", "list[int] | None")


@needs_c1541
def test_block_write_tool_pokes_and_matches_the_cli(image):
    res = mcp_server.c64_disk_block_write(str(image), 1, 0, values=[0xDE, 0xAD],
                                          offset=4)
    assert res == {"image": str(image), "track": 1, "sector": 0,
                   "written": 2, "offset": 4}
    assert res == _cli(["disk", "block", "write", str(image), "1", "0",
                        "$de", "$ad", "--offset", "4"])
    data = bytes.fromhex(mcp_server.c64_disk_block_read(str(image), 1, 0)["hex"])
    assert data[4:6] == bytes([0xDE, 0xAD])


@needs_c1541
def test_block_write_tool_pokes_at_offset_zero_by_default(image):
    res = mcp_server.c64_disk_block_write(str(image), 1, 0, values=[1, 2])
    assert res["offset"] == 0 and res["written"] == 2
    data = bytes.fromhex(mcp_server.c64_disk_block_read(str(image), 1, 0)["hex"])
    assert data[:2] == bytes([1, 2])


@needs_c1541
def test_block_write_tool_replaces_a_whole_sector_from_a_file(image, tmp_path):
    src = tmp_path / "sector.bin"
    src.write_bytes(bytes(range(256)))
    res = mcp_server.c64_disk_block_write(str(image), 1, 0, src=str(src))
    assert res == {"image": str(image), "track": 1, "sector": 0,
                   "written": 256, "offset": 0}
    assert res == _cli(["disk", "block", "write", str(image), "1", "0",
                        "--from", str(src)])


@needs_c1541
def test_block_write_tool_needs_exactly_one_source(image, tmp_path):
    src = tmp_path / "sector.bin"
    src.write_bytes(bytes(range(256)))
    for kwargs in ({}, {"src": str(src), "values": [1]}):
        with pytest.raises(ValueError, match="exactly one"):
            mcp_server.c64_disk_block_write(str(image), 1, 0, **kwargs)


@needs_c1541
def test_block_write_tool_rejects_offset_with_src(image, tmp_path):
    """--from replaces the whole sector, so an offset for it is contradictory —
    and an explicit --offset 0 is just as contradictory as a nonzero one. The
    CLI decides that from the parameter source; the tool needs None to tell an
    explicit 0 from an unset one, and says it in the CLI's words."""
    from click.testing import CliRunner

    from c64lib.cli import main
    src = tmp_path / "sector.bin"
    src.write_bytes(bytes(range(256)))
    for offset in (4, 0):
        with pytest.raises(ValueError) as e:
            mcp_server.c64_disk_block_write(str(image), 1, 0, src=str(src),
                                            offset=offset)
        r = CliRunner().invoke(main, ["--json", "disk", "block", "write",
                                      str(image), "1", "0", "--from", str(src),
                                      "--offset", str(offset)])
        assert r.exit_code != 0
        assert str(e.value) == json.loads(r.output)["error"]


@needs_c1541
def test_block_write_tool_rejects_a_poke_past_the_end(image):
    with pytest.raises(DiskError, match="runs past the end"):
        mcp_server.c64_disk_block_write(str(image), 1, 0, values=[1, 2],
                                        offset=255)


@needs_c1541
def test_block_write_tool_reports_a_short_source_file(image, tmp_path):
    src = tmp_path / "short.bin"
    src.write_bytes(bytes(4))
    with pytest.raises(DiskError, match="exactly 256"):
        mcp_server.c64_disk_block_write(str(image), 1, 0, src=str(src))


# --- validate / build -------------------------------------------------------

@needs_c1541
def test_validate_tool_matches_the_cli(image):
    res = mcp_server.c64_disk_validate(str(image))
    assert res["clean"] is True
    assert set(res) == {"image", "clean", "blocks_free_before",
                        "blocks_free_after", "repaired_blocks", "messages"}
    assert res == _cli(["disk", "validate", str(image)])


@needs_c1541
def test_build_tool_matches_the_cli(tmp_path):
    res = mcp_server.c64_disk_build(str(_manifest(tmp_path)))
    assert res["files"] == ["mygame"] and res["blocks_total"] == 664
    assert set(res) == {"image", "label", "files", "blocks_used", "blocks_free",
                        "blocks_total", "run"}
    assert res == _cli(["disk", "build", str(_manifest(tmp_path))])


@needs_c1541
def test_build_tool_honours_output_and_model(tmp_path):
    out = tmp_path / "out.d64"
    res = mcp_server.c64_disk_build(str(_manifest(tmp_path)), output=str(out),
                                    model="c64pal")
    assert res["image"] == str(out) and out.exists()
    assert res["run"].startswith("x64sc") and "-ntsc" not in res["run"]


def test_build_tool_rejects_an_unknown_model(tmp_path):
    with pytest.raises(KeyError, match="unknown machine profile"):
        mcp_server.c64_disk_build(str(_manifest(tmp_path)), model="vic20")
    assert not (tmp_path / "game.d64").exists()      # nothing written


@needs_c1541
def test_build_tool_round_trips_through_the_mcp_server(tmp_path):
    err, out = call_tool("c64_disk_build", {"manifest": str(_manifest(tmp_path))})
    assert err is False and out["label"] == "MYGAME"


# --- lockstep ---------------------------------------------------------------

def test_every_disk_cli_command_has_an_mcp_tool():
    """The repo's cardinal rule: CLI and MCP move in lockstep."""
    from c64lib.cli import main
    registered = _registered_tool_names()
    disk = main.commands["disk"]
    for name, cmd in disk.commands.items():
        if name == "delete":
            continue                            # alias of rm
        leaves = ([f"{name}_{sub}" for sub in cmd.commands]
                  if hasattr(cmd, "commands") else [name])
        for leaf in leaves:
            tool = f"c64_disk_{leaf.replace('-', '_')}"
            assert hasattr(mcp_server, tool), f"missing MCP tool {tool}"
            assert tool in registered, f"{tool} is not registered with the server"
