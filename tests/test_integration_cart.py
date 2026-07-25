"""Cartridge builds against the real toolchain, and boots on a real x64sc."""

import shutil
from pathlib import Path

import pytest

from c64lib.cart_build import build_cart, wrap_prg
from c64lib.cartridge import cart_info, cart_verify

needs_build = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("ca65", "ld65", "cartconv")),
    reason="needs the cc65 suite and VICE's cartconv",
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
    src.write_text(HELLO)
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
def test_ultimax_build_maps_romh_at_e000(tmp_path):
    src = tmp_path / "u.s"
    # No KERNAL under an Ultimax cart, so poke the screen directly.
    src.write_text(
        '.export cart_main\n'
        '.segment "CODE"\n'
        'cart_main:\n'
        '        lda #21\n'
        '        sta $0400\n'
        '        jmp cart_main\n'
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
def test_missing_cart_main_export_explains_itself(tmp_path):
    from c64lib.cartridge import CartError
    src = tmp_path / "bad.s"
    src.write_text('.segment "CODE"\nnope: rts\n')
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
        'mine:   jmp mine\n'
    )
    res = build_cart(src, cart_type="8k", title="OWN")
    assert cart_verify(res["crt"]) == []


@needs_build
def test_wrapping_a_basic_program_builds_a_bootable_cart(tmp_path):
    bas = tmp_path / "hello.bas"
    bas.write_text('10 print "wrapped basic ok"\n20 goto 20\n')
    res = wrap_prg(bas, cart_type="8k", title="WRAPBAS")
    assert res["kind"] == "basic" and res["load_addr"] == 0x0801
    assert cart_verify(res["crt"]) == []


@needs_build
def test_wrapping_an_assembly_program_uses_the_ml_path(tmp_path):
    src = tmp_path / "m.s"
    src.write_text(
        '.segment "LOADADDR"\n        .word $0801\n'
        '.segment "CODE"\n'
        'start:  lda #1\n        sta $0400\n        jmp start\n'
    )
    res = wrap_prg(src, cart_type="8k", title="WRAPML")
    assert res["kind"] == "ml"
    assert cart_verify(res["crt"]) == []
