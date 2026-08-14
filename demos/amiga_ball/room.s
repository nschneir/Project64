; room.s -- the wire-grid room (SPEC.md Section 4).
;
; Stub: Task 2 fills room_init in.  It will copy screen_map to $0400, fill
; colour RAM by row range, and set $D011/$D016/$D018/$D020/$D021.  Until then
; the machine keeps the KERNAL's own text mode, which is what lets Task 1 judge
; the ball against a plain background.

        .segment "CODE"

room_init:
        rts
