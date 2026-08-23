"""Cartridge builds against the real toolchain, and boots on a real x64sc."""

import importlib.util
import os
import shutil
import time
from pathlib import Path

import pytest

from c64lib.build import build_asm
from c64lib.cart_build import build_cart, build_easyflash, cart_include_dir, wrap_prg
from c64lib.cartridge import cart_info, cart_verify
from tests.vice_helpers import PROGRAM_KINDS, PROGRAMS_DIR, example_programs

needs_build = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("ca65", "ld65", "cartconv")),
    reason="needs the cc65 suite and VICE's cartconv",
)

needs_vice = pytest.mark.skipif(
    not (shutil.which("x64sc") or os.environ.get("C64_TOOLS_X64SC")),
    reason="x64sc not installed",
)

# Tokenizing a .bas is petcat's job, and petcat is not in `needs_build`'s list:
# a machine with cc65 and cartconv but no petcat must skip these, not fail.
needs_petcat = pytest.mark.skipif(
    not (shutil.which("petcat") or os.environ.get("C64_TOOLS_PETCAT")),
    reason="petcat (VICE) not installed",
)

HELLO = """\
; Minimal cart-native program: print through CHROUT, then spin.
.export cart_main
.segment "CODE"
cart_main:
        ldx     #0
loop:   lda     msg,x
        beq     done
        jsr     $FFD2
        inx
        bne     loop
done:   jmp     done
msg:    .byte   "CART HELLO", $0D, $00
"""


@needs_build
@pytest.mark.parametrize("cart_type,size,mode", [
    ("8k", 8192, "8k"),
    ("16k", 16384, "16k"),
])
def test_native_build_produces_a_verifiable_crt(tmp_path, cart_type, size, mode):
    src = tmp_path / "hello.s"
    src.write_text(HELLO, encoding="utf-8")
    res = build_cart(src, cart_type=cart_type, title="HELLO")
    info = cart_info(res["crt"])
    assert info["mode"] == mode
    assert info["name"] == "HELLO"
    assert sum(c["size"] for c in info["chips"]) == size
    assert cart_verify(res["crt"]) == []
    assert res["free"] == size - res["bytes"]
    assert res["run"].startswith("x64sc -ntsc -cartcrt")
    # The raw ROM image is kept beside the .crt, not discarded with the tempdir.
    raw = Path(res["bin"])
    assert raw == Path(res["crt"]).with_suffix(".bin")
    assert raw.exists()
    assert raw.stat().st_size == size


@needs_build
def test_a_native_cart_build_pins_the_model_in_its_run_hint(tmp_path):
    """Cart-native code owns its boot sequence, so `--model` changes nothing
    about the image — but it does change which emulator the recipient runs,
    and a c64pal author was being handed `-ntsc`."""
    src = tmp_path / "hello.s"
    src.write_text(HELLO, encoding="utf-8")
    res = build_cart(src, out=tmp_path / "pal.crt", title="HELLO",
                     model="c64pal")
    assert res["run"].startswith("x64sc -pal -cartcrt")


@needs_build
def test_ultimax_build_maps_romh_at_e000(tmp_path):
    src = tmp_path / "u.s"
    # No KERNAL under an Ultimax cart, so poke the screen directly.
    src.write_text(
        '.export cart_main\n'
        '.segment "CODE"\n'
        'cart_main:\n'
        '        lda #21\n'
        '        sta $0400\n'
        '        jmp cart_main\n', encoding="utf-8"
    )
    res = build_cart(src, cart_type="ultimax", title="ULTI")
    info = cart_info(res["crt"])
    assert info["mode"] == "ultimax"
    assert info["chips"][0]["load_addr"] == "$E000"
    assert cart_verify(res["crt"]) == []
    assert Path(res["bin"]).stat().st_size == 0x2000
    # The reset vectors at $FFFA are never $FF, so a naive fill-tail scan would
    # call this five-instruction cart completely full.
    assert res["free"] > 0
    assert res["bytes"] + res["free"] == 0x2000


