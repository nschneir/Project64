# Debug hunt — three layers of bugs, found from the running machine

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
