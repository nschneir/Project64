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
KEYDOWN  = $cb                  ; matrix code of the key held right now
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
        jsr     pollkey         ; $CB FIRST.  `c64 key hold` pokes the matrix
                                ; code while the machine sits at this label
                                ; and the IRQ keyboard scan puts 64 back
                                ; within a jiffy, so any work before this read
                                ; loses the keypress.
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

; pollkey — latch $CB, and note every moment the keyboard is empty.
;
; `keyarm` is what stops a key held from BEFORE a screen appeared from
; dismissing it: entering the title or the game-over panel clears it, and
; only a frame with no key down sets it again.  Without that the RETURN that
; typed RUN is still down when the title paints, and the game starts before
; anyone has seen it.  Steering does not consult `keyarm` — a held W has to
; keep steering, so it must not need a release first.
pollkey:
        lda     KEYDOWN
        cmp     #NOKEY
        beq     pkrel
        sta     keycode
        rts
pkrel:  lda     #1
        sta     keyarm
        lda     #NOKEY
        sta     keycode
        rts

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
pacew:  jsr     pollkey         ; sampling $CB through the wait keeps a
                                ; human-held key as responsive as the one
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

        ; vars.s comes first: ca65 resolves a forward reference to an
        ; absolute address, but `sta sidshadow,x` has to know the symbol to
        ; pick zp,x versus abs,x, and an unresolved one is an error there.
        .include "vars.s"
        .include "screen.s"
        .include "chars.s"
        .include "sound.s"
        .include "play.s"
        .include "title.s"
