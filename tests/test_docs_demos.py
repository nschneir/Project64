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
            # `_` is in the class because a demo directory may hold one
            # (`amiga_ball`); without it the slug read here is a truncation
            # that mismatches the markdown surfaces for a reason nothing names.
            link = re.search(r"tree/main/demos/([A-Za-z0-9_-]+)", row.group(0))
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
    canonical = _md_roster(DEMOS_README.read_text(encoding="utf-8"))
    readme = _md_roster(README.read_text(encoding="utf-8"), section="## Demos")
    site = _html_roster(INDEX.read_text(encoding="utf-8"))
    assert readme == canonical, \
        "README's demos section disagrees with demos/README.md"
    assert site == canonical, \
        "index.html's demos section disagrees with demos/README.md"


def test_no_status_column_or_dogfood_framing():
    """The demos are finished artefacts, not runs being tracked."""
    for path in (DEMOS_README, README, INDEX):
        text = path.read_text(encoding="utf-8")
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
    text = GRAPHICS_POLICY.read_text(encoding="utf-8")
    section = text[text.index("## 5."):text.index("## 6.")]
    assert "The shape of an evidence script" in section
    assert "key hold" in section and "--at" in section
    assert "does not resume" in section, \
        "the wait-after-until rule is the one that costs a debugging pass"
    assert "c64 call" in section
    for demo in ("invaders", "ms-muncher"):
        script = DEMOS_DIR / demo / "tools" / "evidence.sh"
        assert script.exists(), f"{script} is the cited worked example"
        body = script.read_text(encoding="utf-8")
        assert re.search(r"until \w+", body), \
            f"{script} no longer parks on a frame anchor before capturing"
        assert "screen --png" in body


def test_graphics_policy_scopes_raster_work_by_evidence_not_by_technique():
    """§1 forbade raster-chasing outright while `demos/la-galaxia` shipped a
    raster-IRQ multiplexer and a `$D016` split, both verified under
    `--warp --headless`. The line the policy actually draws is whether a
    failing implementation produces a failing number."""
    section = GRAPHICS_POLICY.read_text(encoding="utf-8").split("## 1. Scope")[1].split("## 2.")[0]
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
    exported = (DEMOS_DIR / "la-galaxia" / "vars.s").read_text(encoding="utf-8")
    spec = (DEMOS_DIR / "la-galaxia" / "test.yaml").read_text(encoding="utf-8")
    for name in ("mux_overflow", "tick_overrun"):
        assert name in section, f"the policy cites no {name}"
        assert re.search(rf"^\s*\.export .*\b{name}\b", exported, re.M), \
            f"la-galaxia does not export {name}"
        assert f'mem: "{name}"' in spec, f"test.yaml never asserts {name}"


def test_graphics_policy_requires_program_side_high_water_marks():
    """A per-frame budget sampled by the harness reads whatever the sampled
    frame happened to cost: la-galaxia's redraw counter read 4 against a
    ceiling of 64 while the program's own mark read 88."""
    section = GRAPHICS_POLICY.read_text(encoding="utf-8").split("## 4. Testing policy")[1] \
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
    assert str(evidence.as_posix()) in GRAPHICS_POLICY.read_text(encoding="utf-8"), \
        "the worked capture is not cited"
    assert "cells_drawn_peak=88" in evidence.read_text(encoding="utf-8"), \
        "the cited capture no longer carries the figure the policy quotes"


