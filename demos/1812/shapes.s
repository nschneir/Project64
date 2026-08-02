; shapes.s — the shape vocabulary and the fill masks.
;
; Everything here is authored as commented .byte rows per
; docs/graphics-and-sprites.md section 2 — no binary blobs, and the numbers
; are readable as the thing they draw.

        .segment "RODATA"

; ==========================================================================
; Ink bits.  A multicolour bitmap byte is four pixels of two bits each, so an
; ink is its bit-pair replicated four times (SPEC.md 3).
;   0 = background ($D021, black)   1 = screen high nybble
;   2 = screen low nybble           3 = colour RAM
; ==========================================================================

inkbits:
        .byte   %00000000       ; 0 — never used as an ink; shapes use 1..3
        .byte   %01010101       ; 1
        .byte   %10101010       ; 2
        .byte   %11111111       ; 3

; ==========================================================================
; Span edge masks.  A span starts and ends mid-cell, so the first and last
; bytes are painted through these; the cells between need no edge test.
; ==========================================================================

; keep pixels (spxa & 3) .. 3
leftmask:
        .byte   %11111111, %00111111, %00001111, %00000011

; keep pixels 0 .. ((spxb - 1) & 3)
rightmask:
        .byte   %11000000, %11110000, %11111100, %11111111

; ==========================================================================
; Dither masks — eight 8x8 patterns, 8 rows of 2 bytes each (8 pixels wide).
; A pixel's bit-pair is 11 to paint or 00 to leave what is underneath, so a
; masked fill reads as translucency over whatever the canvas already holds.
;
; The mask is indexed by (y & 7) for the row and by cell-column parity for
; the byte, so the pattern is locked to the SCREEN, not to the shape:
; overlapping shapes interleave instead of moiring.
;
; Index: dither + pattern*16 + (y & 7)*2, then +0 for even cells, +1 for odd.
; ==========================================================================

dither:
        ; --- 0: solid ---------------------------------------------------
        ;   ########
        ;   ########  (all eight rows)
        .byte   $ff, $ff
        .byte   $ff, $ff
        .byte   $ff, $ff
        .byte   $ff, $ff
        .byte   $ff, $ff
        .byte   $ff, $ff
        .byte   $ff, $ff
        .byte   $ff, $ff

        ; --- 1: 50% checker, on where (x + y) is even -------------------
        ;   # # # #
        ;    # # # #
        .byte   %11001100, %11001100
        .byte   %00110011, %00110011
        .byte   %11001100, %11001100
        .byte   %00110011, %00110011
        .byte   %11001100, %11001100
        .byte   %00110011, %00110011
        .byte   %11001100, %11001100
        .byte   %00110011, %00110011

        ; --- 2: vertical stripes, 2 px on / 2 px off --------------------
        ;   ##  ##
        ;   ##  ##  (all eight rows)
        .byte   %11110000, %11110000
        .byte   %11110000, %11110000
        .byte   %11110000, %11110000
        .byte   %11110000, %11110000
        .byte   %11110000, %11110000
        .byte   %11110000, %11110000
        .byte   %11110000, %11110000
        .byte   %11110000, %11110000

        ; --- 3: horizontal stripes, 2 rows on / 2 rows off --------------
        ;   ########
        ;   ########
        ;   ........
        ;   ........
        .byte   $ff, $ff
        .byte   $ff, $ff
        .byte   $00, $00
        .byte   $00, $00
        .byte   $ff, $ff
        .byte   $ff, $ff
        .byte   $00, $00
        .byte   $00, $00

        ; --- 4: diagonal, on where (x + y) & 3 == 0 ---------------------
        ;   #...#...
        ;   ...#...#
        ;   ..#...#.
        ;   .#...#..
        .byte   %11000000, %11000000
        .byte   %00000011, %00000011
        .byte   %00001100, %00001100
        .byte   %00110000, %00110000
        .byte   %11000000, %11000000
        .byte   %00000011, %00000011
        .byte   %00001100, %00001100
        .byte   %00110000, %00110000

        ; --- 5: sparse dots, 1 pixel in 16 ------------------------------
        ;   #...#...
        ;   ........
        ;   ........
        ;   ........
        .byte   %11000000, %11000000
        .byte   %00000000, %00000000
        .byte   %00000000, %00000000
        .byte   %00000000, %00000000
        .byte   %11000000, %11000000
        .byte   %00000000, %00000000
        .byte   %00000000, %00000000
        .byte   %00000000, %00000000

        ; --- 6: cross-hatch, on where x&3 == 0 or y&3 == 0 --------------
        ;   ########
        ;   #...#...
        ;   #...#...
        ;   #...#...
        .byte   %11111111, %11111111
        .byte   %11000000, %11000000
        .byte   %11000000, %11000000
        .byte   %11000000, %11000000
        .byte   %11111111, %11111111
        .byte   %11000000, %11000000
        .byte   %11000000, %11000000
        .byte   %11000000, %11000000

        ; --- 7: quarter tone, on where x and y are both even ------------
        ;   # # # #
        ;   ........
        ;   # # # #
        ;   ........
        .byte   %11001100, %11001100
        .byte   %00000000, %00000000
        .byte   %11001100, %11001100
        .byte   %00000000, %00000000
        .byte   %11001100, %11001100
        .byte   %00000000, %00000000
        .byte   %11001100, %11001100
        .byte   %00000000, %00000000

