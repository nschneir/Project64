from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from c64lib.testing import TestError, run_test


def _fake_session():
    s = Mock()
    s.profile.basic_version = "2.0"
    s.profile.basic_start = 0x0801
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


def _spec(**kw):
    base = {"name": "t", "machine": "c64", "timeout": 2,
            "autorun": True, "steps": []}
    base.update(kw)
    return base


def test_happy_path_key_wait_assert(tmp_path):
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.registers.return_value = {"PC": 0xC500}
    screens = ["READY.", "READY.", "HELLO", "HELLO", "HELLO"]
    spec = _spec(steps=[
        {"key": "RUN\n"},
        {"wait": {"text": "HELLO"}},
        {"assert": {"reg": "pc", "in_range": ["$C000", "$E000"]}},
    ])
    with patch("c64lib.testing.read_screen_text", side_effect=screens):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert [st.ok for st in result.steps] == [True, True, True]
    launch.assert_called_once_with(model="c64", name=result.session_name,
                                   headless=True, warp=True, cart=None,
                                   disk8=None)
    mon.keyboard_feed.assert_called_once_with(b"RUN\r")
    s.stop.assert_called_once()


def test_wait_text_since_ignores_stale_occurrence():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    screens = ["READY.", "TOO HIGH", "TOO HIGH", "TOO HIGH\nTOO HIGH", "TOO HIGH\nTOO HIGH"]
    spec = _spec(steps=[
        {"wait": {"text": "TOO HIGH", "since": True}},
    ])
    with patch("c64lib.testing.read_screen_text", side_effect=screens):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert [st.ok for st in result.steps] == [True]


def test_poke_and_until_steps():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[
        {"poke": {"addr": "$CB", "values": [68]}},
        {"until": {"ref": "$0419", "count": 3}},
    ])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.run_until",
               return_value={"registers": {"PC": 0x0419}, "reached": 3,
                             "count": 3}) as ru:
        result = run_test(spec, launch=launch)
    assert result.passed is True
    mon.memory_write.assert_called_once_with(0xCB, bytes([68]))
    ru.assert_called_once_with(s, 0x0419, timeout=2, count=3)


def test_until_timeout_fails_step_with_progress():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"until": {"ref": "$0419", "count": 5, "timeout": 1}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.run_until",
               return_value={"registers": None, "reached": 2, "count": 5}):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert "2/5" in result.steps[0].detail


def test_fail_fast_captures_screen():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    # constant screen: boot sees READY. immediately; the failing wait spins
    # (sleep patched to a no-op) without exhausting a side_effect list
    spec = _spec(steps=[
        {"wait": {"text": "NEVER", "timeout": 0.5}},
        {"key": "RUN\n"},          # must not execute
    ])
    with patch("c64lib.testing.read_screen_text", return_value="READY.\nNOPE"), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert len(result.steps) == 1 and result.steps[0].ok is False
    assert "NOPE" in result.screen
    mon.keyboard_feed.assert_not_called()
    s.stop.assert_called_once()


