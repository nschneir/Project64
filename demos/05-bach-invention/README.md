# Bach's Invention No. 13

J. S. Bach's Invention No. 13 in A minor, BWV 784, played through the SID
from a Commodore BASIC program. The invention is written in two parts, so
voice 1 takes the upper part and voice 2 the lower, answering each other in
imitation; voice 3 carries noise-waveform percussion accents that Bach did
not write and that the agent designs itself.

This is the demo that exercises **audio verification**. Every other demo is
proved with screenshots and memory reads — things an agent can look at. Music
is the case where an agent cannot check its own work by looking, so the run
turns on the register-level tooling instead: a reference score written from
the program's own note data, a capture checked against it, and a piano roll
the agent has to read and describe.

**What a passing run shows.** At least the first 16 bars play with the two
parts clearly independent and the subject audibly answered rather than
accompanied; a YAML reference score written *before* the capture and derived
from the program's note data rather than from the tool's transcription; a
capture whose report passes with an empty score diff and no anomalies; a
piano roll the agent reads back in words — two melodic lines plus regular
percussive marks on voice 3; WAV metrics with no clipping and no silence
where music should be; and a `capture.wav` handed over for a human listen.

The tempo evidence is the score diff itself. BASIC driving three voices is
where timing drifts, and drift shows up as transcribed note durations
diverging from the reference's frame counts — so a diff that stays empty
across the whole passage is the proof the loop held its pulse.

Beyond this README, `PROMPT.md` is all this directory holds. The program the
agent writes and the audio evidence it reads off the running machine are the
deliverable of the run, not files committed here.
