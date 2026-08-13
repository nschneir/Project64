; snake.s — an arcade Snake for the Commodore 64, in 6502 assembly.
;
; Character graphics only: screen RAM $0400, colour RAM $D800, and a custom
; hires character set copied to $3000.  No sprites, no bitmap, no raster
; interrupts — everything the game draws is a screen code, which is what
; makes the whole of it readable back through `c64 screen --codes`.
;
; The state machine is title -> play -> game over -> play again, and one
; pass of `mainloop` is one game tick in every state.  In play a tick is
; exactly one snake move, so `c64 until mainloop --count N` advances N moves
; and `c64 key hold KEY --at mainloop --frames N` steers across N of them.
;
; Build:   .venv/bin/c64 build snake.s
; Play:    .venv/bin/c64 run snake.s
; Package: .venv/bin/c64 package snake.s -o snake.d64 --title "SNAKE"

CHARSET  = $3000                ; RAM character set (VIC bank 0)
SID      = $d400
JIFFLO   = $a2                  ; low byte of the 60 Hz jiffy clock
KEYDOWN  = $cb                  ; the KERNAL's held-key byte — read as a
                                ; fallback only; see `keyscan`
PTR      = $fb                  ; screen pointer
AUX      = $fd                  ; colour pointer, or a borrowed scratch pointer

KEY_W    = 9                    ; keyboard MATRIX codes, not PETSCII
KEY_A    = 10
KEY_S    = 13
KEY_D    = 18
KEY_SPC  = 60
NOKEY    = 64

; The custom glyphs sit at screen codes 112-123.  They deliberately do NOT
; live at 128+: that half of the character set is the ROM's reverse-video
; images, and codes 129-154 are reverse A-Z — glyphs parked there would make
; reverse-video text unusable, which is the cheapest emphasis the machine has
; (the game-over heading uses it).  112-123 are ROM graphics characters
; nothing here draws, and their reverse forms 240-251 are free too.
GLYPH0   = 112
BORDH    = GLYPH0 + 0
BORDV    = GLYPH0 + 1
BORDTL   = GLYPH0 + 2
BORDTR   = GLYPH0 + 3
BORDBL   = GLYPH0 + 4
BORDBR   = GLYPH0 + 5
HEADUP   = GLYPH0 + 6
HEADDN   = GLYPH0 + 7
HEADLF   = GLYPH0 + 8
HEADRT   = GLYPH0 + 9
BODY     = GLYPH0 + 10
FOODCODE = GLYPH0 + 11

BLANK    = 32                   ; screen code for a space
BLOCK    = 160                  ; reverse space: the title's solid block
REVERSE  = 128                  ; OR this into a screen code for reverse video

FOODCOL  = 2                    ; red
BORDCOL  = 14                   ; light blue
MAXLEN   = 240                  ; the body ring is 256 entries.  Growth is
                                ; owed in threes and `grow` accumulates, so
                                ; the cap has to sit far enough below 256 that
                                ; a pending debt cannot carry snlen past it.

        .segment "LOADADDR"
        .word   $0801

        .segment "EXEHDR"
        .word   nextln
        .word   10
        .byte   $9E, "2061", $00
nextln: .word   $0000

        .segment "CODE"

; ---------------------------------------------------------------------------
; start — bring the machine up, then fall into the tick.

start:  cld                     ; an interrupt does not clear D on the NMOS 6502
        lda     #<bsstart       ; BSS is address space, not file bytes: at load
        sta     PTR             ; it holds whatever was in RAM, so zero it all
        lda     #>bsstart       ; before anything reads a flag or a counter
        sta     PTR+1
        ldy     #0
bzloop: lda     PTR+1
        cmp     #>bssend
        bne     bzgo
        lda     PTR
        cmp     #<bssend
        beq     bzdone
bzgo:   lda     #0
        sta     (PTR),y
        inc     PTR
        bne     bzloop
        inc     PTR+1
        jmp     bzloop
bzdone:
        lda     JIFFLO          ; seed the LFSR from the clock, so each run
        bne     sdok            ; deals different apples...
        lda     #1              ; ...but never from zero, its fixed point
sdok:   sta     seed
        jsr     sidzero
        jsr     charsinit
        lda     #6
        sta     $d020           ; blue screen border
        lda     #0
        sta     $d021           ; black background
        sta     gstate          ; 0 = title
        jsr     drawtitle

; ---------------------------------------------------------------------------
; mainloop — one game tick.

mainloop:
        jsr     pollkey         ; THE KEYBOARD FIRST.  `c64 key hold` pokes a
                                ; matrix code into $CB while the machine sits
                                ; at this label and the IRQ keyboard scan puts
                                ; 64 back within a jiffy, so any work before
                                ; this read loses the keypress.
        lda     gstate
        bne     mlnot0
        jsr     titletick
        lda     #4
        jmp     mlpace
