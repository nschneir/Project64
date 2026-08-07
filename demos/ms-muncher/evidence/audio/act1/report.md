# SID audio verification

## Transcription

### Voice 1

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 14 | rest | - | none | 0 |
| 14 | 32 | E4 | -0.1 | pulse | 32 |
| 46 | 32 | G4 | -0.1 | pulse | 32 |
| 78 | 48 | C5 | +0.1 | pulse | 48 |
| 126 | 16 | rest | - | none | 0 |
| 142 | 32 | D5 | -0.1 | pulse | 32 |
| 174 | 31 | C5 | +0.1 | pulse | 31 |
| 205 | 155 | rest | - | none | 0 |

### Voice 2

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 14 | rest | - | none | 0 |
| 14 | 64 | C4 | +0.1 | sawtooth | 64 |
| 78 | 64 | F4 | +0.0 | sawtooth | 64 |
| 142 | 63 | G4 | -0.1 | sawtooth | 63 |
| 205 | 155 | rest | - | none | 0 |

### Voice 3

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 14 | rest | - | none | 0 |
| 14 | 64 | C3 | +0.1 | triangle | 64 |
| 78 | 64 | F3 | -0.3 | triangle | 64 |
| 142 | 63 | G3 | -0.1 | triangle | 63 |
| 205 | 155 | rest | - | none | 0 |

## Score diff

No differences against the reference score — an empty diff list is also what a run with no reference score produces.

## Anomalies

None found.

## WAV metrics

| Metric | Value |
|---|---|
| Duration | 6.10 s |
| Clipped samples | 0 |
| Silence windows | 3.70-6.10 s |
| RMS min / median / max | -120.0 / -24.4 / -20.1 dBFS over 62 windows of 0.1 s |

## Artifacts

- [capture.wav](capture.wav)
- [sid-log.jsonl](sid-log.jsonl)
- [piano-roll.png](piano-roll.png)
- [spectrogram.png](spectrogram.png)

## Verdict

**PASS**
