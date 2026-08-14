; staff.s -- the grand staff and the column renderer.
;
; drawcol renders ONE score column into ONE screen column.  It is the whole
; display: drawscreen is 40 calls to it, and the scroll is one call to it per
; column shift.  Nothing carries between columns, so the picture is a pure
; function of `shifts` -- which is what makes it reproducible to the frame and
; lets a test stage any column it likes.
;
; THE GRID (SPEC.md section 6).  Two character columns per sixteenth note:
; the first is the accidental / bar-line slot, the second the note-head slot.
; Two columns is what buys an accidental a cell of its own beside the head it
; modifies; at one column per sixteenth it could only sit in the previous
; sixteenth's head cell, which collides exactly when accidentals are most
; likely -- a repeated letter name, C then C sharp.
;
;   score column       content
;   0, 3..SC0-1        blank staff (the lead-in)
;   1..2               treble and bass clefs
;   SC0 + 2k           accidental / bar-line slot of sixteenth k
;   SC0 + 2k + 1       head slot of sixteenth k
;
; NO KEY SIGNATURE.  Every altered note carries its own accidental, every
; time.  That is a departure from engraving convention and it is deliberate:
; a key signature is printed once at the head of a system, this score has no
; systems, and it would scroll off leaving the reader to infer flats from a
; symbol no longer on screen.  The consequence here is that a natural sign is
; never drawn -- an unmarked head IS the natural.

        .segment "CODE"

; --------------------------------------------------------------------------
; Row tables.  Band row i is screen row BANDTOP+i.
; --------------------------------------------------------------------------
rowlo:  .repeat BANDROWS, i
        .byte   <(SCREEN + (BANDTOP + i) * 40)
        .endrepeat
rowhi:  .repeat BANDROWS, i
        .byte   >(SCREEN + (BANDTOP + i) * 40)
        .endrepeat
crowlo: .repeat BANDROWS, i
        .byte   <(COLRAM + (BANDTOP + i) * 40)
        .endrepeat
crowhi: .repeat BANDROWS, i
        .byte   >(COLRAM + (BANDTOP + i) * 40)
        .endrepeat

; The staff itself.  TREB is the band row of the treble staff's top line and
; BASSR the bass staff's; between them, one row down from the treble's bottom
; line, is where middle C sits on its own ledger, exactly as printed.
TREB    = STAFFTOP - BANDTOP     ; band row of the treble top line (F5)
BASSR   = TREB + 6               ; band row of the bass top line (A3)
BARTOP  = TREB                   ; a bar line joins the two staves, treble
BARBOT  = BASSR + 4              ;   top line to bass bottom line

bgcode: .repeat BANDROWS, i
        .if (((i >= TREB) && (i <= TREB + 4)) || ((i >= BASSR) && (i <= BASSR + 4)))
        .byte   GLINE
        .else
        .byte   GBLANK
        .endif
        .endrepeat
rowline: .repeat BANDROWS, i
        .if (((i >= TREB) && (i <= TREB + 4)) || ((i >= BASSR) && (i <= BASSR + 4)))
        .byte   1
        .else
        .byte   0
        .endif
        .endrepeat

; Which ledger lines a note at ladder position p needs, as a bitmask over the
; five ledger positions.  A note in the first space beyond a staff needs no
; ledger (F2 below the bass, G5 above the treble); the first space beyond a
; ledger needs that ledger under it.
;              bit0 = p1  C6      bit1 = p3  A5      bit2 = p15 C4
;              bit3 = p27 E2      bit4 = p29 C2
ledgmask:
        .byte   3, 3, 2, 2       ; p0  D6, p1  C6, p2  B5, p3  A5
        .byte   0, 0, 0, 0       ; p4  G5, p5  F5, p6  E5, p7  D5
        .byte   0, 0, 0, 0       ; p8  C5, p9  B4, p10 A4, p11 G4
        .byte   0, 0, 0, 4       ; p12 F4, p13 E4, p14 D4, p15 C4
        .byte   0, 0, 0, 0       ; p16 B3, p17 A3, p18 G3, p19 F3
        .byte   0, 0, 0, 0       ; p20 E3, p21 D3, p22 C3, p23 B2
        .byte   0, 0, 0, 8       ; p24 A2, p25 G2, p26 F2, p27 E2
        .byte   8, 24            ; p28 D2, p29 C2
