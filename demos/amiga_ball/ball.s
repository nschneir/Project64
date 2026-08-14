; ball.s -- the ball: physics, impacts, rotation index, shadow band, and every
; sprite register written each frame (SPEC.md Sections 5.4, 6, 7, 9, 12).
;
; The whole per-frame job is a fixed cost.  Nothing here allocates, searches, or
; loops a number of times that depends on where the ball is: the bounce is a
; table lookup, the travel is two adds, the rotation is an add and a mask, and
; the shadow band is three compares.  That is what makes SPEC.md Section 11's
; budget a claim about the code rather than about a lucky frame.

Y_FLOOR = 158                   ; sprite-0 Y at floor contact.  The sphere's
                                ; bottom raster is sprite_y + 77 = 235, the
                                ; floor line (SPEC.md Section 6.1).
X_BASE  = 24                    ; ball_xi is measured from here: sprite-0 X is
                                ; 24 + ball_xi, so the integer stays in a byte
                                ; while the sprite X reaches 247.
X_MAX   = 223                   ; ball_xi's right bound.  24 + 223 + 48 + 48 is
                                ; the right edge of the ball at 343 -- the last
                                ; fully visible column, so the ball never leaves
                                ; the screen (SPEC.md Section 6.2).
X_OOB   = X_MAX+1               ; one past the bound.  ball_xi is unsigned, so a
                                ; step off the LEFT edge wraps to $FF and a step
                                ; off the right reaches 224-225: a single
                                ; `cmp #224 / bcs` catches both, and the sign of
                                ; ball_vx says which one happened.
X_MSB   = 184                   ; 24 + 184 + 48 = 256: at and above this the
                                ; right-hand column of sprites needs X bit 8
                                ; (SPEC.md Section 6.3).
MSB_ON  = $2A                   ; bits 1, 3, 5 -- sprites 1, 3 and the right
                                ; half of the shadow, the only three that can
                                ; ever cross 256.

VX_INIT = $01C0                 ; 1.75 px/frame in signed 8.8
PH_INIT = 32                    ; start at the apex, so the first floor impact
                                ; is frame 32 and every 64th after it
XI_INIT = 40

BOUNCE_P = 64                   ; frames per bounce = entries in bounce_tab
ROT_MASK = $0F                  ; 16 rotation frames spanning the texture's 45
                                ; deg period (SPEC.md Section 5.3)

SPRY_LO = 42                    ; the bottom sprite row sits +42 rasters: 21
                                ; rasters of data, Y-expanded.
SPRX_R  = 48                    ; the right column sits +48 px: 24 px of data,
                                ; X-expanded.

SHBLK0  = 224                   ; $3800 / 64 -- shadow.inc is linked immediately
                                ; after sprites.inc, so its first block is here.
SHADOW_Y = 225                  ; fixed: the shadow lives on the floor plane,
                                ; not under the ball.  Row 10 of its 21 lands on
                                ; raster 235, the contact line (Section 7).
SH_BAND = 26                    ; shadow size band width, in rasters of height

        .segment "CODE"

; ---------------------------------------------------------------------------
; ball_init -- the initial physical state (SPEC.md Section 12: this is what
; makes the demo deterministic, so an evidence capture at frame N is the same
; picture on every run) and the sprite configuration that never changes.
ball_init:
        lda     #XI_INIT
        sta     ball_xi
        lda     #$00
        sta     ball_xf
        lda     #<VX_INIT
        sta     ball_vx
        lda     #>VX_INIT
        sta     ball_vx+1
        lda     #PH_INIT
        sta     bounce_phase
        lda     #$01
        sta     spin_dir        ; $01 or $FF, and nothing else: ball_step adds it
                                ; to rot_frame, so the two directions are the
                                ; same instruction.
        lda     #$00
        sta     rot_frame
        sta     freeze
        sta     bounce_count
        sta     wall_count
        sta     last_impact
        sta     frame_count
        sta     frame_count+1
                                ; The VARS area ships as zeros, so these stores
                                ; are redundant on the first run and load-bearing
                                ; on none -- they are here so the initial state
                                ; is stated in one place rather than inferred
                                ; from a segment type.

        lda     #$3F
        sta     SPRENA          ; sprites 0-5: the ball's four and the shadow's
        sta     SPREXPX         ; two.  $D01D is $3F, not $0F -- the shadow pair
                                ; is X-expanded too, which is what makes two
                                ; 24-px hires sprites exactly the ball's width.
        lda     #$0F
        sta     SPRMC           ; only the ball is multicolour: 12 pixel-pairs
        sta     SPREXPY         ; per row, and expanded in Y as well, for 4x2 px
                                ; texels.  The shadow stays hires so its ellipse
                                ; edge is finer than the ball's (Section 7).
        lda     #$30            ; bits 4/5: the shadow goes BEHIND character
        sta     SPRPRI          ; data, so the floor's grid lines run over it and
                                ; it reads as lying on the floor.  Bits 0-3 stay
                                ; clear: the ball passes in front.

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
        lda     #$0B            ; dark gray.  The floor is black, so nothing can
        sta     SPRCOL0+4       ; be darker than it: what the shadow supplies is
        sta     SPRCOL0+5       ; a gray patch where the black would otherwise
        rts                     ; be, which is the only way a shadow exists
                                ; against black (SPEC.md Section 7).

