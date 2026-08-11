# Changelog

All notable changes to Project64 (`c64-tools` / `c64lib`). Dates are the
day the release was tagged. Project64 is a Commodore 64 port of
[PET-Project](https://github.com/nschneir/PET-Project); its PET-era history
lives in that repository (and in this one's git history before the fork
commit).

## [Unreleased]

`c64 key hold` releases the key. `$CB` goes back to 64 after the last held
frame, `--no-release` (`release=false` over MCP) keeps the old behaviour, and
the payload says which happened. What makes that a bug rather than a nicety
is a game that switches the KERNAL keyboard scan off: nothing else ever
writes 64 back, so an unreleased hold pins the key down for the rest of the
run, and every hold in La Galaxia's evidence script and its regression spec
had to be chased with a poke of 64. The release is a plain monitor write with
no resume, so a completed hold still ends stopped on its anchor exactly as
before. A *timed-out* hold releases too — that is where it matters most,
since the usual cause is a mistyped anchor on a perfectly healthy running
game — and there it pokes and then resumes, which is what keeps the "machine
left RUNNING" promise honest; the failure message either says `key released
($CB=64)` or names the byte still held along with the write that clears it.

`c64 profile --samples N` (MCP `c64_profile(samples=N)`) prices N consecutive
arrivals at a routine and reports min, max and mean. One measurement of a
routine whose cost depends on its data — a multiplexer band, a collision pass
over however many objects are alive — is a sample of a distribution reported
as a fact, and the spread is the answer. At `N = 1` the payload still carries
`cycles`, so nothing that read the single-shot form breaks, and the
impossible-measurement guard (a raw count of 0, which no routine can cost)
still aborts the whole run rather than averaging a fiction. `profile_routine`
itself is gone, with its tests moved onto the sampling form rather than
deleted: both front ends call the one entry point now.

`c64 session stop --all` (MCP `c64_session_stop(all=true)`) stops every
session in the registry and returns the names it stopped — the one command
for the emulators an interrupted run leaves behind, which until now had to be
hunted with `pgrep` and killed by hand. It reads the registry records
directly rather than through the loader that prunes them, because the pruning
loader drops a session whose process is already gone *before* anything can
clean up after it, and reaping means the socket file, the respawn counter and
the audio pin as well as the record. One stubborn session does not strand the
rest: the errors are collected and raised once, naming what was stopped and
what was not. `c64 session start` also says on stderr how many sessions were
already up, printed before the launch attempt so it explains the failure in
the very case where the name is already taken.

Three operational failures that escaped as tracebacks now exit 1 through
`fail()` with a parseable `--json` error object, which is the same bug three
times and worth naming as a class: an operational failure is exactly as
likely as the operation, so every path that can raise has to be inside the
handler. `c64 profile` let a daemon-side `ValueError` through, because the
narrowed old-daemon fallback made that a second exception type the command
had never caught; `c64 session start` read the registry for its new count
*above* the `try`, so a truncated or older-format record — which `launch`
itself has always reported cleanly — escaped instead; and `c64 audio report`
turned an undecodable log into a traceback.

The sheet encoders went a step further than the per-block modes below. A
**sprite** sheet takes `name:` headers carrying their own mode
(`fighter:hires`, `captured:multicolor`), `#` comment lines, and
`--background CHAR`: a visible character for the transparent pair, so a
shape's edges can be counted instead of being trailing spaces an editor may
or may not have kept. Because `.` is pair 01 by default, the multicolour
legend also gained `1`/`2`/`3` for pairs 01/10/11 — the digit is the pair
value, exactly how `charset` already spells it — so `--background .` turns a
sprite sheet's legend into a charset sheet's and every pair stays spellable.
A header with no art rows is rejected where it used to be dropped in silence,
errors name the block, and `--json` carries a `blocks` array of names and
modes. `c64 charset encode --label NAME` names the emitted block, which is
the other half of the same job; both reach MCP with the same spellings, and
one header parser now serves both encoders. La Galaxia's own converter,
`tools/gensprites.py`, is deleted: its 21 shapes took two invocations over
two generated intermediate files and take one over the authored sheet now,
byte-identical across the change.

La Galaxia's regression spec builds from source. It named the packaged `.d64`
because that was the only route to symbols for a program that needs `--area`
to link at all; with `areas:` on a spec it assembles `la-galaxia.s` on every
run, which also takes the ~13 s of serial load out of the gate — 35 s end to
end, and nothing that can go stale between the symbols and the bytes they are
read against. Regenerating the demo's art closed the other half of that:
`sprites.inc` had drifted a whole block out of date, holding a sixth *hires*
fighter at block 5 where the sheet and `sprites.s`'s own manifest
(`SPR_CAPTIVE = SPRBLK + 5`, "multicolour from here down") both say the
multicolour captive belongs — so the game drew a hires bitmap through the
multicolour bit. Regenerated, rebuilt, repackaged, and pinned: a test
re-encodes `tools/sprites.txt` and compares it against the committed include,
because a generated file with no regeneration test can disagree with its
source forever.

And `audio-verification.md` gains the two things this demo's score work cost
most. **Generating a score is constructive**: model the player one frame at a
time — one entry per frame, including the gate-down frame a retrigger costs —
and run-length encode that. It is the transcriber's own algorithm, so the two
agree by construction, and it is not the forbidden move of pasting a
transcription back in as the score, because the input is the note table;
`demos/la-galaxia/tools/genmusic.py`'s `per_frame()` is the worked example.
The reference had the retrigger *fact* and no recipe, and this demo's first
generator walked its rows and multiplied: every note a frame too long, no
leading rests, one whole capture to find out. **A reference score is hostage
to its window**: it claims every voice for every frame, so the dive whines
and the collisions the game raised on its own were in the score too; it
passed on the run it was written from and failed on the next one, when an
unrelated edit moved the enemies and the same effects landed on different
frames. The fix is to take the other sounds out of the window — clear the
state that can seize a voice before the capture opens — rather than to
re-score them.

A `--mem` wait that times out now says **where the machine was**. Issued after
a `c64 until` — or a `step`, a `finish`, a fired checkpoint — a wait polls a
byte no running CPU is writing, so it can only burn its whole timeout and hand
back the value it started with; the la-galaxia dogfood spent two minutes that
way and filed a false "the game is stuck". `c64 wait --mem` and
`c64_wait_mem` now sample the machine's state on **both** sides of the wait —
one sample cannot support "stopped the whole time", since a machine stopped
only at the end really was running for part of the window — and when both read
stopped, the CLI's error names the cause and points at `c64 continue` while
the JSON carries `"machine": "stopped"` in place of the `"running"` that path
used to assert unconditionally. The MCP tool, which had carried no `machine`
key at all where its three siblings all did, gains the same field plus a
`diagnosis` string, so the surface agents actually drive stops being the one
that fails silently.

`skills/6502-assembly/references/fix-branch-range.py` makes the branch-range
trap mechanical. Growing a routine pushes its branches past ±127 bytes, and
the skill's advice — prefer a `jmp` trampoline from the start — is right and
nearly impossible to apply pre-emptively: La Galaxia hit 25 "Range error"
failures across six files in a single build. Pipe the failed build in and the
script inverts each reported branch over a `jmp`, bottom-up so the reported
line numbers stay valid. It **reports rather than touches** two cases and
exits 1 so a human sees them: a branch whose target is an anonymous label, and
any rewrite whose new `:` would land between another `:+` and the label that
reference resolves to. An anonymous label has no name, only a position, so
either edit still assembles and quietly branches somewhere else — the one
failure a green build cannot catch.

Five documentation gaps the same dogfood walked into, each now carrying the
test that would have caught it. The **character ROM image is 4 KB**, which
`hardware.md` and `memory-maps.md` both described correctly and neither sized:
it covers *two* of the eight 2 KB charset bases, so a reader who obeys the
cookbook's stated rule ("in the VIC's bank") can still pick `$1800` and get
the ROM's lowercase half — silent, because lowercase glyphs look like text
rather than like a fault. A live test settles it on the machine, patching the
same glyph into RAM at `$1800` and `$3800` and drawing each. `--area`'s fill
rule gains the half that decides file size — every area below the last is
filled to its declared size, the last is not, so only the top area's unused
tail is free, and a `.res` inside any area is `type = ro` content that ships
as zeros wherever it sits. La Galaxia's three areas cost a flat 14,337 bytes;
the test extracts that number from `docs/cli.md` and rebuilds it, because the
unverified copy of this same figure in the demo's plan had already drifted by
five bytes. `docs/graphics-and-sprites.md` §1 stops forbidding a technique the
repo ships: mid-frame register changes and raster-IRQ multiplexing are in
scope **when the demo exposes counters a test can assert on** — warp makes the
moment a test observes unpredictable, not the state it observes — and only
effects whose sole evidence is a photograph stay out. And §4 gains the rule
that a **per-frame budget is max-tracked by the program**, with the harness
reading the mark: sampled every tenth tick, La Galaxia's redraw counter read 4
against a ceiling of 64 while the program's own mark read 88.

`--area` reaches the two places that could not use it. `c64 run --area
NAME=START:SIZE` (MCP `c64_run(areas=[…])`) links a fixed-address segment on
the way to the machine, and a test spec takes the same strings as an `areas:`
list beside a `.s` `program:`. A program that needs an area to link at all —
La Galaxia links its engine at `$4000` — was until now unrunnable from
`c64 run` and untestable from source: the demo shipped a two-command
`build.sh` and pointed its spec at the packaged `.d64`, paying ~13 s of
serial load before step 1, because a disk was the only route to symbols
there was. A `.prg` `program:` now picks up a sibling `.lbl` of the same
stem, the rule `cart:` and `disk:` already followed — without it a `.prg`
spec resolved nothing at all, and `until: {ref: tick}` failed with an empty
known-list. `areas:` is rejected, naming the conflict, beside anything it
would not reach (a `.bas`, a `.prg`, a `cart:`, a `disk:`), and a malformed
one is refused before a session boots. Finally, a `disk:` spec whose image is
*older* than the sibling `.lbl` it takes symbols from now stops with "the
image predates its symbols" and both timestamps, instead of resolving fresh
addresses against stale bytes and failing on a plausible wrong byte
(`mem $414b = 4a != 00`). Only the sibling file is judged that way: the label
copies `c64 disk build` keeps are written by the command that wrote the
image, so they cannot go stale on their own.

A capture window can be **aimed** now, and it says what it cost to open.
`c64 audio capture --at-frame N 'ADDR=VAL[,ADDR=VAL…]'` (repeatable;
`at_frame={"N": "…"}` over MCP) performs those writes at frame N of the
window. This is the la-galaxia dogfood's single biggest audio cost — about
ninety minutes and a program change — and it was unreachable rather than
merely awkward: arming spends emulated frames before log frame 0, and once
the window is open the sampling loop owns the session, running as one round
trip inside the daemon, so a poke from another command queues behind the
whole capture instead of landing inside it. A six-frame laser was therefore
always over before frame 0, and the game's own trigger was no better — the
fighter fires on an input *edge*, `key hold` pins `$CB` to one value, and
with the KERNAL scan off the state never falls. The writes travel with the
sampling loop as a separate `sid_log_at` daemon method, deliberately not a
third argument on `sid_log`: an older daemon drops extra positional args
silently, and a capture that looks aimed and is not is the worst outcome
available. A write lands while the machine is halted, immediately before the
resume that runs its frame, so frame N is the first *logged* frame that shows
it and the schedule costs no emulated time at all. A frame outside the window
is refused before anything is pinned, where a malformed `--ref` already was.

`lead_in_frames` is that arming cost, measured per capture instead of quoted
from somebody else's run: the KERNAL jiffy read before the pin against the
jiffy read after the arm, converted through the jiffy's 60.00 Hz — it is a
clock, not a frame counter, and PAL ticks it 1.2 times a frame — plus the
sampling loop's own first resume. It is **null**, never a plausible number,
when the jiffy cannot answer: the KERNAL's IRQ handler is what increments it,
so a player that owns the IRQ freezes it. The text monitor's cycle
`STOPWATCH` would have been program-independent and cycle-exact, and it is
not used on measurement grounds — opening that channel at real time costs
several frames of the very lead-in it would report, where the jiffy read
costs one round trip. VICE's binary monitor has neither counter.

`sid-log.jsonl` now opens with a clock stamp — `{"machine", "clock_hz",
"fps"}` from the session's own model — so `c64 audio report` needs `-s` only
as an override. Before it, a re-score run after the session had stopped
silently assumed PAL and renamed every note of an NTSC capture, which reads
as a badly tuned program rather than a mistake in the tooling. The payload's
new `clock_source` says which of the three answered (`session`, `log`,
`default`), because "assumed PAL" and "told PAL" produce identical reports
and only one of them is evidence. Logs written before the stamp still parse:
the header is optional to the reader and mandatory for the writer.

And the score diff compares **pitch, not spelling**. A score written from
music data spells its black keys the way its key signature does, while the
transcription only ever emits sharps — a frequency carries no key signature
to choose from — so the first `--ref` run of one demo came back as seven
diffs, every one of them a flat against its own sharp. `Ab4`, `A♭4`, `G#4`
and `G♯4` are now one note; the round trip goes through MIDI rather than
pitch class, so `Cb4` matches `B3` an octave digit down and a real
wrong-octave bug still fails. A diff quotes both spellings when they differ:
`expected Ab4 (= G#4), heard A4 at frame 96`.

The `warp on` wedge is fixed at its cause, not just retried around — and
fixing it surfaced a second latent race, so `pinned_record_stop` now does
three things in an order where neither can fire. It re-arms the recorder
onto a throwaway sink first, which closes the capture WAV while the sound
layer is live; it restores speed and warp while the sink is consuming; and
it disarms only the sink, under warp, where its unfinalized header is
nobody's problem. The first race is the wedge investigation's: VICE's
sound device is the emulation loop's flow control, and a `warp on`
readback made at real time with no consumer stalled 39 times in 240
measured pin/unpin cycles (0 in ~877 readbacks made outside that window).
The old order — disarm, then restore — made that window on every stop.
The second race is why the obvious fix (just swap the two) was not
shipped after its first trial run: VICE finalizes a closed WAV's header
asynchronously, ~50 ms after the close is *serviced*, and it is serviced
only while sound runs — a disarm issued milliseconds after re-warping
races the sound teardown, and the loser leaves the placeholder sizes
(`0x6c6c6c6c`, which `wave` reads as five hours of audio) on disk until
the session exits. The arpeggio round-trip test caught it: 6 of 11 runs
of the swap-only fix read that placeholder, all with the identical
18948.385125 s phantom duration. With the sink order, the forced-arm
re-runs of the investigation's measurement confirmed both mechanisms: 1
first-reply miss in 258 post-fix pin/unpin cycles on tone-program
sessions against 39 in 240 before (16.25% to 0.4%; the one miss was
rescued by the retry and its cycle stayed clean), 158 of 158 sink-order
stops handing back an already-finalized header, and the arpeggio test 8
for 8 against 6 failures in 11 runs of the swap alone.
`pinned_record_stop` also now *confirms* the header before it
returns — `record_stop`'s "confirm a stop by the file", finally made real
— and refuses a WAV that never settles rather than handing back phantom
evidence. The readback retry in `warp_state` stays: it is cheap,
measured, and defends every other path through `restore_speed`,
including the best-effort fallback when the sink itself cannot be armed.
The second failure mode the investigation left unattributed — bursty
binary-monitor timeouts that appear in a window and vanish — reproduced
live during this work and is now attributed, with the diagnostics the
investigation said it lacked: it is the host, not the protocol. Three
consecutive pin/unpin smokes wedged identically while the machine sat
user-idle (`x64sc` alive at 1.8% CPU, its binary port still accepting
TCP, its text monitor still answering — the emulation loop throttled,
not blocked on a socket), and the identical code ran clean at full
speed the moment it was wrapped in `caffeinate -dimsu`: macOS idle
throttling of the `-minimized` headless emulator slows it until every
binary-monitor call times out. Unattended VICE work on an idle Mac
needs a user-activity assertion; the re-verification runs here were
made under one. One ordering experiment is recorded as
tried-and-inconclusive rather than silently abandoned: arming the
recorder before the pin (to close the start's sub-second no-consumer
gap) wedged its one live trial, but that trial ran inside the
idle-throttling window — the pin-first control wedged too — so
`pinned_record_start` keeps its measured-good pin-first order, and its
docstring records what would justify revisiting. A failed restore still leaves the pin sidecar for `c64
audio record --stop` to retry, and still disarms on the way out. And the
stop now *says* which half failed instead of leaving `capture` to infer
it from whether the sidecar survived — an inference the
both-halves-failed case fooled into overstating what was on disk:
`PinnedStopError` carries `restore_error`, `disarm_error`, and
`wav_complete`, and `capture` branches on the report. A disarm failure
whose recording the sink had already taken over is a warning now, not a
discarded capture; the fatal case that remains is the honest one — no
sink armed and no disarm means the capture WAV is still being written.
That was `docs/todo.md`'s last open item, so the file itself is gone:
it is deleted when its last item lands (maintainer ruling, noted in
`AGENTS.md`, whose dogfood post-mortems recreate it).

The other half of that wedge is gone as well: a headless session no
longer needs anything on the host to listen to it. The la-galaxia
dogfood run turned the flow-control mechanism from a hypothesis into a
reproducer — on a host reporting no audio output device (`ioreg -rc
IOAudioDevice` counts 0 nodes, `system_profiler SPAudioDataType` comes
back empty) every real-time operation wedged, every time, while
everything warped stayed green: builds, tests, 14 evidence captures,
thousands of frame-stepped ticks. The narrowing was exact — `audio
record --start`, the pin-and-arm step, is what hung. So `Session.launch`
now starts every headless emulator with `-sounddev dump -soundarg
<os.devnull>`. VICE's `dump` device is file-backed, always consumes, and
never opens coreaudio at all (its own log: `Opened device 'dump'`, with
none of the `coreaudio_init` lines the default device prints), so the
dependency disappears instead of being raced around. The obvious
spelling, `-sounddev dummy`, is measured wrong and now has a test
against it: dummy consumes nothing, so VICE overflows its own sound
buffer (`Sound buffer overflow (cycle based)`, 25 times before it stops
warning) and discards it — the WAV recorder then receives no samples,
and the live arpeggio capture came back as a bare 44-byte header where
the same run on `dump` passed with the arpeggio in it, its WAV growing
at real time's 96 kB/s. The `-soundarg` half is load-bearing too:
unset, the dump device writes its register dump to `vicesnd.sid` in the
*caller's* working directory (this repo's root collected one during the
measurements). Windowed sessions keep host audio, because `headless` is
already the flag that means nobody is watching or listening — the inert
`SDL_AUDIODRIVER=dummy` line beside it always intended as much. The
device *name* is probed against the binary's own `--help`, the way
`-minimized` already is, and the failure that probe avoids is the nastier
of the two: VICE rejects an unknown command-line option by exiting, but
it rejects an unknown `-sounddev` value by logging `device '<name>' not
found or not supported` **and popping a modal error dialog** — which
blocks the emulation loop even on a `-minimized` headless launch, so the
process stays up with its monitor unanswered and looks exactly like the
wedge being fixed. That was found the hard way during this work, by a
human watching the screen while a bogus-value probe ran; nothing the
runner could see said so. A build whose `-sounddev` list has no `dump`
therefore keeps host audio, and the device list is read from that line
alone (`dump` is also a *recording* driver, on a different resource).
What is not claimed: the zero-device host is not reproducible here — this Mac has
output devices, and on it a real-time launch plus five monitor round
trips came back clean — so the fix is verified by mechanism (a device
that needs no consumer cannot wait for one) plus a live capture on a
dump-sink session, not by literal reproduction. The stop's sink dance
and the `warp_state` retry are untouched: they defend paths this does
not remove.

