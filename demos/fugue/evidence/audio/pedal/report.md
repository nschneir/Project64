# SID audio verification

## Transcription

### Voice 1

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 5 | G4 | -0.1 | pulse | 5 |
| 5 | 16 | rest | - | pulse | 0 |
| 21 | 16 | A4 | +0.0 | pulse | 16 |
| 37 | 16 | B4 | +0.0 | pulse | 16 |
| 53 | 16 | C5 | +0.1 | pulse | 16 |
| 69 | 8 | F4 | +0.0 | pulse | 8 |
| 77 | 8 | D#4 | +0.1 | pulse | 8 |
| 85 | 8 | D4 | -0.1 | pulse | 8 |
| 93 | 24 | C4 | +0.1 | pulse | 24 |
| 117 | 8 | C5 | +0.1 | pulse | 8 |
| 125 | 8 | B4 | +0.0 | pulse | 8 |
| 133 | 16 | C5 | +0.1 | pulse | 16 |
| 149 | 16 | G4 | -0.1 | pulse | 16 |
| 165 | 16 | G#4 | +0.0 | pulse | 16 |
| 181 | 8 | C5 | +0.1 | pulse | 8 |
| 189 | 8 | B4 | +0.0 | pulse | 8 |
| 197 | 16 | C5 | +0.1 | pulse | 16 |
| 213 | 16 | D5 | +0.0 | pulse | 16 |
| 229 | 16 | G4 | -0.1 | pulse | 16 |
| 245 | 8 | C5 | +0.1 | pulse | 8 |
| 253 | 8 | B4 | +0.0 | pulse | 8 |
| 261 | 16 | C5 | +0.1 | pulse | 16 |
| 277 | 16 | D5 | +0.0 | pulse | 16 |
| 293 | 8 | F4 | +0.0 | pulse | 8 |
| 301 | 8 | G4 | -0.1 | pulse | 8 |
| 309 | 32 | G#4 | +0.0 | pulse | 32 |
| 341 | 8 | G4 | -0.1 | pulse | 8 |
| 349 | 8 | F4 | +0.0 | pulse | 8 |
| 357 | 64 | E4 | -0.1 | pulse | 64 |
| 421 | 419 | rest | - | pulse | 0 |

### Voice 2

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 5 | C4 | +0.1 | sawtooth | 5 |
| 5 | 16 | rest | - | sawtooth | 0 |
| 21 | 16 | C4 | +0.1 | sawtooth | 16 |
| 37 | 8 | F4 | +0.0 | sawtooth | 8 |
| 45 | 8 | D4 | -0.1 | sawtooth | 8 |
| 53 | 8 | D#4 | +0.1 | sawtooth | 8 |
| 61 | 24 | C4 | +0.1 | sawtooth | 24 |
| 85 | 16 | B3 | +0.0 | sawtooth | 16 |
| 101 | 32 | C4 | +0.1 | sawtooth | 32 |
| 133 | 16 | rest | - | sawtooth | 0 |
| 149 | 16 | E4 | -0.1 | sawtooth | 16 |
| 165 | 32 | F4 | +0.0 | sawtooth | 32 |
| 197 | 16 | rest | - | sawtooth | 0 |
| 213 | 32 | F4 | +0.0 | sawtooth | 32 |
| 245 | 8 | D#4 | +0.1 | sawtooth | 8 |
| 253 | 8 | D4 | -0.1 | sawtooth | 8 |
| 261 | 16 | D#4 | +0.1 | sawtooth | 16 |
| 277 | 16 | F4 | +0.0 | sawtooth | 16 |
| 293 | 16 | B3 | +0.0 | sawtooth | 16 |
| 309 | 16 | rest | - | sawtooth | 0 |
| 325 | 16 | B3 | +0.0 | sawtooth | 16 |
| 341 | 16 | rest | - | sawtooth | 0 |
| 357 | 64 | G3 | -0.1 | sawtooth | 64 |
| 421 | 419 | rest | - | sawtooth | 0 |

### Voice 3

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 5 | D#2 | +0.1 | triangle | 5 |
| 5 | 16 | rest | - | triangle | 0 |
| 21 | 16 | D#3 | +0.1 | triangle | 16 |
| 37 | 16 | D3 | +0.2 | triangle | 16 |
| 53 | 16 | C3 | +0.1 | triangle | 16 |
| 69 | 16 | G3 | -0.1 | triangle | 16 |
| 85 | 16 | G2 | +0.4 | triangle | 16 |
| 101 | 320 | C3 | +0.1 | triangle | 320 |
| 421 | 419 | rest | - | triangle | 0 |

## Score diff

No differences against the reference score — an empty diff list is also what a run with no reference score produces.

## Anomalies

None found.

## WAV metrics

| Metric | Value |
|---|---|
| Duration | 14.27 s |
| Clipped samples | 0 |
| Silence windows | 7.40-14.27 s |
| RMS min / median / max | -65.6 / -38.8 / -19.0 dBFS over 143 windows of 0.1 s |

## Artifacts

- [capture.wav](capture.wav)
- [sid-log.jsonl](sid-log.jsonl)
- [piano-roll.png](piano-roll.png)
- [spectrogram.png](spectrogram.png)

## Verdict

**PASS**