mlnot0: cmp     #1
        bne     mlover
        jsr     playtick
        lda     speed
        jmp     mlpace
mlover: jsr     overtick
        lda     #4
mlpace: jsr     pace
        jmp     mainloop

; pollkey — latch the held key, and note every moment the keyboard is empty.
;
; `keyarm` is what stops a key held from BEFORE a screen appeared from
; dismissing it: entering the title or the game-over panel clears it, and
; only a frame with no key down sets it again.  Without that the RETURN that
; typed RUN is still down when the title paints, and the game starts before
; anyone has seen it.  Steering does not consult `keyarm` — a held W has to
; keep steering, so it must not need a release first.
pollkey:
        jsr     keyscan
        cmp     #NOKEY
        beq     pkrel
        sta     keycode
        rts
pkrel:  lda     #1
        sta     keyarm
        lda     #NOKEY
        sta     keycode
        rts

; keyscan — the key held right now, as a matrix code, or NOKEY for none.
;
; Read from the hardware: $DC00 drives one keyboard row low at a time and
; $DC01 reads the columns back.  It has to be the hardware.  $CB is the
; Commodore KERNAL's private scratch byte and not a published call, so a
; clean-room KERNAL has no reason to maintain it — on MEGA65 open-roms, the
; ROM the web player boots, $CB reads 0 forever and a keyboard read through
; it registers nothing at all.  The CIA is the machine either way.
;
; Rows are walked 7 down to 0 and the highest column bit wins: that is the
; order Commodore's own scan resolves two keys held at once, so what this
; returns is the code $CB would have held, and everything downstream of the
; read is unchanged.
;
; With the matrix idle the KERNAL byte is still consulted, because that is
; how this program is driven from the CLI: `c64 key hold` re-pokes $CB
; before each tick and every input step in test.yaml arrives that way.  A
; $CB of 0 is read as NOKEY — code 0 is INST/DEL, no screen here maps it,
; and 0 is exactly what a ROM that never writes the byte leaves behind.
keyscan:
        php                     ; the KERNAL's IRQ scan drives the same port
        sei
        lda     $dc00
        pha                     ; ... so put it back exactly as found
        lda     #$ff
        sta     $dc02           ; port A: outputs, the row drive
        lda     #$00
        sta     $dc03           ; port B: inputs, the column sense
        ldx     #7
kscan1: lda     ksrows,x
        sta     $dc00
        lda     $dc01
        cmp     #$ff            ; all columns high: nothing down on this row
        bne     kshit
        dex
        bpl     kscan1
        pla
        sta     $dc00
        plp
        lda     KEYDOWN
        bne     :+
        lda     #NOKEY
:       rts
kshit:  eor     #$ff            ; set bits = the columns pulled low
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
        sta     $dc00
        plp
        tya
        rts
ksrows: .byte   $fe, $fd, $fb, $f7, $ef, $df, $bf, $7f

; titletick — any key starts a game, once the keyboard has been seen empty.
titletick:
        lda     keyarm
        beq     ttdone
        lda     keycode
        cmp     #NOKEY
        beq     ttdone
        jsr     newgame
ttdone: rts

; overtick — SPACE starts another game.  The high score is not reset.
overtick:
        lda     keyarm
        beq     otdone
        lda     keycode
        cmp     #KEY_SPC
        bne     otdone
        jsr     newgame
otdone: rts

; pace — wait A jiffies, sampling the keyboard and ageing the sound effect
; through the wait.  This is the game's whole clock: the tick rate is
; `speed` jiffies in play (12 down to 2 across the levels) and 4 otherwise.
pace:   sta     pcnt
paceo:  lda     JIFFLO
        sta     pjlast
pacew:  jsr     pollkey         ; sampling the keyboard through the wait keeps
                                ; a human-held key as responsive as the one
                                ; `key hold` pokes at the anchor
        lda     pjlast
        cmp     JIFFLO
        beq     pacew
        lda     sfxlen          ; one jiffy of the current effect
        beq     pacen
        dec     sfxlen
        bne     pacen
        jsr     sfxoff
pacen:  dec     pcnt
        bne     paceo
        rts

        ; Order is a readability choice, not a requirement: ca65 resolves
        ; forward references across includes, so vars.s could sit last.  Each
        ; included file opens with its own `.segment`, which IS a requirement
        ; — the active segment carries across an include boundary.
        .include "vars.s"
        .include "screen.s"
        .include "chars.s"
        .include "sound.s"
        .include "play.s"
        .include "title.s"
