; raster.s — the rasteriser: span fill, signed multiply, vertex transform,
; edge build, active-edge table, even-odd scanline fill.
;
; No ROM call happens anywhere in this file.  SPEC.md section 5 is the
; contract.

        .segment "CODE"

; ==========================================================================
; spanfill — paint one horizontal span of the bitmap and stamp the section's
; palette onto exactly the cells it covers.
;
;   in:  spy    scanline 0..199
;        spxa   first multicolour pixel, 0..159
;        spxb   one past the last, spxa < spxb <= 160
;        sh_pat dither pattern 0..7
;        sh_ink 1..3
;   out: lsbytes advanced by the number of cells touched
;   clobbers A/X/Y and the claimed zero page
;
; Bytes, not pixels: whole cells along the span through a mask, with the two
; end cells masked further by leftmask/rightmask.  The row address comes from
; a table, so there is no multiply in here (SPEC.md 5.6).
; ==========================================================================

spanfill:
        ; ---- the dither row for this scanline --------------------------
        lda     sh_pat
        asl     a
        asl     a
        asl     a
        asl     a               ; pattern * 16
        sta     sfm             ; borrow sfm as the pattern base
        lda     spy
        and     #7
        asl     a               ; (y & 7) * 2
        clc
        adc     sfm
        tax
        lda     dither,x
        sta     dm0
        lda     dither+1,x
        sta     dm1
        ldx     sh_ink
        lda     inkbits,x
        sta     sfink

        ; ---- the unmasked (middle-cell) AND/OR pair, precomputed -------
        lda     dm0
        eor     #$ff
        sta     ANDM0
        lda     dm0
        and     sfink
        sta     ORB0
        lda     dm1
        eor     #$ff
        sta     ANDM1
        lda     dm1
        and     sfink
        sta     ORB1

        ; ---- cell range -----------------------------------------------
        lda     spxa
        lsr     a
        lsr     a
        sta     spca
        lda     spxb
        sec
        sbc     #1
        sta     sfpb            ; the last painted pixel
        lsr     a
        lsr     a
        sta     spcb
        clc
        adc     #1
        sta     spcb1

        ; ---- pointers --------------------------------------------------
        ldx     spy
        lda     rowaddrl,x
        sta     BMPPTR
        lda     rowaddrh,x
        sta     BMPPTR+1
        ldx     spca
        lda     BMPPTR
        clc
        adc     xoff8l,x
        sta     BMPPTR
        lda     BMPPTR+1
        adc     xoff8h,x
        sta     BMPPTR+1
        lda     spy
        lsr     a
        lsr     a
        lsr     a
        tax                     ; cell row
        lda     attrscrl,x
        sta     SCRPTR
        lda     attrscrh,x
        sta     SCRPTR+1
        lda     attrcoll,x
        sta     COLPTR
        lda     attrcolh,x
        sta     COLPTR+1

        ; ---- edge masks -------------------------------------------------
        lda     spxa
        and     #3
        tax
        lda     leftmask,x
        sta     sflm
        lda     sfpb
        and     #3
        tax
        lda     rightmask,x
        sta     sfrm

        lda     spca
        and     #1
        sta     cpar

        ; ---- one cell, or first / middle / last ------------------------
        lda     spca
        cmp     spcb
        bne     sfmulti
        lda     sflm
        and     sfrm
        jsr     sfcell
        jmp     sfattr

sfmulti:
        lda     sflm
        jsr     sfcell          ; first cell, left-masked
        lda     spcb
        sec
        sbc     spca
        sec
        sbc     #1              ; middle cell count
        beq     sflast
        tax
        ldy     #0              ; (BMPPTR),y indexing — Y stays 0 throughout
        lda     cpar
        bne     sfmodd
sfmeven:
        lda     (BMPPTR),y
        and     ANDM0
        ora     ORB0
        sta     (BMPPTR),y
        lda     BMPPTR
        clc
        adc     #8
        sta     BMPPTR
        bcc     :+
        inc     BMPPTR+1
:       dex
        beq     sfmdone
