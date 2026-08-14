; ball.s -- the ball: physics, sprite registers, pointers, shadow selection
; (SPEC.md Sections 5.4, 6, 7).
;
; Task 1 ships the STATIC version of this: the four ball sprites are configured
; and parked, and ball_step rewrites their registers every frame from constants.
; It writes the registers each frame rather than once at init because that is
; the shape Task 3 fills in -- and because a tick that costs nothing measures
; nothing, so irq_hwm would read 0 and prove neither that the handler runs nor
; that the cost measurement works.

PARK_X  = 120                   ; sprite-0 X while the ball is parked
PARK_Y  = 120                   ; sprite-0 Y ditto

        .segment "CODE"

; ---------------------------------------------------------------------------
; ball_init -- sprite configuration that never changes afterwards.
ball_init:
        lda     #$0F
        sta     SPRENA          ; sprites 0-3; the shadow's 4-5 arrive in Task 4
        sta     SPRMC           ; all four multicolour: 12 pixel-pairs per row
        sta     SPREXPY         ; ... and the ball is expanded in both axes.
        lda     #$3F            ; Expansion changes no data -- the texel grid is
        sta     SPREXPX         ; 24x36 either way -- it buys size for free, at
                                ; 4x2 px texels.  $D01D is $3F, not $0F, because
                                ; the shadow pair is X-expanded too (Section 7).
        lda     #$30            ; bits 4/5: the shadow goes BEHIND character
        sta     SPRPRI          ; data, so the floor's grid lines run over it.
                                ; Bits 0-3 stay clear: the ball is in front.

        ; Multicolour bit pair -> colour (SPEC.md Section 3.3).  $D025/$D026 are
        ; shared by every multicolour sprite, which is why red -- the one colour
        ; only the ball needs -- has to be the per-sprite one.
        lda     #$00
        sta     SPRMC0          ; pair 01 -> black, the one-texel rim
        lda     #$01
        sta     SPRMC1          ; pair 11 -> white checker
        lda     #$02
        ldx     #3
ballcol: sta    SPRCOL0,x       ; pair 10 -> red checker, sprites 0-3
        dex
        bpl     ballcol
        rts

; ---------------------------------------------------------------------------
; ball_step -- one frame's worth of ball.  Task 3 replaces the constants below
; with the bounce table and the 8.8 travel; the register writes are already in
; the order and the pairing Section 14 items 7 and 8 assert.
ball_step:
        ; The 2x2 grid: sprites 0/1 are the top row, 2/3 the bottom.  The right
        ; column is +48 and the bottom row +42 because expansion doubles the
        ; sprite -- 24 px of data is 48 px wide, 21 rasters are 42 tall.
        lda     #PARK_X
        sta     SPR0X+0         ; $D000  sprite 0, top left
        sta     SPR0X+4         ; $D004  sprite 2, bottom left
        lda     #PARK_X+48
        sta     SPR0X+2         ; $D002  sprite 1, top right
        sta     SPR0X+6         ; $D006  sprite 3, bottom right
        lda     #PARK_Y
        sta     SPR0X+1         ; $D001
        sta     SPR0X+3         ; $D003
        lda     #PARK_Y+42
        sta     SPR0X+5         ; $D005
        sta     SPR0X+7         ; $D007

        ; $D010 is rebuilt from scratch every frame, never read-modify-written:
        ; a stale MSB is a ball that teleports 256 pixels, and rebuilding is
        ; cheaper than being careful (SPEC.md Section 6.3).
        lda     #$00
        sta     SPRXMSB

        ; Switching a rotation frame is four pointer writes and no data movement
        ; -- the reason all 16 frames can be resident at once (Section 5.4).
        ; Task 1 holds frame 0, so the blocks are BLOCK0..BLOCK0+3.
        ldx     #0
ballptr: txa
        clc
        adc     #BLOCK0
        sta     SPRPTR,x
        sta     sptr,x          ; mirrored so a test can compare the two
        inx
        cpx     #4
        bne     ballptr

        inc     frame_count
        bne     ballfc
        inc     frame_count+1
ballfc: rts
