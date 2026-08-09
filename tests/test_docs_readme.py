import json
import re
from pathlib import Path

from tests.doc_helpers import (
    BOOT_FREE,
    all_command_paths,
    code_blocks,
    mentioned_commands,
    valid_mention_paths,
)
# Imported at module scope, not inside the tests that use them: conftest's
# session-wide `_track_launches` swaps `subprocess.Popen` for a plain
# function, and importing `mcp` after that point dies on its
# `subprocess.Popen[bytes]` annotation. Collection-time imports run first.
from tests.test_mcp_scaffold import _leaf_command_paths, list_tools

README = Path("README.md")
AGENT_SETUP = Path("docs/agent-setup.md")
MCP_DOC = Path("docs/mcp.md")


def test_install_section_near_top():
    text = README.read_text()
    assert text.index("## Install") < text.index("## Quickstart")
    assert "brew install vice cc65" in text
    assert "apt install vice cc65" in text


def test_readme_links_the_agent_setup_doc():
    text = README.read_text()
    idx = text.index("## Using with AI coding agents")
    section = text[idx:text.index("\n## ", idx + 1)]
    assert "docs/agent-setup.md" in section, \
        "the agents section must link the moved setup doc"


def test_agent_setup_covers_the_majors():
    text = AGENT_SETUP.read_text()
    for agent in ("Claude Code", "Codex", "Cursor", "Gemini", "Antigravity"):
        assert agent in text, f"agent setup doc missing {agent}"
    for path in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursor/mcp.json",
                 "config.toml", "mcp_config.json", ".gemini/settings.json"):
        assert path in text, f"agent setup doc missing {path}"


def test_mcp_json_snipc64_parses():
    readme_blocks = code_blocks(README.read_text(), "json")
    setup_blocks = code_blocks(AGENT_SETUP.read_text(), "json")
    for block in readme_blocks + setup_blocks:
        json.loads(block)  # every fenced JSON snippet must be valid
    assert any("c64-tools-mcp" in b for b in setup_blocks), \
        "agent setup doc needs a fenced json mcpServers snippet using c64-tools-mcp"


def test_readme_names_the_domain_skills_beside_their_sections():
    """The Cartridges section names `cartridge-programming`; the Disk images
    section shipped without ever naming `disk-io-programming`, so the skill
    was undiscoverable from the one page that introduces disk work."""
    text = README.read_text()
    for heading, skill in (("## Disk images", "disk-io-programming"),
                           ("## Cartridges", "cartridge-programming")):
        idx = text.index(heading)
        section = text[idx:text.index("\n## ", idx + 1)]
        assert skill in section, f"{heading} never names the `{skill}` skill"


def test_readme_c64_commands_exist():
    valid = valid_mention_paths()  # leaf commands plus bare group names
    for doc in (README, AGENT_SETUP, MCP_DOC):
        unknown = {c for c in mentioned_commands(doc.read_text()) if c not in valid}
        assert not unknown, f"{doc} mentions nonexistent commands: {sorted(unknown)}"


def test_readme_release_line_matches_pyproject():
    """`pyproject.toml` is the single version source.
    `tests/test_package.py::test_changelog_has_current_version` pins the
    CHANGELOG to it, but nothing pinned the README, so a bump (or a revert)
    could leave the release line stale and the suite green — it had to be
    updated by hand for both 0.7.0 and 0.8.0. Parse both sides; never
    hard-code a version here, or this test becomes the next stale copy."""
    from tests.test_package import _pyproject_version

    m = re.search(r"current release \*\*v([^*]+)\*\*", README.read_text())
    assert m, "README no longer states 'current release **vX.Y.Z**'"
    assert m.group(1) == _pyproject_version(), \
        f"README says v{m.group(1)}; pyproject says {_pyproject_version()}"


def test_supported_machines_table_matches_profiles():
    """Every fact in the README model table is enforced against machines.py
    and the captured boot banners — the table cannot drift."""
    from c64lib.machines import PROFILES
    text = README.read_text()
    idx = text.index("## Supported machines")
    end = text.index("\n## ", idx + 1)
    section = text[idx:end]
    rows = {}
    for line in section.splitlines():
        if line.startswith("| `c64"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows[cells[0].strip("`")] = cells
    assert set(rows) == set(PROFILES), \
        f"table models {sorted(rows)} != profiles {sorted(PROFILES)}"
    for name, p in PROFILES.items():
        cells = rows[name]   # 0=model 1=ram 2=free 3=basic 4=screen 5=notes
        assert f"{p.ram_kb} KB" in cells[1], f"{name}: RAM cell {cells[1]!r}"
        assert BOOT_FREE[name] in cells[2], f"{name}: free cell {cells[2]!r}"
        assert p.basic_version in cells[3], f"{name}: BASIC cell {cells[3]!r}"
        assert f"{p.screen_cols}×{p.screen_rows}" in cells[4], \
            f"{name}: screen cell {cells[4]!r}"


def test_mcp_md_names_every_tool():
    """`docs/mcp.md` claims to map every registered tool. A tool added
    without a row would leave that claim false and silently wrong — the same
    drift index.html's counts used to have. The tool docstrings remain the
    per-tool reference (guarded by test_mcp_scaffold's roster test); this
    only pins that the map is complete."""
    text = MCP_DOC.read_text()
    missing = sorted(t.name for t in list_tools().tools
                     if f"`{t.name}`" not in text)
    assert not missing, f"docs/mcp.md never names: {missing}"


def _invocable_paths() -> set[str]:
    """Everything a table row may point at. `_leaf_command_paths()` is the
    inventory index.html's command count uses (leaves only);
    `all_command_paths()` adds the groups that also run bare — `c64 reg` is
    one, and it is the command `c64_reg_get` twins."""
    return _leaf_command_paths() | all_command_paths()


def _mcp_table_commands() -> set[str]:
    """Every `c64 ...` command backticked inside a table row of docs/mcp.md,
    trimmed to its command path (trailing options/arguments dropped by
    longest-prefix match). A span that matches no real command is returned
    whole, so the caller reports it verbatim."""
    invocable = _invocable_paths()
    out: set[str] = set()
    for line in MCP_DOC.read_text().splitlines():
        if not line.startswith("|"):
            continue
        for span in re.findall(r"`(c64 [^`]+)`", line):
            words = span.split()
            for depth in range(len(words), 1, -1):
                cand = " ".join(words[:depth])
                if cand in invocable:
                    out.add(cand)
                    break
            else:
                out.add(span)
    return out


def test_mcp_md_commands_exist():
    """The CLI side of the map is measured too: a renamed or dropped command
    must fail here rather than leave the table pointing at a command that no
    longer exists."""
    invocable = _invocable_paths()
    unknown = sorted(c for c in _mcp_table_commands() if c not in invocable)
    assert not unknown, f"docs/mcp.md maps nonexistent commands: {unknown}"


# index.html's headline CLI/MCP/skills counts are gated by
# tests/test_mcp_scaffold.py::test_index_html_counts_match_the_real_inventory,
# which owns the definition of what "N-command CLI" counts (invocable leaves,
# groups excluded — `c64 reg` is both, and is counted once).
