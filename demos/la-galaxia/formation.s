; formation.s -- the settled grid, in character RAM.
;
; Forty enemies, and none of them a sprite while they sit still: each is a
; 2x2 block of custom glyphs in the screen matrix, coloured per cell in
; colour RAM.  That is what leaves all eight sprites for the things that
; move.  The handoff in both directions is one call -- tosprite erases the
; block and spawns the sprite, togrid does the reverse -- so no frame can
; ever observe an enemy as both or as neither.
;
;   row 1   4 Flagships
;   rows 2-3   16 Sentinels
;   rows 4-5   20 Drones
;
; The grid breathes on a 128-frame cycle.  The rigid part of the sway comes
; free from $D016's fine-scroll bits under a raster split confined to the
; formation band; the expansion proper cannot come from a scroll register,
; which only translates, so it is a redraw at a new cell spacing -- one
; formation row per frame, which keeps it inside the 64-cell budget.

        .segment "ENGINE"

rowwidth:   .byte   4, 8, 8, 10, 10
rowleft:    .byte   16, 12, 12, 10, 10  ; PFCOL + (PFW - width*2)/2
rowscreen:  .byte   3, 5, 7, 9, 11      ; top screen row of the block
rowhalf:    .byte   2, 4, 4, 5, 5       ; where the expansion changes sign
rowtype:    .byte   ETY_FLAGSHIP, ETY_SENTINEL, ETY_SENTINEL, ETY_DRONE, ETY_DRONE
rowfirst:   .byte   0, 4, 12, 20, 30, 40

; The block quadrants: code 64 + type*8 + frame*4 + quadrant.
blockbase:  .byte   GLY_BLOCK0 + 0*8, GLY_BLOCK0 + 1*8, GLY_BLOCK0 + 2*8
; Per-type cell colours: the top half, then the bottom half.
coltop:     .byte   COL_YELLOW, COL_RED, COL_CYAN
colbot:     .byte   COL_RED, COL_YELLOW, COL_BLUE
; A Flagship that has taken one hit.
hurttop     = COL_PURPLE
hurtbot     = COL_RED

; ---- slotrow/slotidx -- slot number to (formation row, index in row) -----
slotrow:
        .repeat 4
        .byte   0
        .endrepeat
        .repeat 8
        .byte   1
        .endrepeat
        .repeat 8
        .byte   2
        .endrepeat
        .repeat 10
        .byte   3
        .endrepeat
        .repeat 10
        .byte   4
        .endrepeat
slotidx:
        .repeat 4, i
        .byte   i
        .endrepeat
        .repeat 8, i
        .byte   i
        .endrepeat
        .repeat 8, i
        .byte   i
        .endrepeat
        .repeat 10, i
        .byte   i
        .endrepeat
        .repeat 10, i
        .byte   i
        .endrepeat

; How many slots the rolling repaint may touch in one frame.  Three is what
; keeps both ceilings: 3 slots x 8 cells (erase + draw) = 24 of the 64 cells
; §11 allows, leaving room for twelve shots and the life icons, and about
; 2,700 cycles of the frame.
REPAINT_SLOTS = 2

; --------------------------------------------------------------------------
; slotcell -- X = slot; sets scrrow/scrcol to the block's top-left cell and
; tmp2 to the formation row.  The expansion pushes the left half of a row one
; cell left and the right half one cell right, which is a real expansion of
; the grid and still fits the 24-column window at the widest row.
; --------------------------------------------------------------------------
slotcell:
        ldy     slotrow,x
        sty     tmp2
        lda     rowscreen,y
        sta     scrrow
        lda     slotidx,x
        asl     a
        clc
        adc     rowleft,y
        sta     scrcol
        lda     slotidx,x
        cmp     rowhalf,y
        bcs     sc1
        lda     scrcol                  ; left half: outward is left
        sec
        sbc     gridexp
        sta     scrcol
        rts
sc1:    lda     scrcol
        clc
        adc     gridexp
        sta     scrcol
        rts

