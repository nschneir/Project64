; vars.s — every mutable byte in the demo.
;
; The observable block lives in DATA, not BSS: BSS is not in the .prg, so a
; .res byte holds whatever was in RAM at load time (often $AA).  Everything a
; test or `c64 until` reads is initialised by the file itself, and `init`
; re-initialises it anyway so a restart behaves like a fresh load.
;
; SPEC.md section 8 is the contract this file implements; the labels here are
; the names tests use.

        .segment "DATA"

; ---- the observable block (SPEC.md section 8) ----------------------------

seed:   .word   $1812           ; RNG seed.  POKE THIS BEFORE RUN to pin a run.
rng:    .word   0               ; live 16-bit Galois LFSR state
frames: .word   0               ; frames since the run started
section: .byte  0               ; 0..5, the current section
secframe: .word 0               ; frames elapsed inside the current section
noteidx: .byte  0               ; events consumed from voice 1 this section
shapes: .word   0               ; shapes completed
dropped: .byte  0               ; spawn requests dropped (queue was full)
cannons: .byte  0               ; cannon shots fired
flash:  .byte   0               ; frames of screen flash remaining
painting: .byte 0               ; 1 while the rasteriser is inside a shape
qhead:  .byte   0               ; spawn ring buffer write index
qtail:  .byte   0               ; spawn ring buffer read index
lstype: .byte   0               ; last shape: type 0..9
lssize: .byte   0               ; last shape: radius in screen pixels
lsx:    .byte   0               ; last shape: centre x, multicolour pixels
lsy:    .byte   0               ; last shape: centre y, screen rows
lsangle: .byte  0               ; last shape: angle 0..255
lspat:  .byte   0               ; last shape: dither pattern 0..7
lsink:  .byte   0               ; last shape: ink bit-pair 1..3
lsbytes: .word  0               ; bitmap bytes the last shape wrote
typeseen: .word 0               ; bitmask of shape types drawn; $03FF = all ten
patseen: .byte  0               ; bitmask of dither patterns used; $FF = all
sidshadow: .res 25, 0           ; shadow of $D400-$D418 (SPEC.md section 6.5)

; ---- the shape parameter block — drawshape's inputs ----------------------

sh_type: .byte  0
sh_size: .byte  0               ; radius in SCREEN pixels (x is halved later)
sh_cx:  .byte   0               ; centre, multicolour pixels 0..159
sh_cy:  .byte   0               ; centre, screen rows 0..199
sh_angle: .byte 0
sh_pat: .byte   0
sh_ink: .byte   0               ; 1..3

; ---- the live palette, written by setpal and read by spanfill ------------

palscr: .byte   0               ; screen-RAM byte: (c01 << 4) | c10
palcol: .byte   0               ; colour-RAM byte: c11

; ---- span fill scratch ---------------------------------------------------

spy:    .byte   0               ; row 0..199
spxa:   .byte   0               ; span start, multicolour pixels
spxb:   .byte   0               ; span end (exclusive), 1..160
dm0:    .byte   0               ; raw dither mask, even cell columns
dm1:    .byte   0               ; raw dither mask, odd cell columns
spca:   .byte   0               ; first cell column
spcb:   .byte   0               ; last cell column
spcb1:  .byte   0               ; spcb + 1, the attribute loop's limit
sfpb:   .byte   0               ; spxb - 1, the last painted pixel
cpar:   .byte   0               ; parity of the cell column being painted
sfink:  .byte   0               ; ink bits, replicated four times
sflm:   .byte   0               ; left edge mask
sfrm:   .byte   0               ; right edge mask
sfm:    .byte   0               ; working mask for one cell
sfand:  .byte   0               ; its complement
sfor:   .byte   0               ; ink AND mask

; ---- the IRQ wedge -------------------------------------------------------

oldvec: .word   0               ; the CINV value we chained from

; ==========================================================================
; Rasteriser working storage — at $C200, NOT in BSS.
;
; With the bitmap at $2000 the program has under a hundred bytes of headroom
; below it, and these arrays are about 370.  $C000-$CFFF is the 4 KB BASIC
; never touches: $C000-$C1FF holds the quarter-square multiply tables that
; `qsgen` builds, and $C200-$C3FF holds this.  Neither is in the .prg and
; neither needs to be visible to the VIC-II, which cannot see $C000 anyway.
;
; Laid out as explicit offsets rather than .res so the block is one contiguous
; region `rwzero` can clear with a single loop.  Keep the map below in sync
; with the offsets — RWEND is asserted against the block size.
; ==========================================================================

MAXV    = 16                    ; vertices per shape
MAXE    = 16                    ; edges per shape
MAXX    = 8                     ; crossings per scanline

RWORK   = $C400
RWSIZE  = $0200

