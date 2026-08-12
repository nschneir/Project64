"""The demo roster is published in three places: the README's demos section,
demos/README.md, and the site's demos section (index.html). Nothing generates
one from another — GitHub renders the markdown as-is and the site is
hand-authored — so this is the guard that keeps the three surfaces telling
the same story: same demos, same tiers, a description on every row, and no
demo directory left unlisted anywhere.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_every_audio_evidence_script_captures_strictly():
    """`docs/cli.md` names these scripts as the callers `c64 audio capture
    --strict` exists for, and an evidence run reads its success from an exit
    code. All ten capture calls pass `--ref` today, and for nine of them the
    flag is a second line of defence: those scores list sounding notes, so a
    silent window already diffs each scored entry as "heard nothing", FAILs and
    exits 1 without it. The tenth is why this pin is per capture call rather
    than per script. ms-muncher's `play` score is `voices: {1: []}` with voices
    2 and 3 deliberately unscored ("read off the piano roll instead"), and
    `diff_score` compares only the voices a score lists while reading an empty
    list as "this voice should be silent" — so a silent `play` window diffs
    clean, silence is not an anomaly (`find_anomalies`: "a voice that never
    sounds is not one of them"), and `_silence_failure` returns None when
    nothing sounded. That is a PASS at exit 0, and `--strict` is the only thing
    standing in front of it. For the other nine the flag also covers the day
    their scores stop holding — one regenerated to nothing, or a window that
    loses its `--ref`."""
    for demo in ("la-galaxia", "ms-muncher"):
        script = DEMOS_DIR / demo / "tools" / "audio-evidence.sh"
        # Logical lines, not physical ones: a capture whose flags moved onto a
        # backslash continuation would otherwise fail this pin while being
        # perfectly strict.
        body = script.read_text().replace("\\\n", " ")
        calls = [line for line in body.splitlines()
                 if "audio capture" in line and not line.lstrip().startswith("#")]
        assert calls, f"{script} no longer captures"
        for line in calls:
            assert "--strict" in line, \
                f"{script} captures without --strict: {line.strip()}"


# --- the nine sounding scores and the one silent one ----------------------

# The demos that ship an audio evidence run, found rather than listed: a third
# one would join this pin the day it lands a script, not the day someone
# remembers to add it here.
AUDIO_EVIDENCE = sorted(DEMOS_DIR.glob("*/tools/audio-evidence.sh"))

_ARGV_END = "--- end of call ---"

# Records its argv and does nothing else. What is being read out of an
# evidence script is the command line it builds, not what the tools do with it.
_ARGV_STUB = f"""#!/bin/sh
for arg in "$@"; do printf '%s\\n' "$arg" >>"$C64_ARGV_LOG"; done
printf '%s\\n' '{_ARGV_END}' >>"$C64_ARGV_LOG"
"""

MS_MUNCHER_PLAY = "demos/ms-muncher/evidence/audio/play.score.yaml"

_THREE_SITES = (
    "Nine scored captures that sound and one that does not is load-bearing prose "
    "in three places, and a score that gains or loses its last sounding note has "
    "to change all three: this file's "
    "test_every_audio_evidence_script_captures_strictly docstring, "
    "demos/ms-muncher/tools/audio-evidence.sh's cap() comment, and CHANGELOG.md's "
    "[Unreleased] --strict paragraph."
)


def _audio_capture_calls(script: Path, sandbox: Path) -> list[list[str]]:
    """Every `c64 audio capture` argv an evidence script builds.

    The script is *run*, in a throwaway tree where `.venv/bin/c64` and `python3`
    are argv-recording stubs, rather than read. The two scripts reach `--ref`
    differently — la-galaxia passes each score to its `cap` helper as an
    argument, ms-muncher derives one from the capture name and only on the
    branch where that file exists — and three of ms-muncher's five captures
    come out of a `for` loop. Recovering those paths from the text would be a
    small shell interpreter, and it would quietly stop covering whatever shape
    the next capture is written in.
    """
    demo = script.parent.parent.name
    scores = DEMOS_DIR / demo / "evidence" / "audio"
    tools, audio = sandbox / script.parent, sandbox / scores
    tools.mkdir(parents=True)
    audio.mkdir(parents=True)
    shutil.copy(script, tools / script.name)
    # ms-muncher's helper passes --ref only for a capture that has a committed
    # score beside it, so the scores have to be here for that branch to be taken.
    for score in sorted(scores.glob("*.score.yaml")):
        shutil.copy(score, audio / score.name)
    log = sandbox / "argv.log"
    log.touch()
    stubs = sandbox / "stub"
    # `python3` too, not just the CLI: la-galaxia regenerates two of its scores
    # from genmusic.py before it captures anything, and `set -e` would take the
    # run down at that line.
    for exe in (sandbox / ".venv" / "bin" / "c64", stubs / "python3"):
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text(_ARGV_STUB)
        exe.chmod(0o755)
    env = dict(os.environ, C64_ARGV_LOG=str(log),
               PATH=f"{stubs}{os.pathsep}{os.environ['PATH']}")
    run = subprocess.run(["sh", str(tools / script.name)], env=env,
                         capture_output=True, text=True)
    assert run.returncode == 0, (
        f"{script} does not run against stubbed tools (exit {run.returncode}), so "
        f"the captures it makes cannot be read off it: {run.stderr.strip()}")
    calls = [c.splitlines() for c in log.read_text().split(_ARGV_END + "\n")]
    return [c for c in calls if c[:2] == ["audio", "capture"]]


def _refs(call: list[str]) -> list[str]:
    """The reference scores of one capture argv, in either spelling of the flag."""
    found = []
    for index, arg in enumerate(call):
        if arg.startswith("--ref="):
            found.append(arg.split("=", 1)[1])
        elif arg == "--ref" and index + 1 < len(call):
            found.append(call[index + 1])
    return found


def test_exactly_one_captured_audio_score_lists_no_sounding_note(tmp_path):
    """The pin under the docstring above, which nothing but prose held. That
    docstring, ms-muncher's `cap()` comment and the CHANGELOG all rest on the
    same split — ten scored captures, nine of whose scores list sounding notes
    and one, ms-muncher's `play`, that lists none — and the same branch got the
    claim wrong twice running. Adding a note to `play.score.yaml`, or emptying
    one of the other nine, silently falsifies all three sentences.

    "Sounding" and not "listed" is the property counted, and it is deliberately
    the wider of the two rather than a claim about what `diff_score` lets
    through. What really does diff a silent window clean is an empty voice list
    — a silent voice transcribes to one long rest, which
    `_drop_unscored_leading_rest` drops where the score claims nothing — or a
    single rest entry that omits `frames` or names the whole window. Two or more
    rest entries FAIL it, one "expected rest, heard nothing (log ended)" apiece.
    So a rests-only score is flagged here because it claims nothing audible, not
    because it would PASS; counting this way over-flags that shape and cannot
    miss one that really does PASS at exit 0.

    The scores come out of the scripts rather than a list here, so an eleventh
    capture is in scope the moment it is written.
    """
    from c64lib.sid_analysis import REST, load_score

    refs: list[str] = []
    for script in AUDIO_EVIDENCE:
        for call in _audio_capture_calls(script, tmp_path / script.parent.parent.name):
            found = _refs(call)
            assert len(found) == 1, (
                f"{script} makes a capture with {len(found)} --ref scores: "
                f"{' '.join(call)}\n{_THREE_SITES}")
            refs.extend(found)
    assert len(refs) == 10, (
        f"the evidence scripts now make {len(refs)} scored captures, not ten: "
        f"{refs}\n{_THREE_SITES}")

    sounding = {}
    for ref in refs:
        path = Path(ref)
        assert path.exists(), f"a capture passes --ref {ref}, which is not committed"
        entries = [entry for _voice, voiced in load_score(path) for entry in voiced]
        missing = [entry for entry in entries if "note" not in entry]
        assert not missing, f"{ref} has entries with no 'note': {missing}"
        sounding[ref] = sum(1 for e in entries if str(e["note"]).strip() != REST)

    silent = sorted(ref for ref, notes in sounding.items() if not notes)
    assert silent == [MS_MUNCHER_PLAY], (
        f"the scores with no sounding note are {silent}, not [{MS_MUNCHER_PLAY!r}]. "
        f"{_THREE_SITES} A score that lists no sounding note claims nothing audible, "
        "and in the shape ms-muncher's `play` has — an empty voice list — it diffs a "
        "silent window clean and PASSes at exit 0, leaving `--strict` that capture's "
        f"only guard. Sounding notes per score: {sounding}")


def test_every_demo_directory_is_listed():
    dirs = {p.name for p in DEMOS_DIR.iterdir() if p.is_dir()}
    listed = set(_md_roster(DEMOS_README.read_text()))
    assert listed == dirs, \
        f"demos/README.md lists {sorted(listed)}; demos/ holds {sorted(dirs)}"


# --- generated art stays generated ----------------------------------------

LG = DEMOS_DIR / "la-galaxia"


def _inc_bytes(path: Path) -> list[int]:
    """The `%01010101` payload of a generated `.inc`, labels and comments off."""
    text = re.sub(r";[^\n]*", "", path.read_text())
    return [int(b, 2) for b in re.findall(r"%([01]{8})", text)]


def _genart_sprite_flags() -> tuple[bool, str]:
    """(file-level multicolor, background char) read out of `genart.sh`.

    Mirroring the script's flags here instead would make this test model an
    invocation it does not read: a `--hires` or a different `--background`
    added there would leave the test re-encoding the sheet its own way and
    then blaming the include for the difference.
    """
    script = (LG / "tools" / "genart.sh").read_text()
    # Command lines only: the header comment discusses `sprite encode` too.
    calls = [ln for ln in script.splitlines()
             if "sprite encode" in ln and not ln.lstrip().startswith("#")]
    assert len(calls) == 1, \
        f"expected one sprite encode invocation in genart.sh, found {calls}"
    background = re.search(r"--background (\S+)", calls[0])
    assert background, "genart.sh's sprite encode passes no --background"
    return "--hires" not in calls[0], background.group(1)


def test_la_galaxia_sprites_inc_is_its_sheet_re_encoded():
    """`sprites.inc` is generated from `tools/sprites.txt`, and nothing pinned
    that until now: the committed include had drifted a whole block out of
    date — block 5 held a *hires* sixth fighter where `sprites.s`'s manifest
    (`SPR_CAPTIVE = SPRBLK + 5`, "multicolour from here down") and the sheet
    both say the multicolour captive belongs, so the game drew the wrong art
    through the multicolour bit. A generated file with no regeneration test is
    a file that can disagree with its source forever; this is that test."""
    from c64lib.sprites import encode_sheet_blocks

    sheet = (LG / "tools" / "sprites.txt").read_text()
    multicolor, background = _genart_sprite_flags()
    blocks = encode_sheet_blocks(sheet, multicolor=multicolor,
                                 background=background)
    expected = [b for block in blocks for b in block.data]
    got = _inc_bytes(LG / "sprites.inc")
    assert got == expected, (
        "demos/la-galaxia/sprites.inc no longer matches tools/sprites.txt — "
        "re-run `sh demos/la-galaxia/tools/genart.sh` (and rebuild "
        "la-galaxia.prg / la-galaxia.d64, which carry the art)"
    )
    # The drift was a *mode* drift as much as a byte drift, and the split is
    # what sprites.s promises: five hires shapes, then multicolour all the way
    # down, because `installsprites` sets $D01C once and never per band.
    manifest = (LG / "sprites.s").read_text()
    assert "SPR_CAPTIVE = SPRBLK + 5" in manifest, \
        "sprites.s no longer puts the captive at block 5"
    assert [b.multicolor for b in blocks] == [False] * 5 + [True] * 16, \
        "the sheet's hires/multicolour split moved away from sprites.s's"
    # Every block must spell its own mode. `genart.sh` passes no --hires, so
    # the file-level default is whatever the CLI's is; a bare `name:` header
    # would take that default, and this test's model of the invocation would
    # start deciding the answer instead of checking it.
    headers = re.findall(r"^([A-Za-z_]\w*):(\w*)\s*$", sheet, re.M)
    assert len(headers) == len(blocks), \
        f"{len(blocks)} blocks but {len(headers)} `name:mode` headers"
    bare = [name for name, mode in headers if not mode]
    assert not bare, \
        f"blocks {bare} name no mode, so they inherit the sheet default — " \
        "spell hires/multicolor on every block, the way sprites.s does"


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_la_galaxia_prg_is_a_build_of_the_committed_sources(tmp_path):
    """The include above is pinned to its sheet; this pins the shipped binary
    to the sources that carry it. `la-galaxia.prg` is tracked, and a stale one
    contradicts every `.s` and `.inc` beside it — the same "generated file
    with no regeneration test" failure, one level down. It costs one ca65 and
    one ld65 pass over a single translation unit (~0.2 s) and is
    byte-reproducible. The `.d64` is deliberately not pinned: packaging shells
    out to c1541 and costs seconds where this pass costs a fraction of one, so
    nothing here checks that the shipped image carries the `.prg` this test
    just rebuilt — re-package by hand after any rebuild.

    The areas and the load address both come from data — `test.yaml` and the
    machine profile — so the spec stays the one place the program's link
    layout is written down and no line here restates it."""
    import yaml

    from c64lib.build import build_asm
    from c64lib.machines import get_profile
    from c64lib.ops import parse_areas

    spec = yaml.safe_load((LG / "test.yaml").read_text())
    areas = spec.get("areas")
    assert areas, ("test.yaml no longer declares any `areas:` — la-galaxia "
                   "cannot link without one")
    basic_start = get_profile("c64").basic_start
    built = build_asm(LG / "la-galaxia.s", out_prg=tmp_path / "la-galaxia.prg",
                      basic_start=basic_start,
                      areas=parse_areas(areas, basic_start)).prg
    flags = " ".join(f"--area '{a}'" for a in areas)
    assert built.read_bytes() == (LG / "la-galaxia.prg").read_bytes(), (
        "demos/la-galaxia/la-galaxia.prg is not a build of the committed "
        f"sources — re-run `c64 build demos/la-galaxia/la-galaxia.s {flags}` "
        "(and `c64 package` the .d64, which nothing pins to it)"
    )