; --------------------------------------------------------------------------
; drawslot -- X = slot: paint the 2x2 block and claim its cells in gridmap.
;
; The four cells are PTR, PTR+1, PTR+40 and PTR+41, so the pointer is built
; ONCE and walked with Y.  Four independent pfput calls rebuilt scrrow/scrcol
; into four pointers -- screen, colour, and the two shadow pointers -- from
; scratch every time, about 160 cycles a cell before a byte was stored; that
; is what put a ten-slot row repaint at 26,306 cycles, half again an NTSC
; frame, all by itself.
; --------------------------------------------------------------------------
drawslot:
        stx     tmp3
        jsr     slotcell
        ldx     tmp3
        lda     enemy_type,x
        cmp     #3
        bcc     :+
        lda     #ETY_FLAGSHIP           ; anything odd draws as a Flagship
:       tay
        lda     blockbase,y
        clc
        adc     animphase
        adc     animphase
        adc     animphase
        adc     animphase               ; + frame*4
        sta     tmp4                    ; first quadrant code
        lda     coltop,y
        sta     tmp0
        lda     colbot,y
        sta     tmp1
        ; a damaged Flagship swaps its colour pointer to purple/red
        cpy     #ETY_FLAGSHIP
        bne     dsl0
        lda     enemy_hp,x
        cmp     #2
        bcs     dsl0
        lda     #hurttop
        sta     tmp0
        lda     #hurtbot
        sta     tmp1
dsl0:   lda     gridexp
        sta     slotexp,x               ; where this block now stands
        jsr     pfptr                   ; PTR/CPTR/BGP/BGC = the top-left cell
        ldy     #0
        lda     tmp4
        sta     (PTR),y
        sta     (BGP),y
        lda     tmp0
        sta     (CPTR),y
        sta     (BGC),y
        iny
        inc     tmp4
        lda     tmp4
        sta     (PTR),y
        sta     (BGP),y
        lda     tmp0
        sta     (CPTR),y
        sta     (BGC),y
        ldy     #40
        inc     tmp4
        lda     tmp4
        sta     (PTR),y
        sta     (BGP),y
        lda     tmp1
        sta     (CPTR),y
        sta     (BGC),y
        iny
        inc     tmp4
        lda     tmp4
        sta     (PTR),y
        sta     (BGP),y
        lda     tmp1
        sta     (CPTR),y
        sta     (BGC),y
        lda     cells_drawn
        clc
        adc     #4
        sta     cells_drawn
        ldx     tmp3
        jsr     claimcells
        ldx     tmp3                    ; claimcells goes through gmptr, which
        rts                             ; leaves X holding the gridmap row

; ---- eraseslot -- X = slot: stars back, and release the cells ------------
; Erases at slotexp -- the spacing this block is really drawn at -- not at the
; global gridexp, which during a rolling repaint is where the block is going,
; not where it is.
eraseslot:
        stx     tmp3
        lda     gridexp
        pha
        lda     slotexp,x
        sta     gridexp
        jsr     slotcell
        pla
        sta     gridexp
        jsr     pfptr
        ldx     scrrow
        lda     row5,x
        clc
        adc     scrcol
        sta     tmp4                    ; star pattern index of the top-left
        ldy     #0
        jsr     starput
        inc     tmp4
        ldy     #1
        jsr     starput
        lda     tmp4                    ; row+1 is five along the star pattern
        clc
        adc     #4
        sta     tmp4
        ldy     #40
        jsr     starput
        inc     tmp4
        ldy     #41
        jsr     starput
        lda     cells_drawn
        clc
        adc     #4
        sta     cells_drawn
        ldx     tmp3
        jsr     releasecells
        ldx     tmp3                    ; same: X comes back as the slot
        rts

; starput -- tmp4 = star pattern index (masked here), Y = cell offset from the
; block pointer: put the starfield back into the screen and the shadow.
starput:
        lda     tmp4
        and     #31
        tax
        lda     starpat,x
        tax
        lda     starglyph,x
        sta     (PTR),y
        sta     (BGP),y
        lda     starcolour,x
        sta     (CPTR),y
        sta     (BGC),y
        rts

