; vars.s — every variable and every table the game reads.
;
; BSS is address space, not file bytes: at load these hold whatever was in
; RAM, so `start` zeroes the whole block (bsstart..bssend) before anything
; reads one.  `hidig` lives in here too and is zeroed exactly once, at
; `start` — `newgame` must never touch it, which is what makes the high
; score survive into the next game.

        .segment "BSS"

bsstart:
gstate:   .res 1        ; 0 = title, 1 = play, 2 = game over
keycode:  .res 1        ; last matrix code seen at $CB (64 = none)
keyarm:   .res 1        ; the keyboard has been seen empty since this screen
                        ; appeared — see pollkey
curdir:   .res 1        ; direction of the last move: 0 up 1 down 2 left 3 right
newdir:   .res 1        ; direction the next move will take
hrow:     .res 1        ; head cell
hcol:     .res 1
nrow:     .res 1        ; the cell the head is moving into
ncol:     .res 1
head:     .res 1        ; ring index of the newest segment
tail:     .res 1        ; ring index of the oldest segment
snlen:    .res 1        ; segments currently drawn (<= MAXLEN)
grow:     .res 1        ; segments still owed from eating
ate:      .res 1        ; this move landed on food
level:    .res 1        ; 1-9
eaten:    .res 1        ; pickups since the last level-up
speed:    .res 1        ; jiffies per move, from spdtab
snakecol: .res 1        ; current snake colour, from lvcolor
newhi:    .res 1        ; this game beat the high score
scdig:    .res 4        ; score, one decimal digit per byte, most significant first
hidig:    .res 4        ; high score, same encoding — survives newgame
foodr:    .res 1        ; food cell (bookkeeping; the screen code is the truth)
foodc:    .res 1
seed:     .res 1        ; Galois LFSR state — never zero
sidshadow: .res 25      ; mirror of $D400-$D418 — the SID is write-only, so
                        ; this array is the only readable evidence for sound
sfxlen:   .res 1        ; jiffies until sfxoff gates the voice down
sfxreg:   .res 1        ; control register offset of the sounding voice
sfxctl:   .res 1        ; the value that gates it off (waveform, gate clear)
pcolor:   .res 1        ; colour the drawing primitives write
pcodeor:  .res 1        ; ORed into every screen code they write — see putcell
clrcol:   .res 1        ; colour clrscr paints into every cell
row8:     .res 1        ; plotaddr scratch
dcnt:     .res 1        ; putdig digit count
pcnt:     .res 1        ; pace: jiffies left
pjlast:   .res 1        ; pace: the jiffy value being waited out
rccnt:    .res 1        ; recolor: segments left
ptsleft:  .res 1        ; eat: tens of points still to add
bcidx:    .res 1        ; bigchar: letter index
bccol:    .res 1        ; bigchar: left column
bcrow:    .res 1        ; bigchar: row within the 5-row glyph
bcbits:   .res 1        ; bigchar: the row's four column bits
dtidx:    .res 1        ; drawtitle: which of the five letters
bodylo:   .res 256      ; ring buffer of segment SCREEN addresses
bodyhi:   .res 256
bssend:

; ---------------------------------------------------------------------------

        .segment "RODATA"

; jiffies per move, by level.  60 Hz, so level 1 is 5 moves/second and level
; 9 is 30 — the top of what $CB steering can still be aimed at.
spdtab:   .byte 12, 10, 8, 7, 6, 5, 4, 3, 2

; snake colour by level.  Nine distinct hues, none of them the border's
; light blue (14), the food's red (2) or the black background.
lvcolor:  .byte 5, 13, 7, 8, 10, 4, 3, 15, 1

; direction 0 up, 1 down, 2 left, 3 right
rowdelta: .byte $ff, $01, $00, $00
coldelta: .byte $00, $00, $ff, $01
headcode: .byte HEADUP, HEADDN, HEADLF, HEADRT

; bigchar: bits 3-0 select the four columns of each 5-row title letter
bcmask:   .byte 8, 4, 2, 1

; S N A K E, five rows each, bits 3-0 = columns 0-3
bigfont:  .byte %1111, %1000, %1111, %0001, %1111   ; S
          .byte %1001, %1101, %1011, %1001, %1001   ; N
          .byte %0110, %1001, %1111, %1001, %1001   ; A
          .byte %1001, %1010, %1100, %1010, %1001   ; K
          .byte %1111, %1000, %1110, %1000, %1111   ; E

titlecol: .byte 7, 10, 13, 3, 14

; every string is uppercase ASCII: ca65 does no translation, and ASCII
; $41-$5A coincides with PETSCII's letters, which putstr folds to screen
; codes by subtracting $40.
msscore:  .byte "SCORE", 0
mslevel:  .byte "LEVEL", 0
mshi:     .byte "HI", 0
mspress:  .byte "PRESS ANY KEY TO PLAY", 0
mssteer:  .byte "W A S D TO STEER", 0
mshiscr:  .byte "HIGH SCORE", 0
msmade:   .byte "6502 ASSEMBLY ON A REAL EMULATED C64", 0
msover:   .byte "GAME OVER", 0
msnewhi:  .byte "NEW HIGH SCORE", 0
msagain:  .byte "PRESS SPACE TO PLAY AGAIN", 0
