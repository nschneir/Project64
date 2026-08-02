; play.s — the game itself: the playfield, the snake, food, scoring, levels
; and death.
;
; The snake is a ring buffer of SCREEN ADDRESSES (bodylo/bodyhi), oldest at
; `tail`, newest at `head`.  A move touches exactly three cells — erase the
; tail, demote the old head to a body glyph, draw the new head — so the cost
; of a move does not grow with the snake.
;
; Collision is a read of the screen code of the cell being entered.  Nothing
; but spaces, food and the snake/border glyphs is ever written inside the
; playfield, so the test is three-way: 32 = empty, FOODCODE = eat, anything
; else = death.  That is deterministic under the debugger, unlike the VIC
; collision latches, and it names what was hit.

        .segment "CODE"

; ---------------------------------------------------------------------------
; Starting a game

; newgame — reset everything except the high score and the RNG state, paint
; the playfield, seat a three-segment snake and drop the first apple.
newgame:
        lda     #0
        sta     scdig
        sta     scdig+1
        sta     scdig+2
        sta     scdig+3
        sta     eaten
        sta     grow
        sta     ate
        sta     newhi
        sta     tail
        sta     sfxlen
        lda     #1
        sta     level
        lda     #3
        sta     snlen
        lda     #2
        sta     head            ; segments 0,1,2 are seated below
        lda     #3
        sta     curdir          ; heading right
        sta     newdir
        lda     #12
        sta     hrow
        lda     #10
        sta     hcol
        lda     #NOKEY
        sta     keycode         ; the key that started the game must not steer
        ldx     #0
        lda     spdtab,x
        sta     speed
        lda     lvcolor,x
        sta     snakecol
        lda     #0
        sta     clrcol
        jsr     clrscr
        jsr     drawfield
        jsr     drawhud
        jsr     seatsnake
        jsr     newfood
        lda     #1
        sta     gstate
        rts

; seatsnake — three segments across row 12, head at column 10 facing right.
seatsnake:
        lda     snakecol
        sta     pcolor
        lda     #12
        ldy     #8
        jsr     plotaddr
        ldy     #0
        lda     #BODY
        jsr     putcell
        lda     PTR
        sta     bodylo+0
        lda     PTR+1
        sta     bodyhi+0
        lda     #12
        ldy     #9
        jsr     plotaddr
        ldy     #0
        lda     #BODY
        jsr     putcell
        lda     PTR
        sta     bodylo+1
        lda     PTR+1
        sta     bodyhi+1
        lda     #12
        ldy     #10
        jsr     plotaddr
        ldy     #0
        lda     #HEADRT            ; head facing right
        jsr     putcell
        lda     PTR
        sta     bodylo+2
        lda     PTR+1
        sta     bodyhi+2
        rts

; drawfield — the border box: row 1 and row 24 across, columns 0 and 39 down.
; The interior (rows 2-23, columns 1-38) is left as the spaces clrscr laid.
drawfield:
        lda     #BORDCOL
        sta     pcolor
        lda     #1
        ldy     #0
        jsr     plotaddr
        ldy     #0
        lda     #BORDTL            ; top-left corner
        jsr     putcell
        ldy     #1
dftop:  lda     #BORDH
        jsr     putcell
        iny
        cpy     #39
        bne     dftop
        lda     #BORDTR            ; top-right corner
        jsr     putcell
        lda     #24
        ldy     #0
        jsr     plotaddr
        ldy     #0
        lda     #BORDBL            ; bottom-left corner
        jsr     putcell
        ldy     #1
dfbot:  lda     #BORDH
        jsr     putcell
        iny
        cpy     #39
        bne     dfbot
        lda     #BORDBR            ; bottom-right corner
        jsr     putcell
        ldx     #2
dfside: txa
        ldy     #0
        jsr     plotaddr
        ldy     #0
        lda     #BORDV
        jsr     putcell
        ldy     #39
        lda     #BORDV
        jsr     putcell
        inx
        cpx     #24
        bne     dfside
        rts

; ---------------------------------------------------------------------------
; The status line

; drawhud — labels once, then all three numbers.
drawhud:
        lda     #14
        sta     pcolor
        lda     #0
        ldy     #1
        jsr     plotaddr
        ldx     #<msscore
        ldy     #>msscore
        jsr     putstr
        lda     #0
        ldy     #16
        jsr     plotaddr
        ldx     #<mslevel
        ldy     #>mslevel
        jsr     putstr
        lda     #0
        ldy     #30
        jsr     plotaddr
        ldx     #<mshi
        ldy     #>mshi
        jsr     putstr
        jsr     drawscore
        jsr     drawlevel
        ; fall through to drawhi