; --------------------------------------------------------------------------
; gridmap -- ten rows of 24 cells covering screen rows 3-12, holding slot+1
; for every cell a settled enemy occupies.  A missile then tests one byte
; instead of walking forty slots.
; --------------------------------------------------------------------------
GRIDMAP_ROW0 = 3

gmptr:  ; scrrow/scrcol -> PTR = gridmap cell
        ; Reduce the column to 0..PFW-1 FIRST, then one clc/adc chain.  The
        ; old order was `adc scrcol` then `sec / sbc #PFCOL`, which threw away
        ; the add's carry and then fed the subtract's borrow flag into the
        ; high byte -- so the pointer came out a page high on nearly every
        ; cell and the whole gridmap was addressed off the end of the array.
        lda     scrrow
        sec
        sbc     #GRIDMAP_ROW0
        tax
        lda     scrcol
        sec
        sbc     #PFCOL
        clc
        adc     gmrowlo,x
        sta     PTR
        lda     gmrowhi,x
        adc     #0
        sta     PTR+1
        rts

gmrowlo: .repeat 10, i
        .byte   <(gridmap + PFW*i)
        .endrepeat
gmrowhi: .repeat 10, i
        .byte   >(gridmap + PFW*i)
        .endrepeat

claimcells:
        txa
        clc
        adc     #1
        sta     tmp0
        jmp     gmfill
releasecells:
        lda     #0
        sta     tmp0
gmfill: jsr     gmptr
        ldy     #0
        lda     tmp0
        sta     (PTR),y
        iny
        sta     (PTR),y
        ldy     #PFW
        sta     (PTR),y
        iny
        sta     (PTR),y
        rts

; --------------------------------------------------------------------------
; tosprite / togrid -- the handoff, in one call each.
; --------------------------------------------------------------------------
tosprite:
        jsr     eraseslot
        lda     #EST_DIVE
        sta     enemy_state,x
        jsr     slotpixels              ; start the sprite where the block was
        ; Give it its shape and put it in the multiplexer's list here and now.
        ; Waiting for the next enemytick to notice it left the enemy as
        ; neither a block nor a sprite for two frames.  The erase lands well
        ; after the beam has passed the formation band, so this frame still
        ; shows the block and the next one shows the sprite.
        ldy     enemy_type,x
        cpy     #3
        bcs     :+
        lda     typeshape0,y
        sta     enemy_shape,x
        lda     typecolour,y
        cpy     #ETY_FLAGSHIP
        bne     :++
        ldy     enemy_hp,x
        cpy     #2
        bcs     :++
        lda     #FLAG_HURT_COL
:       jmp     muxadd
:       sta     enemy_col,x
        jmp     muxadd

togrid: jsr     gridsnap
        lda     #EST_GRID
        sta     enemy_state,x
        jsr     drawslot
        rts

; ---- slotpixels -- X = slot: seed the 16.8 position from the grid cell ---
slotpixels:
        stx     tmp3
        jsr     slotcell
        ldx     tmp3
        lda     scrcol
        asl     a
        asl     a
        asl     a                       ; col*8, may carry into the 9th bit
        sta     enemy_x_lsb,x
        lda     #0
        rol     a
        sta     enemy_x_msb,x
        lda     enemy_x_lsb,x
        clc
        adc     #20                     ; 24 (screen origin) - 4 (art inset)
        sta     enemy_x_lsb,x
        bcc     :+
        inc     enemy_x_msb,x
:       lda     scrrow
        asl     a
        asl     a
        asl     a
        clc
        adc     #49                     ; 51 (first raster) - 2 (art inset)
        sta     enemy_y,x
        lda     #0
        sta     enemy_y_msb,x
        sta     enemy_x_frac,x
        sta     enemy_y_frac,x
        rts

gridsnap:
        jmp     slotpixels

; --------------------------------------------------------------------------
; formtick -- the breathe cycle.  One counter drives both halves: the low
; bits pick the fine-scroll sway, and crossing the midpoint flips the
; expansion, which schedules a five-frame redraw.
; --------------------------------------------------------------------------
formtick:
        inc     breathe
        lda     breathe
        and     #$7F
        sta     breathe

        ; triangle 0..63..0 out of the 128-frame counter
        cmp     #64
        bcc     :+
        eor     #$7F                    ; mirror the second half