@needs_build
def test_16k_romh_data_does_not_charge_for_the_roml_fill(tmp_path):
    """One byte in ROMH used to make the whole ROML fill region count as used."""
    src = tmp_path / "romh.s"
    src.write_text(
        '.export cart_main\n'
        '.segment "CODE"\n'
        'cart_main: jmp cart_main\n'
        '.segment "ROMH"\n'
        'table:  .byte 42\n', encoding="utf-8"
    )
    res = build_cart(src, cart_type="16k", title="ROMH")
    # Boot stub + 3-byte program + 1 byte of ROMH: nowhere near the ~8 KB the
    # whole-image rstrip reported.
    assert 0 < res["bytes"] < 256
    assert res["free"] == 16384 - res["bytes"]
    assert cart_verify(res["crt"]) == []


@needs_build
@pytest.mark.parametrize("cart_type,size", [
    ("8k", 8192), ("16k", 16384), ("ultimax", 8192),
])
def test_bss_variables_link_into_ram(tmp_path, cart_type, size):
    """Mutable state goes in BSS, which must resolve to a RAM area and cost no
    image bytes — a cartridge cannot write to its own ROM."""
    src = tmp_path / "bss.s"
    src.write_text(
        '.export cart_main\n'
        '.segment "BSS"\n'
        'counter: .res 2\n'
        '.segment "CODE"\n'
        'cart_main:\n'
        '        inc counter\n'
        '        jmp cart_main\n', encoding="utf-8"
    )
    res = build_cart(src, cart_type=cart_type, title="BSS")
    assert cart_verify(res["crt"]) == []
    assert Path(res["bin"]).stat().st_size == size


@needs_build
def test_missing_cart_main_export_explains_itself(tmp_path):
    from c64lib.cartridge import CartError
    src = tmp_path / "bad.s"
    src.write_text('.segment "CODE"\nnope: rts\n', encoding="utf-8")
    with pytest.raises(CartError, match=r"\.export cart_main"):
        build_cart(src, cart_type="8k", title="BAD")


@needs_build
def test_own_startup_suppresses_the_generated_stub(tmp_path):
    """An author who writes their own STARTUP owns the boot sequence — and the
    build must not inject a second one (duplicate symbols would fail the link)."""
    src = tmp_path / "own.s"
    src.write_text(
        '.segment "STARTUP"\n'
        '        .word mine\n'
        '        .word mine\n'
        '        .byte $C3,$C2,$CD,$38,$30\n'
        'mine:   jmp mine\n', encoding="utf-8"
    )
    res = build_cart(src, cart_type="8k", title="OWN")
    assert cart_verify(res["crt"]) == []


@needs_build
@needs_petcat
def test_wrapping_a_basic_program_builds_a_bootable_cart(tmp_path):
    bas = tmp_path / "hello.bas"
    bas.write_text('10 print "wrapped basic ok"\n20 goto 20\n', encoding="utf-8")
    res = wrap_prg(bas, cart_type="8k", title="WRAPBAS")
    assert res["kind"] == "basic" and res["load_addr"] == 0x0801
    assert cart_verify(res["crt"]) == []


@needs_build
def test_wrapping_an_assembly_program_uses_the_ml_path(tmp_path):
    src = tmp_path / "m.s"
    src.write_text(
        '.segment "LOADADDR"\n        .word $0801\n'
        '.segment "CODE"\n'
        'start:  lda #1\n        sta $0400\n        jmp start\n', encoding="utf-8"
    )
    res = wrap_prg(src, cart_type="8k", title="WRAPML")
    assert res["kind"] == "ml"
    assert cart_verify(res["crt"]) == []


# The layout skills/6502-assembly documents and both reference programs use:
# a BASIC `10 SYS 2061` stub at $0801 ahead of the code.
CANONICAL_ASM = """\
        .segment "LOADADDR"
        .word   $0801
        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000
        .segment "CODE"
start:  lda     #1
        sta     $0400
        jmp     start
"""


