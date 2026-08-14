; amiga_ball.s -- the 1984 Amiga Boing Ball on a Commodore 64.
;
; SPEC.md is the contract; the section numbers below point into it.  This file
; owns the load address, the BASIC stub, the hardware equates, startup, the
; raster interrupt, the `tick` subroutine every observation anchors on, and the
; main loop.  Everything else arrives through the .include list at the bottom.
;
; Build (all three areas, every time -- SPEC.md Section 2):
;   c64 build demos/amiga_ball/amiga_ball.s \
;       --area 'CHARS=$2000:$0800' --area 'SPRITES=$2800:$1800' \
;       --area 'VARS=$4000:$0100'

; --- VIC-II -----------------------------------------------------------------
SPR0X   = $D000                 ; sprite 0 X; +1 is its Y, +2 sprite 1's X, ...
SPRXMSB = $D010                 ; X bit 8, one bit per sprite
SCRCTL1 = $D011                 ; bit 7 is raster compare bit 8
RASTER  = $D012                 ; raster line, low 8 bits
SPRENA  = $D015
SPREXPY = $D017
SPRPRI  = $D01B                 ; 1 = the sprite goes behind character data
SPRMC   = $D01C
SPREXPX = $D01D
VICIRQ  = $D019                 ; interrupt latch: write a 1 bit to clear it
VICIMR  = $D01A                 ; interrupt enable
SPRMC0  = $D025                 ; shared multicolour 0 -- the rim
SPRMC1  = $D026                 ; shared multicolour 1 -- white
SPRCOL0 = $D027                 ; per-sprite colour, +n for sprite n

SPRPTR  = $07F8                 ; screen + $3F8; holds block = address / 64

; --- CIA / KERNAL vectors ---------------------------------------------------
CIA1ICR = $DC0D
CINV    = $0314                 ; the KERNAL's IRQ vector, taken after $FF48
                                ; has already pushed A/X/Y

; --- Layout -----------------------------------------------------------------
IRQLINE = 10                    ; SPEC.md Section 10.2: $D012 wraps at 263, so a
                                ; tick that starts at 10 and costs under 40 lines
                                ; cannot straddle the wrap and compute a negative
                                ; cost; and the display window opens at raster 51,
                                ; so every sprite register is written before the
                                ; VIC draws a pixel of the frame.
BLOCK0  = 160                   ; $2800 / 64 -- the first rotation-frame block

; ===========================================================================
        .segment "LOADADDR"
        .word   $0801

; "10 SYS 2061" -- 12 bytes, $0801-$080C, so CODE begins at $080D = 2061.
        .segment "EXEHDR"
        .word   nextln          ; pointer to the next BASIC line
        .word   10              ; line number
        .byte   $9E, "2061", $00 ; SYS 2061
nextln: .word   $0000           ; end of program

; ===========================================================================
        .segment "CODE"

start:  sei
        cld                     ; an interrupt does not clear D on the NMOS
                                ; 6502, so clear it before anything adds
        ldx     #$FF
        txs

        ; Zero all 25 SID registers.  SID registers survive a program stop, and
        ; a left-over gate bit blocks the first note of the next run.  Through
        ; sidput, so sid_shadow starts out agreeing with the chip -- the shadow
        ; is the only evidence a stopped machine can give about a write-only
        ; chip (SPEC.md Section 8).
        lda     #$00
        ldx     #24
sidzero: jsr    sidput          ; preserves A and X
        dex
        bpl     sidzero

        jsr     room_init
        jsr     ball_init
        jsr     sound_init

        ; --- the interrupt install, SPEC.md Section 10.2 -------------------
        lda     #$7F
        sta     CIA1ICR         ; CIA1's timer interrupt off: nothing but the
        lda     CIA1ICR         ; raster may reach the handler.  The read acks
                                ; whatever the CIA had already latched.
        lda     #<irq
        sta     CINV
        lda     #>irq
        sta     CINV+1
        lda     SCRCTL1
        and     #$7F            ; compare line is below 256, so its bit 8 is 0
        sta     SCRCTL1
        lda     #IRQLINE
        sta     RASTER
        lda     #$01
        sta     VICIMR          ; raster is the only source
        sta     VICIRQ          ; and no stale latch is left to fire at once
        cli

; mainloop -- a liveness signal and nothing else.  It is deliberately NOT the
; frame anchor: it free-runs, so `until mainloop --count N` would count loops
; rather than frames.  `tick` is the anchor (SPEC.md Section 10.2).
mainloop:
        inc     alive
        jmp     mainloop

; ---------------------------------------------------------------------------
; irq -- one raster interrupt per frame at line IRQLINE.  Nothing from ROM runs
; inside it: it exits by pulling A/X/Y itself, not through $EA31 or $EA81.  The
; KERNAL's $FF48 entry pushed A, X and Y before `jmp (CINV)`, so the three pulls
; below are the exact complement.
irq:    lda     #$01
        sta     VICIRQ          ; ack first -- an unacknowledged raster IRQ
                                ; re-fires the instant RTI runs
        cld                     ; the interrupt did not clear D; the cost
                                ; arithmetic below is binary
        lda     RASTER
        sta     rasterin

        jsr     tick

        ; Cost of the tick in raster lines.  Line 10 plus a cost under 40 can
        ; never reach the 263 wrap, so the subtract needs no wrap case.
        lda     RASTER
        sec
        sbc     rasterin
        sta     irq_last
        cmp     irq_hwm         ; a high-water MARK, not a sample: per-frame
        bcc     irqout          ; cost spikes only on the frames that do the
        sta     irq_hwm         ; expensive thing, and a sampler steps over them
irqout: pla
        tay
        pla
        tax
        pla
        rti

; ---------------------------------------------------------------------------
; tick -- the whole per-frame job, and a subroutine ending in rts so that
; `c64 profile tick` can price it: profiling masks interrupts, so it can price a
; routine but not a handler in situ.  The handler is the wrapper; this is the
; job.
tick:   jsr     ball_step
        jsr     sound_step
        rts

; ===========================================================================
; ca65 does not reset the active segment at a file boundary, so every one of
; these opens with its own .segment directive.  Order matters in one place:
; sprites.inc must be the first thing linked into SPRITES so its first block is
; $2800 / 64 = 160, and shadow.inc follows it at 224.
        .include "vars.s"
        .include "room.s"
        .include "ball.s"
        .include "sound.s"
        .include "sprites.inc"
        .include "chars.inc"
        .include "screen.inc"
        .include "shadow.inc"
        .include "bounce.inc"
        .include "sound.inc"
