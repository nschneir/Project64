; vars.s -- the VARS area: every byte a stopped machine is allowed to be asked
; about, at an address fixed by `--area 'VARS=$4000:$0100'` rather than by where
; the code happened to end (SPEC.md Section 9).
;
; The ORDER of these .res directives is the layout: the addresses in SPEC.md
; Section 9 are a consequence of it, and `test.yaml`, `c64 audio capture
; --at-frame` and the evidence scripts all name literal addresses.  Change the
; order and those break silently.  ball_xf = $4000, irq_hwm = $4010,
; freeze = $4015, sid_shadow = $401D.
;
; VARS sits outside the VIC's bank 0, so the chip never reads any of it.  It is
; the last area, which is why it is not padded out to $0100.  Its .res storage
; still ships as zeros -- the segment is type = ro, not bss -- so every counter
; below starts at 0 without an init loop.

        .segment "VARS"

        .export ball_xf, ball_xi, ball_x16, ball_vx, ball_yf, ball_yi
        .export bounce_phase, rot_frame, spin_dir, bounce_count, wall_count
        .export last_impact, frame_count, irq_hwm, irq_last
        .export shadow_x16, shadow_size, freeze, sptr, alive
        .export snd_timer, snd_kind, sid_shadow, rasterin, tmp

ball_xf:      .res 1            ; +0  X fraction (8.8 low byte)
ball_xi:      .res 1            ; +1  X integer 0-223, offset from X_BASE = 24
ball_x16:     .res 2            ; +2  absolute sprite-0 X, lo/hi (24-247)
ball_vx:      .res 2            ; +4  X velocity, signed 8.8 ($01C0 / $FE40)
ball_yf:      .res 1            ; +6  Y fraction
ball_yi:      .res 1            ; +7  Y integer = the sprite-0 Y register (54-158)
bounce_phase: .res 1            ; +8  0-63, index into the bounce table
rot_frame:    .res 1            ; +9  0-15
spin_dir:     .res 1            ; +10 $01 or $FF
bounce_count: .res 1            ; +11 floor impacts, wraps at 256
wall_count:   .res 1            ; +12 wall impacts, wraps at 256
last_impact:  .res 1            ; +13 0 none, 1 floor, 2 wall-left, 3 wall-right
frame_count:  .res 2            ; +14 16-bit, lo/hi
irq_hwm:      .res 1            ; +16 most raster lines any tick has consumed
irq_last:     .res 1            ; +17 what the last tick consumed
shadow_x16:   .res 2            ; +18 sprite-4 X, lo/hi
shadow_size:  .res 1            ; +20 0-3
freeze:       .res 1            ; +21 non-zero freezes physics -- the staging
                                ;     hook every capture and test poses with
sptr:         .res 4            ; +22 the four ball sprite pointers as written
alive:        .res 1            ; +26 incremented by the main loop
snd_timer:    .res 1            ; +27 0-24, 24 = idle
snd_kind:     .res 1            ; +28 1 = floor, 2 = wall
sid_shadow:   .res 25           ; +29 mirror of $D400-$D418; the SID is
                                ;     write-only, so this is the only thing a
                                ;     stopped machine can read back
rasterin:     .res 1            ; +54 scratch: $D012 at tick entry
tmp:          .res 8            ; +55 scratch.  UNUSED by the shipped program --
                                ;     grepped, zero references outside this file
                                ;     -- and kept because SPEC.md Section 9
                                ;     declares it at $4037 and every address
                                ;     after $4000 is load-bearing by arrangement.
                                ;     The whole per-frame job runs out of A/X/Y:
                                ;     the physics is two adds, the bounce and the
                                ;     shadow are table lookups, and the sound
                                ;     schedule keeps its state in snd_timer, so
                                ;     nothing has ever needed a spill slot.
