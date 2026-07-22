---
name: 6502-debugging
description: Use when a C64 program misbehaves at runtime — crashes, corruption, wrong values, dead input, visual glitches — and you need a procedure, not a guess. Symptom-indexed playbook of runtime debugging procedures using c64-tools.
---

# 6502 debugging playbook

Procedures that turn a symptom into a verified cause using `c64` commands.
Follow the procedure before forming theories — each one exists because
improvising in its situation reliably wastes time. The companion
references are the `c64-development` skill's diagnosis table (quick
symptom→cause lookups) and the `6502-assembly` skill's gotchas (the bugs
you write, rather than find).

## Rule zero: prove you are debugging the binary you think you are

The most expensive class of debugging failure is the hunt for a "bug"
that does not exist: a rebuild failed silently and every observation is
of the *previous* binary. Before trusting any runtime evidence:

1. `c64 status` — read the `program:` line and look for
   `STALE (source changed since load)`. Stale means rebuild and reload
   before doing anything else.
2. If in doubt, spot-check code bytes: `c64 mem read <label> 8` and compare
   against the assembler listing. Two minutes here beats hours of
   fiction-driven debugging.
3. A failed `c64 run` says loudly that the emulator still runs the previous
   program. Believe it.

## Triage: the first three commands

For any misbehavior, in order: `c64 status` (running or stopped? stale?),
`c64 screen` (what does the program think is happening?), `c64 reg` (where
is PC — in your code, in ROM, or in the weeds?). If PC is in unmapped or
BSS space, the crash already happened; the question becomes "what jumped
here," not "what is wrong here."

The `brk` opcode is **$00**, so execution that runs off into zeroed or
uninitialized RAM hits `brk` almost immediately and vectors through `$FFFE`
into the KERNAL — a PC parked in KERNAL ROM (or a program that mysteriously
"returns to BASIC") after running past the end of your code is the classic
tell that it fell off the rails, not that ROM itself is at fault.

## Something is corrupting memory

Symptom: a variable changes that "nothing writes to"; code bytes change;
behavior degrades over time. Do not read code looking for the writer —
trap it:

    c64 watch add <addr> --store
    c64 wait --break <ID>

The machine halts ON the writing instruction; `c64 reg` and the PC symbol
name the culprit. Pass the watchpoint's ID to `--break` so a leftover
breakpoint cannot intercept the wait. One watchpoint routinely finds in
seconds what an hour of code-reading cannot. If the writes are legitimate
but wrong (right routine, wrong index), add a condition:
`c64 break add <label> --condition 'X > 4'`.

## A loop goes wrong partway / the wrong actor moves

Symptom of a **register clobber**: a helper called inside the loop
destroys X or Y. Two procedures:

- Audit by isolation: `c64 call <helper> --x 3` then `c64 reg` — did X
  survive? Repeat for each helper the loop body calls. (In YAML:
  `call: { routine: helper, x: 3 }` then `assert: { reg: x, equals: 3 }`.)
- Audit in place: `c64 until <loop-label>`, note X, `c64 step --over`
  through the body watching for the register to change across a `jsr`.

Clobber bugs cluster in helpers added to an existing loop late in
development (sound triggers, HUD updates) — audit those first.

## Reproducing a timing-dependent bug deterministically

Wall-clock time is poison under `--warp` (seconds of your time are emulated
minutes). Rebuild the failure state explicitly instead of replaying to it:

1. `c64 until <tick-label>` — stop at the frame anchor.
2. `c64 mem write --stdin` — poke the exact state (positions, timers,
   flags) that precedes the failure.
3. `c64 until <tick-label> --count N` — advance exactly N frames.
4. Inspect. Every run is now identical; bisect N to find the failing frame.

Encode the reproduction as YAML `poke:`/`until:`/`assert:` steps
immediately — the reproduction *is* the regression test.

## Testing one routine without the rest of the program

`c64 call <routine>` emulates a JSR in isolation: fake return address on
the stack, optional `--a/--x/--y` on entry, halts at the routine's own RTS
with registers and memory holding its results. Poke inputs first, call,
assert after. Use it to prove a suspect routine innocent (or guilty)
without the game loop muddying the evidence, and as the YAML `call:` step
for permanent routine-level unit tests. A `call` timeout means the routine
never returned from that entry state — itself a finding (runaway loop, or
you called a non-subroutine).

## Waiting for something that might stop happening

`c64 until <label>` deadlocks if the program can stop visiting the label
(death, menu, pause). For transitions, set a breakpoint at a path that
MUST execute and `c64 wait --break <ID>`; for transient values that polling
would miss at warp, use a store watchpoint instead of `c64 wait --mem`.

## Visual glyph bugs

`c64 screen` decodes graphics to Unicode look-alikes — good for reading,
ambiguous for identity (several screen codes map to similar glyphs). To
assert exactly which character is in a cell: `c64 screen --codes` (raw
code matrix) or `c64 mem get '@row,col'`. For pixel truth:
`c64 screen --png shot.png --scale 3`.

## Inspection discipline (warp)

End every inspection batch STOPPED (`c64 until`, `c64 step`, or a fired
`c64 wait --break` all leave the machine halted, and it stays halted across
commands). A machine left running between two inspection commands has
played on for emulated minutes; conclusions drawn across that gap compare
two different worlds. Batch reads while stopped; `c64 continue` only when
you mean "let time pass."
