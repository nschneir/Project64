# Sieve benchmark

A sieve of Eratosthenes to 1000, written twice: once in Commodore BASIC,
once in 6502 assembly. Each run prints the prime count, the largest prime,
and its own elapsed time from the jiffy clock (`TI`), and the demo reports
the measured speedup of the assembly version over the BASIC one — then goes
back over the assembly a second time, optimizing it for speed and reporting
what that pass bought.

**What a passing run shows.** The BASIC run ends with `168 PRIMES,
LARGEST 997` (or equivalent wording) plus a time; the assembly version
produces the same count dramatically faster; the optimized assembly still
produces that same count and largest prime, timed again and reported
against the first assembly version, with the agent naming what it changed
to get there; and every one of those numbers is read from the screen output
of the running program rather than assumed.

Beyond this README, `PROMPT.md` is all this directory holds. The programs
the agent writes and the timings it reads off the running machine are the
deliverable of the run, not files committed here.
