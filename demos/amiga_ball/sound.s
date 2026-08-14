; sound.s -- the impact synth (SPEC.md Section 8).
;
; Task 5 fills sound_init, sound_step and sound_impact in.  sidput is here from
; Task 1 because startup already needs it to zero the chip.

SIDBASE = $D400

        .segment "CODE"

; ---------------------------------------------------------------------------
; sidput -- A = value, X = SID register offset 0-24.  EVERY SID write in this
; demo goes through here: the SID is write-only, so sid_shadow is the only thing
; a stopped machine can be asked what the program played.  A bare `sta $D4xx`
; anywhere else is a defect, not a shortcut.  A and X come back unchanged, which
; is what lets startup's zeroing loop keep its counter in X.
sidput: sta     SIDBASE,x
        sta     sid_shadow,x
        rts

; ---------------------------------------------------------------------------
sound_init:
        rts

; ---------------------------------------------------------------------------
sound_step:
        rts

; ---------------------------------------------------------------------------
; sound_impact -- A = 1 floor, 2 wall-left, 3 wall-right.
sound_impact:
        rts
