; room.s -- the wire-grid room (SPEC.md Section 4).
;
; One static picture: a purple wall grid over rows 0-14, the horizon on row 15,
; and a light-blue floor in true perspective over rows 16-24.  It is drawn once,
; here, out of a generated character set -- so after room_init returns the room
; costs the frame budget exactly nothing (SPEC.md Section 1).
;
; room_init runs before the interrupt is installed, so nothing below has to be
; fast and nothing below can be interrupted mid-copy.
;
; It does NOT copy the character ROM.  All 256 glyphs come from
; tools/gen_room.py (SPEC.md Section 4.3), so there is no $01 banking dance to
; do and no interrupt window to protect -- the usual "switch $01 to $33, copy
; $D000-$DFFF, switch back, and keep the IRQ out of the gap" is simply absent
; from this program.

        .segment "CODE"

; --- VIC-II registers this file owns ---------------------------------------
SCRCTL2 = $D016                 ; reads back $C8: bits 6-7 unused, read as 1
VICMEM  = $D018                 ; reads back $19: bit 0 unused, reads as 1
BORDER  = $D020
BGCOL   = $D021

SCREEN  = $0400                 ; the toolset requires the matrix here
COLRAM  = $D800

COL_WALL  = $04                 ; purple -- the C64 has exactly one, and it is
                                ; the Amiga grid's magenta/violet as close as
                                ; this palette gets (SPEC.md Section 4)
COL_FLOOR = $0E                 ; light blue: the colour CHANGE is the horizon,
                                ; so the two planes separate without the ball
                                ; ever crossing an ambiguous line
WALL_CELLS = 15 * 40            ; 600 -- rows 0-14; row 15 starts at $DA58

room_init:
        ; --- the screen matrix: 1,000 bytes from RODATA to $0400 ----------
        ; Four 250-byte blocks rather than four 256-byte pages: a 1,024-byte
        ; copy would run past the matrix and overwrite the sprite pointers at
        ; $07F8, which ball_step owns.
        ldx     #$00
copyscr: lda    screen_map,x
        sta     SCREEN,x
        lda     screen_map+250,x
        sta     SCREEN+250,x
        lda     screen_map+500,x
        sta     SCREEN+500,x
        lda     screen_map+750,x
        sta     SCREEN+750,x
        inx
        cpx     #250
        bne     copyscr

        ; --- colour RAM by row range, no table (SPEC.md Section 4.3) ------
        ; Rows 0-14 are 600 bytes: $D800-$D9FF is 512 of them, $DA00-$DA57 the
        ; other 88.  Rows 15-24 are the remaining 400: $DA58-$DAFF is 168,
        ; $DB00-$DBE7 the last 232.  $DBE8-$DBFF is past the matrix and is left
        ; alone.
        lda     #COL_WALL
        ldx     #$00
wall1:  sta     COLRAM,x
        sta     COLRAM+256,x
        inx
        bne     wall1
        ldx     #$00
wall2:  sta     COLRAM+512,x
        inx
        cpx     #WALL_CELLS-512 ; 88
        bne     wall2

        lda     #COL_FLOOR
        ldx     #$00
floor1: sta     COLRAM+WALL_CELLS,x
        inx
        cpx     #$A8            ; 168, up to the end of $DAFF
        bne     floor1
        ldx     #$00
floor2: sta     COLRAM+768,x
        inx
        cpx     #$E8            ; 232, up to $DBE7 -- the last cell of row 24
        bne     floor2

        ; --- the VIC's picture --------------------------------------------
        lda     #$1B
        sta     SCRCTL1         ; standard text mode, 25 rows, display on,
                                ; raster compare bit 8 = 0
        lda     #$08
        sta     SCRCTL2         ; 40 columns, no horizontal scroll, not
                                ; multicolour: the grid is single-colour, and
                                ; multicolour text would halve its resolution
        lda     #$18
        sta     VICMEM          ; screen $0400 (bits 7-4 = 1), charset $2000
                                ; (bits 3-1 = 4).  $2000 and not $1000/$1800:
                                ; the character ROM's image covers both of those
                                ; in bank 0 and $1800 fails silently
                                ; (SPEC.md Section 2).
        lda     #$00
        sta     BORDER
        sta     BGCOL           ; black on black: the grid is the only light in
                                ; the room, as it was on the Amiga
        rts