sfmodd:
        lda     (BMPPTR),y
        and     ANDM1
        ora     ORB1
        sta     (BMPPTR),y
        lda     BMPPTR
        clc
        adc     #8
        sta     BMPPTR
        bcc     :+
        inc     BMPPTR+1
:       dex
        bne     sfmeven
sfmdone:
        lda     spcb            ; the last cell's parity is its column's
        and     #1
        sta     cpar
sflast: lda     sfrm
        jsr     sfcell

        ; ---- stamp the palette on exactly these cells -------------------
        ; Once per cell, not once per cell per row.  A shape's scan visits a
        ; cell row for eight consecutive scanlines and never comes back, so a
        ; per-cell-row "already stamped" flag makes the eight visits into one
        ; without ever stamping a cell the shape does not cover.  `stampcr`
        ; is invalidated at the start of every drawshape, so the next shape
        ; re-claims the same cells with whatever palette is current then.
sfattr: lda     spy
        lsr     a
        lsr     a
        lsr     a
        cmp     stampcr
        beq     sfa0
        sta     stampcr
        lda     #0
        ldx     #39
sfaz:   sta     stamped,x
        dex
        bpl     sfaz
sfa0:   ldy     spca
        ldx     spca
sfa1:   lda     stamped,x
        bne     sfa2
        lda     #1
        sta     stamped,x
        lda     palscr
        sta     (SCRPTR),y
        lda     palcol
        sta     (COLPTR),y
sfa2:   inx
        iny
        cpy     spcb1
        bne     sfa1
        lda     spcb1           ; lsbytes += cells touched
        sec
        sbc     spca
        clc
        adc     lsbytes
        sta     lsbytes
        bcc     :+
        inc     lsbytes+1
:       rts

; --------------------------------------------------------------------------
; sfcell — paint one cell through (dither mask for cpar) AND (A), then
; advance BMPPTR by 8 and flip cpar.  Used for the two masked end cells only;
; the middle runs the unrolled loop above.
; --------------------------------------------------------------------------

sfcell: ldx     cpar
        bne     sfcodd
        and     dm0
        jmp     sfcgo
sfcodd: and     dm1
sfcgo:  beq     sfcadv          ; nothing of this cell is painted
        sta     sfm
        eor     #$ff
        sta     sfand
        lda     sfm
        and     sfink
        sta     sfor
        ldy     #0
        lda     (BMPPTR),y
        and     sfand
        ora     sfor
        sta     (BMPPTR),y
sfcadv: lda     cpar
        eor     #1
        sta     cpar
        lda     BMPPTR
        clc
        adc     #8
        sta     BMPPTR
        bcc     :+
        inc     BMPPTR+1
:       rts

; ==========================================================================
; smul — signed 8 x 8 -> 16 multiply.
;
;   in:  MULA, MULB   signed bytes
;   out: MULR/MULR+1  signed 16-bit product
;
; Magnitudes through a shift-add, then one sign fixup.  This is the hot
; routine of the transform (four calls per vertex), so its cost is measured
; with `c64 profile`, not guessed.
; ==========================================================================

; Quarter squares: a*b = f(a+b) - f(a-b) where f(x) = floor(x*x/4), exactly,
; for integers.  Two table lookups and a 16-bit subtract replace eight
; shift-add rounds — measured at 330 cycles for the shift-add version against
; a 16-vertex transform that calls this 64 times.
;
; The tables are GENERATED AT STARTUP into $C000-$C1FF (qsgen), the 4 KB
; BASIC never touches.  They are not in the .prg: with the bitmap at $2000
; the program has under 100 bytes of headroom, and 512 bytes of table would
; not fit.  The VIC-II cannot see $C000, which does not matter — nothing but
; the CPU reads them.
;
; Operand magnitudes are at most 127 (the sin table's amplitude, and every
; size and unit vertex is smaller), so a+b never exceeds 254 and the index
; always lands in the table.