An MCP-wired agent no longer needs a shell. The six commands both
`docs/agent-setup.md` and the `c64-development` skill told it to shell
out for have tools now — `c64_break_enable`/`c64_break_disable`, the MCP
twin of the monitor's `checkpoint_toggle`, and the four offline ones that
need no session at all: `c64_basic_tokenize`/`c64_basic_detokenize`,
`c64_sprite_encode` and `c64_charset_encode`. That takes the server from
68 tools to 74, and every one of the 75 CLI capabilities has a tool. The
two counts differ in both directions. Seven commands have no tool of
their own: `c64 help`, whose usage text the protocol already delivers
with every tool's schema; `c64 mem get`, a print-formatting variant of
`c64_mem_read`; and five second spellings of commands that already have
one. Six tools have no command of their own: `c64 wait` splits into
four, `c64 screen` into three, and the bare `c64 reg` group is spelled
`c64_reg_get`. 75 - 7 + 6 = 74. The carve-out list in
`tests/test_mcp_scaffold.py` is empty as a result; the list and its test
stay, so a future exclusion has to be written down with the reason it is
one instead of accumulating in silence. Encoding is shared with the CLI
rather than reimplemented — `sprites.render_sheet` is now the one place a
multi-sprite sheet gets its running line numbers, called by both — and
the two encode tools are the one place a payload deliberately exceeds the
CLI's `--json`: they add `rendered`, the paste-ready text the command
prints to stdout, because MCP has no stdout and without it `fmt`,
`start_line` and `first_code` would be no-ops.