def test_every_audio_evidence_script_captures_strictly():
    """`docs/cli.md` names these scripts as the callers `c64 audio capture
    --strict` exists for, and an evidence run reads its success from an exit
    code. All twelve capture calls pass `--ref` today, and for eleven of them
    the flag is a second line of defence: those scores list sounding notes, so a
    silent window already diffs each scored entry as "heard nothing", FAILs and
    exits 1 without it. The twelfth is why this pin is per capture call rather
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
        body = script.read_text(encoding="utf-8").replace("\\\n", " ")
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

_BOTH_SITES = (
    "Eleven scored captures that sound and one that does not is load-bearing "
    "prose in two places, and a score that gains or loses its last sounding note "
    "has to change both: this file's "
    "test_every_audio_evidence_script_captures_strictly docstring and "
    "demos/ms-muncher/tools/audio-evidence.sh's cap() comment."
)

#: CHANGELOG.md was a third site until 2026-08-13. It is not one now, by
#: maintainer ruling: a changelog says what was true when its entry was
#: written, so a guard requiring it to track the tree forever makes it
#: unrewritable — this one blocked a rewrite that was condensing prose, not
#: changing a fact. Anchoring a live claim to a dated record was the error.

#: One sentence out of each site `_BOTH_SITES` sends an editor to, so the
#: message cannot quietly become a lie about where the claim lives. The
#: docstring is read off the function rather than off this file: an anchor
#: matched against the file that holds the anchor is satisfied by itself.
_SITE_ANCHORS = [
    ("demos/ms-muncher/tools/audio-evidence.sh", "the cap() comment",
     "The other four scores list notes"),
]


def _prose(text: str) -> str:
    """Wrapped text as one line, with comment markers dropped — the sentences
    below are wrapped across lines and two of them are inside `#` comments."""
    return " ".join(text.replace("#", " ").split())


def test_the_sites_the_failure_message_names_still_say_it():
    """`_BOTH_SITES` tells a future editor which sentences to update.
    Nothing made those sentences exist, so the guidance could go stale while
    every assert it is attached to still passed — a failure message that sends
    someone to prose that has already moved is worse than none."""
    doc = _prose(test_every_audio_evidence_script_captures_strictly.__doc__ or "")
    assert "for eleven of them the flag is a second line of defence" in doc, \
        (f"this file's test_every_audio_evidence_script_captures_strictly "
         f"docstring no longer states the eleven/one split.\n{_BOTH_SITES}")
    for path, where, sentence in _SITE_ANCHORS:
        assert sentence in _prose(Path(path).read_text(encoding="utf-8")), \
            f"{path}: {where} no longer says {sentence!r}.\n{_BOTH_SITES}"


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
    # run down at that line. And `c64` twice over, at both spellings a script
    # could reach it by: `.venv/bin/c64` is how both scripts invoke it today
    # (after their `cd` to the repo root), `stub/c64` covers a bare `c64` off
    # PATH. Neither placement covers the other.
    for exe in (sandbox / ".venv" / "bin" / "c64", stubs / "c64", stubs / "python3"):
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text(_ARGV_STUB, encoding="utf-8")
        exe.chmod(0o755)
    env = dict(os.environ, C64_ARGV_LOG=str(log),
               PATH=f"{stubs}{os.pathsep}{os.environ['PATH']}")
    # `cwd` is the load-bearing one, not a tidiness flag. Both scripts open with
    # `cd "$(dirname "$0")/../../.."`, so today `.venv/bin/c64` lands on the
    # stub whatever this process's cwd is — but a script that ever drops that
    # line resolves `.venv/bin/c64` against the inherited cwd, which is the real
    # checkout with the real CLI in it, and a unit test boots a headless VICE.
    # `timeout` and a closed stdin for the same reason from the other side: a
    # script that blocks on input or on a tool that never returns must fail this
    # test, not hang the suite.
    run = subprocess.run(["sh", str(tools / script.name)], env=env, cwd=sandbox,
                         capture_output=True, text=True,
                         timeout=120, stdin=subprocess.DEVNULL)
    assert run.returncode == 0, (
        f"{script} does not run against stubbed tools (exit {run.returncode}), so "
        f"the captures it makes cannot be read off it: {run.stderr.strip()}")
    calls = [c.splitlines() for c in log.read_text(encoding="utf-8").split(_ARGV_END + "\n")]
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
    docstring and ms-muncher's `cap()` comment both rest on the same split —
    twelve scored captures, eleven of whose scores list sounding notes and one,
    ms-muncher's `play`, that lists none — and the same branch got the claim
    wrong twice running. Adding a note to `play.score.yaml`, or emptying one of
    the other eleven, silently falsifies both sentences.

    "Sounding" and not "listed" is the property counted, and it is deliberately
    the wider of the two rather than a claim about what `diff_score` lets
    through. What really does diff a silent window clean is an empty voice list
    — a silent voice transcribes to one long rest, which
    `_drop_unscored_leading_rest` drops where the score claims nothing — or a
    single rest entry that omits `frames` or names the whole window. Two or more
    rest entries FAIL it: a silent window transcribes to ONE long rest, so every
    entry past the first diffs as "expected rest, heard nothing (log ended)" —
    N entries, N−1 messages (measured: 2 → 1, 10 → 9).
    So a rests-only score is flagged here because it claims nothing audible, not
    because it would PASS; counting this way over-flags that shape and cannot
    miss one that really does PASS at exit 0.

    The scores come out of the scripts rather than a list here, so a thirteenth
    capture is in scope the moment it is written.
    """
    from c64lib.sid_analysis import REST, load_score

    refs: list[str] = []
    for script in AUDIO_EVIDENCE:
        for call in _audio_capture_calls(script, tmp_path / script.parent.parent.name):
            found = _refs(call)
            assert len(found) == 1, (
                f"{script} makes a capture with {len(found)} --ref scores: "
                f"{' '.join(call)}\n{_BOTH_SITES}")
            refs.extend(found)
    assert len(refs) == 12, (
        f"the evidence scripts now make {len(refs)} scored captures, not twelve: "
        f"{refs}\n{_BOTH_SITES}")

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
        f"{_BOTH_SITES} A score that lists no sounding note claims nothing audible, "
        "and in the shape ms-muncher's `play` has — an empty voice list — it diffs a "
        "silent window clean and PASSes at exit 0, leaving `--strict` that capture's "
        f"only guard. Sounding notes per score: {sounding}")


