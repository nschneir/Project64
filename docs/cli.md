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
  - `--session, -s NAME` — target a specific session by name. Must come
    before the subcommand.
  - `--version` — print `c64 <version>` and exit. Must come before the
    subcommand.
  - `--help` — print usage and exit. Works on every command and group, in
    either position (e.g. `c64 session start --help`).
- **Numbers.** Address and value arguments accept `$hex` (e.g. `$0400`),
  `0xhex`, or decimal. Where a label file is registered on the session (via
  `c64 build`/`c64 run` of assembly, or `c64 load --symbols`), a **symbol
  name** is accepted anywhere an address is. Addresses additionally accept
  an **offset** (`alienX+49`, `tick-1`, `dots+$52`, `$0400+40`) and a
  **screen cell** `@row,col`
  (e.g. `@23,18`), resolved against the machine's LIVE screen base
  (relocation-aware; 40×25, $0400 at power-on).
- **Exit codes.** `0` on success; `1` on error, on a `c64 wait` timeout, or on
  a failing `c64 test`.
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
- `--headless` — suppress the VICE window (video/audio dummied).
- `--warp` — run at maximum speed (recommended for automation).
- `--disk PATH` — attach a `.d64`/`.d71`/`.d81` image to drive 8 at boot.

Human: `started c64 session 'c64' (pid 1234, monitor port 6510)`.
JSON: `{"name", "model", "pid", "port"}`. Machine left running.

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

Type text into the running C64's keyboard buffer (`\n` = RETURN). Use it to
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
- `--timeout SECS` (default `30`) — per-frame wait limit.

JSON: `{"registers", "pc_symbol", "stopped": true, "frames"}`. On a frame
timeout: exit 1, machine left running, checkpoint removed.

---

## Memory

### `c64 mem read`

Read emulated memory and print a hex dump (16 bytes/line with an ASCII column).

- `ADDR` — start address (`$hex`/`0x`/decimal/symbol).
- `LENGTH` (default `256`) — number of bytes.
- `--decimal` — render decimal values instead of a hex dump.

JSON: `{"addr", "length", "hex", "bytes"}` (`hex` is the bytes hex-encoded;
`"bytes"` is always present as a decimal int array). Machine state
preserved.

### `c64 mem get`

    c64 mem get ADDR [LENGTH]