ledgbit: .byte  1, 2, 4, 8, 16
; The band row each ledger position lives in: p>>1 through the ladder map.
ledgrow: .byte  LADTOP + 0 - BANDTOP, LADTOP + 1 - BANDTOP
         .byte  LADTOP + 7 - BANDTOP
         .byte  LADTOP + 13 - BANDTOP, LADTOP + 14 - BANDTOP

hbit:   .byte   1, 2            ; occupancy bit for half 0 (upper), 1 (lower)

; --------------------------------------------------------------------------
; drawscreen -- score columns 0..39 into screen columns 0..39.  Called once,
; from init, with shifts still 0.
; --------------------------------------------------------------------------
drawscreen:
        lda     #0
        sta     dscr
dsloop: lda     dscr
        sta     dcol
        lda     #0
        sta     dcol+1
        jsr     drawcol
        inc     dscr
        lda     dscr
        cmp     #40
        bne     dsloop
        rts

; --------------------------------------------------------------------------
; drawcol -- render score column `dcol` into screen column `dscr`.
; --------------------------------------------------------------------------
drawcol:
        jsr     dcbg
        jsr     dcclef
        jsr     dcscore
        ; fall through to the blit

; Stage to colbuf/colclr first and blit once, rather than read-modify-write
; the screen: two voices landing in one cell then combine in RAM, where the
; occupancy bits can see each other.
dcblit:
        ldx     #0
dcbl:   lda     rowlo,x
        sta     ptr
        lda     rowhi,x
        sta     ptr+1
        lda     crowlo,x
        sta     cptr
        lda     crowhi,x
        sta     cptr+1
        ldy     dscr
        lda     colbuf,x
        sta     (ptr),y
        lda     colclr,x
        sta     (cptr),y
        inx
        cpx     #BANDROWS
        bne     dcbl
        rts

; ---- background ----------------------------------------------------------
dcbg:   ldx     #BANDROWS - 1
dcbgl:  lda     bgcode,x
        sta     colbuf,x
        lda     #CWHITE
        sta     colclr,x
        lda     rowline,x
        sta     curline,x
        lda     #0
        sta     colocc,x
        sta     colhol,x
        dex
        bpl     dcbgl
        lda     #0
        sta     ledgset
        rts

; ---- clefs ---------------------------------------------------------------
; Drawn from custom characters at the head of the score, columns 1 and 2.
; They stand still for the whole HOLD and then scroll away with the music,
; the way a printed clef leaves your field of view as your eye moves along
; the system.  The hold exists because they do not last otherwise: measured
; on the first build, at frame 30 the score had already advanced seven
; columns and both clefs were off the left edge.
dcclef: lda     dcol+1
        bne     dcclno
        lda     dcol
        cmp     #1
        beq     dccl0
        cmp     #2
        beq     dccl1
dcclno: rts
dccl0:  lda     #0
        jmp     putclef
dccl1:  lda     #1
        ; fall through

putclef:                        ; A = clef column, 0 or 1
        sta     tmp0
        asl     a
        asl     a
        clc
        adc     tmp0            ; col * 5
        clc
        adc     #GTREB
        ldx     #TREB
pctl:   sta     colbuf,x
        clc
        adc     #1
        inx
        cpx     #TREB + 5
        bne     pctl
        lda     tmp0
        asl     a
        clc
        adc     tmp0            ; col * 3
        clc
        adc     #GBASS
        ldx     #BASSR
pcbl:   sta     colbuf,x
        clc
        adc     #1
        inx
        cpx     #BASSR + 3
        bne     pcbl
        rts

; ---- the score -----------------------------------------------------------
dcscore:
        lda     dcol
        sec
        sbc     #<SC0
        sta     tmp0
        lda     dcol+1
        sbc     #>SC0
        sta     tmp1
        bcs     dcsin
        rts                     ; before the music: staff only
