import os
import re
import shutil
from pathlib import Path

import pytest

from tests.doc_helpers import all_command_paths, documented_paths

DOC = Path("docs/cli.md")


def test_every_command_documented_and_vice_versa():
    documented = documented_paths(DOC.read_text())
    actual = all_command_paths()
    missing = actual - documented
    stale = documented - actual
    assert not missing, f"commands lacking a '### `c64 ...`' entry: {sorted(missing)}"
    assert not stale, f"documented commands that do not exist: {sorted(stale)}"


def test_inventory_size_sanity():
    assert len(all_command_paths()) >= 35


def test_session_commands_share_name_option():
    """WS4: one spelling (-s/--name) works on every session-targeting command."""
    import click

    from c64lib.cli import main as cli
    session = cli.commands["session"]
    # click types Group.commands as dict[str, Command]; `session` is a group.
    assert isinstance(session, click.Group)
    for cmd_name in ("start", "stop"):
        cmd = session.commands[cmd_name]
        names = {o for p in cmd.params for o in getattr(p, "opts", [])}
        assert "--name" in names and "-s" in names, \
            f"session {cmd_name} lacks -s/--name (has {sorted(names)})"


def _section(text: str, heading: str) -> str:
    idx = text.index(heading)
    return text[idx:text.index("\n---", idx)]


def test_disk_build_documents_its_labels_key_and_lbl_side_effect():
    """`build_disk` always returns `labels`, and for every `.s` entry it writes
    a `<image-stem>.<cbm-name>.lbl` into the *output* directory. A file
    appearing beside a user's image has to be named where a user would look."""
    section = _section(DOC.read_text(), "### `c64 disk build`")
    assert '"labels"' in section, "the build payload's `labels` key is undocumented"
    assert ".lbl" in section, "the `.lbl` files build writes are undocumented"


def test_mem_get_and_mem_read_document_the_shared_byte_keys():
    """Both payloads carry both `values` and `bytes` since the dogfood filed
    the one-key-each mismatch as a silent KeyError trap."""
    text = DOC.read_text()
    # `_section` runs to the next `---`, and `mem read`'s block contains the
    # `mem get` entry — cut at it, or `mem get`'s `values` answers for both.
    read = _section(text, "### `c64 mem read`").split("### `c64 mem get`")[0]
    assert '"bytes"' in _section(text, "### `c64 mem get`")
    assert '"values"' in read


def test_disk_validate_documents_its_damage_findings():
    """`validate` is the one verb where a DOS status line is a finding about
    the image rather than a failed operation, so it reports rather than
    erroring — the docs' `messages` promise has to say so."""
    section = _section(DOC.read_text(), "### `c64 disk validate`")
    assert "messages" in section
    assert "65" in section, \
        "the docs never mention the DOS error validate reports as a finding"


def test_mem_read_documents_its_text_column_gloss():
    """The gutter is a *gloss*, not the bytes: the docs have to say which
    decoding is in play and how to override it, or the ASCII-on-screen-RAM
    trap comes straight back."""
    section = _section(DOC.read_text(), "### `c64 mem read`")
    assert "--as" in section, "the `--as` encoding override is undocumented"
    assert "screen codes" in section
    assert "text column" in section, "the gutter's label is undocumented"
    assert "text_encoding" in section, "the JSON key is undocumented"


def test_mem_read_documents_colour_ram_open_bus_and_the_mask():
    """`$D800-$DBFF` is four bits wide and reads back `(phi1 & $F0) | storage`,
    so a raw comparison there fails on unchanged builds and passes on changed
    ones. The passage shipped with no guard; `demos/1812` paid for the missing
    knowledge twice in one pass, and a doc claim nothing tests can be deleted by
    a compression pass without anything noticing."""
    section = " ".join(_section(DOC.read_text(), "### `c64 mem read`").split())
    assert "(phi1 & $F0) | storage" in section, \
        "the docs never say what a colour-RAM read actually returns"
    assert "differ in all 1000 bytes" in section, \
        "the docs never say two dumps of ONE build can differ everywhere"
    assert "compare equal by luck" in section, \
        "the docs never say two dumps of DIFFERENT builds can agree"
    assert 'mask: { and: "$0f"' in section, \
        "the docs never give the masked comparison a spec should use"
    assert "on purpose" in section, \
        "the docs never say the tool leaves the high nybble unmasked deliberately"


