# Debug hunt — three layers of bugs, found from the running machine

A deliberately broken Commodore BASIC sales dashboard, its listing
included below. The bugs sit in three layers — a static one, a wedge
inside a poked machine-language routine, and a character-encoding trap —
and the demo turns on finding each from the machine rather than the
listing: breakpoints, stepping, memory inspection.

This Commodore BASIC program is a little sales dashboard for a
Commodore 64. It is supposed to clear the screen, write `SALES` in the
top-left corner, call a small machine-language routine (poked into the
cassette buffer at 828) that draws a line of `=` across the second row,
then list five days of figures and their total. It misbehaves in more
than one way.

Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
run it and find every bug from the machine's actual behavior — the
screen, memory, registers, breakpoints, `c64 step` — not by eyeballing
the listing. If the machine wedges, work out exactly where it is stuck
and why before you reset. Fix the bugs while keeping the program's
design (the divider must still be drawn by the machine-language
routine), then prove the fixed version produces the intended screen.

```
10 print chr$(147)
20 dim v(4)
30 for i=1 to 5: read v(i): next
40 data 12,9,17,4,11
50 for i=1 to 5: poke 1023+i, asc(mid$("sales",i,1)): next
60 for i=0 to 12: read b: poke 828+i,b: next
70 data 162,0,169,61,157,40,4,234,224,40,208,248,96
80 sys 828
90 print: print: print
100 for i=1 to 5: print " day";i;":";v(i): next
110 print: print "total:";v(1)+v(2)+v(3)+v(4)+v(5)
```

**What success looks like:** the agent hits all three layers, each proven
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