def test_every_demo_directory_is_listed():
    dirs = {p.name for p in DEMOS_DIR.iterdir() if p.is_dir()}
    listed = set(_md_roster(DEMOS_README.read_text(encoding="utf-8")))
    assert listed == dirs, \
        f"demos/README.md lists {sorted(listed)}; demos/ holds {sorted(dirs)}"


# --- generated art stays generated ----------------------------------------

LG = DEMOS_DIR / "la-galaxia"


def _inc_bytes(path: Path) -> list[int]:
    """The `%01010101` payload of a generated `.inc`, labels and comments off."""
    text = re.sub(r";[^\n]*", "", path.read_text(encoding="utf-8"))
    return [int(b, 2) for b in re.findall(r"%([01]{8})", text)]


def _genart_sprite_flags() -> tuple[bool, str]:
    """(file-level multicolor, background char) read out of `genart.sh`.

    Mirroring the script's flags here instead would make this test model an
    invocation it does not read: a `--hires` or a different `--background`
    added there would leave the test re-encoding the sheet its own way and
    then blaming the include for the difference.
    """
    script = (LG / "tools" / "genart.sh").read_text(encoding="utf-8")
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

    sheet = (LG / "tools" / "sprites.txt").read_text(encoding="utf-8")
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
    manifest = (LG / "sprites.s").read_text(encoding="utf-8")
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


