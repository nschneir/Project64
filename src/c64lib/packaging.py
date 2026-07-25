"""One-step packaging: turn a source file into an artifact any VICE user can
run — a bare .prg, or a d64/d71/d81 disk image whose FIRST file is the
program (so `x64sc image.d64` autostarts it). Pure file operations; no
running session involved."""

from __future__ import annotations

import shutil
from pathlib import Path

from .basic import tokenize
from .build import build_asm
from .cart_build import build_cart, wrap_prg
from .disk import IMAGE_DRIVE_TYPES, create_image, put_file
from .machines import get_profile


class PackageError(Exception):
    pass


# Characters CBM DOS / c1541 treat specially in file names.
_CBM_SPECIAL = set('":,=*?')


def cbm_title(raw: str) -> str:
    """Normalize to a CBM-legal name: uppercase, 1-16 chars, PETSCII-printable."""
    t = str(raw).upper().strip()
    if not t:
        raise PackageError("title is empty")
    if len(t) > 16:
        raise PackageError(f"title {t!r} is {len(t)} chars; CBM names max out at 16")
    for ch in t:
        if not (0x20 <= ord(ch) <= 0x5D) or ch in _CBM_SPECIAL:
            raise PackageError(
                f"title {t!r}: {ch!r} won't survive as a CBM filename "
                "(use A-Z, 0-9, space, and simple punctuation)"
            )
    return t


def package_program(source, out=None, title: str | None = None,
                    model: str = "c64", fmt: str | None = None,
                    cart_type: str = "8k", wrap: bool = False) -> dict:
    """Build SOURCE (.s/.bas/.prg) and package it as OUT.

    The format comes from `fmt` when given, otherwise from OUT's extension:
    .prg (default), .d64/.d71/.d81 (an autostart-first disk image), or .crt
    (a bootable cartridge). The disk/prg formats return
    {"prg", "image", "title", "run"} — `run` is the exact command a recipient
    uses, `image` is None for .prg-only output; .crt returns the cartridge
    dict from cart_build. Existing outputs are overwritten."""
    source = Path(source)
    out = Path(out) if out is not None else None
    if fmt is None and out is not None and out.suffix.lower() == ".crt":
        fmt = "crt"
    if fmt == "crt":
        crt_out = out if out is not None else source.with_suffix(".crt")
        # A .s is cartridge-native code unless --wrap says otherwise; anything
        # else is an existing program the launcher stub has to copy down.
        if source.suffix.lower() == ".s" and not wrap:
            # build_cart takes no model: cart-native code owns its own boot
            # sequence and never touches the BASIC start address.
            return build_cart(source, out=crt_out, cart_type=cart_type,
                              title=title)
        return wrap_prg(source, out=crt_out, cart_type=cart_type, title=title,
                        model=model)
    if fmt not in (None, "prg"):
        raise PackageError(
            f"unsupported format {fmt!r} (use 'prg' or 'crt', or pick a disk "
            "image by output extension)")
    if wrap:
        raise PackageError(
            "wrap only applies to cartridges; pass --format crt or name a "
            ".crt output")
    profile = get_profile(model)
    t = cbm_title(title if title is not None else source.stem)
    out = out if out is not None else source.with_suffix(".prg")
    ext = out.suffix.lower()
    if ext == ".prg":
        image, prg_path = None, out
    elif ext in IMAGE_DRIVE_TYPES:
        image, prg_path = out, out.with_suffix(".prg")
    else:
        supported = ", ".join([".prg", *IMAGE_DRIVE_TYPES])
        raise PackageError(
            f"unsupported output type {ext!r} (use one of: {supported})")

    src_ext = source.suffix.lower()
    if src_ext == ".s":
        prg = build_asm(source, out_prg=prg_path,
                        basic_start=profile.basic_start).prg
    elif src_ext == ".bas":
        prg = tokenize(source, prg_path, profile.basic_version)
    elif src_ext == ".prg":
        if source.resolve() != prg_path.resolve():
            shutil.copyfile(source, prg_path)
        prg = prg_path
    else:
        raise PackageError(
            f"cannot package {src_ext!r} files (use .s, .bas, or .prg)")

    if image is not None:
        create_image(image, label=t.lower())     # -format overwrites = fresh image
        put_file(image, prg, t.lower())          # first file on a fresh image
    artifact = image if image is not None else prg
    # Pin the model in the run hint: stock x64sc boots its default (PAL)
    # machine, so both profiles pin their video standard (-ntsc / -pal).
    # vice_args is exactly what Session.launch passes.
    run = " ".join([profile.vice_emulator, *profile.vice_args, str(artifact)])
    return {"prg": str(prg), "image": str(image) if image else None,
            "title": t, "run": run}
