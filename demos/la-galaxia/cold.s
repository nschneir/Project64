; cold.s -- the cold open (PROMPT.md §1a): the narration screen that comes
; before the title, and the one place this game leaves text mode.
;
; The screen is a hires bitmap at $2000-$3F3F -- ON TOP of the sprite blocks
; and the charset.  That is safe only because of when this state runs:
; nothing needs a sprite or a custom glyph while the cold open is up, and the
; way out rebuilds both (the exit phases below re-run the charset copy and
; the sprite fan-out) before the title state ever draws a cell.  The glyphs
; are therefore scaled from chars.inc's data in the ENGINE segment, never
; from $3800, which this screen has just overwritten.
;
; $D018 never changes: $1E already means screen $0400, and its bit 3 selects
; bitmap base $2000 in bitmap mode -- the same byte serves both worlds.
;
; Everything here is a step machine.  A full-screen bitmap clear is ~45,000
; cycles, a page of 4x glyphs ~55,000, the art restore ~50,000 -- each of
; them several NTSC frames -- so every phase does a bounded slice per tick
; and tick_overrun stays 0.  The visible cost is a top-down wipe and a
; typewriter reveal, which read as intent rather than as slowness.
;
; Layout, from §1a's arithmetic: 4x narration is 10 characters by 6 lines
; maximum, and the text is 98 characters, so it pages -- four pages of three
; lines, each line centred, the block sitting above the vertical centre
; (cell rows 2-15).  The Spanish instruction is pinned at 2x on two rows
; (cell rows 20-23) on every page.  SPACE skips to the title at any point;
; the timer advances the pages otherwise, and after the last page the state
; leaves for the title on its own -- the attract loop's cycle is
; cold open -> title -> (game) -> game over -> cold open.

        .segment "ENGINE"

BITMAP  = $2000

; entry phases
CPH_CLR  = 0                    ; clear the whole bitmap, 2 cell rows a tick
CPH_COL  = 1                    ; colour nibbles into the screen matrix
CPH_SPA  = 2                    ; the pinned Spanish line, 2x, screen still off
CPH_DRAW = 3                    ; narration glyphs at 4x, 3 a tick
CPH_HOLD = 4                    ; hold the page on a timer
CPH_WIPE = 5                    ; clear the narration band for the next page
; exit phases -- the art restore, one slice a tick
CPX_OFF  = 6                    ; screen off, back to text mode
CPX_CHR0 = 7                    ; blank charset $3800-$3BFF
CPX_CHR1 = 8                    ; blank charset $3C00-$3FFF
CPX_FONT = 9                    ; font glyphs back in
CPX_PUNCT = 10                  ; punctuation glyphs back in -- a separate
                                ; tick: both through copyblock (~30 cycles a
                                ; byte) crossed the frame and tick_overrun
                                ; counted it, measured on the machine
CPX_GAME = 11                   ; game glyphs back in
CPX_SPR0 = 12                   ; sprite shapes 0-10 fanned back out
CPX_SPR1 = 13                   ; sprite shapes 11-20
CPX_SCR0 = 14                   ; clear the screen matrix, first half
CPX_SCR1 = 15                   ; second half
CPX_GO   = 16                   ; screen on, titlereset, ST_TITLE

COLDPAGES = 4
PAGE_HOLD = 240                 ; four seconds a page at 60 Hz

; the colour nibbles: high nibble = the 1-pixels, low = the 0-pixels
COLD_NARR = $10                 ; white on black
COLD_SPA  = $30                 ; cyan on black, like the title's start lines

; ---- coldenter -- the only way into ST_COLD ------------------------------
coldenter:
        lda     #ST_COLD
        jmp     setstate

; ---- the state handler ---------------------------------------------------
stcold: lda     stinit
        beq     cnorm
        lda     #0
        sta     stinit
        ; Screen off and bitmap mode selected in one write: the clear and
        ; the art teardown happen in the dark.
        lda     #$2B
        sta     SPRCTRL1
        ; Kill every sprite object the game left behind -- after a game
        ; over the mux list still carries the formation, and six sprites
        ; pointed into what is about to become bitmap would draw garbage.
        lda     #0
        sta     SPRENA
        sta     mux_n
        sta     plalive
        sta     pldual
        sta     plstate
        sta     mus_on                  ; the theme belongs to the title
        ldx     #NMUXOBJ-1