@needs_build
def test_wrapping_a_sys_stub_assembly_program_runs_it_through_basic(tmp_path):
    """The canonical .s layout must not be jumped into directly.

    `jmp $0801` would land on the BASIC line-link bytes ($0B $08 $0A $00) and
    execute them as code — a silently dead cartridge that `cart_verify` still
    calls fine. The SYS stub has to be reached through the interpreter.
    """
    src = tmp_path / "canon.s"
    src.write_text(CANONICAL_ASM, encoding="utf-8")
    res = wrap_prg(src, cart_type="8k", title="CANON")
    assert res["kind"] == "basic"
    assert cart_verify(res["crt"]) == []
    # The embedded image must survive .incbin byte-for-byte: a wrong offset
    # here is invisible to every other assertion.
    body = build_asm(src, out_prg=tmp_path / "canon.prg").prg.read_bytes()[2:]
    assert body.startswith(bytes([0x0B, 0x08, 0x0A, 0x00, 0x9E]))
    assert body in Path(res["bin"]).read_bytes()


@needs_build
def test_a_built_prg_and_its_source_agree_on_the_wrap_kind(tmp_path):
    """Wrapping foo.s and wrapping the foo.prg it builds must not disagree."""
    src = tmp_path / "canon.s"
    src.write_text(CANONICAL_ASM, encoding="utf-8")
    prg = build_asm(src, out_prg=tmp_path / "canon.prg").prg
    from_source = wrap_prg(src, out=tmp_path / "a.crt", title="A")
    from_prg = wrap_prg(prg, out=tmp_path / "b.crt", title="B")
    assert from_source["kind"] == from_prg["kind"] == "basic"


@needs_build
def test_a_9000_byte_program_wraps_into_the_full_16k_window(tmp_path):
    """The 8k rejection points at --cart-type 16k, so 16k has to actually work.

    A 16K wrap gets one contiguous $8000-$BFFF area: binding the launcher to
    ROML only would cap it at 8K and make that hint a lie.

    Loaded at $2000, not $C000: the only copyable space at $C000 is the 4K
    below the I/O area, so no 9000-byte program can start there.
    """
    prg = tmp_path / "big.prg"
    body = bytes(range(256)) * 35 + bytes(40)       # 9000 bytes, not $FF-heavy
    assert len(body) == 9000
    prg.write_bytes(bytes([0x00, 0x20]) + body)     # loads at $2000 -> ml path
    res = wrap_prg(prg, cart_type="16k", title="BIG16")
    assert res["kind"] == "ml" and res["load_addr"] == 0x2000
    assert cart_verify(res["crt"]) == []
    assert Path(res["bin"]).stat().st_size == 0x4000
    assert body in Path(res["bin"]).read_bytes()
    # `free` must describe the whole 16K, not just ROML.
    assert res["bytes"] > 0x2000
    assert res["bytes"] + res["free"] == 0x4000


def write_banked_game(tmp_path):
    """A three-bank EasyFlash game: boot in bank 0 hi, main in bank 0 lo,
    and a routine in bank 1 that bank 0 reaches through bankcall."""
    (tmp_path / "boot.s").write_text('.include "cart.inc"\n', encoding="utf-8")
    (tmp_path / "main.s").write_text("""\
.include "cart.inc"
.segment "JUMPTAB"
        ef_entry cold                   ; entry 0 — where ef_start lands
.segment "CODE"
cold:   ef_call 1, 0                    ; call bank 1's entry 0
        lda #$2A
        sta $0506                       ; '*' = we came back from bank 1
here:   jmp here
""", encoding="utf-8")
    (tmp_path / "far.s").write_text("""\
.include "cart.inc"
.segment "JUMPTAB"
        ef_entry shout
.segment "CODE"
shout:  lda #$41                        ; 'A' — proof bank 1 executed
        sta $0505
        rts
""", encoding="utf-8")
    m = tmp_path / "game.ef.yaml"
    m.write_text("""\
name: BANKED
banks:
  0: {lo: main.s, hi: boot.s}
  1: {lo: far.s}
""", encoding="utf-8")
    return m


@needs_build
def test_cart_inc_assembles_into_a_banked_easyflash(tmp_path):
    res = build_easyflash(write_banked_game(tmp_path))
    assert res["cart_type"] == "easyflash"
    assert res["banks"] == [0, 1]
    assert cart_verify(res["crt"]) == []
    info = cart_info(res["crt"])
    assert info["hardware_name"] == "EasyFlash"
    # Bank 0 hi is the boot window and must survive cartconv's optimizer.
    assert any(c["bank"] == 0 and c["window"] == "hi" for c in info["chips"])
    # The mandated raw image is persisted beside the .crt, full 1 MB of it.
    raw = Path(res["bin"])
    assert raw == Path(res["crt"]).with_suffix(".bin")
    assert raw.exists()
    assert raw.stat().st_size == 1_048_576