Three smaller gaps went with them. `c64_build` takes `output`, the CLI's
`-o`, which the tool had no way to spell — a build could only land beside
its source. `c64_sid_report` takes `peak_hz`, the same rFFT measurement
as the command's `--peak-hz`, and refuses it without a `wav` because a
dominant partial is a property of the recording and not of the register
log. And `c64_load` records what it loaded, so `c64_status`'s stale-source
warning fires after an MCP load: it had been reporting `"stale": []` no
matter how old the binary was, because the tool never called
`record_loaded` the way `c64 load` and `c64_run` always have.

The map itself is written down and measured, in the new `docs/mcp.md`:
one row per registered tool, naming the command it twins and the one-line
difference where there is one — the folded rows, the renamed parameters
(`--from` → `src`, `--format` → `fmt`), the headless-and-warp sessions
the tools hardcode, and the wait timeouts that return
`{"fired": null, ...}` as data where the CLI exits 1. The page
states no tool or command counts of its own, since a second uncounted
copy of index.html's numbers is the drift it exists to prevent; two tests
guard it the way those counts are guarded — every registered tool must
appear in it, and every command its tables name must still exist in the
CLI. `README.md`, `docs/cli.md`, `docs/agent-setup.md` and the
`c64-development` skill point at it, and index.html reads 74 tools.

