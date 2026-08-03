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
# The tables say what each demo *is*; they carry no status of any kind.
_RETIRED = re.compile(r"✅|🔲|dogfood", re.I)


def _md_roster(text: str, section: str | None = None) -> dict[str, str]:
    """slug -> tier from a markdown surface.

    Rows are table lines whose first link points into demos/; the tier is
    whichever tier marker (a `## ` heading or a bold lead-in) came last.
    """
    if section is not None:
        idx = text.index(section)
        end = text.find("\n## ", idx + 1)
        text = text[idx:end if end != -1 else len(text)]
    roster: dict[str, str] = {}
    tier = None
    for line in text.splitlines():
        for key, title in TIERS.items():
            if line.startswith(("#", "**")) and title in line:
                tier = key
        m = _MD_ROW.match(line)
        if not m:
            continue
        slug = m.group(1).removeprefix("demos/").split("/")[0]
        assert tier is not None, f"demo row before any tier marker: {line!r}"
        description = line.strip().strip("|").split("|")[-1].strip()
        assert description, f"demo row without a description: {line!r}"
        roster[slug] = tier
    return roster


def _html_roster(text: str) -> dict[str, str]:
    """slug -> tier from the site's demos section."""
    idx = text.index('id="demos"')
    section = text[idx:text.index("</section>", idx)]
    markers = []
    for key, title in TIERS.items():
        m = re.search(rf"<b>{re.escape(title)}</b>", section)
        assert m, f"site demos section lost its '{title}' marker"
        markers.append((m.start(), key))
    markers.sort()
    roster: dict[str, str] = {}
    for row in re.finditer(r"<tr>.*?</tr>", section, re.S):
        link = re.search(r"tree/main/demos/([A-Za-z0-9-]+)", row.group(0))
        if not link:
            continue
        tier = [key for pos, key in markers if row.start() > pos][-1]
        # cells run demo, language, description — the leading number column
        # in the test-demos table shifts them all right by one
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(0), re.S)
        at = next(i for i, c in enumerate(cells) if "tree/main/demos/" in c)
        assert len(cells) > at + 2, f"demo row has no description cell: {row.group(0)!r}"
        assert cells[at + 2].strip(), f"demo row without a description: {row.group(0)!r}"
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
            text = text[text.index("## Demos"):text.index("## Sharing")]
        assert not _RETIRED.search(text), \
            f"{path} still carries demo status / dogfood framing"


def test_every_demo_directory_is_listed():
    dirs = {p.name for p in DEMOS_DIR.iterdir() if p.is_dir()}
    listed = set(_md_roster(DEMOS_README.read_text()))
    assert listed == dirs, \
        f"demos/README.md lists {sorted(listed)}; demos/ holds {sorted(dirs)}"