NPAT    = 8

; ==========================================================================
; The shape vocabulary (SPEC.md section 4).
;
; Unit vertices in ISOTROPIC screen-pixel space, radius 64 (Q6, so 64 = 1.0).
; They are rotated in that square-pixel space and only then projected onto
; the 160-wide multicolour grid by halving x — which is what makes a rotated
; square a square on screen instead of a sheared rhombus (SPEC.md 5.3).
;
; Angles below are measured with y pointing DOWN, the way the screen does, so
; "apex up" is (0, -64).
; ==========================================================================

; vertex counts, indexed by sh_type
shpn:   .byte   3, 4, 5, 6, 10, 16, 12, 16, 8, 12

; index of each type's first vertex in shpvx/shpvy
shpoff: .byte   0, 3, 7, 12, 18, 28, 44, 56, 72, 80

shpvx:
        ; 0 triangle — equilateral, apex up: 64*cos(-90 + k*120)
        .byte     0,  55, <-55
        ; 1 rectangle — a square, corners at 64/sqrt(2) = 45
        .byte   <-45,  45,  45, <-45
        ; 2 pentagon — 64*cos(-90 + k*72)
        .byte     0,  61,  38, <-38, <-61
        ; 3 hexagon — 64*cos(-90 + k*60)
        .byte     0,  55,  55,   0, <-55, <-55
        ; 4 star5 — outer r 64 at -90+k*72, inner r 25 at -54+k*72
        .byte     0,  15,  61,  24,  38,   0, <-38, <-24, <-61, <-15
        ; 5 circle — 16-gon, r 64, 64*cos(k*22.5)
        .byte    64,  59,  45,  24,   0, <-24, <-45, <-59
        .byte   <-64, <-59, <-45, <-24,   0,  24,  45,  59
        ; 6 oval — 12-gon, x 64 / y 48
        .byte    64,  55,  32,   0, <-32, <-55
        .byte   <-64, <-55, <-32,   0,  32,  55
        ; 7 ellipse — 16-gon, x 64 / y 26; a rotated one visibly tilts
        .byte    64,  59,  45,  24,   0, <-24, <-45, <-59
        .byte   <-64, <-59, <-45, <-24,   0,  24,  45,  59
        ; 8 star4 — outer r 64 on the axes, inner r 20 on the diagonals
        .byte     0,  14,  64,  14,   0, <-14, <-64, <-14
        ; 9 cross — a plus sign, arm half-width 22, arm length 64
        .byte   <-22,  22,  22,  64,  64,  22
        .byte    22, <-22, <-22, <-64, <-64, <-22

shpvy:
        ; 0 triangle
        .byte   <-64,  32,  32
        ; 1 rectangle
        .byte   <-45, <-45,  45,  45
        ; 2 pentagon
        .byte   <-64, <-20,  52,  52, <-20
        ; 3 hexagon
        .byte   <-64, <-32,  32,  64,  32, <-32
        ; 4 star5
        .byte   <-64, <-20, <-20,   8,  52,  25,  52,   8, <-20, <-20
        ; 5 circle
        .byte     0,  24,  45,  59,  64,  59,  45,  24
        .byte     0, <-24, <-45, <-59, <-64, <-59, <-45, <-24
        ; 6 oval
        .byte     0,  24,  42,  48,  42,  24
        .byte     0, <-24, <-42, <-48, <-42, <-24
        ; 7 ellipse
        .byte     0,  10,  18,  24,  26,  24,  18,  10
        .byte     0, <-10, <-18, <-24, <-26, <-24, <-18, <-10
        ; 8 star4
        .byte   <-64, <-14,   0,  14,  64,  14,   0, <-14
        ; 9 cross
        .byte   <-64, <-64, <-22, <-22,  22,  22
        .byte    64,  64,  22,  22, <-22, <-22

NSHAPE  = 10