A segment can be linked where the VIC needs it. `c64 build --area
NAME=START:SIZE` (repeatable; also on `c64 package`, and `areas` on the
`c64_build`/`c64_package` MCP tools) declares an extra linker MEMORY area
and puts the identically named segment in it — so a RAM character set lands
on its 2 KB boundary and sprite blocks on their 64-byte ones without a
startup copy loop. A `.prg` is a flat file, so the flag caps `MAIN` at
`area.start - load_address` and fills it: the gap below the area ships as
real zero bytes, which is what makes the segment land there. Areas are
declared `define = yes`, so `__NAME_LOAD__`/`__NAME_SIZE__` are available
for a link-time `.assert` on the ceiling. Everything a wrong `--area` could
do quietly is a rejection instead, naming the flag rather than the config
generated behind it: a gap between two areas (with the size to raise), an
overlap, an area at or below the load address, a zero size, a name that
would redefine one of the config's own, and — the same way `--cart-type`
already works — `--area` passed for a `.bas`, a `.prg`, or a cartridge.
With no areas the generated config is byte-identical to what it has always
been, pinned by a test.

Two sheet-encoder frictions the same dogfood turned up. `c64 charset encode`
takes a per-block mode — `wall:multicolor`, `letter:hires` — so a multicolor
playfield charset and a hires HUD font are one sheet and one invocation
instead of two of each; `--hires` now sets the file's default, which a block
may override, and an unrecognized suffix is rejected by name. The JSON
payload carries `multicolor` per glyph. And `c64 sprite encode` says *which*
block is malformed: `sprite 12 (line 265): art must be 21 rows, got 14`,
where before a sheet of 27 shapes reported only the row count and had to be
bisected by hand. Sheets that name no mode encode byte-identically to before
— both committed demo sheets re-encode to their existing `.inc` files.