; ---------------------------------------------------------------------------
; ball_step -- one frame of ball, in the order SPEC.md Section 12 depends on:
;
;   1. advance the physics -- SKIPPED while `freeze` is set;
;   2. derive everything else from the state, frozen or not;
;   3. write the registers, frozen or not.
;
; That split is the staging hook: with `freeze` set, poking bounce_phase = 32
; and running one tick puts the apex on screen exactly, because steps 2 and 3
; still run.  If freezing skipped the register writes as well, a staged state
; would be invisible and the evidence in Section 13 could not be captured.
ball_step:
        lda     freeze
        beq     ballrun
        jmp     ballderive      ; jmp, not a branch: steps 2-4 are well over 127
                                ; bytes away.
ballrun:

; --- 1. advance ------------------------------------------------------------
        ; X travel: 16-bit 8.8, ball_xf/ball_xi += signed ball_vx.  clc before
        ; the low add and NOT before the high one -- the carry out of the low
        ; byte is the whole point of the pair.  Adding a negative velocity is
        ; the same two instructions because $FE40 is -$01C0 in two's complement.
        clc
        lda     ball_xf
        adc     ball_vx
        sta     ball_xf
        lda     ball_xi
        adc     ball_vx+1
        sta     ball_xi

        cmp     #X_OOB          ; 0-223 is in bounds; 224-225 overshot the right
        bcc     ballnowall      ; wall and $FE-$FF underflowed past the left one
        bit     ball_vx+1       ; N = sign of the velocity that got us here
        bmi     ballleft

        ; --- right wall --------------------------------------------------
        lda     #X_MAX
        sta     ball_xi
        lda     #$00
        sta     ball_xf         ; clamp the fraction too, so the reversal always
                                ; happens from exactly the bound and the motion
                                ; stays reproducible frame for frame.
        lda     #3              ; 3 = wall-right
        bne     ballwall        ; always taken; A is the impact code

ballleft:
        lda     #$00
        sta     ball_xi
        sta     ball_xf
        lda     #2              ; 2 = wall-left

ballwall:
        sta     last_impact
        pha
        inc     wall_count

        sec                     ; VX = -VX, 16-bit two's complement
        lda     #$00
        sbc     ball_vx
        sta     ball_vx
        lda     #$00
        sbc     ball_vx+1
        sta     ball_vx+1

        sec                     ; spin_dir = -spin_dir, i.e. $01 <-> $FF.  The
        lda     #$00            ; ball rolls the way it travels, so reversing
        sbc     spin_dir        ; direction without reversing the spin would read
        sta     spin_dir        ; as the ball skidding off the wall.

        pla                     ; A = 1 floor, 2 wall-left, 3 wall-right
        jsr     sound_impact
ballnowall:

        ; Vertical: the phase advances and the table does the rest.  Impact is
        ; the WRAP 63 -> 0, not a comparison against the floor -- the table's
        ; last entry is 6.4 rasters above contact, so a "y >= 158" test would
        ; never fire (SPEC.md Section 6.1).
        inc     bounce_phase
        lda     bounce_phase
        cmp     #BOUNCE_P
        bcc     ballnofloor
        lda     #$00
        sta     bounce_phase
        inc     bounce_count
        lda     #1              ; 1 = floor
        sta     last_impact
        jsr     sound_impact
ballnofloor:

        ; rot_frame = (rot_frame + spin_dir) & 15.  spin_dir is $01 or $FF, so
        ; one add and one mask serve both directions: +$FF is -1 modulo 256, and
        ; the mask takes it back into 0-15 either way.
        lda     rot_frame
        clc
        adc     spin_dir
        and     #ROT_MASK
        sta     rot_frame

        inc     frame_count
        bne     ballderive
        inc     frame_count+1

