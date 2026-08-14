#!/usr/bin/env python3
"""J. S. Bach, Fugue No. 2 in C minor, BWV 847 (WTC I) -- three-voice score data.

Pure data plus mechanical self-checks.  Nothing here knows anything about the
Commodore 64; a later step turns ``BARS`` into assembly tables.  Run this file
(``python3 bwv847.py``) to print the report and exit non-zero on any failure.

Sourcing
--------
The notes are Bach's and are public domain.  They were read off the engraved
score -- the Bach-Gesellschaft plate (B.W. XIV) and a modern engraving of the
same text -- and typed out here as original work for this demo.  No SID tune,
MIDI file, ABC transcription or published arrangement was used as a note
source.  The voice assignment, the register choices, and every decision about
what to do where Bach's texture is not exactly three voices are documented at
the bar concerned.

Grid
----
4/4, 31 bars, sixteenth-note grid: exactly 16 slots per bar per voice.
Voice 1 = soprano/top, 2 = alto/middle, 3 = bass.  An event is
``(pitch, sixteenths)``; ``"rest"`` is silence and ``"tie"`` continues the
previous event's pitch (the only way a note crosses a bar line here).

Structural map (bar numbers are 1-based, as in the score)
---------------------------------------------------------
    bars  1-9    EXPOSITION
          1-2      subject, ALTO, C minor        <- voice 2 first enters, bar 1 slot 2
          3-4      answer, SOPRANO, G minor      <- voice 1 first enters, bar 3 slot 2
                   tonal: the subject's 4th note (a 4th below the head) becomes
                   a 5th below in the answer; the alto adds countersubject 1
          5-6      codetta, two voices only
          7-8      subject, BASS, C minor        <- voice 3 first enters, bar 7 slot 2
          9        episode begins; the soprano quotes the head of the answer
                   (G5 F#5 G5 D5) and breaks off after five notes
    bars  9-10   EPISODE 1
    bars 11-12   MIDDLE ENTRY, soprano, E-flat major (relative major)
    bars 13-14   EPISODE 2 -- soprano in unbroken sixteenths over the two lower
                   voices in parallel eighths
    bars 15-16   MIDDLE ENTRY, alto, G minor (answer form, an octave below the
                   bar-3 answer)
    bars 17-19   EPISODE 3
    bars 20-21   MIDDLE ENTRY, soprano, C minor
    bars 22-28   EPISODE 4 -- the head of the subject is quoted twice (bar 22 in
                   C minor, bar 23 in B-flat) and abandoned both times
    bars 29-31   CODA over the tonic pedal.  The pedal enters on beat 3 of bar
                   29 and is held to the end.  The last complete subject entry
                   starts in the soprano on the second half of beat 3 of bar 29
                   (bar index 28, slot 10) and runs into bar 30.  The fugue ends
                   on a Picardy third (E natural in the soprano).

Countersubject 1, which accompanies most of the entries, is a scale that falls
a full octave in sixteenths and then resumes in eighths: bar 3 alto (C5 down to
C4, then Eb5 D5 C5), bar 7 soprano (F5 down to F4, then Ab5 G5 F5), bar 11 bass
(Ab3 down to Ab2, then C4 Bb3 Ab3), bar 15 soprano (C6 down to C5, then Eb5 D5
C5), bar 20 alto (F4 down to F3, then Ab4 G4 F4).  Where the scale ends far
below where the continuation resumes the voice leaps back up a tenth or more --
that leap is Bach's, not a transcription slip, and it is the same gesture every
time; at bar 15 the whole shape sits an octave higher, so there the leap is only
a third.

Reduction decisions (places where the score is not literally three voices)
--------------------------------------------------------------------------
* Bars 29-31, the pedal.  Bach writes the pedal C in octaves (C3 and C2 in the
  bass staff, one stem).  Voice 3 takes the upper octave, C3: it is the octave
  the preceding bass line arrives in (D3 C3 G3 G2 -> C3) and it keeps the pedal
  where a filter sweep has harmonics to work on.  The doubling C2 is dropped.
* Bar 30, slots 6-7 and 14-15.  Bach thickens to four parts: F4 + Ab4 + B natural4
  + D5 on the first, F4 + Ab4 + D5 on the second.  Voice 1 takes the top note
  and voice 2 the bottom note of the inner chord; Ab4 (and B natural4) are dropped.
* Bar 31.  The inner part is in double stops throughout: (B natural3 + D4),
  (B natural3 + D4), and the final (G3 + C4).  Voice 2 takes the lower note of
  each, which is also what completes the final chord: with voice 1 on E natural4
  and voice 3 on C3, the closing sonority is a full C major triad, C3-G3-E4.
  The dropped notes are D4, D4 and C4.
* Bars 12-14 the alto and the bass are both notated in the bass staff, and in
  bar 15 the alto's first note (G3) is still there; voice assignment follows the
  engraved stem directions, upper stems to voice 2 and lower stems to voice 3.
* Where a voice rests it is written out as ``("rest", n)``; voices 1 and 3 are
  silent for whole bars at the start (``[("rest", 16)]``) rather than being
  given invented filler.
"""