def _pinnable_demos() -> list[str]:
    """Every demo directory shipping a tracked `.prg` built from a `.s` this
    repo can rebuild — i.e. every one the next test can pin.

    Derived, not listed. A demo that gains a committed program joins the guard
    by existing, which is the whole point: the failure this catches is a
    *new* demo shipping a binary nobody rebuilds, and a hand-maintained list
    would have to be updated by the same commit that introduces the risk.
    """
    import yaml

    out = []
    for demo in sorted(p.name for p in DEMOS_DIR.iterdir() if p.is_dir()):
        spec_path = DEMOS_DIR / demo / "test.yaml"
        if not spec_path.exists() or not (DEMOS_DIR / demo / f"{demo}.prg").exists():
            continue
        program = (yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}).get("program")
        if program and program.endswith(".s"):
            out.append(demo)
    return out


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
@pytest.mark.parametrize("demo", _pinnable_demos())
def test_demo_prg_is_a_build_of_the_committed_sources(demo, tmp_path):
    """The include above is pinned to its sheet; this pins each shipped binary
    to the sources that carry it. A demo's `.prg` is tracked (`.gitignore`
    carves `!demos/*/*.prg` out so a demo can ship the artifact its own prompt
    builds), and a stale one contradicts every `.s` and `.inc` beside it — the
    same "generated file with no regeneration test" failure, one level down.
    It costs one ca65 and one ld65 pass per demo (~0.2 s) and is
    byte-reproducible.

    Parameterised over every demo rather than written once for la-galaxia,
    because the drift is not hypothetical: the amiga_ball dogfood committed a
    `.prg` in its first task and let it sit **five commits** stale — 1,986
    differing bytes against its own sources — and nothing failed, because the
    only guard named a different demo. Four other demos had no guard at all.

    The `.d64` is pinned by the sibling test below, behind `needs_c1541` —
    it shells out to c1541, which this fraction-of-a-second pass must not.

    The areas and the load address both come from data — `test.yaml` and the
    machine profile — so each spec stays the one place its program's link
    layout is written down and no line here restates it."""
    import yaml

    from c64lib.build import build_asm
    from c64lib.machines import get_profile
    from c64lib.ops import parse_areas

    demo_dir = DEMOS_DIR / demo
    spec = yaml.safe_load((demo_dir / "test.yaml").read_text(encoding="utf-8"))
    source = demo_dir / spec["program"]
    areas = spec.get("areas") or []
    basic_start = get_profile(spec.get("machine") or "c64").basic_start
    built = build_asm(source, out_prg=tmp_path / f"{demo}.prg",
                      basic_start=basic_start,
                      areas=parse_areas(areas, basic_start)).prg
    flags = "".join(f" --area '{a}'" for a in areas)
    assert built.read_bytes() == (demo_dir / f"{demo}.prg").read_bytes(), (
        f"demos/{demo}/{demo}.prg is not a build of the committed sources — "
        f"re-run `c64 build {source}{flags}` (and `c64 package` the .d64, "
        "which the needs_c1541 sibling test pins to it)"
    )


@pytest.mark.needs_c1541
@pytest.mark.parametrize("demo", _pinnable_demos())
def test_demo_d64_carries_the_committed_prg(demo):
    """The other half of the pin above, and the residual its docstring used to
    concede: a re-packaged image can drift from a rebuilt program with nothing
    to notice, because `c64 package` and `c64 build` are separate commands run
    by hand. The image's autostart file — the `*` read, which c1541 resolves
    to the first directory entry, exactly what `LOAD"*",8,1` runs — must be
    byte-identical to the committed `.prg` beside it. Behind `needs_c1541`
    (not in this file's default sweep) because it shells out to c1541;
    `pytest -m "needs_c1541 and not vice"` is the subset that runs it."""
    import tempfile

    from c64lib.disk import get_file

    demo_dir = DEMOS_DIR / demo
    image = demo_dir / f"{demo}.d64"
    assert image.exists(), \
        f"{image} is missing while {demo}.prg is committed — package it"
    with tempfile.TemporaryDirectory() as td:
        pulled = get_file(image, "*", Path(td) / "auto.prg")
        assert pulled.read_bytes() == (demo_dir / f"{demo}.prg").read_bytes(), (
            f"demos/{demo}/{demo}.d64's autostart file is not the committed "
            f"{demo}.prg — the image was packaged from a different build; "
            f"re-run `c64 package`"
        )


AUDIT_1812 = Path("demos/1812/AUDIT.md")
#: `rnd`'s two code paths, and the PAL badline DMA steal, in cycles. The A13
#: passage's whole claim is that its inflated readings are these three numbers
#: added, so they are named once here and the guard below does the arithmetic.
_RND_PATHS = (29, 38)
_BADLINE_STEAL = 43