; --- 2. derive (runs frozen too) -------------------------------------------
ballderive:
        ; Y from the table: two bytes per entry, fraction first, so the index is
        ; 2 * bounce_phase and the pair lands in ball_yf/ball_yi in order.
        lda     bounce_phase
        asl     a               ; 0-63 doubled is 0-126: no carry out
        tax
        lda     bounce_tab,x
        sta     ball_yf
        lda     bounce_tab+1,x
        sta     ball_yi

        ; Absolute sprite-0 X.  ball_xi <= 223, so 24 + ball_xi <= 247 and the
        ; high byte is always 0 -- it is stored anyway because shadow_x16 and
        ; the tests read it as a 16-bit quantity.
        lda     ball_xi
        clc
        adc     #X_BASE
        sta     ball_x16
        sta     shadow_x16      ; the shadow tracks the ball's X with no lag,
                                ; because it is derived from the same byte in
                                ; the same frame (SPEC.md Section 7).
        lda     #$00
        adc     #$00
        sta     ball_x16+1
        sta     shadow_x16+1

        ; Shadow size from the ball's height above contact, h = 158 - ball_yi,
        ; in 26-raster bands: 0-25 -> 0, 26-51 -> 1, 52-77 -> 2, 78+ -> 3.  h
        ; reaches 104 at the apex, which is band 4 by division and 3 by these
        ; compares -- the top band is deliberately open-ended, because there is
        ; no fifth shape.
        lda     #Y_FLOOR
        sec
        sbc     ball_yi
        ldx     #0
        cmp     #SH_BAND
        bcc     ballsz
        inx
        cmp     #SH_BAND*2
        bcc     ballsz
        inx
        cmp     #SH_BAND*3
        bcc     ballsz
        inx
ballsz: stx     shadow_size

; --- 3. the sprite registers ------------------------------------------------
        ; The 2x2 grid: sprites 0/1 are the top row, 2/3 the bottom, and the
        ; shadow's 4/5 share the same two X columns.  The right column is +48
        ; and the bottom row +42 because expansion doubles the sprite -- 24 px
        ; of data is 48 px wide, 21 rasters are 42 tall.
        lda     ball_x16
        sta     SPR0X+0         ; $D000  sprite 0, top left
        sta     SPR0X+4         ; $D004  sprite 2, bottom left
        sta     SPR0X+8         ; $D008  sprite 4, shadow left
        clc
        adc     #SPRX_R
        sta     SPR0X+2         ; $D002  sprite 1, top right
        sta     SPR0X+6         ; $D006  sprite 3, bottom right
        sta     SPR0X+10        ; $D00A  sprite 5, shadow right

        lda     ball_yi
        sta     SPR0X+1         ; $D001
        sta     SPR0X+3         ; $D003
        clc
        adc     #SPRY_LO
        sta     SPR0X+5         ; $D005
        sta     SPR0X+7         ; $D007
        lda     #SHADOW_Y
        sta     SPR0X+9         ; $D009  the shadow does not rise with the ball
        sta     SPR0X+11        ; $D00B

        ; $D010 is REBUILT from scratch every frame, never read-modify-written.
        ; A stale MSB is a ball that teleports 256 pixels the moment anything
        ; else touches the register, and rebuilding is cheaper than being
        ; careful: the byte has exactly two legal values here (Section 6.3).
        lda     ball_xi
        cmp     #X_MSB
        lda     #$00
        bcc     ballmsb
        lda     #MSB_ON
ballmsb: sta    SPRXMSB

; --- 4. the pointers --------------------------------------------------------
        ; Switching a rotation frame is four pointer writes and no data movement
        ; -- the reason all 16 frames can be resident at once, and the reason
        ; the frame budget is what it is (SPEC.md Section 5.4).  Frame f is
        ; blocks 160+4f .. 163+4f.
        lda     rot_frame
        asl     a
        asl     a               ; 4 * rot_frame; rot_frame <= 15, so no carry out
        clc
        adc     #BLOCK0
        ldx     #0
ballptr: sta    SPRPTR,x
        sta     sptr,x          ; mirrored into VARS so a test can compare what
                                ; the code meant to write against what the
                                ; screen actually holds
        clc
        adc     #1
        inx
        cpx     #4
        bne     ballptr

        ; The shadow's two blocks: 224 + 2*size, and its right half one past it.
        lda     shadow_size
        asl     a
        clc
        adc     #SHBLK0
        sta     SPRPTR+4        ; $07FC
        clc
        adc     #1
        sta     SPRPTR+5        ; $07FD
        rts
