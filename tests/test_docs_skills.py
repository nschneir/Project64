import re
from pathlib import Path

import yaml

from tests.doc_helpers import mentioned_commands, valid_mention_paths

SKILLS = [Path("skills/c64-development/SKILL.md"),
          Path("skills/6502-assembly/SKILL.md"),
          Path("skills/6502-debugging/SKILL.md"),
          Path("skills/cartridge-programming/SKILL.md"),
          Path("skills/disk-io-programming/SKILL.md")]


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


def test_disk_io_skill_exists_and_is_wired_up():
    p = Path("skills/disk-io-programming/SKILL.md")
    assert p.exists(), "the disk-I/O skill must ship"
    fm, text = _frontmatter(p)
    assert fm["name"] == "disk-io-programming"
    for topic in ("SETLFS", "SETNAM", "$FFD5", "device 8", "secondary address"):
        assert topic in text, f"skill never mentions {topic}"
    # Discoverable from the umbrella skill.
    assert "disk-io-programming" in Path(
        "skills/c64-development/SKILL.md").read_text()


def test_disk_io_reference_commands_exist():
    """The KERNAL reference is prose the agent acts on too, so its `c64 ...`
    mentions get the same reality check the SKILL.md files get."""
    ref = Path("skills/disk-io-programming/references/kernal-disk-io.md")
    assert ref.exists(), "the KERNAL disk-I/O reference must ship"
    valid = valid_mention_paths()
    unknown = {c for c in mentioned_commands(ref.read_text()) if c not in valid}
    assert not unknown, f"{ref}: mentions nonexistent commands {sorted(unknown)}"


def test_disk_io_entry_points_agree_with_the_kernal_reference():
    """The two references must not disagree about an address.

    Both tables list the KERNAL disk routines; a copy that drifts is worse
    than no copy, so every `| FFxx | NAME |` row in the new reference is
    checked against the umbrella skill's jump table.
    """
    umbrella = Path("skills/c64-development/references/kernal-routines.md").read_text()
    known = dict(re.findall(r"^\|\s*(FF[0-9A-F]{2})\s*\|\s*(\w+)", umbrella, re.M))
    ref = Path("skills/disk-io-programming/references/kernal-disk-io.md").read_text()
    rows = re.findall(r"^\|\s*`?\$?(FF[0-9A-F]{2})`?\s*\|\s*`?(\w+)`?", ref, re.M)
    assert rows, "the reference lists no KERNAL entry points"
    for addr, name in rows:
        assert known.get(addr) == name, (
            f"kernal-disk-io.md says ${addr} is {name}; "
            f"kernal-routines.md says {known.get(addr)}")


C64_DEV = Path("skills/c64-development/SKILL.md")
AUDIO_REF = Path("skills/c64-development/references/audio-verification.md")


def test_audio_lead_in_covers_assembly():
    """The section was written entirely for BASIC, and an assembly program
    has the same problem with a different fix: a lead-in consumed once per
    start, not one baked into the track data — which repeats on every loop."""
    text = AUDIO_REF.read_text()
    section = text[text.index("### Give the program a silent lead-in"):
                   text.index("## Writing a reference score")]
    assert "In assembly" in section
    assert "loop" in section and "baking the silence into the track data" in section
    assert "84" in section, "the measured arming cost is the number to size against"


def test_audio_has_one_shot_cue_recipe():
    """The manoeuvre that actually made the dogfood's act scores
    deterministic, as opposed to the mitigations for window-edge fragility."""
    text = AUDIO_REF.read_text()
    assert "one-shot cue" in text
    assert "Both edges then fall in silence" in text


def test_audio_says_durations_drift():
    text = AUDIO_REF.read_text()
    assert "jiffy" in text and "omitting `frames` is a legitimate score" in text


def test_skill_says_call_ends_the_run():
    """docs/cli.md states plainly that `c64 call` replaces the running
    program's control flow; the skill that recommends `c64 call` did not, and
    the Ms. Muncher dogfood lost two debugging passes to a machine that looked
    wedged before re-reading the CLI reference."""
    text = C64_DEV.read_text()
    section = text[text.index("## Verifying a change"):]
    assert "ends that run" in section
    assert "docs/cli.md" in section


def test_skill_says_wait_does_not_resume():
    """The skill stated the stopped-state rule and separately stated that
    waits poll, and never joined them: a wait issued after `until` polls a
    stopped machine and can only time out."""
    text = C64_DEV.read_text()
    start = text.index("**The stopped-state rule.**")
    section = text[start:text.index("## Text encodings")]
    assert "poll" in section and "do not resume" in section
    assert "c64 continue" in section
    assert "c64 test run" in section or "YAML" in section, \
        "the same rule applies inside a spec, where the runner behaves the same"


def test_skill_diagnosis_rows_present():
    rows = C64_DEV.read_text()
    assert "The machine is stopped —" in rows
    assert "the program is gone" in rows


def test_cartridge_reference_commands_exist():
    """The EasyFlash reference is prose the agent acts on too, so its `c64 ...`
    mentions get the same reality check the SKILL.md files get."""
    ref = Path("skills/cartridge-programming/references/easyflash.md")
    assert ref.exists(), "the EasyFlash reference must ship"
    valid = valid_mention_paths()
    unknown = {c for c in mentioned_commands(ref.read_text()) if c not in valid}
    assert not unknown, f"{ref}: mentions nonexistent commands {sorted(unknown)}"
