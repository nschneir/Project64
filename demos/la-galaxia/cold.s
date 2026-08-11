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
; The 4x glyphs are not block-scaled.  Quadrupling a pixel into a 4x4 solid
; block turns every diagonal into a staircase with 4-pixel treads, which at
; this size is all the eye sees; so each glyph goes through one EPX (Scale2x)
; pass to 16x16 first, where a corner whose two orthogonal neighbours agree
; is cut, and only then is that doubled to 32x32.  A diagonal comes out as a
; joined-up 45-degree stroke drawn in 2x2 pixels instead of a flight of
; steps.  It is done in code, per glyph, per draw: a table of pre-smoothed
; 32x32 glyphs is 128 bytes each and there are forty of them, and the ENGINE
; segment has to end below BASIC at $A000.
;
; Layout, from §1a's arithmetic: 4x narration is 10 characters by 6 lines
; maximum, and the text is 100 characters in fourteen lines, so it pages --
; five pages, the first of four lines and the other four of three, each line
; centred ((40 - 4*len) / 2) and the block above the vertical centre.  A
; page's lines are pagefirst[page] up to pagefirst[page+1]: the pages are no
; longer a uniform three, so nothing multiplies by three any more.  Three-line
; pages sit on cell rows 2/7/12 and four-line pages on 0/5/10/15 -- a 4x glyph
; is four cell rows tall, so both stop at row 18 and clear the pinned Spanish
; line, which is at 2x on cell rows 21-22 on every page.  ANY key skips to the
; title at any point (anykey_edge, from player.s); the timer advances the
; pages otherwise, and after the last page the state leaves for the title on
; its own -- the attract loop's cycle is cold open -> title -> (game) -> game
; over -> cold open.  Nothing on the screen names the key: the pinned line is
; the story's last words rather than an instruction, which is exactly why the
; skip has to answer to every key and not to a documented one.

        .segment "ENGINE"

BITMAP  = $2000

; entry phases
CPH_CLR  = 0                    ; clear the whole bitmap, 2 cell rows a tick
CPH_COL  = 1                    ; colour nibbles into the screen matrix
CPH_SPA  = 2                    ; the pinned Spanish line, 2x, screen still off
                                ; -- one row, so it is three ticks, not five
CPH_DRAW = 3                    ; narration glyphs at 4x, GLYPHTICK a tick
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

COLDPAGES = 5
PAGE_HOLD = 240                 ; four seconds a page at 60 Hz
; Glyphs per CPH_DRAW tick.  A smoothed 4x blit costs ~5,500 cycles against
; the old block-scaled ~2,000, so three a tick no longer fits an NTSC frame
; and tick_overrun would count it.  Two is what the frame holds; the reveal
; is slower and reads as the typewriter it always was.
GLYPHTICK = 2

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

cnorm:  ; ANY key leaves for the title from ANY point, including part-way
        ; through the first page -- but once the exit is running, let it run.
        ; anykey_edge, not input_edge: this screen answers to keys the game
        ; has no mapping for, and it is the edge because the game over walks
        ; back in here with whatever the player was holding still held.
        lda     coldphase
        cmp     #CPX_OFF
        bcs     cdisp
        lda     anykey_edge
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
; The bound is SPALINES rather than a literal because the pinned text has
; been one row and two rows and may be either again; the loop below is the
; same either way.
SPALINES = 1
cphspa: lda     #8
        sta     coldn
csp1:   ldx     coldline
        cpx     #SPALINES
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
        cpx     #SPALINES
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

; ---- CPH_DRAW: narration glyphs, GLYPHTICK 4x blits a tick ---------------
cphdraw:
        lda     #GLYPHTICK
        sta     coldn
        ldx     coldpage                ; tmp5 = the line past this page's
        lda     pagefirst+1,x           ; last, straight out of the table
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
        ldx     coldpage
        lda     pagefirst,x
        sta     coldline
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

