; sections.s — the section table.  One row per section; the section index is
; the only thing that couples the music to the picture.
;
; SPEC.md sections 3.1 and 6.4 are the source of these numbers.

        .segment "RODATA"

NSEC    = 6                     ; 0 hymn, 1 marseillaise, 2 battle,
                                ; 3 cannon, 4 finale, 5 hold

; ---- frame budgets (SPEC.md 6.4) ----------------------------------------
; 60 Hz.  2400 + 1500 + 2100 + 1800 + 2400 = 10200 frames = 170 s = 2:50.
; Section 5 is the hold; its budget is never reached.

secframel:
        .byte   <2400, <1500, <2100, <1800, <2400, <$FFFF
secframeh:
        .byte   >2400, >1500, >2100, >1800, >2400, >$FFFF

; ---- palettes (SPEC.md 3.1) ---------------------------------------------
; Two bytes per section: the screen-RAM byte (c01 << 4 | c10) and the
; colour-RAM byte (c11).  Bit-pair 00 is always $D021 = black.
;
;   0 hymn         11 dark grey  / 12 medium grey / 15 light grey
;   1 marseillaise  6 blue       /  2 red         /  1 white
;   2 battle        2 red        /  8 orange      /  7 yellow
;   3 cannon        9 brown      /  8 orange      /  1 white
;   4 finale        6 blue       /  7 yellow      /  1 white
;   5 hold          — the finale's palette, held
;
; The finale was 7 yellow / 13 light green / 1 white and it did not work: all
; three are bright, so overlapping shapes dissolved into each other and the
; dithers stopped reading as translucency.  Compare the Marseillaise, whose
; blue/red/white is the best-looking section precisely because it spends the
; luminance ladder the prompt asks for.  Blue/gold/white gives the finale the
; same separation, and stays distinct from the battle's reds and the cannon's
; browns so the picture still reads as strata.

secpal: .byte   $bc, $0f
        .byte   $62, $01
        .byte   $28, $07
        .byte   $98, $01
        .byte   $67, $01
        .byte   $67, $01

; ---- shape vocabulary per section ---------------------------------------
; A 16-bit mask of allowed sh_type values.  Bit n = type n:
;   0 triangle  1 rectangle  2 pentagon  3 hexagon  4 star5
;   5 circle    6 oval       7 ellipse   8 star4    9 cross
;
;   0 hymn         round and calm:      circle, oval, ellipse, hexagon
;   1 marseillaise flat and heraldic:   triangle, rectangle, pentagon
;   2 battle       small and jagged:    triangle, star5, star4, cross
;   3 cannon       everything
;   4 finale       bright and pointed:  pentagon, star5, circle, star4
;   5 hold         nothing spawns, but keep a legal mask

secshapel:
        .byte   <%0000000011101000, <%0000000000000111, <%0000000100010001
        .byte   <%0000001111111111, <%0000000100110100, <%0000000000000001
secshapeh:
        .byte   >%0000000011101000, >%0000000000000111, >%0000000100010001
        .byte   >%0000001111111111, >%0000000100110100, >%0000000000000001

; ---- size range, radius in SCREEN pixels --------------------------------
; pickshape draws size = lo + rndlt(hi - lo + 1).

secsizelo:
        .byte   50, 30,  8, 40, 12,  8
secsizehi:
        .byte   90, 60, 28, 90, 40,  8

; ---- which voices' note onsets spawn a shape ----------------------------
; Bit 0 = voice 1, bit 1 = voice 2, bit 2 = voice 3.
;
;   0 hymn         voice 1 only  — few, large, slow
;   1 marseillaise voices 1+2
;   2 battle       voices 2+3    — the stabs and the bass hits
;   3 cannon       voice 1; the shots throw their own bursts
;   4 finale       all three     — fill the remaining black
;   5 hold         none
;
; The battle listens to voices 2 and 3 and NOT to voice 1.  Voice 1 there is
; a running sixteenth-note figure — 350 onsets in the section's 2100 frames,
; one every six.  Spawning on it asked for 612 shapes in 35 seconds against a
; measured cost of about four frames each, and 52 of them were dropped
; (measured, after three rounds of optimisation had already taken the shape
; cost down by more than half).  The running figure is texture; the stabs and
; the bass hits are the accents, and accents are what a shape should mark.
; This is a policy choice, not a capitulation: it is why `dropped` reads 0.

