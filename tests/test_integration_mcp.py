"""MCP integration: stdio subprocess handshake + live-x64sc flow in-memory."""

import json
import os
import shutil
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import (
    create_connected_server_and_client_session as client_session,
)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def test_stdio_subprocess_handshake(tmp_path):
    """The installed c64-tools-mcp binary serves MCP over stdio.
    No emulator needed — c64_session_list works on an empty registry."""
    exe = Path(sys.executable).parent / "c64-tools-mcp"
    assert exe.exists(), "c64-tools-mcp entry point not installed"

    async def go():
        params = StdioServerParameters(
            command=str(exe), env={**os.environ, "C64_TOOLS_HOME": str(tmp_path)}
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as cs:
                await cs.initialize()
                tools = await cs.list_tools()
                names = [t.name for t in tools.tools]
                assert "c64_screen_text" in names and "c64_build" in names
                r = await cs.call_tool("c64_session_list", {})
                assert json.loads(r.content[0].text) == {"sessions": []}

    anyio.run(go)


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
def test_live_flow_through_mcp():
    """Full loop via MCP tools: start session, wait for READY., type a BASIC
    program, wait for its output, read memory, stop."""
    from c64lib.mcp_server import srv

    async def go():
        async with client_session(srv._mcp_server) as client:
            async def call(name, args):
                r = await client.call_tool(name, args)
                assert not r.isError, r.content[0].text
                return json.loads(r.content[0].text)

            out = await call("c64_session_start", {"model": "c64"})
            try:
                assert out["model"] == "c64"
                fired = await call("c64_wait_text", {"text": "READY.", "timeout": 45})
                assert fired["fired"] == "text"
                await call("c64_basic_type",
                           {"text": '10 print "HELLO VIA MCP"', "run": True})
                fired = await call("c64_wait_text",
                                   {"text": "HELLO VIA MCP", "timeout": 30})
                assert fired["fired"] == "text"
                screen = await call("c64_screen_text", {})
                assert "HELLO VIA MCP" in screen["text"]
                mem = await call("c64_mem_read", {"addr": "$0400", "length": 40})
                assert len(mem["hex"]) == 80
            finally:
                await call("c64_session_stop", {})

    anyio.run(go)