:       sta     inlist,x
        sta     objok,x
        dex
        bpl     :-
        lda     #$FF
        sta     beamslot
        jsr     clearshots
        jsr     sidinit                 ; silence, and a clean shadow
        lda     scrolloff               ; the band events still fire; with
        sta     scrollon                ; scrollon = scrolloff they are no-ops
        lda     #0
        sta     coldphase
        sta     coldpage
        sta     coldrow
        rts

cnorm:  ; SPACE leaves for the title from ANY point, including part-way
        ; through the first page -- but once the exit is running, let it run.
        lda     coldphase
        cmp     #CPX_OFF
        bcs     cdisp
        lda     input_edge
        and     #IN_ST1
        beq     cdisp
        lda     #CPX_OFF
        sta     coldphase
cdisp:  ldx     coldphase
        lda     coldjhi,x
        pha
        lda     coldjlo,x
        pha
        rts

coldjlo:
        .byte   <(cphclr-1),  <(cphcol-1),  <(cphspa-1),  <(cphdraw-1)
        .byte   <(cphhold-1), <(cphwipe-1), <(cpxoff-1),  <(cpxchr0-1)
        .byte   <(cpxchr1-1), <(cpxfont-1), <(cpxpunct-1), <(cpxgame-1)
        .byte   <(cpxspr0-1), <(cpxspr1-1), <(cpxscr0-1), <(cpxscr1-1)
        .byte   <(cpxgo-1)
coldjhi:
        .byte   >(cphclr-1),  >(cphcol-1),  >(cphspa-1),  >(cphdraw-1)
        .byte   >(cphhold-1), >(cphwipe-1), >(cpxoff-1),  >(cpxchr0-1)
        .byte   >(cpxchr1-1), >(cpxfont-1), >(cpxpunct-1), >(cpxgame-1)
        .byte   >(cpxspr0-1), >(cpxspr1-1), >(cpxscr0-1), >(cpxscr1-1)
        .byte   >(cpxgo-1)

; ==========================================================================
; Entry: clear, colour, Spanish line, then page after page
; ==========================================================================

; ---- CPH_CLR: the whole bitmap, two cell rows (640 bytes) a tick ---------
cphclr: lda     #25
        sta     tmp2
        jsr     bmclr1
        jsr     bmclr1
        lda     coldrow
        cmp     #25
        bcc     :+
        lda     #CPH_COL
        sta     coldphase
:       rts

; ---- CPH_COL: the colour matrix, one tick --------------------------------
; Rows 0-19 (bytes 0-799) carry the narration's white; rows 20-24 (bytes
; 800-999) the Spanish line's cyan.  $07E8-$07FF -- the sprite pointers --
; are left alone.
cphcol: lda     #COLD_NARR
        ldx     #0
:       sta     SCREEN,x
        sta     SCREEN+$100,x
        sta     SCREEN+$200,x
        inx
        bne     :-
:       sta     SCREEN+$300,x
        inx
        cpx     #32                     ; $0700-$071F: the last 32 white cells
        bne     :-
        lda     #COLD_SPA
:       sta     SCREEN+$300,x
        inx
        cpx     #232                    ; $0720-$07E7: the 200 cyan cells
        bne     :-
        ; set up the Spanish draw
        lda     #0
        sta     coldline
        sta     coldcp
        lda     spacol
        sta     coldcol
        lda     #CPH_SPA
        sta     coldphase
        rts

; ---- CPH_SPA: the pinned line, eight 2x glyphs a tick --------------------
cphspa: lda     #8
        sta     coldn