@needs_build
def test_ef_bank_bss_links_into_ram(tmp_path):
    """`.segment "BSS"` must link in every EasyFlash window — including the
    boot window — resolve to RAM at $0A00, cost no image bytes, and in the
    boot window stop at the Ultimax RAM ceiling of $0FFF.
    """
    m = write_banked_game(tmp_path)
    # $0600 of BSS fills $0A00-$0FFF exactly, so this build links only while
    # the boot window's RAM area is that big — the address of `bootflag`
    # alone cannot say, since it sits at the area's start whatever the size.
    (tmp_path / "boot.s").write_text(
        '.include "cart.inc"\n'
        '.segment "BSS"\n'
        'bootflag: .res 1\n'
        'bootfill: .res $05FF\n', encoding="utf-8"
    )
    (tmp_path / "far.s").write_text("""\
.include "cart.inc"
.segment "JUMPTAB"
        ef_entry shout
.segment "BSS"
calls:  .res 2
.segment "CODE"
shout:  inc calls
        lda #$41                        ; 'A' — proof bank 1 executed
        sta $0505
        rts
""", encoding="utf-8")
    res = build_easyflash(m)
    assert cart_verify(res["crt"]) == []
    assert Path(res["bin"]).stat().st_size == 1_048_576
    from c64lib.symbols import load_labels
    labels = load_labels(res["labels"])
    assert 0x0A00 <= labels["b01lo_calls"] < 0x8000
    assert 0x0A00 <= labels["b00hi_bootflag"] < 0x1000    # Ultimax boot ceiling
    # The other side of the ceiling: one byte past $0FFF must not link. A boot
    # window handed the 16K-mode RAM size ($0A00-$7FFF) would take it, and the
    # BSS would resolve into ROM the Ultimax boot window cannot write.
    from c64lib.build import BuildError
    over = tmp_path / "over"
    over.mkdir()
    m_over = write_banked_game(over)
    (over / "boot.s").write_text(
        '.include "cart.inc"\n'
        '.segment "BSS"\n'
        'bootflag: .res $0601\n', encoding="utf-8"
    )
    with pytest.raises(BuildError, match="overflows memory area 'RAM'"):
        build_easyflash(m_over)


@needs_build
def test_the_window_report_is_keyed_like_the_merged_labels(tmp_path):
    """`windows` and the label prefixes name the same thing the same way: a
    report saying `0hi` beside a symbol called `b00hi_boot` reads as two
    different addressing schemes for one cartridge."""
    res = build_easyflash(write_banked_game(tmp_path))
    assert sorted(res["windows"]) == ["b00hi", "b00lo", "b01lo"]
    assert all(0 < n <= 8192 for n in res["windows"].values())


@needs_build
def test_a_short_raw_boot_window_is_refused(tmp_path):
    """The CPU takes RESET from $FFFC — the last words of bank 0 hi. A raw
    .bin shorter than the window leaves them $FF, so the machine jumps to
    $FFFF and nothing runs; cart_verify cannot see it because the reset vector
    it reads is the fill.
    """
    from c64lib.cartridge import CartError
    m = write_banked_game(tmp_path)
    (tmp_path / "stub.bin").write_bytes(b"\x00" * 64)
    m.write_text(
        m.read_text(encoding="utf-8").replace("hi: boot.s", "hi: stub.bin"), encoding="utf-8"
    )
    with pytest.raises(CartError, match="boot window must fill all"):
        build_easyflash(m)


@needs_build
def test_a_binary_only_manifest_writes_no_label_file(tmp_path):
    """Nothing was assembled, so there are no symbols: an empty .lbl is a file
    that looks like a symbol table and is not one."""
    boot = tmp_path / "boot.bin"
    boot.write_bytes(b"\xFF" * 8186 + b"\x00\xE0" * 3)   # vectors at $FFFA
    m = tmp_path / "blob.ef.yaml"
    m.write_text("name: BLOB\nbanks:\n  0: {hi: boot.bin}\n", encoding="utf-8")
    res = build_easyflash(m)
    assert res["labels"] is None
    assert not (tmp_path / "blob.lbl").exists()
    assert cart_verify(res["crt"]) == []


