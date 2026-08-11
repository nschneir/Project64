# Verifying SID audio without ears

Screenshots prove the picture. Until you capture it, sound is the one claim
in a demo that nothing checks: a shadow block proves your player *wrote*
bytes, not that a note had the right pitch, that the gate ever released, or
that voice 2 was doing anything at all for four hundred frames.

`c64_audio_capture` closes that gap. It records the machine's own audio to a
WAV while sampling the SID register file once per frame, transcribes the
register log into notes, diffs those notes against a score you wrote, and
writes a `report.md` with a PASS/FAIL verdict — plus a piano roll and a
spectrogram you read the way you read an evidence screenshot.

## Why registers instead of ears

Nobody in the build loop can listen. You cannot, and the maintainer listens
once, at the end, as the final gate — not on every iteration. So the loop
needs a signal that is exact, cheap, and mechanical.

- **The register log is the machine's, not your program's.** It is sampled
  from `$D400–$D418` on the running machine, so it sees what the chip
  actually holds: a player writing the right bytes to the wrong voice, an
  IRQ that stopped calling the sequencer, an effect routine that clobbered
  the music's control register. A shadow block, by construction, cannot
  catch any of those — it agrees with your code because it *is* your code.
- **Registers are exact.** A 16-bit frequency is a note name and a cents
  offset, not an impression. "The melody is a semitone flat from frame 300
  on" is a diff, not a listening opinion.
- **The WAV covers what registers cannot say.** Clipping, dead silence,
  level balance, and everything the filter does are properties of the mix,
  and the registers look perfect while all four go wrong.
- **The verdict is mechanical.** Transcription minus reference score, plus
  anomalies, plus WAV metrics — empty means PASS. That is a gate a loop can
  run every iteration.

Shadow registers do not go away (see *Known facts* below); they are the
evidence that survives on real hardware. Capture is the evidence that the
emulator can produce every iteration, unaided.

## Capturing

Four tools, three of them the pieces and one the whole job:

| Tool / CLI | What it does |
|---|---|
| `c64_audio_record` — `c64 audio record --start <path>` / `c64 audio record --stop` | Drives VICE's WAV sound recorder. Start writes to `<path>`; stop closes it. |
| `c64_sid_log` — `c64 audio sidlog <frames> <path>` | Samples all 25 SID registers once per frame for `<frames>` frames into a JSONL log. |
| `c64_sid_report` — `c64 audio report …` | Analysis only, no machine: takes an existing log (and optionally the WAV and a score) and writes the roll, the spectrogram, and `report.md`. Re-run it after editing a score without re-capturing. |
| `c64_audio_capture` — `c64 audio capture …` | **The one you want.** Starts the recorder, logs the frames, stops the recorder, analyses, and writes all five artifacts. Over MCP: `c64_audio_capture(seconds, outdir, ref=None, session=None, at_frame=None)`; on the CLI the first two are positional and the rest are options (`--help` for the exact spelling). |

**The artifact set.** `c64_audio_capture` writes exactly these five files
into `outdir`, under those exact names, so every demo's audio evidence looks
the same:

| File | What it is |
|---|---|
| `capture.wav` | The machine's audio output. The maintainer's listen is the final gate, and this is what gets listened to. |
| `sid-log.jsonl` | A clock stamp on line 1 (`{"machine", "clock_hz", "fps"}`), then one line per frame: `{"frame": <int>, "regs": [25 ints]}`, `regs[0]` = `$D400`. The raw evidence — everything else is derived from it, and the stamp is what lets `c64 audio report` re-score it later without a session to name the machine. |
| `piano-roll.png` | Transcribed notes per voice over time. |
| `spectrogram.png` | The WAV's frequency content over time — where the filter and the noise live. |
| `report.md` | Transcription, score diff, anomalies, WAV metrics, and the overall verdict. |

The verdict is PASS only when the score diff is empty, no anomalies were
found, and the WAV shows no clipping and no unexpected silence. Anything
else is a FAIL, with every diff and anomaly listed — and the fix belongs in
the program, not in the score.

**One PASS is not evidence: the one where nothing played.** No voice gated
and a silent recording passes every check above, because no check had
anything to disagree with. The report says so under the verdict (**Nothing
played**), the CLI prints `warning: nothing played`, and the payload carries
`nothing_played`. It is a legitimate result when your claim is that the
program is *quiet*; it is also exactly what a capture window that opened on
a title screen, or on a program that never started, produces. Confirm which
before you file it as audio evidence.

