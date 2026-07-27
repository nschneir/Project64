import json
from pathlib import Path

from tests.doc_helpers import (
    BOOT_FREE,
    code_blocks,
    mentioned_commands,
    valid_mention_paths,
)

README = Path("README.md")
AGENT_SETUP = Path("docs/agent-setup.md")


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
    for doc in (README, AGENT_SETUP):
        unknown = {c for c in mentioned_commands(doc.read_text()) if c not in valid}
        assert not unknown, f"{doc} mentions nonexistent commands: {sorted(unknown)}"


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
