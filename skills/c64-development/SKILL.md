---
name: c64-development
description: Use when developing, running, or debugging Commodore 64 software (Commodore BASIC or 6510/6502 assembly) on the VICE emulator with the c64 CLI or the c64-tools MCP server. Covers the build/run/observe/debug loop, the stopped-state discipline, C64 text encodings, graphics and sprites, and the memory map.
---

# Developing for the Commodore 64

This skill drives an emulated Commodore 64 through the `c64` command line (or
the equivalent `c64-tools` MCP tools). Full command reference: `docs/cli.md`.
Every command takes `--json` for machine-readable output.

**Finding the binary.** `c64` is installed into this project's virtualenv,
not onto `PATH` — invoke it as `.venv/bin/c64` from the repository root, or
`source .venv/bin/activate` once per shell. If `.venv` is missing, stop and
say so rather than substituting another environment.

**Using MCP instead of the CLI?** The tools map mechanically — `c64 screen`
→ `c64_screen_text`, `c64 break add` → `c64_break_add`, `c64 basic check`
→ `c64_basic_check`, and so on — with the
same sessions, semantics, and stopped-state rule. Known differences: `c64 wait`
is split into `c64_wait_text` / `c64_wait_mem` / `c64_wait_break` /
`c64_wait_idle`; top-level `c64 disasm` is an alias for `c64 rom disasm`, so
its tool keeps the older name `c64_rom_disasm` (there is no `c64_disasm`); wait
timeouts return `{"fired": null, ...}` as data instead of an error.
Every command has a tool; `c64 basic tokenize`/`detokenize`, `c64 sprite
encode`, `c64 charset encode`, and `c64 break enable`/`disable` map to
`c64_basic_tokenize`, `c64_basic_detokenize`, `c64_sprite_encode`,
`c64_charset_encode`, `c64_break_enable`, and `c64_break_disable`.
Every `c64 disk` and `c64 cart` verb has a twin; `c64 watch remove` is the
same command as `c64 break remove`, so `c64_break_remove` removes watchpoints
too, and `c64 mem get` is only a print-formatting variant of `c64_mem_read`.
The complete map — every tool, the command it twins, and the one-line
difference where there is one — is `docs/mcp.md`.

**Driving a game move by move? Use MCP.** Each `c64` CLI invocation is a
fresh Python process — measured at ~130 ms of startup on a 2026 laptop,
before the emulator does anything. Steering a snake for a few hundred moves
at 3-4 calls per move spends minutes in process startup while the emulated
machine, at warp, is idle. The MCP tools run in a live process and have no
such floor. The CLI is right for a handful of commands; a loop wants MCP.

The rule inverts for a one-shot sequence where the *gap between* two commands
is what matters — arming a capture the instant a `wait` returns, say. Two tool
calls put a model round trip in that gap; one shell line with `&&` closes it
to process startup. Reach for the CLI when the timing between commands is part
of what you are doing, and for MCP when the number of commands is.

## The loop

Write → run → observe → fix:

1. Write BASIC (`.bas`) or 6502 assembly (`.s`).
2. For BASIC, `c64 basic check FILE` first — it catches keyword fusion
   (`total=5` tokenizes as `TO TAL=5` and cannot run), missing GOTO/GOSUB
   targets, out-of-range POKEs, non-V2 keywords and oversize programs without
   an emulator round trip. Fix every `E…` before running.
3. `c64 run FILE` — tokenizes/assembles as needed, loads, and RUNs.
4. Observe with `c64 screen` (decoded screen text) — this is the primary way
   to see output. Use `c64 wait --text "..."` to block until expected output
   appears; loading and running take a few emulated seconds even in warp, so
   never assume a program has finished — wait for a signal.
   **Pick that signal out of your own output.** `c64 run` resets the
   machine, so a wait cannot match the *previous* run's text — but the
   reset restores the boot banner, and a wait for `READY.`, `BASIC`, `*`
   or `64K` matches *that* immediately and returns before your program has
   printed anything. Wait on a distinctive string the program itself emits,
   or (if it clears the screen first) on a cell the clear must blank:
   `c64 wait --mem '$042C=32'`. When you cannot predict the output at all —
   a first run, a program you are debugging — use `c64 wait --idle`, which
   blocks until the program has *finished or errored* rather than until it
   prints something; its timeout is then your wedge detector.
   For a text-mode program, decoded text is also the *cheapest* observation —
   prefer it over `--png` for verification, and read color back from the
   registers (`c64 mem read '$D020' 2` — bytes come back in address order, so
   the first is `$D020`, the border, and the second is `$D021`, the
   background) rather than from an image. Reach for
   `c64 screen --png` when the appearance itself is the artifact (sprites,
   bitmap modes, a screenshot for a human); add `--border` when the border
   color matters, or it is cropped out.