Print LENGTH (default 1) byte values at ADDR in decimal — bare,
space-separated, pipe-friendly (`[ $(c64 mem get score) -gt 0 ]`). JSON:
`{"addr": N, "values": [ints]}`. ADDR is `$hex`/`0x`/decimal or a symbol
from the loaded label file. Does not disturb run/stop state. (MCP note:
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
- `VALUES...` — one or more byte values (`$hex`/`0x`/decimal).
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
PC is annotated with the nearest symbol when a label file is loaded.

JSON: `{"registers": {"PC", "A", "X", "Y", "SP", "FL", ...}, "pc_symbol"}`.
Machine state preserved.

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

- `REF` — the routine's address or symbol (must end in `RTS`).
- `--a N`, `--x N`, `--y N` — register values on entry (`$hex`/decimal).
- `--timeout SECS` (default `30`).

JSON: `{"registers", "pc_symbol", "stopped": true, "called"}`. Exit 1 on
timeout, machine left running — a timeout usually means the routine never
`RTS`es from this entry state (infinite loop, or REF isn't a subroutine
entry point).

The same operation is a YAML test step: `call: { routine: LABEL, a: 5 }`
followed by ordinary `assert:` steps (see `c64 test run`).

---

## Waiting

### `c64 wait`

Block until exactly one condition fires; reports which one. This is the primary
synchronization primitive for scripted use.

- `--text STR` — wait until STR appears on the screen.
- `--since` — with `--text`, fire only when the string appears *more times*
  than it did when the command started. Screen output persists, so a
  repeated prompt (`YOUR GUESS?`) or verdict (`TOO HIGH`) otherwise matches
  the stale copy already on screen and returns instantly. On a screen that
  scrolls the count can stay flat as an old copy scrolls off; anchor on a
  cell there instead (`c64 wait --mem '@6,0=20'`).
- `--mem ADDR=VALUE` — wait until the byte at ADDR equals VALUE (e.g.
  `'$1000=42'`).
- `--break [CK_ID]` — wait until a checkpoint fires; **leaves the machine
  stopped**. Give an id to wait for that checkpoint only, so a leftover
  breakpoint can't intercept the wait meant for a watchpoint.
- `--timeout SECS` (default `30`).

Exactly one of `--text`/`--mem`/`--break` is required. JSON on fire:
`{"fired": "text"|"mem", "elapsed"}` or `{"fired": "break", "checkpoint",
"pc", "pc_symbol", "elapsed"}`. Exit 1 on timeout (the error carries the last
screen for `--text`).

On timeout `c64 wait` exits 1 and the machine is **left running**;
checkpoints you set remain set (JSON gains `"machine": "running"`).

---

## Building

### `c64 build`

Assemble 6502 source (ca65 syntax) to a `.prg` plus a VICE label file.

- `SOURCE` — the `.s` file.
- `-o, --output PATH` — output `.prg` (defaults next to the source).
- `--model MODEL` (default `c64`) — selects the BASIC load address.

JSON: `{"prg", "labels"}`. No session required.

### `c64 package`

Package a program into an artifact any VICE user can run — a bare `.prg`, or
a disk image with the program as its first (autostart) file. Pure file
operation; no session required.

- `SOURCE` — a `.s`, `.bas`, or `.prg` file (assembled/tokenized as needed).
- `-o, --output PATH` — the artifact; the extension picks the format:
  `.d64`/`.d71`/`.d81` build the `.prg` and write it to a fresh image
  (the `.prg` is kept beside it); `.prg` (or omitted) builds just the
  program file. Existing outputs are overwritten.
- `--title NAME` — the CBM file/disk name (uppercased, max 16 characters;
  defaults to the source stem).
- `--model MODEL` (default `c64`) — selects the BASIC load address and
  is pinned in the reported run command.

The recipient needs only stock VICE: `x64sc -ntsc game.d64` (or the
`.prg`) autostarts it, and from inside the emulator `LOAD"NAME",8` then
`RUN` works the traditional way. No ROMs or c64-tools ship in the artifact.
The video-standard flag matters for timing-sensitive programs: stock x64sc
boots its own default machine, so the run command pins `-ntsc` / `-pal` to
match the profile the program was tested on.

JSON: `{"prg", "image", "title", "run"}` — `run` is the exact command to
hand to the recipient (model pinned); `image` is `null` for `.prg`-only
output.

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

- `SOURCE` — a `.bas`, `.s`, or `.prg` file.

JSON: `{"source", "prg", "symbols"}`. Machine left running.

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

- `IMAGE` — the image file. JSON: `{"booted": PATH}`. Machine left running.

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

- `IMAGE` — the input image file.
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
  image-authored sprites look identical in your source. `basic` emits `DATA`
  lines, one row (3 bytes) per line, decimal; the `DATA` lines carry no line
  numbers — add them yourself before the listing will store or run in a real
  BASIC program. Multiple sprites in one file get distinct labels
  (`sprite0`, `sprite1`, …).
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

## ROM tools

ROM tooling reads ROM bytes from *your* running emulator; nothing
Commodore-copyrighted is shipped with c64-tools.

### `c64 rom info`

Identify the loaded ROM set (names + content hashes).
JSON: `{"basic", "kernal", "editor", "hashes": {...}}`. Machine state preserved.

### `c64 rom disasm`

Disassemble live memory with ROM + session symbol annotations.

- `START` — address or symbol (e.g. `CHROUT`).
- `LENGTH` (default `32`) — bytes to disassemble.

JSON: `{"start", "length", "lines": [...]}`. Machine state preserved.

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
autorun: true              # default true: load and RUN. false = load only
                           #   (then drive it yourself with key steps)
timeout: 30                # default per-step timeout, seconds
steps:
  - wait:   { text: "READY." }              # screen text appears
  - key:    "run\n"                         # type keys (\n = RETURN)
  - wait:   { text: "HELLO", timeout: 5 }   # per-step timeout override
  - wait:   { text: "TOO LOW", since: true }  # only a NEW occurrence counts
  - wait:   { mem: "$1000", equals: 42 }    # byte reaches a value
  - until:  { ref: mainloop, count: 3 }     # frame-step to a label; the
                                            #   machine STAYS stopped there
  - poke:   { addr: "$CB", values: [18] }   # write bytes (state-preserving)
  - call:   { routine: add_score, a: 5 }    # JSR one routine in isolation
                                            #   (unit test: poke inputs
                                            #   first, assert results after)
  - assert: { screen: "READY." }            # substring on screen now
  - assert: { mem: "@12,20", equals: 81 }   # screen cell row 12, col 20
  - assert: { mem: "$0400", equals_text: "HELLO" }  # screen RAM as text
  - assert: { mem: "$1000", equals: [1, 2, 3] }     # exact bytes
  - assert: { mem: "@3,7", equals_any: [[81], [98]] }  # any alternative
  - assert: { mem: "$D020", mask: { and: "$0f", equals: [0] } }
                                            # masked compare — VIC-II color
                                            #   registers are 4-bit, so a
                                            #   read of $D020 returns $F0
  - assert: { mem: "$1000", between: { min: 50, max: 54 } }  # byte range
  - assert: { reg: pc, in_range: ["$C000", "$E000"] }
  - assert: { reg: a, equals: "$2A" }
  - sample: { mem: "$D000", as: x0 }        # capture a byte under a name
  - assert: { mem: "$D000", differs: x0 }   # compare against a sample:
  - assert: { mem: "$D000", greater_than: x0 }   # differs / greater_than /
  - assert: { mem: "ballx", less_than: x0 }      # less_than (plain bytes —
                                            #   wraparound is yours to handle)
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
A `poke` right before an `until` is the held-key protocol (`c64 key
hold` as steps). Step addresses accept everything the CLI does —
`$hex`/`0xhex`/decimal, symbols from the built program's label file,
`symbol+offset`, and `@row,col`.

JSON: `{"passed", "tests": [<report>]}`. Exit 1 if the test fails.

### `c64 test programs`

Run every example-program directory (one with an `expect.txt`) as a generated
test.

- `DIRECTORY` (default `tests/programs`).

JSON: `{"passed", "tests": [...]}`. Exit 1 if any program fails.
