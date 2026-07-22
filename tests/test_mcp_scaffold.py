import json

import anyio
import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as client_session,
)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def call_tool(name: str, args: dict) -> tuple[bool, dict]:
    """Sync helper: call one MCP tool in-memory; returns (is_error, payload)."""
    from c64lib.mcp_server import srv

    async def go():
        async with client_session(srv._mcp_server) as client:
            return await client.call_tool(name, args)

    r = anyio.run(go)
    text = r.content[0].text if r.content else ""
    payload = json.loads(text) if not r.isError and text else {"raw": text}
    return r.isError, payload


def test_server_lists_tools():
    from c64lib.mcp_server import srv

    async def go():
        async with client_session(srv._mcp_server) as client:
            return await client.list_tools()

    tools = anyio.run(go)
    names = [t.name for t in tools.tools]
    assert "c64_session_list" in names
    listed = next(t for t in tools.tools if t.name == "c64_session_list")
    assert "session" in (listed.description or "").lower()


def test_session_list_empty():
    err, payload = call_tool("c64_session_list", {})
    assert err is False
    assert payload == {"sessions": []}


def test_entry_point_importable():
    from c64lib.mcp_server import main
    assert callable(main)