def test_until_count_documents_its_measured_per_arrival_cost():
    """The cost note is the one place a reader learns whether a four-figure
    `--count` is affordable, and it was written from an unverified aside that
    re-measurement refuted — "tens of minutes" for a run that takes 27 s. So the
    guard is on the *measurement*: the two anchors, both run counts, the span
    they share, and the wrapper the figures were taken under. Prose that drops
    them is prose that is no longer showing its work."""
    section = " ".join(_section(DOC.read_text(), "### `c64 until`").split())
    assert "until seqtick --count 10200" in section and \
        "until secchange --count 5" in section, \
        "the cost note names neither of the two anchors it was measured on"
    assert "frames = $27D8" in section, \
        "the docs never establish that the two anchors cover the SAME span"
    assert "caffeinate -dimsu" in section, \
        "the docs quote timings without the conditions they were taken under"
    assert "budget by the span you cover, not" in section, \
        "the docs still let a reader budget by N rather than by the span"
    for lie in ("tens of minutes", "many times dearer", "expire long before"):
        assert lie not in section, \
            f"the refuted claim {lie!r} is back in the `until` cost note"


def test_until_cost_notes_conclusions_follow_from_its_own_table():
    """Naming the measurement is not enough on its own: an edit could swap the
    timings, or restate the conclusions, and leave the guard above green while
    the paragraph stopped following from the table under it. So this one does
    the arithmetic. It recomputes the marginal per-arrival cost, the ratio and
    the frame-stepping rate from the six timings the table publishes, and
    requires the prose's stated figures to match.

    It is also the guard against the two quantities being conflated again:
    0.44 ms per arrival and ~370 frames per second are not reciprocals — one is
    what a stop costs, the other is how fast the emulator covers the program —
    and a reader who reads them as one is out by a factor of six.
    """
    section = " ".join(_section(DOC.read_text(), "### `c64 until`").split())
    rows = re.findall(r"\| `c64 until (\w+) --count (\d+)\`[^|]*\|[^|]*\|"
                      r"([^|]*)\|([^|]*)\|([^|]*)\|", section)
    assert len(rows) == 2, f"the cost note's measurement table is gone or reshaped: {rows}"
    means, arrivals = {}, {}
    for ref, count, *cells in rows:
        runs = [float(m) for c in cells for m in re.findall(r"([\d.]+) s", c)]
        assert len(runs) == 3, f"`{ref}` no longer publishes three runs: {cells}"
        means[ref] = sum(runs) / len(runs)
        arrivals[ref] = int(count)

    def stated(pattern: str, what: str) -> float:
        """The figure the prose claims — and a readable failure when the prose
        has stopped claiming it at all, which is the other way this guard can
        need to fire."""
        m = re.search(pattern, section)
        assert m is not None, f"the cost note no longer states {what}"
        return float(m.group(1))

    dense, sparse = "seqtick", "secchange"
    # marginal cost of one arrival, from the two anchors' shared span
    ms = (means[dense] - means[sparse]) * 1000 / (arrivals[dense] - arrivals[sparse])
    stated_ms = stated(r"marginal cost is ~([\d.]+) ms", "a per-arrival cost")
    assert abs(ms - stated_ms) < 0.05, \
        f"the stated ~{stated_ms} ms per arrival is not what the table gives ({ms:.3f})"

    ratio = means[dense] / means[sparse]
    stated_ratio = stated(r"\*\*([\d.]+)×\*\* five stops", "the dense/sparse ratio")
    assert abs(ratio - stated_ratio) < 0.02, \
        f"the stated {stated_ratio}x is not what the table gives ({ratio:.3f})"

    rate = arrivals[dense] / means[dense]
    stated_rate = stated(r"~(\d+) emulated frames per second", "a frame-stepping rate")
    assert abs(rate - stated_rate) < 15, \
        f"the stated ~{stated_rate}/s is not what the table gives ({rate:.1f})"
    # …and the rate is NOT the reciprocal of the per-arrival cost. If a future
    # edit ever makes it so, the two quantities have been collapsed into one.
    assert abs(rate - 1000 / stated_ms) > 100, \
        "the frame rate now reads as 1/(per-arrival cost) — two different things"


