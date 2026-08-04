# Fugue No. 2 in C Minor

J. S. Bach's Fugue No. 2 in C minor, BWV 847, from *The Well-Tempered
Clavier* Book I — played on the SID while the notated score scrolls across
the screen in time with it.

The piece is chosen for the hardware rather than in spite of it. BWV 847 is
a **three-voice fugue** and the SID has exactly three voices, so nothing has
to be dropped or merged to make it fit: the subject goes to voice 1 as a
pulse wave with pulse-width modulation, the countersubject to voice 2 as a
sawtooth, and the bass to voice 3 as a triangle through the resonant filter.
The fugue's perpetual-motion sixteenths are the material that rewards the
SID's crisp attack, and the pedal point near the end is where the filter
sweep earns its place.

The screen is text mode with a custom character set: white staves on black,
scrolling right to left so notes travel toward a fixed "now" column. Each of
the twelve pitch classes carries its own bright color, repeating every
octave, so a given note name always looks the same whatever register it is
in; sharps and flats are drawn beside the heads they modify. A sprite sits
*behind* the sounding note with the sprite/character priority bit set, so the
note reads as backlit rather than covered.

**What a passing run shows.** The three voice entries of the exposition
individually audible as each enters; the score on screen advancing smoothly,
with the scroll offset sampled across frames to prove the fine scroll and
column wrap are clean; the sprite's coordinates matching the cell of the note
the sequencer says is sounding, read at the same stop; accidentals present
wherever the pitch departs from the staff position; and audio evidence
captured against a reference score written from the arrangement's own note
data, with the report passing.

The cross-check unique to this demo is that the picture and the sound come
from one source. The piano roll from the audio capture and the notes on the
scrolling staff are two renderings of the same note data, so they must tell
the same story — and where they disagree, one of the two paths is wrong.

Beyond this README, `PROMPT.md` is what this directory holds until the demo
is built; the sources, plan, audit, evidence, and the packaged `.d64` land
here as the run produces them.