5. Fix and repeat.

Start a machine with `c64 session start` before anything else, and
`c64 session stop` when done.

## Sessions and models

`c64 session start` boots a C64 (NTSC, the default — model name `c64`). Add
`--warp` to run at full speed for automation and `--headless` to keep it out
of the way: no window at all on SDL builds, and on GTK builds (what's
installed here) it starts minimized and never steals focus. `--model
c64pal` boots the PAL variant — same machine, 50 Hz frame
rate and a slightly different CPU clock; pick it only when timing against
PAL software. Both run BASIC 2.0 with 38911 bytes free.

The CPU is the **6510**: a 6502 core (same instruction set ca65 assembles)
plus an on-chip port at `$00/$01` that banks ROMs and I/O in and out — see
references/zero-page.md before touching `$01`.

## Writing BASIC

BASIC sources follow the `petcat` convention: **write keywords AND string
text in lowercase.** Lowercase ASCII maps to unshifted PETSCII, which the C64
displays as uppercase — so `10 print "hello"` shows on screen as
`10 PRINT "HELLO"`. Writing uppercase in the source produces shifted PETSCII,
which shows as graphics characters instead of letters. This is the single most
common mistake.

- `c64 basic check prog.bas` — static check before running (see below).
- `c64 run prog.bas` — tokenize, load, and RUN in one step.
- `c64 basic type prog.bas --run` — type the program in through the keyboard
  instead, which works mid-session and exercises the real ROM tokenizer.
- `c64 basic tokenize` / `c64 basic detokenize` — convert between `.bas` and
  `.prg` without a session (`c64_basic_tokenize` / `c64_basic_detokenize`
  over MCP).

Conventions `c64 basic check` enforces (know them even without running it):

- **Never embed a keyword in a variable name.** The C64 tokenizes greedily at
  every character, so `total`, `score` and `paint` become `TO TAL`, `SC OR E`
  and `PA INT` — use `tot`, `sc`, `pnt`. petcat accepts all of them silently;
  the machine does not.
- **Only the first two characters are significant**, so `speed` and `spent`
  are the *same* variable.
- **Logical lines ≤ 80 characters.** petcat tokenizes longer lines and they
  run, but the screen editor cannot re-enter them, and >255 tokenized bytes
  break outright.
- **Line numbers 0–63999**, ascending, no duplicates — and in steps of 10, so
  a later insertion doesn't force a renumber.
- **BASIC V2 keywords only.** No 3.5/7.0 words (`else`, `do`/`loop`, `sound`,
  `graphic`, `joy`, `volume`, …): on a C64 they tokenize as fused variables
  and fail at RUN.
- **Program + variables ≤ 38911 bytes.** `c64 basic check --json` reports
  `tokenized_bytes`; watch it as a game grows.

## Driving an interactive program

A program that blocks on `INPUT` or `GET` is driven by feeding the keyboard
and reading the screen back. The trap: **screen output persists**, so every
prompt and verdict is still on screen the next time round, and a bare
`c64 wait --text "YOUR GUESS?"` matches the stale copy and returns
immediately. Two ways through:

1. Anchor on the cell the text lands in — `c64 wait --mem '@6,0=20'`, or in
   a YAML test `assert: { mem: "@6,0", equals_text: "TOO HIGH" }`. **The
   default for turn-by-turn play**: `wait --mem` polls the byte directly, so
   there is no occurrence count to race and nothing breaks when an old copy
   scrolls off. `c64 screen --numbered` prints row indices and a column
   ruler so you can read the reference off the screen instead of computing
   it.