@needs_build
def test_merged_labels_are_bank_tagged(tmp_path):
    from c64lib.symbols import load_labels
    res = build_easyflash(write_banked_game(tmp_path))
    labels = load_labels(res["labels"])
    assert "b00lo_cold" in labels
    assert "b01lo_shout" in labels
    # Both banks link their own code to the same window, so the tags are what
    # keeps the two apart — the addresses themselves need not differ or agree.
    assert labels["b00lo_cold"] >= 0x8000 and labels["b01lo_shout"] >= 0x8000


@needs_build
def test_window_overflow_names_the_bank_and_the_amount(tmp_path):
    from c64lib.cartridge import CartError
    m = write_banked_game(tmp_path)
    (tmp_path / "fat.bin").write_bytes(b"\x00" * (8192 + 17))
    m.write_text(m.read_text(encoding="utf-8").replace("  1: {lo: far.s}",
                                       "  1: {lo: far.s, hi: fat.bin}"), encoding="utf-8")
    with pytest.raises(CartError, match="bank 1 hi .* 17 over"):
        build_easyflash(m)


def test_cart_inc_is_shipped_as_package_data():
    inc = cart_include_dir() / "cart.inc"
    assert inc.exists(), "cart.inc must ship with the package"
    text = inc.read_text(encoding="utf-8")
    assert "bankcall" in text and "ef_boot" in text


@pytest.mark.skipif(importlib.util.find_spec("hatchling") is None,
                    reason="hatchling (the build backend) not installed")
def test_the_built_distributions_carry_the_data_files(tmp_path):
    """The data directory is selected by `artifacts`, not by the VCS.

    hatchling picks files through git, so `*.lbl` in .gitignore silently
    dropped basic2.lbl out of the wheel — an installed package where
    `romdoc.rom_labels()` and `cart_include_dir()` resolve to nothing, with
    every test still green because the tests run from the source tree. The
    sdist is checked too: `artifacts` under `targets.wheel` alone left the
    sdist short, and a downstream rebuild from it produces exactly the broken
    wheel this file exists to prevent. Only inspecting real archives sees it.
    """
    import tarfile
    import zipfile

    # hatchling is the build backend (`[build-system] requires`), not a `dev`
    # dependency, so it is absent from the project venv a type checker
    # resolves against. The skipif above is the runtime guard; these say the
    # same thing to pyright. Do not "fix" by adding hatchling to `dev` —
    # installing the build backend into the runtime env to satisfy a checker
    # is the wrong trade.
    from hatchling.builders.sdist import SdistBuilder  # pyright: ignore[reportMissingImports]
    from hatchling.builders.wheel import WheelBuilder  # pyright: ignore[reportMissingImports]

    root = str(Path(__file__).resolve().parents[1])
    wheel = next(iter(WheelBuilder(root).build(directory=str(tmp_path))))
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
    assert "c64lib/data/cart/cart.inc" in names
    assert "c64lib/data/rom_labels/basic2.lbl" in names

    sdist = next(iter(SdistBuilder(root).build(directory=str(tmp_path))))
    with tarfile.open(sdist) as t:
        shipped = {n.split("/", 1)[-1] for n in t.getnames()}
    assert "src/c64lib/data/cart/cart.inc" in shipped
    assert "src/c64lib/data/rom_labels/basic2.lbl" in shipped