secspawn:
        .byte   %001, %011, %110, %001, %111, %000

; ---- instruments: 5 bytes per voice, 3 voices per section ---------------
; waveform (control byte with the gate bit CLEAR), attack/decay,
; sustain/release, pulse width low, pulse width high.
; Nybbles are from references/hardware.md's envelope-rate and instrument
; tables.  Waveform bits: $10 triangle, $20 sawtooth, $40 pulse, $80 noise;
; $04 ring mod (triangle against the previous voice's oscillator).

; THE TEXTURE ARC (SPEC.md 6.4) is what these rows spell: the piece opens on
; ONE instrument and gains them — 1, 2, 3, 2 + artillery, 3, 0 — so the
; finale's full texture is arrived at rather than merely present.  Sections
; 2, 3 and 4 are unchanged; the arc is carried entirely by the six rows below.
;
; A PIANO IS AN ENVELOPE, NOT A WAVEFORM.  Attack 0 (2 ms) and SUSTAIN 0 are
; the whole of it: a struck string has an instantaneous onset and then only
; decays, and a non-zero sustain nybble is the single thing that makes a SID
; voice read as an organ.  That is why the old hymn was thin — three pads at
; sustain 10, 9 and 10 with 68/68/38 ms attacks, which is an organ chord and
; not an orchestra.  The sustain nybble of every piano row here reads 0, and
; music.s explains why the hymn's NOTES had to be re-voiced to match.
;
; Only the decay nybble moves between piano rows, and it tracks the tempo:
; $A (1.5 s) at the hymn's quarter = 60 frames, 8 (300 ms) for the march's
; chords at quarter = 32.  The bass hand gets 9 (750 ms) — one step longer,
; because low notes sound weaker than high ones on the 6581 and the usual
; remedy, raising the sustain level, is the one thing these rows may not do.
; Release is 2 (48 ms) rather than hardware.md's 0 (6 ms): voicetick releases
; a note three frames before its event ends, so 48 ms lands the damper fall
; exactly inside the gap the sequencer already leaves, where 6 ms would chop a
; still-audible decay and click.
;
; No piano voice is filtered, and that is not a preference: $D415 has no
; writer anywhere and $D416 is written only by cantick during a cannon shot,
; so the cutoff is 0 for the whole of sections 0-2.  A voice routed through a
; filter parked at the bottom of its range is subtracted, not shaped.  The
; same fact is why the reed below drops the trumpet's band-pass.

secinstr:
        ; --- 0 hymn: a solo piano, two hands, one instrument ---
        .byte   $40, $0a, $02, $00, $08   ; v1 piano PW $0800, right hand
        .byte   $40, $0a, $02, $00, $08   ; v2 the left hand — an IDENTICAL
                                          ; row, so the two fuse into one
                                          ; instrument rather than reading as
                                          ; two.  Only secpw parts them.
        .byte   $10, $00, $00, $00, $00   ; v3 silent — see s0v3.  Triangle
                                          ; because that is the convention
                                          ; section 5's silent rows use.
        ; --- 1 marseillaise: a reed arrives over the piano ---
        .byte   $20, $18, $a2, $00, $00   ; v1 sawtooth reed, the anthem.
                                          ; Attack 1 (8 ms), not the trumpet
                                          ; row's 6 (68 ms = four frames):
                                          ; the anacrusis is 16-frame notes
                                          ; and a four-frame attack blunts it.
                                          ; Sustain 10 — a wind holds its
                                          ; level, and that is exactly the
                                          ; contrast that makes the piano
                                          ; beside it read as percussive.
                                          ; PW is 0 because a sawtooth has no
                                          ; pulse width.  The trumpet row's
                                          ; band-pass is dropped: the WHY is
                                          ; with secres/secvol, which is the
                                          ; table that would route it.
        .byte   $40, $08, $02, $00, $08   ; v2 piano, chords
        .byte   $40, $09, $02, $00, $08   ; v3 piano, bass hand
        ; --- 2 battle: running figures, stabs, driving bass ---
        .byte   $20, $06, $81, $00, $00   ; v1 sawtooth, band-passed
        .byte   $40, $05, $71, $00, $01   ; v2 narrow pulse stabs
        .byte   $20, $07, $91, $00, $00   ; v3 octave bass
        ; --- 3 cannon: the hymn returns over artillery ---
        .byte   $10, $69, $a4, $00, $08   ; v1 triangle, wide-spaced
        .byte   $20, $58, $a3, $00, $00   ; v2 sustained chords
        .byte   $80, $0a, $08, $00, $00   ; v3 noise — cannonfire overrides
        ; --- 4 finale: the hymn in triumph over bells ---
        .byte   $40, $18, $a3, $00, $06   ; v1 pulse, swept PW
        .byte   $20, $28, $93, $00, $00   ; v2 countermelody
        .byte   $14, $0a, $00, $00, $00   ; v3 ring-modulated triangle: bells
        ; --- 5 hold: silence ---
        .byte   $10, $00, $00, $00, $00
        .byte   $10, $00, $00, $00, $00
        .byte   $10, $00, $00, $00, $00

; ---- filter setup per section -------------------------------------------
; $D417 (resonance + routing) and $D418 (mode + volume).  The cannon rewrites
; both while a shot is sounding.
;
; WHY SECTION 1's REED IS NOT BAND-PASSED — the deliberate omission, recorded
; at the table that enforces it.  references/hardware.md's Trumpet row pairs a
; sawtooth with a band-pass, and secinstr's reed takes everything else from
; that row; routing it would mean a non-zero secres[1] here.  It is dropped on
; purpose, because the cutoff word is 0 for the whole of sections 0-2: $D415
; has no writer anywhere in the program, and $D416 is written only by cantick
; during a cannon shot.  A voice routed through a filter parked at the bottom
; of its range is subtracted, not shaped, so secres[1] stays $00 and the reed
; is sold by its envelope alone.  The same fact is why no piano voice in
; sections 0 and 1 is filtered either.

secres: .byte   $00, $00, $f1, $f4, $00, $00   ; battle routes v1, cannon routes v3
secvol: .byte   $0f, $0f, $2f, $1f, $0f, $00   ; battle band-pass, cannon low-pass

; ---- pulse-width sweep ---------------------------------------------------
; The base $D403 value for voice 1's swept pulse; 0 disables the sweep.
; Only the sections whose voice 1 is a pulse waveform use it.
;
; Both of the first two entries moved with the arc, because both sections'
; voice-1 waveform changed:
;   [0] $00 -> $08  the hymn's voice 1 is now a pulse piano, and $08 centres
;                   the sweep on its own PW $0800 — the same relation
;                   [1] used to have to secinstr's PW hi, and [4] still does.
;                   pwtick's period is 128 frames against notes of 60-120, so
;                   the width really does move WITHIN a note at this tempo.
;   [1] $04 -> $00  the Marseillaise's voice 1 is now a sawtooth reed, which
;                   has no pulse width.  Leaving $04 would have pwtick writing
;                   $D403 every frame for a voice that ignores it, which is
;                   exactly what this table's comment says it does not do.
;
; pwtick writes $D403 and nothing else, so pulse-width motion is available to
; VOICE 1 ONLY: the hymn's right hand has it and its left hand does not.  That
; asymmetry is wanted — two hands of one piano are never spectrally identical,
; and the envelope, which is bit-identical across both, is what names the
; instrument.  If a capture ever shows the hands separating into two
; instruments instead of fusing, [0] back to $00 undoes it and nothing else
; has to move.

secpw:  .byte   $08, $00, $00, $00, $06, $00