def test_test_run_documents_the_always_present_tests_envelope():
    """A spec-level error emits `{"error", "passed": false, "tests": []}` rather
    than dropping `tests` — 1812's harness crashed on the missing key. A promise
    a harness codes against has to be written down, not just implemented."""
    # These two entries end the file, so there is no trailing `---` for
    # `_section` to cut on: slice between the headings by hand, or the sibling
    # command's envelope answers for `test run`.
    text = DOC.read_text()
    section = text[text.index("### `c64 test run`"):text.index("### `c64 test programs`")]
    assert '"tests": []' in section, "the spec-error envelope is undocumented"
    assert "always present" in section, \
        "the docs never promise `tests` is present whether or not the test ran"


def test_sprite_encode_documents_named_blocks_and_a_visible_background():
    """The sheet grew headers, comments and `--background`; and the old "count
    columns rather than trusting the rendering" warning only ever existed
    because the background pixel was an invisible space."""
    section = _section(DOC.read_text(), "### `c64 sprite encode`")
    assert "--background" in section, "the visible-background option is undocumented"
    assert "`name:` headers" in section and ":hires" in section, \
        "per-block mode headers are undocumented"
    assert "count columns rather than trusting the rendering" not in section, \
        "the trailing-whitespace warning outlived the space background"


def test_charset_encode_documents_its_label_option():
    section = _section(DOC.read_text(), "### `c64 charset encode`")
    assert "--label" in section, "the block-label option is undocumented"


def test_run_documents_its_area_option():
    """`c64 run --area` is what a program linked above the load address needs
    to be runnable at all — undocumented, it may as well not exist."""
    section = _section(DOC.read_text(), "### `c64 run`")
    assert "--area" in section, "the linker-area option is undocumented"
    assert "assembly sources only" in section, \
        "the docs never say --area is rejected for a .bas/.prg/.crt"


def test_test_run_documents_areas_and_the_prg_label_rule():
    """The spec's `areas:` key and the sibling-`.lbl` rule for `program:` are
    the two things La Galaxia's spec went the long way round for."""
    text = DOC.read_text()
    section = text[text.index("### `c64 test run`"):text.index("### `c64 test programs`")]
    assert "areas:" in section, "the spec's `areas:` key is undocumented"
    assert ".lbl" in section, \
        "the sibling label file a `.prg` program: picks up is undocumented"


def test_test_run_documents_the_sample_width_option():
    """A one-byte sample against a 16-bit counter passes on margin rather than
    on logic, and the spec that hit it (1812's `shapes greater_than s0`) had no
    way to say otherwise. Undocumented, `width:` would go on being unavailable
    to everyone who did not read the runner."""
    text = DOC.read_text()
    section = text[text.index("### `c64 test run`"):text.index("### `c64 test programs`")]
    assert "width: 2" in section, "the two-byte sample option is undocumented"
    assert "lo/hi" in section, "the docs never say which byte order a width-2 read is"
    assert "the width of the sample they name" in section, \
        "the docs never say the comparison inherits the sample's width"


def test_test_run_documents_where_an_s_program_builds():
    """`build_asm` writes beside the source, so a spec that names a `.s`
    rewrites `<stem>.prg` and `<stem>.lbl` in the demo's own directory every
    run — which republishes a *tracked* binary (la-galaxia's `.prg` is one)
    and leaves the label file newer than any sibling image, which is exactly
    the state the staleness stop two paragraphs later refuses."""
    text = DOC.read_text()
    section = text[text.index("**Program tests.**"):
                   text.index("**Cartridge tests.**")]
    assert "beside the source" in section, \
        "the docs never say where a `.s` program:'s build output lands"
    assert "overwriting both" in section, \
        "the docs never say the build overwrites what is there"
    assert "newer than any sibling" in section, \
        "the docs never connect a source build to the disk staleness stop"


def test_test_run_documents_the_staleness_override():
    """A guard with no documented escape gets worked around instead of used:
    `cp -r` without `-p` restamps a tree, and the stop is mtime-based."""
    text = DOC.read_text()
    section = text[text.index("### `c64 test run`"):text.index("### `c64 test programs`")]
    assert "--allow-stale" in section, "the staleness override is undocumented"
    assert "warns" in section or "warning" in section, \
        "the docs never say the override reports what it let through"
    # both nouns: the `.prg` comparison is symmetric, and documenting one
    # direction is how a caller learns to distrust the other one's silence
    for direction in ("newer than its symbols", "predates its symbols"):
        assert direction in section, \
            f"the docs never mention `{direction}`"


