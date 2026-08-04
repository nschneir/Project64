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
| `c64_audio_capture` — `c64 audio capture …` | **The one you want.** Starts the recorder, logs the frames, stops the recorder, analyses, and writes all five artifacts. Over MCP: `c64_audio_capture(seconds, outdir, ref, session)`; the CLI takes the same values (`--help` for the exact spelling). |

**The artifact set.** `c64_audio_capture` writes exactly these five files
into `outdir`, under those exact names, so every demo's audio evidence looks
the same:

| File | What it is |
|---|---|
| `capture.wav` | The machine's audio output. The maintainer's listen is the final gate, and this is what gets listened to. |
| `sid-log.jsonl` | One line per frame: `{"frame": <int>, "regs": [25 ints]}`, `regs[0]` = `$D400`. The raw evidence — everything else is derived from it. |
| `piano-roll.png` | Transcribed notes per voice over time. |
| `spectrogram.png` | The WAV's frequency content over time — where the filter and the noise live. |
| `report.md` | Transcription, score diff, anomalies, WAV metrics, and the overall verdict. |

The verdict is PASS only when the score diff is empty, no anomalies were
found, and the WAV shows no clipping and no unexpected silence. Anything
else is a FAIL, with every diff and anomaly listed — and the fix belongs in
the program, not in the score.

**Frames are the timeline.** The log carries no cycle counts; the frame
index is the clock. At PAL 50 fps frame 100 is 2.00 s in; at NTSC 60 fps it
is 1.67 s. Score lengths, roll positions and report offsets are all frames.

**The speed caveat — captures run in real time.** Sessions boot headless
*and under warp*, which is why everything else in this toolset is fast. A
capture cannot: for its duration it clears `WarpMode` and pins `Speed` to
100 so the recorded WAV has the right sample rate and the frame log paces to
real frames, then restores what it found. **A 30-second capture takes 30
seconds of wall clock.** Two consequences:

- Capture the shortest span that proves the claim — one phrase, one effect,
  the bar where the tempo is supposed to change — not the whole tune. Five
  to fifteen seconds proves most claims.
- Do not wrap a long capture in a short tool timeout, and do not read the
  wall-clock cost as a hang.

**Capture the right moment.** The tools record what is playing when you call
them; they do not start the music for you. Drive the machine to the moment
first — `c64 until` on your per-frame tick label, a hidden key that jumps to
the act you want, a `c64 call` into the effect routine — and capture from
there. Same discipline as a screenshot: stage the state, then sample it.

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
note's length in frames. All three voices are listed; a voice that sits out
the captured passage gets an empty list.

**Write it from your note data, not from the transcription.** Capturing
first and pasting the transcribed notes back in as the score produces a
diff that passes by construction — with your bug baked in as the
specification. Read the transcription to *understand* a failure; write the
score from the sequencer table you composed.

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

If instead your player re-gates on every row, that same pattern is two
6-frame E4 notes — write what your player actually does. The gate is what
divides notes, so this is the one place where the score has to follow the
player rather than the sheet.

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
| One long bar where the score has repeated notes | The gate is never released between notes, so the notes never retrigger — the transcriber correctly sees one long note. |
| Bars of ragged, unequal length where the score is even | Tempo drift: the sequencer is driven from a loop instead of the frame tick, or a frame counter is reset on the wrong branch. |
| The melody's contour inverted or scrambled | Note-table index off by one, or the frequency high/low bytes swapped. |
| Every note offset by the same small amount | Wrong clock for the table (see the PAL/NTSC row above) — check `cents_off`, not the shape. |
| Notes that are one frame long | Gate set and cleared inside the same frame; the envelope never gets to attack. |
| Bars where the score says rest | An un-zeroed gate bit left over from the previous section, or an effect firing on a voice it was not assigned. |

The roll is the diff's picture: when `report.md` names a failing frame
range, look at that range in the roll before touching code.

## WAV metrics and what they catch

`wav_metrics` reports four things about `capture.wav`, and each catches a
class of bug the register log is blind to:

| Metric | What it catches |
|---|---|
| `duration_s` | That the capture really ran as long as you asked. Far short means the speed pin did not hold or the session died mid-capture — the whole artifact set is then suspect. |
| `clipped_samples` | Three voices at volume 15 sum past full scale. Clipping is a mixing bug; every register in the log is perfect while the output crunches. |
| `silence_windows` | The audio stopped. Cross-check with the roll: registers changing while the WAV is silent means `$D418` volume is 0 or the filter is swallowing the voices; registers static too means the sequencer or its IRQ died. |
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
  NTSC-tuned score without converting.
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
  while dropping most frames. The reported `fps` is the check that does — at
  real time it lands near the machine's frame rate.

Related: `references/hardware.md` for the SID register, ADSR and note
tables; `references/cookbook.md` for working sound recipes; and, in the
Project64 repo, `docs/graphics-and-sprites.md` for the screenshot half of
the same evidence convention.