@needs_build
def test_the_launcher_fits_its_reserved_budget(tmp_path):
    """LAUNCHER_BYTES is what the fit check reserves before any tool runs.

    If the launcher outgrows it, wrap_prg accepts a program that then fails in
    ld65 with a raw memory-area overflow instead of the actionable rejection —
    so the constant has to be checked against the real assembled size.
    """
    from c64lib.cart_build import LAUNCHER_BYTES
    for kind, load_addr, prg in (
            ("basic", 0x0801, bytes([0x01, 0x08, 0x0B, 0x08, 0x0A, 0x00, 0x9E])
             + b"2061" + b"\x00\x00\x00"),
            ("ml", 0xC000, bytes([0x00, 0xC0, 0xA9, 0x01, 0x8D, 0x00, 0x04])),
    ):
        src = tmp_path / f"{kind}.prg"
        src.write_bytes(prg)
        res = wrap_prg(src, out=tmp_path / f"{kind}.crt", title=kind.upper())
        assert res["kind"] == kind and res["load_addr"] == load_addr
        launcher_only = res["bytes"] - (len(prg) - 2)
        assert 0 < launcher_only <= LAUNCHER_BYTES, (
            f"the {kind} launcher is {launcher_only} bytes, over the "
            f"{LAUNCHER_BYTES} the fit check reserves")


@needs_build
def test_a_program_in_the_old_rejection_band_now_wraps(tmp_path):
    """8000 bytes was rejected by the round 256-byte estimate and fits.

    Loaded at $2000: 8000 bytes from $C000 would run into the I/O area, which
    the launcher cannot copy through whatever the size estimate says.
    """
    prg = tmp_path / "band.prg"
    prg.write_bytes(bytes([0x00, 0x20]) + bytes(range(256)) * 31 + bytes(64))
    assert prg.stat().st_size == 8002
    res = wrap_prg(prg, cart_type="8k", title="BAND")
    assert cart_verify(res["crt"]) == []
    assert res["bytes"] <= 8192


# What the banked game leaves behind once the cross-bank call has round-tripped:
# 'A' from bank 1, '*' from bank 0 after control came back, and a bank register
# the trampoline restored to 0. ($DE00 is write-only on real hardware but reads
# back under VICE, which is the only reason it can be asserted here.)
_BANKED_STATE = {0x0505: 0x41, 0x0506: 0x2A, 0xDE00: 0x00}


def _read_banked_state(session, timeout=30.0):
    """Poll until bank 0 has written its 'we came back' marker, then report."""
    deadline = time.monotonic() + timeout
    while True:
        with session.monitor() as mon:
            try:
                state = {a: mon.memory_read(a, 1)[0] for a in _BANKED_STATE}
            finally:
                mon.resume()
        if state[0x0506] == 0x2A or time.monotonic() > deadline:
            return state
        time.sleep(0.5)


@needs_build
@needs_vice
@pytest.mark.vice
def test_cart_inc_boots_and_calls_across_banks(tmp_path):
    """The gate cart.inc exists for: power on a real x64sc with the banked
    cartridge attached and prove the whole boot chain ran.

    Every step here is a separate way the cartridge can be silently dead and
    still pass `cart_verify`: the CPU has to take RESET from bank 0 HI at
    $E000, copy the trampoline to $0900 while still in Ultimax mode, leave
    Ultimax through $DE02 before touching the KERNAL, reach bank 0's jump
    table at $9F00, and bank-switch to bank 1 and back from RAM.
    """
    from c64lib.session import Session
    res = build_easyflash(write_banked_game(tmp_path))
    session = Session.launch(name="cart-inc-banked", headless=True, warp=True,
                             cart=res["crt"])
    try:
        state = _read_banked_state(session)
    finally:
        session.stop()
    assert state == _BANKED_STATE


@needs_build
@pytest.mark.parametrize("index,fits", [(84, True), (85, False)])
def test_ef_call_rejects_an_entry_index_past_the_jump_table(tmp_path, index, fits):
    """The jump table is one page of 3-byte JMPs, so it holds 85 entries and
    the last valid *index* is 84. Index 85's JMP would spill 2 bytes past
    $9FFF — ld65 does catch that, but only as a raw memory-area overflow on
    the callee's bank, which names neither ef_call nor the index. The guard
    exists to fail at the call site instead.
    """
    from c64lib.build import BuildError
    m = write_banked_game(tmp_path)
    main = tmp_path / "main.s"
    main.write_text(
        main.read_text(encoding="utf-8").replace("ef_call 1, 0", f"ef_call 1, {index}"),
        encoding="utf-8",
    )
    if fits:
        build_easyflash(m)      # assembles; the callee simply has no such entry
        return
    with pytest.raises(BuildError, match="entry index above EF_MAX_ENTRY"):
        build_easyflash(m)