; umul — UNSIGNED 8 x 8 -> 16.  in: MULA, MULB.  out: MULR/MULR+1.
;
; a + b reaches 510 for two full-range bytes, so the tables carry 512 entries
; and the sum's carry selects the upper half.  |a - b| never exceeds 255, so
; the subtrahend always comes from the lower half.
umul:   lda     MULA
        clc
        adc     MULB
        tax
        bcc     umlo
        lda     QSL+256,x
        sta     MULR
        lda     QSH+256,x
        sta     MULR+1
        jmp     umd
umlo:   lda     QSL,x
        sta     MULR
        lda     QSH,x
        sta     MULR+1
umd:    lda     MULA            ; minus f(| a - b |); f is even
        sec
        sbc     MULB
        bcs     :+
        eor     #$ff
        clc
        adc     #1
:       tax
        lda     MULR
        sec
        sbc     QSL,x
        sta     MULR
        lda     MULR+1
        sbc     QSH,x
        sta     MULR+1
        rts

; smul — SIGNED, by magnitudes through umul plus one sign fixup.
; MULA and MULB are left holding their magnitudes; no caller reuses them.
smul:   lda     MULA
        bpl     smpa
        eor     #$ff
        clc
        adc     #1
        ldx     #1
        stx     smSgn
        jmp     sma2
smpa:   ldx     #0
        stx     smSgn
sma2:   sta     MULA
        lda     MULB
        bpl     smpb
        eor     #$ff
        clc
        adc     #1
        sta     MULB
        lda     smSgn
        eor     #1
        sta     smSgn
        jmp     smgo
smpb:   sta     MULB
smgo:   jsr     umul
        lda     smSgn
        beq     smdone
        lda     #0              ; negate the 16-bit product
        sec
        sbc     MULR
        sta     MULR
        lda     #0
        sbc     MULR+1
        sta     MULR+1
smdone: rts

; --------------------------------------------------------------------------
; qsgen — build the 512-entry quarter-square tables, once, at startup.
;
; f(x) = floor(x*x/4) is accumulated by its own first difference,
; f(x+1) - f(x) = floor((x+1)/2), which steps up by one on every odd index.
; So the generator needs no multiply either — and accumulating f directly
; rather than x*x keeps everything inside 16 bits (x*x would overflow at
; x = 256, f(511) = 65280 does not).
; --------------------------------------------------------------------------

qsgen:  lda     #0
        sta     flo
        sta     fhi
        sta     dlt
        sta     qspg
        lda     #<QSL
        sta     qs1+1
        lda     #>QSL
        sta     qs1+2
        lda     #<QSH
        sta     qs2+1
        lda     #>QSH
        sta     qs2+2
        ldx     #0
qsl:    lda     flo
qs1:    sta     $ffff,x         ; self-modified: QSL, then QSL+256
        lda     fhi
qs2:    sta     $ffff,x
        txa                     ; index parity == X parity, 256 being even
        and     #1
        beq     qsev
        inc     dlt
qsev:   lda     flo
        clc
        adc     dlt
        sta     flo
        bcc     :+
        inc     fhi
:       inx
        bne     qsl
        inc     qs1+2
        inc     qs2+2
        inc     qspg
        lda     qspg
        cmp     #2
        bne     qsl
        rts

; --------------------------------------------------------------------------
; shr7 / shr6 — arithmetic right shift of the 16-bit signed value in t1:t0,
; result in A.  Both leave t0/t1 alone.
;
;   shr7: (t1 << 1) | bit7(t0)
;   shr6: (t1 << 2) | (t0 >> 6)
; --------------------------------------------------------------------------

shr7:   lda     t0
        asl     a
        lda     t1
        rol     a
        rts

shr6:   lda     t0
        asl     a
        lda     t1
        rol     a
        sta     tt
        lda     t0
        asl     a
        asl     a
        lda     tt
        rol     a
        rts

; --------------------------------------------------------------------------
; addcx / addcy — vx = sh_cx + (signed A), 16-bit, into vxl/vxh index Y.
; Split out because the sign extension is the same both times.
; --------------------------------------------------------------------------