drawhi: lda     #0
        ldy     #33
        jsr     plotaddr
        lda     #10
        sta     pcolor
        ldx     #<hidig
        ldy     #>hidig
        lda     #4
        jsr     putdig
        rts

drawscore:
        lda     #0
        ldy     #7
        jsr     plotaddr
        lda     #1
        sta     pcolor
        ldx     #<scdig
        ldy     #>scdig
        lda     #4
        jsr     putdig
        rts

drawlevel:
        lda     #0
        ldy     #22
        jsr     plotaddr
        lda     #7
        sta     pcolor
        ldx     #<level
        ldy     #>level
        lda     #1
        jsr     putdig
        rts

; ---------------------------------------------------------------------------
; The move

; playtick — one game tick in state 1: steer, then move exactly one cell.
playtick:
        jsr     steer
        jsr     movesnake
        rts

; steer — turn the latched matrix code into `newdir`.  A key that is not one
; of W/A/S/D leaves the direction alone; so does the direct reversal of the
; direction actually LAST MOVED, which is what stops a double turn inside one
; tick from folding the snake back into itself.
steer:  lda     keycode
        cmp     #NOKEY
        beq     stdone
        ldx     #4              ; sentinel: not a steering key
        cmp     #KEY_W
        bne     stnw
        ldx     #0
stnw:   cmp     #KEY_S
        bne     stns
        ldx     #1
stns:   cmp     #KEY_A
        bne     stna
        ldx     #2
stna:   cmp     #KEY_D
        bne     stnd
        ldx     #3
stnd:   cpx     #4
        beq     stdone
        txa                     ; up/down and left/right differ in bit 0 only,
        eor     curdir          ; so a reversal is exactly an XOR of 1
        cmp     #1
        beq     stdone
        stx     newdir
stdone: lda     #NOKEY
        sta     keycode
        rts

; movesnake — advance one cell, resolving what is in the cell entered.
movesnake:
        lda     newdir
        sta     curdir
        tax
        lda     hrow
        clc
        adc     rowdelta,x
        sta     nrow
        lda     hcol
        clc
        adc     coldelta,x
        sta     ncol
        lda     nrow
        ldy     ncol
        jsr     plotaddr        ; PTR = the cell being entered
        ; The tail vacates its own cell on this very move, so entering it is
        ; legal — resolve that before reading the screen, or a snake at full
        ; stretch dies chasing a segment that is no longer there.
        lda     grow
        bne     msread
        ldx     tail
        lda     PTR
        cmp     bodylo,x
        bne     msread
        lda     PTR+1
        cmp     bodyhi,x
        bne     msread
        lda     #BLANK
        bne     mscode          ; always taken (32 != 0)
msread: ldy     #0
        lda     (PTR),y
mscode: cmp     #BLANK
        beq     msempty
        cmp     #FOODCODE
        beq     msfood
        jmp     died
msempty:
        lda     #0
        sta     ate
        beq     msmove          ; always taken
msfood: lda     #1
        sta     ate
msmove: lda     grow            ; erase the tail unless growth is still owed
        beq     mstail
        dec     grow
        jmp     mshead
mstail: ldx     tail
        lda     bodylo,x
        sta     AUX
        lda     bodyhi,x
        sta     AUX+1
        lda     #BLANK
        ldy     #0
        sta     (AUX),y         ; a space needs no colour
        inc     tail
        dec     snlen
mshead: ldx     head            ; the old head becomes a body segment
        lda     bodylo,x
        sta     AUX
        lda     bodyhi,x
        sta     AUX+1
        lda     #BODY
        ldy     #0
        sta     (AUX),y
        inc     head            ; ring in the cell just entered
        ldx     head
        lda     PTR
        sta     bodylo,x
        lda     PTR+1
        sta     bodyhi,x
        inc     snlen
        jsr     colptr          ; AUX was borrowed above; re-derive it
        ldx     curdir
        lda     headcode,x
        ldy     #0
        sta     (PTR),y
        lda     snakecol
        sta     (AUX),y
        lda     nrow
        sta     hrow
        lda     ncol
        sta     hcol
        lda     ate
        beq     msdone
        jsr     eat
msdone: rts

