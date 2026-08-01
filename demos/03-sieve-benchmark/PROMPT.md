# Sieve benchmark — the same sieve twice, BASIC against assembly

A sieve of Eratosthenes to 1000, written once in Commodore BASIC and once
in 6502 assembly, with both runs timed on the machine. It shows the jiffy
clock used as a stopwatch and the speedup that dropping into assembly
buys.

Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
write a Commodore BASIC program for a Commodore 64 that computes all
primes up to 1000 with a sieve of Eratosthenes, prints the count and the
largest prime found, and prints how many jiffies it took (the TI
variable counts 60ths of a second). Then write a 6502 assembly version
of the same sieve, run both, and report the speedup.

**What success looks like:** the BASIC run ends with `168 PRIMES,
LARGEST 997` (or equivalent wording) plus a time; the assembly version
produces the same count dramatically faster; and the agent verifies both
from the screen output of the running program rather than assuming.
