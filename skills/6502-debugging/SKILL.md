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

## A wedged machine (infinite loop)

Symptom: the screen stops changing, input does nothing, and `c64 status`
still reports the machine running. The usual first signal is a `c64 wait`
that times out — the machine ran for the whole timeout without ever
reaching the state you asked for. `c64 wait --idle` is the sharpest form of
that signal, because it asks for the one state every finished or errored
program reaches: it fires the moment BASIC is back at direct mode, and its
*timeout* means the machine never got there and reports the PCs it saw, so
step 1 below is already done for you. Resist the urge to reset: a wedged
machine is still holding every piece of evidence you need. Three steps
name the defective instruction:

1. `c64 reg`, two or three times, a second apart. A PC pinned in a narrow
   range names the loop; compare that range against where your program
   lives. `reg` names the ROM region beside the PC — `(KERNAL ROM)`,
   `(BASIC ROM)`, `(I/O)` — so you can tell at a glance whether the loop is
   yours or ROM code you called into. A SYS stub's loop sits in its own addresses, and the
   cassette-buffer idiom at 828 (`$033C`) is a classic host for a routine
   poked in from BASIC. A PC wandering around `$E5xx` means the machine is
   idling in BASIC waiting for input — not wedged at all (that is exactly
   what `c64 wait --idle` fires on).
2. `c64 disasm <PC-8> 24` — read the loop body. Backing up a few bytes
   catches the branch target that sits above the sampled PC. It disassembles
   *live memory*, RAM included, so it reads code poked in at runtime just as
   well as it reads ROM (it is also spelled `c64 rom disasm` — same command,
   the top-level name is the one that says what it does).
3. `c64 step` a handful of times, watching which register never changes.
   The frozen register names the defective instruction: the loop's exit
   condition depends on it, and nothing in the body advances it.

The worked example is `demos/05-debug-hunt.md`. The PC circled the
cassette buffer at $033C-$0348, where the BASIC program had poked a
machine-language routine from `data` bytes. The disassembly showed
`cpx #$28 / bne` guarding the exit, and stepping showed X frozen at 0 —
so the loop could never reach 40. The byte where `inx` ($E8) belongs read
`nop` ($EA): one mistyped `data` value, and the whole machine hangs on it.

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

## An index or address lands one cell off

Symptom: a computed screen offset, sprite pointer, or table index is
consistently wrong by a small, constant amount — never wildly wrong, just
one row, one cell, or one entry off — and it doesn't misfire the same way
on every run. Before doubting the formula, doubt carry: `adc` always folds
in the carry bit, so a stray carry left set by an *earlier*, unrelated
operation (a `cmp`, a prior `adc` chain, a `sec` from a subtraction that
never got re-cleared) silently turns `10*y + x` into `10*y + x + 1`.
Because the stray carry depends on whatever ran before it, the miscount
comes and goes with control flow instead of failing identically every
time — the hallmark of a hard-to-reproduce off-by-one.

Rule: `clc` before **every** `adc` chain, no exceptions — including the
ones you're sure already start from a clear carry. Prefer computing index
math fresh in registers over reusing one zero-page temp for two roles in
the same routine; the second role silently inherits whatever carry state
the first left behind. (The carry/decimal rules themselves live in the
`6502-assembly` skill's gotchas — this is the runtime symptom they cause.)

To confirm before fixing: `c64 reg` at the suspect `adc` — its `FL` byte's
bit 0 is carry; if it's set going in and nothing upstream was meant to
leave it that way, that's the bug, not the arithmetic.

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
