# Sieve of Eratosthenes benchmark *(dogfooded 2026-07-10 — pass; ~93x asm speedup)*

Paste this prompt into your agent:

> Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
> write a Commodore BASIC program for a PET 4032 that computes all primes
> up to 1000 with a sieve of Eratosthenes, prints the count and the largest
> prime found, and prints how many jiffies it took (the PET's TI variable
> counts 60ths of a second). Then write a 6502 assembly version of the same
> sieve, run both, and report the speedup.

**What success looks like:** the BASIC run ends with `168 PRIMES, LARGEST
997` (or equivalent wording) plus a time; the assembly version produces the
same count dramatically faster; the agent verifies both from screen output
rather than assuming.
