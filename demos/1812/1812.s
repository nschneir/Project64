; 1812.s — randomised shapes painted to the 1812 Overture, for the C64.
;
; A black 160x200 multicolour bitmap that fills up over 2:50 with rotated,
; dither-filled polygons.  Every shape is spawned by a note onset in a
; three-voice SID reduction of the Overture; the section of the arrangement
; decides the vocabulary, the palette, the size range and the spawn rate.
; Nothing is ever erased — the finished picture is a record of the piece.
;
; A CINV wedge keeps time at 60 Hz and pushes spawn requests onto a ring
; buffer; the main loop pops them and rasterises.  A shape that takes twenty
; frames therefore cannot stretch a note; it can only make the queue deeper,
; and a full queue drops and counts rather than letting shapes lag the music.
;
;   c64 run demos/1812/1812.s
;   c64 package demos/1812/1812.s -o demos/1812/1812.d64 --title "1812"
;   x64sc -ntsc demos/1812/1812.d64
;
; Memory map (SPEC.md 2.2)
;   $0801-$080C  BASIC stub "10 SYS 2061"
;   $080D-$1FFF  CODE / RODATA / DATA / BSS — MUST end below $2000
;   $0400-$07E7  screen RAM: bit-pair 01 = high nybble, 10 = low nybble
;   $2000-$3F3F  the 8000-byte bitmap
;   $D800-$DBE7  colour RAM: bit-pair 11

; ---- hardware ------------------------------------------------------------
BITMAP  = $2000
SCREEN  = $0400
COLRAM  = $D800
VICCTL1 = $D011                 ; bitmap bit 5, DEN bit 4, RSEL bit 3
VICCTL2 = $D016                 ; multicolour bit 4, CSEL bit 3
VICMEM  = $D018                 ; screen base bits 7-4, bitmap base bit 3
BORDER  = $D020
BGCOL   = $D021
SIDBASE = $D400
QSL     = $C000                 ; quarter-square table f(x)=floor(x*x/4), low
QSH     = $C200                 ; ...and high bytes.  512 entries each, built by
                                ; qsgen at startup.  $C000-$CFFF is the 4 KB
                                ; BASIC never touches, and none of it is in the
                                ; .prg — see vars.s on why that matters.
CINV    = $0314                 ; IRQ RAM vector; default $EA31
BLNSW   = $CC                   ; nonzero suppresses the KERNAL cursor blink
KEYDOWN = $CB                   ; the KERNAL's held-key byte -- read as a
                                ; fallback only; see `keyscan`
KEY_NONE = 64
CIA1PRA = $DC00                 ; keyboard matrix: rows out ...
CIA1PRB = $DC01                 ; ... columns in
CIA1DDRA = $DC02
CIA1DDRB = $DC03
JIFFLO  = $A2

; The mode bytes, spelled out once (SPEC.md 2.1).
MODECTL1 = $3B                  ; bitmap + DEN + 25 rows + yscroll 3
MODECTL2 = $18                  ; multicolour + 40 columns + xscroll 0
MODEMEM  = $18                  ; screen $0400, bitmap $2000

; ---- zero page (SPEC.md 2.3; proved free by PLAN task 1) -----------------
ORB1    = $02                   ; dither OR bits, odd cell columns
COLPTR  = $22                   ; colour-RAM row pointer
MULA    = $24                   ; signed multiply operand A
MULB    = $25                   ; signed multiply operand B
MULR    = $26                   ; signed multiply result, 16-bit
ANDM0   = $28                   ; dither AND mask, even cell columns
ORB0    = $29                   ; dither OR bits, even cell columns
ANDM1   = $2A                   ; dither AND mask, odd cell columns
BMPPTR  = $FB                   ; bitmap byte pointer
SCRPTR  = $FD                   ; screen-RAM row pointer

        .exportzp MULA, MULB, MULR, BMPPTR, SCRPTR, COLPTR
        .import __BSS_LOAD__, __BSS_SIZE__

        .segment "LOADADDR"
        .word   $0801

        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"

; ==========================================================================
; init — take the machine, set the mode, black the canvas.
; ==========================================================================

start:  sei
        cld
        jsr     zerobss
        jsr     rwzero          ; the $C400 rasteriser block is not in the .prg either
        jsr     qsgen           ; the multiply tables, before anything multiplies
        jsr     setmode
        jsr     clrbitmap
        lda     #0
        sta     section
        jsr     setpal
        jsr     resetstate
        lda     #$ff
        sta     BLNSW           ; the KERNAL blink would write a COLOUR cell
        jsr     sndinit
        jsr     seqreset
        jsr     irqinstall
        cli
        ; fall through

; ==========================================================================
; mainloop — drain the spawn queue.  NOT a frame anchor: it spins when the
; queue is empty.  Anchor frame counts on `seqtick` (SPEC.md 8).
; ==========================================================================

