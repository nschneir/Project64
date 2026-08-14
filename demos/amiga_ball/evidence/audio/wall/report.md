# SID audio verification

## Transcription

### Voice 1

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 13 | rest | - | triangle | 0 |
| 13 | 20 | E3 | +0.2 | triangle | 20 |
| 33 | 57 | rest | - | triangle | 0 |

### Voice 2

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 13 | rest | - | noise | 0 |
| 13 | 20 | F#4 | - | noise | 20 |
| 33 | 57 | rest | - | noise | 0 |

### Voice 3

| Start frame | Frames | Note | Cents off | Waveform | Gated frames |
|---|---|---|---|---|---|
| 0 | 90 | rest | - | none | 0 |

## Score diff

No differences against the reference score — an empty diff list is also what a run with no reference score produces.

## Anomalies

None found.

## WAV metrics

| Metric | Value |
|---|---|
| Duration | 1.75 s |
| Clipped samples | 0 |
| Silence windows | 0.70-1.75 s |
| RMS min / median / max | -68.5 / -67.9 / -26.0 dBFS over 18 windows of 0.1 s |

## Artifacts

- [capture.wav](capture.wav)
- [sid-log.jsonl](sid-log.jsonl)
- [piano-roll.png](piano-roll.png)
- [spectrogram.png](spectrogram.png)

## Verdict

**PASS**