A `c64 test run` comparator given a literal now says what it wanted.
`differs`, `greater_than`, `less_than` and `unchanged` compare against a
recorded `sample:`, never against a number — `differs: 0` used to fail with
"no sample named '0'", which is true and unhelpful. When the operand parses
as a number the error names the design and shows the `sample:` step to add;
when it does not, the message is unchanged, so a typo'd sample name still
reads as a typo. `docs/cli.md` gains the table of which assert keys take a
literal and which take a sample name.

Six things the skills and references were silent about, each of which cost
the Ms. Muncher dogfood a debugging pass or a whole audit iteration. The
`c64-development` skill now says that `c64 call` **ends the run** it is
called in (the CLI reference always said so; the skill that recommends the
command did not) and that `c64 wait --text/--mem` **poll and do not
resume**, so one issued after `until`/`step`/`finish`/`wait --break` can
only time out — inside a YAML spec too. Both get a diagnosis-table row.
`zero-page.md` gains a second, live-measured table: the 75 bytes a program
that owns the machine may claim, with the caveats that make them free (one
ROM call takes them back; `$73-$8A` is the CHRGET *routine*; everything the
KERNAL IRQ maintains stays off the list). The `6502-assembly` skill gains
the gotcha that an indexed loop calling a subroutine must reload its index.
The cookbook gains the bank-0 budget — all three consumers of the VIC's
16 KB, the three ways out, and the `.assert` that turns the ceiling into a
build failure — and the two ways a Galois LFSR silently stops being random,
with the recipe extended to *prove* its 255-value cycle as a live-tested
`DISTINCT 255`. `audio-verification.md` covers assembly lead-ins (taken per
start, not baked into looping track data) and the one-shot cue that makes a
score independent of arming latency. Finally, `docs/graphics-and-sprites.md`
§5 writes down the deterministic evidence protocol both game demos had
reinvented separately.