mainloop:
        jsr     qpop
        bcc     mlidle
        jsr     pickshape
        jsr     drawshape
        jmp     mainloop
mlidle: lda     section
        cmp     #5
        bne     mainloop
        jsr     keyscan         ; the hold: a key restarts with a fresh seed
        cmp     #KEY_NONE
        beq     mainloop
        jsr     restart
        jmp     mainloop

; ==========================================================================
; keyscan — the key held right now, as a matrix code, or KEY_NONE for none.
;
; Read from the hardware: $DC00 drives one keyboard row low at a time and
; $DC01 reads the columns back.  It has to be the hardware.  $CB is the
; Commodore KERNAL's private scratch byte and not a published call, so a
; clean-room KERNAL has no reason to maintain it — on MEGA65 open-roms, the
; ROM the web player boots, $CB reads 0 forever.  0 is not KEY_NONE, so the
; hold above read a key that was never pressed and the piece relaunched
; itself the moment it reached section 5.  The CIA is the machine either way.
;
; Rows are walked 7 down to 0 and the highest column bit wins: that is the
; order Commodore's own scan resolves two keys held at once, so what this
; returns is the code $CB would have held.
;
; With the matrix idle the KERNAL byte is still consulted, because that is
; how the hold is driven from the CLI: test.yaml re-pokes $CB before each
; `until`.  A $CB of 0 is read as KEY_NONE — code 0 is INST/DEL, which this
; demo does not distinguish from any other key anyway, and 0 is exactly what
; a ROM that never writes the byte leaves behind.
; ==========================================================================

keyscan:
        php                     ; the KERNAL's scan runs under the wedge and
        sei                     ; drives this same port
        lda     CIA1PRA
        pha                     ; ... so put it back exactly as found
        lda     #$FF
        sta     CIA1DDRA        ; port A: outputs, the row drive
        lda     #$00
        sta     CIA1DDRB        ; port B: inputs, the column sense
        ldx     #7
kscan1: lda     ksrows,x
        sta     CIA1PRA
        lda     CIA1PRB
        cmp     #$FF            ; all columns high: nothing down on this row
        bne     kshit
        dex
        bpl     kscan1
        pla
        sta     CIA1PRA
        plp
        lda     KEYDOWN
        bne     :+
        lda     #KEY_NONE
:       rts
kshit:  eor     #$FF            ; set bits = the columns pulled low
        pha
        txa                     ; matrix code = row*8 + column
        asl     a
        asl     a
        asl     a
        ora     #7
        tay
        pla
kscan2: asl     a
        bcs     kscan3
        dey
        jmp     kscan2          ; a bit is set, so this always lands
kscan3: pla
        sta     CIA1PRA
        plp
        tya
        rts
ksrows: .byte   $FE, $FD, $FB, $F7, $EF, $DF, $BF, $7F

; ==========================================================================
; setmode — the five registers of SPEC.md 2.1, and nothing else.  The VIC
; bank stays 0, so $DD00 is untouched and the screen stays at $0400.
; ==========================================================================

setmode:
        lda     #MODECTL1
        sta     VICCTL1
        lda     #MODECTL2
        sta     VICCTL2
        lda     #MODEMEM
        sta     VICMEM
        lda     #0
        sta     BORDER
        sta     BGCOL
        rts

; ==========================================================================
; clrbitmap — 8000 bytes of $2000 to zero.  Called once at start and once
; per restart; never per frame, and never between shapes.
; ==========================================================================

clrbitmap:
        lda     #<BITMAP
        sta     BMPPTR
        lda     #>BITMAP
        sta     BMPPTR+1
        lda     #0
        ldx     #31             ; 31 whole pages = 7936 bytes
        ldy     #0
cb1:    sta     (BMPPTR),y
        iny
        bne     cb1
        inc     BMPPTR+1
        dex
        bne     cb1
        ldy     #0              ; the remaining 64
cb2:    sta     (BMPPTR),y
        iny
        cpy     #64
        bne     cb2
        rts

; ==========================================================================
; setpal — stamp every cell with `section`'s palette triple.
;
; This is the whole-canvas version, used at start and at a restart.  During
; play, spanfill stamps only the cells a shape actually covers, which is what
; makes the re-tinting of SPEC.md 3 follow the shapes' geometry rather than
; their bounding boxes.
;
; Writes four whole pages, so $07E8-$07FF (including the unused sprite
; pointers) and $DBE8-$DBFF get written too.  Harmless: no sprite is enabled.
; ==========================================================================

; loadpal only moves the two palette bytes spanfill reads.  A SECTION CHANGE
; calls this and nothing else: re-stamping all 1000 cells there would re-tint
; the whole canvas at once, including cells the new section never touches,
; and the policy of SPEC.md 3 is that re-tinting follows the shapes.
loadpal:
        lda     section
        asl     a
        tax
        lda     secpal,x
        sta     palscr
        lda     secpal+1,x
        sta     palcol
        rts

