; scroll.s -- the character-column shift underneath the $D016 fine scroll.
;
; The fine scroll walks 6,4,2,0 (two pixels a frame, written in tick); on the
; frame after 0 the picture has to move one whole character column left, and
; that is this file.
;
; ONE LINEAR MOVE, NOT FIFTEEN ROW MOVES.  Screen rows BANDTOP..BANDTOP+14 are
; contiguous in memory, so shifting the band left by one column is a single
; 600-byte memmove of screen RAM interleaved with 600 bytes of colour RAM.  A
; linear move puts new[r][39] = old[r+1][0], which is wrong -- and harmless,
; because drawcol overwrites column 39 of every band row before it can be
; seen.  Being linear is also what makes it top-down, which is the order the
; beam needs.
;
; THE DEADLINE IS PER ROW, AND IT IS THE BADLINE.  The VIC fetches a text
; row's whole character matrix and its colour nybbles on the badline at that
; row's FIRST raster, so row R's bytes must be final by raster 51 + 8*R -- not
; by the row's last line.  Band row j is screen row BANDTOP+j, so the last row
; here is deadline 51 + 8*19 = 203.  The IRQ is armed at raster 251, in the
; bottom border of the frame BEFORE the one it prepares, which is worth 12
; lines of head start; see the comment on irqon in fugue.s.
;
; PAGE ALIGNMENT IS WORTH 1.7 CYCLES A CELL.  `lda base+1+i,x` costs an extra
; cycle whenever base+1+i+x crosses a page, and with a single 256-cell block
; based at $04C9 that is most of the reads: the first build measured 22.3
; cycles a cell against an 18-cycle instruction floor.  Splitting the move at
; page boundaries removes almost all of them.  The chunk sizes below are
; computed for BANDTOP = 5 and BANDROWS = 15 and asserted, rather than derived
; -- change the geometry and the assert tells you to recompute them.

        .segment "CODE"

SBAND    = SCREEN + BANDTOP * 40        ; $04C8 with BANDTOP = 5
CBAND    = COLRAM + BANDTOP * 40        ; $D8C8
SCELLS   = BANDROWS * 40                ; 600

        .assert SBAND = $04C8, error, "shiftband's chunk sizes assume BANDTOP = 5"
        .assert SCELLS = 600, error, "shiftband's chunk sizes assume BANDROWS = 15"

; One 8-cell group, screen and colour together.  Unrolled by eight so the loop
; overhead is 11 cycles per 8 cells rather than per cell.
.macro  SHIFT8  sbase, cbase
        .repeat 8, i
        lda     sbase + 1 + i,x
        sta     sbase + 0 + i,x
        lda     cbase + 1 + i,x
        sta     cbase + 0 + i,x
        .endrepeat
.endmacro

; `count` cells starting at `off`, never crossing a page.  A count of 256 is
; spelled `cpx #0`: X wraps to 0 after the last group, which ends the loop.
.macro  SHIFTCHUNK off, count
        ldx     #0
:       SHIFT8  SBAND + off, CBAND + off
        txa
        clc
        adc     #8
        tax
        cpx     #<(count)
        bne     :-
.endmacro

shiftband:
        SHIFTCHUNK   0,  56         ; $04C8-$04FF, $D8C8-$D8FF
        SHIFTCHUNK  56, 256         ; $0500-$05FF, $D900-$D9FF
        SHIFTCHUNK 312, 256         ; $0600-$06FF, $DA00-$DAFF
        SHIFTCHUNK 568,  32         ; $0700-$071F, $DB00-$DB1F
        rts
