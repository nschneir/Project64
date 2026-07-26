import re
from pathlib import Path

import yaml

from tests.doc_helpers import mentioned_commands, valid_mention_paths

SKILLS = [Path("skills/c64-development/SKILL.md"),
          Path("skills/6502-assembly/SKILL.md"),
          Path("skills/6502-debugging/SKILL.md"),
          Path("skills/cartridge-programming/SKILL.md")]


def _frontmatter(path):
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path}: missing YAML front-matter"
    return yaml.safe_load(m.group(1)), text


def test_frontmatter_parses_with_name_and_description():
    for p in SKILLS:
        if not p.exists():
            continue  # 6502-assembly arrives in Task 5
        fm, _ = _frontmatter(p)
        assert fm["name"] == p.parent.name
        assert 20 < len(fm["description"]) < 1024


def test_c64_commands_in_skills_exist():
    valid = valid_mention_paths()  # leaf commands plus bare group names
    for p in SKILLS:
        if not p.exists():
            continue
        _, text = _frontmatter(p)
        unknown = {c for c in mentioned_commands(text) if c not in valid}
        assert not unknown, f"{p}: mentions nonexistent commands {sorted(unknown)}"


def test_referenced_files_exist():
    for p in SKILLS:
        if not p.exists():
            continue
        text = p.read_text()
        # A repo-root-relative path (skills/.../references/x.md) is resolved
        # from the repo root; a bare references/x.md is skill-local.
        for full in re.findall(r"skills/[\w./-]+/references/[\w.-]+\.md", text):
            assert Path(full).exists(), f"{p}: missing {full}"
        text_wo_full = re.sub(r"skills/[\w./-]+/references/[\w.-]+\.md", "", text)
        for ref in re.findall(r"references/[\w.-]+\.md", text_wo_full):
            assert (p.parent / ref).exists(), f"{p}: missing {ref}"


def test_cartridge_skill_exists_and_is_wired_up():
    p = Path("skills/cartridge-programming/SKILL.md")
    assert p.exists(), "the cartridge skill must ship"
    fm, text = _frontmatter(p)
    assert fm["name"] == "cartridge-programming"
    for topic in ("CBM80", "$DE00", "Ultimax", "bankcall"):
        assert topic in text, f"skill never mentions {topic}"
    # Discoverable from the umbrella skill.
    assert "cartridge-programming" in Path(
        "skills/c64-development/SKILL.md").read_text()


def test_cartridge_reference_commands_exist():
    """The EasyFlash reference is prose the agent acts on too, so its `c64 ...`
    mentions get the same reality check the SKILL.md files get."""
    ref = Path("skills/cartridge-programming/references/easyflash.md")
    assert ref.exists(), "the EasyFlash reference must ship"
    valid = valid_mention_paths()
    unknown = {c for c in mentioned_commands(ref.read_text()) if c not in valid}
    assert not unknown, f"{ref}: mentions nonexistent commands {sorted(unknown)}"
