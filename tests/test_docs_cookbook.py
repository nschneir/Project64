"""Every cookbook recipe must build — and run correctly on a real C64."""

import os
import re
import shutil
from pathlib import Path

import pytest

from c64lib.basic import tokenize
from c64lib.build import build_asm
from c64lib.testing import run_test
from tests.doc_helpers import code_blocks

COOKBOOK = Path("skills/c64-development/references/cookbook.md")


def _blocks(lang: str) -> list[str]:
    return code_blocks(COOKBOOK.read_text(), lang)


def _block_by_key(lang: str, key: str) -> str:
    hits = [b for b in _blocks(lang) if key in (b.splitlines() or [""])[0]]
    assert len(hits) == 1, \
        f"expected exactly 1 {lang} block whose first line contains {key!r}, found {len(hits)}"
    return hits[0]


def test_cookbook_has_recipes():
    assert len(_blocks("basic")) >= 3
    assert len(_blocks("asm")) >= 2


@pytest.mark.skipif(shutil.which("petcat") is None, reason="petcat not installed")
def test_basic_recipes_tokenize(tmp_path):
    for i, block in enumerate(_blocks("basic")):
        src = tmp_path / f"r{i}.bas"
        src.write_text(block)
        prg = tokenize(src, tmp_path / f"r{i}.prg", "2.0")
        assert prg.read_bytes()[:2] == b"\x01\x08"


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_asm_recipes_assemble(tmp_path):
    for i, block in enumerate(_blocks("asm")):
        src = tmp_path / f"r{i}.s"
        src.write_text(block)
        res = build_asm(src)
        assert res.prg.read_bytes()[:2] == b"\x01\x08"


# --- live: each recipe runs and behaves as the cookbook promises -----------

