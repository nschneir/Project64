"""MCP parity for the cartridge verbs.

The repo's cardinal rule: every verb reachable from `c64 ...` is reachable as
an MCP tool with the same payload. These tests pin the payloads against the
CLI's (commit 413d21b) and sweep the whole `cart` group for missing tools.
"""

import inspect
import json
from unittest.mock import Mock, patch

import pytest

from c64lib import mcp_server
from c64lib.session import SessionError
from tests.conftest import cli_json
from tests.test_cartridge import chip_packet, make_crt
from tests.test_cli_cart import good_body
from tests.test_mcp_scaffold import call_tool, list_tools


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("C64_TOOLS_HOME", str(tmp_path))


@pytest.fixture
def crt(tmp_path):
    return make_crt(tmp_path, name="MCPCART",
                    chips=[chip_packet(0, 0x8000, good_body())])


def _registered_tool_names() -> list[str]:
    return [t.name for t in list_tools().tools]


def _fake_session():
    s = Mock()
    s.name, s.model, s.pid, s.port = "c64", "c64", 1, 6502
    mon = Mock()
    s.monitor.return_value.__enter__ = Mock(return_value=mon)
    s.monitor.return_value.__exit__ = Mock(return_value=False)
    return s, mon


# --- offline tools ----------------------------------------------------------

def test_cart_info_tool_matches_the_cli_payload(crt):
    from c64lib.cartridge import cart_info
    assert mcp_server.c64_cart_info(str(crt)) == cart_info(crt)


def test_cart_info_round_trips_through_the_mcp_server(crt):
    """Registered, and its payload survives JSON serialization."""
    err, out = call_tool("c64_cart_info", {"file": str(crt)})
    assert err is False
    assert out["name"] == "MCPCART" and out["mode"] == "8k"


def test_cart_verify_tool_reports_ok_and_reasons(crt, tmp_path):
    assert mcp_server.c64_cart_verify(str(crt)) == {
        "path": str(crt), "ok": True, "reasons": []}
    body = bytearray(good_body())
    body[4:9] = b"\xFF" * 5
    bad = make_crt(tmp_path, chips=[chip_packet(0, 0x8000, bytes(body))],
                   filename="bad.crt")
    res = mcp_server.c64_cart_verify(str(bad))
    assert res["ok"] is False and "CBM80" in res["reasons"][0]


def test_cart_verify_tool_reports_an_unparseable_file_as_data(tmp_path):
    """cart_verify raises on junk; the tool reports it the CLI's way instead."""
    junk = tmp_path / "junk.crt"
    junk.write_bytes(b"not a cartridge at all")
    res = mcp_server.c64_cart_verify(str(junk))
    assert res["ok"] is False and res["path"] == str(junk)
    assert res["error"] and "reasons" not in res


def test_cart_dump_tool_writes_the_window(crt, tmp_path):
    out = tmp_path / "w.bin"
    res = mcp_server.c64_cart_dump(str(crt), str(out), bank=0, window="lo")
    assert res == {"path": str(out), "bank": 0, "window": "lo", "bytes": 8192}
    assert out.read_bytes()[4:9] == bytes([0xC3, 0xC2, 0xCD, 0x38, 0x30])


def test_cart_build_tool_delegates_to_build_easyflash(tmp_path):
    manifest = tmp_path / "game.ef.yaml"
    manifest.write_text("banks: []\n", encoding="utf-8")
    with patch("c64lib.mcp_server.build_easyflash",
               return_value={"crt": "game.crt"}) as bef:
        assert mcp_server.c64_cart_build(str(manifest), output="out.crt") == {
            "crt": "game.crt"}
    (args, kwargs) = bef.call_args
    assert str(args[0]) == str(manifest) and kwargs == {"out": "out.crt"}