2. `c64 wait --text STR --since` — fires only on an occurrence that appears
   after the command starts. Use it when a real gap separates the trigger
   from the appearance (an animation, a multi-second countdown, a slow
   render). It does **not** fit an instant responder: `--since` takes its
   baseline when the wait starts, so a program that answers faster than a
   CLI round-trip (or a YAML `key` step) has already printed the new text
   into that baseline, and the wait hangs out for a second occurrence that
   never comes.

Under MCP both waits are separate tools — `c64_wait_mem` and `c64_wait_text`
(which takes the same `since` flag, with the same caveat); see "Using MCP
instead of the CLI?" above.

`c64 key type` fills the keyboard buffer and returns — it does **not** wait
for the machine to consume the keys. Always follow it with a `wait` before
asserting; asserting straight after a `key` is a race that passes on a fast
host and fails on a slow one.

## Writing assembly

6502 assembly is assembled with ca65/ld65 via `c64 build` or run directly with
`c64 run prog.s`. A C64 program loads at `$0801` and needs a small BASIC `SYS`
stub (`10 SYS 2061`) so `RUN` starts it; the `6502-assembly` skill has the
working skeleton and the details. `c64 run` on a `.s` file automatically
registers the assembled label file on the session, so you can immediately set
symbolic breakpoints like `c64 break add start`.

## Sibling skills

- Writing 6502/6510 assembly? The `6502-assembly` skill has the program
  skeleton, the ca65 conventions and the gotchas.
- Hunting a crash, a corrupted byte or a register clobber? The
  `6502-debugging` skill has the systematic procedures.
- Building a cartridge (8K/16K/Ultimax or a bank-switched EasyFlash game)?
  Use the `cartridge-programming` skill — cartridges boot themselves, so the
  failure modes are different from a `.prg`: there is no load address, no
  `READY.`, and a broken header just boots to BASIC without a word.
- Loading levels, music or save data off a disk *at runtime*? Use the
  `disk-io-programming` skill — the secondary address decides where a file
  lands, and getting it wrong is the classic disk bug.

## Graphics and sprites

Character graphics (screen RAM `$0400` + color RAM `$D800`) are fully
observable through `c64 screen` — prefer them where text-level observation
matters. The VIC-II's 8 hardware sprites are the idiomatic way to move
things smoothly: registers, data layout, and the SID sound registers are in
references/hardware.md, and working recipes are in the cookbook. In the
Project64 repo, `docs/graphics-and-sprites.md` adds the house rules for demo
programs — which graphics modes a demo may use, where evidence screenshots
are committed, and what the test tier keeps. Read it if that file is
present; everything needed to write and verify the code itself is here and
in the cookbook. One hard rule: sprites are
invisible to `c64 screen` text — inspect them with `c64 sprite status`
(decoded registers), `c64 sprite show` (ASCII art), and `c64 sprite png`
(exact rendered shape), and assert on registers and state bytes. Screen
relocation is followed automatically by `c64 screen` and `@row,col`.

**More than eight objects, and things that must happen at a known
scanline.** Eight sprites is a per-scanline ceiling, not a per-screen one:
the cookbook's *sprite multiplexer* recipe sorts objects by Y, hands each
the first register free by the time the beam reaches it, and — the part
that makes it testable — publishes a displayed count and an overflow count
as plain memory, because a screenshot shows the result and never the
budget. Its reposition schedule is played out by the *raster event chain*
recipe, one sorted `(line, kind, arg)` list per frame with a frame marker
that paces the main loop. Read both before writing a raster handler by
hand; between them they carry the two subtleties that cost the most time
(arming `$D012` past the live raster, and the `$D019` re-acknowledge on the
way out).

**Anchoring an observation on a moving program.** Anything you sample or
screenshot while the machine runs is a race — at warp the ball has flown on
before the capture lands. Park the machine at the exact moment first, then
inspect:

- **Assembly:** `c64 until mainloop` — frame-stepping on a label.
- **BASIC (no labels to break on):** have the program `poke` a byte at the
  moment of interest (a spare zero-page location: 251-254 / `$FB`-`$FE` are
  free), then `c64 watch add '$FC' --store` + `c64 wait --break`. The machine
  stops on that write, so `mem read`, `sprite status` and
  `screen --png` all see the instant the event happened, not a frame later.
  Give each event a distinct code in that byte and you can wait for a
  *specific* one. A store watchpoint on a VIC-II position register
  (`c64 watch add '$D001' --store`) is the same trick for per-frame stepping.

This is also what makes a BASIC graphics demo testable: the state byte is a
non-graphics signal a YAML test can assert on, which register-only tests
cannot express.

**Sprites: authoring with generative AI.** The primary path: obtain a small
image of the shape you want — from any image-generation model, a drawing
tool, or by rendering one yourself — then convert it:

1. `c64 sprite from-png art.png` (add `--multicolor` for 3-color shapes) —
   emits ready-to-paste `.byte %...` rows; commit the rows, never the image.
2. Paste the rows into your source, place the block, set the pointer
   (`block = address / 64`).
3. Load and **verify against intent**: `c64 sprite show N` for a quick
   terminal check, `c64 sprite png N -o check.png` for the exact rendered
   shape with live colors.

Fallback when no image is at hand: author the `.byte %...` rows directly —
the binary literals read as a picture in the source (see the cookbook's
sprite recipes and `tests/programs/sprite-ball/`).

## Debugging

Breakpoints and watchpoints are set while the machine runs, then you block on
them:

1. `c64 break add SYMBOL` (or an address) — set an execution breakpoint. It
   also accepts `--condition 'A != 0'` and `--temporary`. Checkpoints survive a
   later `c64 load`/`c64 run`, so set the breakpoint first, then load.
   Checkpoints persist across c64 run/rebuilds by design, and duplicates
   accumulate silently — clear stale ones, but note that **`c64 break clear`
   only clears execution breakpoints**. Watchpoints need `c64 watch clear`;
   `c64 break list` shows both, and is the check to run when the machine
   stops somewhere you did not ask for.
2. `c64 wait --break` — **resumes the machine and runs to the NEXT hit**,
   leaving it stopped there. It is the checkpoint counterpart of
   `c64 until`, not a passive block.
3. Inspect: `c64 reg` (registers, PC annotated with the nearest symbol),
   `c64 mem read ADDR LEN`, `c64 break list`. Inspection never advances the
   machine.
