# Debug hunt

A deliberately broken Commodore BASIC sales dashboard — the listing ships
inside the prompt — with bugs in three layers: a static one `c64 basic
check` catches, a wedge in a machine-language routine poked into the
cassette buffer, and a PETSCII-versus-screen-codes encoding trap. A run
finds each from the machine's actual behavior (screen, memory, registers,
breakpoints, `c64 step`) rather than from the listing, then fixes them
without changing the program's design.

`PROMPT.md` is all this directory holds. The fixed program and the evidence
for each bug are the deliverable of the run, not files committed here. For
one demo whose answer *is* kept in full — sources, plan, audit, evidence
frames and a packaged disk — see [`demos/invaders/`](../invaders/).