addcx:  jsr     sgnext
        lda     dxy
        clc
        adc     sh_cx
        sta     vxl,y
        lda     sgnb
        adc     #0
        sta     vxh,y
        rts

addcy:  jsr     sgnext
        lda     dxy
        clc
        adc     sh_cy
        sta     vyl,y
        lda     sgnb
        adc     #0
        sta     vyh,y
        rts

sgnext: sta     dxy
        lda     #0
        bit     dxy
        bpl     sgn1
        lda     #$ff
sgn1:   sta     sgnb
        rts

; ==========================================================================
; xform — rotate and scale the current shape's unit vertices into screen
; coordinates (SPEC.md 5.3).
;
;   in:  sh_type, sh_size, sh_angle, sh_cx, sh_cy
;   out: vxl/vxh, vyl/vyh, nvert
;
;   sc = (cos(angle) * size) >> 7
;   ss = (sin(angle) * size) >> 7
;   vx = cx + ((ux*sc - uy*ss) >> 7)     <- the extra >>1 is the 2:1 aspect
;   vy = cy + ((ux*ss + uy*sc) >> 6)
; ==========================================================================

xform:  lda     sh_angle
        clc
        adc     #64             ; cos(a) = sin(a + 90 degrees)
        tax
        lda     sintab,x
        sta     MULA
        lda     sh_size
        sta     MULB
        jsr     smul
        lda     MULR
        sta     t0
        lda     MULR+1
        sta     t1
        jsr     shr7
        sta     xsc

        ldx     sh_angle
        lda     sintab,x
        sta     MULA
        lda     sh_size
        sta     MULB
        jsr     smul
        lda     MULR
        sta     t0
        lda     MULR+1
        sta     t1
        jsr     shr7
        sta     xss

        ldx     sh_type
        lda     shpn,x
        sta     nvert
        lda     shpoff,x
        sta     vidx
        ldy     #0

xfvert: ldx     vidx
        lda     shpvx,x
        sta     ux
        lda     shpvy,x
        sta     uy

        ; ---- x: t = ux*sc - uy*ss -------------------------------------
        lda     ux
        sta     MULA
        lda     xsc
        sta     MULB
        jsr     smul
        lda     MULR
        sta     t0
        lda     MULR+1
        sta     t1
        lda     uy
        sta     MULA
        lda     xss
        sta     MULB
        jsr     smul
        lda     t0
        sec
        sbc     MULR
        sta     t0
        lda     t1
        sbc     MULR+1
        sta     t1
        jsr     shr7
        jsr     addcx

        ; ---- y: u = ux*ss + uy*sc -------------------------------------
        lda     ux
        sta     MULA
        lda     xss
        sta     MULB
        jsr     smul
        lda     MULR
        sta     t0
        lda     MULR+1
        sta     t1
        lda     uy
        sta     MULA
        lda     xsc
        sta     MULB
        jsr     smul
        lda     t0
        clc
        adc     MULR
        sta     t0
        lda     t1
        adc     MULR+1
        sta     t1
        jsr     shr6
        jsr     addcy

        inc     vidx
        iny
        cpy     nvert
        beq     :+              ; jmp trampoline: the loop body is > 127 bytes
        jmp     xfvert
:       rts

; ==========================================================================
; buildedges — turn the transformed vertices into a DDA edge list.
;
;   in:  vxl/vxh, vyl/vyh, nvert
;   out: eytl/h eybl/h exl/h edxl/h edyl/h eerl/h esx, nedge, eord,
;        symin, symax
;
; Horizontal edges are dropped: they cross no scanline, and keeping them
; would break the even-odd crossing count at a flat top or bottom.
;
; There is no division here.  x advances by a Bresenham DDA whose total work
; over an edge's life is dy + |dx| steps, which is cheaper than a 16.8 slope
; and needs no 16/16 divide at setup (SPEC.md 5.4).
; ==========================================================================

buildedges:
        lda     #0
        sta     nedge
        lda     #$ff            ; symin = $7FFF
        sta     syminl
        lda     #$7f
        sta     syminh
        lda     #$00            ; symax = $8000
        sta     symaxl
        lda     #$80
        sta     symaxh
        lda     #0
        sta     bei

