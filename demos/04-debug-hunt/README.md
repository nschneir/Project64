# Debug hunt

A deliberately broken Commodore BASIC sales dashboard — the listing ships
inside the prompt — with bugs in three layers: a static one `c64 basic
check` catches, a wedge in a machine-language routine poked into the
cassette buffer, and a PETSCII-versus-screen-codes encoding trap. A run
finds each from the machine's actual behavior (screen, memory, registers,
breakpoints, `c64 step`) rather than from the listing, then fixes them
without changing the program's design.

**What a passing run shows** (spoilers — the answer key the prompt
deliberately withholds). The agent hits all three layers, each proven
from the running machine — `c64 basic check` flags layer 1 statically
(rule E131), and finding a bug that way instead of by running does not
clear a layer.
(1) The run dies immediately with `?BAD SUBSCRIPT` — `dim v(4)` is too
small for `v(5)`.
(2) The next run wedges at `sys 828`: the poked routine's `INX` was
mistyped as a `NOP` (`data` byte 234 instead of 232), so X never advances
and the fill loop spins forever — the agent should prove this from the
machine (PC circling the cassette buffer around $033C-$0348, X frozen at
0 under `c64 step`, or a disassembly of 828) rather than by staring at
the byte list.
(3) The title shows the wrong characters instead of `SALES`, because
`asc()` yields PETSCII codes and screen memory wants screen codes — the
classic encoding trap.
The fixed program shows `SALES`, a full row of `=` drawn by the routine,
DAY 1 through DAY 5 with their figures, and `TOTAL: 53`.

`PROMPT.md` is all this directory holds. The fixed program and the evidence
for each bug are the deliverable of the run, not files committed here. For
one demo whose answer *is* kept in full — sources, plan, audit, evidence
frames and a packaged disk — see [`demos/invaders/`](../invaders/).