4. Read the code you are about to step through: `c64 disasm <addr|label> 24`
   — an alias of `c64 rom disasm` that works on RAM just as well as ROM, so
   point it at your own routine (or at `c64 reg`'s PC) before stepping.
   Guessing at which instruction you are on wastes more steps than
   disassembling does.
5. Single-step: `c64 step N` (add `--over` to step over `JSR`s), `c64 finish`
   (run to the current subroutine's return), or `c64 until SYMBOL` (run to a
   point). Use `c64 watch add ADDR --store` to break on writes.
6. `c64 continue` when you are done inspecting and want it to run free.

**Never put `c64 continue` in front of `c64 wait --break`.** The wait
resumes by itself, so the pair advances *two* hits and you observe every
second arrival — deltas come out doubled and a bounce, a wrap or a one-frame
state can vanish between samples. To step frame by frame, loop
`wait --break` → inspect → `wait --break`, with nothing else in between:

```bash
c64 watch add '$D001' --store         # or: c64 break add mainloop
for i in $(seq 1 12); do
  c64 wait --break --timeout 30       # runs one more frame, stops
  c64 mem read '$D000' 2              # inspection: does not advance
done
c64 watch clear && c64 continue        # let it run again
```

**Catching the first frame of a state you just triggered.** `c64 until
mainloop` right after the keypress that starts play does *not* stop you at
move 1: `until` sets its checkpoint only when it runs, and the wall-clock
gap since the previous command is emulated seconds at warp. It does not
fail — it silently returns some arbitrary later arrival, with the score
already moving. Arm the checkpoint **before** the trigger instead; a
breakpoint halts the machine on arrival by itself, so there is no gap to
race:

```bash
c64 break add mainloop        # BEFORE the key that starts the game
c64 key type " "              # the machine runs, hits mainloop, stops there
c64 mem get headrow 2         # move 1, deterministically
```

The same applies to a level-up, a death screen, or any other transition:
break on the code path first, then trigger it.

**The stopped-state rule.** The machine's run/stop state persists across `c64`
commands (a per-session monitor daemon holds it). Four commands intentionally
halt it so you can inspect it: `c64 step`, `c64 finish`, `c64 until`, and
`c64 wait --break` when it fires. After any of those the machine STAYS paused —
through as many inspection commands (`screen`, `mem`, `reg`, `sprite status`,
`screen --png`, ...) as you like — until you `c64 continue` or an
explicitly-resuming command (`c64 run`, `c64 load`, `c64 disk boot`,
`c64 session reset`). Inspection never disturbs the state.

Three of those four halting commands *also resume first*: `until`, `step` and
`wait --break` all run the machine forward from wherever it is. Only their
arrival is passive. That is why an extra `c64 continue` before one of them
costs you a hit.

**`c64 wait --text` and `c64 wait --mem` poll; they do not resume.** They are
the two that are purely passive, which makes them the trap: issue one after
`until`, `step`, `finish` or a `wait --break` that fired and it polls a
machine that is not executing, so the value it is waiting for can never
arrive and the only outcome is the timeout. Resume first with `c64 continue`,
or — better, when you want the frame count to stay deterministic — step the
state out on the frame anchor with `c64 until <label> --count N`, which
resumes and re-parks in one command. **The same is true inside a spec:** in
`c64 test run`, a `wait:` step after an `until:` step polls a stopped machine
and times out exactly the same way. Replace it with another `until:`.

## Text encodings — keep three straight

The C64 uses three different byte encodings, and confusing them is a frequent
source of bugs:

- **ASCII** — what your host files and the CLI use.
- **PETSCII** — what the keyboard produces and what ROM output routines
  (CHROUT) consume. `$0D` is RETURN; letters are ASCII-uppercase codes.
- **Screen codes** — what actually sits in screen RAM at `$0400`. These are
  *not* PETSCII: `0` is `@`, `1`–`26` are `A`–`Z`, and bit 7 means reverse
  video. Reading screen RAM with `c64 mem read '$0400'` shows raw screen codes;
  `c64 screen` decodes them to text for you.

## Common pitfalls

- Uppercase in BASIC source → graphics garbage on screen (write lowercase).
- Write PETSCII control codes as `{clr}`-style escapes — petcat supports them;
  see references/basic-internals.md. No accented or non-PETSCII characters
  anywhere, including inside strings.
- **Scope check before coding.** If a game needs 3D, physics, or more than
  ~38K of program plus variables, simplify the design first.
- **Prefer keyboard input (`get`) over joystick** for games: the keyboard is
  drivable from tests (`c64 basic type`, `c64 key hold`); the emulator has no
  joystick injection, so a joystick game cannot be driven by tests.
- **Playtest from the source, not from guesses.** Before playing or testing a
  game, read the code and derive the controls, win/lose conditions and timing.
- Multi-file assembly crashing with `?SYNTAX ERROR` at RUN, or a build
  failing with branch "Range error" after adding code — both are ca65
  traps (segment state leaking across `.include`; short branches
  outgrowing ±127 bytes). See the `6502-assembly` skill's gotchas for the
  fixes.
- Forgetting to `c64 wait` after `c64 run` and reading the screen too early.
- Reading `$0400` and expecting ASCII — it holds screen codes. In a
  `c64 mem read` dump the hex is the truth and the text column is only a
  gloss: check the `# text column:` label under the dump, and use `--as
  screen|petscii|ascii` to override it. `c64 screen --codes` is still the
  purpose-built view of the screen.
- Assuming the machine is running after `c64 step`/`finish`/`until` — it is
  stopped; `c64 continue` to resume.
- **Warp discipline.** At `--warp`, wall-clock seconds between your commands
  are emulated *minutes* — a game left running between two inspection
  batches will have played on (lives lost, screens changed, state moved).
  End every inspection batch STOPPED (`c64 until <label>`) and do
  multi-command verification in one atomic sequence, or expect drift.
- **`c64 wait --text/--mem` POLL.** Transient states (a 3-second game-over
  screen, a byte that holds a value for a few frames) can slip between
  polls at warp. For transitions, prefer a watchpoint:
  `c64 watch add ADDR --store` then `c64 wait --break`.
- Driving a game that reads the held key from `$CB` (or the joystick)?
  `c64 key type` only fills the type-ahead buffer — use
  `c64 key hold KEY --at <loop-label>` (it re-pokes the key's matrix code
  into `$CB` each frame; see the hardware reference). The hold lets the key
  go afterwards unless you pass `--no-release`: the re-poke assumes the
  KERNAL keyboard scan is running to clear `$CB`, and a game that owns the
  interrupt has no scan, so an unreleased key stays down for ever.
- A sprite demo that "shows nothing" in `c64 screen` — sprites never appear
  in decoded text. Check `$D015` and positions with `c64 mem read '$D000' 17`
  and capture `c64 screen --png` for the visual.
- **A custom charset changes the glyphs, not the screen codes.** `c64 screen`
  decodes each code through its *ROM* meaning, so your redefined glyph reads
  back as whatever the ROM drew there — and codes **32, 96 and 224 decode to
  a blank**, so a glyph parked on 96 is missing from decoded text while
  sitting plainly in `--png`. Assert with `c64 screen --codes` or
  `c64 mem read`, look with `c64 screen --png`, and keep anything you want to
  eyeball as text off those three codes. The cookbook's custom-character-set
  recipe has the install sequence. Reverse video doubles both traps:
  `c64 screen` decodes reverse space as a block, so `wait --text` never
  matches a reverse-video heading (assert its screen codes with `--codes`
  instead) — and codes **129-154 are reverse A-Z**, so a charset that
  patches 128+ turns every reverse-video line into game glyphs. Park custom
  glyphs outside 128-154 (112-123 is a proven run).
- **Reading back a VIC-II color register — or a color-RAM cell — and
  comparing to the value you poked.** `$D020`/`$D021` are 4-bit; the high
  nybble reads as 1s, so `POKE 53280,0` reads back as `$F0`. Color RAM
  (`$D800-$DBE7`) is 4-bit too, but its high nybble is open bus and varies
  (a cell written 13 read back `$FD` in one session, `$0D` in another) — so
  an unmasked compare can even pass by luck and prove nothing. Mask with
  `AND $0F` (`mask: { and: "$0f", equals: [0] }` in a YAML test).

## When something goes wrong — diagnosis table

(Quick lookups only — for full procedures such as store-watchpoint
corruption hunts, register-clobber audits, and deterministic
reproduction, use the `6502-debugging` skill.)

| Symptom | First move |
|---------|------------|
| Screen shows graphics glyphs instead of text | Uppercase in the `.bas` source — rewrite keywords AND strings lowercase. |
| `c64 wait --text` times out | `c64 screen` and look. The program may be awaiting input (feed it with `c64 basic type` or a `key` step), still loading, or crashed. |
| `c64 until LABEL` times out on a label that used to fire | The program branched away (death/menu/pause) and never executes LABEL again. Break at a code path that must still run and `c64 wait --break`. |
| `c64 until LABEL` returned, but the numbers are nonsense | It answered a different question: the current state does not reach LABEL every tick, so the run sailed an arbitrary number of frames before landing there. Check the state/mode byte before anchoring timing on LABEL — and for a routine's cost, `c64 profile` needs no anchor at all. |
| Program seems to hang | Sample it: run `c64 reg` two or three times and compare PC. PC stuck in your code = your loop is wrong — then follow the wedged-machine playbook in the `6502-debugging` skill; PC around $E5xx = the machine is idling in BASIC waiting for input. |
| Assembly crashes or drops to READY immediately | The SYS stub math is off — `c64 rom disasm 2061 16` and confirm your first instruction is at $080D. |
| `?SYNTAX ERROR` when running a loaded program | Inspect what actually loaded: `c64 basic detokenize file.prg` (`c64_basic_detokenize` over MCP). |
| Machine appears frozen after debugging | It's stopped (step/finish/until/wait --break leave it stopped) — `c64 continue`. |
| Sampled values step by exactly 2× the delta the code says | A `c64 continue` in front of `c64 wait --break` — the wait resumes too, so you see every second hit. Drop the `continue`. |
| The machine stops somewhere you set no breakpoint | A stale watchpoint. `c64 break list` (it lists watchpoints too); `c64 break clear` does NOT remove them — use `c64 watch clear`. |
| `c64 wait --mem '$FB=20'` never fires on a counter | Waits poll, so a counter can step over 20 between polls. Use an inequality: `c64 wait --mem '$FB>=20'`. |
| `c64 wait --mem`/`--text` times out and the value never moves at all | The machine is stopped — `until`/`step`/`finish`/`wait --break` leave it that way, and a wait only polls, so it can never fire. `c64 continue` first, or advance deterministically with `c64 until <label> --count N`. Same inside a spec: a `wait:` step after an `until:` step. |
| After `c64 call`, `until`/`continue` behave as if the program is gone | It is. The call's fake return address replaced the program's own control flow. Reload with `c64 run`; treat a call as the end of that run. |
| Program vanished after `c64 run` | Autostart resets the machine first — that's normal; reload anything else you need. |
| A color register or color-RAM assert fails with `f0 != 00` (or `fd != 0d`) | VIC-II color registers AND color RAM (`$D800-$DBE7`) are 4-bit — the high nybble is junk on readback. Mask with `and: "$0f"`. |
| Disk command misbehaves | Read the error channel from a program: `open 15,8,15 : input#15,e,e$,t,s` (error table in references/basic-internals.md; INPUT# is illegal in direct mode). Then inspect the image itself from the host — `c64 disk ls`, `c64 disk validate`, `c64 disk block read IMAGE 18 0` for the BAM. |
| A file the program LOADs isn't on the disk | `c64 disk ls IMAGE` — CBM names are written lowercase (they display uppercase on the C64) and max out at 16 chars, so they rarely match the host filename. Put it there with `c64 disk put`, or list it in a `*.disk.yaml` and rebuild with `c64 disk build`. |

## When the tooling itself misbehaves

The `c64` CLI drives a real VICE emulator process, so occasionally an
*operational* failure happens that has nothing to do with your program. Stay
out of the weeds — do NOT read c64-tools' own source or launch `x64sc` by
hand. The fixes are simple:

- **`c64 session start` fails ("monitor never answered").** A cold emulator
  under load can be slow to come up. Just run `c64 session start` again
  (add `--warp` for a faster boot). If it keeps failing, list what's running
  with `c64 session list`, `c64 session stop` anything stale, and retry.
- **"session already running" / a name is taken.** `c64 session stop <name>`
  (or pick a different `--name`), then start fresh.
- **Commands say "no C64 session running."** You have no session, or you're
  not naming it — start one, or pass `--session <name>`.
- **A session seems wedged.** `c64 session stop <name>` and start a new one;
  a fresh session is cheap.
- **A capture died mid-window** — `audio capture: no response to EXIT`. The
  window is lost and no artifacts are written: no WAV, no register log, not
  even a partial one. The machine is left stopped, so the next command on
  that session will not behave either. Stop the session, start a fresh one,
  and capture again. The *program* is fine — this costs you the capture's
  wall clock and nothing else, so retry before you go looking for a bug in
  the player.

## Verifying a change

Prove a change works, don't assume it. Either assert on output with
`c64 wait --text "EXPECTED"`, or write a declarative test and run it with
`c64 test run mytest.yaml` (a `program` plus `wait`/`key`/`assert` steps —
full format under `c64 test run` in docs/cli.md). Existing example
programs can all be run as tests with `c64 test programs`.

**Testing motion.** A moving sprite is asserted by sampling, not by a fixed
coordinate: `until` a frame anchor, `sample` a register under a name, `until`
again, then `assert … differs` (or `greater_than`/`less_than` when the
program documents its direction, or `unchanged` for the opposite claim — a
hold or pause state where the byte must **not** move) — the `sample`/`differs`
steps are documented under `c64 test run` in docs/cli.md and worked out in
`tests/programs/sprite-ball/test.yaml`. Test collision through the program's
own state change (a lives byte decrementing), not by racing `$D01E`, whose
latch clears on read. Anchor every sampled read on a `c64 until` stop at the
main-loop label; never assert on a free-running frame count. The anchor
must itself be frame-paced: a main loop that spins (draining a work queue
rather than waiting on the jiffy) makes `until --count N` a loop count,
not a frame count — anchor those programs on the IRQ handler instead.

**A BASIC program has no label to anchor on.** There are two substitutes,
and both require the program to publish state. The first is a *saturating*
summary byte — a bitmask of the events seen so far, or a high-water mark —
that only ever moves one way, so `wait: { mem: "$fa", equals: 15 }` cannot
race a value that has already gone past; prefer this in tests. The second is
a store watchpoint on a byte the program pokes at the moment of interest
(`c64 watch add '$FC' --store`, then `c64 wait --break`), which stops the
machine *at* the event; prefer this for evidence capture and hand-driven
sampling.

A program with randomness cannot be pinned by a static test until it is
seeded. `RND(-X)` reseeds deterministically (`30 x=rnd(-1)`), so the run is
reproducible; `RND(-TI)` gives a different game each run. Keep the seeding
call on its own line so a test can substitute it — see the cookbook's
prompt-loop recipe.

For one routine, do not wait for a symptom: unit-test it against the live
machine with `c64 call` — poke its inputs, call, assert on registers and
memory — and keep the proof as a YAML `call:` step in a permanent test.
Boundary sweeps that would take hours in-game take seconds this way:
prove a scoring routine at shot counts 1/5/22/23/24 in one loop instead
of engineering the 23rd live shot. `c64 profile ROUTINE` prices the same
bracket in cycles (IRQs masked, so the sample is clean).

**A call ends that run.** `c64 call` reaches its routine by pushing a fake
return address, so when the routine returns it returns to the harness, not
to whatever your program was doing — the program that was running is gone
(the same warning `c64 call` carries in docs/cli.md). Inspect all you like
afterwards, but a following `until` will time out on a label nothing
executes any more, and it will look exactly like a wedged machine. `c64 run`
again to play on. In a YAML spec this is why `call:` steps go last, or in
their own file; in a hand-driven evidence protocol it is why a call is the
final action before a capture.

## References

Read the matching file when you need the detail:

- `references/cookbook.md` — **start here for a new program**: tested,
  copy-adaptable recipes (game loops, screen pokes, sprites, sprite
  multiplexing, raster event chains, sound) in BASIC and asm.
- `references/memory-maps.md` — the C64 memory layout (RAM, screen, ROM, I/O, banking).
- `references/zero-page.md` — the 6510 port, BASIC pointer chain, low-memory
  usage, handy control-flag locations (RUN/STOP, key repeat, color, region),
  and the zero-page half of the label database `c64 disasm` annotates with.
- `references/kernal-routines.md` — KERNAL jump table, the ST status word,
  hardware vectors, stable BASIC-ROM math/output entry points, and the
  BASIC-interpreter / KERNAL internals a stopped program's PC lands in.
- `references/basic-internals.md` — program storage & tokens, statement
  execution / GOTO cost, variables & number formats, keyword abbreviations,
  runtime errors, string GC / FRE footgun, derived math functions, and disk I/O.
- `references/petscii.md` — the three text encodings and the screen-code table.
- `references/hardware.md` — VIC-II (sprites, bitmap & color-text modes, VIC
  bank/raster/collision IRQ), SID (voices, filter, envelopes, note table),
  CIA 6526 (timers, TOD, ICR, serial bus), color RAM.
- `references/audio-verification.md` — proving music and sound effects
  without listening: `c64 audio capture` (WAV + per-frame SID register log),
  writing a reference score, reading a piano roll and a spectrogram.