belp:   ldx     bei             ; j = (i + 1) mod nvert
        inx
        cpx     nvert
        bne     :+
        ldx     #0
:       stx     bej

        ldx     bei             ; the y extent tracks every vertex
        lda     vyl,x
        sta     t0
        lda     vyh,x
        sta     t1
        jsr     updspan

        ldx     bei
        ldy     bej
        lda     vyl,x           ; horizontal edge?
        cmp     vyl,y
        bne     bene
        lda     vyh,x
        cmp     vyh,y
        bne     bene
        jmp     benext          ; equal y: contributes no crossing
bene:   lda     vyl,x           ; signed: vy[i] < vy[j] ?
        cmp     vyl,y
        lda     vyh,x
        sbc     vyh,y
        bvc     :+
        eor     #$80
:       bpl     berev
        lda     bei             ; i is the top
        sta     betop
        lda     bej
        sta     bebot
        jmp     bestore
berev:  lda     bej             ; j is the top
        sta     betop
        lda     bei
        sta     bebot

bestore:
        ldx     nedge
        ldy     betop
        lda     vyl,y
        sta     eytl,x
        lda     vyh,y
        sta     eyth,x
        lda     vxl,y
        sta     exl,x
        lda     vxh,y
        sta     exh,x
        ldy     bebot
        lda     vyl,y
        sta     eybl,x
        lda     vyh,y
        sta     eybh,x

        lda     eybl,x          ; dy = ybot - ytop, always > 0
        sec
        sbc     eytl,x
        sta     edyl,x
        lda     eybh,x
        sbc     eyth,x
        sta     edyh,x

        lda     vxl,y           ; dx = xbot - xtop, signed
        sec
        sbc     exl,x
        sta     t0
        lda     vxh,y
        sbc     exh,x
        sta     t1

        lda     t1              ; split into a step direction and |dx|
        bpl     bepos
        lda     #$ff
        sta     esx,x
        lda     #0
        sec
        sbc     t0
        sta     edxl,x
        lda     #0
        sbc     t1
        sta     edxh,x
        jmp     bezer
bepos:  lda     #$01
        sta     esx,x
        lda     t0
        sta     edxl,x
        lda     t1
        sta     edxh,x
bezer:  lda     #0
        sta     eerl,x
        sta     eerh,x
        inc     nedge

benext: inc     bei
        lda     bei
        cmp     nvert
        beq     :+
        jmp     belp
:                                ; fall through to the sort

; ---- sort edge indices by ytop, so the scanline loop admits in order -----
; Bubble sort, nedge at most 16 — and MEASURED, because "a few hundred cycles
; once per shape" stood here for the life of the demo and is wrong by ~50x.
; At the very nedge 16 that bound names it costs 16,381 cycles worst case
; (16-gon at size 90, angle 192, max of 8 samples; 14,369-14,628 at angle 0),
; and 3,444 on the natural mid-run 8-edge shape.  Only a triangle comes near
; the old claim, at 147.  The conclusion survives its number: against a
; scanline loop measured in tens of thousands (75,996 on that same 8-edge
; shape, as this build ships — it was 78,688 before the two-crossing case went
; in) this is 3.0% of a worst-case drawshape — but it is also 70% of
; buildedges itself, which the old sentence did not say and which is the more
; interesting fact.  Anchor: `c64 profile $0eb9 --samples 8` after
; `call xform`, $0EB9 being the `ldx #0` below; the block falls through to
; besorted, which IS buildedges' rts, and the index init makes re-entry
; idempotent, so --samples is honest here.  The angle sweep behind those
; figures is in AUDIT.md's iteration-3 performance section.

        ldx     #0
beid:   txa
        sta     eord,x
        inx
        cpx     nedge
        bne     beid

        ldx     nedge
        dex
        beq     besorted        ; 0 or 1 edges: nothing to order
        cpx     #0
        beq     besorted
