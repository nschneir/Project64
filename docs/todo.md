# TODO

Open items carried out of the `.crt` cartridge support work (2026-07-26) plus
the standing project backlog. Strike items as they land.

## Decisions (maintainer)

- [ ] **Release timing for 0.5.0.** `pyproject.toml`, `CHANGELOG.md`, and
      `README.md` are coherent at 0.5.0; pushing `main` arms the release
      workflow. Revert the bump as a unit to ship later.

## Cartridge follow-ups

- [ ] **EasyFlash window configs have no BSS/RAM area.** Deliberate for now
      (the `.org`-based resident block needs none, and the design question —
      where per-bank RAM should live after the 16K-mode switch — is open).
      Wrapped and native single-region carts do get a BSS area.
- [ ] **`wrap_prg` still accepts ML load addresses in `$A000-$BFFF` (8k),
      `$D000-$DFFF`, and `$E000-$FFFF`** — the launcher copies under
      BASIC ROM / I/O / KERNAL and then jumps into what reads back as ROM.
      Same silent-dead-cart class as the fixed `$8000-$9FFF`/window case.
- [ ] **`src/c64lib/build.py` starts the ZP memory area at `$0000`** for
      ordinary (non-cart) programs — the first two zero-page variables land on
      the 6510 port registers `$00`/`$01`. The cart linker configs were fixed
      to `$0002`; `build.py` should match.
- [ ] **Version-coherence test.** Assert `README.md`'s release line matches
      `pyproject.toml`'s `version` (parse, don't hard-code — survives a
      revert). Suggested home: `tests/test_docs_readme.py`.

## Accepted behavior (documented, revisit only if it bites)

- [x] Stale `.crt`/`.bin` beside the output path after a failed rebuild —
      consistent with `build_asm`'s `.prg`/`.lbl` behavior; now documented in
      `docs/cli.md`.
- [x] `index.html` tool count and missing cartridge card — fixed (55 tools,
      CARTRIDGES card added).

## Test health

- [ ] **`tests/test_integration_debug.py::test_symbolic_debug_loop` flakes
      under load** (breakpoint-never-hit; two sightings, both under parallel
      load/coverage tracing; passes standalone and in plain full runs).
      Pre-existing, non-cart. Needs its own investigation.

## Standing backlog (pre-cartridge)

- [ ] Dogfood the six C64 demo prompts (statuses in `demos/README.md` are
      "awaiting C64 dogfood").
- [ ] Build the full annotated C64 ROM label DB (only the KERNAL jump-table
      seed ships today).
- [ ] Deferred spec items: sprite-aware screenshot diffing, `c64 sprite` CLI
      helpers, VIC-II screen relocation support.
