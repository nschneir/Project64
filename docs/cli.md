# `c64` CLI reference

A complete reference for the `c64` command line — everything the toolset can
do without the MCP server. For MCP-native clients the `c64-tools-mcp` server
exposes the same operations; see the README.

## Conventions

- **Sessions.** Most commands act on a running emulator session. Sessions are
  tracked in a registry under `~/.c64-tools/sessions/` (override the base with
  `$C64_TOOLS_HOME`). A command with no `--session` targets the single running
  session; if several are running you must name one.
- **Global options**:
  - `--json` — emit machine-readable JSON on stdout instead of human text.
    This is the intended interface for AI agents. Every command supports it,
    in either position: `c64 --json session list` and
    `c64 session list --json` are equivalent.
  - `--session, -s NAME` — target a specific session by name. Every command
    supports it, in either position: `c64 -s inv mem get $0400` and
    `c64 mem get $0400 -s inv` are equivalent. One exception: on
    `session start`, `session ensure`, and `session stop`, `-s` is the alias
    of their own `--name` option, so there is no trailing `--session` there —
    name the session with `--name` (or, for `stop`, positionally).
  - `--version` — print `c64 <version>` and exit. Must come before the
    subcommand.
  - `--help` — print usage and exit. Works on every command and group, but
    always describes the level it is typed at: `c64 session start --help`
    documents that command, while `c64 --help session start` prints the
    top-level help. `c64 help session start` is the subcommand spelling.
- **Numbers.** Address and value arguments accept `$hex` (e.g. `$0400`),
  `0xhex`, or decimal. Where a label file is registered on the session (via
  `c64 build`/`c64 run` of assembly, or `c64 load --symbols`), a **symbol
  name** is accepted anywhere an address is. Addresses additionally accept
  an **offset** (`alienX+49`, `tick-1`, `dots+$52`, `$0400+40`) and a
  **screen cell** `@row,col`
  (e.g. `@23,18`), resolved against the machine's LIVE screen base
  (relocation-aware; 40×25, $0400 at power-on).
  `@@row,col` is the same cell in **color RAM** — hardwired at `$D800`
  (the screen relocates; the color matrix does not). Color RAM reads back
  4-bit, so compare masked (`& $0F`; `mask: { and: "$0f", ... }` in YAML).
- **Exit codes.** `0` on success; `1` on error, on a `c64 wait` timeout, or on
  a failing `c64 test`; `2` on CLI misuse (Click's usage errors — an unknown
  option, a bad `--flag` value, or an input-file argument naming a path that
  does not exist).
- **Machine state.** Every session runs a monitor daemon that owns the one
  VICE connection, so the machine's run/stop state persists across `c64`
  commands. **`c64 step`**, **`c64 finish`**, **`c64 until`**, and
  **`c64 wait --break`** (on a checkpoint hit) halt the machine, and it
  STAYS halted — across as many commands as you like — until
  `c64 continue`, an explicitly-resuming command (`c64 run`, `c64 load`,
  `c64 disk boot`, `c64 session reset`), or a new halt. Inspection commands
  (`screen`, `mem`, `reg`, ...) never disturb the state.

---

## Help and version

### `c64 help`

Print help for `c64` or one of its commands, then exit. Equivalent to the
`--help` option, but as a subcommand.

- `COMMAND...` (optional) — a command path to describe; with no argument,
  prints the top-level help.

Examples: `c64 help`, `c64 help session`, `c64 help session start`. No
session required.

---

## Sessions

### `c64 session start`

Boot a fresh emulated C64.

- `--model MODEL` (default `c64`) — `c64` (NTSC) or `c64pal` (see the
  README's Supported machines table).
- `-s, --name NAME` — session name (defaults to the model name).
- `--headless` — no window on SDL builds; on GTK builds (the installed
  `x64sc`) it starts minimized and never takes focus.
- `--warp` — run at maximum speed (recommended for automation).
- `--disk PATH` — attach a `.d64`/`.d71`/`.d81` image to drive 8 at boot.
  Attaching only fills the drive — the machine still boots to BASIC;
  `c64 disk boot IMAGE` (naming the image again) is what LOAD+RUNs it. The
  image's label file is registered if one exists (same rule as
  `c64 disk boot`).
- `--cart PATH` — attach a `.crt` cartridge at power-on. The machine boots
  straight into it; there is nothing to load afterwards. A sibling `.lbl` of
  the cartridge's stem is registered as the session's symbols if it is there.

Human: `started c64 session 'c64' (pid 1234, monitor port 6510)`.
JSON: `{"name", "model", "pid", "port", "symbols"}` — `symbols` is the label
file registered from `--disk`/`--cart`, or `null`. Machine left running.

Starting a session also starts its monitor daemon — the process that owns
the VICE monitor connection and holds run/stop state between commands.
Daemon output goes to `<sessions-dir>/<name>.daemon.log`; a crashed daemon
is respawned automatically by the next command (repeated crashes error out
and ask for a session restart). `C64_TOOLS_NO_DAEMON=1` disables it.

### `c64 session ensure`

Attach to a running session, or start one if none exists. Idempotent:
exits 0 either way and reports which happened — the safe bootstrap for
scripts and the recovery step after a dead daemon.

- `--model MODEL` — model to boot if starting (default `c64`).
- `--name/-s NAME` — session name to look for / start.
- `--headless`, `--warp` — apply only when a session is started.

JSON: `{"name", "model", "pid", "port", "started"}` — `started` is `true`
when a new session was booted, `false` when one was already running.

### `c64 session list`

List running sessions (dead ones are pruned).
JSON: `{"sessions": [{"name", "model", "pid", "port"}, ...]}`.

### `c64 session stop`

Stop a session and remove its registry record.

- `NAME` (optional) — the session to stop; defaults to the current one.
- `-s, --name NAME` — the same, as an option (the spelling every command
  understands). Giving both forms with different names is an error.

JSON: `{"stopped": NAME}`.

### `c64 session reset`

Reset the running machine; leaves it running.

- `--hard` — power-cycle instead of a soft reset.

JSON: `{"reset": NAME, "hard": bool}`.

### `c64 status`

    c64 status

Show the current session (name, model, pid, port) and whether the machine
is **running** or **stopped** right now. The state comes from the session
daemon's own tracking — no emulator traffic, so it never disturbs the
machine. Without a daemon it reports `unknown` (a direct monitor
connection stops the CPU, making the question unanswerable). `c64 reg`
also includes `"state"` in its JSON output.

---

## Screen

### `c64 screen`

Show the emulated screen (relocation-aware: reads wherever the VIC-II
currently points). With no option, prints the screen decoded to text —
the preferred way to observe program output. With `--png` it writes an image;
with `--codes` it prints the raw screen-code matrix.

- `--png PATH` — save a PNG screenshot instead of printing text.
- `--scale N` — integer nearest-neighbour upscale for `--png` (default 1;
  C64 screens read better at 2–3×).
- `--border` — include the border area in `--png`. The default capture is
  the 320×200 inner screen only, so a `POKE 53280` border color does **not**
  appear without this flag.
- `--codes` — print the 25×40 matrix of raw screen codes (decimal). With
  `--json`, nested arrays under `"codes"`. Use this to assert exact glyph
  identity.
- `--style unicode|ascii` — text decoding style (default `unicode`).
  Unicode maps graphics to real box/block/shape glyphs (`╭─╮ ● ▌ █ …`);
  `ascii` is the legacy conservative mapping (graphics → `·` except
  `- | +`).
- `--ansi-reverse` — wrap reverse-video cells with no Unicode complement
  in terminal inverse-video escapes.
- `--numbered` — prefix each row with its index and print a column ruler.
  Use it to read off the `@row,col` references that `c64 wait --mem` and
  YAML `assert: {mem: "@r,c"}` take. `--json` output is unaffected (`rows`
  is already indexed).

JSON (text): `{"text", "rows": [...]}`. JSON (`--png`): `{"png", "width",
"height"}`. JSON (`--codes`): `{"codes": [[...], ...]}`. Machine state
preserved.

> **Migration note (v1.2):** the default decoding changed from the
> conservative ASCII mapping to Unicode. `c64 wait --text` and YAML
> `wait: {text: ...}` match against the decoded text, so patterns that
> relied on graphics decoding to `·` (or reverse-space decoding to blank)
> must be updated or run with `--style ascii`. Plain-text patterns
> (letters/digits/punctuation) are unaffected.

---

## Keyboard

### `c64 key type`

