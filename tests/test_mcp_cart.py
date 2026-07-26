"""MCP parity for the cartridge verbs.

The repo's cardinal rule: every verb reachable from `c64 ...` is reachable as
an MCP tool with the same payload. These tests pin the payloads against the
CLI's (commit 413d21b) and sweep the whole `cart` group for missing tools.
"""

import inspect
from unittest.mock import Mock, patch

import anyio
import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as client_session,
)

from c64lib import mcp_server
from tests.test_cartridge import chip_packet, make_crt
from tests.test_cli_cart import good_body
from tests.test_mcp_scaffold import call_tool


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


@pytest.fixture
def crt(tmp_path):
    return make_crt(tmp_path, name="MCPCART",
                    chips=[chip_packet(0, 0x8000, good_body())])


def _registered_tool_names() -> list[str]:
    async def go():
        async with client_session(mcp_server.srv._mcp_server) as client:
            return await client.list_tools()

    return [t.name for t in anyio.run(go).tools]


def _fake_session():
    s = Mock()
    s.name, s.model, s.pid, s.port = "c64", "c64", 1, 6502
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


# --- offline tools ----------------------------------------------------------

def test_cart_info_tool_matches_the_cli_payload(crt):
    from c64lib.cartridge import cart_info
    assert mcp_server.c64_cart_info(str(crt)) == cart_info(crt)


def test_cart_info_round_trips_through_the_mcp_server(crt):
    """Registered, and its payload survives JSON serialization."""
    err, out = call_tool("c64_cart_info", {"file": str(crt)})
    assert err is False
    assert out["name"] == "MCPCART" and out["mode"] == "8k"


def test_cart_verify_tool_reports_ok_and_reasons(crt, tmp_path):
    assert mcp_server.c64_cart_verify(str(crt)) == {
        "path": str(crt), "ok": True, "reasons": []}
    body = bytearray(good_body())
    body[4:9] = b"\xFF" * 5
    bad = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, bytes(body))],
                   filename="bad.crt")
    res = mcp_server.c64_cart_verify(str(bad))
    assert res["ok"] is False and "CBM80" in res["reasons"][0]


def test_cart_verify_tool_reports_an_unparseable_file_as_data(tmp_path):
    """cart_verify raises on junk; the tool reports it the CLI's way instead."""
    junk = tmp_path / "junk.crt"
    junk.write_bytes(b"not a cartridge at all")
    res = mcp_server.c64_cart_verify(str(junk))
    assert res["ok"] is False and res["path"] == str(junk)
    assert res["error"] and "reasons" not in res


def test_cart_dump_tool_writes_the_window(crt, tmp_path):
    out = tmp_path / "w.bin"
    res = mcp_server.c64_cart_dump(str(crt), str(out), bank=0, window="lo")
    assert res == {"path": str(out), "bank": 0, "window": "lo", "bytes": 8192}
    assert out.read_bytes()[4:9] == bytes([0xC3, 0xC2, 0xCD, 0x38, 0x30])


def test_cart_build_tool_delegates_to_build_easyflash(tmp_path):
    manifest = tmp_path / "game.ef.yaml"
    manifest.write_text("banks: []\n")
    with patch("c64lib.mcp_server.build_easyflash",
               return_value={"crt": "game.crt"}) as bef:
        assert mcp_server.c64_cart_build(str(manifest), output="out.crt") == {
            "crt": "game.crt"}
    (args, kwargs) = bef.call_args
    assert str(args[0]) == str(manifest) and kwargs == {"out": "out.crt"}


def test_cart_convert_tool_builds_the_cartconv_args(tmp_path):
    with patch("c64lib.mcp_server.run_cartconv", return_value="  done\n") as rc:
        res = mcp_server.c64_cart_convert("in.bin", "out.crt", cart_type="normal",
                                          name="DEMO")
    rc.assert_called_once_with(
        ["-i", "in.bin", "-o", "out.crt", "-t", "normal", "-n", "DEMO"])
    assert res == {"source": "in.bin", "output": "out.crt", "cartconv": "done"}


# --- live tool --------------------------------------------------------------

def test_cart_bank_reads_the_registers_and_releases():
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([0x07, 0x00, 0x87])
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_cart_bank", {})
    assert err is False
    assert out == {"bank": 7, "de00": "$07", "de02": "$87", "mode": "16k",
                   "led": True}
    mon.memory_read.assert_called_once_with(0xDE00, 3)
    # an inspection command: it must never resume a halted machine
    mon.release.assert_called_once()
    mon.resume.assert_not_called()


# --- lockstep ---------------------------------------------------------------

def test_every_cart_cli_command_has_an_mcp_tool():
    """The repo's cardinal rule: CLI and MCP move in lockstep."""
    from c64lib.cli import main
    registered = _registered_tool_names()
    for name in main.commands["cart"].commands:
        tool = f"c64_cart_{name.replace('-', '_')}"
        assert hasattr(mcp_server, tool), f"missing MCP tool {tool}"
        assert tool in registered, f"{tool} is not registered with the server"


def test_package_tool_accepts_the_cart_options():
    sig = inspect.signature(mcp_server.c64_package)
    for param in ("fmt", "cart_type", "wrap"):
        assert param in sig.parameters
    with patch("c64lib.mcp_server.package_program", return_value={}) as pp:
        mcp_server.c64_package("game.s", output="game.crt", fmt="crt",
                               cart_type="ultimax", wrap=True)
    kwargs = pp.call_args.kwargs
    assert kwargs["fmt"] == "crt" and kwargs["cart_type"] == "ultimax"
    assert kwargs["wrap"] is True


def test_session_start_tool_accepts_a_cart():
    assert "cart" in inspect.signature(mcp_server.c64_session_start).parameters
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.launch.return_value = s
        mcp_server.c64_session_start(cart="game.crt")
    assert S.launch.call_args.kwargs["cart"] == "game.crt"