def test_audit_a13_rnd_table_is_its_own_arithmetic():
    """A13's `rnd` figure was a bare `72` that nobody could reproduce, and what
    made it reproducible was not a better number but an *explanation*: 72 is the
    29-cycle path plus one badline's DMA, and whether any arrival is inflated at
    all is set by the raster line the anchor parked on, not by the screen being
    on. The passage proves that with a seven-anchor table.

    A published table with no guard is what this branch exists to fix, so this
    one checks the claim rather than the wording. Every inflated value the table
    admits must be a path plus exactly one steal; the anchors that report no
    inflation must show only the bare paths; and the ordering claim — that a
    stop in the lower border sees none and one inside the display window sees
    several — has to survive too, since the whole point is that the anchor is
    what governs it.
    """
    text = AUDIT_1812.read_text(encoding="utf-8")
    rows = re.findall(
        r"\| `until drawshape --count (\d+)` \| (\d+) \| (\d+) / 96 \| ([\d, ]+?) \|", text)
    assert len(rows) >= 5, \
        f"A13's rnd anchor table is gone or reshaped (found {len(rows)} rows)"

    allowed = set(_RND_PATHS) | {p + _BADLINE_STEAL for p in _RND_PATHS}
    clean, dirty = [], []
    for count, line, inflated, values in rows:
        seen = {int(v) for v in values.split(",")}
        assert seen <= allowed, (
            f"--count {count} reports {sorted(seen - allowed)}, which is neither "
            f"a path {_RND_PATHS} nor a path plus one {_BADLINE_STEAL}-cycle steal")
        n = int(inflated)
        assert (n == 0) == (seen <= set(_RND_PATHS)), (
            f"--count {count} says {n}/96 inflated but lists {sorted(seen)} — the "
            "count and the values disagree")
        (clean if n == 0 else dirty).append((int(line), n))

    assert clean and dirty, \
        "the table no longer shows both a clean anchor and an inflated one, which is the claim"
    # Badlines live in raster $30-$F7. The clean anchors are the ones parked
    # outside it; if that ever inverts, the table is no longer evidence for
    # "the anchor governs it" and is just a list of numbers.
    assert max(n for _, n in clean) < min(n for _, n in dirty), \
        "an anchor reported as clean now shows more inflation than one reported as dirty"
    assert any(not (0x30 <= line <= 0xF7) for line, _ in clean), \
        "no clean anchor is parked outside the badline range, so the table does not explain itself"
    assert any(0x30 <= line <= 0xF7 for line, _ in dirty), \
        "no inflated anchor is parked inside the badline range"


# --- the play page's registry, pinned to the tree it serves ----------------

PLAY = Path("play.html")

#: Every `DEMOS` field that names a file this repo serves, and the path each
#: one must have inside its own demo directory. Pinned in full rather than
#: merely resolved: a tile that points at a real file belonging to a
#: *different* demo passes an existence check and then ships the wrong game
#: under the right name — which is what a copied registry entry does.
PLAY_ASSETS = {
    "prg": "{demo}.prg",
    "d64": "{demo}.d64",
}

#: The tile art is the one asset whose *name* is not derivable. Every game has
#: an `evidence/title.png`; 1812 has no title screen to shoot, so its tile is
#: an evidence frame. The rule that survives both is the one that catches the
#: real mistake — the image must live under the demo's own `evidence/`.
PLAY_IMAGE_DIR = "demos/{demo}/evidence/"


def _play_registry() -> list[dict[str, str]]:
    """`play.html`'s `DEMOS` array, one dict of its string fields per entry.

    Read out of the page rather than restated here. That array is the only
    list of what the play page serves, and a copy of it in this file would be
    one more surface to keep in step — the thing this module exists to stop.
    """
    text = PLAY.read_text(encoding="utf-8")
    start = text.index("var DEMOS = [")
    end = text.index("\n  ];", start)
    entries = [
        dict(re.findall(r'(\w+):\s*"((?:[^"\\]|\\.)*)"', obj))
        for obj in re.findall(r"\{(.*?)\n    \}", text[start:end], re.S)
    ]
    assert entries, \
        "play.html's DEMOS array no longer parses — the shape this reads changed"
    return entries