csp1:   ldx     coldline
        cpx     #2
        bcs     cspdone
        lda     spalo,x
        sta     TXT
        lda     spahi,x
        sta     TXT+1
        ldy     coldcp
        lda     (TXT),y
        bne     csp2
        inc     coldline                ; this line is finished
        ldx     coldline
        cpx     #2
        bcs     cspdone
        lda     #0
        sta     coldcp
        lda     spacol,x
        sta     coldcol
        jmp     csp1
csp2:   inc     coldcp
        cmp     #32
        bne     csp3
        inc     coldcol                 ; a space is two already-clear cells
        inc     coldcol
        jmp     csp4
csp3:   jsr     glysrc
        ldx     coldline
        lda     sparow,x
        sta     tmp4
        jsr     bmdst
        jsr     blit2x
        inc     coldcol
        inc     coldcol
csp4:   dec     coldn
        bne     csp1
        rts
cspdone:
        lda     #$3B                    ; lights on: bitmap mode, screen on
        sta     SPRCTRL1
        jsr     pagesetup
        lda     #CPH_DRAW
        sta     coldphase
        rts

; ---- CPH_DRAW: narration glyphs, three 4x blits a tick -------------------
cphdraw:
        lda     #3
        sta     coldn
        lda     coldpage                ; tmp5 = (page+1)*3, the line past
        clc                             ; this page's last
        adc     #1
        sta     tmp5
        asl     a
        adc     tmp5
        sta     tmp5
cdr1:   lda     coldline
        cmp     tmp5
        bcs     cdrdone
        ldx     coldline
        lda     linlo,x
        sta     TXT
        lda     linhi,x
        sta     TXT+1
        ldy     coldcp
        lda     (TXT),y
        bne     cdr2
        inc     coldline
        lda     coldline
        cmp     tmp5
        bcs     cdrdone
        tax
        lda     #0
        sta     coldcp
        lda     lincol,x
        sta     coldcol
        jmp     cdr1
cdr2:   inc     coldcp
        cmp     #32
        bne     cdr3
        lda     coldcol                 ; a space is four already-clear cells
        clc
        adc     #4
        sta     coldcol
        jmp     cdr4
cdr3:   jsr     glysrc
        ldx     coldline
        lda     linrow,x
        sta     tmp4
        jsr     bmdst
        jsr     blit4x
        lda     coldcol
        clc
        adc     #4
        sta     coldcol
cdr4:   dec     coldn
        bne     cdr1
        rts
cdrdone:
        lda     #PAGE_HOLD
        sta     coldtimer
        lda     #CPH_HOLD
        sta     coldphase
        rts

; ---- CPH_HOLD: the page sits; the timer or SPACE moves things on ---------
cphhold:
        dec     coldtimer
        bne     chd9
        lda     coldpage
        cmp     #COLDPAGES-1
        bcc     chd1
        lda     #CPX_OFF                ; the story is told: go to the title
        sta     coldphase
        rts
chd1:   inc     coldpage
        lda     #0
        sta     coldrow
        lda     #CPH_WIPE
        sta     coldphase
chd9:   rts

; ---- CPH_WIPE: clear the narration band (rows 0-19) for the next page ----
cphwipe:
        lda     #20
        sta     tmp2
        jsr     bmclr1
        jsr     bmclr1
        lda     coldrow
        cmp     #20
        bcc     cwp9
        jsr     pagesetup
        lda     #CPH_DRAW
        sta     coldphase
cwp9:   rts

; pagesetup -- point the draw cursor at the current page's first line
pagesetup:
        lda     coldpage
        asl     a
        adc     coldpage                ; *3; asl of a value this small
        sta     coldline                ; cannot carry
        lda     #0
        sta     coldcp
        ldx     coldline
        lda     lincol,x
        sta     coldcol
        rts

; ==========================================================================
; Exit: back to text mode, and the art the bitmap destroyed rebuilt
; ==========================================================================
cpxoff: lda     #$0B                    ; text mode, screen still off
        sta     SPRCTRL1
        inc     coldphase
        rts

cpxchr0:
        lda     #>CHARSET
        jsr     blank4pg
        inc     coldphase
        rts