def test_profile_documents_samples_and_why_one_arrival_lies():
    """`--samples` is only worth reaching for if the docs say what a single
    arrival gets wrong: a per-frame cost that spikes on a repaint every few
    frames reads as fine 27 times in 32."""
    section = _section(DOC.read_text(), "### `c64 profile`")
    assert "--samples" in section, "the sampling option is undocumented"
    assert "bimodal" in section, \
        "the docs never say WHY one arrival can lie about a per-frame cost"
    for key in ('"samples"', '"min"', '"max"', '"mean"'):
        assert key in section, f"the {key} payload key is undocumented"
    assert '"cycles"' in section, \
        "the docs never pin that `cycles` survives at --samples 1"


def test_profile_documents_that_samples_re_enters_rather_than_reruns():
    """`--samples` synthesises the same JSR N times; it does not advance the
    program. For a per-frame tick that steps the game the spread is real, and
    for a leaf routine whose caller sets its operands it is badline jitter
    around one repeated case — which four `demos/1812` routines were read as
    regressions for. Sibling of the `--samples`/`bimodal` guard above: that one
    says why ONE arrival lies, this one says why N can lie the same way."""
    section = " ".join(_section(DOC.read_text(), "### `c64 profile`").split())
    assert "re-enters the routine; it does not re-run the program" in section, \
        "the docs never say `--samples` does not advance the program"
    assert "advances the state its cost depends on" in section, \
        "the docs never name the case where the spread IS the distribution"
    assert "leaf routine whose inputs its caller sets up" in section, \
        "the docs never name the case where the spread is jitter, not a range"
    assert "control the inputs instead of sampling" in section, \
        "the docs give the limitation without the technique that answers it"


def test_profile_documents_blanking_and_the_differential_distinction():
    """Two claims a reader chases a phantom without.

    Blanking the screen is the only way to ask a profile about *code* cost, and
    a blanked count is not the frame budget — so the caveat has to travel with
    the trick or the trick becomes a wrong answer to the other question.

    And a patched differential is not cross-checkable against a whole-routine
    profile across two builds: a size-changing commit moves tables and branches
    into and out of page crossings, which the differential cancels by
    construction and the whole-routine figure keeps. `demos/1812`'s `52b2ed3`
    was filed as "the differential is 6.2% low" for exactly as long as that
    went unwritten.
    """
    # Prose wraps; these are sentences, not lines.
    section = " ".join(_section(DOC.read_text(), "### `c64 profile`").split())
    assert "DEN (`$D011` bit 4)" in section, \
        "the blanking write is undocumented"
    assert "does not answer *does this fit in a frame*" in section, \
        "the docs give the blanking trick without the caveat that limits it"
    assert "not a cross-check" in section, \
        ("the docs never say a patched differential and a whole-routine "
         "profile measure different quantities across builds")
    assert "`(base & $FF) + index` carries" in section, \
        "the docs never name the mechanism relocation moves cycles by"
    # What blanking buys, stated as the data supports it. The absolute legs
    # moved when the workload did; what came back identical across the two
    # batches was the subtraction, and an earlier draft promoted that into
    # "all six legs reproduced exactly", which the second batch's own numbers
    # contradict.
    assert "is the difference, not the leg" in section, \
        "the docs claim a blanked leg reproduces, rather than the subtraction"
    # The multiplier's derivation, with the step that turns a stolen fraction
    # into a scale factor. Without it the stated equality is simply false:
    # 1,075 / 17,095 is 6.29%, not 1.0671.
    assert "6.29% of the frame stolen" in section, \
        "the badline arithmetic states a quotient it does not compute"
    assert "0.0629" in section, \
        "the docs never show the step from a stolen fraction to a multiplier"
    # The overclaim this paragraph was corrected for. gapB measured a different
    # shape configuration and four of the six legs moved with it; only the
    # subtraction came back identical. Negative, like the `until` guard's, since
    # the failure mode here is a compression pass restoring a tidier sentence.
    for lie in ("All six blanked legs", "all six blanked legs"):
        assert lie not in section, \
            f"the refuted claim {lie!r} is back in the blanking passage"