def test_play_page_registry_is_the_runnable_demos_in_the_roster_order():
    """`play.html` publishes its own roster and derives it from nothing:
    `DEMOS` is a hand-written array inside the page. That makes the array a
    fourth copy of a list the three markdown surfaces already share, so it is
    held to the same standard: a new demo, a reordering, or a renamed
    directory should not be able to leave the play page serving the old set.

    What belongs on it is "every demo with a committed program", not a tier.
    The games qualify; so does 1812, which is watched rather than played but
    runs perfectly well in a browser. `fugue` and the numbered teaching demos
    do not, because nothing in the tree builds them into a `.prg` — and that
    is the condition this asserts, so a demo that gains one is a test failure
    rather than an omission nobody notices.
    """
    runnable = [slug for slug in _md_roster(DEMOS_README.read_text(encoding="utf-8"))
                if (DEMOS_DIR / slug / f"{slug}.prg").exists()]
    ids = [entry["id"] for entry in _play_registry()]
    assert ids == runnable, (
        f"play.html's DEMOS roster is {ids} but the demos with a committed "
        f".prg are {runnable} — both lists are maintained by hand and they "
        f"have parted")
    for demo in ids:
        assert (DEMOS_DIR / demo).is_dir(), \
            f"play.html serves {demo!r}, which is not a demo directory"


def test_every_demo_file_play_html_serves_exists_and_is_tracked():
    """Nothing else covers a path in `play.html`. The roster's `.prg`, `.d64`
    and `title.png` live in JavaScript strings, and the `<noscript>` fallback
    repeats the same two downloads per demo as hand-written links; neither is
    reachable from the markdown surfaces the tests above compare. GitHub Pages
    serves the *committed* tree, so a file that is merely present resolves
    perfectly on the author's disk and 404s for every visitor — which is how a
    broken play page ships green.
    """
    registry = _play_registry()
    # path -> what points at it, so a failure names the line to go fix.
    referenced: dict[str, str] = {}

    for entry in registry:
        demo = entry.get("id")
        for field, shape in PLAY_ASSETS.items():
            assert field in entry, f"play.html's {demo!r} entry has no {field}"
            want = f"demos/{demo}/{shape.format(demo=demo)}"
            assert entry[field] == want, (
                f"play.html's {demo!r} tile takes its {field} from "
                f"{entry[field]!r}, not {want!r} — a tile pointing into another "
                f"demo's directory resolves fine and ships the wrong game")
            referenced[entry[field]] = f"DEMOS[{demo}].{field}"

        assert "image" in entry, f"play.html's {demo!r} entry has no image"
        want_dir = PLAY_IMAGE_DIR.format(demo=demo)
        assert entry["image"].startswith(want_dir), (
            f"play.html's {demo!r} tile takes its image from "
            f"{entry['image']!r}, which is not under {want_dir!r} — a tile "
            f"showing another demo's screen resolves fine and misleads")
        referenced[entry["image"]] = f"DEMOS[{demo}].image"

    text = PLAY.read_text(encoding="utf-8")
    fallback = text[text.index("<noscript>"):text.index("</noscript>")]
    links = re.findall(r'href="(demos/[^"]+)"', fallback)
    assert len(links) == 2 * len(registry), (
        f"the <noscript> fallback offers {len(links)} downloads for "
        f"{len(registry)} demos — it is written out by hand, one .prg and one "
        f".d64 per demo, and it is the whole page for a visitor without JS")
    assert set(links) == {entry[f] for entry in registry for f in ("prg", "d64")}, \
        "the <noscript> downloads and the DEMOS registry name different files"
    for href in links:
        referenced.setdefault(href, "the <noscript> fallback")

    missing = {path: where for path, where in referenced.items()
               if not Path(path).is_file()}
    assert not missing, f"play.html points at files that are not there: {missing}"

    # WHY the guard: the claim being made is about what the *published* tree
    # contains, and only git can answer that. Without git there is no weaker
    # version of this assertion worth running — a plain existence check is the
    # one already made above, and it is exactly what cannot catch this.
    if shutil.which("git") is None:
        pytest.skip("git is not on PATH, so tracked-ness cannot be established")
    run = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", *sorted(referenced)],
        capture_output=True, text=True)
    assert run.returncode == 0, (
        "play.html points at files git does not track, so GitHub Pages serves a "
        f"404 for them however well they resolve locally:\n{run.stderr.strip()}")