Type text into the running C64's keyboard buffer (`\n` = RETURN, whether
written as a real newline or as the two characters backslash-n; `\\` types
a literal backslash). Use it to
answer `INPUT` prompts or drive menus; for typing in whole programs prefer
`c64 basic type`. Buffered keys never touch the live current-key state at
`$CB` — to steer a game that reads held keys, use `c64 key hold`.

- `TEXT` — the keystrokes (letters are case-folded to the C64's convention).

JSON: `{"typed_chars"}`. Machine state preserved.

### `c64 key hold`

Hold KEY down for N game ticks by re-poking the current-key byte `$CB`
before each one: write the key's keyboard-matrix code, run to the frame
anchor, repeat. The machine ends **stopped** at the anchor (resume with
`c64 continue`). The IRQ keyboard scan rewrites `$CB` every tick (64 = no
key), which is why the code is re-poked per frame. For a fully
deterministic first frame, stop at the anchor first (`c64 until REF`).

- `KEY` — one character, or `space`.
- `--at REF` (required) — the frame anchor: a label or address executed once
  per game tick (your main-loop label).
- `--frames N` (default `1`) — how many ticks to hold the key across.
  `--frames 0` is a validated no-op (exit 0, machine untouched) — a
  computed hold length of zero needs no shell guard.
- `--timeout SECS` (default `30`) — per-frame wait limit.

JSON: `{"registers", "pc_symbol", "stopped": true, "frames"}`. With
`--frames 0`: `{"frames": 0, "requested": 0, "machine": "untouched"}`. On a
frame timeout: exit 1, machine left running, checkpoint removed.

---

## Memory

### `c64 mem read`

Read emulated memory and print a hex dump (16 bytes/line plus a text column).

- `ADDR` — start address (`$hex`/`0x`/decimal/symbol).
- `LENGTH` (default `256`) — number of bytes.
- `--decimal` — render decimal values instead of a hex dump.
- `--as auto|screen|petscii|ascii` (default `auto`) — decoding for the text
  column.

**The hex is the truth; the text column is a gloss.** Every dump ends with a
line naming the gloss it used, so the column can never mislead silently:

    c64 mem read $0400 5
    0400: 13 01 0c 05 13                                   SALES
    # text column: screen codes

`auto` asks where the *live* screen is — `$DD00`'s VIC bank plus `$D018`'s
slot, so a relocated screen is followed — and glosses ranges that intersect
it as screen codes (`1`-`26` are `A`-`Z`, `0` is `@`, `32`-`63` match ASCII,
graphics and reverse video show as `.`); everything else stays ASCII. If the
VIC state cannot be read, the dump falls back to ASCII and says so
(`# text column: ascii (VIC state unreadable)`). `--as screen` forces the
screen-code gloss anywhere (a sprite/charset buffer, a screen you are
building in spare RAM), `--as petscii` suits keyboard-buffer and
CHROUT-bound bytes, and `--as ascii` restores the old unconditional gloss.
`c64 screen --codes` remains the purpose-built view of the whole screen.

JSON: `{"addr", "length", "hex", "bytes", "values", "text_encoding"}` (`hex`
is the bytes hex-encoded; `"bytes"` and `"values"` are the same decimal int
array — `values` mirrors `mem get`'s key so a script can use either;
`"text_encoding"` is the resolved gloss — `screen`, `petscii`, or `ascii`).
Machine state preserved.

### `c64 mem get`

    c64 mem get ADDR [LENGTH]

Print LENGTH (default 1) byte values at ADDR in decimal — bare,
space-separated, pipe-friendly (`[ $(c64 mem get score) -gt 0 ]`). JSON:
`{"addr": N, "values": [ints], "bytes": [ints]}` — the two arrays are
identical; `bytes` mirrors `mem read`'s key so a script written against
either command works against both. ADDR takes everything the rest of the CLI
does — `$hex`/`0x`/decimal, a symbol from the loaded label file,
`symbol+offset`, or a screen cell `@row,col`. Does not disturb run/stop
state. (MCP note:
there is deliberately no `c64_mem_get` tool — `c64_mem_read` already
returns a decimal `bytes` array.)

### `c64 mem find`

    c64 mem find VALUE... [--start ADDR] [--length N] [--limit M]

Search memory for a byte pattern and print every match address. VALUE is
one or more bytes (`$hex`/`0x`/decimal) forming the pattern. Defaults:
`--start $0000`, `--length $10000` (clamped to the 64 KB space),
`--limit 256`. JSON: `{"pattern", "start", "length", "matches", "count",
"truncated"}` — `truncated` is true when the limit clipped the list
(searching for `$00` legitimately matches thousands of addresses). Does
not disturb run/stop state.

### `c64 mem write`

Write bytes to emulated memory.

- `ADDR` — start address (`$hex`/`0x`/decimal/symbol).
- `VALUES...` — one or more byte values (`$hex`/`0x`/decimal). They may be
  separate arguments or a single whitespace-separated string
  (`c64 mem write score "0 0 1 4 9 0"`), which is what a shell variable
  expands to. A value that is not a byte is reported by position and text
  (`byte 2 is 'x9', not a number`), not as a traceback.
- `--stdin` — batch form: read one write per line (`REF V1 V2 …`; blank
  lines and `#` comments skipped) from stdin instead of arguments. The
  heredoc pattern:

      c64 mem write --stdin <<EOF
      dots+82 0
      hs_sc   $01 $23 $45
      EOF

JSON: `{"writes": [{"addr", "written"}, ...], "written": total}`. Machine
state preserved.

---

## Registers

### `c64 reg`

Show the CPU registers (this is a callable group — run it with no subcommand).
PC is annotated with the nearest symbol from the ROM label database plus the
session's label file (the same lookup `c64 disasm` uses), so a PC parked on a
KERNAL entry point is named even with no label file loaded.

When no symbol is within reach, the **ROM region** is named instead —
`PC=e5d1  (KERNAL ROM)` — so a PC that landed in `$A000-$BFFF` (BASIC ROM),
`$D000-$DFFF` (I/O) or `$E000-$FFFF` (KERNAL ROM) reads as such without
consulting a memory map. A PC in RAM gets no annotation: the region says
nothing there. The region is the *address space*, not which bank `$01` has
switched in. Sampling `c64 reg` a second apart is step 1 of the wedged-machine
playbook in the `6502-debugging` skill; a PC wandering the KERNAL around
`$E5xx` usually means the program has finished or errored and BASIC is back at
its input loop — which is the condition `c64 wait --idle` blocks on.

JSON: `{"registers": {"PC", "A", "X", "Y", "SP", "FL", ...}, "pc_symbol",
"pc_region", "state"}` — `pc_region` is reported whether or not a symbol
matched, and is `null` for a PC in RAM. Machine state preserved.

### `c64 reg set`

Set a register.

- `NAME` — register name (e.g. `PC`, `A`, `X`, `Y`).
- `VALUE` — new value (`$hex`/`0x`/decimal).

JSON: `{"register", "value"}`. Machine state preserved.

---

## Breakpoints and watchpoints

Breakpoints and watchpoints are VICE checkpoints. Setting one leaves the
machine running; use `c64 wait --break` to block until it fires. Checkpoints
survive a subsequent `c64 load`/`c64 run`, so set them before loading.

Checkpoints **persist across `c64 run`/rebuilds by design** — reloading a
program does not remove them. Clear stale ones (`c64 break clear`,
`c64 watch clear`) or duplicates accumulate.

### `c64 break add`

Set an execution breakpoint at an address or symbol.

- `REF` — address or symbol.
- `--condition EXPR` — a VICE condition, e.g. `'A != 0'`.
- `--temporary` / `--once` — delete the breakpoint after it fires once.

JSON: `{"id", "address", "condition", "temporary"}`. Machine state preserved.

### `c64 break list`

List all checkpoints with hit counts.
JSON: `{"breakpoints": [{"id", "address", "end", "op", "enabled", "hits",
"has_condition"}, ...]}`.

### `c64 break remove` (alias: `c64 break rm`)

- `CK_ID` — checkpoint id (integer). JSON: `{"removed": id}`.

### `c64 break enable`

- `CK_ID` — checkpoint id. JSON: `{"enabled": id}`.

### `c64 break disable`

- `CK_ID` — checkpoint id. JSON: `{"disabled": id}`.

### `c64 break clear`

    c64 break clear

Remove ALL breakpoints (exec checkpoints); watchpoints are kept. JSON:
`{"removed": [ids], "count": n}`.

### `c64 watch add`

Set a watchpoint on a memory range (default: both load and store).

- `REF` — address or symbol.
- `--load` — break on reads.
- `--store` — break on writes.
- `--length N` (default `1`) — number of bytes to watch.

JSON: `{"id", "address", "length", "op"}`. Machine state preserved.

### `c64 watch remove` (alias: `c64 watch rm`)

- `CK_ID` — checkpoint id (integer). JSON: `{"removed": id}`.

### `c64 watch clear`

    c64 watch clear

Remove ALL watchpoints (load/store checkpoints); breakpoints are kept.
JSON: `{"removed": [ids], "count": n}`.

---

## Execution control

### `c64 step`

Execute N instructions; **the machine stays stopped** afterwards.

- `COUNT` (default `1`) — number of instructions.
- `--over` — step over `JSR` subroutines.

JSON: `{"registers", "pc_symbol", "stopped": true}`.

### `c64 finish`

Run until the current subroutine returns; **stays stopped**.
JSON: `{"registers", "pc_symbol", "stopped": true}`.

### `c64 continue`

Resume a stopped machine. JSON: `{"running": true}`.

### `c64 until`

Run until `REF` (address or symbol) is executed; **stays stopped** there —
across subsequent commands — until you `c64 continue`.

- `REF` — address or symbol.
- `--count N` (default `1`) — stop at the Nth arrival at REF. With REF set
  to the program's main-loop label this is deterministic **frame stepping**
  (see the cookbook's frame-stepping recipe). The count loop runs inside
  the session daemon, so large counts are fast (hundreds of frames per
  second of wall clock, not one per half-second).
- `--timeout SECS` (default `30`).

JSON: `{"registers", "pc_symbol", "stopped": true, "count"}`. Exit 1 on
timeout (the error reports how many arrivals were reached); after a timeout
the machine is left running and the checkpoint is removed.

On timeout `c64 until` exits 1, **leaves the machine RUNNING**, and removes
the checkpoint it set (JSON: `"machine": "running"`,
`"checkpoint_removed": true`). Beware the branch-away deadlock: if the
program can stop visiting REF (death, menu, pause screen), `until REF` can
never fire — set a breakpoint at a code path that must still execute and use
`c64 wait --break` instead.

### `c64 call`

JSR the routine at `REF` in isolation and stop when it returns — the
**unit-test primitive**: poke inputs, call one routine, assert registers
and memory afterwards without running the rest of the program. Emulates a
real `JSR` (fake return address on the stack, so the routine's own `RTS`
ends the call at a trap address). The machine ends **STOPPED** at the
trap.

Stopped is not paused: the fake return address replaced the program's own
control flow, so **the program that was running is gone** — `c64 continue`
resumes from the trap, not from wherever the program was. Treat a call as
the end of that program run; reload (or `c64 run`) to play on.

- `REF` — the routine's address or symbol (must end in `RTS`).
- `--a N`, `--x N`, `--y N` — register values on entry (`$hex`/decimal).
- `--timeout SECS` (default `30`).

JSON: `{"registers", "pc_symbol", "stopped": true, "called"}`. Exit 1 on
timeout, machine left running — a timeout usually means the routine never
`RTS`es from this entry state (infinite loop, or REF isn't a subroutine
entry point).

The same operation is a YAML test step: `call: { routine: LABEL, a: 5 }`
followed by ordinary `assert:` steps (see `c64 test run`).

### `c64 profile`

Measure the cycle cost of one routine: a fake JSR at `REF` exactly like
`c64 call`, with CIA#2 timers A+B cascaded into a 32-bit hardware cycle
counter across the run. Reports the cycles from the routine's first
instruction through its own RTS.

- `REF` — address or symbol of a subroutine ending in RTS.
- `--with-irq` — leave interrupts live during the window (real-world cost;
  expect variance and rerun a few times). By default the I flag is set on
  entry so the KERNAL IRQ cannot land inside the measurement, and the
  flag's entry value is restored afterwards.
- `--timeout N` (default `30.0`) — give up after N seconds (machine left
  running, like `c64 call`).

Counts are wall cycles: badline DMA steals are included, which is the
frame-budget truth (blank the screen — `$D011` bit 4 — if you want the
bare instruction cost).

A run whose timers read back untouched — a raw count of 0, which no real
routine can cost — is reported as an error naming the likely cause (the CIA
pokes never reached the chip model, e.g. I/O banked out), never as a
too-small cycle count; the machine is left stopped at the trap, as on
success.

Perturbs CIA#2 timers A/B: they are left stopped on success, but a run
that times out leaves them running — the machine is running by then, so
they cannot be stopped safely. The same goes for the I flag: a timed-out
profile leaves it as profile set it (masked, unless `--with-irq`), so the
jiffy clock stays frozen and the keyboard stays dead until you clear it —
`c64 reg set FL ...` with the I bit off, or a session restart, recovers.
The machine ends STOPPED at the trap, like `c64 call` — and as with `call`,
the interrupted program is gone, not paused (see `c64 call`). Sessions
started before this verb existed need a `c64 session stop`/`start` once
(the old daemon predates a monitor argument profile uses).

JSON: `{"called", "cycles", "irq_masked", "registers", "trap"}`.

---

## Waiting

### `c64 wait`

Block until exactly one condition fires; reports which one. This is the primary
synchronization primitive for scripted use.

- `--text STR` — wait until STR appears on the screen.
- `--since` — with `--text`, fire only when the string appears *more times*
  than it did when the command started. Screen output persists, so a string
  already printed once (a `READY.` from the last load, a banner from the
  previous level) otherwise matches the stale copy and returns instantly.
  Use it when a real gap separates the trigger from the appearance — a
  countdown or animation frame due a second or two from now, a slow render
  finishing mid-screen. Two cases where it does not apply: a *fast*
  responder prints the new text before the wait command has even started,
  so the baseline already counts it and the wait holds out for a second
  occurrence that never comes; and on a screen that scrolls the count can
  stay flat as an old copy scrolls off the top. In both, anchor on the cell
  the text lands in instead (`c64 wait --mem '@6,0=20'`, and in YAML
  `assert: { mem: "@6,0", equals_text: "TOO HIGH" }`) — polling the byte
  has no count to race.
- `--mem ADDR<op>VALUE` — wait until the byte at ADDR compares to VALUE,
  where `<op>` is one of `=` `==` `!=` `>` `>=` `<` `<=` (e.g. `'$1000=42'`,
  `'$fb>=20'`, `'@6,0=20'`). The condition is split on the operator *before*
  the address is resolved, so a malformed one is reported as a bad condition
  rather than as an unknown symbol. Reach for an inequality whenever the
  value you are waiting on is a **counter or a progress byte**: waits poll
  (0.4 s), so a counter can step past an exact value between two polls and
  `'$fb=20'` then hangs forever, while `'$fb>=20'` cannot miss. Equality is
  right for a byte that *settles* — a saturating flag or state code.
- `--break [CK_ID]` — **resumes the machine if it is stopped**, then blocks
  until the NEXT checkpoint hit, and leaves it stopped there. It is
  "run to the next hit", the checkpoint counterpart of `c64 until` — so
  **never put `c64 continue` in front of it**: that resumes the machine
  yourself, the wait resumes again after the following hit, and you silently
  observe every *second* arrival. To step frame by frame, call
  `c64 wait --break` repeatedly with only inspection commands
  (`mem read`, `reg`, `screen`, `sprite`, `screen --png`) in between —
  inspection never advances the machine. Give an id to wait for that
  checkpoint only, so a leftover breakpoint can't intercept the wait meant
  for a watchpoint.
- `--idle` — wait until **the program has finished or errored**: the PC
  observed inside the KERNAL direct-mode input loop on three consecutive
  reads (0.1 s apart). This is the one wait that needs no prediction about
  what the program prints, so it is what to use after running something
  whose output you do not know yet — a first run, a debug hunt. Do *not*
  reach for `--text "READY."` instead: the reset banner already says
  `READY.` and matches instantly.
  Consecutive reads are the whole trick — the IRQ handler transits ROM, so
  a single sample landing in the loop proves nothing (measured at about one
  read in forty at an idle prompt). Two things it cannot distinguish,
  because the KERNAL routine is literally the same code: a program blocked
  on `INPUT`/`GET` reads as idle, and so does a machine that never started
  your program at all.
- `--timeout SECS` (default `30`).

Exactly one of `--text`/`--mem`/`--break`/`--idle` is required. JSON on fire:
`{"fired": "text"|"mem"|"idle", "elapsed"}` or `{"fired": "break",
"checkpoint", "pc", "pc_symbol", "elapsed"}`. Exit 1 on timeout (the error
carries the last screen for `--text`).

On timeout `c64 wait` exits 1 and the machine is **left running**;
checkpoints you set remain set (JSON gains `"machine": "running"`).

A `--idle` timeout is the **wedge detector**: the machine ran the whole
window without ever reaching direct mode, so it is still running or stuck in
a loop. The error says so and carries the PCs it last saw — feed one to
`c64 disasm` — and points at the wedged-machine playbook in the
`6502-debugging` skill, which takes it apart in three steps.

---

## Building

### `c64 build`

Assemble 6502 source (ca65 syntax) to a `.prg` plus a VICE label file.

- `SOURCE` — the `.s` file.
- `-o, --output PATH` — output `.prg` (defaults next to the source).
- `--model MODEL` (default `c64`) — selects the BASIC load address.

JSON: `{"prg", "labels"}`. No session required.

### `c64 package`

Package a program into an artifact any VICE user can run — a bare `.prg`, a
disk image with the program as its first (autostart) file, or a bootable
cartridge. Pure file operation; no session required. One program per artifact:
a disk carrying several files comes from `c64 disk build` and its manifest,
not from here.

- `SOURCE` — a `.s`, `.bas`, or `.prg` file (assembled/tokenized as needed).
- `-o, --output PATH` — the artifact; the extension picks the format:
  `.d64`/`.d71`/`.d81` build the `.prg` and write it to a fresh image
  (the `.prg` is kept beside it); `.crt` builds a cartridge; `.prg` (or
  omitted) builds just the program file. Existing outputs are overwritten.
- `--title NAME` — the CBM file/disk name (uppercased, max 16 characters;
  defaults to the source stem). For a cartridge it is the `.crt` name field
  (up to 32 characters).
- `--format prg|crt` — pick the format explicitly instead of by extension
  (disk images are always chosen by extension). It has to agree with the
  output name: `--format prg -o game.crt` and `--format crt -o game.d64` are
  both errors naming the conflict, rather than one of the two quietly winning.
- `--cart-type 8k|16k|ultimax` (default `8k`) — cartridge geometry. Cartridge
  output only: passing it for a `.prg` or a disk image is an error, the same
  way `--wrap` is, so a mistyped format never passes unnoticed.
- `--wrap` — force launcher-stub mode: build `SOURCE` to a `.prg` first, then
  wrap it in a launcher cartridge, instead of building cart-native code.
- `--model MODEL` (default `c64`) — selects the BASIC load address and
  is pinned in the reported run command.

**Cartridges.** A `.s` is treated as cart-native code (it owns the boot
sequence: export `cart_main`, or supply your own `STARTUP` segment) unless
`--wrap` says otherwise; a `.bas` or `.prg` is always wrapped, because an
existing program has to be copied down to its load address and started. The
`8k` and `16k` geometries are **not** interchangeable for `--wrap`: a 16K
cartridge maps ROM over `$8000-$BFFF`, which covers the BASIC interpreter at
`$A000`, so any program BASIC has to start — a tokenized `.bas`, or the
`10 SYS` stub the standard `.s` layout emits — must be wrapped as `8k`.
A program that loads into the mapped window itself — `$8000-$9FFF` for `8k`,
`$8000-$BFFF` for `16k` — is rejected for the same reason: the launcher's copy
would land under cart ROM and the jump would read the ROM back. So are the
other regions the launcher cannot copy into: `$A000-$BFFF` (under the BASIC
ROM, which the launcher never banks out), `$D000-$DFFF` (I/O — the copy would
poke the VIC/SID/CIA registers live), and `$E000-$FFFF` (under the KERNAL the
launcher runs through). Relocate it (below `$8000`, or into `$C000-$CFFF`), or
write it as cart-native code.
Wrapping into `ultimax` is rejected outright: the launcher chains through the
KERNAL, and an Ultimax cartridge replaces it. Multi-bank EasyFlash images come
from `c64 cart build`, not from here.

As with `.prg` builds, a failed rebuild leaves the outputs of the previous
successful build in place (ld65 and cartconv write nothing on error) — after
a build error, do not trust a `.crt`/`.bin` already sitting at the output
path without checking its timestamp.

Cartridge output is `x64sc -ntsc -cartcrt game.crt`; check it first with
`c64 cart verify`, which catches the boot failures that are silent on
hardware.

The recipient needs only stock VICE: `x64sc -ntsc game.d64` (or the
`.prg`) autostarts it, and from inside the emulator `LOAD"NAME",8` then
`RUN` works the traditional way. No ROMs or c64-tools ship in the artifact.
The video-standard flag matters for timing-sensitive programs: stock x64sc
boots its own default machine, so the run command pins `-ntsc` / `-pal` to
match the profile the program was tested on.

JSON: `{"prg", "image", "title", "run"}` — `run` is the exact command to
hand to the recipient (model pinned); `image` is `null` for `.prg`-only
output. For a cartridge the payload is the cartridge dict instead:
`{"crt", "bin", "labels", "title", "cart_type", "run", "bytes", "free"}`
(plus `"wrapped"`, `"load_addr"` and `"kind"` on the `--wrap` path) — `bytes`
is what the program actually spent and `free` what is left in the window.

---

## BASIC

### `c64 basic tokenize`

Tokenize a BASIC source file to a `.prg` with `petcat`.

- `SOURCE` — the `.bas` file. **petcat convention: keywords and string text
  must be lowercase** (lowercase ASCII becomes unshifted PETSCII, which
  displays as uppercase on the C64).
- `-o, --output PATH` — output `.prg`.
- `--model MODEL` (default `c64`) — selects the BASIC dialect.

JSON: `{"prg"}`. No session required.

### `c64 basic detokenize`

Print a `.prg` back as a BASIC listing.

- `PRG` — the tokenized program.
- `--model MODEL` (default `c64`).

JSON: `{"listing"}`. No session required.

### `c64 basic check`

Statically check a BASIC V2 source file for the errors `petcat` accepts and
the C64 rejects at RUN. Offline; no session. **Run it after writing or
editing BASIC and before `c64 run`** — every issue it finds is an emulator
round trip saved.

- `SOURCE` — the `.bas` file.

The check models the real BASIC cruncher, so crunched code (`fori=1to10`) is
parsed correctly and keyword fusion is detected: `total=5` tokenizes as
`TO TAL = 5` on a C64 and cannot run. Rules have stable IDs — `E…` means the
program will not run correctly, `W…` means legal but suspect.

Human output is one line per issue
(`ERROR E20: line 10: goto target 999 does not exist`), or `clean`. Exit
status is 1 if any error-severity issue was found, 0 otherwise (warnings
never fail the command).

JSON: `{"issues": [{"line", "severity", "rule", "message"}], "errors",
"warnings", "tokenized_bytes"}`. `tokenized_bytes` is the exact loaded size
(the 2-byte load address excluded); C64 BASIC has 38911 bytes free, so it is
the number to watch as a program grows.

### `c64 basic type`

Type a BASIC program into the running C64 through the keyboard (exercises the
real tokenizer; works mid-session).

- `SOURCE` — the `.bas` file.
- `--run` — type `RUN` afterwards.

JSON: `{"typed", "run"}`. Machine state preserved.

---

## Loading and running

### `c64 load`

Load a `.prg` on the running C64 via VICE autostart.

- `PRG` — the program file.
- `--run / --no-run` (default `--run`) — whether to RUN after loading.
- `--symbols PATH` — register a VICE label file for symbolic debugging.

JSON: `{"loaded", "run", "symbols"}`. Machine left running.

### `c64 run`

Build/tokenize `SOURCE` as needed, then load and RUN it. `.bas` is tokenized,
`.s` is assembled (its labels are registered on the session automatically),
`.prg` is loaded directly.

- `SOURCE` — a `.bas`, `.s`, `.prg`, or `.crt` file.

JSON: `{"source", "prg", "symbols"}`. Machine left running.

**Cartridges.** A `.crt` cannot be loaded into a running machine — it is
mapped at power-on — so `c64 run game.crt` stops the current session and boots
a fresh one of the same name and model with the cartridge attached (with no
session running it boots a `c64` — and so does a `--session NAME` that matches
nothing, which is the one verb where an unknown name is not an error; check
`c64 session list` if a boot lands somewhere unexpected). A `.lbl` beside the
`.crt` is registered on the new session, so symbols work straight away.

Only the name and the model survive the relaunch — the **launch flags do
not**. The CLI always reboots windowed and at normal speed, even if the
session it replaced was started `--headless --warp`; pass those back
explicitly with `c64 session start --cart` when you want them. (MCP note:
`c64_run` reboots headless + warp instead, following that server's convention
that a client is an automation rather than someone watching a window.)

JSON for a `.crt`: `{"cart", "session", "model", "symbols"}` — `symbols` is
`null` when there is no sibling `.lbl`.

---

## Disk images

### `c64 disk create`

Create a blank disk image.

- `IMAGE` — output path; the extension picks the type (`.d64`/`.d71`/`.d81`).
- `--label TEXT` (default `disk`).
- `--id NN` (default `00`).

JSON: `{"image", "label"}`.

### `c64 disk ls`

List a disk image's directory.

- `IMAGE` — the image file. JSON: `{"label", "files": [...], "blocks_free"}`.

### `c64 disk put`

Copy a host file onto a disk image.

- `IMAGE` — the image file.
- `FILE` — the host file.
- `NAME` (optional) — the CBM filename (defaults to the source stem, lowercased).

JSON: `{"image", "name"}`.

### `c64 disk get`

Copy a file off a disk image to the host.

- `IMAGE` — the image file.
- `NAME` — the CBM filename.
- `DEST` (optional) — output path (defaults to `NAME.prg`).

JSON: `{"image", "name", "dest"}`.

### `c64 disk boot`

Attach an image to the running C64 and LOAD+RUN its first file.

- `IMAGE` — the image file. JSON: `{"booted": PATH, "symbols": PATH|null}`.
  Machine left running.

Symbols: a sibling `IMAGE.lbl` (same stem) is registered on the session, so
`until`/`key hold --at` resolve the booted program's labels straight away —
the same convention a `.crt` enjoys under `c64 run`. When there is no
sibling, the `c64 disk build` convention is tried instead: the label file
of the image's *first* directory entry (`IMAGE.<cbm-name>.lbl`), which is
the file autostart runs. Silently skipped when neither exists.

### `c64 disk rename`

Rename a file on a disk image.

- `IMAGE` — the image file.
- `OLD` — the current CBM name.
- `NEW` — the new CBM name (validated: 1-16 chars, no `":,=*?`).

Errors when `OLD` is not on the disk — `c1541 -rename` reports that as
`ERR = 62, FILE NOT FOUND` and still exits 0, so the DOS status is what is
checked. A wildcard in `OLD` is refused by c1541 itself, so a rename can never
touch more than the one file you named.

JSON: `{"image", "old", "name"}`.

### `c64 disk rm` (alias: `c64 disk delete`)

Scratch a file from a disk image.

- `IMAGE` — the image file.
- `NAME` — the CBM filename, optionally with the CBM wildcards `*` (any tail)
  and `?` (any one character).

Wildcards scratch every match at once and the reported count stays honest:
`c64 disk rm game.d64 "al*"` removes both `alpha` and `album` and reports 2,
and `c64 disk rm game.d64 "*"` empties the whole disk. The count is the point —
c1541 answers a scratch that matched nothing with the same
`ERR = 01, FILES SCRATCHED` line at exit 0, so `c64 disk rm` errors when the
count comes back 0 instead of reporting a silent no-op. `"`, `:`, `,` and `=`
are refused: CBM DOS parses them inside a name and they would silently
retarget the scratch.

JSON: `{"image", "name", "deleted"}`.

### `c64 disk block read`

Read one 256-byte sector. `TRACK` is 1-based, `SECTOR` 0-based — on a 1541
image 18/0 is the BAM and 18/1 the first directory sector.

- `IMAGE TRACK SECTOR` — the sector to read.
- `-o, --output FILE` — write the raw bytes to a host file instead of
  hex-dumping them.

```
$ c64 disk block read game.d64 18 0
0000: 12 01 41 00 15 ff ff 1f 15 ff ff 1f 15 ff ff 1f  ..A.............
# text column: ascii
```

Out-of-range tracks and sectors are refused with the limit named
(`track 40 out of range (1-35 for d64)`).

JSON: `{"image", "track", "sector", "bytes", "hex"}` — `hex` is the sector as a
hex string and `bytes` the count. `c64 mem read` uses the same two key names,
but its `bytes` is a decimal int array, not a count.
With `-o`: `{"image", "track", "sector", "output", "bytes"}`, and a dump the
host refuses to write is reported as an error, not a traceback.

### `c64 disk block write`

Write a sector, wholesale or in part.

- `IMAGE TRACK SECTOR` — the sector to write.
- `--from FILE` — replace the whole sector from a file of exactly 256 bytes.
- `VALUES…` with `--offset N` — poke bytes at an offset, leaving the rest of
  the sector alone (`$hex`/`0x`/decimal, the same tokens `c64 mem write`
  takes: separate arguments or a single whitespace-separated string, which
  is what a shell variable expands to; a bad value is named by position).
  `--offset` belongs to this form only; giving it with `--from` is refused
  rather than ignored, since a whole-sector write has nothing to offset.

```
c64 disk block write game.d64 1 0 --from sector.bin
c64 disk block write game.d64 1 0 $de $ad --offset 4
```

Exactly one of `--from`/`VALUES` is required. Both forms are size-checked
first, because c1541's own answers are not usable: it truncates a
whole-sector write longer than 256 bytes at exit 0, blames a shorter one on
`floppy read failed` without naming the file or its size, and writes only the
bytes that fit when a poke runs off the end of a sector — again at exit 0.

JSON: `{"image", "track", "sector", "written", "offset"}`.

### `c64 disk validate`

Check and repair a disk image's block allocation — the CBM fsck. Rewrites the
BAM in place, like the real command.

- `IMAGE` — the image file.

`c1541 -validate` prints the same line and exits 0 whether it repaired
anything or not, so cleanliness is decided by comparing the image before and
after: a clean image comes back byte-identical. `repaired_blocks` is the size
of the change in blocks free, which can be 0 on an image that really was
repaired — the free total leaves the directory track out, so a repair confined
to it does not move it. `clean` is the flag to trust; `repaired_blocks` sizes
it, and `messages` explains it in words.

Structural damage is the case c1541 *does* speak up about, and it is not
treated as a failed command. A directory entry whose data block points off the
end of the disk makes `-validate` print `ERR = 65, NO BLOCK` — still at exit
0 — so each such status line is reported as a `messages` entry
(`validate reported no block (DOS error 65) at track 0 sector 40`) and `clean`
goes `false`. The command still exits 0: a finding about the image is what you
ran `validate` to get. That damage is also damage c1541 leaves alone —
measured, the image comes back byte-identical and `repaired_blocks` is
honestly 0.

JSON: `{"image", "clean", "blocks_free_before", "blocks_free_after",
"repaired_blocks", "messages"}`.

### `c64 disk build`

Build a populated disk image from a manifest in one reproducible step.

- `MANIFEST` — a `*.disk.yaml` file.
- `-o, --output IMAGE` — output path; the extension picks the type (`.d64`
  default, `.d71`, `.d81`). Defaults to the manifest's name with `.d64`.
- `--model` (default `c64`) — selects the BASIC load address/version for
  `.s`/`.bas` entries, and the video mode in the printed run hint.

```yaml
label: MYGAME             # <=16 chars, the disk header name
id: "01"                  # optional 2-char disk id (default "00")
files:
  - {src: loader.s,  name: "*"}      # "*" => use the disk label as the name
  - {src: level1.bin, name: level1}
  - {src: music.sid,  name: music}
```

```
$ c64 disk build game.disk.yaml
MYGAME  1 files, 1/664 blocks used (663 free)
built game.d64
run it with: x64sc -ntsc game.d64
```

The run hint carries the chosen model's video mode, so it is the command that
actually reproduces the build (`--model c64pal` prints the PAL form).

Files are written in listed order, so the first one autostarts. `.s` entries
are assembled, `.bas` tokenized, everything else copied verbatim. A manifest
that would overflow the disk — on blocks or on directory entries — is refused
before the image is formatted, so a build that cannot fit writes nothing at
all (c1541's own overflow handling would leave a truncated file and a corrupt
BAM). An unknown `--model` is refused up front too, for the same reason.

**Label files.** Every `.s` entry is assembled, and its VICE label file is
kept beside the *output image* as `<image-stem>.<cbm-name>.lbl` — a
`loader.s` written as `boot` onto `game.d64` leaves `game.boot.lbl` next to
it. Those are the paths `labels` maps each CBM name to; hand one to
`c64 load --symbols` to debug that file symbolically after booting the disk.
They are only ever written, never swept: rebuild from a manifest that dropped
or renamed an entry and the
previous run's `.lbl` stays where it is, so delete it yourself if a stale
symbol table would mislead you.

JSON: `{"image", "label", "labels", "files", "blocks_used", "blocks_free",
"blocks_total", "run"}` — `labels` is `{cbm-name: .lbl path}`, empty when no
`.s` entry produced one.

---

## Cartridges

A cartridge is mapped at power-on, not loaded: the machine boots straight into
it and there is nothing to `LOAD`. Build one with `c64 package --format crt`
(single-bank) or `c64 cart build` (multi-bank EasyFlash), check it with
`c64 cart verify`, and boot it with `c64 run game.crt` or
`c64 session start --cart game.crt`.

### `c64 cart build`

Build a multi-bank EasyFlash `.crt` from an `.ef.yaml` manifest. Offline; no
session required.

```
c64 cart build game.ef.yaml
```

- `MANIFEST` — the `.ef.yaml` file: a cartridge `name` and a `banks` map of
  bank number to `lo`/`hi` window sources (`.s` files are assembled against
  that window's own linker config; anything else is included verbatim). `name`
  defaults to the manifest stem with `.ef` dropped. Bank numbers must be
  `0-63`, `lo`/`hi` are the only window keys, and **bank 0 must have a `hi:`
  window** — that is the boot window holding the reset vector, and a manifest
  without one is rejected before anything is assembled.
- `-o, --output PATH` — output `.crt` (defaults next to the manifest).

Every window is exactly 8192 bytes and an overflow is a hard error naming the
bank, the window, and the overflow amount — never a silent truncation. The
per-bank fill table is always printed, so a window filling up is visible
before it overflows. The raw 1 MB image is kept beside the `.crt` as `.bin`,
and the per-bank label files are merged into one `.lbl` with every symbol
tagged by bank.

JSON: `{"crt", "bin", "labels", "title", "cart_type", "run", "banks",
"windows", "fill", "bytes", "free"}`.

### `c64 cart info`

Decode a `.crt` header and every CHIP packet. Offline; no session required —
the container is parsed directly, with no `cartconv` round trip.

```
c64 cart info game.crt
```

- `FILE` — the `.crt` image.

Human output is the cartridge name and hardware type, the memory mode with
its EXROM/GAME lines, then one row per CHIP packet (bank, window, load
address, size).

JSON: `{"path", "name", "hardware", "hardware_name", "version", "exrom",
"game", "mode", "banks", "chips": [{"bank", "window", "load_addr", "size",
"type", "offset"}], "total_bytes"}`.

### `c64 cart verify`

Check that a `.crt` should actually boot, without an emulator round trip.
Offline; no session required.

```
c64 cart verify game.crt
```

- `FILE` — the `.crt` image.

Catches the failures that are silent on hardware: a missing CBM80 signature
(the machine boots straight to BASIC and says nothing), a cold or reset vector
pointing outside the cartridge, a wrong image size, and an EasyFlash image
with no bank 0 HIROM window — which is where the reset vector lives. Prints
`ok` and exits 0 when clean, otherwise one line per problem and exit 1. A file
that is not a parseable `.crt` at all is an error, not a reason.

JSON, for an image that parses: `{"path", "ok", "reasons": [...]}` — `ok` is
`false` exactly when `reasons` is non-empty. An unparseable file takes the
usual CLI error path instead: `{"error": MESSAGE}` and exit 1, with no `ok`
key. (MCP note: `c64_cart_verify` is a verdict tool, so it hands that second
case back as data rather than raising — `{"path", "ok": false, "error":
MESSAGE}`, with no `reasons` key. Its parseable-image shape is the same
`{"path", "ok", "reasons"}` as here, so a caller must branch on which of
`reasons`/`error` is present.)

### `c64 cart dump`

Extract one bank window's bytes for offline disassembly. Offline; no session
required.

```
c64 cart dump game.crt --bank 3 --window hi -o bank3hi.bin
```

- `FILE` — the `.crt` image.
- `--bank N` (default `0`) — the bank to extract.
- `--window lo|hi` (default `lo`) — `lo` is the `$8000` window, `hi` the
  `$A000` one (the same window an Ultimax cartridge maps at `$E000`).
- `-o, --output PATH` (required) — where to write the raw window bytes.

Asking for a window the image does not have is an error listing the windows
it does have.

JSON: `{"path", "bank", "window", "bytes"}` — `path` is the file that was
**written** (`-o`), not the `.crt` it was read from.

### `c64 cart bank`

Report the live EasyFlash state of the running machine: the bank register at
`$DE00`, the mode register at `$DE02`, and the memory mode `$DE02` selects
(`$87` → `16k`, `$86` → `8k`, `$84` → `ultimax`, anything else `unknown`).

```
c64 cart bank
```

VICE lets these registers be read back; on real EasyFlash hardware they are
write-only, so treat this as a debugging aid, not a program interface. With
no EasyFlash cartridge mapped both addresses are open bus and read back `$FF`,
so `$DE02` decodes to mode `unknown` — the command is only meaningful on an
EasyFlash image. Inspection only — the machine's run/stop state is preserved.

JSON: `{"bank", "de00", "de02", "mode", "led"}` — `bank` is the raw `$DE00`
byte as an integer, `de00`/`de02` are the same two bytes as `$XX` strings, and
`led` is bit 7 of `$DE02`.

### `c64 cart convert`

Convert between a raw `.bin` and a `.crt` with VICE's `cartconv` — the escape
hatch for cartridge types this tool does not model natively. Offline; no
session required.

```
c64 cart convert rom.bin rom.crt --type normal --name "MY CART"
```

- `SOURCE` — the input file.
- `OUTPUT` — the output file.
- `--type TYPE` — a `cartconv` type id or name (see `cartconv --types`).
- `--name NAME` — the cartridge name written into the `.crt` header.

JSON: `{"source", "output", "cartconv"}` — `cartconv` is the tool's own
output.

---

## Sprites

### `c64 sprite status`

Decode the VIC-II sprite registers (`$D000-$D02E`) and the sprite data
pointers (live screen base + `$3F8`) into a per-sprite table: enabled,
x (MSB folded in), y, pointer/block address, color, and the multicolor /
expand / priority flags, plus the shared colors.

JSON: `{"sprites": [{"index", "enabled", "x", "y", "pointer",
"block_addr", "color", "multicolor", "expand_x", "expand_y",
"behind_text"}, ...], "shared": {"mc_color1", "mc_color2", "background",
"border"}}`. Machine state preserved.

### `c64 sprite show`

Render a sprite's 63-byte shape as ASCII art — 21 rows of 24 cells
(`█`/`·`; multicolor pairs render double-wide as `·▒█▓`).

- `INDEX` — sprite number 0-7 (its current pointer picks the block).
- `--block ADDR` — dump an explicit block (address or symbol) instead.

JSON: `{"rows", "block_addr", "multicolor"}`. Machine state preserved.

### `c64 sprite png`

Render a sprite's shape to a PNG, colored from the live registers
(sprite color, background, multicolor shared colors).

- `INDEX` — sprite number 0-7.
- `-o, --out PATH` (required) — output PNG.
- `--scale N` (default `8`) — integer nearest-neighbour upscale.
- `--block ADDR` — render an explicit block instead of the pointer target.

JSON: `{"png", "width", "height"}`. Machine state preserved.

### `c64 sprite from-png`

Convert any PNG (from an image model, a drawing tool, anywhere) into
ready-to-paste ca65 `.byte %...` sprite rows. Needs no session. The image
is resized to sprite resolution; hires sets pixels darker than 50%
luminance (transparent = clear), `--multicolor` quantizes to the C64
palette and records the pair-value mapping in the emitted header. Verify
the pasted result with `c64 sprite show` / `c64 sprite png`.

- `IMAGE` — the input image file. Must exist: a missing path is a usage error
  (exit 2), while a present-but-undecodable image is a runtime error (exit 1).
- `-o, --out PATH` — write the rows to a file instead of stdout.
- `--multicolor` — quantize to multicolor pairs instead of hires 1-bit.

JSON: `{"rows", "bytes", "out"}`.

### `c64 sprite encode`

Encode ASCII-art sprite(s) authored directly in a text file into 63
sprite bytes each — the first-class way to author a sprite by hand,
alongside `c64 sprite from-png` (image input) and the inverse of
`c64 sprite show` (bytes back to ASCII). Needs no session.

- `FILE` — one or more sprites, each exactly 21 rows, separated by a
  truly blank line (a row of all-background pixels is 12/24 spaces and is
  *not* a separator — only a zero-character line splits sprites).
  Multicolor rows (the default) are 12 characters using the friendly
  legend `' .#+'` (background/mc_color1/sprite-color/mc_color2); hires
  rows are 24 characters using `' #'`. Either mode also accepts the
  glyphs `c64 sprite show` emits (`·▒█▓` multicolor, `█·` hires — including
  its double-wide 24-char multicolor rows), so `show` output round-trips
  straight back through `encode`.
- `--hires` — encode as hires (1 bit/pixel, 24 chars/row) instead of the
  default multicolor pairs (12 chars/row).
- `--format asm|basic` (default `asm`) — `asm` emits ca65 `.byte %...` rows,
  one sprite row (3 bytes) per line, under a `spriteN:` label with a header
  comment — the same shape `c64 sprite from-png` emits, so hand- and
  image-authored sprites look identical in your source. `basic` emits `data`
  lines, one row (3 bytes) per line, decimal. Multiple sprites in one file
  get distinct labels (`sprite0`, `sprite1`, …).

  The `basic` keyword is **lowercase on purpose**: petcat reads lowercase
  source as unshifted PETSCII, and an uppercase `DATA` tokenizes to
  `STR$ ATN ATN` instead of the DATA keyword — the listing then fails at
  RUN, not at tokenize time.
- `--start-line N` — with `--format basic`, number the emitted lines from N
  so the block pastes straight into a `.bas` source. Without it the rows are
  unnumbered and a bare `data` line will not store in a BASIC program.
  Numbering runs on across every sprite in the file, so a multi-sprite file
  stays one ascending listing. Refused past line 63999.
- `--line-step N` (default `10`) — with `--start-line`, the gap between
  generated line numbers; 10 leaves room to insert lines later.
- `-o, --out PATH` — write the rendered rows to PATH instead of stdout.

Worked example (one 12x21 multicolor sprite — a small diamond, padded
with all-background rows). Every content row below is exactly 12
characters wide (trailing spaces are significant — some viewers trim
them visually, so count columns rather than trusting the rendering if
you retype this by hand):

```
   ..##..   
   .####.   
   ######   
   ######   
   .####.   
   ..##..   
            
            
            
... (12 more all-space rows to reach 21 total)
```

```
$ c64 sprite encode diamond.txt
; sprite 0, 24x21 multicolor (63 bytes: 3 bytes x 21 rows) — c64 sprite encode
; place in a 64-byte block; pointer = block_address / 64
sprite0: .byte %00000001, %01101001, %01000000
         .byte %00000001, %10101010, %01000000
         .byte %00000010, %10101010, %10000000
         .byte %00000010, %10101010, %10000000
         .byte %00000001, %10101010, %01000000
         .byte %00000001, %01101001, %01000000
         .byte %00000000, %00000000, %00000000
... (14 more all-background rows to reach 21 total)
```

JSON: `{"sprites": [[...63 ints...], ...]}` — one array per sprite in
FILE.

---

## Charsets

### `c64 charset encode`

Encode ASCII-art glyph sheets into 8 charset bytes per glyph — the charset
twin of `c64 sprite encode`. Needs no session.

- `FILE` — `name:` blocks (a bare `squid:` header works too), each exactly
  8 rows. Multicolor rows (the default) are 4 characters of `.123`: pair
  values `00 01 10 11` = background `$D021` / `$D022` / `$D023` / the
  cell's own color — the multicolor-*text* order, which is **not** the
  sprite legend's (sprites order their pairs differently, so the two
  commands deliberately do not share a legend). Hires rows are 8
  characters of `.#`. Blank lines and `#` comments are ignored (a comment
  cannot consist solely of legend characters at exactly row width). Block
  order is screen-code order.
- `--hires` — 1 bit/pixel, 8 chars/row (`.#`) instead of multicolor pairs.
- `--first-code N` (default `0`) — screen code of the first glyph; sets
  the `; code N: name` comments (the data itself is position-independent).
- `-o, --out PATH` — write the rendered rows to PATH instead of stdout.

Output is one contiguous block: a `glyphs:` label, 8 `.byte %binary` rows
per glyph (each echoing its art row as a trailing comment), and a
`glyphs_end:` label — so an installer copies with
`cpx #(glyphs_end - glyphs)` and patches over `CHARSET + code*8`. See the
cookbook's custom-character-set recipe for the RAM-charset setup.

JSON: `{"glyphs": [{"name", "bytes"}, ...]}` — 8 ints per glyph, file order.

---

## ROM tools

ROM tooling reads ROM bytes from *your* running emulator; nothing
Commodore-copyrighted is shipped with c64-tools.

### `c64 rom info`

Identify the loaded ROM set (names + content hashes).
JSON: `{"basic", "kernal", "editor", "hashes": {...}}`. Machine state preserved.

### `c64 rom disasm`

Disassemble live memory — RAM or ROM — with ROM + session label
annotations. Also reachable as `c64 disasm`.

- `START` — address or symbol (e.g. `CHROUT`, `$C000`, `828`).
- `LENGTH` (default `32`) — bytes to disassemble.

JSON: `{"start", "length", "lines": [...]}`. Machine state preserved.

### `c64 disasm`

The same command as [`c64 rom disasm`](#c64-rom-disasm) under a top-level
name — same arguments, same output. It lives at the top level because
reading the code you are stepping through is a debugging move, not a ROM
chore; the address may be anywhere, RAM included. See `c64 rom disasm`
above for the reference.

---

## Audio

### `c64 audio record`

Record the emulated SID to a WAV file. Give exactly one of:

- `--start PATH` — arm VICE's WAV recorder on PATH (made absolute; a
  relative path resolves against the current directory, never VICE's).
- `--stop` — disarm the recorder, finalizing the WAV, and unpin the speed.

Recording holds the machine at real time — warp off, `Speed` 100 — for the
whole window and restores both on `--stop`, so a 3-second capture costs 3
real seconds and nothing else should drive the session in between. The pin
is not optional: while warped VICE writes a **0-frame** WAV, so an unpinned
capture comes back empty rather than merely fast. Warp is not a resource on
VICE 3.10; it is cleared over VICE's text monitor, which `audio record`
starts on the session at need and leaves running.

JSON: `{"wav", "pinned": {"warp", "speed"}}` on `--start`, and
`{"wav", "bytes", "restored": {"warp", "speed"}}` on `--stop` — `bytes` is
the finished file's size, which is the honest evidence that the recording
landed (a 44-byte file is a header with no samples). A `--stop` with no
recording in flight still disarms and reports `{"wav": null}`.

### `c64 audio sidlog`

Log the SID's registers once per video frame to a JSONL file — what the
analysis side reads to work out what a tune actually played.

- `FRAMES` — how many frames to sample (at least 1).
- `PATH` — the JSONL file to write.

One line per frame and nothing else: `{"frame": n, "regs": [25 ints]}`,
where `regs[0]` is `$D400` and `regs[24]` is `$D418`. The whole block is
one 25-byte read taken at a frame boundary, so the registers in a record
are consistent with each other.

The sampling loop runs inside the session daemon, one frame per round trip
— a per-frame round trip from the client would cost about half a second
each. 100 frames take about 5 seconds at real time and a quarter of a
second warped. It leaves the machine running and does not touch the
emulator's speed, so pair it with `c64 audio record --start` when the frame
numbers have to line up with a WAV.

Frame numbers count captured frames from 0, and they are the elapsed frames
as long as a round trip is short against a frame. At real time it is, by a
wide margin — 200 samples covered 201 elapsed frames when measured. Warped,
an emulated frame is about as long as a round trip, a frame can slip past
between records (200 samples over 202 frames), and the command says so on
stderr and in `warning`: VICE hands the monitor control once per frame and
exposes no frame counter, so a missed frame can be flagged but never
counted. Pin real time when the timeline matters.

JSON: `{"path", "frames", "requested", "seconds", "warning"}` — `frames` is
what landed, `requested` what was asked for (they differ when the sampling
budget ran out), and `warning` is null or the line to show the user.

---

## Test runner

### `c64 test run`

Run one declarative YAML test. The runner boots its own fresh session
(headless + warp), loads the program, executes the steps fail-fast, and
reports pass/fail per step — capturing the screen at the point of failure.

- `YAML_FILE` — the test file.

The format:

```yaml
name: hello-world          # optional; defaults to the file name
machine: c64           # optional; any c64 model
program: hello.bas         # .bas/.s/.prg, path relative to this file;
                           #   built/tokenized as needed
cart: game.crt             # instead of program: — a .crt, a .s, or an
                           #   .ef.yaml manifest, path relative to this file;
                           #   built as needed and mapped at power-on
cart_type: 8k              # default 8k; only consulted when cart: is a .s
disk: game.disk.yaml       # instead of program:/cart: — a .d64/.d71/.d81 or
                           #   a .disk.yaml manifest, path relative to this
                           #   file; built as needed, attached to drive 8 and
                           #   autostarted (LOAD"*",8,1)
autorun: true              # default true: load and RUN. false = load only
                           #   (then drive it yourself with key steps)
timeout: 30                # default per-step timeout, seconds
steps:
  - wait:   { text: "READY." }              # screen text appears
  - key:    "run\n"                         # type keys (\n = RETURN)
  - wait:   { text: "HELLO", timeout: 5 }   # per-step timeout override
  - wait:   { text: "LIFTOFF", since: true } # only a NEW occurrence counts —
                                            #   for text a real gap away (a
                                            #   countdown, an animation frame)
  - wait:   { mem: "@6,0", equals: 20 }     # an instant reply races `since`:
  - assert: { mem: "@6,0", equals_text: "TOO HIGH" }  # anchor its cell instead
  - wait:   { mem: "$1000", equals: 42 }    # byte reaches a value
  - wait:   { idle: true }                  # the program has FINISHED or
                                            #   errored (BASIC back at direct
                                            #   mode) — the one wait that
                                            #   predicts nothing about the
                                            #   output. A timeout means the
                                            #   machine is still running or
                                            #   wedged, and reports the PCs
  - wait:   { mem: "$fb", at_least: 20 }    # counter passes a value —
                                            #   equals/not_equals/above/
                                            #   at_least/below/at_most, one
                                            #   per step — assert: takes
                                            #   the same six. Waits POLL, so a
                                            #   counter can step over an
                                            #   exact value: use at_least
                                            #   for anything that climbs
  - until:  { ref: mainloop, count: 3 }     # frame-step to a label; the
                                            #   machine STAYS stopped there
  - poke:   { addr: "$CB", values: [18] }   # write bytes (state-preserving)
  - call:   { routine: add_score, a: 5 }    # JSR one routine in isolation
                                            #   (unit test: poke inputs
                                            #   first, assert results after).
                                            #   A call DISCARDS the running
                                            #   program's PC: any until/wait
                                            #   after it runs against a dead
                                            #   program. Put call: steps
                                            #   last, or in their own spec
  - assert: { text: "READY." }              # substring on screen now
  - assert: { screen: "READY." }            # `screen` is an accepted alias for
                                            #   `text` — in `wait` too
  - assert: { mem: "@12,20", equals: 81 }   # screen cell row 12, col 20
  - assert: { mem: "@@12,20", mask: { and: "$0f", equals: [13] } }
                                            # the cell's COLOR ($D800
                                            #   matrix); masked because
                                            #   color RAM reads back 4-bit
  - assert: { mem: "$0400", equals_text: "HELLO" }  # screen RAM as text
  - assert: { mem: "$1000", equals: [1, 2, 3] }     # exact bytes
  - assert: { mem: "@3,7", equals_any: [[81], [98]] }  # any alternative
  - assert: { mem: "@3,7", mask: { and: "$7f", equals: [81] } }
                                            # masked compare — e.g. ignore
                                            #   the reverse-video bit
  - assert: { mem: "$D020", mask: { and: "$0f", equals: [0] } }
                                            # same, for the 4-bit VIC-II
                                            #   color registers: a read of
                                            #   $D020 returns $F0, not $00
  - assert: { mem: "$1000", between: { min: 50, max: 54 } }  # byte range
  - assert: { reg: pc, in_range: ["$C000", "$E000"] }
  - assert: { reg: a, equals: "$2A" }
  - sample: { mem: "$D000", as: x0 }        # capture a byte under a name
  - assert: { mem: "$D000", differs: x0 }   # compare against a sample:
  - assert: { mem: "$D000", greater_than: x0 }   # differs / greater_than /
  - assert: { mem: "ballx", less_than: x0 }      # less_than (plain bytes —
                                            #   wraparound is yours to handle)
  - assert: { mem: "$D000", unchanged: x0 } # equality against a sample:
                                            #   "this byte did NOT change"
                                            #   (holds, pauses, game over)
```

Step kinds: `wait` (poll until true or timeout — fails the test on
timeout), `key` (feed keyboard input — fills the buffer and returns
immediately; it does not wait for the machine to consume the keys, so
follow it with a `wait` before asserting), `assert` (check once, now),
`poke` (write bytes; `value:` or `values:`), `until` (run to `ref`
`count` times via a checkpoint and leave the machine stopped there —
deterministic frame stepping; fails on timeout with the reached count),
and `call` (JSR `routine` in isolation with optional `a`/`x`/`y` on
entry, stopping at its RTS — routine-level unit testing; fails on
timeout, which usually means the routine never returns from that entry
state).
The screen-substring check is spelled `text` in both `wait` and `assert`,
and `screen` is accepted as an alias in both — so a copied step survives a
change of verb.
A `poke` right before an `until` is the held-key protocol (`c64 key
hold` as steps). Step addresses accept everything the CLI does —
`$hex`/`0xhex`/decimal, symbols from the built program's label file,
`symbol+offset`, `@row,col`, and `@@row,col` (color RAM).

**Cartridge tests.** A spec sets `cart:` **or** `program:`, never both —
setting both is an error, because a cartridge boots itself and there is
nothing to autostart. `cart:` is resolved relative to the spec file (exactly
like `program:`) and takes one of three things: a `.crt`, used as-is; a `.s`,
built as a single-region cartridge whose geometry comes from `cart_type:`
(default `8k`, one of `8k`/`16k`/`ultimax`); or an `.ef.yaml`/`.ef.yml`
manifest, built as an EasyFlash image. Anything else is an error.

With `cart:` set the runner boots its session with the image attached and goes
**straight to the steps**: there is no `READY.` gate to wait for and `autorun:`
does not apply, because the cartridge is already running its own code. Symbols
come from the build's label file for a `.s` or a manifest; for a ready-made
`.crt` a sibling `.lbl` of the same stem is picked up if it is there, and
silently skipped if it is not.

**Disk tests.** `disk:` names either a ready-made `.d64`/`.d71`/`.d81` or a
`.disk.yaml`/`.disk.yml` manifest that `c64 disk build` turns into one; the
path is resolved relative to the spec file, and anything else is an error. It
is exclusive with both `program:` and `cart:` — a disk owns the boot, so a
program named beside it would never load and a cartridge would run instead of
the image ever being started.

Unlike a cartridge, a disk **does** wait for `READY.`: attaching an image only
fills drive 8, so the runner then autostarts the image, which issues
`LOAD"*",8,1` — the disk's *first* file, which is why `c64 disk build` writes a
manifest in listed order. `autorun:` applies as usual, including its gate:
`autorun: false` loads without running and the runner then waits for the load
to finish before the first step, which matters more here than for a `.prg`
(serial loading is seconds, not milliseconds). Symbols follow the same rule as
the CLI: a sibling `.lbl` of the image's stem, else the label file `disk build`
kept for the image's first entry, silently skipped when absent.

JSON: `{"passed", "tests": [<report>]}`. Exit 1 if the test fails. A
spec-level error — a malformed spec, a missing program, a build or session
failure — emits the same envelope with an added message and no results:
`{"error", "passed": false, "tests": []}`. So `tests` is always present, and
a harness can read the payload the same way whether the test ran or the spec
never loaded.

### `c64 test programs`

Run every example-program directory as a generated test. A directory qualifies
when it holds an `expect.txt` (each non-blank line becomes a `wait: {text}`
step) plus either a `program.bas`/`program.s` or a `test.yaml` with a `cart:`
or `disk:` key — a cartridge and a disk image have no program file of their
own, and a source file sitting beside one is that image's *input*, never a
second thing to autostart. An optional
`test.yaml` supplies the rest of the spec; its own steps run after the
`expect.txt` ones. A generated spec takes the same defaults a written one
does, including the 30-second per-step `timeout:`, which a `test.yaml` can
raise for a slow program.

- `DIRECTORY` (default `tests/programs`).

JSON: `{"passed", "tests": [...]}`. Exit 1 if any program fails. A spec-level
error — one program's spec failing to load, or no example programs in
`DIRECTORY` at all — emits the same `{"error", "passed": false, "tests": []}`
envelope `test run` does, so `tests` is always present here too.