; ---------------------------------------------------------------------------
; Eating, scoring, levels

; eat — level x 10 points, three more segments, a blip, a fresh apple.
;
; The point counter is a memory byte, not X: `inc scdig,x` has no ,Y form, so
; add10 owns X and returns it wherever the carry stopped.  Counting the
; repetitions in X instead scored 100 for the first apple.
eat:    lda     level
        sta     ptsleft
eloop:  jsr     add10
        dec     ptsleft
        bne     eloop
        jsr     drawscore
        lda     snlen           ; cap growth: the ring must never lap itself
        cmp     #MAXLEN
        bcs     enogrow
        lda     grow
        clc
        adc     #3
        sta     grow
enogrow:
        jsr     sfxeat
        inc     eaten
        lda     eaten
        cmp     #5
        bcc     enolvl
        jsr     levelup         ; its sound replaces the pickup blip
enolvl: jsr     newfood
        rts

; add10 — +10 on the four-digit score, carrying leftwards, clamped at 9999.
add10:  ldx     #2              ; the tens digit
adloop: inc     scdig,x
        lda     scdig,x
        cmp     #10
        bcc     addone
        lda     #0
        sta     scdig,x
        dex
        bpl     adloop
        lda     #9              ; carried out of the thousands: clamp
        sta     scdig
        sta     scdig+1
        sta     scdig+2
        sta     scdig+3
addone: rts

; levelup — every fifth pickup: faster, a new snake colour, a higher blip.
levelup:
        lda     #0
        sta     eaten
        lda     level
        cmp     #9
        bcs     lumax
        inc     level
lumax:  ldx     level
        dex
        lda     spdtab,x
        sta     speed
        lda     lvcolor,x
        sta     snakecol
        jsr     recolor
        jsr     drawlevel
        jsr     sfxlevel
        rts

; recolor — repaint every live segment in the current level's colour, so a
; level change is visible on the whole snake and not just on new growth.
recolor:
        lda     snlen
        sta     rccnt
        ldx     tail
        ldy     #0
rcloop: lda     bodylo,x
        sta     AUX
        lda     bodyhi,x
        clc
        adc     #$d4            ; screen address -> colour address
        sta     AUX+1
        lda     snakecol
        sta     (AUX),y
        inx
        dec     rccnt
        bne     rcloop
        rts

; newfood — an apple on a random EMPTY interior cell (rows 2-23, columns
; 1-38).  Reject-and-retry rather than a modulo, which would bias the low
; rows; the interior has 836 cells against a snake capped at 250, so the
; retry always terminates.
newfood:
nfrow:  jsr     random
        and     #31
        cmp     #22
        bcs     nfrow
        clc
        adc     #2
        sta     foodr
nfcol:  jsr     random
        and     #63
        cmp     #38
        bcs     nfcol
        clc
        adc     #1
        sta     foodc
        lda     foodr
        ldy     foodc
        jsr     plotaddr
        ldy     #0
        lda     (PTR),y
        cmp     #BLANK
        bne     nfrow           ; occupied — draw again
        lda     #FOODCOL
        sta     pcolor
        lda     #FOODCODE
        ldy     #0
        jsr     putcell
        rts

; random — 8-bit maximal Galois LFSR.  The state must never be zero; `start`
; seeds it from the jiffy clock and guards that.
random: lda     seed
        lsr
        bcc     nofb
        eor     #$b8            ; taps for the full 255-value cycle
nofb:   sta     seed
        rts

; ---------------------------------------------------------------------------
; Death

; died — reached by a jmp from inside movesnake, one JSR level down from
; playtick, so its rts unwinds to exactly the right place.
died:   lda     #2
        sta     gstate
        lda     #0
        sta     keyarm          ; the key that steered into the wall must not
        lda     #NOKEY          ; also dismiss the panel it just raised
        sta     keycode
        jsr     sfxdie
        jsr     checkhi
        jsr     drawover
        rts

; checkhi — four-digit compare, most significant first; copy on a win only.
checkhi:
        ldx     #0
chloop: lda     scdig,x
        cmp     hidig,x
        bcc     chdone          ; score < high score
        bne     chcopy          ; score > high score
        inx
        cpx     #4
        bne     chloop
        rts                     ; equal: not a new high score
chcopy: ldx     #3
chcp:   lda     scdig,x
        sta     hidig,x
        dex
        bpl     chcp
        lda     #1
        sta     newhi
        jsr     drawhi
chdone: rts