LIVE_RECIPES = [
    # (name, lang, first-line key, steps)
    ("basic-game-loop", "basic", "press q to quit", [
        {"wait": {"text": "PRESS Q TO QUIT"}},
        {"wait": {"text": "..."}},            # frames ticking
        {"key": "q"},
        {"wait": {"text": "BYE"}},
    ]),
    ("basic-prompt-loop", "basic", "guess the number", [
        {"wait": {"text": "YOUR GUESS?"}},
        {"key": "50\n"},
        # row-anchored, not `wait: {text, since}` — the program prints its
        # verdict before the next step samples its `since` baseline, so the
        # fresh occurrence is already counted and `since` would wait for a
        # second one that never comes. See cookbook.md's "Driving it from
        # the CLI" note and tests/programs/guess-the-number/test.yaml.
        {"wait": {"mem": "@6,0", "equals": 20}},        # 20 = screen code 'T'
        {"assert": {"mem": "@6,0", "equals_text": "TOO HIGH"}},
    ]),
    ("basic-poke-stars", "basic", "three stars", [
        {"wait": {"text": "DONE"}},
        # 1024 + 40*5 + 10 = $04D2 holds screen code 42 ('*')
        {"assert": {"mem": "$04D2", "equals": 42}},
    ]),
    ("basic-beep", "basic", "gosub 900", [
        {"wait": {"text": "BEEPED"}},
    ]),
    ("basic-multicolor-sprite", "basic", "multicolor beach ball", [
        {"wait": {"text": "BALL ON"}},
        {"assert": {"mem": "$D015", "equals": 1}},      # sprite 0 enabled
        {"assert": {"mem": "$D01C", "equals": 1}},      # multicolor on
        {"assert": {"mem": "$07F8", "equals": 13}},     # pointer -> $0340
        # 4-bit color registers read back with the high nybble set
        {"assert": {"mem": "$D025", "mask": {"and": "$0f", "equals": [1]}}},
        {"assert": {"mem": "$D026", "mask": {"and": "$0f", "equals": [0]}}},
        {"assert": {"mem": "$D027", "mask": {"and": "$0f", "equals": [2]}}},
        # the shape reached the block: row 10 of the ball is 234,165,87
        {"assert": {"mem": "$0340", "equals": [0, 255, 0]}},
        {"assert": {"mem": "$035E", "equals": [234, 165, 87]}},
    ]),
    ("asm-ball", "asm", "ball.s", [
        # the program's first act is a $93 clear, which wipes the boot
        # banner: the '*' at row 1, col 4 ($042C) -> space. Waiting on that
        # proves the code is running — the boot screen's own '*'s and
        # READY. would satisfy the next two waits otherwise.
        {"wait": {"mem": "$042C", "equals": 32}},
        {"wait": {"text": "*"}},              # the ball — only '*' left now
        {"key": "q"},
        {"wait": {"text": "READY."}},         # clean exit to BASIC
    ]),
    ("asm-beep", "asm", "beep.s", [
        {"wait": {"text": "OK"}},
    ]),
    ("asm-keyhold", "asm", "keyhold.s", [
        # one full iteration draws the paddle (the first mainloop arrival
        # is before any draw), then the poke/until pair IS c64 key hold
        {"until": {"ref": "mainloop", "count": 2}},
        {"assert": {"mem": "@12,20", "equals": 81}},
        {"poke": {"addr": "$CB", "values": [18]}},     # hold D (matrix 18)...
        {"until": {"ref": "mainloop"}},
        {"poke": {"addr": "$CB", "values": [18]}},
        {"until": {"ref": "mainloop"}},
        {"assert": {"mem": "@12,22", "equals": 81}},   # slid two columns
        {"assert": {"mem": "pos", "equals": 22}},      # symbol addressing
        {"assert": {"mem": "@12,20", "equals": 32}},   # old cell erased
    ]),
    ("asm-frame-counter", "asm", "frame counter", [
        {"wait": {"text": "FRAME COUNTER"}},
    ]),
    ("asm-random-lfsr", "asm", "random.s", [
        # LFSR from seed $2A is fully deterministic: 21, 178, 89
        {"wait": {"mem": "$03F2", "equals": 89}},
        {"assert": {"mem": "$03F0", "equals": 21}},
        {"assert": {"mem": "$03F1", "equals": 178}},
    ]),
    ("asm-plotaddr", "asm", "plot.s", [
        # row 10 * 40 + col 20 = 420 -> $0400 + $1A4; '*' is screen code 42
        {"wait": {"mem": "$05A4", "equals": 42}},
    ]),
    ("asm-poke-text", "asm", "hud.s", [
        {"wait": {"text": "SCORE 000"}},
        # 'S' folds to screen code 19 at $0400 + 2*40 + 5 = $0455
        {"assert": {"mem": "$0455", "equals": 19}},
    ]),
    ("asm-digits", "asm", "digits.s", [
        {"wait": {"text": "142"}},
        # '1' = screen code 49, at $0400 + 30
        {"assert": {"mem": "$041E", "equals": 49}},
        {"assert": {"mem": "$0420", "equals": 50}},   # '2' = 50
    ]),
    ("asm-irq-wedge", "asm", "wedge.s", [
        # the wedge unhooks itself after exactly 60 ticks (~1 s)
        {"wait": {"mem": "$03F1", "equals": "$2a", "timeout": 20}},
        {"assert": {"mem": "$03F0", "equals": 60}},
    ]),
    ("asm-sprite", "asm", "sprite.s", [
        # the sweep takes ~190 jiffies, then writes the done marker
        {"wait": {"mem": "$03F0", "equals": "$2a", "timeout": 30}},
        {"assert": {"mem": "$D015", "equals": 1}},    # sprite 0 enabled
        {"assert": {"mem": "$07F8", "equals": 13}},   # pointer: block 13
        {"assert": {"mem": "$D000", "equals": 219}},  # last x written
    ]),
    ("basic-charset", "basic", "lowercase (business)", [
        {"wait": {"text": "HELLO FROM BUSINESS MODE"}},   # decoder is case-canonical
        {"assert": {"mem": "53272", "equals": 23}},        # $D018 readback
    ]),
    ("basic-score-hud", "basic", "score digits", [
        {"wait": {"text": "DONE"}},
        {"assert": {"mem": "$041E", "equals": 49}},   # '1' at $0400+30
        {"assert": {"mem": "$041F", "equals": 52}},   # '4'
        {"assert": {"mem": "$0420", "equals": 50}},   # '2'
    ]),
    ("basic-sprite", "basic", "solid 24x21 sprite", [
        {"wait": {"text": "SPRITE ON"}},
        {"assert": {"mem": "$D015", "equals": 1}},    # sprite 0 enabled
        {"assert": {"mem": "2040", "equals": 13}},    # pointer: block 13
    ]),
    ("basic-sys-plot", "basic", "move the cursor with kernal", [
        {"wait": {"text": "DONE"}},
        # PLOT moved the cursor to row 10, col 5 ($0400+10*40+5=$0595), where
        # "HI" was printed: 'H' = screen code 8, 'I' = 9
        {"assert": {"mem": "$0595", "equals": 8}},
        {"assert": {"mem": "$0596", "equals": 9}},
    ]),
]

