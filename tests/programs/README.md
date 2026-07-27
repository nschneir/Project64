# Example program library

Reference programs that exercise the whole toolchain end to end. Each
directory contains:

- a reference program: `program.bas` (Commodore BASIC, petcat conventions:
  keywords and string text lowercase) or `program.s` (ca65 assembly)
- `expect.txt` — screen text that must appear after the program runs
  (one required substring per non-empty line)
- `prompt.md` — the one-shot task the program solves (kept for AI-evaluation
  use)
- `test.yaml` (optional) — extra declarative steps (asserts, until/sample
  motion checks) appended after the expect.txt gate — see sprite-ball

Two variations ship no loadable program of their own:

- A **cartridge** program's `test.yaml` sets `cart:` (a cart-native `.s`, an
  `.ef.yaml` manifest, or a prebuilt `.crt`). The image is attached at
  power-on, so nothing is autostarted and there is no `READY.` prompt to gate
  on — see cart-hello (single-region 8K) and cart-banked (multi-bank
  EasyFlash).
- A **disk** program's `test.yaml` sets `disk:` (a `.d64`/`.d71`/`.d81` or a
  `.disk.yaml` manifest built by `c64 disk build`). The image is attached to
  drive 8 at power-on and autostarted after `READY.`, which loads and runs its
  first file — see disk-loader, which then pulls a *second* file off the same
  disk while running.

In both cases any `.s`/`.bas` in the directory is the image's source, not
something the runner autostarts.

Run them all as tests with `c64 test programs` (or via the integration
suite): each program is built, run on a fresh emulated C64, and its
expectations asserted. Add a directory here and it is automatically part of
the regression suite.

Looking for showcase prompts to hand your AI agent? Those live in `demos/`
at the repo root.