def test_cart_convert_tool_builds_the_cartconv_args(tmp_path):
    with patch("c64lib.mcp_server.run_cartconv", return_value="  done\n") as rc:
        res = mcp_server.c64_cart_convert("in.bin", "out.crt", cart_type="normal",
                                          name="DEMO")
    rc.assert_called_once_with(
        ["-i", "in.bin", "-o", "out.crt", "-t", "normal", "-n", "DEMO"])
    assert res == {"source": "in.bin", "output": "out.crt", "cartconv": "done"}


# --- live tool --------------------------------------------------------------

def test_cart_bank_reads_the_registers_and_releases():
    s, mon = _fake_session()
    mon.memory_read.return_value = bytes([0x07, 0x00, 0x87])
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = s
        err, out = call_tool("c64_cart_bank", {})
    assert err is False
    assert out == {"bank": 7, "de00": "$07", "de02": "$87", "mode": "16k",
                   "led": True}
    mon.memory_read.assert_called_once_with(0xDE00, 3)
    # an inspection command: it must never resume a halted machine
    mon.release.assert_called_once()
    mon.resume.assert_not_called()


def test_cart_bank_payload_matches_the_cli():
    """A regression pin, not a reproduction: the two front ends already agree.

    Both decoded $DE00/$DE02 with their own copy of the same literal mode
    table, so agreement was a coincidence maintained by hand. It is one
    library function now (`ops.easyflash_state`), and this holds the payloads
    together if either front end starts embellishing again.
    """
    from click.testing import CliRunner

    from c64lib.cli import main
    regs = bytes([0x07, 0x00, 0x86])          # 8k mode, LED on
    cli_s, cli_mon = _fake_session()
    cli_mon.memory_read.return_value = regs
    with patch("c64lib.cli.Session") as S:
        S.attach.return_value = cli_s
        r = CliRunner().invoke(main, ["--json", "cart", "bank"])
    assert r.exit_code == 0, r.output
    cli_payload = json.loads(r.output)
    mcp_s, mcp_mon = _fake_session()
    mcp_mon.memory_read.return_value = regs
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = mcp_s
        mcp_payload = mcp_server.c64_cart_bank()
    assert mcp_payload == {"bank": 7, "de00": "$07", "de02": "$86",
                           "mode": "8k", "led": True}
    assert mcp_payload == cli_payload


# --- run a .crt -------------------------------------------------------------

def test_run_a_crt_reboots_the_session_with_it_attached(crt):
    """A cartridge is mapped at power-on, so running one boots a fresh session
    with it attached instead of loading into the current one."""
    old, _ = _fake_session()
    new, _ = _fake_session()
    # `run` of a .crt is `ops.reboot_with_cart` on both front ends, so the
    # Session seam to patch is the library's, not this front end's.
    with patch("c64lib.ops.Session") as S:
        S.attach.return_value = old
        S.launch.return_value = new
        out = mcp_server.c64_run(str(crt))
    old.stop.assert_called_once()
    S.launch.assert_called_once_with(model="c64", name="c64", headless=True,
                                     warp=True, cart=str(crt.resolve()))
    assert out == {"cart": str(crt.resolve()), "session": "c64",
                   "model": "c64", "symbols": None}


def test_run_a_crt_with_no_session_boots_a_default_one(crt):
    with patch("c64lib.ops.Session") as S:
        S.attach.side_effect = SessionError("no session is running")
        S.launch.return_value = _fake_session()[0]
        err, out = call_tool("c64_run", {"source": str(crt)})
    assert err is False and out["cart"] == str(crt.resolve())
    S.launch.assert_called_once_with(model="c64", name=None, headless=True,
                                     warp=True, cart=str(crt.resolve()))


@pytest.mark.parametrize("boom", [SessionError("monitor is gone"),
                                  OSError("monitor is gone")])
