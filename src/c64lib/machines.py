"""Machine profiles: everything model-specific is data here, not code elsewhere.

Adding a machine (e.g. VIC-20 later) means adding a profile, not new code paths.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MachineProfile:
    name: str
    vice_emulator: str          # VICE binary, e.g. "x64sc"
    vice_args: tuple[str, ...]  # model selection args
    basic_version: str          # "1.0" | "2.0" | "4.0"
    basic_start: int            # BASIC program load address
    screen_addr: int            # screen RAM base
    screen_cols: int
    screen_rows: int
    ram_kb: int                 # total RAM (BASIC sees 38911 bytes free)
    clock_hz: int               # CPU/SID clock: sets SID pitch and cycle costs
    fps: int                    # video frames per second


def _c64(name: str, extra_args: tuple[str, ...], clock_hz: int,
         fps: int) -> MachineProfile:
    return MachineProfile(
        name=name,
        vice_emulator="x64sc",
        vice_args=extra_args,
        basic_version="2.0",
        basic_start=0x0801,     # C64 BASIC start
        screen_addr=0x0400,     # power-on default; VIC-II can relocate it
        screen_cols=40,
        screen_rows=25,
        ram_kb=64,
        clock_hz=clock_hz,
        fps=fps,
    )


PROFILES: dict[str, MachineProfile] = {
    p.name: p
    for p in (
        # The clock is the SID's too: a note frequency is `reg16 * clock_hz /
        # 2**24`, so reading a register log with the other machine's clock
        # transcribes every note about 65 cents out.
        _c64("c64", ("-ntsc",), clock_hz=1022727, fps=60),   # NTSC, the default
        _c64("c64pal", ("-pal",), clock_hz=985248, fps=50),
    )
}


def get_profile(name: str) -> MachineProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(
            f"unknown machine profile {name!r}; available: {', '.join(sorted(PROFILES))}"
        ) from None