:       lsr     a
        lsr     a
        lsr     a                       ; 0..7 -- the +-7 pixel rigid sway
        ora     #$08                    ; keep 40 columns
        sta     scrollon

        ; the expansion proper: out for the middle half of the cycle
        lda     breathe
        and     #$7F
        cmp     #32
        bcc     ftin
        cmp     #96
        bcs     ftin
        lda     #1
        bne     ftset
ftin:   lda     #0
ftset:  cmp     gridexp
        beq     ftredraw
        sta     gridexp
        lda     #0
        sta     redrawslot              ; a fresh sweep of the forty starts
        ldx     #NMUXOBJ-1              ; and every homing target has moved
:       sta     homeok,x
        dex
        bpl     :-

; The repaint is a rolling cursor over the forty slots, REPAINT_SLOTS a frame,
; not one whole formation row: the widest row is ten slots, and repainting ten
; in one frame was 26,306 cycles -- half again an NTSC frame.  Each slot
; carries the spacing it is drawn at in slotexp, so restarting the sweep part
; way through (the animation flip does exactly that) is harmless: a slot
; already at the new spacing is simply repainted in place, never erased at a
; position it does not occupy.
ftredraw:
        lda     redrawslot
        cmp     #FORMATION_SIZE
        bcs     ftanim
        ; The repaint yields to a busy frame.  Nothing needs it to finish
        ; inside any particular number of frames -- the expansion only changes
        ; twice in a 128-frame breathe -- and an entrance frame already
        ; carrying sixteen sprites has no cycles to spare for it.  slotexp
        ; keeps every block's erase honest however long the sweep takes.
        lda     mux_count
        cmp     #4
        bcs     ftanim
        lda     #REPAINT_SLOTS
        sta     ftrcount
ftr1:   ldx     redrawslot
        cpx     #FORMATION_SIZE
        bcs     ftanim
        lda     enemy_state,x
        cmp     #EST_GRID
        bne     ftr2                    ; not settled: nothing on screen to fix
        lda     slotexp,x
        cmp     gridexp
        beq     ftrd                    ; same cells: repaint in place
        jsr     eraseslot               ; moved: clear where it really is
        ldx     redrawslot
ftrd:   jsr     drawslot
        inc     redrawslot
        dec     ftrcount
        bne     ftr1
        beq     ftanim
ftr2:   inc     redrawslot
        jmp     ftr1

ftanim: ; the settled grid flaps on a slow cadence
        lda     frames
        and     #$1F
        bne     ftdone
        lda     animphase
        eor     #1
        sta     animphase
        lda     #1
        sta     animdirty               ; sprites re-derive their shape once
        lda     #0
        sta     redrawslot              ; and that is a full repaint too
ftdone: rts

; --------------------------------------------------------------------------
; buildformation -- fill the forty slots for a new stage.  Nothing is drawn:
; every enemy arrives by flying its entrance path.
; --------------------------------------------------------------------------
buildformation:
        ldx     #0
bf1:    lda     #EST_DEAD
        sta     enemy_state,x
        lda     #0
        sta     enemy_flags,x
        sta     enemy_timer,x
        sta     slotexp,x
        sta     objok,x
        inx
        cpx     #MAX_ENEMIES
        bne     bf1

        ldx     #0
bf2:    ldy     slotrow,x
        lda     rowtype,y
        sta     enemy_type,x
        cmp     #ETY_FLAGSHIP
        bne     :+
        lda     #2                      ; two hits destroy a Flagship
        bne     :++
:       lda     #1
:       sta     enemy_hp,x
        txa
        sta     enemy_slot,x
        inx
        cpx     #FORMATION_SIZE
        bne     bf2

        lda     #FORMATION_SIZE
        sta     enemies_left
        ; gridmap is 10*PFW = 240 bytes, which fits in one indexed pass.  The
        ; second store (`gridmap+256,x`) wrote 256 bytes past the end of it,
        ; straight through the start of bgbuf.
        ldx     #0
bf3:    lda     #0
        sta     gridmap,x
        inx
        cpx     #10*PFW
        bne     bf3
        rts