bepass: lda     #0
        sta     bswap
        ldx     #1
bein:   cpx     nedge
        beq     bechk
        ldy     eord-1,x
        lda     eytl,y
        sta     t0
        lda     eyth,y
        sta     t1
        ldy     eord,x
        lda     eytl,y          ; cur < prev ?
        cmp     t0
        lda     eyth,y
        sbc     t1
        bvc     :+
        eor     #$80
:       bpl     benx
        lda     eord-1,x
        pha
        lda     eord,x
        sta     eord-1,x
        pla
        sta     eord,x
        lda     #1
        sta     bswap
benx:   inx
        jmp     bein
bechk:  lda     bswap
        bne     bepass
besorted:
        rts

; --------------------------------------------------------------------------
; updspan — fold the 16-bit signed value in t1:t0 into symin/symax.
; --------------------------------------------------------------------------

updspan:
        lda     t0
        cmp     syminl
        lda     t1
        sbc     syminh
        bvc     :+
        eor     #$80
:       bpl     us1
        lda     t0
        sta     syminl
        lda     t1
        sta     syminh
us1:    lda     symaxl
        cmp     t0
        lda     symaxh
        sbc     t1
        bvc     :+
        eor     #$80
:       bpl     us2
        lda     t0
        sta     symaxl
        lda     t1
        sta     symaxh
us2:    rts

; ==========================================================================
; scanfill — even-odd scanline fill through an active-edge table.
;
; y runs from symin (which may be negative — a shape may hang off the top)
; to symax, stopping early once it passes 199.  Edges are admitted as y
; reaches their ytop and dropped as it reaches their ybot, so the per-row
; cost is proportional to the crossings actually on that row: two for every
; convex shape, four for the concave ones.
;
; Rows outside 0..199 still step the DDAs — the geometry has to stay
; correct — but paint nothing.  Spans are clipped to x 0..160, never skipped.
; ==========================================================================

scanfill:
        lda     syminl
        sta     scany
        lda     syminh
        sta     scany+1
        lda     #0
        sta     enext
        sta     naet

        jmp     sfloop

; jmp trampolines: scanfill's body is far longer than a short branch reaches,
; so the two loop exits are reached indirectly (6502-assembly skill gotcha).
sfjdone: jmp    sfdone

sfloop: lda     scany+1         ; past the bottom of the screen? stop.
        bmi     sfin            ; negative y is still above the screen
        bne     sfjdone
        lda     scany
        cmp     #200
        bcs     sfjdone
sfin:   lda     symaxl          ; past the shape? stop.
        cmp     scany
        lda     symaxh
        sbc     scany+1
        bvc     :+
        eor     #$80
:       bmi     sfjdone

; ---- admit every edge whose ytop has been reached ------------------------
adm:    ldx     enext
        cpx     nedge
        beq     admdone
        ldy     eord,x
        lda     scany           ; scany < ytop ?  then not yet
        cmp     eytl,y
        lda     scany+1
        sbc     eyth,y
        bvc     :+
        eor     #$80
:       bmi     admdone
        ldx     naet
        tya
        sta     aet,x
        inc     naet
        inc     enext
        jmp     adm
admdone:

; ---- pass A: drop finished edges, compacting the table -------------------
        lda     #0
        sta     aetw
        sta     aetrd
paA:    ldx     aetrd
        cpx     naet
        beq     paAdone
        ldy     aet,x
        lda     scany           ; scany >= ybot ?  then finished
        cmp     eybl,y
        lda     scany+1
        sbc     eybh,y
        bvc     :+
        eor     #$80
:       bpl     paAnext
        ldx     aetw
        tya
        sta     aet,x
        inc     aetw
paAnext:
        inc     aetrd
        jmp     paA
paAdone:
        lda     aetw
        sta     naet
        cmp     maxcross        ; high-water mark proves the MAXX ceiling
        bcc     :+
        sta     maxcross
:

; ---- pass B: read the crossings off the surviving edges ------------------
        ldx     #0