def _html_descriptions(text: str) -> dict[str, str]:
    """`index.html`'s demo table, slug -> Description cell as plain prose.

    Tags are stripped and the handful of entities the cells actually use are
    decoded, because the same sentence lives in `play.html` as a JavaScript
    string with no markup at all — so the two are only comparable once
    `index.html`'s is reduced to what it says.
    """
    section = text[text.index('id="demos"'):]
    out: dict[str, str] = {}
    for table in re.finditer(r"<table[^>]*>.*?</table>", section, re.S):
        head = re.search(r"<thead>.*?</thead>", table.group(0), re.S)
        assert head, "demos table without a <thead>"
        header = [
            re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<th[^>]*>(.*?)</th>", head.group(0), re.S)
        ]
        if "Description" not in header:
            continue
        desc_col = header.index("Description")
        for row in re.finditer(r"<tr>.*?</tr>", table.group(0), re.S):
            # `_` is in the class because a demo directory may hold one
            # (`amiga_ball`); without it the slug read here is a truncation
            # that mismatches the markdown surfaces for a reason nothing names.
            link = re.search(r"tree/main/demos/([A-Za-z0-9_-]+)", row.group(0))
            if not link:
                continue
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(0), re.S)
            if len(cells) <= desc_col:
                continue
            plain = re.sub(r"<[^>]+>", "", cells[desc_col])
            plain = plain.replace("&mdash;", "—").replace("&amp;", "&")
            out[link.group(1)] = " ".join(plain.split())
    return out


def test_play_page_describes_each_game_the_way_the_landing_page_does():
    """The play page repeats `index.html`'s description for the selected game,
    so the same sentence is now authored twice — once as a table cell, once as
    a JavaScript string. Nothing derives one from the other at build time
    because neither page has a build step, which leaves this test as the only
    thing standing between them and a slow divergence: the landing page
    describing a demo one way and the page you play it on another.
    """
    site = _html_descriptions(INDEX.read_text(encoding="utf-8"))
    for entry in _play_registry():
        demo = entry["id"]
        assert demo in site, \
            f"play.html serves {demo!r}, which index.html's demo table omits"
        assert "description" in entry, (
            f"play.html's {demo!r} entry has no description — the play page "
            "shows one for every game it serves")
        assert entry["description"] == site[demo], (
            f"the description of {demo!r} has drifted between the two pages:\n"
            f"  index.html: {site[demo]!r}\n"
            f"  play.html:  {entry['description']!r}")


#: `$CB` with no hex digit after it, so `$CB00` is not a hit; and the CIA port
#: whose bits are the keyboard matrix rows. Written against the source text
#: rather than a routine name because the five demos do not share one —
#: la-galaxia scans the matrix inside `keydecode`, the others in `keyscan`.
_READS_CB = re.compile(r"\$[cC][bB](?![0-9a-fA-F])")
_READS_MATRIX = re.compile(r"\$[dD][cC]01")


