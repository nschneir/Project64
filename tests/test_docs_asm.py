import os
import shutil
from pathlib import Path

import pytest

from c64lib.build import build_asm
from tests.doc_helpers import code_blocks

SKILL = Path("skills/6502-assembly/SKILL.md")


def test_hardware_doc_base_addresses():
    doc = Path("skills/c64-development/references/hardware.md").read_text()
    for needle in ("D000", "D400", "D800", "DC00", "DD00"):
        assert needle in doc


def test_asm_skill_warns_about_indexed_loop_calls():
    """The worst bug of the Ms. Muncher dogfood, and then the same pattern a
    second time: a loop keeping its counter in X called a routine that uses X
    as a table index, and the store wrote outside the array."""
    text = SKILL.read_text()
    assert "dec table,x" in text, "the gotcha needs the exemplar that hurts"
    assert "reload" in text
    assert "c64 watch add" in text, "the one-step diagnosis is the payoff"


def test_asm_skill_branch_range_count():
    """The parenthetical cites the dogfood; it hit four build failures across
    four files, ten branches — not the three the bullet claimed."""
    assert "four separate build failures" in SKILL.read_text()


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_skill_skeleton_assembles(tmp_path):
    text = SKILL.read_text()
    blocks = code_blocks(text, "(?:asm|ca65)")
    assert blocks, "6502-assembly SKILL.md must contain an ```asm skeleton block"
    src = tmp_path / "skeleton.s"
    src.write_text(blocks[0])
    res = build_asm(src)
    assert res.prg.read_bytes()[:2] == b"\x01\x08"