def test_run_a_crt_reports_a_failed_stop_instead_of_downgrading(crt, boom):
    """A stop that fails must not be read as 'there was no session': relaunching
    under the no-session defaults would silently swap a c64pal 'snake' for an
    NTSC 'c64' while the real 'snake' is possibly still alive.

    OSError counts as a failed stop the same way the CLI's guard has it:
    stopping is kill() + unlink() of the registry record and socket, so a
    permission or filesystem failure leaves the old session exactly as alive.
    """
    old, _ = _fake_session()
    old.name, old.model = "snake", "c64pal"
    old.stop.side_effect = boom
    with patch("c64lib.ops.Session") as S:
        S.attach.return_value = old
        with pytest.raises(SessionError) as e:
            mcp_server.c64_run(str(crt))
    assert "snake" in str(e.value) and "monitor is gone" in str(e.value)
    S.launch.assert_not_called()


def test_run_a_crt_registers_its_label_file(crt):
    lbl = crt.with_suffix(".lbl")
    lbl.write_text("al C:8009 .cart_main\n", encoding="utf-8")
    new, _ = _fake_session()
    with patch("c64lib.ops.Session") as S:
        S.attach.return_value = _fake_session()[0]
        S.launch.return_value = new
        out = mcp_server.c64_run(str(crt))
    new.set_labels_path.assert_called_once_with(str(lbl))
    assert out["symbols"] == str(lbl)


def test_run_a_crt_payload_matches_the_cli_emit(crt):
    """Lockstep: the same scenario through the CLI and through MCP reports the
    same keys with the same values."""
    from click.testing import CliRunner

    from c64lib.cli import main
    with patch("c64lib.ops.Session") as S:
        S.attach.return_value = _fake_session()[0]
        S.launch.return_value = _fake_session()[0]
        r = CliRunner().invoke(main, ["--json", "run", str(crt)])
    assert r.exit_code == 0, r.output
    cli_payload = json.loads(r.output)
    with patch("c64lib.ops.Session") as S:
        S.attach.return_value = _fake_session()[0]
        S.launch.return_value = _fake_session()[0]
        mcp_payload = mcp_server.c64_run(str(crt))
    assert mcp_payload == cli_payload


def test_run_a_crt_failed_stop_message_matches_the_cli(crt):
    """One implementation, not two copies that happen to agree.

    Both front ends reach the same `ops.reboot_with_cart`, so the failed-stop
    wording cannot drift — which is why the two messages are compared against
    each other rather than against a literal. A literal here would just be a
    third copy of the string.
    """
    from click.testing import CliRunner

    from c64lib.cli import main

    def _wont_stop():
        s, _ = _fake_session()
        s.name, s.model = "snake", "c64pal"
        s.stop.side_effect = SessionError("monitor is gone")
        return s

    with patch("c64lib.ops.Session") as S:
        S.attach.return_value = _wont_stop()
        r = CliRunner().invoke(main, ["--json", "run", str(crt)])
    assert r.exit_code == 1, r.output
    cli_err = json.loads(r.output)["error"]
    with patch("c64lib.ops.Session") as S:
        S.attach.return_value = _wont_stop()
        with pytest.raises(SessionError) as e:
            mcp_server.c64_run(str(crt))
    assert str(e.value) == cli_err
    assert "snake" in cli_err and "monitor is gone" in cli_err


def test_run_names_crt_among_the_runnable_extensions(tmp_path):
    junk = tmp_path / "thing.txt"
    junk.write_text("nope", encoding="utf-8")
    with patch("c64lib.mcp_server.Session") as S:
        S.attach.return_value = _fake_session()[0]
        with pytest.raises(ValueError) as e:
            mcp_server.c64_run(str(junk))
    assert ".crt" in str(e.value)


# --- lockstep ---------------------------------------------------------------

def test_every_cart_cli_command_has_an_mcp_tool():
    """The repo's cardinal rule: CLI and MCP move in lockstep."""
    import click

    from c64lib.cli import main
    registered = _registered_tool_names()
    cart = main.commands["cart"]
    # click types Group.commands as dict[str, Command]; `cart` is a group.
    assert isinstance(cart, click.Group)
    for name in cart.commands:
        tool = f"c64_cart_{name.replace('-', '_')}"
        assert hasattr(mcp_server, tool), f"missing MCP tool {tool}"
        assert tool in registered, f"{tool} is not registered with the server"