Sound is verifiable now. `c64 audio capture` (MCP `c64_audio_capture`)
records the machine's audio to a WAV while sampling `$D400–$D418` once per
frame, transcribes the register log into notes, diffs them against a
reference score you write in YAML, and drops five artifacts — `capture.wav`,
`sid-log.jsonl`, `piano-roll.png`, `spectrogram.png`, `report.md` — with a
PASS/FAIL verdict; the pieces are also separately available as `c64 audio
record`, `c64 audio sidlog` and `c64 audio report`, the last of which takes
`--peak-hz` to measure a recording's loudest frequency against the pitch its
registers predict. Piano-roll voice colors are fixed (voice 1 red, 2 green,
3 blue) so rolls compare across demos, and a capture pins real time for its
duration — warp off, `Speed` 100 — so real time is the floor on what it
costs: every logged frame is a monitor round trip on top, which puts a
30-second capture at 60–80 seconds of wall clock. The five full-build demo
prompts — Snake, Invaders, Ms. Muncher, La Galaxia and 1812 — now require
the artifact set under
`evidence/audio/` and a passing report, alongside the SID shadow bytes they
already required: the shadows prove a write was issued, the capture proves
what came out of the chip. Finally, the method — capturing, authoring a
score from your note tables, reading a roll and a spectrogram, and the
register facts behind all of it — is written up in the new reference at
`skills/c64-development/references/audio-verification.md`. Two demos arrive
with it: `demos/05-bach-invention/`, a test demo asking for Bach's two-part
Invention No. 13 out of BASIC and proved by capture — prompt-only like the
rest of that tier, where the run is the deliverable and nothing is
committed — and `demos/fugue/`, BWV 847 on three voices in assembly with
its score scrolling past as it plays, prompt-only so far and waiting to be
built.

