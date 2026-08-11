import importlib.util
import os
import re
import shutil
import time
from pathlib import Path

import pytest
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
        # `.py` as well as `.md`: references/ now ships a tool (the branch-range
        # fixer), and a skill that names a script that isn't there is worse
        # than one that names nothing.
        for full in re.findall(r"skills/[\w./-]+/references/[\w.-]+\.(?:md|py)", text):
            assert Path(full).exists(), f"{p}: missing {full}"
        text_wo_full = re.sub(r"skills/[\w./-]+/references/[\w.-]+\.(?:md|py)", "", text)
        for ref in re.findall(r"references/[\w.-]+\.(?:md|py)", text_wo_full):
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


#: The generator the reference cites as its worked example. Named here so a
#: rename has to fix the reference too, instead of leaving it pointing at a
#: file that no longer exists.
GENMUSIC = Path("demos/la-galaxia/tools/genmusic.py")


def test_audio_gives_the_constructive_rule_for_a_generated_score():
    """The reference had the retrigger *fact* (a gate dropped across a frame
    boundary costs a 1-frame rest the score has to list) and no recipe, so
    this demo's generator walked its rows and multiplied: every note a frame
    too long, no leading rests. The rule is model the player one frame at a
    time and run-length encode that — the transcriber's own algorithm."""
    text = AUDIO_REF.read_text()
    section = text[text.index("#### Generate the score"):
                   text.index("To check that the table entry behind")]
    assert "one frame at a time" in section
    assert "Run-length encode" in section
    assert "not the forbidden move" in section or "not** the forbidden" in section, \
        "generating from the note table must be distinguished from " \
        "pasting the transcription back in as the score"
    # The worked example has to be a real function in a file that ships.
    assert str(GENMUSIC.as_posix()) in section, "the worked example is unnamed"
    assert GENMUSIC.exists(), f"{GENMUSIC} is cited and does not exist"
    src = GENMUSIC.read_text()
    for func in ("per_frame", "events"):
        assert f"def {func}(" in src, \
            f"the reference cites {func}(), which {GENMUSIC} no longer defines"


def test_audio_warns_a_score_is_hostage_to_its_window():
    """"Score the window, not the phrase" reads as advice about counting. It
    is also a warning: this demo's first play score included the dive whines
    and collisions the game raised on its own, passed once, and failed when
    unrelated edits moved the enemies. The fix was clearing that state before
    the window, not re-scoring it."""
    text = AUDIO_REF.read_text()
    section = text[text.index("**Score the window, not the phrase.**"):
                   text.index("Both edges are where a first")]
    assert "under your control" in section
    assert "every voice for every frame" in section, \
        "the reason is that a score claims the whole window, not the music"
    assert "clear the enemy state" in section, \
        "the fix — take the other sounds out of the window — is unstated"
    assert "fails on the next unrelated change" in section


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


# --- the character ROM's 4 KB image ---------------------------------------

HARDWARE = Path("skills/c64-development/references/hardware.md")
MEMORY_MAPS = Path("skills/c64-development/references/memory-maps.md")


#: Each reference states the claim in one bullet; the assertions below are
#: scoped to it, since "4 KB" and "$1800" appear elsewhere in both files.
_CHAR_ROM_BULLET = {
    HARDWARE: ("- **VIC 16 KB bank**", "- **`$D018` bit-fields**"),
    MEMORY_MAPS: ("- The VIC-II always reads through", "- The screen can be relocated"),
}


def test_char_rom_image_size_is_stated_with_its_consequence():
    """Both references named the image and neither gave its size, so a reader
    who obeyed the stated rule ("inside the VIC's bank") could still pick
    `$1800` and get the ROM's lowercase half — silent, because it looks like
    text. The number is only useful with the count of bases it costs."""
    for doc, (start, end) in _CHAR_ROM_BULLET.items():
        text = doc.read_text()
        bullet = " ".join(text[text.index(start):text.index(end)].split())
        assert "4 KB" in bullet, f"{doc} never gives the char ROM image's size"
        assert "$1800" in bullet, \
            f"{doc} never names the second base the image makes unusable"
        assert re.search(r"two\**\s+of the eight", bullet), \
            f"{doc} never says the image costs TWO of the eight charset bases"


