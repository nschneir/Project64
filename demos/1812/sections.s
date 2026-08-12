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
; a running sixteenth-note figure of duration-6 events — 7 real ticks each,
; so 300 onsets in the section's 2100 frames, one every seven.  Spawning on
; it asked for 612 shapes in 35 seconds against a measured cost of about
; four frames each, and 52 of them were dropped (measured, after three
; rounds of optimisation had already taken the shape cost down by more than
; half).  The running figure is texture; the stabs and the bass hits are the
; accents, and accents are what a shape should mark.  This is a policy
; choice, not a capitulation: it is why `dropped` reads 0.

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
; Nothing in either section is routed through the filter — not the pianos, and
; not the reed, which drops the trumpet row's band-pass.  That is a carve-out
; rather than an oversight, and its WHY is recorded once, with the filter
; tables below: that is where the routing would have to be done, and since
; seccut the reason is a judgement about these instruments rather than a fact
; about the chip.

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
                                          ; Decay 8 (300 ms), not the trumpet
                                          ; row's 0 (6 ms).  Sustain is a
                                          ; LEVEL and not a time, so with
                                          ; sustain 10 the envelope floors at
                                          ; the held level and this decay
                                          ; cannot end a note early the way a
                                          ; sustain-0 row's does.  And the
                                          ; 300 ms is the rate column's
                                          ; full-scale time — decay and
                                          ; release share that column — so
                                          ; the fall from peak to 10 of 15
                                          ; costs a third of it, well inside
                                          ; even the 13 frames an s1v1
                                          ; 16-duration event stays gated.
                                          ; EVERY note here reaches the held
                                          ; level, the short ones included;
                                          ; what 8 buys over 6 ms is an
                                          ; audible fall into that level
                                          ; rather than a snap to it.
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
; $D416 (cutoff high), $D417 (resonance + routing) and $D418 (mode + volume),
; all three written by loadinstr — at seqreset, and at every section change
; EXCEPT 4->5.  That boundary takes a different path and is not an oversight
; in this comment: nextsec branches to `silence` and returns before nsplay
; (music.s:224-228), so loadinstr never runs for section 5 and this table's
; [5] entries are never loaded at all.  What runs instead gates all three
; voices off and zeroes $D418 — more thorough than a table load, not less —
; but it does mean the hold inherits the finale's cutoff and routing, both of
; which are already inert.
;
; A cannon shot rewrites all three as well, but by TWO routines on two
; schedules, and collapsing them into "the cannon" is a conflation this file
; has already had to correct once: cannonfire writes $D417 and $D418 once, at
; the shot (music.s:424-429), while cantick writes $D416 once a frame for the
; 24 frames after it (music.s:455-469).
;
; THE CUTOFF HAS TO BE A REAL VALUE, AND FOR THE WHOLE LIFE OF THIS DEMO IT
; WAS NOT.  A filter does nothing until secres routes a voice into it, and
; nothing USEFUL until the cutoff sits where that voice's harmonics are.  The
; battle has always routed voice 1 through a band-pass — secres[2] = $f1,
; secvol[2] = $2f — but before this table existed nothing ever wrote the
; cutoff pair ahead of section 3, so the battle band-passed at sndinit's
; zero.  references/hardware.md:253 puts the 11-bit $D415/$D416 pair at
; about 30 Hz to 12 kHz, so a word of 0 is the bottom of the range: the
; band-pass was SUBTRACTING voice 1, not shaping it.  seccut is the fix.
;
; seccut[2] = $19, and here is where that number comes from.  $D415 stays 0
; (below), so the word is 8 * $19 = 200 of 2047.  hardware.md:253 gives that
; pair's ENDPOINTS — about 30 Hz to 12 kHz — and no curve between them, so any
; frequency put on 200 is interpolated, and interpolating LINEARLY is an
; assumption of this comment rather than something the reference licenses:
; 30 + (12000-30)*200/2047 = about 1.2 kHz.  Read that as a label for the byte,
; not as a measurement of it — the NOMINAL paragraph below says what was
; actually measured, and it does not agree.
;
; s2v1's running figure spans D#4 to E5 — 311 to 659 Hz — so 1.2 kHz sits
; ABOVE every fundamental in it and BELOW the fifth harmonic of every note in
; it: in the harmonically dense part of a sawtooth's spectrum in every case,
; though not at the same harmonic in every case — near the fourth of the
; lowest notes, between the first and second of the highest.  It is NOT inside
; the second-to-fourth harmonic band of all of them, and no byte could be:
; those [2f, 4f] windows intersect only across a pitch ratio of 2 or less and
; this figure spans 2.12, so D#5 and E5 — three of its 32 events — sit above
; where a cutoff satisfying the rest can reach.  That is a property of the
; figure's range and not of this value.  With secres[2]'s resonance nybble $F
; the result is a fixed formant the figure runs under, which is what a
; band-pass on an ostinato is for; it also leaves the bottom of the mix to
; voice 3's octave bass, which is not routed.  Centring the band ON the
; fundamentals was the alternative and is rejected: passing the fundamental
; and rejecting the harmonics turns a sawtooth into a sine and takes the
; battle's bite away.
;
; That 1.2 kHz is a NOMINAL twice over — once for the interpolation and once
; for the chip — and hardware.md:360-361 is the reason to say so out loud
; rather than quote it as a fact.  x64sc emulates a reSID MOS6581 here (VICE
; says so in its own log), and a three-second capture inside the battle,
; against the identical capture taken before seccut existed, gained +4.5 dB in
; the 1.0-1.6 kHz band and +7.5 dB in 1.6-2.5 kHz — so the real resonant peak
; sits somewhat ABOVE 1.2 kHz.  Two things could put it there and one capture
; cannot separate them: the linear interpolation being wrong about where 200
; lands, and the 6581's analog curve varying as the caveat warns.  The first
; is the likelier.  Neither moves the choice, because the choice is argued in
; harmonics and not in hertz: the band is still above every fundamental and
; still below the fifth harmonic of every note.  Another chip would place it
; differently again, which is the whole reason for arguing it that way.
; (The same capture pair: whole mix +1.5 dB, no clipped samples, so the voice
; came back without costing the headroom.)
;
; seccut[3] = $10 is cantick's own floor (its ctfloor value), so section 3
; starts where the sweep ends rather than wherever the previous section left
; the register.  Shot 1 fires on section 3's first tick and overwrites it
; with $F5 the same frame, so this is a defined restore point rather than an
; audible value — but "defined" is the point: before seccut nothing restored
; $D416 at all.
;
; $D415 GETS NO TABLE, DELIBERATELY.  It is the low three bits of the word —
; one eighth of a seccut step — and hardware.md:360-361 ("6581 caveats") says
; the analog filter varies between machines and that exact cutoff is never to
; be relied on.  Three bits below the resolution of a figure that is itself
; approximate would cost a second six-byte table and its own write for
; nothing audible, so sndinit's zero is left standing and the word is always
; 8 * seccut.
;
; WHY SECTIONS 0, 1, 4 AND 5 STILL ROUTE NOTHING — the deliberate omission,
; recorded here and only here, because this is the table that would have to
; do the routing.  It covers the hymn's two pianos, the Marseillaise's piano
; pair and its reed, and the finale's three keepers.  The reed is the one
; that looks like an oversight: references/hardware.md's Trumpet row is a
; sawtooth WITH a band-pass, and the reed takes its waveform and its sustain
; 10 from that row — but only those two.  Its attack and decay differ for the
; reasons given beside the row itself; its release differs for the reason
; given with the piano rows above, since the 48 ms and the argument for it
; are shared by every sounding row in sections 0 and 1; and the band-pass is
; dropped for the reason below.
;
; It is NO LONGER that the cutoff is unusable — seccut fixed that, and the
; chip would band-pass the reed perfectly well now.  It is that these
; instruments were chosen and judged against an unfiltered signal path and
; are settled: the piano is sold by its envelope alone (see the arc block
; above), and the filter is GLOBAL, so a band-pass placed for the reed would
; also sit on whichever piano voices secres routed alongside it and the two
; would have to be re-judged together.  seccut[0], [1], [4] and [5] are
; therefore $00 and inert — with secres $00 no voice reaches the filter at
; all, so those sections cannot hear their cutoff whatever it holds.  Zero is
; chosen over some other inert value only because it is what sndinit already
; leaves there, so the table records the state rather than changing it.
;
; The writers of the cutoff pair, since a comment here is read as a contract:
;   sndinit   zeroes registers $00-$18 — its loop runs to `cpx #25` — once at
;             startup and once per restart.  Still the ONLY writer of $D415.
;   loadinstr writes $D416 from seccut at seqreset and at every section change
;             but 4->5 (see the head of this block), so section 0 has its
;             value from the first frame and section 5 inherits the finale's.
;   cantick   writes $D416 too, but only while csweep is counting down from a
;             cannon shot, which cannot happen before section 3.
; sndinit's zeroing is load-bearing, not incidental: SID registers survive a
; program stop (see sndinit's own comment), so a register nothing wrote would
; hold whatever the last program left there — $D415 reads 0 precisely BECAUSE
; sndinit writes it.

seccut: .byte   $00, $00, $19, $10, $00, $00   ; $D416; $D415 stays sndinit's 0
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