dobtab:                                 ; every bit doubled: the 2x line's
        .byte   $00, $03, $0C, $0F, $30, $33, $3C, $3F
        .byte   $C0, $C3, $CC, $CF, $F0, $F3, $FC, $FF

; What the smoother needs on top of the five zero page bytes la-galaxia.s
; names for it.  epxD and epxE0 are deliberately the same byte: the row below
; is spent the moment the corner masks are built, and one more scratch
; location for it would be one the game has not got.
epxA    = tmp0                          ; the row above, carried down the glyph
epxD    = tmp1                          ; the row below
epxE0   = tmp1                          ; ... then the left/top output bits
epxE1   = tmp2                          ; ... and the right/bottom ones

; ---- blit4x -- the glyph at SRC, smoothed, 32x32, to DST -----------------
; EPX/Scale2x in 1bpp, a whole source row at a time.  For pixel P with
; neighbours A (up), B (right), C (left), D (down) the 2x2 output is
;
;   E0 = (C==A && C!=D && A!=B) ? A : P     E1 = (A==B && A!=C && B!=D) ? B : P
;   E2 = (D==C && D!=B && C!=A) ? C : P     E3 = (B==D && B!=A && D!=C) ? D : P
;
; With one bit per pixel those four conditions collapse into two masks that
; cannot both be set: SX = ~((A^C)|(B^D)) & (A^B) says the up/left and
; down/right corners are the ones to cut, SY = ~((A^B)|(C^D)) & (A^C) says it
; is the other diagonal.  Then E0 = P^(SX&(A^P)), E1 = P^(SY&(A^P)),
; E2 = P^(SY&(C^P)), E3 = P^(SX&(B^P)) -- eight bits at a time, no branches
; and no per-pixel loop.  C and B are the row shifted one bit each way, so a
; neighbour off the edge of the glyph shifts in as background, which is what
; §1a asks for; A and D are the rows either side, zero past the ends.
;
; That gives 16x16.  The doubling to 32x32 happens in the same pass:
; epxemit's dobtab entry is indexed by two pixels' worth of E0/E1 bits, so
; one table lookup writes four output pixels, and each 16x16 row is written
; to two scanlines.  Two source rows fill one bitmap cell row (byte offsets
; 0-31), then DST steps down 320.
blit4x: lda     #0
        sta     tmp3
        sta     epxA                    ; nothing above the first row
b4k:    ldy     tmp3
        lda     (SRC),y
        sta     epxP
        lda     #0                      ; ... and nothing below the last
        iny
        cpy     #8
        bcs     :+
        lda     (SRC),y
:       sta     epxD
        lda     epxP
        lsr     a
        sta     epxC
        lda     epxP
        asl     a
        sta     epxB
        lda     epxA                    ; X0 = A^C, parked where SY will go
        eor     epxC
        sta     epxSY
        lda     epxB                    ; SX = ~(X0 | (B^D)) & (A^B)
        eor     epxD
        ora     epxSY
        eor     #$FF
        sta     epxSX
        lda     epxA
        eor     epxB                    ; X2 = A^B, wanted by both masks
        pha
        and     epxSX
        sta     epxSX
        lda     epxC
        eor     epxD                    ; C^D; D is spent from here
        sta     epxD
        pla
        ora     epxD
        eor     #$FF
        and     epxSY                   ; SY = ~(X2 | (C^D)) & X0
        sta     epxSY
        lda     epxA                    ; A^P, wanted by E1 and then E0
        eor     epxP
        sta     epxD
        and     epxSY
        eor     epxP
        sta     epxE1
        lda     epxD
        and     epxSX
        eor     epxP
        sta     epxE0
        lda     tmp3                    ; even source rows fill scanlines 0-3
        and     #1                      ; of the cell row, odd rows 4-7
        asl     a
        asl     a
        sta     tmp4
        tay
        jsr     epxemit
        lda     epxC                    ; E2 = P ^ (SY & (C^P))
        eor     epxP
        and     epxSY
        eor     epxP
        sta     epxE0
        lda     epxB                    ; E3 = P ^ (SX & (B^P))
        eor     epxP
        and     epxSX
        eor     epxP
        sta     epxE1
        lda     tmp4
        ora     #2
        tay
        jsr     epxemit
        lda     epxP                    ; this row is the next one's "above"
        sta     epxA
        inc     tmp3
        lda     tmp3
        and     #1
        bne     b4c
        lda     DST                     ; two source rows finish a cell row
        clc
        adc     #<320
        sta     DST
        lda     DST+1
        adc     #>320
        sta     DST+1
