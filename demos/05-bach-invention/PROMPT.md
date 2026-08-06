# Bach's Invention No. 13 — three SID voices, driven from BASIC

Using the c64 CLI (see skills/c64-development/SKILL.md and docs/cli.md),
write a Commodore BASIC program for a Commodore 64 that plays **J. S. Bach's
Invention No. 13 in A minor, BWV 784** through the SID chip. The music is
public domain; Bach died in 1750.

BWV 784 is a *two-part* invention, so the parts map to the chip cleanly:

- **Voice 1** takes the upper part, **voice 2** the lower. They trade the
  subject in imitation — the second part answers the first rather than
  accompanying it, and that call-and-answer is the thing a listener
  recognizes. Keep both parts genuinely independent; do not collapse one
  into block chords under the other.
- **Voice 3 is yours.** Bach wrote no third part, so do not invent one.
  Use voice 3 for **noise/percussion accents** — a noise-waveform hit with a
  short decay marking the pulse, and whatever fills or accents you think
  earn their place. Keep it percussive, not melodic: it should read as a
  drum track laid under the invention, never as a third contrapuntal line.

Play at least the **first 16 bars** — enough that the imitation between the
two parts is unmistakable. More is welcome if the timing holds.

**Getting the notes right.** Source the score yourself and encode it as
note data (`DATA` statements are the natural fit), then derive each SID
frequency from the note and the machine's clock rather than hardcoding
register values you cannot check. The note tables and the
`hz = reg16 * clock / 2**24` relationship are in the skill's hardware
reference — mind that the PAL and NTSC clocks differ, so a table built for
the wrong one is uniformly sharp or flat by about 65 cents.

**Make it sound like an instrument.** Choose waveform and ADSR per voice
deliberately and say why: a plucked envelope suits the two parts, and the
noise voice wants a fast attack and short decay so it punctuates instead of
smearing. Set the volume at `$D418`, gate each note on and off (a note ends
when its gate bit clears), and give the two parts enough separation in
envelope that they stay distinguishable when they cross.

**Timing is the hard part, and it is the point.** BASIC is slow, and three
voices driven from an interpreted loop is exactly where tempo falls apart.
Hold each event a fixed number of frames, drive the loop off a clock you can
actually read, and keep the per-event work bounded — a loop that does more
work on some events than others will drift audibly.

## Prove it

Verify this the way the toolset verifies audio — by register-level evidence
and rendered artifacts, not by asserting it sounded fine:

1. **Write a reference score first.** Author the YAML reference from *your
   own note data*, before you capture — never from the transcription the
   tool produces. A reference derived from the output cannot fail, and a
   gate that cannot fail proves nothing.
2. **Capture against it** with `c64 audio capture` (or `c64_audio_capture`),
   long enough to cover the passage you claim to play. Real time is pinned
   for the duration and every logged frame costs a monitor round trip on top,
   so a 30-second capture takes at least 30 seconds of wall clock and in
   practice two to three times that — budget for it rather than cutting the
   capture short.
3. **The report must pass.** Show the verdict, the score diff (empty), and
   the anomalies (empty).
4. **Read your own piano roll**, the way you would read a screenshot, and
   say in words what you see: voice 1 and voice 2 as two independent lines,
   the subject appearing in the answering voice after it appears in the
   leading one, and voice 3 as regular percussive marks rather than a
   melodic contour. Wrong contour, a missing voice, or ragged bar spacing
   are bugs — report them as bugs.
5. **Show the tempo held.** The reference's per-note frame durations are
   what catch drift: if the loop slows under load, the transcribed durations
   diverge from the reference and the diff says so. Durations are compared
   with no tolerance, and a BASIC loop clocked off a frame counter has a
   frame of granularity per event — so a scattered one-frame difference is
   that resolution, not drift. Drift is a run of them, growing through the
   passage and all in the same direction. If the report fails on a handful of
   isolated ±1-frame diffs, report the verdict as it came out and say which
   they were; do not loosen the score to match the capture, which is the
   mistake in step 1 wearing a different hat.
6. **Show the WAV metrics** — no clipped samples, and no silence window
   where the music should be playing.
7. **Hand over `capture.wav`** at the end for a human listen. That listen is
   the final gate; the automated checks narrow what a human has to catch,
   they do not replace it.

If any of that disagrees with what you expected, treat the disagreement as
the finding and chase it down — a piano roll that contradicts your note data
means one of the two is wrong, and it is worth knowing which.

This is a test demo: nothing here is committed. The program you write and
the evidence you read off the running machine are the deliverable of the
run, so produce the artifacts, show them, and leave the directory as you
found it.

Work from this prompt and the skills alone: do not read any
`demos/*/README.md` — those READMEs are documentation for human readers
and can spoil the exercise.