## The anomaly checks

Three, all reference-free — they run whether or not you wrote a score:

| Anomaly | What it means |
|---|---|
| Gate held over a zero frequency for more than 50 frames | A stuck gate or a zero-frequency drone: a real release drops the gate, and a real note has a frequency. |
| A note more than 15 cents off pitch for at least 25 frames | A tuning bug — most often a note table built for the other machine's clock (65 cents), or a wrong table index. Short blips are exempt: those are slides and arpeggios. |
| A note the log calls sounding while the WAV says nothing sounded, for more than a second | The gate is held over an envelope that already decayed — a sustain of 0 with no release. The transcription and the piano roll over-report the note's audible length by that much. Needs the WAV; a register-only report cannot see it. |

**The detune check does not apply to noise, and must not.** Noise is an
LFSR clocked by the oscillator, so `$D400/$D401` sets how *bright* it is,
not what pitch it is — there is no pitch to be out of tune with. The report
still names the note the frequency register works out to, because that is
what the register holds and what positions the bar in the roll, but its
cents column reads `-`. Drum accents on voice 3 are ordinary C64 arranging;
they are not a tuning finding.

**Frames are the timeline.** The log carries no cycle counts; the frame
index is the clock. At PAL 50 fps frame 100 is 2.00 s in; at NTSC 60 fps it
is 1.67 s. Score lengths, roll positions and report offsets are all frames.

