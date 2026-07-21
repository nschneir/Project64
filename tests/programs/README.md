# Example program library

Reference programs that exercise the whole toolchain end to end. Each
directory contains:

- a reference program: `program.bas` (Commodore BASIC, petcat conventions:
  keywords and string text lowercase) or `program.s` (ca65 assembly)
- `expect.txt` — screen text that must appear after the program runs
  (one required substring per non-empty line)
- `prompt.md` — the one-shot task the program solves (kept for AI-evaluation
  use)

Run them all as tests with `c64 test programs` (or via the integration
suite): each program is built, run on a fresh emulated PET, and its
expectations asserted. Add a directory here and it is automatically part of
the regression suite.

Looking for showcase prompts to hand your AI agent? Those live in `demos/`
at the repo root.
