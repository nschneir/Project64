import json
import re
from pathlib import Path

import anyio
import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as client_session,
)
from mcp.types import TextContent


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


def text_of(block) -> str:
    """The text of one tool-result content block.

    `CallToolResult.content` is a union — TextContent, ImageContent,
    AudioContent, ResourceLink, EmbeddedResource — and only the first has
    `.text`. Every tool in this server answers with a JSON string, so the
    isinstance check is the invariant these tests already assume; stating it
    narrows the union and turns the day it stops holding into a named failure
    instead of `AttributeError: 'ImageContent' object has no attribute 'text'`.
    """
    assert isinstance(block, TextContent), f"expected text content, got {block!r}"
    return block.text


def call_tool(name: str, args: dict) -> tuple[bool, dict]:
    """Sync helper: call one MCP tool in-memory; returns (is_error, payload)."""
    from c64lib.mcp_server import srv

    async def go():
        async with client_session(srv._mcp_server) as client:
            return await client.call_tool(name, args)

    r = anyio.run(go)
    text = text_of(r.content[0]) if r.content else ""
    payload = json.loads(text) if not r.isError and text else {"raw": text}
    return r.isError, payload


def list_tools():
    """Sync helper: every tool the server registers, over one in-memory
    client session. Shared so no other test file re-implements the dance."""
    from c64lib.mcp_server import srv

    async def go():
        async with client_session(srv._mcp_server) as client:
            return await client.list_tools()

    return anyio.run(go)


def test_server_lists_tools():
    tools = list_tools()
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


def test_every_defined_tool_is_registered_and_described():
    """The roster guard: a `c64_*` function that never reached the server, or
    reached it without a docstring, is invisible to an agent — the description
    IS the documentation an MCP client reads."""
    from c64lib import mcp_server

    listed = {t.name: t for t in list_tools().tools}
    defined = {n for n in dir(mcp_server)
               if n.startswith("c64_") and callable(getattr(mcp_server, n))}
    assert defined <= set(listed), \
        f"defined but not registered: {sorted(defined - set(listed))}"
    undescribed = [n for n, t in listed.items()
                   if not (t.description or "").strip()]
    assert not undescribed, f"registered tools with no description: {undescribed}"


def _leaf_command_paths() -> set[str]:
    """Invocable leaf commands (aliases included, groups excluded) — the
    number index.html means by "N-command CLI"."""
    import click

    from c64lib.cli import main as cli

    out: set[str] = set()

    def walk(cmd, prefix):
        if isinstance(cmd, click.Group):
            for name, sub in cmd.commands.items():
                walk(sub, f"{prefix} {name}")
        else:
            out.add(prefix)

    walk(cli, "c64")
    return out


# The commands docs/agent-setup.md and skills/c64-development/SKILL.md tell an
# MCP-wired agent to shell out for.
DOCUMENTED_CLI_ONLY = ["c64 basic tokenize", "c64 basic detokenize",
                       "c64 sprite encode", "c64 break disable",
                       "c64 break enable"]


def test_documented_cli_only_commands_really_have_no_tool():
    """Both docs promise these five have no MCP twin. When one grows a tool the
    docs go stale silently — which is exactly what happened to the disk verbs'
    entry while the disk plan landed."""
    registered = {t.name for t in list_tools().tools}
    commands = _leaf_command_paths()
    for path in DOCUMENTED_CLI_ONLY:
        assert path in commands, f"docs name {path!r}, which is not a command"
        tool = "c64_" + "_".join(path.split()[1:])
        assert tool not in registered, \
            f"{path} now has {tool} — the CLI-only lists must drop it"


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def test_index_html_counts_match_the_real_inventory():
    """The landing page's headline counts are measured, not remembered. This
    is the guard that keeps a doc count from drifting the next time a tool or
    a skill lands."""
    text = Path("index.html").read_text()
    m = re.search(r"A (\d+)-command CLI, (\d+) MCP tools, (\w+) skills", text)
    assert m, "index.html no longer states the CLI/MCP/skills counts"
    commands, tools, skills = m.groups()
    assert int(commands) == len(_leaf_command_paths()), \
        f"index.html says {commands} commands; the CLI has {len(_leaf_command_paths())}"
    assert int(tools) == len(list_tools().tools), \
        f"index.html says {tools} MCP tools; the server registers " \
        f"{len(list_tools().tools)}"
    actual_skills = sorted(p.name for p in Path("skills").iterdir()
                           if (p / "SKILL.md").exists())
    assert NUMBER_WORDS[skills] == len(actual_skills), \
        f"index.html says {skills} skills; skills/ holds {actual_skills}"