@needs_build
def test_ef_call_rejects_a_negative_entry_index(tmp_path):
    """The symmetric half of the bank guard: `ldx #(index * 3)` with a negative
    index assembles to a range error naming neither ef_call nor the index."""
    from c64lib.build import BuildError
    m = write_banked_game(tmp_path)
    main = tmp_path / "main.s"
    main.write_text(
        main.read_text(encoding="utf-8").replace("ef_call 1, 0", "ef_call 1, -1"), encoding="utf-8"
    )
    with pytest.raises(BuildError, match="entry index is negative"):
        build_easyflash(m)


# --- the end-to-end gate: reference cartridges that boot on a real x64sc ----

# Discovered, never listed: tests/test_integration_build.py autostarts the
# loadable share of the same library and tests/test_integration_runner.py boots
# the disks, all from the same predicate, so every example program is claimed
# by exactly one runner and a new cart directory joins this gate by existing.
# The partition is pinned below.
CART_PROGRAMS = example_programs("cart")


def _explain(name: str, result) -> str:
    failed = "\n".join(f"  {s.kind}: {s.detail}" for s in result.steps if not s.ok)
    return f"{name} failed:\n{failed}\nscreen:\n{result.screen}"


def test_program_kinds_partition_the_example_library():
    """No example program may fall between the three runners.

    A cart directory that no file claims is tested only by the CLI, which is
    exactly the silent gap a hardcoded parametrize list creates. Asserting each
    share is non-empty also catches a glob regression that would retire an
    end-to-end gate without failing anything.
    """
    every = {p.parent for p in PROGRAMS_DIR.glob("*/expect.txt")}
    shares = {k: set(example_programs(k)) for k in PROGRAM_KINDS}
    assert all(shares.values()), f"an empty share: { {k: len(v) for k, v in shares.items()} }"
    assert set().union(*shares.values()) == every
    assert sum(len(v) for v in shares.values()) == len(every)   # no overlap


@needs_build
@needs_vice
@pytest.mark.vice
@pytest.mark.parametrize("program", CART_PROGRAMS, ids=[d.name for d in CART_PROGRAMS])
def test_reference_cartridges_boot_and_pass(program):
    """Build the cart from the sources in its own directory, power on a real
    x64sc with the image attached, and assert the screen and the state bytes.

    These are the same directories `c64 test programs` discovers, so the
    published reference programs and the regression suite cannot drift apart.
    """
    from c64lib.testing import program_test, run_test

    result = run_test(program_test(program))
    assert result.passed, _explain(program.name, result)


@needs_build
@needs_petcat
@needs_vice
@pytest.mark.vice
def test_a_wrapped_basic_program_actually_runs_when_the_cart_boots(tmp_path):
    """A launcher cartridge is only correct if the wrapped program RUNS.

    `cart_verify` accepts any wrap carrying a CBM80 header and in-range
    vectors — which is exactly what two shipped bugs looked like: entering a
    tokenized BASIC image with `jmp $0801` executed the line-link bytes as
    code, and the 16K launcher left the BASIC interpreter banked out from
    under the program it had just started. Both produce a dead machine that
    every static check calls fine, so booting the image and reading the
    printed output is the only gate for this class of failure.
    """
    from c64lib.basic import tokenize
    from c64lib.machines import get_profile
    from c64lib.testing import run_test

    bas = tmp_path / "wrapped.bas"
    bas.write_text('10 print "wrap boot ok"\n20 goto 20\n', encoding="utf-8")
    prg = tokenize(bas, tmp_path / "wrapped.prg", get_profile("c64").basic_version)
    res = wrap_prg(prg, cart_type="8k", title="WRAPBOOT")
    assert res["kind"] == "basic"
    assert cart_verify(res["crt"]) == []
    result = run_test({
        "name": "wrap-boot", "machine": "c64", "timeout": 45, "autorun": True,
        "cart": res["crt"], "dir": str(tmp_path),
        "steps": [{"wait": {"text": "WRAP BOOT OK"}}],
    })
    assert result.passed, _explain("wrap-boot", result)
