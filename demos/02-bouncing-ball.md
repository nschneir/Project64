# Bouncing ball *(dogfooded 2026-07-10 — first-try pass)*

Paste this prompt into your agent:

> Using the c64 CLI (see skills/pet-development/SKILL.md and docs/cli.md),
> write a Commodore BASIC program for a PET 4032 that animates a ball (`O`)
> bouncing around the 40×25 screen by poking screen memory at $8000, leaving
> a border drawn around the screen edge. Let it run for a while, take a
> screenshot with `c64 screen --png ball.png`, and show me the screen text
> too.

**What success looks like:** the agent works out screen-memory addressing
(row × 40 + column offsets into $8000), uses screen codes rather than
PETSCII for the pokes, and produces a screen showing the border and the
ball mid-flight.
