# SID audio verification

## Transcription

### Voice 1

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 16 | G#4 | +0.0 | pulse | 16 |
| 16 | 16 | G4 | -0.1 | pulse | 16 |
| 32 | 16 | rest | - | pulse | 0 |
| 48 | 16 | A4 | +0.0 | pulse | 16 |
| 64 | 16 | B4 | +0.0 | pulse | 16 |
| 80 | 16 | C5 | +0.1 | pulse | 16 |
| 96 | 8 | F4 | +0.0 | pulse | 8 |
| 104 | 8 | D#4 | +0.1 | pulse | 8 |
| 112 | 8 | D4 | -0.1 | pulse | 8 |
| 120 | 24 | C4 | +0.1 | pulse | 24 |
| 144 | 8 | C5 | +0.1 | pulse | 8 |
| 152 | 8 | B4 | +0.0 | pulse | 8 |
| 160 | 16 | C5 | +0.1 | pulse | 16 |
| 176 | 16 | G4 | -0.1 | pulse | 16 |
| 192 | 16 | G#4 | +0.0 | pulse | 16 |
| 208 | 8 | C5 | +0.1 | pulse | 8 |
| 216 | 8 | B4 | +0.0 | pulse | 8 |
| 224 | 16 | C5 | +0.1 | pulse | 16 |
| 240 | 16 | D5 | +0.0 | pulse | 16 |
| 256 | 16 | G4 | -0.1 | pulse | 16 |
| 272 | 8 | C5 | +0.1 | pulse | 8 |
| 280 | 8 | B4 | +0.0 | pulse | 8 |
| 288 | 16 | C5 | +0.1 | pulse | 16 |
| 304 | 16 | D5 | +0.0 | pulse | 16 |
| 320 | 8 | F4 | +0.0 | pulse | 8 |
| 328 | 8 | G4 | -0.1 | pulse | 8 |
| 336 | 32 | G#4 | +0.0 | pulse | 32 |
| 368 | 8 | G4 | -0.1 | pulse | 8 |
| 376 | 8 | F4 | +0.0 | pulse | 8 |
| 384 | 64 | E4 | -0.1 | pulse | 64 |
| 448 | 392 | rest | - | pulse | 0 |

### Voice 2

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 16 | B3 | +0.0 | sawtooth | 16 |
| 16 | 16 | C4 | +0.1 | sawtooth | 16 |
| 32 | 16 | rest | - | sawtooth | 0 |
| 48 | 16 | C4 | +0.1 | sawtooth | 16 |
| 64 | 8 | F4 | +0.0 | sawtooth | 8 |
| 72 | 8 | D4 | -0.1 | sawtooth | 8 |
| 80 | 8 | D#4 | +0.1 | sawtooth | 8 |
| 88 | 24 | C4 | +0.1 | sawtooth | 24 |
| 112 | 16 | B3 | +0.0 | sawtooth | 16 |
| 128 | 32 | C4 | +0.1 | sawtooth | 32 |
| 160 | 16 | rest | - | sawtooth | 0 |
| 176 | 16 | E4 | -0.1 | sawtooth | 16 |
| 192 | 32 | F4 | +0.0 | sawtooth | 32 |
| 224 | 16 | rest | - | sawtooth | 0 |
| 240 | 32 | F4 | +0.0 | sawtooth | 32 |
| 272 | 8 | D#4 | +0.1 | sawtooth | 8 |
| 280 | 8 | D4 | -0.1 | sawtooth | 8 |
| 288 | 16 | D#4 | +0.1 | sawtooth | 16 |
| 304 | 16 | F4 | +0.0 | sawtooth | 16 |
| 320 | 16 | B3 | +0.0 | sawtooth | 16 |
| 336 | 16 | rest | - | sawtooth | 0 |
| 352 | 16 | B3 | +0.0 | sawtooth | 16 |
| 368 | 16 | rest | - | sawtooth | 0 |
| 384 | 64 | G3 | -0.1 | sawtooth | 64 |
| 448 | 392 | rest | - | sawtooth | 0 |

### Voice 3

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 32 | D#2 | +0.1 | triangle | 32 |
| 32 | 16 | rest | - | triangle | 0 |
| 48 | 16 | D#3 | +0.1 | triangle | 16 |
| 64 | 16 | D3 | +0.2 | triangle | 16 |
| 80 | 16 | C3 | +0.1 | triangle | 16 |
| 96 | 16 | G3 | -0.1 | triangle | 16 |
| 112 | 16 | G2 | +0.4 | triangle | 16 |
| 128 | 320 | C3 | +0.1 | triangle | 320 |
| 448 | 392 | rest | - | triangle | 0 |

## Score diff

No differences against the reference score — an empty diff list is also what a run with no reference score produces.

## Anomalies

None found.

## WAV metrics

| Metric | Value |
|---|---|
| Duration | 14.29 s |
| Clipped samples | 0 |
| Silence windows | 7.90-14.29 s |
| RMS min / median / max | -65.9 / -21.0 / -19.1 dBFS over 143 windows of 0.1 s |

## Artifacts

- [capture.wav](capture.wav)
- [sid-log.jsonl](sid-log.jsonl)
- [piano-roll.png](piano-roll.png)
- [spectrogram.png](spectrogram.png)

## Verdict

**PASS**