# Some recipes seed RND from the jiffy clock (RND(-TI)) so every run deals
# a different game — great for the docs, useless for an assertion. Keyed by
# recipe name, (old, new) is substituted into the extracted block before it
# is written to disk, so the live run is deterministic. See
# tests/programs/guess-the-number/program.bas for the fixed-seed rationale.
LIVE_RECIPE_SUBS = {
    "basic-prompt-loop": ("130 x=rnd(-ti)", "130 x=rnd(-1)"),
}


def test_every_live_recipe_key_resolves():
    for _name, lang, key, _steps in LIVE_RECIPES:
        _block_by_key(lang, key)
    # A substitution keyed on a renamed recipe silently stops applying (the
    # guard below only fires for a recipe that is actually selected), which
    # would turn a seeded live run back into a coin flip.
    names = {n for n, _l, _k, _s in LIVE_RECIPES}
    assert set(LIVE_RECIPE_SUBS) <= names, \
        f"stale sub keys: {set(LIVE_RECIPE_SUBS) - names}"


def _slug(title: str) -> str:
    """GitHub-style anchor slug: word chars (incl. '_') kept, spaces -> '-'."""
    keep = [c for c in title.lower() if c.isalnum() or c in " -_"]
    return "".join(keep).replace(" ", "-")


def test_toc_lists_every_recipe_bidirectionally():
    text = COOKBOOK.read_text()
    assert "## Contents" in text, "cookbook needs a '## Contents' section at the top"
    toc = text.split("## Contents")[1].split("\n## ")[0]
    headings = re.findall(r"^### (.+)$", text, re.M)
    toc_entries = re.findall(r"\[([^\]]+)\]\(#([^)]+)\)", toc)
    listed = [t for t, _ in toc_entries]
    assert sorted(headings) == sorted(listed), (
        f"TOC/heading mismatch: missing {set(headings) - set(listed)}, "
        f"stale {set(listed) - set(headings)}")
    # GitHub dedupes repeated anchors with -1/-2 suffixes _slug doesn't
    # model, so recipe titles must stay slug-unique.
    anchors = [a for _, a in toc_entries]
    assert len(set(anchors)) == len(anchors), f"duplicate anchors in TOC: {anchors}"
    for title, anchor in toc_entries:
        assert anchor == _slug(title), f"bad anchor for {title!r}: {anchor}"


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
@pytest.mark.parametrize("name,lang,key,steps",
                         LIVE_RECIPES, ids=[r[0] for r in LIVE_RECIPES])
def test_cookbook_recipe_runs_live(tmp_path, shared_launch, name, lang, key, steps):
    if lang == "asm" and shutil.which("ca65") is None \
            and not os.environ.get("C64_TOOLS_CA65"):
        pytest.skip("cc65 not installed")
    src = tmp_path / f"{name}{'.bas' if lang == 'basic' else '.s'}"
    text = _block_by_key(lang, key)
    if name in LIVE_RECIPE_SUBS:
        old, new = LIVE_RECIPE_SUBS[name]
        assert old in text, \
            f"{name}: substitution target {old!r} not found in recipe block"
        text = text.replace(old, new, 1)
    src.write_text(text)
    spec = {"name": name, "machine": "c64", "timeout": 30,
            "autorun": True, "program": str(src), "steps": steps}
    result = run_test(spec, launch=shared_launch)
    assert result.passed, [s.detail for s in result.steps] + [result.screen]


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed")
def test_cookbook_frame_stepping_workflow_live(tmp_path, session):
    """The frame-stepping recipe delivers what it promises: until --count N
    advances FRAMES by exactly N."""
    if shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"):
        pytest.skip("cc65 not installed")
    from c64lib.ops import run_until
    from c64lib.symbols import load_labels
    from tests.vice_helpers import wait_for_text
    src = tmp_path / "counter.s"
    src.write_text(_block_by_key("asm", "frame counter"))
    res = build_asm(src)
    labels = load_labels(res.labels)
    s = session
    with s.monitor() as mon:
        try:
            mon.autostart(res.prg.resolve(), run=True)
        finally:
            mon.resume()
    wait_for_text(s, "FRAME COUNTER", timeout=45.0)
    out = run_until(s, labels["mainloop"], timeout=15.0)
    assert out["registers"] is not None
    with s.monitor() as mon:
        f0 = mon.memory_read(labels["FRAMES"], 1)[0]     # stays stopped
    out = run_until(s, labels["mainloop"], timeout=30.0, count=5)
    assert out["registers"] is not None and out["reached"] == 5
    with s.monitor() as mon:
        f1 = mon.memory_read(labels["FRAMES"], 1)[0]
    assert (f1 - f0) % 256 == 5
