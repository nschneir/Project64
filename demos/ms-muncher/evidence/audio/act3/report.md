# SID audio verification

## Transcription

### Voice 1

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 14 | rest | - | none | 0 |
| 14 | 32 | C5 | +0.1 | pulse | 32 |
| 46 | 32 | E5 | -0.1 | pulse | 32 |
| 78 | 64 | G5 | -0.1 | pulse | 64 |
| 142 | 32 | F5 | +0.0 | pulse | 32 |
| 174 | 31 | E5 | -0.1 | pulse | 31 |
| 205 | 155 | rest | - | none | 0 |

### Voice 2

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 14 | rest | - | none | 0 |
| 14 | 64 | E4 | -0.1 | sawtooth | 64 |
| 78 | 64 | C4 | +0.1 | sawtooth | 64 |
| 142 | 63 | F4 | +0.0 | sawtooth | 63 |
| 205 | 155 | rest | - | none | 0 |

### Voice 3

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 14 | rest | - | none | 0 |
| 14 | 128 | C3 | +0.1 | triangle | 128 |
| 142 | 64 | F3 | -0.3 | triangle | 64 |
| 206 | 154 | rest | - | none | 0 |

## Score diff

No differences against the reference score — an empty diff list is also what a run with no reference score produces.

## Anomalies

None found.

## WAV metrics

| Metric | Value |
|---|---|
| Duration | 6.12 s |
| Clipped samples | 0 |
| Silence windows | 3.70-6.12 s |
| RMS min / median / max | -120.0 / -21.7 / -20.2 dBFS over 62 windows of 0.1 s |

## Artifacts

- [capture.wav](capture.wav)
- [sid-log.jsonl](sid-log.jsonl)
- [piano-roll.png](piano-roll.png)
- [spectrogram.png](spectrogram.png)

## Verdict

**PASS**
