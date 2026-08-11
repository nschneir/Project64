"""The demo roster is published in three places: the README's demos section,
demos/README.md, and the site's demos section (index.html). Nothing generates
one from another — GitHub renders the markdown as-is and the site is
hand-authored — so this is the guard that keeps the three surfaces telling
the same story: same demos, same tiers, a description on every row, and no
demo directory left unlisted anywhere.
"""

import re
from pathlib import Path

README = Path("README.md")
DEMOS_README = Path("demos/README.md")
INDEX = Path("index.html")
DEMOS_DIR = Path("demos")

# tier key -> the heading/marker text every surface must use for it
TIERS = {
    "test": "Test demos",
    "game": "Game demos",
    "misc": "Miscellaneous cool stuff",
}

_MD_ROW = re.compile(r"^\|.*?\[[^\]]+\]\(([^)]+)\)")
_MD_SEP = re.compile(r"^\|[\s:|-]+$")
# The tables say what each demo *is*; they carry no status of any kind.
_RETIRED = re.compile(r"✅|🔲|dogfood", re.I)


def _md_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _md_roster(text: str, section: str | None = None) -> dict[str, str]:
    """slug -> tier from a markdown surface.

    Rows are table lines whose first link points into demos/; the tier is
    whichever tier marker (a `## ` heading or a bold lead-in) came last.
    Every table must declare a Description column by name, and each row's
    description is read at that column's index — not from the last cell,
    which would still pass if the column were dropped.
    """
    if section is not None:
        idx = text.find(section)
        assert idx != -1, f"markdown surface lost its {section!r} heading"
        end = text.find("\n## ", idx + 1)
        text = text[idx:end if end != -1 else len(text)]
    roster: dict[str, str] = {}
    tier = None
    desc_col: int | None = None
    for line in text.splitlines():
        for key, title in TIERS.items():
            if line.startswith(("#", "**")) and title in line:
                tier = key
        if not line.startswith("|"):
            continue
        m = _MD_ROW.match(line)
        if not m:
            if _MD_SEP.match(line):
                continue
            # a header row: it names the columns, Description among them
            header = _md_cells(line)
            assert "Description" in header, \
                f"demo table header without a Description column: {header}"
            desc_col = header.index("Description")
            continue
        slug = m.group(1).removeprefix("demos/").split("/")[0]
        assert tier is not None, f"demo row before any tier marker: {line!r}"
        assert desc_col is not None, f"demo row before any table header: {line!r}"
        cells = _md_cells(line)
        assert len(cells) > desc_col, f"demo row has no description cell: {line!r}"
        assert cells[desc_col], f"demo row without a description: {line!r}"
        roster[slug] = tier
    return roster


def _html_roster(text: str) -> dict[str, str]:
    """slug -> tier from the site's demos section.

    Each table declares its columns in a `<thead>`; the description is read
    at the index of the `<th>Description</th>` cell, so dropping the column
    fails here rather than sliding the check onto a neighbouring cell.
    """
    idx = text.find('id="demos"')
    assert idx != -1, "index.html lost its id=\"demos\" section"
    end = text.find("</section>", idx)
    assert end != -1, "index.html's demos section is unterminated"
    section = text[idx:end]
    markers = []
    for key, title in TIERS.items():
        m = re.search(rf"<b>{re.escape(title)}</b>", section)
        assert m, f"site demos section lost its '{title}' marker"
        markers.append((m.start(), key))
    markers.sort()
    roster: dict[str, str] = {}
    for table in re.finditer(r"<table[^>]*>.*?</table>", section, re.S):
        head = re.search(r"<thead>.*?</thead>", table.group(0), re.S)
        assert head, f"demos table without a <thead>: {table.group(0)[:80]!r}"
        header = [
            re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<th[^>]*>(.*?)</th>", head.group(0), re.S)
        ]
        assert "Description" in header, \
            f"demos table header without a Description column: {header}"
        desc_col = header.index("Description")
        for row in re.finditer(r"<tr>.*?</tr>", table.group(0), re.S):
            link = re.search(r"tree/main/demos/([A-Za-z0-9-]+)", row.group(0))
            if not link:
                continue
            at = table.start() + row.start()
            tier = [key for pos, key in markers if at > pos][-1]
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(0), re.S)
            assert len(cells) > desc_col, \
                f"demo row has no description cell: {row.group(0)!r}"
            assert cells[desc_col].strip(), \
                f"demo row without a description: {row.group(0)!r}"
            roster[link.group(1)] = tier
    return roster


def test_demo_roster_matches_across_readme_site_and_demos_readme():
    canonical = _md_roster(DEMOS_README.read_text())
    readme = _md_roster(README.read_text(), section="## Demos")
    site = _html_roster(INDEX.read_text())
    assert readme == canonical, \
        "README's demos section disagrees with demos/README.md"
    assert site == canonical, \
        "index.html's demos section disagrees with demos/README.md"