b4c:    lda     tmp3
        cmp     #8
        bcs     b4x
        jmp     b4k                     ; the row body is far away
b4x:    rts

; epxemit -- Y = the first byte offset: four bitmap bytes from E0/E1, each
; written to two scanlines and stepping one cell column (8 bytes) along.
; Four bits -- two pixels of E0 interleaved with two of E1 -- index dobtab,
; which doubles each of them, so one lookup is four output pixels.  Y ends at
; base+32 and the bases are 0, 2, 4 and 6, so `cpy #32` is the column count.
epxemit:
        lda     #0
        asl     epxE0
        rol     a
        asl     epxE1
        rol     a
        asl     epxE0
        rol     a
        asl     epxE1
        rol     a
        tax
        lda     dobtab,x
        sta     (DST),y
        iny
        sta     (DST),y
        tya
        clc
        adc     #7
        tay
        cpy     #32
        bcc     epxemit
        rts

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

; The narration, wrapped at 10 characters and paged where the story pauses.
; Each line's column centres it ((40 - 4*len) / 2); a three-line page sits on
; cell rows 2/7/12 and the one four-line page on 0/5/10/15, which puts the
; block above the vertical centre and stops clear of the pinned line, per
; §1a.  pagefirst has COLDPAGES+1 entries: page p owns lines pagefirst[p] up
; to pagefirst[p+1], so a page is whatever length the wrap made it.
;
;   1  IN THE / BACK OF A / LONG / SHUTTERED    (four: "IN THE BACK" is 11
;   2  MEXICO / CITY / ARCADE,                   characters and 4x fits ten)
;   3  BEHIND THE / BROKEN
;   4  PINBALL / MACHINES,
;   5  SITS A / FORGOTTEN / RELIC...
pagefirst:
        .byte   0, 4, 7, 9, 11, 14
linlo:  .byte   <t_cold1, <t_cold2, <t_cold3, <t_cold4
        .byte   <t_cold5, <t_cold6, <t_cold7, <t_cold8
        .byte   <t_cold9, <t_cold10, <t_cold11, <t_cold12
        .byte   <t_cold13, <t_cold14
linhi:  .byte   >t_cold1, >t_cold2, >t_cold3, >t_cold4
        .byte   >t_cold5, >t_cold6, >t_cold7, >t_cold8
        .byte   >t_cold9, >t_cold10, >t_cold11, >t_cold12
        .byte   >t_cold13, >t_cold14
linrow: .byte   0, 5, 10, 15,  2, 7, 12,  2, 7,  2, 7,  2, 7, 12
lincol: .byte   8, 2, 12, 2,   8, 12, 6,  0, 8,   6, 2,  8, 2, 4

; The pinned Spanish line: one 2x row, the same place on every page.
; "COMIENZA TU VIAJE..." is twenty glyphs and 2x is two columns each, so it
; fills the row exactly -- column 0 to column 39, the last byte at offset 319
; of the row.  Row 21, not 20: a 2x glyph is two cell rows tall, so one line
; at 21 sits centred in the 20-24 band the colour pass gives it, where 20
; would pin it to the top of that band with three empty rows underneath.
spalo:  .byte   <t_pulsa1
spahi:  .byte   >t_pulsa1
sparow: .byte   21
spacol: .byte   0
