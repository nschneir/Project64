"""Declarative YAML test runner (spec §8).

A test boots a fresh warp session, optionally loads a program (autostart),
then executes wait/key/assert steps. The example programs (spec §8.1,
tests/programs/) run through the same engine via program_test(). Fail-fast;
the failure screen is captured for debugging.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .basic import tokenize
from .build import Area, build_asm
from .cart_build import build_cart, build_easyflash
from .disk import IMAGE_DRIVE_TYPES, build_disk
from .machines import get_profile
from .ops import (
    MEM_COND_KEYS,
    MEM_OPS,
    call_routine,
    disk_labels_path,
    parse_areas,
    run_until,
    session_ref,
    wait_for_idle,
)
from .screen import read_screen_text
from .session import Session
from .symbols import load_labels
from .text import ascii_to_petscii, screen_to_text


class TestError(Exception):
    __test__ = False  # not a pytest test class despite the Test* name


_STEP_KINDS = ("wait", "key", "assert", "poke", "until", "call", "sample")

#: required and allowed keys for the step kinds that take a mapping we
#: fully define (the older kinds predate validation and stay lenient).
_STEP_KEYS = {
    "poke": ({"addr"}, {"addr", "value", "values"}),
    "until": ({"ref"}, {"ref", "count", "timeout"}),
    "call": ({"routine"}, {"routine", "a", "x", "y", "timeout"}),
    "sample": ({"mem", "as"}, {"mem", "as", "width"}),
}

#: Manifest suffixes a spec's `disk:` may name instead of a ready-made image.
#: Both spellings, because a manifest is hand-written and YAML answers to two.
_DISK_MANIFEST_SUFFIXES = (".disk.yaml", ".disk.yml")


def _num(v) -> int:
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.startswith("$"):
        return int(s[1:], 16)
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s)


def _looks_numeric(v) -> bool:
    """Would this operand have been a sensible literal? Drives the comparator
    hint, and nothing else — a sample name that happens to be `0x1` is not a
    name anyone types by accident."""
    try:
        _num(v)
    except ValueError:
        return False
    return True


def _sample_width(arg: dict) -> int:
    """How many bytes a `sample:` step captures, defaulting to 1.

    1 or 2, and nothing else. 2 is the 6502's lo/hi word — the shape every
    16-bit counter on this machine has, because that is what `.word` emits and
    what `INC lo / BNE / INC hi` maintains — so a wider read would have no
    idiom behind it and no comparator to judge it with. The named width is
    recorded with the sample and the comparators read back at it, so a spec
    states the width once, at the step that decides what the value *is*.

    Validated at load time (so a bad width costs no emulator boot) and read
    back here at run time, which is also the check for a hand-built spec that
    never went through `load_test`.
    """
    raw = arg.get("width", 1)
    # `bool` is an `int` in Python, so `width: true` would otherwise pass
    # `isinstance(True, int)`, satisfy `True in (1, 2)`, and read ONE byte with
    # no width note — a typo silently downgraded to the default instead of
    # refused, which is the one outcome this validator exists to prevent.
    try:
        width = -1 if isinstance(raw, bool) else _num(raw)
    except ValueError:
        width = -1
    if width not in (1, 2):
        raise TestError(
            f"width must be 1 or 2, not {raw!r} — a two-byte sample reads the "
            "6502's lo/hi word at that address, and the comparison against it "
            "reads two bytes too")
    return width


def _width_note(width: int) -> str:
    """How a sampled read announces its width in a step's detail line — and
    silence at width 1, so every spec written before `width:` existed reports
    itself in exactly the words it always did."""
    return " (16-bit)" if width == 2 else ""


def _spec_path(spec_dir: str | Path, value: str | Path) -> Path:
    """A spec's `cart:`/`disk:` is relative to the spec's own directory, never
    the cwd, so a test runs the same from anywhere. An absolute path is left
    alone — joining it is a no-op, which keeps re-resolution harmless."""
    return (Path(spec_dir) / Path(value)).resolve()


def is_cart_spec(path: str | Path) -> bool:
    """True when the spec file at `path` declares a cartridge (`cart:`).

    The single definition of that question repo-wide: `program_test` uses it to
    accept an example directory that ships a cartridge instead of a program
    file, and the live-VICE helpers use it to split the example programs
    between the load-and-run runner and the boot-a-cartridge one. It parses the
    YAML rather than sniffing the text, so a commented-out `# cart:` or the
    word inside a step string cannot masquerade as a cartridge spec.

    A missing file is not a cartridge spec; unparseable YAML is an error,
    because `load_test` would fail on it moments later anyway.
    """
    return bool(_spec_key(path, "cart"))


def is_disk_spec(path: str | Path) -> bool:
    """True when the spec file at `path` declares a disk image (`disk:`).

    The disk twin of `is_cart_spec`, and used the same two ways: `program_test`
    accepts an example directory whose only artifact is an image, and the
    live-VICE helpers split the example library three ways so every directory
    is claimed by exactly one runner.
    """
    return bool(_spec_key(path, "disk"))


def _spec_key(path: str | Path, key: str):
    path = Path(path)
    if not path.exists():
        return None
    try:
        spec = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise TestError(f"{path}: test file is not valid YAML ({e})") from e
    return spec.get(key) if isinstance(spec, dict) else None


def load_test(path: str | Path) -> dict:
    """Load and validate one test spec, filling in the documented defaults.

    Paths in the spec (`program:`, `cart:`, `disk:`) are resolved against the
    spec file's own directory, which is also recorded in the returned spec's
    `dir` key so a later `prepare_cart`/`prepare_disk` can re-resolve from
    anywhere. A spec that sets `dir:` literally overrides that computed value —
    an escape hatch for generated specs, and a foot-gun otherwise, since
    `cart:` has already been resolved by then and only a hand-built spec's is
    left relative.
    """
    path = Path(path)
    spec = yaml.safe_load(path.read_text())
    if not isinstance(spec, dict):
        raise TestError(f"{path}: test file must be a YAML mapping")
    spec.setdefault("name", path.stem)
    spec.setdefault("machine", "c64")
    spec.setdefault("timeout", 30)
    spec.setdefault("autorun", True)
    spec.setdefault("steps", [])
    spec.setdefault("cart", None)
    spec.setdefault("cart_type", "8k")
    spec.setdefault("disk", None)
    spec.setdefault("areas", [])         # `--area NAME=START:SIZE` strings
    spec.setdefault("dir", str(path.parent.resolve()))  # what `cart:` is relative to
    # Every conflict first, then every existence check: a spec that names two
    # boot sources is contradictory whether or not both paths exist, and
    # "cart … not found" would send the reader off to create a file the spec
    # should not have named at all.
    _reject_spec_conflicts(f"{path}", spec)
    if spec["cart"]:
        cart = _spec_path(path.parent, spec["cart"])
        if not cart.exists():
            raise TestError(f"{path}: cart {cart} not found")
        spec["cart"] = str(cart)
    if spec["disk"]:
        disk = _spec_path(path.parent, spec["disk"])
        if not disk.exists():
            raise TestError(f"{path}: disk {disk} not found")
        spec["disk"] = str(disk)
    get_profile(spec["machine"])  # raises KeyError listing known models
    if spec.get("program"):
        prog = (path.parent / spec["program"]).resolve()
        if not prog.exists():
            raise TestError(f"{path}: program {prog} not found")
        spec["program"] = str(prog)
    for i, step in enumerate(spec["steps"], start=1):
        if (not isinstance(step, dict) or len(step) != 1
                or next(iter(step)) not in _STEP_KINDS):
            raise TestError(
                f"{path}: step {i} must be a single {'/'.join(_STEP_KINDS)} mapping"
            )
        kind = next(iter(step))
        if kind in _STEP_KEYS:
            required, allowed = _STEP_KEYS[kind]
            arg = step[kind]
            if not isinstance(arg, dict):
                raise TestError(f"{path}: step {i} ({kind}) must be a mapping")
            missing = required - arg.keys()
            unknown = arg.keys() - allowed
            if missing:
                raise TestError(
                    f"{path}: step {i} ({kind}) missing {sorted(missing)}")
            if unknown:
                raise TestError(
                    f"{path}: step {i} ({kind}) has unknown keys "
                    f"{sorted(unknown)} (allowed: {sorted(allowed)})")
            if kind == "poke" and not ({"value", "values"} & arg.keys()):
                raise TestError(
                    f"{path}: step {i} (poke) needs value or values")
            if kind == "sample":
                try:
                    _sample_width(arg)
                except TestError as e:
                    raise TestError(f"{path}: step {i} (sample) {e}") from None
    return spec


def _reject_spec_conflicts(where: str, spec: dict) -> None:
    """Every mutual-exclusion rule between `program:`, `cart:` and `disk:`, in
    one place so a caller can run them all before any per-key existence check.
    A contradictory spec should be told what contradicts, not which of its
    contradictory paths happens to be missing.
    """
    if spec.get("cart") and spec.get("program"):
        raise TestError(
            f"{where}: a spec sets either `cart` or `program`, not both — "
            "a cartridge boots itself and nothing is autostarted")
    _reject_areas_conflicts(where, spec)
    if spec.get("disk"):
        _reject_disk_conflicts(where, spec)


def _reject_areas_conflicts(where: str, spec: dict) -> None:
    """`areas:` is `--area`, and it rewrites the linker config only a `.s`
    `program:` goes through. Everything else it could be written beside would
    drop it silently: a cartridge brings its own memory map, a disk image is
    built by its own manifest, a `.bas` is tokenized and a `.prg` is loaded as
    it is. This is the single enforcing site: `_prepare` forwards `areas`
    straight to `build_asm` on the strength of it.
    """
    areas = spec.get("areas")
    if not areas:
        return
    if not isinstance(areas, list):
        # A bare `areas: ENGINE=$4000:$6000` is a string, and parse_areas
        # would iterate it one character at a time — "got 'E'" tells nobody
        # that the dash is what is missing.
        raise TestError(
            f"{where}: `areas:` is a YAML list of NAME=START:SIZE strings, "
            f"one per `- ` item (got {areas!r})")
    program = spec.get("program")
    if not program:
        raise TestError(
            f"{where}: `areas:` needs a `program:` — a cartridge brings its "
            "own memory map and a disk image is built by its own manifest, so "
            "areas beside one would link nothing")
    if Path(program).suffix.lower() != ".s":
        raise TestError(
            f"{where}: `areas:` applies to assembly programs only, but "
            f"`program:` is {Path(program).name} — a .bas is tokenized and a "
            ".prg is loaded as it is, so neither is linked (drop `areas:`, or "
            "name the .s source)")


def _reject_disk_conflicts(where: str, spec: dict) -> None:
    """A `disk:` spec owns the boot: it is attached at power-on and then
    autostarted. Neither companion can share that, and both failures would be
    silent — the disk branch wins in `run_test`, so a `program:` would never
    load and a `cart:` would boot instead of the image ever being started.
    """
    if spec.get("program"):
        raise TestError(
            f"{where}: a spec sets either `disk` or `program`, not both — "
            "a disk boots the image's first file and nothing else is "
            "autostarted")
    if spec.get("cart"):
        raise TestError(
            f"{where}: a spec sets either `disk` or `cart`, not both — a "
            "cartridge boots itself, so an attached disk would never be "
            "started")


def program_test(program_dir: str | Path) -> dict:
    """Synthesize a test spec from an example-program directory
    (program.bas/.s + expect.txt — see tests/programs/).

    A directory whose test.yaml declares a `cart:` or a `disk:` needs no
    program file: the cartridge, or the image's first file, is what runs. Every
    synthesized spec uses the same per-step timeout as a hand-written one (30s,
    `load_test`'s default).
    """
    program_dir = Path(program_dir)
    prog = next(
        (program_dir / n for n in ("program.bas", "program.s")
         if (program_dir / n).exists()),
        None,
    )
    expect = program_dir / "expect.txt"
    extra = program_dir / "test.yaml"
    has_image = is_cart_spec(extra) or is_disk_spec(extra)
    if (prog is None and not has_image) or not expect.exists():
        raise TestError(
            f"{program_dir}: not an example-program directory "
            "(needs program.bas/.s or a test.yaml with `cart:`/`disk:`, "
            "plus expect.txt)"
        )
    steps = [{"wait": {"text": ln}} for ln in expect.read_text().splitlines() if ln.strip()]
    if extra.exists():
        spec = load_test(extra)
        spec["name"] = program_dir.name
        # A program file beside a cart or a disk spec is that image's *source*,
        # not a second thing to autostart: promoting it would boot the wrong
        # artifact and pass or fail for the wrong reason.
        if prog is not None and not (spec.get("cart") or spec.get("disk")):
            spec["program"] = str(prog.resolve())
        spec["steps"] = steps + spec["steps"]   # expect lines still gate first
        return spec                             # timeout: load_test's default
    # `prog` is not None on this path and the ignore is a checker limitation,
    # not a papered-over hole: reaching here means `extra` does not exist, and
    # `_spec_key` answers None for a missing file, so `has_image` is False —
    # and with `has_image` False the guard above has already raised for a
    # missing program file. Pyright cannot carry a Path.exists() result from
    # one call to another, so it cannot see that `has_image` and this branch
    # exclude each other.
    return {"name": program_dir.name, "machine": "c64", "timeout": 30,
            "autorun": True,
            "program": str(prog.resolve()),  # pyright: ignore[reportOptionalMemberAccess]
            "steps": steps,
            "dir": str(program_dir.resolve())}


@dataclass
class StepResult:
    index: int
    kind: str
    ok: bool
    detail: str


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class despite the Test* name
    name: str
    machine: str
    passed: bool
    steps: list[StepResult]
    elapsed: float
    screen: str
    session_name: str = ""
    #: Non-fatal notes about the run itself rather than about a step — today
    #: only a staleness guard waived by `allow_stale`. Always in `to_dict`, so
    #: a harness can read the key whether or not anything was waived.
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "machine": self.machine, "passed": self.passed,
            "elapsed": self.elapsed,
            "steps": [{"index": s.index, "kind": s.kind, "ok": s.ok,
                       "detail": s.detail} for s in self.steps],
            "screen": self.screen,
            "warnings": list(self.warnings),
        }


def _sibling_labels(artifact: Path) -> Path | None:
    """The `<stem>.lbl` beside `artifact`, or None — the sibling symbol table a
    ready-made artifact carries, and the same shape `cart:`/`disk:` look for."""
    lbl = artifact.with_suffix(".lbl")
    return lbl if lbl.exists() else None


def _prepare(program: str, profile,
             areas: Sequence[Area] = ()) -> tuple[Path, Path | None]:
    """Build/tokenize the program; returns (prg, label file or None).

    `areas` is the spec's `areas:`, already parsed — the same fixed-address
    segments `c64 build --area` links, and reaching only the `.s` branch.
    `areas` beside a `.bas`/`.prg` program is rejected before anything boots,
    by `_reject_areas_conflicts`; it is not silently dropped here.
    """
    src = Path(program)
    ext = src.suffix.lower()
    if ext == ".prg":
        # Same rule as `cart:` and `disk:`: a sibling .lbl of the same stem is
        # this program's symbol table, silently skipped when it is not there.
        # Without it a `.prg` spec resolved no symbols at all, and every
        # `until: {ref: …}` failed with an empty known-list. Whether that pair
        # is consistent is `_reject_stale_prg_labels`' question, asked before
        # the machine boots.
        return src, _sibling_labels(src)
    if ext == ".bas":
        return tokenize(src, src.with_suffix(".prg"), profile.basic_version), None
    if ext == ".s":
        out = build_asm(src, basic_start=profile.basic_start, areas=areas)
        return out.prg, out.labels
    raise TestError(
        f"cannot run {ext!r} programs (a spec's `program:` is a .bas, .s, or "
        ".prg; a cartridge goes in `cart:` instead — .crt, .s, or .ef.yaml)")


def _stamp(mtime: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))


def _gate_stale(note: str, remedy: str, allow_stale: bool,
                warnings: list[str]) -> None:
    """Refuse a staleness `note`, or record it as a warning under `allow_stale`.

    The override exists because an mtime is evidence, not proof: `cp -r`
    without `-p` restamps a whole working tree, so an ordinary copy of a
    perfectly consistent pair can trip either guard with no way past it. It
    warns rather than going quiet — a guard that can be waived in silence is
    one nobody notices they waived.

    `remedy` is a whole sentence, ending in its own full stop: a `.prg`'s ends
    in an alternative ("or delete p.lbl…"), and continuing that sentence here
    would attach the continuation to the wrong clause.
    """
    if allow_stale:
        warnings.append(f"staleness allowed: {note}")
        return
    raise TestError(f"{note} {remedy} To test the artifact as it is, allow the "
                    "staleness explicitly (--allow-stale, or allow_stale=true).")


def _reject_stale_disk_labels(image: Path, labels: Path, allow_stale: bool,
                              warnings: list[str]) -> None:
    """Refuse a disk image older than the sibling `.lbl` it takes symbols from.

    Rebuilding the program without repackaging the image is the whole failure:
    the runner resolves fresh addresses against stale bytes and the spec fails
    on a plausible wrong value (`mem $414b = 4a != 00`) that says nothing about
    the artifact being the wrong one.

    Only the sibling `<stem>.lbl` is checked, because only it can go stale on
    its own — it comes from a separate command (`c64 build`, `c64 package`).
    `c64 disk build`'s `<stem>.<cbm-name>.lbl` copies are written immediately
    *after* the image they were copied for, so they are newer by milliseconds
    on every successful build and comparing them would reject working images.
    """
    if labels != image.with_suffix(".lbl"):
        return
    img_at, lbl_at = image.stat().st_mtime, labels.stat().st_mtime
    if lbl_at <= img_at:
        # Equal is not stale. Only a label file strictly later than the image
        # is evidence the program was rebuilt after being packaged; a tie is
        # what a shared or coarse timestamp looks like (two writes inside one
        # clock tick, a copy that carried both stamps over), and refusing it
        # would cost a working image for no signal.
        return
    _gate_stale(
        f"{image.name} predates its symbols: the image is dated "
        f"{_stamp(img_at)} and {labels.name} {_stamp(lbl_at)}, so every symbol "
        f"this spec names would resolve against a program the image does not "
        f"contain.",
        f"Rebuild the image (c64 package <source> -o {image.name}, or "
        "c64 disk build) and run the test again.", allow_stale, warnings)


#: How far apart a ready-made artifact and its sibling `.lbl` may be stamped and
#: still count as one act of writing — a build, a copy, a checkout, an unpacked
#: archive — in whichever order the two files happened to land. `ld65 -Ln`
#: finishes a `.prg` and its labels ~60 µs apart, `cp p.lbl p.prg` reverses that
#: order for nothing, the two cartridge builders disagree about which of the
#: `.crt`/`.lbl` pair they write last (see `_reject_stale_cart_labels`), and a
#: slow copy of a big tree can space any pair by seconds. The failures worth
#: refusing separate the pair by minutes to days, so a minute of grace buys its
#: false-positive immunity for no signal it gives up.
_LABELS_GRACE = 60.0


def _reject_far_apart_labels(artifact: Path, labels: Path, what: str,
                             remedy: str, allow_stale: bool,
                             warnings: list[str]) -> None:
    """Refuse a ready-made artifact and its sibling `.lbl` stamped far apart.

    The one comparison both ready-made routes make — a `.prg` `program:` and a
    `.crt` `cart:` — because both fail the same way and on the same evidence:
    either file can be the one that was replaced alone, so the gap is judged in
    both directions and the order is not judged at all. `what` is the artifact's
    noun in the message ("program", "cartridge") and `remedy` a whole sentence
    ending in its own full stop, per `_gate_stale`.

    The `disk:` guard does not come through here on purpose: its `.lbl` is
    written by a *different* command from the image (`c64 build`, `c64 package`),
    so for it the order alone is evidence and any label file strictly newer is
    refused, with no grace window to hide behind.
    """
    a_at, lbl_at = artifact.stat().st_mtime, labels.stat().st_mtime
    if abs(a_at - lbl_at) <= _LABELS_GRACE:
        return
    dated = (f"the {what} is dated {_stamp(a_at)} and {labels.name} "
             f"{_stamp(lbl_at)}")
    if a_at > lbl_at:
        note = (f"{artifact.name} is newer than its symbols: {dated}, so every "
                f"symbol this spec names would resolve against the {what} "
                f"{labels.name} describes, which is not this one.")
    else:
        note = (f"{artifact.name} predates its symbols: {dated}, so every "
                f"symbol this spec names would resolve against a later {what} "
                f"than the one this spec loads.")
    _gate_stale(note, remedy, allow_stale, warnings)


def _reject_stale_prg_labels(prg: Path, labels: Path, allow_stale: bool,
                             warnings: list[str]) -> None:
    """Refuse a ready-made `.prg` and a sibling `.lbl` written far apart.

    The disk guard's failure one artifact down — symbols that do not describe
    the bytes — but symmetric, because for a program pair either file can be
    the one that was replaced alone: a `.prg` copied in over labels nobody
    regenerated, or a `.lbl` copied in from a build whose `.prg` went somewhere
    else. Both resolve every `ref:` this spec names against a program that is
    not the one loaded, and both used to do it in silence.

    What the *order* cannot decide is anything inside `_LABELS_GRACE`:
    `build_asm` is the only writer here of both files, and its `ld65 -Ln` emits
    the `.lbl` microseconds after the `.prg` it describes — so "labels newer"
    is what every successful build looks like, and which landed first is an
    accident of the tool. Only a real gap is evidence, in either direction,
    because plenty of in-tree commands write one side of the pair alone:
    `c64 basic tokenize` and `c64 disk get` land a bare `.prg`, `c64 package`
    tokenizes a `.bas` or copies a `.prg` without writing any labels, and a
    `c64 cart build` of `game.crt` writes `game.bin` and `game.lbl` and no
    `.prg` at all. That last one is refused here in the "predates" direction
    when a `game.prg` sits beside it — correctly, since those labels describe
    the cartridge link and not the `.prg`.

    Only a `.prg` `program:` reaches this: a `.s` is linked by the run itself,
    pair and all, and a `.bas` is tokenized with no label file to disagree
    with.
    """
    _reject_far_apart_labels(
        prg, labels, "program",
        "Rebuild the pair together (c64 build <source>) and run the test "
        f"again, or delete {labels.name} to run without symbols.",
        allow_stale, warnings)


def _reject_stale_cart_labels(crt: Path, labels: Path, allow_stale: bool,
                              warnings: list[str]) -> None:
    """Refuse a ready-made `.crt` and a sibling `.lbl` written far apart.

    The `.prg` guard one artifact over, and symmetric for the same reason: a
    cartridge relinked without the `.crt` being refreshed, or a `.crt` copied in
    over labels nobody regenerated, both resolve every `ref:` this spec names
    against a link that is not the one mapped at power-on.

    Order is no evidence here at all, which is why this cannot be the disk
    guard's bare comparison. Measured on this tree: `c64 package game.s -o
    game.crt` (`build_cart`) writes the `.lbl` and then the `.crt` ~3 ms later,
    because `cartconv` runs after `ld65`; `c64 cart build game.ef.yaml`
    (`build_easyflash`) writes the `.crt` and then merges the per-window labels
    into the `.lbl` ~0.6 ms later. The two builders disagree about which file
    lands last, so "labels newer than the cartridge" is both what an EasyFlash
    build looks like and what a stale pair looks like — only a gap no single
    command could produce separates them.

    Only a `.crt` `cart:` reaches this: a `.s` or an `.ef.yaml` is built by the
    run itself, labels and all, and its pair cannot disagree. The one command
    that writes a `.crt` alone and leaves the labels *valid* is
    `c64 cart convert game.bin game.crt` — same image, same addresses — so a
    conversion run long after the build is judged stale when it is not, and
    `--allow-stale` is the answer for it as it is for a restamping `cp -r`.
    """
    _reject_far_apart_labels(
        crt, labels, "cartridge",
        "Rebuild the cartridge (c64 cart build <manifest>, or c64 package "
        f"<source> -o {crt.name}) and run the test again, or delete "
        f"{labels.name} to run without symbols.", allow_stale, warnings)


def prepare_cart(spec_dir: str | Path, cart: str | Path,
                 cart_type: str = "8k") -> tuple[Path, Path | None]:
    """Resolve a spec's `cart:` to a .crt plus its label file.

    `cart` is taken relative to `spec_dir` (the directory holding the spec), so
    the helper is self-sufficient whether it is handed a raw `cart:` value or a
    path `load_test` already resolved. A .crt is used as-is; a .s is built as a
    single-region cartridge and an .ef.yaml manifest as an EasyFlash image, so
    a reference program can live in source and still be regression-covered.
    """
    cart = _spec_path(spec_dir, cart)
    suffix = "".join(cart.suffixes[-2:]).lower()
    if cart.suffix.lower() == ".crt":
        lbl = cart.with_suffix(".lbl")
        return cart, (lbl if lbl.exists() else None)
    if suffix.endswith(".ef.yaml") or suffix.endswith(".ef.yml"):
        res = build_easyflash(cart)
    elif cart.suffix.lower() == ".s":
        res = build_cart(cart, cart_type=cart_type)
    else:
        raise TestError(
            f"{cart}: a test cart must be a .crt, a .s, or an .ef.yaml manifest")
    # `labels` is None when the build assembled nothing to make symbols out of
    # — an all-binary EasyFlash manifest — and Path(None) is a TypeError in the
    # middle of a test run, not a missing symbol table.
    return Path(res["crt"]), (Path(res["labels"]) if res["labels"] else None)


def prepare_disk(spec_dir: str | Path, disk: str | Path,
                 model: str = "c64") -> Path:
    """Resolve a spec's `disk:` to an image, taken relative to `spec_dir`.

    A .d64/.d71/.d81 is used as-is; a .disk.yaml manifest is built first, so a
    reference program can live in source and still be regression-covered.

    No label file comes back, unlike `prepare_cart`, because a disk can hold
    several assembled programs and there is no one symbol table to return.
    `build_disk` does now keep them: each `.s` entry's `.lbl` is copied beside
    the image as `<image-stem>.<cbm-name>.lbl` (its `labels` key maps CBM name
    to path), so a disk spec that needs symbols for `until`/`poke` steps can
    load the one it wants instead of rebuilding the program itself.
    """
    disk = _spec_path(spec_dir, disk)
    name = disk.name.lower()
    if disk.suffix.lower() in IMAGE_DRIVE_TYPES:
        return disk
    if name.endswith(_DISK_MANIFEST_SUFFIXES):
        return Path(build_disk(disk, model=model)["image"])
    raise TestError(
        f"{disk}: a test disk must be a .d64/.d71/.d81 or a .disk.yaml manifest")


def _screen(session) -> str:
    with session.monitor() as mon:
        try:
            return read_screen_text(mon, session.profile)
        finally:
            mon.release()          # preserve run/stop state (an until step
                                   # deliberately leaves the machine stopped)


def _wait_screen(session, pred, timeout: float) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    text = ""
    while time.monotonic() < deadline:
        text = _screen(session)
        if pred(text):
            return True, text
        time.sleep(0.3)
    return False, text


def _loaded(text: str) -> bool:
    return "LOADING" in text and text.rfind("READY.") > text.rfind("LOADING")


def _do_step(session, kind: str, arg, default_timeout: float,
             labels: dict[str, int] | None = None,
             captures: dict[str, tuple[int, int]] | None = None
             ) -> tuple[bool, str]:
    labels = labels or {}
    captures = captures if captures is not None else {}

    def _addr(v) -> int:
        # symbols, symbol+offset, and @row,col all work in step addresses;
        # @row,col follows the machine's live screen base. One resolver
        # (ops.session_ref) serves this runner and both front ends.
        # `labels` is never None here, so no label file is re-read.
        return session_ref(session, v, labels)

    if kind == "sample":
        addr = _addr(arg["mem"])
        width = _sample_width(arg)
        with session.monitor() as mon:
            try:
                data = mon.memory_read(addr, width)
            finally:
                mon.release()
        val = int.from_bytes(data, "little")
        captures[str(arg["as"])] = (val, width)
        return True, (f"sampled mem ${addr:04x}{_width_note(width)} = {val} "
                      f"as {arg['as']!r}")

    if kind == "key":
        # `ascii_to_petscii` directly, NOT `ops.key_type` — so a `\n` in a
        # spec is decoded by YAML or not at all, and never a second time here.
        # Deliberate: `key_type`'s escape decoding exists because a shell
        # argument cannot carry a real newline, and a YAML scalar can. Measured
        # with this build's pyyaml: `key: "run\n"` (the spelling docs/cli.md
        # documents) already arrives as a real newline, which maps to RETURN,
        # while `key: 'run\n'` arrives as a backslash and an n — which is what
        # single quotes ASK for in YAML. Decoding again here would make the
        # single-quoted form mean something YAML says it does not, and it would
        # leave no way to type a literal backslash at all. It also matches the
        # `program:` side, where `basic type` types its text literally.
        with session.monitor() as mon:
            try:
                mon.keyboard_feed(ascii_to_petscii(str(arg)))
            finally:
                mon.release()
        return True, f"typed {arg!r}"

    if kind == "poke":
        addr = _addr(arg["addr"])
        vals = arg["values"] if "values" in arg else [arg["value"]]
        data = bytes(_num(v) for v in vals)
        with session.monitor() as mon:
            try:
                mon.memory_write(addr, data)
            finally:
                mon.release()  # a stopped machine STAYS stopped for the next
        return True, f"poked {len(data)} byte(s) at ${addr:04x}"  # until step

    if kind == "call":
        timeout = arg.get("timeout", default_timeout)
        addr = _addr(arg["routine"])
        out = call_routine(session, addr,
                           a=arg.get("a"), x=arg.get("x"), y=arg.get("y"),
                           timeout=timeout)
        if not out["fired"]:
            return False, (f"call ${addr:04x}: never returned in {timeout}s "
                           "(machine left running)")
        r = out["registers"]
        return True, (f"call ${addr:04x} returned: "
                      f"A={r.get('A', 0):02x} X={r.get('X', 0):02x} "
                      f"Y={r.get('Y', 0):02x} (machine stopped at trap)")

    if kind == "until":
        timeout = arg.get("timeout", default_timeout)
        count = int(arg.get("count", 1))
        addr = _addr(arg["ref"])
        out = run_until(session, addr, timeout=timeout, count=count)
        if out["registers"] is None:
            return False, (f"until ${addr:04x}: reached {out['reached']}/{count}"
                           f" in {timeout}s (machine left running)")
        return True, f"until ${addr:04x} x{count} (machine stopped there)"

    if kind == "wait":
        timeout = arg.get("timeout", default_timeout)
        if "text" in arg or "screen" in arg:
            # `screen` is the assert spelling; both verbs accept both so a
            # copied step survives a verb change.
            want = str(arg["text"] if "text" in arg else arg["screen"])
            base = _screen(session).count(want) if arg.get("since") else 0
            ok, _ = _wait_screen(session, lambda t: t.count(want) > base, timeout)
            return ok, (f"text {want!r} seen" if ok
                        else f"text {want!r} not seen in {timeout}s")
        if "mem" in arg:
            # A `@row,col` reference is resolved against the machine's live
            # screen base, and the reset `autostart` performs leaves the VIC
            # registers unreadable for a moment ($D018 reads 0, putting the
            # cell in zero page). Resolved once, that address is polled for
            # the whole timeout and the wait can never fire — so re-resolve
            # per poll. It also follows a screen the program relocates.
            follow = "@" in str(arg["mem"])
            addr = _addr(arg["mem"])
            keys = [k for k in MEM_COND_KEYS if k in arg]
            if len(keys) != 1:
                raise TestError(
                    "wait mem step needs exactly one of "
                    f"{'/'.join(MEM_COND_KEYS)}: {arg}")
            op = MEM_COND_KEYS[keys[0]]
            cmp_, want = MEM_OPS[op], _num(arg[keys[0]])
            deadline = time.monotonic() + timeout
            val = None
            while time.monotonic() < deadline:
                if follow:
                    addr = _addr(arg["mem"])
                with session.monitor() as mon:
                    try:
                        val = mon.memory_read(addr, 1)[0]
                    finally:
                        mon.release()
                if cmp_(val, want):
                    return True, f"mem ${addr:04x} = {val} {op} {want}"
                time.sleep(0.3)
            return False, (f"mem ${addr:04x} was {val}, wanted {op} {want}"
                           f" ({timeout}s)")
        if arg.get("idle"):
            # "the program has finished or errored" without predicting a
            # single character of its output — the step demo 05 had to
            # hand-roll as an in_range assert on PC.
            out = wait_for_idle(session, timeout)
            if out["fired"]:
                return True, f"machine idle after {out['elapsed']}s"
            pcs = " ".join(f"${pc:04x}" for pc in out["last_pcs"])
            return False, (f"machine never went idle in {timeout}s — it never "
                           f"reached direct mode, and may be wedged (PC at "
                           f"{pcs}). Note an earlier `until` step leaves the "
                           f"machine STOPPED, which never goes idle either.")
        raise TestError(
            f"wait step needs 'text' (alias 'screen'), 'mem', or 'idle': {arg}")

    # kind == "assert"
    if "screen" in arg or "text" in arg:
        # `text` is the wait spelling; accepted here for the same reason.
        needle = str(arg["screen"] if "screen" in arg else arg["text"])
        text = _screen(session)
        ok = needle in text
        return ok, (f"screen contains {needle!r}" if ok
                    else f"screen missing {needle!r}")
    if "mem" in arg:
        addr = _addr(arg["mem"])

        def _bytes(v) -> bytes:
            return bytes(_num(b) for b in v) if isinstance(v, list) else bytes([_num(v)])

        def _read(length: int) -> bytes:
            with session.monitor() as mon:
                try:
                    return mon.memory_read(addr, length)
                finally:
                    mon.release()

        # One chain, not two. Sizing the read and judging the bytes are the same
        # decision, and splitting them across two if-chains let a step naming two
        # conditions be sized by one and judged by the other: `between` sized the
        # read, then the sample branch judged it out of three names `between` had
        # never bound — UnboundLocalError mid-run instead of a pass or a fail.
        # The order below is the old sizing order, which is what the machine was
        # actually read for; for the documented one-condition-per-step shape
        # every branch does exactly what it did before.
        if "equals_text" in arg:
            want_t = str(arg["equals_text"])
            data = _read(len(want_t))
            got = screen_to_text(data, len(want_t))
            ok = got == want_t
            return ok, f"mem ${addr:04x} text {got!r}" + ("" if ok else f" != {want_t!r}")
        if "equals_any" in arg:
            alts = [_bytes(a) for a in arg["equals_any"]]
            if len({len(a) for a in alts}) != 1:
                raise TestError(f"equals_any alternatives differ in length: {arg}")
            data = _read(len(alts[0]))
            ok = data in alts
            return ok, (f"mem ${addr:04x} = {data.hex()}" if ok else
                        f"mem ${addr:04x} = {data.hex()} != any of "
                        + " / ".join(a.hex() for a in alts))
        if "mask" in arg:
            m = arg["mask"]
            mask_and, want_b = _num(m["and"]), _bytes(m["equals"])
            data = _read(len(want_b))
            got_m = bytes(b & mask_and for b in data)
            ok = got_m == want_b
            return ok, (f"mem ${addr:04x} & {mask_and:#04x} = {got_m.hex()}"
                        + ("" if ok else f" != {want_b.hex()} (raw {data.hex()})"))
        if "between" in arg:
            lo, hi = _num(arg["between"]["min"]), _num(arg["between"]["max"])
            val = _read(1)[0]
            ok = lo <= val <= hi
            return ok, (f"mem ${addr:04x} = {val} in [{lo}, {hi}]" if ok
                        else f"mem ${addr:04x} = {val} not in [{lo}, {hi}]")
        if any(k in arg for k in ("differs", "greater_than", "less_than",
                                  "unchanged")):
            cmp_key = next(k for k in ("differs", "greater_than",
                                       "less_than", "unchanged") if k in arg)
            name = str(arg[cmp_key])
            if name not in captures:
                # still before the read, so an unknown name costs no monitor trip
                detail = (f"no sample named {name!r} "
                          f"(have: {', '.join(sorted(captures)) or 'none'})")
                # `differs: 0` and `less_than: 234` read like comparisons
                # against a number and are not. Hint only when the operand
                # parses as one, so a typo'd sample name still reads as a typo.
                if _looks_numeric(name):
                    detail += (
                        " — differs/greater_than/less_than compare against a "
                        "sample, not a literal: record one first with "
                        '`- sample: { mem: "dotsleft", as: d0 }`')
                return False, detail
            # The comparison reads at the width of the sample it names, so the
            # two can never disagree about how wide the value is — the one way
            # a per-step width would let a spec compare a word against a byte.
            ref_val, width = captures[name]
            val = int.from_bytes(_read(width), "little")
            ok = {"differs": val != ref_val,
                  "greater_than": val > ref_val,
                  "less_than": val < ref_val,
                  "unchanged": val == ref_val}[cmp_key]
            op = {"differs": "!=", "greater_than": ">", "less_than": "<",
                  "unchanged": "=="}[cmp_key]
            where = f"mem ${addr:04x}{_width_note(width)}"
            return ok, (f"{where} = {val} {op} sample {name}={ref_val}"
                        if ok else
                        f"{where} = {val} not {op} sample {name}={ref_val}")
        scalar = [k for k in ("not_equals", "above", "at_least", "below",
                              "at_most") if k in arg]
        if scalar:
            op = MEM_COND_KEYS[scalar[0]]
            want = _num(arg[scalar[0]])
            val = _read(1)[0]
            ok = MEM_OPS[op](val, want)
            return ok, (f"mem ${addr:04x} = {val} {op} {want}" if ok else
                        f"mem ${addr:04x} = {val}, wanted {op} {want}")
        if "equals" not in arg:
            raise TestError(
                "assert mem step needs a comparison — one of equals/"
                "equals_text/equals_any/mask/between/differs/greater_than/"
                "less_than/unchanged/not_equals/above/at_least/below/"
                f"at_most: {arg}")
        want_b = _bytes(arg["equals"])
        data = _read(len(want_b))
        ok = data == want_b
        return ok, f"mem ${addr:04x} = {data.hex()}" + ("" if ok else f" != {want_b.hex()}")
    if "reg" in arg:
        with session.monitor() as mon:
            try:
                regs = mon.registers()
            finally:
                mon.release()
        name = str(arg["reg"]).upper()
        if name not in regs:
            return False, f"no register {name!r} (have {', '.join(sorted(regs))})"
        val = regs[name]
        if "equals" in arg:
            want = _num(arg["equals"])
            ok = val == want
            return ok, f"{name}={val:#06x}" + ("" if ok else f" != {want:#06x}")
        lo, hi = (_num(x) for x in arg["in_range"])
        ok = lo <= val <= hi
        return ok, (f"{name}={val:#06x} in [{lo:#06x}, {hi:#06x}]" if ok
                    else f"{name}={val:#06x} not in [{lo:#06x}, {hi:#06x}]")
    raise TestError(
        f"assert step needs 'screen' (alias 'text'), 'mem', or 'reg': {arg}")


def run_test(spec: dict, launch=Session.launch,
             allow_stale: bool = False) -> TestResult:
    t0 = time.monotonic()
    profile = get_profile(spec["machine"])
    session_name = f"t{uuid.uuid4().hex[:6]}"
    steps: list[StepResult] = []
    warnings: list[str] = []
    screen_text = ""
    cart_path, cart_labels, disk_path = (None, None, None)
    # load_test rejects these too, but a hand-built spec (program_test, a caller
    # assembling one in code) never passes through that layer, and one branch
    # would silently win — the losing artifact would never load.
    _reject_spec_conflicts(spec.get("name", "spec"), spec)
    try:
        # Parsed before anything boots, like `c64 build`'s: an area that cannot
        # link is a spec mistake, and paying a session start to find that out
        # helps nobody. ValueError is parse_areas' own spelling and no front
        # end catches it, so it arrives as the TestError every spec mistake is.
        areas = parse_areas(spec.get("areas") or (), profile.basic_start)
    except ValueError as e:
        raise TestError(f"{spec.get('name', 'spec')}: {e}") from None
    if spec.get("disk"):
        # Built before the machine boots: a manifest that cannot fit must fail
        # as a build error, not as a program that never appears on screen.
        disk_path = str(prepare_disk(spec.get("dir", "."), spec["disk"],
                                     spec["machine"]))
        # Two mtimes and a path: nothing the staleness guard reads needs a
        # running machine, and a refusal placed after the launch below charged
        # the caller a boot and a 45-second READY. gate to be told no — the
        # cost `areas` above already refuses to pay.
        image = Path(disk_path).resolve()
        img_labels = disk_labels_path(image)
        if img_labels is not None:
            _reject_stale_disk_labels(image, img_labels, allow_stale, warnings)
    if spec.get("program") and Path(spec["program"]).suffix.lower() == ".prg":
        # A `.prg` is the one `program:` this runner does not build, so it is
        # the one whose symbols can disagree with it. `_prepare` resolves the
        # same sibling `.lbl` after launch; this is the pair it will use.
        prg = Path(spec["program"])
        prg_labels = _sibling_labels(prg)
        if prg_labels is not None:
            _reject_stale_prg_labels(prg, prg_labels, allow_stale, warnings)
    if spec.get("cart"):
        # load_test already resolved `cart:` against the spec's directory;
        # a hand-built spec carries that directory in `dir` (cwd if absent).
        crt, cart_labels = prepare_cart(spec.get("dir", "."), spec["cart"],
                                        spec.get("cart_type", "8k"))
        cart_path = str(crt)
        # A ready-made `.crt` is the third artifact this runner does not build,
        # so it is the third whose sibling symbols can disagree with it — and
        # the judgement belongs here, ahead of the launch below, for the reason
        # the disk one does. The spec's own `cart:` is what decides: a `.s` or
        # an `.ef.yaml` came out of `prepare_cart` as a `.crt` too, labels and
        # all, and the run that just built the pair is not evidence against it.
        if (cart_labels is not None
                and Path(spec["cart"]).suffix.lower() == ".crt"):
            _reject_stale_cart_labels(crt, Path(cart_labels), allow_stale,
                                      warnings)
    session = launch(model=spec["machine"], name=session_name,
                     headless=True, warp=True, cart=cart_path, disk8=disk_path)
    try:
        labels: dict[str, int] = {}
        if cart_path:
            # A cartridge is already running its own code; there is no READY.
            # prompt to gate on and nothing to autostart.
            if cart_labels is not None and Path(cart_labels).exists():
                labels = load_labels(cart_labels)
        else:
            ok, screen_text = _wait_screen(session, lambda t: "READY." in t, 45.0)
            if not ok:
                raise TestError(f"machine never reached READY.; screen:\n{screen_text}")
            started = None
            if disk_path:
                # Attaching the image at launch only makes drive 8 hold it; the
                # machine still boots to BASIC. Autostarting the image is what
                # issues LOAD"*",8,1 — the disk's first file, which is why
                # `disk build` writes a manifest in listed order.
                started = Path(disk_path).resolve()
                # Same rule as `c64 disk boot`: a sibling .lbl, else the label
                # file `disk build` kept for the image's first entry.
                lblp = disk_labels_path(started)
                if lblp is not None:
                    labels = load_labels(lblp)
            elif spec.get("program"):
                prg, lbl = _prepare(spec["program"], profile, areas)
                if lbl is not None and Path(lbl).exists():
                    labels = load_labels(lbl)   # until/poke steps take symbols
                started = Path(prg).resolve()
            if started is not None:
                with session.monitor() as mon:
                    try:
                        mon.autostart(started, run=spec["autorun"])
                    finally:
                        mon.release()
                if not spec["autorun"]:
                    # Nothing gates a load-only start but this: without it the
                    # first step runs while bytes are still coming off the
                    # serial bus, which for a disk is seconds even in warp.
                    ok, screen_text = _wait_screen(session, _loaded, spec["timeout"] + 15)
                    if not ok:
                        # A disk spec autostarts the image's FIRST file, not a
                        # program named in the spec, so "program" alone named
                        # the wrong thing half the time.
                        what = ("the disk's first file" if disk_path
                                else "program")
                        raise TestError(
                            f"{what} never finished loading; "
                            f"screen:\n{screen_text}")
        passed = True
        captures: dict[str, tuple[int, int]] = {}   # name -> (value, width)
        for i, step in enumerate(spec["steps"], start=1):
            kind = next(iter(step))
            try:
                ok, detail = _do_step(session, kind, step[kind],
                                      spec["timeout"], labels=labels,
                                      captures=captures)
            except TestError as e:
                # Only TestError: the runner's unknown-symbol KeyError already
                # says which symbol and where to look, and keeps its own path.
                raise TestError(f"step {i} ({kind}): {e}") from None
            steps.append(StepResult(index=i, kind=kind, ok=ok, detail=detail))
            if not ok:
                passed = False
                break
        screen_text = _screen(session)
        return TestResult(name=spec["name"], machine=spec["machine"], passed=passed,
                          steps=steps, elapsed=round(time.monotonic() - t0, 2),
                          screen=screen_text, session_name=session_name,
                          warnings=warnings)
    finally:
        session.stop()