def test_session_stop_documents_all_and_start_documents_the_notice():
    """Four x64sc processes ran at once during the la-galaxia dogfood, two
    orphaned from an earlier conversation. The one-command cleanup and the
    "N already up" warning only exist for a reader if they are written down —
    including that the notice is on stderr, so `--json` stays parseable."""
    text = DOC.read_text()
    stop = text[text.index("### `c64 session stop`"):
                text.index("### `c64 session reset`")]
    assert "--all" in stop, "the --all flag is undocumented"
    assert '"stopped": [' in stop, \
        "the --all JSON payload (a list, not a name) is undocumented"
    assert "already gone" in stop, \
        "the docs never say --all reaps a session whose emulator has died"
    start = text[text.index("### `c64 session start`"):
                 text.index("### `c64 session ensure`")]
    assert "note: N other session(s) already running" in start, \
        "the already-running notice is undocumented"
    assert "stderr" in start, \
        "the docs never say the notice bypasses --json (it is on stderr)"


def test_headless_documents_the_null_sound_sink():
    """A headless session is silent by construction — its sound goes to a
    file-backed null sink so the emulation loop never waits on a host consumer
    that may not exist. Undocumented, that silence reads as a broken audio path
    and invites someone to "fix" the one thing keeping headless sessions from
    wedging."""
    text = DOC.read_text()
    start = text[text.index("### `c64 session start`"):
                 text.index("### `c64 session ensure`")]
    section = " ".join(start.split())          # the claim is a sentence, not a line
    assert "null sink" in section, "the headless sound sink is undocumented"
    assert "makes no noise" in section, \
        "the docs never say the sink is why a headless session is silent"


def test_session_start_documents_the_macos_idle_throttling_hazard():
    """The second way a headless session presents as broken, and the one that
    costs a debugging session rather than a puzzled minute: macOS idle-throttles
    a minimized background emulator until every binary-monitor call times out,
    while the process is alive and its ports still answer. It reads as a wedge.
    The A/B that attributed it lives in `CHANGELOG.md`, which is not where a
    reader looks for operating guidance — hence the pointer here."""
    text = DOC.read_text()
    start = text[text.index("### `c64 session start`"):
                 text.index("### `c64 session ensure`")]
    section = " ".join(start.split())
    assert "caffeinate -dimsu" in section, \
        "the remedy for macOS idle throttling is undocumented"
    assert "idle-throttles" in section, \
        "the docs never name what slows an unattended headless session"
    assert "wedged emulator" in section, \
        "the docs never say the symptom is indistinguishable from a wedge"
    assert "CHANGELOG.md" in section, \
        "the docs never point at the A/B that attributed the hazard"


#: The three areas the la-galaxia dogfood measured the fill against, and the
#: only thing about them that matters here: the two below `ENGINE` are filled
#: to their declared size, `ENGINE` is not.
_AREA_TRIO = [("SPRITES", 0x2000, 0x1800), ("CHARS", 0x3800, 0x0800),
              ("ENGINE", 0x4000, 0x5000)]


def test_build_documents_which_areas_are_filled():
    """`--area` said "fill" and "contiguous" and never said *which* areas get
    filled — which is what decides how big the file is, and (the trap) that a
    `.res` in an area is content rather than a hole."""
    # Prose wraps; the claim is a sentence, not a line.
    section = " ".join(_section(DOC.read_text(), "### `c64 build`").split())
    assert "Every area below the last one is filled to its declared size" in section, \
        "the docs never say every area but the last is filled to its size"
    assert "the last one is not" in section, \
        "the docs never say the topmost area is left at its real length"
    assert "content, not a hole" in section, \
        "the docs never warn that a `.res` inside an area ships as zeros"


#: Files that DO repeat `docs/cli.md`'s flat-padding figure, and so have to
#: agree with it — as against `_FIGURE_WATCHED` below, where a copy is what is
#: being watched *for*. Every entry here must still hold one (see the per-file
#: assert), so a copy that goes away shows up as a failure and not as silence.
#: `demos/la-galaxia/PLAN.md` is deliberately in neither list: it is a dated
#: lab record that quotes its own wrong 14,342 beside the correction, and a
#: guard over it would forbid saying the number had been wrong.
_FIGURE_ECHOES = ["CHANGELOG.md"]