from __future__ import annotations

import itertools
import re
import sys

TEMPO_NOTE = (
    "quarter = 112.5 (a sixteenth is 8 frames at 60 Hz, so a bar is 128 frames "
    "= 2.133 s and the 31 bars run about 66 s)"
)
KEY_NOTE = (
    "C minor, three flats (Bb Eb Ab).  B natural is the leading note and is "
    "spelled B, not Cb; the answer in G minor brings F# and A natural; the "
    "close is a Picardy third (E natural)."
)

# Each bar is a dict of voice -> list of events.  An event is (pitch, sixteenths).
# pitch is scientific pitch notation with an explicit accidental where the note
# is not natural: "C5", "B4", "Eb4", "F#3", "Ab2".  Each note is spelled the way
# the score spells it (Eb not D#, Ab not G#).
#   "rest" = silence for that many sixteenths
#   "tie"  = the previous event's pitch continues for that many more sixteenths
BARS: list[dict[int, list[tuple[str, int]]]] = [
    # ---- bar 1: subject, alto (C minor) -- the first entry; voices 1 and 3 silent
    {
        1: [("rest", 16)],
        2: [("rest", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("G4", 2), ("Ab4", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("D5", 2)],
        3: [("rest", 16)],
    },
    # ---- bar 2: subject continues in the alto
    {
        1: [("rest", 16)],
        2: [("G4", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("D5", 2), ("F4", 1), ("G4", 1), ("Ab4", 4), ("G4", 1), ("F4", 1)],
        3: [("rest", 16)],
    },
    # ---- bar 3: answer, soprano (G minor, tonal); alto has countersubject 1
    # CS1: the alto falls a full octave C5-C4 in sixteenths and then leaps up to
    # Eb5 D5 C5.  The leap is in both engravings I read; it is Bach's, and the
    # same gesture returns at bars 7, 15 and 20.
    {
        1: [("rest", 2), ("G5", 1), ("F#5", 1), ("G5", 2), ("C5", 2), ("Eb5", 2), ("G5", 1), ("F#5", 1), ("G5", 2), ("A5", 2)],
        2: [("Eb4", 1), ("C5", 1), ("B4", 1), ("A4", 1), ("G4", 1), ("F4", 1), ("Eb4", 1), ("D4", 1), ("C4", 2), ("Eb5", 2), ("D5", 2), ("C5", 2)],
        3: [("rest", 16)],
    },
    # ---- bar 4: answer continues; alto has countersubject 2
    {
        1: [("D5", 2), ("G5", 1), ("F#5", 1), ("G5", 2), ("A5", 2), ("C5", 1), ("D5", 1), ("Eb5", 4), ("D5", 1), ("C5", 1)],
        2: [("Bb4", 2), ("A4", 2), ("Bb4", 2), ("C5", 2), ("F#4", 2), ("G4", 2), ("A4", 2), ("F#4", 2)],
        3: [("rest", 16)],
    },
    # ---- bar 5: codetta -- still only two voices
    {
        1: [("Bb4", 2), ("Eb5", 1), ("D5", 1), ("Eb5", 2), ("G4", 2), ("Ab4", 2), ("F5", 1), ("Eb5", 1), ("F5", 2), ("A4", 2)],
        2: [("G4", 4), ("rest", 1), ("C4", 1), ("D4", 1), ("Eb4", 1), ("F4", 1), ("G4", 1), ("Ab4", 2), ("tie", 1), ("D4", 1), ("Eb4", 1), ("F4", 1)],
        3: [("rest", 16)],
    },
    # ---- bar 6: codetta
    {
        1: [("Bb4", 2), ("G5", 1), ("F5", 1), ("G5", 2), ("B4", 2), ("C5", 2), ("D5", 1), ("Eb5", 1), ("F5", 4)],
        2: [("G4", 1), ("A4", 1), ("Bb4", 2), ("tie", 1), ("Eb4", 1), ("F4", 1), ("G4", 1), ("Ab4", 1), ("G4", 1), ("F4", 1), ("Eb4", 1), ("D4", 2), ("C5", 1), ("B4", 1)],
        3: [("rest", 16)],
    },
    # ---- bar 7: subject, bass (C minor); soprano has CS1, alto has CS2
    {
        1: [("tie", 2), ("Eb5", 1), ("D5", 1), ("C5", 1), ("Bb4", 1), ("Ab4", 1), ("G4", 1), ("F4", 2), ("Ab5", 2), ("G5", 2), ("F5", 2)],
        2: [("C5", 4), ("rest", 4), ("rest", 2), ("F5", 2), ("Eb5", 2), ("D5", 2)],
        3: [("rest", 2), ("C4", 1), ("B3", 1), ("C4", 2), ("G3", 2), ("Ab3", 2), ("C4", 1), ("B3", 1), ("C4", 2), ("D4", 2)],
    },
    # ---- bar 8: subject continues in the bass
    {
        1: [("Eb5", 2), ("D5", 2), ("Eb5", 2), ("F5", 2), ("B4", 2), ("C5", 2), ("D5", 2), ("B4", 2)],
        2: [("rest", 2), ("Ab4", 2), ("G4", 2), ("F4", 2), ("G4", 2), ("F4", 1), ("Eb4", 1), ("F4", 2), ("D4", 2)],
        3: [("G3", 2), ("C4", 1), ("B3", 1), ("C4", 2), ("D4", 2), ("F3", 1), ("G3", 1), ("Ab3", 4), ("G3", 1), ("F3", 1)],
    },
    # ---- bar 9: episode 1 begins; soprano quotes the head of the answer and breaks off
    # The soprano's G5 F#5 G5 D5 Eb5 is the head of the answer with the *real*
    # fourth note (D5, not the tonal C5); it stops after five notes, so it is not
    # listed in SUBJECT_ENTRIES.
    {
        1: [("C5", 2), ("G5", 1), ("F#5", 1), ("G5", 2), ("D5", 2), ("Eb5", 4), ("rest", 2), ("E5", 2)],
        2: [("G4", 4), ("rest", 2), ("B4", 2), ("C5", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("G4", 2)],
        3: [("Eb3", 1), ("C4", 1), ("B3", 1), ("A3", 1), ("G3", 1), ("F3", 1), ("Eb3", 1), ("D3", 1), ("C3", 1), ("D3", 1), ("Eb3", 1), ("D3", 1), ("C3", 1), ("Bb2", 1), ("Ab2", 1), ("G2", 1)],
    },
    # ---- bar 10: episode 1
    {
        1: [("F5", 2), ("F5", 1), ("E5", 1), ("F5", 2), ("C5", 2), ("D5", 4), ("rest", 2), ("D5", 2)],
        2: [("Ab4", 4), ("rest", 2), ("A4", 2), ("Bb4", 2), ("Bb4", 1), ("A4", 1), ("Bb4", 2), ("F4", 2)],
        3: [("F2", 1), ("Bb3", 1), ("Ab3", 1), ("G3", 1), ("F3", 1), ("Eb3", 1), ("D3", 1), ("C3", 1), ("Bb2", 1), ("C3", 1), ("D3", 1), ("C3", 1), ("Bb2", 1), ("Ab2", 1), ("G2", 1), ("F2", 1)],
    },
    # ---- bar 11: middle entry, soprano, E-flat major
    {
        1: [("Eb5", 2), ("Eb5", 1), ("D5", 1), ("Eb5", 2), ("Bb4", 2), ("C5", 2), ("Eb5", 1), ("D5", 1), ("Eb5", 2), ("F5", 2)],
        2: [("G4", 4), ("rest", 2), ("G4", 2), ("Ab4", 2), ("Ab4", 2), ("G4", 2), ("F4", 2)],
        3: [("Eb2", 1), ("Ab3", 1), ("G3", 1), ("F3", 1), ("Eb3", 1), ("Db3", 1), ("C3", 1), ("Bb2", 1), ("Ab2", 2), ("C4", 2), ("Bb3", 2), ("Ab3", 2)],
    },
    # ---- bar 12: middle entry continues; alto and bass are both notated in the bass staff
    {
        1: [("Bb4", 2), ("Eb5", 1), ("D5", 1), ("Eb5", 2), ("F5", 2), ("Ab4", 1), ("Bb4", 1), ("C5", 4), ("Bb4", 1), ("Ab4", 1)],
        2: [("rest", 2), ("Ab3", 2), ("Bb3", 2), ("C4", 2), ("rest", 2), ("Ab3", 1), ("G3", 1), ("Ab3", 2), ("F3", 2)],
        3: [("G3", 2), ("F3", 2), ("G3", 2), ("Ab3", 2), ("D3", 2), ("Eb3", 2), ("F3", 2), ("D3", 2)],
    },
    # ---- bar 13: episode 2 -- soprano in unbroken sixteenths, alto and bass in parallel eighths
    {
        1: [("G4", 1), ("Eb4", 1), ("F4", 1), ("G4", 1), ("Ab4", 1), ("Bb4", 1), ("C5", 1), ("D5", 1), ("Eb5", 1), ("D5", 1), ("C5", 1), ("D5", 1), ("Eb5", 1), ("F5", 1), ("G5", 1), ("A5", 1)],
        2: [("Bb3", 2), ("C4", 2), ("Bb3", 2), ("Ab3", 2), ("Bb3", 2), ("G3", 2), ("F3", 2), ("Eb3", 2)],
        3: [("Eb3", 2), ("Ab3", 2), ("G3", 2), ("F3", 2), ("G3", 2), ("Eb3", 2), ("D3", 2), ("C3", 2)],
    },
    # ---- bar 14: episode 2
    {
        1: [("Bb5", 1), ("F4", 1), ("G4", 1), ("Ab4", 1), ("Bb4", 1), ("C5", 1), ("D5", 1), ("E5", 1), ("F5", 1), ("Eb5", 1), ("D5", 1), ("Eb5", 1), ("F5", 1), ("G5", 1), ("A5", 1), ("B5", 1)],
        2: [("F3", 2), ("Db4", 2), ("C4", 2), ("Bb3", 2), ("C4", 2), ("Ab3", 2), ("G3", 2), ("F3", 2)],
        3: [("D3", 2), ("Bb3", 2), ("Ab3", 2), ("G3", 2), ("Ab3", 2), ("F3", 2), ("Eb3", 2), ("D3", 2)],
    },
    # ---- bar 15: middle entry, alto, G minor (answer form); soprano has CS1
    {
        1: [("C6", 2), ("B5", 1), ("A5", 1), ("G5", 1), ("F5", 1), ("Eb5", 1), ("D5", 1), ("C5", 2), ("Eb5", 2), ("D5", 2), ("C5", 2)],
        2: [("G3", 2), ("G4", 1), ("F#4", 1), ("G4", 2), ("C4", 2), ("Eb4", 2), ("G4", 1), ("F#4", 1), ("G4", 2), ("A4", 2)],
        3: [("Eb3", 2), ("rest", 2), ("rest", 4), ("rest", 2), ("C3", 2), ("Bb2", 2), ("A2", 2)],
    },
    # ---- bar 16: middle entry continues; soprano has CS2
    {
        1: [("Bb4", 2), ("A4", 2), ("Bb4", 2), ("C5", 2), ("F#4", 2), ("G4", 2), ("A4", 2), ("F#4", 2)],
        2: [("D4", 2), ("G4", 1), ("F#4", 1), ("G4", 2), ("A4", 2), ("C4", 1), ("D4", 1), ("Eb4", 4), ("D4", 1), ("C4", 1)],
        3: [("rest", 2), ("Eb3", 2), ("D3", 2), ("C3", 2), ("D3", 2), ("C3", 1), ("Bb2", 1), ("C3", 2), ("D3", 2)],
    },
    # ---- bar 17: episode 3
    {
        1: [("G4", 2), ("D5", 1), ("C5", 1), ("D5", 2), ("rest", 2), ("rest", 2), ("E5", 1), ("D5", 1), ("E5", 2), ("rest", 2)],
        2: [("Bb3", 2), ("rest", 2), ("rest", 1), ("D4", 1), ("E4", 1), ("F#4", 1), ("G4", 1), ("A4", 1), ("Bb4", 2), ("tie", 1), ("E4", 1), ("F4", 1), ("G4", 1)],
        3: [("G2", 2), ("Bb3", 1), ("A3", 1), ("Bb3", 2), ("D3", 2), ("Eb3", 2), ("C4", 1), ("Bb3", 1), ("C4", 2), ("E3", 2)],
    },
    # ---- bar 18: episode 3
    # UNSURE: the last eighth of the bar.  The treble staff carries a low G3 and
    # an eighth rest at the same point; the bass staff is already full (16), so
    # the G3 has to be voice 2 and the rest voice 1.  That leaves voice 2 leaping
    # Eb4 -> G3 to end the bar.  It is the only assignment that balances, but the
    # alternative (G3 in voice 3) would need a different bass reading.
    {
        1: [("rest", 2), ("F#5", 1), ("E5", 1), ("F#5", 2), ("rest", 2), ("rest", 2), ("G4", 1), ("F4", 1), ("G4", 2), ("rest", 2)],
        2: [("A4", 1), ("Bb4", 1), ("C5", 2), ("tie", 1), ("F#4", 1), ("G4", 1), ("A4", 1), ("Bb4", 2), ("Eb4", 1), ("D4", 1), ("Eb4", 2), ("G3", 2)],
        3: [("F3", 2), ("D4", 1), ("C4", 1), ("D4", 2), ("F#3", 2), ("G3", 4), ("rest", 1), ("G2", 1), ("A2", 1), ("B2", 1)],
    },
    # ---- bar 19: episode 3
    {
        1: [("rest", 2), ("A4", 1), ("G4", 1), ("A4", 2), ("rest", 2), ("rest", 2), ("B4", 1), ("A4", 1), ("B4", 2), ("rest", 2)],
        2: [("Ab3", 2), ("F4", 1), ("Eb4", 1), ("F4", 2), ("A3", 2), ("Bb3", 2), ("G4", 1), ("F4", 1), ("G4", 2), ("B3", 2)],
        3: [("C3", 1), ("D3", 1), ("Eb3", 2), ("tie", 1), ("A2", 1), ("Bb2", 1), ("C3", 1), ("D3", 1), ("Eb3", 1), ("F3", 2), ("tie", 1), ("B2", 1), ("C3", 1), ("D3", 1)],
    },
    # ---- bar 20: middle entry, soprano, C minor; alto has CS1 (F4 down to F3, then Ab4 G4 F4)
    {
        1: [("rest", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("G4", 2), ("Ab4", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("D5", 2)],
        2: [("C4", 1), ("F4", 1), ("Eb4", 1), ("D4", 1), ("C4", 1), ("Bb3", 1), ("Ab3", 1), ("G3", 1), ("F3", 2), ("Ab4", 2), ("G4", 2), ("F4", 2)],
        3: [("Eb3", 2), ("rest", 2), ("rest", 2), ("E3", 2), ("F3", 2), ("F2", 2), ("Eb2", 2), ("D2", 2)],
    },
    # ---- bar 21: middle entry continues
    {
        1: [("G4", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("D5", 2), ("F4", 1), ("G4", 1), ("Ab4", 4), ("G4", 1), ("F4", 1)],
        2: [("Eb4", 2), ("D4", 2), ("Eb4", 2), ("F4", 2), ("B3", 2), ("C4", 2), ("D4", 2), ("B3", 2)],
        3: [("rest", 2), ("Ab2", 2), ("G2", 2), ("F2", 2), ("G2", 2), ("F2", 1), ("Eb2", 1), ("F2", 2), ("G2", 2)],
    },
    # ---- bar 22: episode 4 -- soprano quotes the head of the subject in C minor and breaks off
    {
        1: [("Eb4", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("G4", 2), ("Ab4", 4), ("rest", 2), ("A4", 2)],
        2: [("C4", 4), ("rest", 2), ("E4", 2), ("F4", 2), ("F4", 1), ("E4", 1), ("F4", 2), ("C4", 2)],
        3: [("C3", 1), ("D3", 1), ("Eb3", 1), ("D3", 1), ("C3", 1), ("Bb2", 1), ("Ab2", 1), ("G2", 1), ("F2", 1), ("Bb3", 1), ("Ab3", 1), ("G3", 1), ("F3", 1), ("Eb3", 1), ("D3", 1), ("C3", 1)],
    },
    # ---- bar 23: episode 4 -- the head quoted again, on B-flat, and abandoned
    {
        1: [("Bb4", 2), ("Bb4", 1), ("A4", 1), ("Bb4", 2), ("F4", 2), ("G4", 4), ("rest", 2), ("G4", 2)],
        2: [("D4", 4), ("rest", 2), ("D4", 2), ("Eb4", 2), ("Eb4", 1), ("D4", 1), ("Eb4", 2), ("Bb3", 2)],
        3: [("Bb2", 1), ("C3", 1), ("D3", 1), ("C3", 1), ("Bb2", 1), ("Ab2", 1), ("G2", 1), ("F2", 1), ("Eb2", 1), ("Ab3", 1), ("G3", 1), ("F3", 1), ("Eb3", 1), ("D3", 1), ("C3", 1), ("Bb2", 1)],
    },
    # ---- bar 24: episode 4
    {
        1: [("tie", 2), ("Ab4", 1), ("Bb4", 1), ("C5", 1), ("B4", 1), ("C5", 1), ("Ab4", 1), ("F4", 8)],
        2: [("C4", 8), ("tie", 2), ("D4", 1), ("Eb4", 1), ("F4", 1), ("Eb4", 1), ("F4", 1), ("D4", 1)],
        3: [("Ab2", 1), ("Bb2", 1), ("C3", 1), ("Bb2", 1), ("Ab2", 1), ("G2", 1), ("F2", 1), ("Eb2", 1), ("D2", 1), ("G3", 1), ("F3", 1), ("Eb3", 1), ("D3", 1), ("C3", 1), ("B2", 1), ("A2", 1)],
    },
    # ---- bar 25: episode 4
    {
        1: [("tie", 2), ("D5", 1), ("C5", 1), ("D5", 2), ("F4", 2), ("Eb4", 2), ("Eb5", 1), ("D5", 1), ("Eb5", 2), ("G4", 2)],
        2: [("B3", 2), ("rest", 2), ("rest", 2), ("B3", 2), ("C4", 2), ("rest", 2), ("rest", 2), ("Eb4", 2)],
        3: [("G2", 4), ("rest", 4), ("rest", 1), ("G2", 1), ("A2", 1), ("B2", 1), ("C3", 1), ("D3", 1), ("Eb3", 1), ("F3", 1)],
    },
    # ---- bar 26: episode 4
    {
        1: [("F4", 2), ("F5", 1), ("Eb5", 1), ("F5", 2), ("Ab4", 2), ("G4", 1), ("F5", 1), ("Eb5", 1), ("D5", 1), ("C5", 1), ("B4", 1), ("A4", 1), ("G4", 1)],
        2: [("D4", 2), ("rest", 2), ("rest", 2), ("F4", 2), ("tie", 2), ("rest", 2), ("rest", 2), ("F4", 2)],
        3: [("G3", 1), ("F3", 1), ("Ab3", 1), ("G3", 1), ("F3", 1), ("Eb3", 1), ("D3", 1), ("C3", 1), ("B2", 2), ("C3", 1), ("B2", 1), ("C3", 2), ("G2", 2)],
    },
    # ---- bar 27: episode 4
    {
        1: [("C5", 2), ("F5", 2), ("Eb5", 2), ("D5", 2), ("rest", 2), ("Ab4", 2), ("G4", 2), ("F4", 2)],
        2: [("Eb4", 2), ("Ab4", 2), ("G4", 2), ("F4", 2), ("Eb4", 2), ("D4", 2), ("Eb4", 2), ("F4", 2)],
        3: [("Ab2", 2), ("C3", 1), ("B2", 1), ("C3", 2), ("D3", 2), ("G2", 2), ("C3", 1), ("B2", 1), ("C3", 2), ("D3", 2)],
    },
    # ---- bar 28: episode 4 -- approach to the pedal
    # All three voices rest together on slots 12-13.  That eighth of silence is
    # the only general pause in the piece apart from the opening rest, and it is
    # in the score -- it is not a hole in the transcription.
    {
        1: [("G4", 2), ("F4", 1), ("Eb4", 1), ("F4", 2), ("D4", 2), ("Ab4", 2), ("G4", 2), ("rest", 2), ("A4", 2)],
        2: [("B3", 2), ("C4", 2), ("D4", 2), ("B3", 2), ("B3", 2), ("C4", 2), ("rest", 2), ("C4", 2)],
        3: [("F2", 1), ("G2", 1), ("Ab2", 4), ("G2", 1), ("F2", 1), ("Eb2", 4), ("rest", 2), ("Eb3", 2)],
    },
    # ---- bar 29: CODA: tonic pedal enters on beat 3; final subject entry, soprano, from slot 10
    # The pedal is written in octaves, C3 over C2, as one half note tied onward.
    # Voice 3 takes C3 and the C2 doubling is dropped -- see the module docstring.
    # UNSURE: slots 0-9, where the two upper parts run in the same low octave and
    # meet in unison on C4 at slots 8-9.  The soprano's descent F4 Eb4 D4 C4 is
    # beamed above the staff and the alto's C4 quarter note is stemmed downward,
    # so the split below is what the engraving says; but the parts are close
    # enough here that I would want a second reading before betting on it.
    {
        1: [("B4", 2), ("C5", 2), ("F4", 1), ("Eb4", 1), ("D4", 1), ("C4", 1), ("C4", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("G4", 2)],
        2: [("F4", 1), ("D4", 1), ("Eb4", 1), ("C4", 1), ("tie", 2), ("B3", 2), ("C4", 4), ("rest", 2), ("E4", 2)],
        3: [("D3", 2), ("C3", 2), ("G3", 2), ("G2", 2), ("C3", 8)],
    },
    # ---- bar 30: coda over the pedal; the final subject entry finishes here
    # Four-part chords on slots 6-7 (F4 Ab4 B-natural4 D5) and 14-15 (F4 Ab4 D5).
    # Voice 1 takes the top, voice 2 the bottom; Ab4 and B-natural4 are dropped.
    {
        1: [("Ab4", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("D5", 2), ("G4", 2), ("C5", 1), ("B4", 1), ("C5", 2), ("D5", 2)],
        2: [("F4", 4), ("rest", 2), ("F4", 2), ("F4", 2), ("Eb4", 1), ("D4", 1), ("Eb4", 2), ("F4", 2)],
        3: [("tie", 16)],
    },
    # ---- bar 31: coda -- plagal colouring over the pedal, closing on a Picardy third
    # The inner part is in double stops: (B-natural3 D4), (B-natural3 D4), (G3 C4).
    # Voice 2 takes the lower note of each, so the final chord is C3-G3-E4, a full
    # C major triad with the Picardy third on top.  D4, D4 and C4 are dropped.
    {
        1: [("F4", 1), ("G4", 1), ("Ab4", 4), ("G4", 1), ("F4", 1), ("E4", 8)],
        2: [("B3", 2), ("rest", 2), ("B3", 2), ("rest", 2), ("G3", 8)],
        3: [("tie", 16)],
    },
]


# Every entry of the subject or the answer that is played out in full.
# (bar_index_0based, slot_0_15, voice, label)
SUBJECT_ENTRIES: list[tuple[int, int, int, str]] = [
    (0, 2, 2, "subject, alto (C minor)"),
    (2, 2, 1, "answer, soprano (G minor, tonal)"),
    (6, 2, 3, "subject, bass (C minor)"),
    (10, 2, 1, "subject, soprano (E-flat major) -- middle entry"),
    (14, 2, 2, "answer, alto (G minor, tonal) -- middle entry"),
    (19, 2, 1, "subject, soprano (C minor) -- middle entry"),
    (28, 10, 1, "subject, soprano (C minor) -- final entry, over the pedal"),
]

# The head of the subject is also quoted and abandoned at bar 9 (soprano, five
# notes of the answer), bar 22 (soprano, six notes) and bar 23 (soprano, on
# B-flat).  Those are not entries and are deliberately not listed above.

# Closing tonic pedal, as 0-based bar indices: bars 29-31 in the score's
# numbering.  It sounds from slot 8 of bar index 28 and is tied to the end.
PEDAL: tuple[int, int] = (28, 30)

# ---------------------------------------------------------------------------
# Self-checks
# ---------------------------------------------------------------------------

VOICES = (1, 2, 3)
SLOTS_PER_BAR = 16
FRAMES_PER_SIXTEENTH = 8
FRAMES_PER_SECOND = 60

PITCH_RE = re.compile(r"^([A-G])([#b]?)([0-9])$")
_LETTER_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACC_SEMITONE = {"": 0, "#": 1, "b": -1}

# The twelve pitch classes named the way C minor spells them.
PITCH_CLASS_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")

# Lowest and highest note we are willing to believe (roughly C2..C6).
RANGE_LOW = 36   # C2
RANGE_HIGH = 84  # C6

# Interval indices that a subject entry is *allowed* to differ from the first
# entry at, keyed by the entry's index in SUBJECT_ENTRIES.  Each one is a
# deliberate adjustment, not a transcription slip.
INTERVAL_EXEMPTIONS: dict[int, dict[int, str]] = {
    # Tonal answer.  The subject's fourth note drops a perfect fourth from the
    # head (C5 -> G4); in the answer it drops a perfect fifth instead (G5 -> C5)
    # so that the answer stays inside the key.  That changes interval 2 (the
    # descent, -5 becomes -7) and interval 3 (the step back up out of it, +1
    # becomes +3).  Nothing else in the answer moves.
    1: {2: "tonal answer: descent to the 4th note is a 5th, not a 4th",
        3: "tonal answer: recovery from that note is correspondingly wider"},
    4: {2: "tonal answer: descent to the 4th note is a 5th, not a 4th",
        3: "tonal answer: recovery from that note is correspondingly wider"},
    # Middle entry in E-flat major.  The subject's fifth note is the flat sixth
    # of the minor key (Ab in C minor).  In the major-mode entry that note is
    # the natural sixth (C in E-flat major), a semitone higher, which widens
    # interval 3 by one and narrows interval 4 by one.  The entry is otherwise
    # a literal transposition.
    3: {3: "major-mode entry: the flat 6th of the subject becomes a natural 6th",
        4: "major-mode entry: the step out of that note is correspondingly smaller"},
}


def parse_pitch(name: str) -> int:
    """Return the MIDI number of a scientific-pitch-notation name."""
    m = PITCH_RE.match(name)
    if m is None:
        raise ValueError(f"unparseable pitch {name!r}")
    letter, acc, octave = m.group(1), m.group(2), int(m.group(3))
    return (octave + 1) * 12 + _LETTER_SEMITONE[letter] + _ACC_SEMITONE[acc]


def voice_slots(voice: int) -> list[str | None]:
    """Flatten a voice to one entry per sixteenth over the whole piece.

    Each slot holds the pitch name of an *attack*, or None for a slot that is a
    rest, a hold, or a tie continuation.
    """
    out: list[str | None] = []
    for bar in BARS:
        for pitch, dur in bar[voice]:
            out.append(None if pitch in ("rest", "tie") else pitch)
            out.extend([None] * (dur - 1))
    return out


def entry_intervals(bar_index: int, slot: int, voice: int, length: int = 16) -> list[int]:
    """Semitone intervals between successive attacks in `length` sixteenths."""
    flat = voice_slots(voice)
    start = bar_index * SLOTS_PER_BAR + slot
    window = flat[start:start + length]
    attacks = [parse_pitch(p) for p in window if p is not None]
    return [b - a for a, b in itertools.pairwise(attacks)]


def check_structure(fail: list[str]) -> None:
    if len(BARS) != 31:
        fail.append(f"bar count is {len(BARS)}, expected 31")
    for i, bar in enumerate(BARS):
        if set(bar) != set(VOICES):
            fail.append(f"bar {i + 1}: voices are {sorted(bar)}, expected [1, 2, 3]")


def check_durations(fail: list[str]) -> None:
    for i, bar in enumerate(BARS):
        for v in VOICES:
            total = sum(d for _, d in bar.get(v, []))
            if total != SLOTS_PER_BAR:
                fail.append(f"bar {i + 1} voice {v}: {total} sixteenths, expected 16")
            for pitch, d in bar.get(v, []):
                if d <= 0:
                    fail.append(f"bar {i + 1} voice {v}: non-positive duration on {pitch!r}")


def check_ties(fail: list[str]) -> None:
    for v in VOICES:
        previous = "rest"  # nothing has sounded before bar 0
        for i, bar in enumerate(BARS):
            for j, (pitch, _d) in enumerate(bar[v]):
                if pitch == "tie":
                    if i == 0 and j == 0:
                        fail.append(f"bar 1 voice {v}: starts with a tie")
                    elif previous in ("rest", None):
                        fail.append(
                            f"bar {i + 1} voice {v} event {j}: tie follows a rest"
                        )
                if pitch != "tie":
                    previous = pitch


def check_pitches(fail: list[str]) -> dict[int, tuple[str, str]]:
    ranges: dict[int, tuple[str, str]] = {}
    for v in VOICES:
        lo = hi = None
        for i, bar in enumerate(BARS):
            for pitch, _d in bar[v]:
                if pitch in ("rest", "tie"):
                    continue
                try:
                    midi = parse_pitch(pitch)
                except ValueError as exc:
                    fail.append(f"bar {i + 1} voice {v}: {exc}")
                    continue
                if not RANGE_LOW <= midi <= RANGE_HIGH:
                    fail.append(
                        f"bar {i + 1} voice {v}: {pitch} is outside C2..C6"
                    )
                if lo is None or midi < lo[0]:
                    lo = (midi, pitch)
                if hi is None or midi > hi[0]:
                    hi = (midi, pitch)
        ranges[v] = (lo[1] if lo else "-", hi[1] if hi else "-")
    return ranges


def check_entries(fail: list[str], report: list[str]) -> None:
    if not SUBJECT_ENTRIES:
        fail.append("SUBJECT_ENTRIES is empty")
        return
    seqs = [entry_intervals(b, s, v) for (b, s, v, _l) in SUBJECT_ENTRIES]
    reference = seqs[0]
    width = max(len(label) for (_b, _s, _v, label) in SUBJECT_ENTRIES)
    report.append("  subject entries, interval sequences (semitones between attacks):")
    for (b, s, v, label), seq in zip(SUBJECT_ENTRIES, seqs, strict=True):
        marks = []
        for k, iv in enumerate(seq):
            ref = reference[k] if k < len(reference) else None
            if ref is None or iv != ref:
                marks.append(f"{iv:+d}*")
            else:
                marks.append(f"{iv:+d} ")
        report.append(
            f"    bar {b + 1:>2} slot {s:>2} v{v}  {label:<{width}}  "
            + " ".join(marks)
        )
    for idx, ((b, s, v, label), seq) in enumerate(zip(SUBJECT_ENTRIES, seqs, strict=True)):
        if idx == 0:
            continue
        allowed = INTERVAL_EXEMPTIONS.get(idx, {})
        if len(seq) != len(reference):
            fail.append(
                f"entry {idx} (bar {b + 1} v{v}) has {len(seq)} intervals, "
                f"reference has {len(reference)}"
            )
            continue
        for k, (iv, ref) in enumerate(zip(seq, reference, strict=True)):
            if iv == ref:
                continue
            if k in allowed:
                report.append(
                    f"    ...bar {b + 1} v{v} interval {k}: {iv:+d} vs {ref:+d} "
                    f"-- allowed ({allowed[k]})"
                )
            else:
                fail.append(
                    f"entry {idx} (bar {b + 1} slot {s} v{v}, {label}): interval "
                    f"{k} is {iv:+d}, reference is {ref:+d}, not exempted"
                )


def pitch_class_histogram() -> list[tuple[str, int]]:
    counts = dict.fromkeys(PITCH_CLASS_NAMES, 0)
    for bar in BARS:
        for v in VOICES:
            for pitch, _d in bar[v]:
                if pitch in ("rest", "tie"):
                    continue
                counts[PITCH_CLASS_NAMES[parse_pitch(pitch) % 12]] += 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], PITCH_CLASS_NAMES.index(kv[0])))


def attacks_per_voice() -> dict[int, int]:
    return {
        v: sum(
            1
            for bar in BARS
            for pitch, _d in bar[v]
            if pitch not in ("rest", "tie")
        )
        for v in VOICES
    }


def main() -> int:
    fail: list[str] = []
    report: list[str] = []

    report.append(f"BWV 847 fugue -- {KEY_NOTE}")
    report.append(f"tempo: {TEMPO_NOTE}")
    report.append("")

    check_structure(fail)
    check_durations(fail)
    check_ties(fail)
    ranges = check_pitches(fail)

    report.append(f"bars: {len(BARS)}")
    report.append("per-voice range and attack count:")
    names = {1: "soprano", 2: "alto", 3: "bass"}
    counts = attacks_per_voice()
    for v in VOICES:
        lo, hi = ranges[v]
        report.append(
            f"  voice {v} ({names[v]:<7}): {lo:>4} .. {hi:<4}   {counts[v]:>3} attacks"
        )
    report.append("")

    check_entries(fail, report)
    report.append("")

    report.append("  pitch-class histogram (attacks, all voices, descending):")
    report.append("  | pitch class | attacks |")
    report.append("  |-------------|---------|")
    for name, n in pitch_class_histogram():
        report.append(f"  | {name:<11} | {n:>7} |")
    report.append("")

    total = sum(d for bar in BARS for pitch, d in bar[1])
    expected = len(BARS) * SLOTS_PER_BAR
    if total != expected:
        fail.append(f"total sixteenths {total}, expected {expected}")
    seconds = total * FRAMES_PER_SIXTEENTH / FRAMES_PER_SECOND
    report.append(
        f"total: {total} sixteenths (expected {expected}); "
        f"{total * FRAMES_PER_SIXTEENTH} frames at {FRAMES_PER_SIXTEENTH} frames per "
        f"sixteenth = {seconds:.2f} s at {FRAMES_PER_SECOND} Hz"
    )
    report.append("")

    print("\n".join(report))
    if fail:
        print(f"FAILURES ({len(fail)}):")
        for f in fail:
            print(f"  - {f}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