#: The §0 R1 probe from demos/la-galaxia/PLAN.md, reduced to what settles the
#: claim: the same glyph patched at `$1800` and at `$3800`, drawn under each
#: `$D018`. The RAM at `$1800` is under the char ROM's image, so the VIC never
#: sees it.
_CHARBASE_PROBE = """\
; charbase.s — is RAM at $1800 visible to the VIC in bank 0?
        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"
start:  sei                             ; the char ROM replaces I/O at $D000
        lda     $01
        and     #$FB                    ; CHAREN = 0
        sta     $01
        lda     #$18
        jsr     copyset                 ; ROM charset -> $1800
        lda     #$38
        jsr     copyset                 ; ROM charset -> $3800
        lda     $01
        ora     #$04                    ; I/O back
        sta     $01
        cli

        ldx     #7                      ; screen code 1 -> a solid block,
        lda     #$FF                    ;   in BOTH copies
patch:  sta     $1808,x
        sta     $3808,x
        dex
        bpl     patch

        ldx     #3                      ; four code-1 cells on row 0, white
cells:  lda     #1
        sta     $0400,x
        sta     $D800,x
        dex
        bpl     cells

        lda     #$FF
        sta     ready
loop:   jmp     loop

; A = destination page; copies the 2 KB uppercase set from $D000.
copyset:
        sta     $FE
        lda     #$00
        sta     $FB
        sta     $FD
        lda     #$D0
        sta     $FC
        ldx     #8
page:   ldy     #0
byte:   lda     ($FB),y
        sta     ($FD),y
        iny
        bne     byte
        inc     $FC
        inc     $FE
        dex
        bne     page
        rts

ready:  .byte   0
"""

#: `$D018` for screen `$0400` with the charset base in bits 3-1: `$1800` is
#: base 3, `$3800` is base 7.
_D018_1800, _D018_3800 = 0x16, 0x1E


def _inner_frame(session) -> tuple[int, bytes]:
    with session.monitor() as mon:
        try:
            w, _h, pixels = mon.display()
        finally:
            mon.release()
    return w, pixels


def _cells_region(width: int, pixels: bytes) -> bytes:
    """The four patched cells: 32x8 pixels at the top-left of the text area."""
    return b"".join(pixels[y * width:y * width + 32] for y in range(8))


@pytest.mark.vice
@pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)
def test_char_rom_image_hides_the_1800_charset_base_live(tmp_path, session):
    """The docs' claim, on the machine: with `$D018` pointing at `$1800` the
    VIC draws the char ROM's lowercase glyph, not the solid block sitting in
    RAM there; with it pointing at `$3800` it draws the block. Same RAM, same
    patch, two bases — so the image really is 4 KB and really does cost two
    of the eight bases in bank 0."""
    if shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"):
        pytest.skip("cc65 not installed")
    from c64lib.build import build_asm
    from c64lib.ops import wait_for_mem
    from c64lib.symbols import load_labels
    from tests.vice_helpers import timeout_scale

    src = tmp_path / "charbase.s"
    src.write_text(_CHARBASE_PROBE)
    res = build_asm(src)
    labels = load_labels(res.labels)
    s = session
    with s.monitor() as mon:
        try:
            mon.autostart(res.prg.resolve(), run=True)
        finally:
            mon.resume()
    out = wait_for_mem(s, labels["ready"], 0xFF, 45.0 * timeout_scale())
    assert out["fired"], "the probe never finished its setup"

    frames = {}
    for base in (_D018_1800, _D018_3800):
        with s.monitor() as mon:
            try:
                mon.memory_write(0xD018, bytes([base]))
            finally:
                mon.release()
        time.sleep(0.3)                     # let the VIC draw a frame with it
        width, pixels = _inner_frame(s)
        frames[base] = _cells_region(width, pixels)

    assert len(set(frames[_D018_3800])) == 1, (
        "base $3800 did not draw the patched solid block — the probe, not the "
        "claim, is what failed here")
    assert frames[_D018_1800] != frames[_D018_3800], (
        "the same patched RAM drew identically at $1800 and $3800: the VIC "
        "would have to be seeing RAM at $1800, and the char ROM image would "
        "have to be 2 KB")
    assert len(set(frames[_D018_1800])) > 1, \
        "base $1800 drew a solid cell — expected the char ROM's lowercase glyph"


# --- references/fix-branch-range.py ---------------------------------------

FIXER = Path("skills/6502-assembly/references/fix-branch-range.py")