cpxchr1:
        lda     #>(CHARSET+$0400)
        jsr     blank4pg
        inc     coldphase
        rts

; blank4pg -- A = page: zero one KB
blank4pg:
        sta     DST+1
        lda     #0
        sta     DST
        tay
        ldx     #4
:       sta     (DST),y
        iny
        bne     :-
        inc     DST+1
        dex
        bne     :-
        rts

cpxfont:
        lda     #<fontgly
        ldx     #>fontgly
        ldy     #1
        jsr     setglyphsrc
        lda     #<(fontgly_end - fontgly)
        ldx     #>(fontgly_end - fontgly)
        jsr     copyblock
        inc     coldphase
        rts

cpxpunct:
        lda     #<punctgly
        ldx     #>punctgly
        ldy     #33
        jsr     setglyphsrc
        lda     #<(punctgly_end - punctgly)
        ldx     #>(punctgly_end - punctgly)
        jsr     copyblock
        inc     coldphase
        rts

cpxgame:
        lda     #<gamegly
        ldx     #>gamegly
        ldy     #64
        jsr     setglyphsrc
        lda     #<(gamegly_end - gamegly)
        ldx     #>(gamegly_end - gamegly)
        jsr     copyblock
        inc     coldphase
        rts

cpxspr0:
        lda     #0
        ldx     #11
        jsr     sprfan
        inc     coldphase
        rts
cpxspr1:
        lda     #11
        ldx     #NSPRITES-11
        jsr     sprfan
        lda     #$FC                    ; sprites 2-7 multicolour, as ever
        sta     SPRMC
        inc     coldphase
        rts

cpxscr0:
        jsr     ssclr0
        inc     coldphase
        rts
cpxscr1:
        jsr     ssclr1
        inc     coldphase
        rts

cpxgo:  lda     #$1B                    ; text mode, screen on
        sta     SPRCTRL1
        jsr     titlereset              ; and the theme starts at the top
        lda     #ST_TITLE
        jmp     setstate

; ==========================================================================
; The blitters
; ==========================================================================

; bmclr1 -- clear bitmap cell row `coldrow` (320 bytes) if below tmp2
bmclr1: ldx     coldrow
        cpx     tmp2
        bcs     bmc9
        lda     bmlo,x
        sta     DST
        lda     bmhi,x
        sta     DST+1
        lda     #0
        tay
:       sta     (DST),y
        iny
        bne     :-
        inc     DST+1
        ldy     #63
:       sta     (DST),y
        dey
        bpl     :-
        inc     coldrow
bmc9:   rts

; glysrc -- A = screen code: SRC = its 8 bytes in chars.inc's ENGINE data.
; Never $3800: the bitmap has just been written over the installed charset.
glysrc: cmp     #33
        bcs     gsp
        sec
        sbc     #1
        asl     a                       ; codes 1-31: offset <= 240, one byte
        asl     a
        asl     a
        clc
        adc     #<fontgly
        sta     SRC
        lda     #>fontgly
        adc     #0
        sta     SRC+1
        rts
gsp:    sec
        sbc     #33
        asl     a
        asl     a
        asl     a
        clc
        adc     #<punctgly
        sta     SRC
        lda     #>punctgly
        adc     #0
        sta     SRC+1
        rts

; bmdst -- DST = bitmap address of cell (tmp4, coldcol):
; base + row*320 + col*8, from §1a's (y>>3)*320 + (x>>3)*8 with y&7 = 0.
bmdst:  lda     coldcol
        sta     DST
        lda     #0
        sta     DST+1
        asl     DST
        rol     DST+1
        asl     DST
        rol     DST+1
        asl     DST
        rol     DST+1
        ldx     tmp4
        lda     DST
        clc
        adc     bmlo,x
        sta     DST
        lda     DST+1
        adc     bmhi,x
        sta     DST+1
        rts