dcsin:  lda     tmp0
        and     #1
        sta     tmp2            ; 0 = accidental slot, 1 = head slot
        lsr     tmp1
        ror     tmp0            ; k = offset >> 1, for either slot
        lda     tmp1
        cmp     #>NSIX
        bcc     dcsk
        bne     dcsout
        lda     tmp0
        cmp     #<NSIX
        bcs     dcsout
dcsk:   lda     tmp0
        sta     dk
        sta     rendk
        lda     tmp1
        sta     dk+1
        sta     rendk+1
        jsr     fetchnotes
        lda     tmp2
        beq :+
        jmp dchead
:
        jmp     dcacc
dcsout: rts

; --------------------------------------------------------------------------
; fetchnotes -- read this sixteenth's three note bytes and decode each one
; ONCE, into the nb/np/nhalf/ni/nacc/nhol/nmidi arrays.  The three voice
; arrays are one contiguous 1,488-byte block, so the voice stride is a
; constant add on a pointer built once rather than three separate walks.
;
; Called by musfetch too: the sequencer and the renderer decode the same byte
; through the same routine, which is what makes the pitch heard and the head
; drawn incapable of disagreeing.
; --------------------------------------------------------------------------
fetchnotes:
        lda     #<notes
        clc
        adc     dk
        sta     ptr
        lda     #>notes
        adc     dk+1
        sta     ptr+1
        ldx     #0
fnl:    ldy     #0
        lda     (ptr),y
        sta     nb,x
        beq     fnnx
        cmp     #$FF
        beq     fnnx
        jsr     decode
fnnx:   lda     ptr
        clc
        adc     #<NSIX
        sta     ptr
        lda     ptr+1
        adc     #>NSIX
        sta     ptr+1
        inx
        cpx     #3
        bne     fnl
        rts

; decode -- A = a note byte, X = voice.  Preserves X.
; Byte layout: $00 rest, $FF hold, else bits0-4 = p+1, bits5-6 = accidental,
; bit7 = hollow head.  The sounding pitch is posmidi[p] adjusted by the
; accidental, so the picture and the sound are the same byte read two ways.
decode: stx     tmpv
        sta     tmp0
        and     #31
        sec
        sbc     #1
        sta     np,x
        lsr     a
        clc
        adc     #(LADTOP - BANDTOP)
        sta     ni,x
        lda     np,x
        and     #1
        sta     nhalf,x
        lda     tmp0
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        and     #3
        sta     nacc,x
        lda     tmp0
        rol     a               ; bit 7 into carry (A is discarded)
        lda     #0
        rol     a
        sta     nhol,x
        ldy     np,x
        lda     posmidi,y
        ldy     nacc,x
        cpy     #1
        bne     decflat
        clc
        adc     #1
        jmp     decdone
decflat:
        cpy     #2
        bne     decdone
        sec
        sbc     #1
decdone:
        ldx     tmpv
        sta     nmidi,x
        rts

; ---- head slot -----------------------------------------------------------
dchead:
        jsr     dcledg          ; ledgers first: they decide `online`, which
                                ;   decides which head glyph each cell takes
        ldx     #0
dchv:   stx     tmpv
        lda     nb,x
        beq     dchnx
        cmp     #$FF
        beq     dchnx
        ldy     ni,x
        sty     tmp1            ; band row
        lda     nhalf,x
        tay
        lda     hbit,y
        sta     tmp0            ; this half's occupancy bit
        ldx     tmp1
        and     colocc,x
        beq     dchok
        inc     collide         ; this half of this cell is already taken.
        bne     dchnx           ;   The lower-numbered voice keeps it -- the
        inc     collide+1       ;   subject never loses its colour -- and the
        jmp     dchnx           ;   loss is counted, not hidden.
dchok:  lda     colocc,x
        ora     tmp0
        sta     colocc,x
        cmp     tmp0
        bne     dchhol          ; something was already here: keep its colour
        ldy     tmpv
        lda     nmidi,y         ; there is no LDY abs,Y on this CPU -- go
        tay                     ;   through A
        lda     midicol - 33,y
        sta     colclr,x
dchhol: ldy     tmpv
        lda     nhol,y
        beq     dchmk
        lda     colhol,x
        ora     tmp0
        sta     colhol,x