paB:    cpx     naet
        beq     paBdone
        cpx     #MAXX
        bcs     paBdone
        ldy     aet,x
        lda     exl,y
        sta     crossl,x
        lda     exh,y
        sta     crossh,x
        inx
        jmp     paB
paBdone:
        stx     ncross

; ---- pass C: step every surviving edge's DDA one scanline ----------------
        ldx     #0
paC:    cpx     naet
        beq     paCdone
        ldy     aet,x
        lda     eerl,y
        clc
        adc     edxl,y
        sta     eerl,y
        lda     eerh,y
        adc     edxh,y
        sta     eerh,y
ddal:   lda     eerl,y          ; while err >= dy: err -= dy; x += sx
        cmp     edyl,y
        lda     eerh,y
        sbc     edyh,y
        bcc     paCnext
        lda     eerl,y
        sec
        sbc     edyl,y
        sta     eerl,y
        lda     eerh,y
        sbc     edyh,y
        sta     eerh,y
        lda     esx,y
        bmi     ddaneg
        lda     exl,y           ; no inc abs,y on the 6502 — add by hand
        clc
        adc     #1
        sta     exl,y
        bcc     ddal
        lda     exh,y
        adc     #0
        sta     exh,y
        jmp     ddal
ddaneg: lda     exl,y
        sec
        sbc     #1
        sta     exl,y
        lda     exh,y
        sbc     #0
        sta     exh,y
        jmp     ddal
paCnext:
        inx
        jmp     paC
paCdone:

; ---- sort the crossings ---------------------------------------------------
; Two crossings is the common case: it is the only NON-ZERO count a convex
; shape produces, and seven of the ten types are convex.  So it gets a
; straight-line compare-and-swap instead of the general bubble sort below.
; The general sort pays for machinery two elements cannot use: the `bswap`
; flag, the index loop and a second pass that exists only to observe that the
; first one swapped nothing.  Measured entry-to-`sfclip` on the 16-gon at size
; 90, whose 179 rows count {2: 178, 0: 1} — the zero is the LAST row, because
; sfloop runs scany to symax inclusive while pass A drops every edge whose
; ybot has been reached, and symax IS the bottom-most vertex y, so nothing
; survives to cross it (read back at scany 189: naet 0, ncross 0; at 188:
; naet 2, ncross 2).  That row leaves through the `bcc` below, not this case.
; 21,409 cycles of sorting per shape before this case existed, 9,419 after.
; The three concave types are the reason the general sort stays: some of their
; rows carry four crossings, take the same bubble sort as before, and now pay
; 5 cycles more than they used to, on those rows only — the `beq cs2` below as
; a not-taken branch (2) plus the `jmp sfclip` at the sort's exit (3), where it
; used to fall through.  No measured figure moves and the bias runs against the
; improvement.  Both legs of the measurement, and the method, are in AUDIT.md's
; iteration-3 performance section — NOT in the commit body that added this
; case, which predates the row histogram above and still carries the retracted
; claim that every one of the 179 rows crosses twice.
        jmp     cssort
sfjnext: jmp    sfnext          ; the second trampoline, for the tail half
cssort: lda     ncross
        cmp     #2
        bcc     sfjnext         ; 0 or 1 crossings: nothing to order
        beq     cs2             ; exactly 2: the straight-line case below
cspass: lda     #0
        sta     bswap
        ldx     #1
csin:   cpx     ncross
        beq     cschk
        lda     crossl,x        ; cur < prev ?
        cmp     crossl-1,x
        lda     crossh,x
        sbc     crossh-1,x
        bvc     :+
        eor     #$80
:       bpl     csnx
        lda     crossl,x
        ldy     crossl-1,x
        sta     crossl-1,x
        tya
        sta     crossl,x
        lda     crossh,x
        ldy     crossh-1,x
        sta     crossh-1,x
        tya
        sta     crossh,x
        lda     #1
        sta     bswap
csnx:   inx
        jmp     csin
cschk:  lda     bswap
        bne     cspass
        jmp     sfclip          ; three or more crossings rejoin here

