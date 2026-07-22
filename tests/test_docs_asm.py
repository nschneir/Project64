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