#: Files that deliberately DON'T repeat the figure — they point at
#: `docs/cli.md` instead — watched in case one comes back. Zero matches is the
#: passing state here, so this list is the one shape the per-file rule above
#: must not be applied to.
#:
#: `skills/6502-assembly/SKILL.md` is the whole reason the mechanism exists.
#: It carried the figure at `8d5b5d3:.../SKILL.md:286` ("flat 14,337 bytes
#: before `ENGINE`'s own contents"); `d99c561` replaced it with a pointer to
#: `docs/cli.md` and, in the same commit, started reading the file here — an
#: unverified second copy of this exact number is how 14,342 drifted into
#: `demos/la-galaxia/PLAN.md` and reached a task brief. The read was never an
#: echo comparison that had gone stale, and anyone treating it as dead weight
#: because it matches nothing is deleting the watch: that is exactly what
#: happened once already, and this comment is the fix for it.
_FIGURE_WATCHED = ["skills/6502-assembly/SKILL.md"]

#: Matches the figure bolded (`docs/cli.md`) or bare (`CHANGELOG.md`) — one
#: pattern where the source and the echoes used to have a regex each. Neither
#: of those failed to match: the bold one found `docs/cli.md`'s copy and the
#: bare one found `SKILL.md`'s until `d99c561` removed it.
_FLAT_FIGURE = re.compile(r"flat \*{0,2}([\d,]{6,}) bytes")


def _documented_flat_padding() -> tuple[int, str]:
    section = " ".join(_section(DOC.read_text(), "### `c64 build`").split())
    m = _FLAT_FIGURE.search(section)
    assert m, "docs/cli.md no longer states the flat padding cost"
    return int(m.group(1).replace(",", "")), m.group(1)


def test_every_copy_of_the_flat_padding_figure_agrees_with_the_docs():
    """One figure, one source. An unverified second copy is how 14,342
    survived in `demos/la-galaxia/PLAN.md` and reached a task brief.

    Split out of the build below and left ungated on ca65 on purpose: this
    half compares text, and a guard that only runs where a toolchain happens
    to be installed is the same as no guard on the machines that lack it.
    """
    claimed, spelled = _documented_flat_padding()
    for name in _FIGURE_ECHOES:
        strays = _FLAT_FIGURE.findall(Path(name).read_text())
        # Per file, not summed over the list: a list-level count lets one live
        # entry carry the guard while another sits dead beside it, which is the
        # exact state this started in.
        assert strays, (
            f"{name} no longer spells the flat-padding figure this guard "
            f"matches. If it really dropped its copy, move it to "
            f"_FIGURE_WATCHED rather than leaving a dead entry here")
        for stray in strays:
            assert int(stray.replace(",", "")) == claimed, \
                f"{name} says {stray} where docs/cli.md says {spelled}"


def test_the_figure_stays_gone_from_the_files_it_was_removed_from():
    """The other half of "one figure, one source": a file that was made to
    point at `docs/cli.md` must not quietly grow its own copy again.

    Deliberately NOT the per-file rule above. Zero matches is the passing
    state, so this cannot assert that it found something — which is precisely
    why the watch reads as dead weight to anyone who checks whether it matches
    anything today, and why `_FIGURE_WATCHED` carries the history instead.

    A copy that agrees passes, as it did under `d99c561`: once the file is on
    this list every run compares it, so the copy is verified rather than
    unverified, and it is the *unverified* second copy that drifts. Only a
    disagreeing one fails.
    """
    claimed, spelled = _documented_flat_padding()
    for name in _FIGURE_WATCHED:
        for stray in _FLAT_FIGURE.findall(Path(name).read_text()):
            assert int(stray.replace(",", "")) == claimed, (
                f"{name} states the flat-padding figure as {stray} where "
                f"docs/cli.md says {spelled}. This file was made to point at "
                f"docs/cli.md rather than restate the number (d99c561); a copy "
                f"here is only allowed while it agrees")