def test_no_status_column_or_dogfood_framing():
    """The demos are finished artefacts, not runs being tracked."""
    for path in (DEMOS_README, README, INDEX):
        text = path.read_text()
        if path is README:
            # the repo's own release-status heading is not a demo status
            start, end = text.find("## Demos"), text.find("## Sharing")
            assert start != -1 and end != -1, \
                "README.md lost its '## Demos' or '## Sharing' heading — " \
                "retarget the scoping this guard reads"
            text = text[start:end]
        assert not _RETIRED.search(text), \
            f"{path} still carries demo status / dogfood framing"


GRAPHICS_POLICY = Path("docs/graphics-and-sprites.md")


def test_graphics_policy_has_evidence_script_shape():
    """Two demos have now written the same evidence protocol from scratch,
    each rediscovering the same rules the hard way. It is repo policy, so it
    lives in the policy doc rather than travelling with the skill."""
    text = GRAPHICS_POLICY.read_text()
    section = text[text.index("## 5."):text.index("## 6.")]
    assert "The shape of an evidence script" in section
    assert "key hold" in section and "--at" in section
    assert "does not resume" in section, \
        "the wait-after-until rule is the one that costs a debugging pass"
    assert "c64 call" in section
    for demo in ("invaders", "ms-muncher"):
        script = DEMOS_DIR / demo / "tools" / "evidence.sh"
        assert script.exists(), f"{script} is the cited worked example"
        body = script.read_text()
        assert re.search(r"until \w+", body), \
            f"{script} no longer parks on a frame anchor before capturing"
        assert "screen --png" in body


def test_graphics_policy_scopes_raster_work_by_evidence_not_by_technique():
    """§1 forbade raster-chasing outright while `demos/la-galaxia` shipped a
    raster-IRQ multiplexer and a `$D016` split, both verified under
    `--warp --headless`. The line the policy actually draws is whether a
    failing implementation produces a failing number."""
    section = GRAPHICS_POLICY.read_text().split("## 1. Scope")[1].split("## 2.")[0]
    section = " ".join(section.split())
    assert "out of scope for automated demos" not in section, \
        "the blanket prohibition is still there"
    assert "counters a test can assert on" in section, \
        "the policy never states the condition that puts these effects in scope"
    assert "demos/la-galaxia" in section, "the worked example is unnamed"
    assert "only evidence is a photograph" in section, \
        "the policy no longer says what stays out of scope"
    # The named counters have to be real exports the spec really asserts, or
    # the worked example is a story.
    exported = (DEMOS_DIR / "la-galaxia" / "vars.s").read_text()
    spec = (DEMOS_DIR / "la-galaxia" / "test.yaml").read_text()
    for name in ("mux_overflow", "tick_overrun"):
        assert name in section, f"the policy cites no {name}"
        assert re.search(rf"^\s*\.export .*\b{name}\b", exported, re.M), \
            f"la-galaxia does not export {name}"
        assert f'mem: "{name}"' in spec, f"test.yaml never asserts {name}"


def test_graphics_policy_requires_program_side_high_water_marks():
    """A per-frame budget sampled by the harness reads whatever the sampled
    frame happened to cost: la-galaxia's redraw counter read 4 against a
    ceiling of 64 while the program's own mark read 88."""
    section = GRAPHICS_POLICY.read_text().split("## 4. Testing policy")[1] \
        .split("## 5.")[0]
    section = " ".join(section.split())
    assert "per-frame budget is measured by the program" in section
    assert "tick_endline" in section, "the existing worked mark is unnamed"
    assert "**88**" in section and "**4**" in section, \
        "the two numbers are the whole argument"
    assert "Scope it to a window" in section, \
        "a lifetime mark carries the frames the ceiling exempts"
    assert "outside a stage transition" in section, \
        "the policy never says WHY the window matters (the ceiling's carve-out)"
    evidence = DEMOS_DIR / "la-galaxia" / "evidence" / "mux.txt"
    assert str(evidence.as_posix()) in GRAPHICS_POLICY.read_text(), \
        "the worked capture is not cited"
    assert "cells_drawn_peak=88" in evidence.read_text(), \
        "the cited capture no longer carries the figure the policy quotes"


def test_every_demo_directory_is_listed():
    dirs = {p.name for p in DEMOS_DIR.iterdir() if p.is_dir()}
    listed = set(_md_roster(DEMOS_README.read_text()))
    assert listed == dirs, \
        f"demos/README.md lists {sorted(listed)}; demos/ holds {sorted(dirs)}"