**The speed caveat — captures run in real time.** Sessions boot headless
*and under warp*, which is why everything else in this toolset is fast. A
capture cannot: for its duration it takes the machine off warp and pins
`Speed` to 100, **so the WAV and the frame log share one timeline**, then
restores what it found. (Warp is not a resource on VICE 3.10 — it is
cleared over VICE's text monitor, which the capture starts on the session at
need. The sample rate is the sound device's and does not depend on warp.)

The rule is not a nicety. Under warp VICE writes a **zero-frame** WAV — not
time-compressed audio, nothing at all — so a capture that fails to clear
warp comes back empty rather than merely fast.

Real time is the **floor** on what a capture costs, not the price: **a
30-second capture takes at least 30 seconds of wall clock, and in practice
two to three times that.** The sampling loop advances the machine one frame
per monitor round trip, so every logged frame costs one — about 42 ms each
over ~1.1 s of fixed cost when it was measured (2026-08-04, NTSC session,
captures of 30, 60 and 120 frames). Thirty emulated seconds is 1500 PAL
frames or 1800 NTSC ones, which puts that capture at roughly 60–80 s of wall
clock. `c64 audio capture --help` carries the same measurement. Two
consequences:

- Capture the shortest span that proves the claim — one phrase, one effect,
  the bar where the tempo is supposed to change — not the whole tune. Five
  to fifteen seconds proves most claims.
- Size a tool timeout from wall clock, not from the seconds you asked for,
  and do not read the gap between the two as a hang.

`c64 audio record` is the exception, and only because it has no sampler:
nothing halts the machine between its start and its stop, so **there** a
3-second recording really does cost 3 real seconds.

**Capture the right moment.** The tools record what is playing when you call
them; they do not start the music for you. Drive the machine to the moment
first — `c64 until` on your per-frame tick label, a hidden key that jumps to
the act you want, a `c64 call` into the effect routine — and capture from
there. Same discipline as a screenshot: stage the state, then sample it.

### Triggering inside the window: `--at-frame`

For anything **shorter than the lead-in**, staging beforehand does not work
and no amount of care fixes it. Two facts close every outside route:

- Arming spends emulated frames before log frame 0. Every capture now
  measures its own and reports it as `lead_in_frames`.
- Once the window is open, the sampling loop owns the session. It runs as one
  round trip inside the session daemon, so a `c64 mem write` from anywhere
  else waits for the whole capture rather than landing inside it.

So a six-frame laser triggered by a poke is always over before frame 0.
Schedule it instead:

```
c64 audio capture 1 out/ --at-frame 20 '$d404=$81' --at-frame 26 '$d404=$80'
```

Over MCP the same thing is `at_frame={"20": "$d404=$81", "26": "$d404=$80"}`.
The writes happen while the machine is halted, immediately before the resume
that runs frame N, so **frame N is the first logged frame that shows them**
and the schedule costs no emulated time at all. Repeats of one frame merge in
order, so a frequency and its gate go in one flag: `--at-frame 20
'$d400=$67,$d401=$11,$d404=$41'`.

This is also the honest way to test an effect the *game* cannot be made to
fire: driving the real input edge needs the KERNAL scan the program has
usually turned off, and a held key pins its byte to one value instead of
producing an edge. Writing the effect's own registers at a named frame proves
the sound, not the input path — say which of the two you are claiming.

**`lead_in_frames` is null on programs that own the IRQ.** It is measured
from the KERNAL jiffy at `$A0-$A2`, which the KERNAL's own interrupt handler
increments — a player that takes the IRQ over freezes it, and null then means
"not measured", never "no lead-in". Reach for `--at-frame` rather than for a
number in that case.

### Give the program a silent lead-in

Whether the program is BASIC or assembly, arming the capture takes real time
and the first thing the program plays is lost to it. The fix is the same
shape in both — start with a silent delay — but where the delay lives
differs, and putting it in the wrong place makes the tune worse.

**In BASIC** there is usually nothing to drive it *to*: you type `run` and
the music starts. Two things then go wrong at once, and one line in the
program fixes both: **start the program with a silent delay, and make sure
warp is off.**

Arming the capture is not instant. Starting the WAV recorder, clearing warp
and pinning the speed took about **0.75 s** when it was measured (2026-08-06,
NTSC session), and a program that begins playing on the first frame loses its
opening to that. A lead-in long enough to cover it — **8 seconds was
comfortable** — puts the first note safely inside the window, and costs
nothing, because leading silence is exempt from the diff.

The lead-in must be counted in a clock that is still running at real time,
which is the other half of the rule. Under warp, emulated time races: a
jiffy-counted delay that reads as 8 seconds to the program evaporates in a
fraction of a real second, long before the capture has pinned the machine. So
turn warp off *before* the program starts its delay, not as part of arming.
In a BASIC program the delay itself is the usual `t=ti : if ti-t<480 goto …`
one-shot — a legitimate use of `TI`, and not the same thing as pacing a
sequencer on it.

**In assembly the music usually starts on a state entry** — the title screen
comes up, an act begins — and you *can* drive the machine to that moment, so
the lead-in is smaller but not optional: arming still consumed about **84
frames (1.4 s)** on the run this was measured on (2026-08-07, NTSC), which
is a phrase and a half of a fast tune. You no longer have to take that figure
on trust: every capture now measures its own and reports it as
`lead_in_frames`, so size the program's silent lead-in against the number
this host and this program actually produce.

The mistake to avoid is baking the silence into the track data. A player
that loops its pattern replays the lead-in every time round, which puts a
two-second hole in the middle of the tune to solve a problem that only
exists at the start. **Take the lead-in as a parameter to the player's start
routine — a row count, consumed once and cleared — so looping is
unaffected.** Sixteen rows at 8 frames a row is 128 frames, which cleared
the measured 84 comfortably:

    ; musstart: A = rows of silence to play before row 0
    musstart:
            sta     muslead         ; ... and mustick decrements it to zero
            lda     #0              ;     before it fetches its first row
            sta     musrow
            rts

## Writing a reference score

The score is a small YAML file you author from your own music data. It is
the claim; the capture is the check.

```yaml
tempo_frames_per_row: 6      # optional
voices:
  1:
    - {note: E4, frames: 12}
    - {note: rest, frames: 4}
  2: []
  3: []
```

`note` is a note name (`C4`, `F#3`, `A#5`) or `rest`; `frames` is that
note's length in frames, and it is optional — omit it to check the note but
not its duration.

**Spell the note however your music data spells it.** The comparison is by
pitch, not by string: `Ab4`, `A♭4`, `G#4` and `G♯4` are one note, and `Cb4`
is `B3` — an octave digit down, checked as such, so a genuine wrong-octave
bug still fails. The transcription itself only ever emits sharps, because a
frequency carries no key signature to choose a spelling from; a diff quotes
both when they differ (`expected Ab4 (= G#4), heard A4 at frame 96`).

Only the voices the score lists are compared, so listing all three is a
convention rather than a rule: an empty list is the positive claim "this
voice sits out the captured passage", while omitting a voice claims nothing
about it at all. Write all three, and the score says what every voice did.

**Leading and trailing silence are exempt.** A capture usually opens a few
frames before the player's first gate and closes mid-phrase, and neither is
a mistake — so an unscored rest at either end is skipped rather than diffed.
Score the opening rest explicitly when its length is part of the claim, and
it is compared like any other entry.

**The window's edges cut notes in half.** You start the music *before* you
capture, so the window opens mid-note: whatever was sounding at the first
sample is caught only in part, and how much depends on how long arming took.
**Omit `frames` on the first entry of every voice that is already playing** —
the note is still checked, its truncated length is not. Continuous music
closes the window the same way, so omit `frames` on the last entry too,
unless the passage ends in silence you arranged to be there (a capture that
runs past the final gate-off has that last note pinned at both its ends, so
it can carry a duration — the first entry's rule above still applies).

**Score the window, not the phrase.** Silence past the end of a voice's list
is exempt, but an extra *sounding* note is a diff by design — so a score that
stops eight notes into a window holding twelve fails on the last four. Count
what the window holds and list exactly that many events.

**And the window's contents have to be under your control.** Counting what
the window holds only helps if you decide what it holds — a score is a claim
about *every voice for every frame*, not about the music, so anything else in
the program that can gate a voice is in the score whether you meant it or
not. La Galaxia's first play score was captured over ordinary gameplay, so
alongside the melody it scored the enemies' dive whines and the collisions
the game raised on its own. It passed on the run it was written from and
failed on the next one, when an edit to the wave tables moved the enemies:
the same effects fired on different frames, and nothing about the music had
changed. **The fix is to take the other sounds out of the window, not into
the score** — clear the enemy state (and anything else that can seize a
voice) immediately before the capture opens, so the only thing gating a voice
during the window is the thing you are claiming about. Stage the window the
way you stage a screenshot; a score over a window you do not control is a
test that fails on the next unrelated change, and a re-scored one just moves
the failure to the change after that.

Both edges are where a first fully-durationed attempt fails, and neither is a
reason to do what the next paragraph forbids. In the Project64 repo,
`tests/data/arpeggio-score.yaml` is this shape in miniature: an undurationed
first note because the fixture was already sounding, two whole notes pinned
to the frame, and a window that closes inside the fixture's own trailing
silence.

**Durations drift, and omitting `frames` is a legitimate score.** The frame
tick is paced on the jiffy clock, which is not the video frame rate, so a
note's measured length wanders by a frame over a few hundred. A score
without `frames` still claims the note sequence — which is the substantive
claim about the music — and is what to reach for when the passage is long.
Pin durations where a specific length *is* the claim (a tempo change, a
staccato figure) and leave them off elsewhere.

#### Make the passage a one-shot cue

The window's edges are only a problem while the music is still playing at
both of them. For anything that is a *cue* rather than a loop — an
intermission's music, a jingle, a death spiral — you can arrange for neither
edge to land on a note at all: give the track a terminator that stops the
voice for good, make the cue shorter than the window, and capture a window
that opens before it and closes after it. Both edges then fall in silence,
both are exempt from the diff, and the score becomes the whole phrase with
no dependence on how long arming took.

This is worth restructuring a player for. The dogfood's three intermission
cues are 24 rows inside a 360-frame window; their scores passed unchanged
across four separate capture runs, where durationed scores against a looping
tune had failed on every one.

**Write it from your note data, not from the transcription.** Capturing
first and pasting the transcribed notes back in as the score produces a
diff that passes by construction — with your bug baked in as the
specification. Read the transcription to *understand* a failure; write the
score from the sequencer table you composed.

**What divides one entry from the next is the note name, not the gate.** The
transcription starts a new event whenever the pitch it reads changes, so a
pitch change under a held gate is a new note — and two equal pitches in a row
**merge into one entry**, re-gated or not, unless a frame of silence separates
them. That is the rule that turns your sequencer table into score entries:
walk your own data, collapse consecutive equal pitches, and list what is left.

**A worked example.** Say your melody pattern is one row per 6 frames and
the rows are `E4 E4 rest G4`, with the player holding the gate across a
repeated row rather than retriggering it. Two held rows are one 12-frame
note, so the score is:

```yaml
tempo_frames_per_row: 6
voices:
  1:
    - {note: E4, frames: 12}
    - {note: rest, frames: 6}
    - {note: G4, frames: 6}
  2: []
  3: []
```

If instead your player re-gates on every row, what the score says depends on
*where in the frame* the re-gate happens, and that is a design decision worth
making on purpose:

- **Drop and re-raise the gate inside one frame** — both writes between two
  samples. The note retriggers audibly, the sampler never sees the gate low,
  and the two rows come back as one 12-frame E4, indistinguishable from the
  held version above. Every note is articulated *and* every duration stays
  whole, so the score is exactly `frames = ticks × frames_per_tick`. This is
  the option to reach for when you want the arithmetic to be predictable.
- **Spread the drop across a frame boundary** — gate low at one sample, high
  at the next. Now the rest is visible, and it costs **a 1-frame rest per
  note** that the score has to list: a 6-frame E4, a 1-frame rest, a 5-frame
  E4. Reach for this when the note boundaries themselves are part of the claim
  and you want the log to prove each one.

Both are correct players. The choice belongs in the player, and the score
follows it — so decide which one you are writing before you write either.

#### Generate the score: model the player one frame at a time

Hand-counting is fine for the four rows above. For a whole tune it is not,
and the arithmetic that looks obvious — rows × frames-per-row, one entry per
notated note — is wrong for the reason the worked example just gave: what the
player does at a note boundary happens inside the frame grid, and the score
describes that grid, not the sheet. The rule is constructive, and it is two
steps:

1. **Model the player one frame at a time.** Walk your own sequencer data and
   emit one entry per frame — the note name a once-per-frame sampler would
   read on that frame, or `rest` — *including* the frames the player spends
   with the gate down.
2. **Run-length encode that list.** Collapse consecutive equal entries into
   one `{note, frames}`, and that is the score.

It works because it is the same algorithm the transcriber runs from the other
side: it also reads one sample per frame and merges equal neighbours (see
*What divides one entry from the next*, above). Two models of the same grid
agree by construction. This is **not** the forbidden move of pasting a
transcription back in as the score — the input is your note table, not the
capture, so a player that gates the wrong voice, drops a row, or indexes the
wrong note still fails the diff.

Skipping the model costs a capture to rediscover. La Galaxia's first
generator walked rows and multiplied: every note came out one frame too long and no
leading rest was listed anywhere, because the gate-down frame a retrigger
costs exists in the frame grid and not in the row data.

`demos/la-galaxia/tools/genmusic.py` is the worked example. `per_frame()` is
the model — rows in, one entry per frame out:

```python
for entry in part:                    # one entry per row
    if entry == NOTE_OFF:
        gate = False
    elif entry != NOTE_HOLD:          # a new note: this row retriggers
        cur, gate, trig = entry, True, True
    for _ in range(ROWTICKS):         # the row's frames, one at a time
        if cur is None or not gate:
            out.append("rest")
        elif trig:
            trig = False
            out.append("rest")        # the gate-down frame the retrigger costs
        else:
            out.append(cur)
```

and `events()` is the run-length encoder over its output — six lines that
turn the pattern tables into the YAML. Two details there are worth copying.
The model takes the voice's **state on entry to the window** (the note it is
already holding, and whether that note is gated), which is what makes a score
starting mid-phrase come out right; and it takes an **overlay** of the frames
where a sound effect owns the voice, so the score says what the chip did
rather than what the music alone would have done.

To check that the table entry behind `E4` really is E4, run the register
through the frequency formula — `hz = reg16 * clock / 2**24` — with *your
machine's* clock. E4 is 329.63 Hz, so the table value should be:

| Machine | Clock | `reg16` for E4 (`hz * 2**24 / clock`) | Bytes (`$D401`/`$D400`) |
|---|---|---|---|
| PAL | 985248 Hz | 5613 | `$15` / `$ED` |
| NTSC | 1022727 Hz | 5407 | `$15` / `$1F` |

Which is also the most common tuning bug in a ported note table: an
NTSC-tuned table played on a PAL machine sounds **65 cents flat** on every
note. The report names that as a `cents_off` of the same size on every note
instead of leaving you with a mystery.

**A score is optional.** Without one you still get the transcription, the
roll, the anomalies and the WAV metrics — useful while you are still finding
out what your player does. A demo's committed audio evidence needs the
score: without it the report has nothing to fail against.

## Reading a piano roll

X axis is frames, Y axis is pitch. The voice colors are pinned so rolls
compare across runs and across demos: **voice 1 red, voice 2 green, voice 3
blue**. Read it like a screenshot — deliberately, against what you claimed,
not for a general impression of health.

| What you see | What it usually is |
|---|---|
| A color missing entirely | The player never gated that voice: a voice-allocation bug, or an effect seized it and never handed it back. |
| A color that stops partway and never returns | The effect/music priority rule releases the gate but never resumes the sequencer on that voice. |
| One long bar where the score has repeated notes | Either the gate is never released between notes, or it is released and re-set *inside* one frame, which the once-per-frame sampler cannot see. The first is a player bug; the second is a correct player that retriggers audibly. The roll cannot tell them apart — read the player's gate handling to decide. |
| A long bar over a spectrogram that went dark under it | The gate is held over an envelope that decayed to nothing (sustain 0, no release), so the bar over-reports how long the note was audible. Flagged as an anomaly when the WAV is there to say so. |
| Bars of ragged, unequal length where the score is even | Tempo drift: the sequencer is driven from a loop instead of the frame tick, or a frame counter is reset on the wrong branch. |
| The melody's contour inverted or scrambled | Note-table index off by one, or the frequency high/low bytes swapped. |
| Every note offset by the same small amount | Wrong clock for the table (see the PAL/NTSC row above) — check `cents_off`, not the shape. |
| Notes that are one frame long | The gate was sampled set at one frame boundary and clear at the next, so the note lasted about a frame and the envelope barely attacks. Not the same as a gate set *and* cleared between two samples — that one leaves no bar at all (see *Known facts*). |
| Bars where the score says rest | An un-zeroed gate bit left over from the previous section, or an effect firing on a voice it was not assigned. |

The roll is the diff's picture. A diff is a line of prose, not a range —
`voice 1 event 3: expected C4, heard A4 at frame 120` — so it gives you a
voice and the frame the offending event *starts* on. Find that voice's bar
at that frame in the roll, and read forward from it, before touching code.

## WAV metrics and what they catch

`wav_metrics` reports four things about `capture.wav`, and each catches a
class of bug the register log is blind to:

| Metric | What it catches |
|---|---|
| `duration_s` | That the capture really ran as long as you asked. Far short means the speed pin did not hold or the session died mid-capture — the whole artifact set is then suspect. |
| `clipped_samples` | Three voices at volume 15 sum past full scale. Clipping is a mixing bug; every register in the log is perfect while the output crunches. |
| `silence_windows` | The audio stopped. Cross-check with the roll: registers changing while the WAV is silent means `$D418` volume is 0 or the filter is swallowing the voices; registers static too means the sequencer or its IRQ died. A window sitting *under* a note the roll draws is the third anomaly above, and the report makes that cross-check for you. |
| `rms_db_profile` | Level over time — an effect that drowns the music because nothing ducks it, a fade that never fades, a heartbeat that is supposed to grow and does not. |

The **spectrogram** is where everything the note transcription cannot
describe shows up: a filter cutoff sweep is a moving edge, filtered noise (a
cannon, an explosion) is a broadband smear that should narrow as the sweep
closes, and ring modulation or sync puts sidebands around the carrier. If a
spec bullet says "filtered noise with a downward cutoff sweep", the
spectrogram is the evidence for it.

One limit: the WAV is a mix, so it can never tell you *which voice*. Pair
every WAV finding with the roll before naming a cause.

## Known facts

- **Register readback works in the emulator.** VICE's monitor returns device
  state for `$D400+` — verified 2026-08-02 by writing `42 21 11` and reading
  back the same bytes. Sampling therefore needs no cooperation from the
  running program: no shadow block, no checkpoint, no instrumentation.
- **On real hardware `$D400–$D418` is write-only** (only `$D419`–`$D41C`
  read back: paddles, oscillator 3, envelope 3). That is why demos still
  mirror every SID write into a RAM shadow block — the shadow is the
  program's own evidence and holds on a real C64, the register log is the
  emulator's. Keep both; they fail in different directions.
- **Register map** (details in `references/hardware.md`): the block is
  `$D400–$D418`, 25 bytes. Voice *v* (1–3) is based at `$D400 + 7*(v-1)`:
  +0/+1 frequency lo/hi, +2/+3 pulse width lo/hi, +4 control (bit 0 gate,
  bits 4–7 waveform), +5 attack/decay, +6 sustain/release. Globals:
  `$D415`/`$D416` filter cutoff, `$D417` resonance + routing, `$D418` volume
  + filter mode.
- **Frequency:** `hz = reg16 * clock / 2**24`.
- **Clocks and frame rates:** PAL `985248` Hz at 50 fps, NTSC `1022727` Hz
  at 60 fps. The analysis resolves both from the session's machine model —
  never hardcode a clock, and never compare a PAL capture against an
  NTSC-tuned score without converting. A capture stamps its machine on line 1
  of `sid-log.jsonl`, so a later `c64 audio report` on that log resolves the
  clock without a session; `clock_source` in the payload says whether it came
  from the stamp (`log`), from `-s` (`session`), or from nowhere (`default`,
  meaning PAL was assumed).
- **One resume is one frame — not a `$D012` poll.** On real hardware a read
  of `$D012` (the raster line's low byte) wrapping to a smaller value marks
  a new frame, and that is what this reference used to claim the sid log
  did. It cannot: VICE picks up a binary-monitor command at the next vsync,
  so the machine only ever halts at the top of a frame and `$D012` reads 12
  at every halt, forever (measured 2026-08-04: 600 consecutive reads, all
  12, with and without read side effects; `LIN 12 / CYC 0-2` in every
  register dump). The halt itself is the frame boundary, so the log samples
  once per resume and needs no raster at all — and this works whether your
  program runs off a raster IRQ, the jiffy clock, or nothing at all.
- **Gate transitions inside a single frame are invisible — and that is a tool,
  not only a limit.** The control register is read once per frame, so a gate
  that goes low and high again between two samples leaves no trace: the driver
  retriggers audibly, the log shows the gate set at every sample, and two
  re-gated 6-frame notes come back as one 12-frame note with no anomaly to
  flag it. Read one way that is a blind spot — nothing in the log recovers the
  boundary, so leave at least one frame of gate-off between notes when their
  boundaries are part of the claim. Read the other way it is how a player
  articulates every note while keeping every scored duration a whole multiple
  of its tick, with no 1-frame rests to list. Pick the reading you want and
  write the player to it; the score follows the player, not the sheet.
- **A warped session can drop frames from the log.** Sampling costs one
  round trip per frame. A real-time frame is many times that, so nothing
  slips (200 samples over 201 elapsed frames, measured against the KERNAL
  jiffy); a warped frame is about as long as the round trip, so the odd
  frame goes unrecorded (200 over 202). VICE exposes no frame or cycle
  counter to the binary monitor, so a missed frame can be flagged but never
  counted: the tools warn, and the log's frame numbers count captured frames
  rather than elapsed ones. Pin real time — any full capture does — whenever
  the timeline matters. The warning is one-sided, so its *absence* proves
  nothing: a warped session that sampled slowly (loaded host) never trips it
  while dropping most frames.
- **`sample_rate_hz` is wall clock, not the frame rate above.** It counts
  samples per second of real time, and it neither equals nor approaches the
  machine's 50/60 fps: the emulator advances only between round trips, so a
  pinned log measures ~22 samples/s from a 60 Hz machine (200 samples over
  9.1 s) while still covering every emulated frame. Read it one-sidedly —
  above the machine's frame rate, nothing sampled at real time, because
  nothing samples more often than once per frame; below it, the number says
  nothing, since the pinned rate is set by host latency. The separation is
  wide enough to be useful anyway: that same 200-frame log measured ~22/s
  pinned against ~425/s warped.
- **The warning's threshold is fixed, and it is the NTSC one.** It fires
  above 63/s — 60 fps plus a 5% margin — whatever machine the session is.
  On a PAL session that leaves 50 to 63/s unflagged, although a 50 fps
  machine cannot sample above 50/s either. Apply the machine's own frame
  rate to `sample_rate_hz` yourself when the timeline matters; the built-in
  warning is a backstop, not the check.

Related: `references/hardware.md` for the SID register, ADSR and note
tables; `references/cookbook.md` for working sound recipes; and, in the
Project64 repo, `docs/graphics-and-sprites.md` for the screenshot half of
the same evidence convention.