@pytest.mark.skipif(
    shutil.which("ca65") is None and not os.environ.get("C64_TOOLS_CA65"),
    reason="cc65 not installed",
)
def test_the_documented_area_padding_is_the_measured_one(tmp_path):
    """The number in the docs, built — a figure nobody can reproduce is the
    kind that drifts by five bytes and reaches a task brief.

    The fixture is deliberately an *uninitialized* `.res` behind one real
    byte, because that is where the tempting version of the claim ("the last
    area's `.res` costs nothing") is false: the area's segment is `type = ro`,
    so 4,096 reserved bytes ship as zeros. What the last area really saves is
    the tail beyond what it holds — declared `$5000`, and nothing padded out
    to it.
    """
    from c64lib.build import Area, build_asm

    # The text half — every other copy of the figure agreeing with this one —
    # is its own ungated test above; this one builds it.
    claimed, _ = _documented_flat_padding()

    src = tmp_path / "trio.s"
    src.write_text('        .segment "LOADADDR"\n        .word $0801\n'
                   '        .segment "CODE"\nstart:  rts\n'
                   '        .segment "SPRITES"\n        .byte $01\n'
                   '        .segment "CHARS"\n        .byte $02\n'
                   '        .segment "ENGINE"\n        .byte $03\n'
                   '        .res 4096\n')
    res = build_asm(src, areas=[Area(*a) for a in _AREA_TRIO])
    data = res.prg.read_bytes()
    engine_off = 2 + (0x4000 - 0x0801)
    assert engine_off == claimed, (
        f"docs claim {claimed} flat bytes below the last area; the build puts "
        f"ENGINE at file offset {engine_off}")
    # Filled below: CHARS is at its declared address, not packed after CODE.
    assert data[2 + (0x3800 - 0x0801)] == 0x02, "CHARS did not land at $3800"
    # Not filled on top: the declared $5000 tail never ships...
    assert len(data) < claimed + 0x5000, \
        "the last area was padded to its declared size after all"
    # ...but `.res` inside it is content, and does.
    assert data[engine_off:] == bytes([0x03]) + bytes(4096), \
        "an uninitialized .res in the last area did not ship as zero bytes"


def test_wait_documents_the_stopped_machine_timeout():
    """`wait --mem` after a `c64 until` burned 120 s and reported `last value
    1` — the repo's most-repeated footgun. The docs have to say the timeout
    names it, or the reader still reaches for the wrong diagnosis."""
    section = " ".join(_section(DOC.read_text(), "### `c64 wait`").split())
    assert '"machine": "stopped"' in section, \
        "the stopped-machine JSON field is undocumented"
    assert "c64 continue" in section, "the docs never give the way out"
    assert "either side of the wait" in section, \
        ("the docs never say the state is sampled twice (one sample cannot "
         "support 'stopped for the whole wait')")


def test_audio_documents_strict_and_that_the_default_is_unchanged():
    """`--strict` is only half the claim. The default — warn and exit 0 over a
    capture in which nothing played — was reasoned and stays, so the docs have
    to say the flag is opt-in and what it costs to turn on; otherwise the next
    reader takes exit 0 for "the audio works" or the flag for the behaviour."""
    text = DOC.read_text()
    capture = " ".join(_section(text, "### `c64 audio capture`").split())
    assert "`--strict`" in capture, "the flag is undocumented on the command"
    assert "same warning, same exit 0" in capture, \
        "the docs never say the default is unchanged"
    assert "still printed in full" in capture, \
        ("the docs never say a strict exit 1 still emits the payload, which is "
         "what a --json caller needs to read the verdict it failed on")
    report = " ".join(_section(text, "### `c64 audio report`").split())
    assert "`--strict`" in report, \
        "the sibling verdict command carries the flag and the docs omit it"


def test_break_list_documents_what_a_mask_with_no_known_bits_renders_as():
    """The `op` paragraph said what the three bits spell and never what
    *none* of them spells. `protocol.op_name` answers `""` there — a value a
    `--json` caller can only find out by hitting it, and one that reads as a
    missing field rather than as the documented answer."""
    section = " ".join(_section(DOC.read_text(), "### `c64 break list`").split())
    assert 'the empty string `""`' in section, \
        ("the docs never say that an op mask with none of the three bits set "
         "renders as the empty string")


def test_cli_md_names_every_machine_profile():
    from c64lib.machines import PROFILES
    text = DOC.read_text()
    for name in PROFILES:
        assert f"`{name}`" in text, f"docs/cli.md never names {name}"