def test_no_demo_takes_its_input_from_the_kernal_alone():
    """The play page boots these programs on MEGA65 open-roms; every
    `test.yaml` proves them under VICE on Commodore's. Nothing else exercises
    the second ROM set, so a demo that depends on a Commodore-only detail is
    green here and broken in the browser — which is not hypothetical: all five
    read the held key from `$CB`, a KERNAL scratch byte open-roms never writes,
    and all five were unplayable on the play page while every spec passed.

    `$CB` itself is allowed, because the CLI drives held keys by poking it and
    the demos keep it as a fallback. What is not allowed is `$CB` as the *only*
    source: a demo that reads it must also read the keyboard matrix off the
    CIA, which is hardware and answers on any ROM.

    This is the narrow guard, not the general one. It catches the dependency
    that has actually bitten twice; it cannot catch a demo that starts calling
    some other KERNAL routine open-roms does not implement. That wider check
    needs the open ROM images reachable from a test run and is still open in
    `docs/todo.md`.
    """
    for demo in _play_registry():
        slug = demo["id"]
        sources = sorted((DEMOS_DIR / slug).glob("*.s"))
        assert sources, f"{slug} has a committed .prg but no .s sources"
        text = "".join(p.read_text(encoding="utf-8") for p in sources)
        if not _READS_CB.search(text):
            continue
        assert _READS_MATRIX.search(text), (
            f"{slug} reads $CB but never reads the keyboard matrix at $DC01, "
            f"so its input depends on a byte the Commodore KERNAL maintains "
            f"and MEGA65 open-roms does not. It will pass c64 test run under "
            f"VICE and take no input on the play page. Scan the CIA and keep "
            f"$CB as the fallback, the way the other demos do.")


def test_graphics_policy_names_the_shell_its_helpers_assume():
    """The §5 helper block is offered as "worth stealing verbatim", and its
    unquoted `$S` relies on word splitting — which zsh does not perform on
    parameter expansions, so pasted into a zsh prompt the session flag
    arrives as one token and the lookup fails with `no session named
    ' mmev'`. Every committed evidence script is `#!/bin/sh`, where it works;
    the doc must say the helpers assume that shell. (Second instance of the
    class: docs/cli.md lost a zsh driver example the same way in the
    amiga_ball pass; the fugue pass hit this one.)"""
    text = GRAPHICS_POLICY.read_text(encoding="utf-8")
    section = text[text.index("## 5."):text.index("## 6.")]
    assert "worth stealing verbatim" in section, \
        "the helper block lost its framing; retarget this test at it"
    assert "#!/bin/sh" in section and "zsh does not perform" in section, \
        "the helper block no longer names the shell it assumes"
    for demo in ("invaders", "ms-muncher", "la-galaxia", "amiga_ball", "fugue"):
        script = DEMOS_DIR / demo / "tools" / "evidence.sh"
        assert script.read_text(encoding="utf-8").startswith("#!/bin/sh"), \
            f"{script} is not the #!/bin/sh the policy says every evidence " \
            f"script uses"


def test_every_landing_page_screenshot_is_wrapped_and_sized():
    """index.html sizes screenshots through `.shot img { width:104px }`, so a
    bare `<img>` dropped straight into a `.shots` div renders at its natural
    width — 1040 pixels, dwarfing every other row. The fugue row shipped
    exactly that (caught by the maintainer's eye, 2026-08-14, and misread at
    first as a capture bug: the PNGs were identical in size to every other
    bordered demo's). Every image in a shots cell must sit in an
    `<a class="shot">` wrapper and carry explicit dimensions so the layout
    cannot depend on the file."""
    text = INDEX.read_text(encoding="utf-8")
    blocks = re.findall(r'<div class="shots">(.*?)</div>', text, re.S)
    assert blocks, "index.html no longer has any .shots blocks; retarget this"
    for block in blocks:
        imgs = re.findall(r"<img[^>]*>", block)
        anchors = block.count('class="shot"')
        assert len(imgs) == anchors, (
            "a screenshot in index.html is not wrapped in <a class=\"shot\">"
            " — it will render at natural size instead of 104px: "
            + block[:120])
        for img in imgs:
            assert 'width="' in img and 'height="' in img, (
                f"a landing-page screenshot lacks explicit dimensions: {img[:120]}")