## [0.9.5] — 2026-08-03

Removed the pyright CI workflow — type checks are a local, pre-commit gate
again rather than a CI job that could go red on unrelated dependency churn.
Closed out the ROM label database with its final tranche: `basic2.lbl` grew
184 → 291 labels, covering the BASIC token dispatch tables, the
floating-point package, and the IEC serial and tape KERNAL internals.
Dogfooded demo 06 (Invaders), which now ships its whole solution — sources,
a fidelity audit, a regression test and a runnable `.d64` — and closed the
twelve CLI, skill and cookbook gaps it found (its process items were tracked
in `docs/todo.md` and have since landed). Dogfooded Snake under its promoted
game-demo prompt: `demos/snake/` now ships the same way, with a
three-iteration audit, a 101-step regression spec, seven evidence frames and
`snake.d64`. This changelog itself was cut from 843 lines to something a
person can actually skim.

Out of that dogfood: `c64 profile REF` reports hardware cycle counts for
one routine (CIA#2 cascade, IRQs masked by default, `--with-irq`), with the
MCP twin `c64_profile` — and it refuses an impossible measurement,
reporting an error when the timers read back untouched (a raw count of 0,
which no routine can cost, and which the start slack used to dress up as
`"cycles": 3`), with the machine left stopped at the trap as on success;
and `c64 charset encode` turns ASCII art into charset `.byte` rows
(multicolor `.123`, hires `.#`), retiring the invaders demo's local
converter. `-s/--session` is now accepted after the subcommand, like
`--json`. Disk boots register symbols — `c64 disk boot`, `c64 session start
--disk/--cart`, and disk test specs pick up a sibling `.lbl` (or `disk
build`'s first-entry label), silently skipped when absent. `mem get`/`mem
read` JSON payloads now both carry `values` and `bytes`, and `c64 mem
write` names a bad byte token instead of dumping a traceback and accepts
one whitespace-separated byte string — and so do `c64 disk block write`'s
VALUES, which take those same tokens as separate arguments or as one
whitespace-joined string (what an unquoted zsh variable expands to), naming
a bad value by its position; bad LENGTH/COUNT/VALUE args across the CLI
fail cleanly too. Newly documented: the sprite-Y ↔ text-row mapping (`51 +
8*R`), the `.include` resolution contract (now build-tested), routine-level
unit testing with `c64 call`, the misleading-`until` diagnosis row, and a
live-tested screen-code-readback collision recipe.

Out of the Snake dogfood's tool items: `c64 key hold --frames 0` is now a
validated no-op (exit 0, machine untouched) instead of a fabricated
timeout — over the CLI and MCP alike — and `@@row,col` resolves a cell's
color-RAM address (fixed `$D800` base; reads are 4-bit, so compare masked
with `$0F`) everywhere addresses are accepted: mem commands, waits and
watches, YAML `mem:` steps, and the MCP tools.

Three cartridge follow-ups changed shipped behavior. `wrap_prg` now refuses
the load ranges its launcher cannot copy to — `$A000-$BFFF` (under the BASIC
ROM), `$D000-$DFFF` (I/O) and `$E000-$FFFF` (under the KERNAL) — so a
machine-language wrap must land below `$8000` or in `$C000-$CFFF`; images
that used to build, pass `cart_verify` and boot dead are now rejected with
the relocation named. Every EasyFlash window carries a BSS area in RAM, so
`.segment "BSS"` links in a banked cart: `$0A00-$7FFF` for the lo and hi
windows, `$0A00-$0FFF` for the Ultimax boot window, overlapping between banks
by construction. And a non-cart program's ZEROPAGE area starts at `$0002`
rather than `$0000`, off the 6510 port registers at `$00`/`$01` — ZEROPAGE
symbols link two bytes higher than they used to.

Out of the 1812 dogfood's items: `assert:` mem steps now take the same six
word comparisons as `wait:` (`equals`/`not_equals`/`above`/`at_least`/
`below`/`at_most`), a step with no comparison fails naming the step and the
whole comparison menu instead of a bare `KeyError`, and `unchanged: NAME`
asserts sample-vs-sample equality — "this byte did NOT change", the
hold/pause/game-over claim. `c64 test run --json` and `c64 test programs
--json` keep the `{"passed", "tests"}` envelope on spec-level errors, so a
parsing harness reports the failure instead of crashing on a missing key.
The cookbook gained two live-tested recipes — signed 8×8→16 multiply by
quarter squares (512-entry tables built at startup from their own first
difference) and multicolor bitmap from zero (mode bits, clear, one masked
span) — and its LFSR range-trick paragraph now tells the truth:
reject-and-retry yields 1 to N−1 (0 is unreachable), is positionally biased
and slow at small bounds, so scale with `(rnd * bound) >> 8` instead. Newly
documented: equates need `.export`/`.exportzp` to reach the label file, BSS
consumes address space after DATA (guard the ceiling with a deferred linker
`.assert`), and `until --count N` is a frame count only when the anchor
label is frame-paced.

## [0.9.0] — 2026-07-31

Closed out the test-health and observability backlog from dogfooding demo
05: fixed a "headless" VICE launch that was actually stealing keyboard
focus (the likely cause of prior test flakiness), and made hex dumps,
disassembly, register output, and BASIC linting report enough context that
a debugging agent no longer has to guess. Also grew the ROM label database
(44 → 184 labels) and made `pyright` a required, zero-error CI gate.

## [0.8.0] — 2026-07-28

Dogfooding runs of demos 03-05 (benchmark, Snake, and a debug hunt) found
and fixed a stale-build false positive and a screen-wait race, and
documented a batch of C64-specific pitfalls (custom charsets, timing,
frame-stepping, and driving a game via MCP vs. the CLI).

## [0.7.0] — 2026-07-27

Dogfooding demo 02 (bouncing ball) added comparison operators to
`c64 wait --mem`, numbered BASIC sprite-data output, and fixed a
non-pasteable uppercase `DATA` bug, alongside documentation on checkpoint
vs. watchpoint semantics.

## [0.6.0] — 2026-07-27

Disks: complete file CRUD, raw block access, disk validation, one-command
game-disk builds, and the runtime half of disk I/O, plus fixes for c1541
calls that failed silently.

## [0.5.0] — 2026-07-25

Cartridges: build, verify, boot and debug `.crt` images, including an
EasyFlash banking runtime and skill.

## [0.4.0] — 2026-07-25

Driving interactive programs: bordered screenshots, since-aware text
waits, numbered screen output, and a fix for `c64 key type` mishandling a
literal `\n`.

## [0.3.1] — 2026-07-25

Test-suite change only: live tests now share one emulator session instead
of launching a fresh one each, roughly halving full-suite runtime.

## [0.3.0] — 2026-07-24

Added `c64 basic check`, a static BASIC V2 linter that models the real
tokenizer to catch errors petcat would otherwise accept.

## [0.2.0] — 2026-07-22

Added sprite tooling — the `c64 sprite` command group and YAML-based
motion testing.

## [0.1.0] — 2026-07-21

The founding release: the PET edition ported to the Commodore 64.