dchmk:  jsr     mkhead          ; X is still the band row
dchnx:  ldx     tmpv
        inx
        cpx     #3
        bne     dchv
        rts

; mkhead -- X = band row.  Builds the glyph from the cell's occupancy, so a
; third voice arriving at an already-doubled cell cannot produce a nonsense
; code: the glyph is a function of state, not of arrival order.
mkhead: lda     colocc,x
        and     #3
        cmp     #3
        beq     mkboth
        lsr     a               ; 1 -> half 0 (upper), 2 -> half 1 (lower)
        sta     tmp2
        lda     colhol,x
        and     #3
        beq     mksolid
        lda     #2              ; hollow << 1
        bne     mkjoin
mksolid:
        lda     #0
mkjoin: ora     tmp2
        sta     tmp2
        lda     curline,x
        asl     a
        asl     a               ; online << 2
        ora     tmp2
        clc
        adc     #GHEAD1
        sta     colbuf,x
        rts
mkboth: lda     colhol,x
        and     #3              ; bit0 upper hollow, bit1 lower hollow, which
                                ;   IS (lowerhollow<<1) + upperhollow
        sta     tmp2
        lda     curline,x
        asl     a
        asl     a
        ora     tmp2
        clc
        adc     #GHEAD2
        sta     colbuf,x
        rts

; dcledg -- collect every ledger line this column's heads need, then light
; them.  Ledgers are drawn in the head slot only: one in the accidental slot
; too would make the line 16 pixels long under a 6-pixel head.
dcledg: ldx     #0
dclv:   lda     nb,x
        beq     dclnx
        cmp     #$FF
        beq     dclnx
        ldy     np,x
        lda     ledgmask,y
        ora     ledgset
        sta     ledgset
dclnx:  inx
        cpx     #3
        bne     dclv
        ldx     #0
dclap:  lda     ledgbit,x
        and     ledgset
        beq     dclas
        ldy     ledgrow,x
        lda     #1
        sta     curline,y
        lda     colbuf,y
        cmp     #GBLANK
        bne     dclas
        lda     #GLINE
        sta     colbuf,y
dclas:  inx
        cpx     #5
        bne     dclap
        rts

; ---- accidental / bar-line slot ------------------------------------------
; A bar line fills the column from the treble top line to the bass bottom
; line.  Where a voice needs an accidental in that same column the accidental
; takes that one cell instead, leaving a notch in the rule -- which is close
; to what engraving does anyway, since an accidental sits just after the bar
; line.
dcacc:  lda     dk
        and     #15             ; 16 divides 256, so the low byte decides
        bne     dcanobar
        ldx     #BARTOP
dcabar: lda     curline,x
        clc
        adc     #GBAR
        sta     colbuf,x
        inx
        cpx     #BARBOT + 1
        bne     dcabar
dcanobar:
        ldx     #0
dcav:   stx     tmpv
        lda     nb,x
        beq     dcanx
        cmp     #$FF
        beq     dcanx
        lda     nacc,x
        beq     dcanx           ; unmarked head, so no symbol: with no key
                                ;   signature the natural needs no sign
        ldy     ni,x
        sty     tmp1
        ldx     tmp1
        lda     colocc,x
        and     #4
        beq     dcaok
        inc     collide
        bne     dcanx
        inc     collide+1
        jmp     dcanx
dcaok:  lda     colocc,x
        ora     #4
        sta     colocc,x
        ldy     tmpv
        lda     nhalf,y
        asl     a               ; half << 1
        sta     tmp2
        lda     curline,x
        asl     a
        asl     a               ; online << 2
        ora     tmp2
        sta     tmp2
        ldy     tmpv
        lda     nacc,y
        lsr     a               ; 1 sharp -> 0, 2 flat -> 1
        ora     tmp2
        clc
        adc     #GACC
        sta     colbuf,x
        ldy     tmpv
        lda     nmidi,y         ; there is no LDY abs,Y on this CPU -- go
        tay                     ;   through A
        lda     midicol - 33,y
        sta     colclr,x
dcanx:  ldx     tmpv
        inx
        cpx     #3
        bne     dcav
        rts