vxl      = RWORK + $000         ; transformed vertex x, 16-bit signed
vxh      = RWORK + $010
vyl      = RWORK + $020         ; transformed vertex y, 16-bit signed
vyh      = RWORK + $030
eytl     = RWORK + $040         ; edge top y
eyth     = RWORK + $050
eybl     = RWORK + $060         ; edge bottom y
eybh     = RWORK + $070
exl      = RWORK + $080         ; edge current x
exh      = RWORK + $090
edxl     = RWORK + $0A0         ; |dx|
edxh     = RWORK + $0B0
edyl     = RWORK + $0C0         ; dy, always > 0
edyh     = RWORK + $0D0
eerl     = RWORK + $0E0         ; DDA error accumulator
eerh     = RWORK + $0F0
esx      = RWORK + $100         ; x step: $01 or $FF
eord     = RWORK + $110         ; edge indices sorted by ytop
aet      = RWORK + $120         ; active edge indices
crossl   = RWORK + $130         ; crossings on the current scanline (MAXX)
crossh   = RWORK + $138
stamped  = RWORK + $140         ; per-cell "already claimed in this cell row"
nvert    = RWORK + $168
nedge    = RWORK + $169
naet     = RWORK + $16A
enext    = RWORK + $16B         ; index into eord of the next edge to admit
ncross   = RWORK + $16C
maxcross = RWORK + $16D         ; high-water mark — proves the MAXX ceiling
stampcr  = RWORK + $16E         ; which cell row `stamped` describes
syminl   = RWORK + $16F         ; shape y extent, 16-bit signed
syminh   = RWORK + $170
symaxl   = RWORK + $171
symaxh   = RWORK + $172
scany    = RWORK + $173         ; the scanline loop's y, 16-bit signed
RWEND    = RWORK + $175

        .assert (RWEND - RWORK) <= RWSIZE, error, "1812: the $C200 work block overflows its 512 bytes"

        ; named so tests and `c64 until` can reach them
        .export vxl, vxh, vyl, vyh, nvert, nedge, eord, aet, naet, enext
        .export exl, exh, edxl, edxh, edyl, edyh, esx, eytl, eyth, eybl, eybh
        .export crossl, crossh, ncross, maxcross, scany
        .export syminl, syminh, symaxl, symaxh, stamped, stampcr

        .segment "BSS"

queue:  .res    16              ; spawn ring buffer payloads

; ---- sequencer state, all indexed by voice 0..2 --------------------------
; Parallel byte arrays rather than packed 16-bit entries, so `dec vcnt,x`
; works: the 6502 has no `dec abs,y`, and indexing these by X is what keeps
; the per-voice code short.

vptrl:  .res    3               ; stream read pointer
vptrh:  .res    3
vbasel: .res    3               ; the section's stream head, for the $FF rewind
vbaseh: .res    3
vcnt:   .res    3               ; frames left on the current event (max 255)
vnote:  .res    3               ; current note, or 0 for a rest
vrel:   .res    3               ; 1 once this note has been released
vwave:  .res    3               ; the section's waveform byte, gate bit clear
vcur:   .res    1               ; the voice voicetick is serving
gnv:    .res    1               ; sidput value in transit
gnr:    .res    1               ; sidput register base in transit
lisrc:  .res    1               ; loadinstr: index into secinstr
liidx:  .res    1               ; loadinstr: which of the five bytes
livoice: .res   1               ; loadinstr: which voice
lival:  .res    1               ; loadinstr: the byte in transit
cfn:    .res    1               ; small loop counter for routines that JSR

cutoff: .res    1               ; cannon filter cutoff, swept down
csweep: .res    1               ; cannon sweep frames left
pwphase: .res   1               ; pulse-width LFO phase

; ---- smul / xform scratch ------------------------------------------------

smSgn:  .res    1               ; multiply: 1 if the product is negative
xsc:    .res    1               ; (cos(angle) * size) >> 7
xss:    .res    1               ; (sin(angle) * size) >> 7
ux:     .res    1               ; the unit vertex being transformed
uy:     .res    1
t0:     .res    1               ; 16-bit signed accumulator for the transform
t1:     .res    1
t2:     .res    1               ; second 16-bit scratch, span clipping
t3:     .res    1
tt:     .res    1               ; shr6's intermediate
dxy:    .res    1               ; the transformed offset, signed byte
sgnb:   .res    1               ; its sign extension, $00 or $FF
vidx:   .res    1               ; running index into shpvx/shpvy
flo:    .res    1               ; qsgen: f(x), the running quarter square
fhi:    .res    1
dlt:    .res    1               ; qsgen: its first difference
qspg:   .res    1               ; qsgen: which 256-entry half

; ---- buildedges / scanfill scratch ---------------------------------------

bei:    .res    1               ; edge build: this vertex
bej:    .res    1               ; edge build: the next vertex, wrapped
betop:  .res    1               ; edge build: the upper vertex of this edge
bebot:  .res    1               ; edge build: the lower one
bswap:  .res    1               ; bubble-sort dirty flag
aetw:   .res    1               ; active-edge table compaction write index
aetrd:  .res    1               ; ...and its read index
pairi:  .res    1               ; crossing-pair loop index

; ---- spawn scratch --------------------------------------------------------

qpv:    .res    1               ; queue payload in transit
pspay:  .res    1               ; the payload pickshape is serving
psn:    .res    1               ; how many types the section allows
psi:    .res    1               ; mask scan index
pslist: .res    10              ; the allowed types, flattened out of the mask

; The bitmap starts at $2000 and BSS is the last thing allocated below it, so
; this is where the program would silently start painting over its own canvas.
; A deferred linker assertion, not a habit of checking the map by hand.
        .assert (__BSS_LOAD__ + __BSS_SIZE__) <= BITMAP, error, "1812: BSS overruns the bitmap at $2000 — the program is too big"
        .assert (<oldvec) <> $ff, error, "1812: oldvec's low byte is $FF — jmp (oldvec) would hit the 6502 indirect-jump page bug"