def test_assert_mem_equals_text():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    # screen codes for "HI" are 8, 9
    mon.memory_read.return_value = bytes([8, 9])
    spec = _spec(steps=[{"assert": {"mem": "$0400", "equals_text": "HI"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    mon.memory_read.assert_called_with(0x0400, 2)


def test_program_bas_tokenized_and_autostarted(tmp_path):
    prog = tmp_path / "p.bas"
    prog.write_text('10 print "hi"\n')
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(program=str(prog))
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.tokenize", return_value=tmp_path / "p.prg") as tok:
        result = run_test(spec, launch=launch)
    assert result.passed is True
    tok.assert_called_once_with(prog, prog.with_suffix(".prg"), "2.0")
    mon.autostart.assert_called_once_with((tmp_path / "p.prg").resolve(), run=True)


def test_autorun_false_waits_for_load(tmp_path):
    prog = tmp_path / "p.prg"
    prog.write_bytes(b"\x01\x08")
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    screens = ["READY.",                                  # boot
               "LOAD\"*\",8\n\nSEARCHING",                # loading...
               "LOAD\"*\",8\n\nSEARCHING\nLOADING\nREADY.",  # loaded
               "DONE", "DONE"]
    spec = _spec(program=str(prog), autorun=False,
                 steps=[{"wait": {"text": "DONE"}}])
    with patch("c64lib.testing.read_screen_text", side_effect=screens), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    mon.autostart.assert_called_once_with(prog.resolve(), run=False)


def test_boot_timeout_is_error():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    with patch("c64lib.testing.read_screen_text", return_value="GARBAGE"), \
         patch("c64lib.testing.time.sleep"), \
         patch("c64lib.testing.time.monotonic", side_effect=[i * 10.0 for i in range(100)]):
        with pytest.raises(TestError, match="READY"):
            run_test(_spec(), launch=launch)
    s.stop.assert_called_once()


def test_wait_mem_polls_until_value():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.side_effect = [b"\x00", b"\x00", b"\x2a"]
    spec = _spec(steps=[{"wait": {"mem": "$0400", "equals": "$2a"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert mon.memory_read.call_count == 3


def test_wait_mem_timeout_reports_last_value():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.return_value = b"\x07"
    spec = _spec(steps=[{"wait": {"mem": "$0400", "equals": "$2a", "timeout": 0.2}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.time.sleep"):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert "was 7" in result.steps[0].detail and "wanted 42" in result.steps[0].detail


def test_assert_reg_unknown_register_fails_cleanly():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.registers.return_value = {"PC": 0x1234, "A": 0}
    spec = _spec(steps=[{"assert": {"reg": "q", "equals": 1}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is False and "no register" in result.steps[0].detail


def test_assert_reg_in_range_fail_branch():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.registers.return_value = {"PC": 0xC500}
    spec = _spec(steps=[{"assert": {"reg": "pc", "in_range": ["$0400", "$0500"]}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=launch)
    assert result.passed is False and "not in" in result.steps[0].detail


def test_autorun_false_load_never_finishes():
    s, _ = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(autorun=False, timeout=0.2, program="whatever.prg", steps=[])
    # First _wait_screen (READY gate) passes; second (load gate) never does.
    # Patching _wait_screen directly avoids the 45s/15s real-time deadlines.
    with patch("c64lib.testing._wait_screen",
               side_effect=[(True, "READY."), (False, "LOADING")]), \
         patch("c64lib.testing._prepare", return_value=(Path("x.prg"), None)), \
         pytest.raises(TestError, match="never finished loading"):
        run_test(spec, launch=launch)


def test_run_test_isolates_from_user_sessions():
    """FT4(a): documents the isolation contract — each run launches its own
    uniquely-named throwaway session and never attaches to (or stops) a
    user's session."""
    names = []

    def launch(model, name, headless, warp, cart=None, disk8=None):
        names.append(name)
        s, _ = _fake_session()
        return s

    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.Session") as S:
        r1 = run_test(_spec(), launch=launch)
        r2 = run_test(_spec(), launch=launch)
    S.attach.assert_not_called()
    assert names == [r1.session_name, r2.session_name]
    assert len(set(names)) == 2 and all(n.startswith("t") for n in names)


def _assert_step(mem_bytes, assert_arg):
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    mon.memory_read.return_value = mem_bytes
    spec = _spec(steps=[{"assert": assert_arg}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        return run_test(spec, launch=launch)


def test_assert_mem_equals_any():
    # FT6: either alternative passes
    r = _assert_step(bytes([81]), {"mem": "$0400", "equals_any": [[81], [98]]})
    assert r.passed is True
    r = _assert_step(bytes([98]), {"mem": "$0400", "equals_any": [[81], [98]]})
    assert r.passed is True
    r = _assert_step(bytes([32]), {"mem": "$0400", "equals_any": [[81], [98]]})
    assert r.passed is False
    # failure message shows actual and every accepted alternative
    assert "20" in r.steps[0].detail        # actual, hex
    assert "51" in r.steps[0].detail and "62" in r.steps[0].detail


def test_assert_mem_mask():
    # FT6: masked compare — e.g. ignore the reverse-video bit
    arg = {"mem": "$0400", "mask": {"and": 0x7F, "equals": [81]}}
    assert _assert_step(bytes([81]), arg).passed is True
    assert _assert_step(bytes([81 | 0x80]), arg).passed is True
    r = _assert_step(bytes([87]), arg)
    assert r.passed is False


def test_assert_mem_mask_multibyte():
    arg = {"mem": "$0400", "mask": {"and": "$7f", "equals": [81, 87]}}
    assert _assert_step(bytes([0xD1, 0x57]), arg).passed is True


def test_assert_mem_between():
    # FT6: single-byte range check
    arg = {"mem": "$0400", "between": {"min": 50, "max": 54}}
    assert _assert_step(bytes([50]), arg).passed is True
    assert _assert_step(bytes([54]), arg).passed is True
    r = _assert_step(bytes([55]), arg)
    assert r.passed is False
    assert "55" in r.steps[0].detail


def test_assert_mem_between_hex_bounds():
    arg = {"mem": "$0400", "between": {"min": "$30", "max": "$39"}}
    assert _assert_step(bytes([0x35]), arg).passed is True


def test_call_step_resolves_symbol_and_passes_registers(tmp_path):
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    lbl = tmp_path / "p.lbl"
    lbl.write_text("al C:2000 .sndinit\n")
    prog = tmp_path / "p.prg"
    prog.write_bytes(b"\x01\x08")
    spec = _spec(program=str(prog), autorun=True,
                 steps=[{"call": {"routine": "sndinit", "a": 5, "x": 1}}])
    fired = {"fired": True, "registers": {"PC": 0x0400, "A": 5}, "trap": 0x0400}
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._prepare", return_value=(prog, lbl)), \
         patch("c64lib.testing.call_routine", return_value=fired) as cr:
        result = run_test(spec, launch=launch)
    assert result.passed is True, result.steps
    assert cr.call_args.args[1] == 0x2000
    assert cr.call_args.kwargs["a"] == 5 and cr.call_args.kwargs["x"] == 1


def test_call_step_timeout_fails_with_detail():
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(steps=[{"call": {"routine": "$2000", "timeout": 1}}])
    out = {"fired": False, "registers": None, "trap": 0x0400}
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing.call_routine", return_value=out):
        result = run_test(spec, launch=launch)
    assert result.passed is False
    assert "never returned" in result.steps[0].detail


def test_sample_then_differs_passes():
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10]), bytes([12])]
    spec = _spec(steps=[{"sample": {"mem": "$D000", "as": "x0"}},
                        {"assert": {"mem": "$D000", "differs": "x0"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True, [st.detail for st in result.steps]
    assert "x0" in result.steps[0].detail


def test_sample_then_differs_fails_on_equal():
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10]), bytes([10])]
    spec = _spec(steps=[{"sample": {"mem": "$D000", "as": "x0"}},
                        {"assert": {"mem": "$D000", "differs": "x0"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is False
    assert "10" in result.steps[1].detail


def test_greater_and_less_than_samples():
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10]), bytes([12]), bytes([12])]
    spec = _spec(steps=[{"sample": {"mem": "$D000", "as": "x0"}},
                        {"assert": {"mem": "$D000", "greater_than": "x0"}},
                        {"assert": {"mem": "$D000", "less_than": "x0"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is False
    assert result.steps[1].ok is True and result.steps[2].ok is False


def test_unknown_sample_name_fails_actionably():
    s, mon = _fake_session()
    mon.memory_read.side_effect = [bytes([10])]
    spec = _spec(steps=[{"assert": {"mem": "$D000", "differs": "nope"}}])
    with patch("c64lib.testing.read_screen_text", return_value="READY."):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is False
    assert "no sample named" in result.steps[0].detail


def test_cart_spec_resolves_and_leaves_program_unset(tmp_path):
    """`cart:` resolves against the spec's own directory and never becomes a
    program (the runner's skip of the READY./autostart path is asserted by
    test_run_test_forwards_cart_and_skips_the_ready_gate)."""
    from c64lib.testing import load_test

    crt = tmp_path / "game.crt"
    crt.write_bytes(b"C64 CARTRIDGE   " + bytes(48))
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("cart: game.crt\nsteps:\n  - wait: {text: HI}\n")
    spec = load_test(spec_file)
    assert spec["cart"] == str(crt.resolve())
    assert spec.get("program") is None


def test_cart_and_program_are_mutually_exclusive(tmp_path):
    from c64lib.testing import TestError, load_test

    (tmp_path / "game.crt").write_bytes(b"C64 CARTRIDGE   " + bytes(48))
    (tmp_path / "program.s").write_text("nop\n")
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("cart: game.crt\nprogram: program.s\nsteps: []\n")
    with pytest.raises(TestError, match="cart.*program"):
        load_test(spec_file)


def test_missing_cart_file_is_named(tmp_path):
    from c64lib.testing import TestError, load_test

    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("cart: gone.crt\nsteps: []\n")
    with pytest.raises(TestError, match="gone.crt"):
        load_test(spec_file)


# --- the cart execution path -------------------------------------------------

def _crt(path: Path) -> Path:
    path.write_bytes(b"C64 CARTRIDGE   " + bytes(48))
    return path


def test_run_test_forwards_cart_and_skips_the_ready_gate(tmp_path):
    """A cart is mapped at power-on and boots straight into its own code: the
    runner hands it to launch(), never gates on READY., and autostarts nothing."""
    crt = _crt(tmp_path / "game.crt")
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(cart=str(crt), dir=str(tmp_path))
    with patch("c64lib.testing.read_screen_text", return_value="GAME OVER"), \
         patch("c64lib.testing._wait_screen") as waited:
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert launch.call_args.kwargs["cart"] == str(crt)
    waited.assert_not_called()          # no READY. gate for a cartridge
    mon.autostart.assert_not_called()   # and nothing to autostart


def test_run_test_without_cart_still_gates_on_ready(tmp_path):
    """The counterpart: a cart-less spec keeps the READY. gate it always had."""
    s, _ = _fake_session()
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen",
               return_value=(True, "READY.")) as waited:
        launch = Mock(return_value=s)
        run_test(_spec(), launch=launch)
    assert launch.call_args.kwargs["cart"] is None
    assert waited.called


def test_run_test_loads_cart_labels_when_present(tmp_path):
    """A cart's .lbl feeds symbols to until/poke steps, exactly as a program's does."""
    crt = _crt(tmp_path / "game.crt")
    (tmp_path / "game.lbl").write_text("al 00C000 .entry\n")
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([7])
    spec = _spec(cart=str(crt), dir=str(tmp_path),
                 steps=[{"assert": {"mem": "entry", "equals": 7}}])
    with patch("c64lib.testing.read_screen_text", return_value="X"):
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    assert mon.memory_read.call_args.args[0] == 0xC000   # symbol resolved


def test_run_test_rejects_a_spec_with_both_cart_and_program(tmp_path):
    """load_test rejects the pair, but a hand-built spec skips that layer: the
    runner must refuse it too rather than silently ignoring `program`."""
    crt = _crt(tmp_path / "game.crt")
    launch = Mock()
    spec = _spec(cart=str(crt), program="hello.prg", dir=str(tmp_path))
    with pytest.raises(TestError, match="cart.*program"):
        run_test(spec, launch=launch)
    launch.assert_not_called()          # refused before anything booted


def test_shared_launch_bypass_predicate_covers_cart_and_disk():
    """conftest's shared machine can serve neither a cart nor a disk (both are
    attached at power-on), nor another model."""
    from tests.conftest import _needs_own_emulator as own

    assert own("c64", "c64", {}) is False
    assert own("c64", "c64pal", {}) is True
    assert own("c64", "c64", {"cart": "g.crt"}) is True
    assert own("c64", "c64", {"disk8": "g.d64"}) is True


def test_prepare_cart_passes_a_crt_through_with_its_sibling_labels(tmp_path):
    from c64lib.testing import prepare_cart

    crt = _crt(tmp_path / "game.crt")
    assert prepare_cart(tmp_path, "game.crt") == (crt.resolve(), None)
    lbl = tmp_path / "game.lbl"
    lbl.write_text("al 000801 .start\n")
    assert prepare_cart(tmp_path, "game.crt") == (crt.resolve(), lbl.resolve())


def test_prepare_cart_resolves_relative_to_the_spec_dir(tmp_path, monkeypatch):
    """A spec is portable: `cart:` follows the spec's directory, not the cwd."""
    from c64lib.testing import prepare_cart

    specs = tmp_path / "specs"
    specs.mkdir()
    crt = _crt(specs / "game.crt")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert prepare_cart(specs, "game.crt")[0] == crt.resolve()
    # an already-absolute cart is not re-resolved against the spec dir
    assert prepare_cart(elsewhere, str(crt))[0] == crt.resolve()


# A builder reports `labels: None` when it assembled nothing (an all-binary
# EasyFlash manifest has no symbols, and an empty .lbl is a file that looks
# like a symbol table and is not one). Every fake here carries that case, so
# `prepare_cart` cannot go back to calling Path() on it.
@pytest.mark.parametrize("labels", ["out.lbl", None])
def test_prepare_cart_builds_a_source_cart(tmp_path, monkeypatch, labels):
    from c64lib import testing as testing_mod

    (tmp_path / "game.s").write_text("nop\n")
    seen = {}

    def fake_build_cart(source, cart_type="8k"):
        seen["source"], seen["cart_type"] = Path(source), cart_type
        return {"crt": str(tmp_path / "out.crt"),
                "labels": str(tmp_path / labels) if labels else None}

    monkeypatch.setattr(testing_mod, "build_cart", fake_build_cart)
    crt, lbl = testing_mod.prepare_cart(tmp_path, "game.s", "16k")
    assert seen["source"] == (tmp_path / "game.s").resolve()
    assert seen["cart_type"] == "16k"
    assert crt == tmp_path / "out.crt"
    assert lbl == (tmp_path / labels if labels else None)


@pytest.mark.parametrize("name", ["game.ef.yaml", "game.ef.yml"])
@pytest.mark.parametrize("labels", ["ef.lbl", None])
def test_prepare_cart_builds_an_easyflash_manifest(tmp_path, monkeypatch, name,
                                                   labels):
    from c64lib import testing as testing_mod

    (tmp_path / name).write_text("name: game\n")
    seen = {}

    def fake_build_easyflash(manifest):
        seen["manifest"] = Path(manifest)
        return {"crt": str(tmp_path / "ef.crt"),
                "labels": str(tmp_path / labels) if labels else None}

    monkeypatch.setattr(testing_mod, "build_easyflash", fake_build_easyflash)
    crt, lbl = testing_mod.prepare_cart(tmp_path, name)
    assert seen["manifest"] == (tmp_path / name).resolve()
    assert crt == tmp_path / "ef.crt"
    # An all-binary manifest merges no labels: the None has to survive the
    # hand-off, not become Path(None) — a TypeError mid-test-run.
    assert lbl == (tmp_path / labels if labels else None)


def test_prepare_cart_rejects_an_unknown_extension(tmp_path):
    from c64lib.testing import prepare_cart

    (tmp_path / "game.prg").write_bytes(b"\x01\x08")
    with pytest.raises(TestError, match=r"must be a \.crt"):
        prepare_cart(tmp_path, "game.prg")


# --- the disk execution path -------------------------------------------------

def _d64(path: Path) -> Path:
    """A stand-in image. Nothing on this path reads the bytes: prepare_disk
    dispatches on the suffix and the runner only forwards the path."""
    path.write_bytes(bytes(174848))
    return path


def test_disk_spec_resolves_and_leaves_program_unset(tmp_path):
    """`disk:` resolves against the spec's own directory, like `cart:`."""
    from c64lib.testing import load_test

    img = _d64(tmp_path / "game.d64")
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("disk: game.d64\nsteps:\n  - wait: {text: HI}\n")
    spec = load_test(spec_file)
    assert spec["disk"] == str(img.resolve())
    assert spec.get("program") is None


def test_disk_and_program_are_mutually_exclusive(tmp_path):
    """Both want the one autostart slot; a spec that sets both would have the
    disk win silently and the program never load."""
    from c64lib.testing import load_test

    _d64(tmp_path / "game.d64")
    (tmp_path / "program.s").write_text("nop\n")
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("disk: game.d64\nprogram: program.s\nsteps: []\n")
    with pytest.raises(TestError, match="disk.*program"):
        load_test(spec_file)


def test_disk_and_cart_are_mutually_exclusive(tmp_path):
    """A cartridge boots itself and nothing is autostarted, so a disk named
    alongside one would be attached and never started."""
    from c64lib.testing import load_test

    _d64(tmp_path / "game.d64")
    _crt(tmp_path / "game.crt")
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("disk: game.d64\ncart: game.crt\nsteps: []\n")
    with pytest.raises(TestError, match="disk.*cart"):
        load_test(spec_file)


def test_missing_disk_file_is_named(tmp_path):
    from c64lib.testing import load_test

    spec_file = tmp_path / "test.yaml"
    spec_file.write_text("disk: gone.d64\nsteps: []\n")
    with pytest.raises(TestError, match="gone.d64"):
        load_test(spec_file)


def test_is_disk_spec_parses_yaml_rather_than_sniffing_text(tmp_path):
    from c64lib.testing import is_disk_spec

    yes = tmp_path / "yes.yaml"
    yes.write_text("disk: game.d64\n")
    no = tmp_path / "no.yaml"
    no.write_text("# disk: game.d64\nsteps:\n  - key: \"disk:\"\n")
    assert is_disk_spec(yes) is True
    assert is_disk_spec(no) is False
    assert is_disk_spec(tmp_path / "nope.yaml") is False


def test_run_test_attaches_the_disk_and_autostarts_the_image(tmp_path):
    """A disk-booted program is autostarted like any other: the runner gates on
    READY., then autostarts the image itself (which issues LOAD"*",8,1)."""
    img = _d64(tmp_path / "game.d64")
    s, mon = _fake_session()
    launch = Mock(return_value=s)
    spec = _spec(disk=str(img), dir=str(tmp_path))
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen", return_value=(True, "READY.")):
        result = run_test(spec, launch=launch)
    assert result.passed is True
    assert launch.call_args.kwargs["disk8"] == str(img.resolve())
    assert mon.autostart.call_args.args[0] == img.resolve()


def test_run_test_rejects_a_spec_with_both_disk_and_program(tmp_path):
    """load_test rejects the pair, but a hand-built spec skips that layer."""
    img = _d64(tmp_path / "game.d64")
    launch = Mock()
    spec = _spec(disk=str(img), program="hello.prg", dir=str(tmp_path))
    with pytest.raises(TestError, match="disk.*program"):
        run_test(spec, launch=launch)
    launch.assert_not_called()          # refused before anything booted


def test_run_test_rejects_a_spec_with_both_disk_and_cart(tmp_path):
    img = _d64(tmp_path / "game.d64")
    crt = _crt(tmp_path / "game.crt")
    launch = Mock()
    spec = _spec(disk=str(img), cart=str(crt), dir=str(tmp_path))
    with pytest.raises(TestError, match="disk.*cart"):
        run_test(spec, launch=launch)
    launch.assert_not_called()


def test_prepare_disk_passes_an_image_through(tmp_path):
    from c64lib.testing import prepare_disk

    for name in ("game.d64", "game.d71", "game.d81"):
        img = _d64(tmp_path / name)
        assert prepare_disk(tmp_path, name) == img.resolve()


def test_prepare_disk_resolves_relative_to_the_spec_dir(tmp_path, monkeypatch):
    """A spec is portable: `disk:` follows the spec's directory, not the cwd."""
    from c64lib.testing import prepare_disk

    specs = tmp_path / "specs"
    specs.mkdir()
    img = _d64(specs / "game.d64")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert prepare_disk(specs, "game.d64") == img.resolve()
    # an already-absolute image is not re-resolved against the spec dir
    assert prepare_disk(elsewhere, str(img)) == img.resolve()


@pytest.mark.parametrize("name", ["game.disk.yaml", "game.disk.yml"])
def test_prepare_disk_builds_a_manifest(tmp_path, monkeypatch, name):
    from c64lib import testing as testing_mod

    (tmp_path / name).write_text("label: game\n")
    seen = {}

    def fake_build_disk(manifest, model="c64"):
        seen["manifest"], seen["model"] = Path(manifest), model
        return {"image": str(tmp_path / "game.d64")}

    monkeypatch.setattr(testing_mod, "build_disk", fake_build_disk)
    img = testing_mod.prepare_disk(tmp_path, name, model="c64pal")
    assert seen["manifest"] == (tmp_path / name).resolve()
    assert seen["model"] == "c64pal"
    assert img == tmp_path / "game.d64"


def test_prepare_disk_rejects_an_unknown_extension(tmp_path):
    from c64lib.testing import prepare_disk

    (tmp_path / "game.prg").write_bytes(b"\x01\x08")
    with pytest.raises(TestError, match=r"must be a \.d64"):
        prepare_disk(tmp_path, "game.prg")


def test_disk_autorun_false_waits_for_the_load_to_finish(tmp_path):
    """`autorun: false` means "load, don't RUN" for a disk exactly as it does
    for a program — and the load gate has to apply too, or the first `key`
    step types into a machine still pulling bytes off the serial bus."""
    from c64lib.testing import _loaded

    img = _d64(tmp_path / "game.d64")
    s, mon = _fake_session()
    spec = _spec(disk=str(img), dir=str(tmp_path), autorun=False)
    with patch("c64lib.testing.read_screen_text", return_value="READY."), \
         patch("c64lib.testing._wait_screen",
               return_value=(True, "READY.")) as waited:
        result = run_test(spec, launch=Mock(return_value=s))
    assert result.passed is True
    mon.autostart.assert_called_once_with(img.resolve(), run=False)
    # Two gates: the READY. prompt, then the load itself.
    assert len(waited.call_args_list) == 2
    assert waited.call_args_list[1].args[1] is _loaded


def test_disk_autorun_false_load_never_finishes(tmp_path):
    img = _d64(tmp_path / "game.d64")
    s, _ = _fake_session()
    spec = _spec(disk=str(img), dir=str(tmp_path), autorun=False, timeout=0.2)
    with patch("c64lib.testing._wait_screen",
               side_effect=[(True, "READY."), (False, "LOADING")]), \
         pytest.raises(TestError, match="never finished loading"):
        run_test(spec, launch=Mock(return_value=s))
