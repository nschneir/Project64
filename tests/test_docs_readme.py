import json
from pathlib import Path

from tests.doc_helpers import (
    BOOT_FREE,
    code_blocks,
    mentioned_commands,
    valid_mention_paths,
)

README = Path("README.md")


def test_install_section_near_top():
    text = README.read_text()
    assert text.index("## Install") < text.index("## Quickstart")
    assert "brew install vice cc65" in text
    assert "apt install vice cc65" in text


def test_agents_section_covers_the_majors():
    text = README.read_text()
    idx = text.index("## Using with AI coding agents")
    section = text[idx:]
    for agent in ("Claude Code", "Codex", "Cursor", "Gemini", "Antigravity"):
        assert agent in section, f"agents section missing {agent}"
    for path in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursor/mcp.json",
                 "config.toml", "mcp_config.json", ".gemini/settings.json"):
        assert path in section, f"agents section missing {path}"


def test_readme_mcp_json_snipc64_parses():
    text = README.read_text()
    blocks = code_blocks(text, "json")
    for block in blocks:
        json.loads(block)  # every fenced JSON snippet must be valid
    assert any("c64-tools-mcp" in b for b in blocks), \
        "agents section needs a fenced json mcpServers snippet using c64-tools-mcp"


def test_readme_c64_commands_exist():
    valid = valid_mention_paths()  # leaf commands plus bare group names
    unknown = {c for c in mentioned_commands(README.read_text()) if c not in valid}
    assert not unknown, f"README mentions nonexistent commands: {sorted(unknown)}"


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