def _fixer():
    spec = importlib.util.spec_from_file_location("fix_branch_range", FIXER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_asm_skill_points_at_the_branch_fixer():
    """The gotcha predicted the trap and left the reader to do 25 rewrites by
    hand. It has to say the fix is mechanical and that the script exists."""
    text = Path("skills/6502-assembly/SKILL.md").read_text()
    assert FIXER.exists(), "the branch-range fixer must ship"
    assert "fix-branch-range.py" in text, "the skill never names the script"
    assert "mechanical" in text
    assert "25" in text, "the La Galaxia count is what makes it worth tooling"


def test_fixer_parses_ca65_range_errors():
    """Verbatim ca65 wording, taken from a real failed `c64 build`."""
    mod = _fixer()
    log = ("error: ca65 failed:\n"
           "demos/g/enemy.s(210): Error: Range error (204 not in [-128..127])\n"
           "demos/g/enemy.s(97): Error: Range error (-131 not in [-128..127])\n"
           "demos/g/waves.s(12): Error: Range error (130 not in [-128..127])\n"
           "demos/g/waves.s(3): Warning: something else entirely\n")
    assert mod.parse_errors(log) == {Path("demos/g/enemy.s"): [209, 96],
                                     Path("demos/g/waves.s"): [11]}


def test_fixer_inverts_the_branch_over_a_jmp(tmp_path):
    src = tmp_path / "enemy.s"
    src.write_text("        lda #$00\n"
                   "spin:   bne far         ; too far now\n"
                   "        nop\n"
                   "far:    rts\n")
    mod = _fixer()
    report, left = mod.fix_file(src, [1], dry_run=False)
    assert left == 0, report
    assert src.read_text() == ("        lda #$00\n"
                               "spin:   beq :+\n"
                               "        jmp far         ; too far now\n"
                               ":\n"
                               "        nop\n"
                               "far:    rts\n")


def test_fixer_fixes_bottom_up_so_line_numbers_stay_valid(tmp_path):
    """Each rewrite adds two lines; fixing the top branch first would move
    every reported line below it."""
    src = tmp_path / "two.s"
    src.write_text("        bcc one\n"
                   "        nop\n"
                   "        bmi two\n"
                   "one:    rts\n"
                   "two:    rts\n")
    mod = _fixer()
    _report, left = mod.fix_file(src, [0, 2], dry_run=False)
    assert left == 0
    text = src.read_text()
    assert "bcs :+\n        jmp one\n:\n" in text
    assert "bpl :+\n        jmp two\n:\n" in text


def test_fixer_reports_rather_than_touches_an_anonymous_target(tmp_path):
    """The carve-out: the trampoline's own `:` would renumber the label the
    branch is aiming at, so the script hands this one back."""
    src = tmp_path / "anon.s"
    before = "        bne :+\n        nop\n:       rts\n"
    src.write_text(before)
    mod = _fixer()
    report, left = mod.fix_file(src, [0], dry_run=False)
    assert left == 1
    assert src.read_text() == before, "a skipped branch must not be rewritten"
    assert "SKIPPED" in report[0] and "anonymous" in report[0]


def test_fixer_refuses_to_renumber_a_neighbouring_anonymous_label(tmp_path):
    """The same hazard one step out: the branch's own target is a name, but
    inserting `:` below it lands between an earlier `:+` and the label that
    reference resolves to. That build stays green and branches elsewhere,
    which is exactly why it must not be done mechanically."""
    src = tmp_path / "near.s"
    before = ("        beq :+\n"
              "        bcc far\n"
              ":       nop\n"
              "far:    rts\n")
    src.write_text(before)
    mod = _fixer()
    report, left = mod.fix_file(src, [1], dry_run=False)
    assert left == 1
    assert src.read_text() == before
    assert "renumber" in report[0]


def test_fixer_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "dry.s"
    before = "        bne far\n        nop\nfar:    rts\n"
    src.write_text(before)
    mod = _fixer()
    report, left = mod.fix_file(src, [0], dry_run=True)
    assert left == 0 and report and src.read_text() == before


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_fixer_turns_a_real_failing_build_green(tmp_path):
    """The whole loop, against ca65 rather than against a remembered error
    format: build, fail, pipe, rebuild. The rebuild is the only check that
    matters, and it is the one the skill tells the reader to run."""
    from c64lib.build import BuildError, build_asm
    src = tmp_path / "far.s"
    src.write_text('        .segment "LOADADDR"\n        .word $0801\n'
                   '        .segment "CODE"\n'
                   'start:  lda #$00\n'
                   '        bne done\n'
                   '        .res 200, $EA\n'
                   'done:   rts\n')
    with pytest.raises(BuildError) as e:
        build_asm(src)
    assert "Range error" in str(e.value)

    mod = _fixer()
    errors = mod.parse_errors(str(e.value))
    assert errors == {src: [4]}, "the fixer did not recognise ca65's own wording"
    _report, left = mod.fix_file(src, errors[src], dry_run=False)
    assert left == 0
    assert build_asm(src).prg.read_bytes()[:2] == b"\x01\x08"


def test_fixer_exit_code_flags_what_it_left_behind(tmp_path, monkeypatch, capsys):
    """Exit 1 is the signal that a human still has work; a run that fixed
    everything must exit 0 or a build script cannot tell the two apart."""
    import io
    mod = _fixer()
    src = tmp_path / "mix.s"
    src.write_text("        bne :+\n        nop\n:       rts\n")
    log = f"{src}(1): Error: Range error (204 not in [-128..127])\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(log))
    assert mod.main([]) == 1
    src.write_text("        bne far\n        nop\nfar:    rts\n")
    monkeypatch.setattr("sys.stdin", io.StringIO(log))
    assert mod.main([]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("nothing to see here\n"))
    assert mod.main([]) == 0
    assert "nothing to do" in capsys.readouterr().out
