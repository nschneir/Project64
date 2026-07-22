# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged. Project64 is a Commodore 64 port of
[PET-Project](https://github.com/nschneir/PET-Project); its PET-era history
lives in that repository (and in this one's git history before the fork
commit).

## [0.1.0] — 2026-07-21

The founding release: everything the PET edition could do, ported to the
Commodore 64.

### Added
- **C64 machine profiles** — `c64` (NTSC, the default) and `c64pal`, both
  BASIC 2.0 with 38911 bytes free; BASIC start `$0801`, screen `$0400`.
- **C64 ROM support** — BASIC `$A000` / KERNAL `$E000` identification and
  hashing, plus a curated seed label database: the full KERNAL jump table
  (`$FF81-$FFF3`), hardware vectors, and BASIC pointers, all live-verified.
- **C64 key-hold protocol** — `c64 key hold` drives the current-key matrix
  code at `$CB` (with a full ASCII→matrix-code table), verified against a
  live emulator.
- **C64 disk formats** — d64/d71/d81 (1541/1571/1581 drives) via c1541;
  1541 is the attach default.
- **c64-development skill** — SKILL.md plus references (memory map,
  zero page with the 6510 banking port, KERNAL routines, VIC-II/SID/CIA
  hardware, BASIC internals, PETSCII, cookbook) rewritten from the C64
  reference books; every live-assertable claim measured on a real x64sc.
- **Cookbook** — 16 C64 recipes (sprites, SID sound, `$CB` input, CINV IRQ
  wedge, screen+color pokes ...), all exercised live by the test suite.
- **Graphics & sprites spec** — `docs/specs/graphics-and-sprites.md`: how
  demos author sprite data, capture screenshot evidence, and write
  register/memory-based tests.
- **C64 demo prompts** — six graded prompts (bouncing-ball sprite demo,
  Snake with SID + `$CB` steering, sprite-based Invaders flagship),
  awaiting their C64 dogfooding runs.

### Changed
- Renamed throughout from the PET edition: package `petlib` → `c64lib`,
  distribution `pet-tools` → `c64-tools`, CLI `pet` → `c64`, MCP tools
  `pet_*` → `c64_*`, env prefix `PET_TOOLS_` → `C64_TOOLS_`, state dir
  `~/.pet-tools` → `~/.c64-tools`, emulator `xpet` → `x64sc`.
  `petcat`, `PETSCII`, and `c1541` keep their names — they are correct
  for the C64.
- petcat dialects reduced to C64 BASIC 2.0 (`-w2`).
- `c64 package` run hints pin the video standard (`x64sc -ntsc ...`).

### Removed
- PET machine profiles, PET ROM labels, VIA/CB2 sound recipes, BASIC 4
  disk-command docs, and the PET-built demo programs (`demos/invaders/`,
  `demos/muncher/`) — the demo prompts will be re-dogfooded on the C64.
