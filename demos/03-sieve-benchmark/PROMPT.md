# Sieve benchmark — the same sieve twice, BASIC against assembly

Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
write a Commodore BASIC program for a Commodore 64 that computes all
primes up to 1000 with a sieve of Eratosthenes, prints the count and the
largest prime found, and prints how many jiffies it took (the TI
variable counts 60ths of a second). Then write a 6502 assembly version
of the same sieve, run both, and report the speedup. Finally, attempt to
optimize the 6502 version to make it even faster and report the results.

Work from this prompt and the skills alone: do not read any
`demos/*/README.md` — those READMEs are documentation for human readers
and can spoil the exercise.