; ---- the two-crossing case: one signed compare, at most one swap ----------
cs2:    lda     crossl+1        ; cross[1] < cross[0] ?
        cmp     crossl
        lda     crossh+1
        sbc     crossh
        bvc     :+
        eor     #$80
:       bpl     sfclip          ; already ordered, which is the usual way round
        lda     crossl+1
        ldy     crossl
        sta     crossl
        sty     crossl+1
        lda     crossh+1
        ldy     crossh
        sta     crossh
        sty     crossh+1

; ---- fill the pairs, clipped to the screen -------------------------------
; `sfclip` is a label with no code of its own: it names the in-range test so
; the L1 profiling leg (patch it to `jmp sfnext` and no row runs the pair-clip
; in either leg) can be re-derived from the .lbl instead of by counting bytes
; from `cschk`, which moves whenever this sort changes.
sfclip: lda     scany+1         ; only rows 0..199 paint
        bne     sfnext
        lda     scany
        cmp     #200
        bcs     sfnext
        sta     spy
        ldx     #0
pairl:  cpx     ncross
        bcs     sfnext
        stx     pairi
        lda     crossl,x
        sta     t0
        lda     crossh,x
        sta     t1
        inx
        cpx     ncross
        bcs     sfnext          ; an odd crossing left over: nothing to pair
        lda     crossl,x
        sta     t2
        lda     crossh,x
        sta     t3

        lda     t1              ; clip xa
        bmi     xaneg
        bne     pairskip        ; xa >= 256: wholly off the right
        lda     t0
        cmp     #160
        bcs     pairskip
        jmp     xaok
xaneg:  lda     #0
        sta     t0
        sta     t1
xaok:   lda     t3              ; clip xb
        bmi     pairskip        ; xb < 0: wholly off the left
        bne     xbclip
        lda     t2
        beq     pairskip
        cmp     #161
        bcc     xbok
xbclip: lda     #160
        sta     t2
xbok:   lda     t0
        cmp     t2
        bcs     pairskip        ; empty after clipping
        sta     spxa
        lda     t2
        sta     spxb
        jsr     spanfill
pairskip:
        ldx     pairi
        inx
        inx
        jmp     pairl

sfnext: inc     scany
        bne     :+
        inc     scany+1
:       jmp     sfloop
sfdone: rts

; ==========================================================================
; drawshape — paint one shape and record what it was.
;
;   in:  sh_type sh_size sh_cx sh_cy sh_angle sh_pat sh_ink
;   out: the canvas, plus lstype..lsbytes, typeseen, patseen, shapes
;
; `painting` is 1 for the duration, so an observer that stops mid-shape can
; tell.  `shapedone` is the label evidence capture anchors on.
; ==========================================================================

drawshape:
        lda     #1
        sta     painting
        lda     #0
        sta     lsbytes
        sta     lsbytes+1
        lda     #$ff            ; no cell row has been stamped for THIS shape
        sta     stampcr
        jsr     xform
        jsr     buildedges
        jsr     scanfill

        lda     sh_type
        sta     lstype
        lda     sh_size
        sta     lssize
        lda     sh_cx
        sta     lsx
        lda     sh_cy
        sta     lsy
        lda     sh_angle
        sta     lsangle
        lda     sh_pat
        sta     lspat
        lda     sh_ink
        sta     lsink

        ldx     sh_type         ; typeseen |= 1 << type
        lda     #1
        sta     t0
        lda     #0
        sta     t1
dstl:   cpx     #0
        beq     dstd
        asl     t0
        rol     t1
        dex
        jmp     dstl
dstd:   lda     typeseen
        ora     t0
        sta     typeseen
        lda     typeseen+1
        ora     t1
        sta     typeseen+1

        ldx     sh_pat          ; patseen |= 1 << pat
        lda     #1
dspl:   cpx     #0
        beq     dspd
        asl     a
        dex
        jmp     dspl
dspd:   ora     patseen
        sta     patseen

        inc     shapes
        bne     :+
        inc     shapes+1
:       lda     #0
        sta     painting
shapedone:
        rts