; EXP4ROW -- expand tmp0 (one source row) to four bitmap bytes at (DST),
; each written to four consecutive scanlines.  `off` is 0 for the upper
; half of the cell row, 4 for the lower.  Pixel-doubling twice is the
; 4-entry table: two source bits name one output byte.
.macro  EXP4ROW off
.repeat 4, j
        lda     #0
        asl     tmp0
        rol     a
        asl     tmp0
        rol     a
        tax
        lda     quadtab,x
        ldy     #off + j*8
        sta     (DST),y
        iny
        sta     (DST),y
        iny
        sta     (DST),y
        iny
        sta     (DST),y
.endrepeat
.endmacro

quadtab:
        .byte   $00, $0F, $F0, $FF
dobtab:                                 ; every bit doubled, for the 2x line
        .byte   $00, $03, $0C, $0F, $30, $33, $3C, $3F
        .byte   $C0, $C3, $CC, $CF, $F0, $F3, $FC, $FF

; blit4x -- the glyph at SRC, 32x32, to DST.  Two source rows fill one
; bitmap cell row (byte offsets 0-31), then DST steps down 320.
blit4x: lda     #0
        sta     tmp3
b4k:    ldy     tmp3
        lda     (SRC),y
        sta     tmp0
        EXP4ROW 0
        inc     tmp3
        ldy     tmp3
        lda     (SRC),y
        sta     tmp0
        EXP4ROW 4
        inc     tmp3
        lda     DST
        clc
        adc     #<320
        sta     DST
        lda     DST+1
        adc     #>320
        sta     DST+1
        lda     tmp3
        cmp     #8
        bcs     b4x
        jmp     b4k                     ; the unrolled expands are far away
b4x:    rts

; blit2x -- the glyph at SRC, 16x16, to DST.  Four source rows per cell row;
; each source byte becomes two bytes through the nibble-doubling table.
blit2x: lda     #0
        sta     tmp3
b2k:    lda     tmp3
        and     #3
        asl     a
        sta     tmp1                    ; y base = (source row & 3) * 2
        ldy     tmp3
        lda     (SRC),y
        sta     tmp0
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        tax
        ldy     tmp1
        lda     dobtab,x
        sta     (DST),y
        iny
        sta     (DST),y
        lda     tmp0
        and     #$0F
        tax
        lda     tmp1
        ora     #8                      ; the right-hand cell, one column on
        tay
        lda     dobtab,x
        sta     (DST),y
        iny
        sta     (DST),y
        inc     tmp3
        lda     tmp3
        cmp     #4
        bne     b2c
        lda     DST                     ; halfway: down one cell row
        clc
        adc     #<320
        sta     DST
        lda     DST+1
        adc     #>320
        sta     DST+1
b2c:    lda     tmp3
        cmp     #8
        bcc     b2k
        rts

; ---- tables ---------------------------------------------------------------
bmlo:   .repeat 25, i
        .byte   <(BITMAP + 320*i)
        .endrepeat
bmhi:   .repeat 25, i
        .byte   >(BITMAP + 320*i)
        .endrepeat

; The narration, wrapped at 10 and paged 3 lines at a time; each line's
; column centres it ((40 - 4*len) / 2), each page's rows are 2/7/12 -- the
; block sits above the vertical centre, per §1a.
linlo:  .byte   <t_cold1, <t_cold2, <t_cold3, <t_cold4
        .byte   <t_cold5, <t_cold6, <t_cold7, <t_cold8
        .byte   <t_cold9, <t_cold10, <t_cold11, <t_cold12
linhi:  .byte   >t_cold1, >t_cold2, >t_cold3, >t_cold4
        .byte   >t_cold5, >t_cold6, >t_cold7, >t_cold8
        .byte   >t_cold9, >t_cold10, >t_cold11, >t_cold12
linrow: .byte   2, 7, 12,  2, 7, 12,  2, 7, 12,  2, 7, 12
lincol: .byte   8, 2, 8,   12, 6, 0,  8, 6, 2,   8, 2, 4

; The pinned Spanish line, 2x on two rows, the same place on every page.
spalo:  .byte   <t_pulsa1, <t_pulsa2
spahi:  .byte   >t_pulsa1, >t_pulsa2
sparow: .byte   20, 22
spacol: .byte   2, 3
