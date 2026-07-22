import re
import shutil
import subprocess
from pathlib import Path

import pytest

from c64lib.romdoc import rom_labels
from c64lib.text import screen_code_to_char

REF = Path("skills/c64-development/references")

TOKENS = {"end": 0x80, "for": 0x81, "next": 0x82, "data": 0x83,
          "goto": 0x89, "gosub": 0x8D, "rem": 0x8F, "print": 0x99, "sys": 0x9E}


def test_rom_routines_covers_label_db():
    doc = (REF / "kernal-routines.md").read_text()
    for name, addr in rom_labels("2.0").items():
        assert name in doc, f"kernal-routines.md missing {name}"
        assert f"{addr:04x}" in doc.lower(), f"kernal-routines.md missing ${addr:04x} for {name}"


def test_basic_internals_token_table_matches_doc():
    doc = (REF / "basic-internals.md").read_text().lower()
    for kw, val in TOKENS.items():
        assert re.search(rf"{kw}\b.{{0,20}}\${val:02x}", doc), f"{kw}=${val:02x} not in doc"


@pytest.mark.skipif(shutil.which("petcat") is None, reason="petcat not installed")
def test_token_values_against_real_petcat(tmp_path):
    src = tmp_path / "probe.bas"
    src.write_text("10 end\n20 for i=1 to 3\n30 next\n40 data 1\n"
                   "50 goto 10\n60 gosub 90\n70 rem x\n80 print\n90 sys 2061\n")
    out = tmp_path / "probe.prg"
    subprocess.run(["petcat", "-w2", "-o", str(out), "--", str(src)], check=True,
                   capture_output=True)
    data = out.read_bytes()
    for kw, val in TOKENS.items():
        assert bytes([val]) in data, f"token {kw}=${val:02x} absent from tokenized probe"


def test_petscii_doc_matches_c64lib():
    doc = (REF / "petscii.md").read_text()
    assert "@ABCDEFGHIJKLMNOPQRSTUVWXYZ" in doc.replace(" ", "")
    # spot-check the doc's stated mapping against the code's ground truth
    assert screen_code_to_char(1) == "A" and screen_code_to_char(0) == "@"
    assert screen_code_to_char(0x81) == "A"  # reverse bit stripped
    assert "reverse" in doc.lower()