setpal: jsr     loadpal
        ldy     #0
sp1:    lda     palscr
        sta     SCREEN,y
        sta     SCREEN+$100,y
        sta     SCREEN+$200,y
        sta     SCREEN+$300,y
        lda     palcol
        sta     COLRAM,y
        sta     COLRAM+$100,y
        sta     COLRAM+$200,y
        sta     COLRAM+$300,y
        iny
        bne     sp1
        rts

; ==========================================================================
; zerobss — BSS is not in the .prg, so every .res byte holds whatever was in
; RAM at load time.  Zero the lot before anything reads it.
; ==========================================================================

; rwzero — clear the $C400 working block.  Same reason as zerobss: it is not
; in the .prg, so at load it holds whatever was in RAM.
rwzero: lda     #0
        ldx     #0
rwz1:   sta     RWORK,x
        sta     RWORK+$100,x
        inx
        bne     rwz1
        rts

zerobss:
        lda     #<__BSS_LOAD__
        sta     BMPPTR
        lda     #>__BSS_LOAD__
        sta     BMPPTR+1
        lda     #0
        ldx     #>__BSS_SIZE__
        ldy     #0
        beq     zb2             ; always: Y is 0
zb1:    sta     (BMPPTR),y
        iny
        bne     zb1
        inc     BMPPTR+1
        dex
zb2:    cpx     #0
        bne     zb1
        ldy     #0
zb3:    cpy     #<__BSS_SIZE__
        beq     zb4
        sta     (BMPPTR),y
        iny
        bne     zb3
zb4:    rts

; ==========================================================================
; resetstate — the observable counters, and the RNG from `seed`.
; A zero seed would lock the LFSR at its fixed point, so it is forced to 1.
; ==========================================================================

resetstate:
        lda     seed
        sta     rng
        lda     seed+1
        sta     rng+1
        lda     rng
        ora     rng+1
        bne     rs1
        lda     #1
        sta     rng
rs1:    lda     #0
        sta     frames
        sta     frames+1
        sta     secframe
        sta     secframe+1
        sta     noteidx
        sta     shapes
        sta     shapes+1
        sta     dropped
        sta     cannons
        sta     flash
        sta     painting
        sta     qhead
        sta     qtail
        sta     lsbytes
        sta     lsbytes+1
        sta     typeseen
        sta     typeseen+1
        sta     patseen
        sta     maxcross
        rts

; ==========================================================================
; restart — a key during the hold.  Mix the jiffy clock into the seed so the
; new picture really is different, then start over from a black canvas.
; Clearing here is a NEW RUN, not an erase during one (SPEC.md 12, A12).
; ==========================================================================

restart:
        sei
        lda     seed
        eor     JIFFLO
        sta     seed
        lda     seed+1
        eor     rng
        sta     seed+1
        jsr     resetstate
        lda     #0
        sta     section
        jsr     clrbitmap
        jsr     setpal
        jsr     sndinit
        jsr     seqreset
        cli
        rts

; ==========================================================================
; irqinstall — the CINV wedge (cookbook, "IRQ wedge").  Chaining to the old
; vector keeps the jiffy clock alive, and with it the KERNAL's keyboard scan,
; which is what keeps `keyscan`'s $CB fallback fed on a Commodore ROM.
;
; `jmp (oldvec)` would hit the 6502 indirect-jump page bug if oldvec's low
; byte were $FF; PLAN task 8 step 3 checks that in the label file.
; ==========================================================================

irqinstall:
        lda     CINV
        sta     oldvec
        lda     CINV+1
        sta     oldvec+1
        lda     #<wedge
        sta     CINV
        lda     #>wedge
        sta     CINV+1
        rts

; ==========================================================================
; wedge — once per frame, behind everything.  The ROM has already stacked
; A/X/Y by the time CINV is taken, so this needs no save/restore of its own.
; ==========================================================================

wedge:  inc     frames
        bne     wg1
        inc     frames+1
wg1:    inc     secframe
        bne     wg2
        inc     secframe+1
wg2:    jsr     seqtick
        lda     flash           ; the cannon's whole-screen flash
        beq     wgchain
        dec     flash
        bne     wgwhite
        lda     #0              ; expired: back to black, border included
        sta     BORDER
        sta     BGCOL
        jmp     wgchain
wgwhite:
        lda     #1
        sta     BORDER
        sta     BGCOL
wgchain:
        jmp     (oldvec)

        .include "raster.s"
        .include "spawn.s"
        .include "music.s"
        .include "shapes.s"
        .include "sections.s"
        .include "tables.inc"
        .include "vars.s"
