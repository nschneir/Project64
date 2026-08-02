; screen.s — the drawing primitives.  Everything else in the game draws
; through these four routines, so the screen/colour pairing only has to be
; right once.
;
; PTR ($FB/$FC) always points at a screen cell and AUX ($FD/$FE) at that
; cell's colour cell — `plotaddr` sets both, and `colptr` re-derives AUX
; after a routine has borrowed it for something else.  Colour RAM sits
; exactly $D400 above screen RAM, which is the whole of that derivation.

        .segment "CODE"

; plotaddr — PTR = $0400 + row*40 + col, AUX = the matching $D800 cell.
; In: A = row (0-24), Y = column (0-39).  Preserves X.
plotaddr:
        sty     PTR             ; park the column in PTR low
        asl                     ; row*2
        asl                     ; row*4
        asl                     ; row*8 (max 192 — still one byte)
        sta     row8
        lda     #0
        sta     PTR+1
        lda     row8
        asl                     ; row*16 ...
        rol     PTR+1
        asl                     ; row*32, high bits in PTR+1
        rol     PTR+1
        clc
        adc     row8            ; + row*8 = row*40 (low byte)
        bcc     paok
        inc     PTR+1
paok:   clc
        adc     PTR             ; + column
        sta     PTR
        lda     PTR+1
        adc     #$04            ; + $0400 screen base (carry rides along)
        sta     PTR+1
        ; fall through: AUX = PTR + $D400

; colptr — AUX = the colour cell for whatever PTR points at.
colptr: lda     PTR
        sta     AUX
        lda     PTR+1
        clc
        adc     #$d4
        sta     AUX+1
        rts

; putcell — write screen code A and colour `pcolor` at offset Y from PTR.
;
; `pcodeor` is ORed into the code on the way out: REVERSE ($80) turns a run of
; text into reverse video, which is the cheapest emphasis the machine has.
; It is a one-shot — set it immediately before the run that wants it and
; clear it immediately after, because every glyph the game draws goes through
; here and a stale $80 would turn the whole playfield into other characters.
putcell:
        ora     pcodeor
        sta     (PTR),y
        lda     pcolor
        sta     (AUX),y
        rts

; putstr — write a zero-terminated ASCII string from PTR rightwards in
; `pcolor`.  In: PTR/AUX set by plotaddr, X/Y = string address lo/hi.
;
; The source address is patched into the load below.  PTR and AUX are the
; only two pointers zero page has to spare (see references/zero-page.md), and
; both are spoken for here, so a third one would have to come out of BASIC's
; own bytes — self-modifying an absolute,y load is the cheaper trade.
putstr: stx     psrc+1
        sty     psrc+2
        ldy     #0
psloop:
psrc:   lda     $ffff,y         ; patched above
        beq     psdone
        cmp     #$40
        bcc     psput           ; digit/punctuation/space: already a screen code
        sbc     #$40            ; letter: fold (the cmp left carry set)
psput:  jsr     putcell
        iny
        bne     psloop
psdone: rts

; putdig — write A digit bytes (each 0-9) from the array at X/Y as screen
; codes, from PTR rightwards in `pcolor`.  Same self-modified load as putstr.
putdig: stx     dsrc+1
        sty     dsrc+2
        sta     dcnt
        ldy     #0
dloop:
dsrc:   lda     $ffff,y         ; patched above
        ora     #48             ; digit -> screen code '0'-'9'
        jsr     putcell
        iny
        cpy     dcnt
        bne     dloop
        rts

; clrscr — fill all 1000 screen cells with spaces and all 1000 colour cells
; with `clrcol`.  The fourth store of each pair starts at $x6E8 so the run
; ends exactly at cell 999 instead of spilling past it.
clrscr: ldx     #0
clloop: lda     #32
        sta     $0400,x
        sta     $0500,x
        sta     $0600,x
        sta     $06e8,x
        lda     clrcol
        sta     $d800,x
        sta     $d900,x
        sta     $da00,x
        sta     $dae8,x
        inx
        bne     clloop
        rts