def test_package_tool_accepts_the_cart_options():
    sig = inspect.signature(mcp_server.c64_package)
    for param in ("fmt", "cart_type", "wrap"):
        assert param in sig.parameters
    with patch("c64lib.mcp_server.package_program", return_value={}) as pp:
        mcp_server.c64_package("game.s", output="game.crt", fmt="crt",
                               cart_type="ultimax", wrap=True)
    kwargs = pp.call_args.kwargs
    assert kwargs["fmt"] == "crt" and kwargs["cart_type"] == "ultimax"
    assert kwargs["wrap"] is True


def test_package_tool_defaults_match_the_cli():
    """Default drift away from the CLI's --cart-type must fail a test. Both
    front ends pass the None sentinel through; packaging turns it into 8k
    inside a cartridge, which is what makes 'given outside one' detectable."""
    from c64lib.cli import package_cmd
    from c64lib.packaging import package_program

    cli_default = next(p.default for p in package_cmd.params
                       if p.name == "cart_type")
    mcp_default = inspect.signature(mcp_server.c64_package).parameters[
        "cart_type"].default
    assert mcp_default == cli_default is None
    with patch("c64lib.mcp_server.package_program", return_value={}) as pp:
        mcp_server.c64_package("game.s")
    kwargs = pp.call_args.kwargs
    assert kwargs["cart_type"] is None and kwargs["wrap"] is False
    assert kwargs["fmt"] is None
    # ...and the sentinel still means 8k where a cartridge is actually built
    with patch("c64lib.packaging.wrap_prg", return_value={}) as wp:
        package_program("game.prg", out="game.crt")
    assert wp.call_args.kwargs["cart_type"] == "8k"


# --- shared package option validation (CLI/MCP lockstep) --------------------

def _package_error(args: dict) -> str:
    err, out = call_tool("c64_package", args)
    assert err is True, out
    return out["raw"]


@pytest.fixture
def src(tmp_path):
    s = tmp_path / "game.s"
    s.write_text("        .byte 0\n", encoding="utf-8")
    return s


def test_package_tool_rejects_cart_type_outside_a_cartridge(src, tmp_path):
    """Silently ignoring --cart-type was a CLI bug; the fix lives in packaging
    so the MCP caller hears about it in the same words."""
    out = tmp_path / "x.d64"
    msg = _package_error({"source": str(src), "output": str(out),
                          "cart_type": "16k"})
    assert "--cart-type" in msg
    assert msg.endswith(cli_json(
        ["package", str(src), "-o", str(out), "--cart-type", "16k"],
        exit_code=1)["error"])


def test_package_tool_names_the_format_prg_crt_conflict(src, tmp_path):
    out = tmp_path / "x.crt"
    msg = _package_error({"source": str(src), "output": str(out), "fmt": "prg"})
    assert "--format prg" in msg and "cartridge" in msg
    assert msg.endswith(cli_json(
        ["package", str(src), "--format", "prg", "-o", str(out)],
        exit_code=1)["error"])


def test_package_tool_rejects_a_cartridge_named_as_a_disk(src, tmp_path):
    out = tmp_path / "x.d64"
    msg = _package_error({"source": str(src), "output": str(out), "fmt": "crt"})
    assert ".d64" in msg
    assert msg.endswith(cli_json(
        ["package", str(src), "--format", "crt", "-o", str(out)],
        exit_code=1)["error"])


def test_session_start_tool_accepts_a_cart():
    assert "cart" in inspect.signature(mcp_server.c64_session_start).parameters
    s, _ = _fake_session()
    with patch("c64lib.mcp_server.Session") as S:
        S.launch.return_value = s
        mcp_server.c64_session_start(cart="game.crt")
    assert S.launch.call_args.kwargs["cart"] == "game.crt"
