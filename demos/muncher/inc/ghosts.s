; ghosts.s — Bruiser, Pixie, Ivy, Sable (actors 1-4). HOT PATH.
;
; Spec §7: Ms.-style scatter/chase schedule (random-scatter for Bruiser and
; Pixie, corner targets for Ivy and Sable, reversals at ~7 s and ~25 s, then
; chase effectively forever), arcade targeting rules including Pixie's
; up-quirk, dot-counter/timeout house releases, tunnel slowdown.
;
; Ghost states (gstate): 0 housed, 1 normal, 4 exiting the house.
; (2 frightened and 3 eyes arrive with T7.)

GST_HOUSED = 0
GST_NORM   = 1
GST_FRIGHT = 2
GST_EYES   = 3
GST_EXIT   = 4

GSPD_NORM  = $3C                ; board-1 class: ghosts 75% (T11 tables)
GSPD_TUN   = $20                ; tunnel zone 40%

        .segment "CODE"

; ---- ghost_init: board-start placement (spec §5) ----
ghost_init:
        ldx     #1              ; Bruiser: above the door, heading left
        lda     #27
        sta     ax,x
        lda     #18             ; row 9
        sta     ay,x
        lda     #DIR_LEFT
        sta     adir,x
        lda     #GST_NORM
        sta     gstate,x
        lda     #G_BRUISER
        sta     aglyph,x
        jsr     gh_common
        ldx     #2              ; Pixie: house centre
        lda     #27
        sta     ax,x
        lda     #G_PIXIE
        jsr     gh_house
        ldx     #3              ; Ivy: house left
        lda     #24
        sta     ax,x
        lda     #G_IVY
        jsr     gh_house
        ldx     #4              ; Sable: house right
        lda     #30
        sta     ax,x
        lda     #G_SABLE
        jsr     gh_house
        lda     #0              ; release bookkeeping (board 1 limits; T11)
        sta     gdcnt
        sta     sched_state
        lda     #<420           ; scatter #1: ~7 s to the first reversal
        sta     sched_t
        lda     #>420
        sta     sched_t+1
        lda     #<240           ; 4 s no-dot timeout forces a release
        sta     gtimeout
        lda     #>240
        sta     gtimeout+1
        lda     #1
        sta     gon
        rts

gh_house:
        sta     aglyph,x
        lda     #22             ; house interior row 11
        sta     ay,x
        lda     #GST_HOUSED
        sta     gstate,x
        lda     #DIR_NONE
        sta     adir,x
gh_common:
        lda     #$FF
        sta     gdecx,x
        sta     gdecy,x
        lda     #1
        sta     arev,x          ; ghosts render reverse-video
        lda     #GSPD_NORM
        sta     aspd,x
        lda     #0
        sta     aacc,x
        sta     apause,x
        jmp     draw_blob

; ---- ghosts_tick: once per jiffy, after player_tick ----
ghosts_tick:
        lda     gon             ; test hook: 0 freezes the ghost world
        bne     gt0
        lda     #0
        sta     eat_ev
        rts
gt0:    lda     eat_ev
        cmp     #2
        bne     gt01
        jsr     fright_on       ; energizer: reversal + blue time
gt01:   cmp     #1
        bne     gt02
        jsr     elroy_calc      ; dot count moved: refresh elroy stage
gt02:   jsr     fright_tick
        jsr     gh_release
        ldx     #1
gt1:    jsr     ghost_tick
        inx
        cpx     #5
        bne     gt1
        jsr     sched_tick
        lda     #0              ; the eat event is consumed by now
        sta     eat_ev
        rts

; ---- fright_on: spec §9. Reverse everyone; blue time from the board ----
fright_on:
        jsr     rev_all
        lda     #0
        sta     fchain
        ldy     board           ; 1-based, saturated at 21 by the board code
        lda     bluelo-1,y
        sta     frite_t
        lda     bluehi-1,y
        sta     frite_t+1
        ora     frite_t
        beq     fo_done         ; boards with no blue time: reversal only
        ldx     #1
fo1:    lda     gstate,x
        cmp     #GST_NORM
        bne     fo2
        lda     #GST_FRIGHT
        sta     gstate,x
        lda     #G_RING+128     ; reversed: SHE is the only non-reverse
        sta     aglyph,x        ; actor, even mid-step
fo2:    inx
        cpx     #5
        bne     fo1
fo_done:rts

; ---- fright_tick: countdown, warning flash, restore ----
fright_tick:
        lda     frite_t
        ora     frite_t+1
        bne     ft1
        rts
ft1:    lda     frite_t
        bne     ft2
        dec     frite_t+1
ft2:    dec     frite_t
        lda     frite_t
        ora     frite_t+1
        beq     ft_end
        ; warning flash: inside the last flashes*28 jiffies, toggle reverse
        ; video every 14 jiffies (5 flashes normally, 3 on the short boards)
        lda     frite_t+1
        bne     ft_out
        ldy     board
        lda     flashtbl-1,y
        cmp     frite_t         ; window = flashes*28 (table holds it)
        bcc     ft_out
        ldx     #1
ft3:    lda     gstate,x
        cmp     #GST_FRIGHT
        bne     ft4
        lda     frite_t
        lsr
        lsr
        lsr
        lsr                     ; /16 ~ 14-jiffy-ish phase, cheap and steady
        and     #1
        beq     ftw
        lda     #G_RING         ; white flash frame
        bne     ftw2
ftw:    lda     #G_RING+128
ftw2:   sta     aglyph,x
ft4:    inx
        cpx     #5
        bne     ft3
ft_out: rts
ft_end: ldx     #1              ; blue time over: back to the hunt
fe1:    lda     gstate,x
        cmp     #GST_FRIGHT
        bne     fe2
        lda     #GST_NORM
        sta     gstate,x
        lda     glyphtbl,x
        sta     aglyph,x
        lda     #1
        sta     arev,x
fe2:    inx
        cpx     #5
        bne     fe1
        rts

; ---- elroy_calc: stage 0/1/2 from the scaled per-board thresholds ----
elroy_calc:
        lda     #0
        sta     elvl
        lda     dots_left+1
        bne     ec_done         ; > 255 dots left: never
        lda     gdmode          ; suspended while the post-death house
        bne     ec_done         ; counters are still releasing (arcade rule)
        ldy     board
        lda     dots_left
        cmp     elroy2_tbl-1,y
        beq     ec2
        bcs     ec1
ec2:    lda     elroy2_tbl-1,y
        beq     ec_done         ; 0 = table off
        lda     #2
        sta     elvl
        rts
ec1:    cmp     elroy1_tbl-1,y
        beq     ec3
        bcs     ec_done
ec3:    lda     elroy1_tbl-1,y
        beq     ec_done
        lda     #1
        sta     elvl
ec_done:rts

; ---- gh_release: house dot counters and the no-dot timeout ----
gh_release:
        ldx     #2              ; preferred = first housed of Pixie,Ivy,Sable
gr1:    lda     gstate,x
        cmp     #GST_HOUSED
        beq     gr2
        inx
        cpx     #5
        bne     gr1
        lda     #0              ; house empty: normal counters resume
        sta     gdmode
        rts
gr2:    lda     eat_ev
        cmp     #1
        bne     gr3
        inc     gdcnt           ; a dot: bump the counter, c64 the watchdog
        lda     #<240
        sta     gtimeout
        lda     #>240
        sta     gtimeout+1
gr3:    lda     gdmode          ; post-death: the global counter table
        beq     gr30
        lda     gdcnt
        cmp     glimitG,x
        bcs     gr_go
        jmp     gr31
gr30:   lda     gdcnt
        cmp     glimit,x        ; enough dots for the preferred ghost?
        bcs     gr_go
gr31:
        lda     gtimeout        ; or has the no-dot timeout expired?
        bne     gr4
        lda     gtimeout+1
        beq     gr_go
        dec     gtimeout+1
gr4:    dec     gtimeout
        rts
gr_go:  lda     #GST_EXIT       ; release: walk to the door column, then up
        sta     gstate,x
        lda     #0
        sta     gdcnt           ; next ghost counts afresh (close enough to
        lda     #<240           ; the arcade's per-ghost counters)
        sta     gtimeout
        lda     #>240
        sta     gtimeout+1
        rts

; ---- ghost_tick: X = ghost actor ----
ghost_tick:
        lda     gstate,x
        cmp     #GST_HOUSED
        bne     gk1
        rts                     ; sits tight (arcade pacing is cosmetic)
gk1:    cmp     #GST_EXIT
        bne     gk2
        jsr     gh_exit
        jmp     coll_check
gk2:    lda     ax,x
        sta     gprex           ; pre-step position (swap-past detection)
        lda     ay,x
        sta     gprey
        lda     ax,x            ; at a cell centre? decide a direction —
        ora     ay,x            ; but only ONCE per arrival (the arcade
        and     #1              ; decides per tile; re-deciding lets a ghost
        bne     gk3             ; re-pick the way it came and shuttle)
        lda     ax,x
        cmp     gdecx,x
        bne     gk2d
        lda     ay,x
        cmp     gdecy,x
        beq     gk3
gk2d:   lda     ax,x
        sta     gdecx,x
        lda     ay,x
        sta     gdecy,x
        jsr     ghost_decide
gk3:    jsr     gh_speed
        jsr     step_actor
        ; eyes reaching the house interior turn back into a ghost
        lda     gstate,x
        cmp     #GST_EYES
        bne     gk4
        lda     ay,x
        lsr
        cmp     #11
        bne     gk4
        lda     #GST_EXIT       ; revived: walk back out
        sta     gstate,x
        lda     glyphtbl,x
        sta     aglyph,x
        lda     #1
        sta     arev,x
gk4:    jmp     coll_check

; ---- coll_check: X = ghost. Player contact: same half-cell, or the two
; swapped cells in one jiffy (no arcade pass-through bug — spec §4) ----
coll_check:
        lda     gstate,x
        cmp     #GST_EYES
        bne     ck0
        rts                     ; eyes are harmless and inedible
ck0:    cmp     #GST_HOUSED
        bne     ck1
        rts
ck1:    lda     ax,x
        cmp     ax
        bne     ck2
        lda     ay,x
        cmp     ay
        beq     ck_hit          ; coincident
ck2:    lda     ax,x            ; swap-past: ghost sits on her PRE-step cell
        cmp     ppx             ; while she sits on its pre-step cell
        bne     ck_out
        lda     ay,x
        cmp     ppy
        bne     ck_out
        lda     gprex
        cmp     ax
        bne     ck_out
        lda     gprey
        cmp     ay
        beq     ck_hit
ck_out: rts
ck_hit: lda     gstate,x
        cmp     #GST_FRIGHT
        beq     ck_eat
        lda     #1              ; a live ghost: she dies
        sta     game_state
        lda     #0
        sta     death_t
        lda     #FX_DEATH
        jsr     snd_play
        rts
ck_eat: lda     #GST_EYES       ; frightened ghost eaten
        sta     gstate,x
        lda     #G_QUOTE
        sta     aglyph,x
        lda     #0
        sta     arev,x
        inc     fchain          ; 200/400/800/1600 chain
        lda     fchain
        cmp     #5
        bcc     ce1
        lda     #4              ; (5th+ can't happen; clamp anyway)
ce1:    clc
        adc     #SC_GH1-1
        pha
        jsr     addscore
        lda     #FX_GHOST
        jsr     snd_play
        pla
        jsr     popup_at        ; show the value where the ghost was
        lda     #30             ; the arcade's little gulp freeze
        sta     apause
        sta     apause+1
        sta     apause+2
        sta     apause+3
        sta     apause+4
        lda     #0              ; eyes fly immediately after the freeze
        sta     apause,x
        rts

; ---- gh_exit: scripted walk out of the house ----
gh_exit:
        lda     #GSPD_NORM
        sta     aspd,x
        lda     ay,x
        cmp     #18             ; reached row 9: outside
        bne     ge1
        lda     ax,x
        and     #1
        bne     ge1
        lda     #GST_NORM       ; free — join the fray heading left
        sta     gstate,x
        lda     #DIR_LEFT
        sta     adir,x
        rts
ge1:    lda     ax,x
        cmp     #26             ; align to door col 13 (or 14 if right of it)
        beq     ge_up
        bcs     ge2
        lda     #DIR_RIGHT      ; left of the door: head right
        sta     adir,x
        jmp     step_actor
ge2:    cmp     #28
        beq     ge_up
        lda     #DIR_LEFT
        sta     adir,x
        jmp     step_actor
ge_up:  lda     #DIR_UP
        sta     adir,x
        jmp     step_actor

; ---- gh_speed: state + tunnel-zone speed selection ----
gh_speed:
        lda     gstate,x
        cmp     #GST_EYES
        bne     gv1
        lda     #$50            ; eyes race home at full arcade speed
        sta     aspd,x
        rts
gv1:    lda     ahid,x          ; hidden in the void: tunnel speed
        bne     gs_tun
        txa
        tay                     ; (Y borrows the actor index briefly)
        ldx     cur_maze
        lda     ay,y
        lsr
        cmp     tun_a-1,x
        beq     gs_row0
        cmp     tun_b-1,x
        beq     gs_row0
        tya
        tax
        jmp     gs_norm
gs_row0:tya
        tax
        jmp     gs_row          ; on a tunnel row: check the column zone
gs_norm:lda     gstate,x
        cmp     #GST_FRIGHT
        bne     gs_n2
        lda     #GSPD_FRIGHT
        sta     aspd,x
        rts
gs_n2:  lda     #GSPD_NORM
        cpx     #1              ; Bruiser: cruise elroy stages add speed
        bne     gs_set
        ldy     elvl
        beq     gs_set
        clc
        adc     elroybump,y
gs_set: sta     aspd,x
        rts
gs_row: lda     ax,x
        lsr
        cmp     #6              ; zone: cols 0-5 and 22-27
        bcc     gs_tun
        cmp     #22
        bcs     gs_tun
        jmp     gs_norm
gs_tun: lda     #GSPD_TUN
        sta     aspd,x
        rts

; ---- ghost_decide: X = ghost at a centre. Choose adir. ----
ghost_decide:
        lda     #0
        sta     gcn
        ldy     #DIR_UP         ; build candidates in arcade priority order
gd1:    sty     gdir
        lda     adir,x
        tay
        lda     opptbl,y
        cmp     gdir
        beq     gd_next         ; never reverse by choice
        ; door guard: normal/frightened ghosts may not step DOWN into it
        lda     gdir
        cmp     #DIR_DOWN
        bne     gdd
        lda     gstate,x
        cmp     #GST_EYES
        beq     gdd
        lda     ay,x
        lsr
        cmp     #9              ; from row 9...
        bne     gdd
        lda     ax,x
        lsr
        cmp     #13             ; ...into door cols 13/14
        beq     gd_next
        cmp     #14
        beq     gd_next
gdd:    ldy     gdir
        jsr     canmove_dir
        bcs     gd_next
        ldy     gcn             ; open: append
        lda     gdir
        sta     gcand,y
        inc     gcn
gd_next:ldy     gdir
        iny
        cpy     #4
        bne     gd1
        lda     gcn
        bne     gd3
        lda     adir,x          ; boxed in: forced reverse
        tay
        lda     opptbl,y
        sta     adir,x
        rts
gd3:    cmp     #1
        bne     gd4
        lda     gcand           ; corridor: the only way on
        sta     adir,x
        rts
gd4:    ; a junction: random for frightened, and for Bruiser/Pixie during
        ; the scatter windows (the Ms. anti-pattern randomiser)
        lda     gstate,x
        cmp     #GST_FRIGHT
        beq     gd_rand
        cmp     #GST_EYES
        bne     gd41
        ; Eyes navigate by region waypoints — pure greedy toward the door
        ; gets trapped in the pocket below the house (no upward exit near
        ; the door column there): below -> nearest ring-top corner (9,9)/
        ; (18,9); on the ring top -> the door mouth; in the door column ->
        ; the interior.
        lda     ay,x
        lsr
        cmp     #10
        bcs     et1
        lda     #13             ; at/above ring top: aim for the door mouth
        sta     ttx
        lda     #10
        sta     tty
        jmp     gd_scan
et1:    cmp     #12
        bcs     et_below
        lda     ax,x            ; rows 10-11: door/interior column dives in,
        lsr                     ; the ring side columns climb straight up
        cmp     #12
        bcc     et_side
        cmp     #16
        bcs     et_side
        lda     #13
        sta     ttx
        lda     #11
        sta     tty
        jmp     gd_scan
et_side:sta     ttx             ; A = own column (9 or 18)
        lda     #9
        sta     tty
        jmp     gd_scan
et_below:
        lda     ax,x
        lsr
        cmp     #14
        bcs     et_br
        lda     #9
        sta     ttx
        lda     #9
        sta     tty
        jmp     gd_scan
et_br:  lda     #18
        sta     ttx
        lda     #9
        sta     tty
        jmp     gd_scan
gd41:   lda     sched_state
        and     #1              ; states 0/2 = scatter windows
        bne     gd_tgt
        cpx     #1              ; elroy Bruiser hunts even in scatter
        bne     gd42
        lda     elvl
        bne     gd_tgt
gd42:   cpx     #3
        bcs     gd_tgt          ; Ivy/Sable still corner-target in scatter
gd_rand:jsr     lfsr
        and     #3
gdr1:   cmp     gcn
        bcc     gdr2
        sec
        sbc     gcn
        jmp     gdr1
gdr2:   tay
        lda     gcand,y
        sta     adir,x
        rts
gd_tgt: jsr     calc_target     ; -> ttx/tty
gd_scan:lda     #$FF
        sta     gbest
        sta     gbest+1
        ldy     #0
gt2:    sty     gci
        lda     gcand,y         ; candidate: distance^2 from the next cell
        tay
        lda     ax,x
        lsr
        clc
        adc     dxtbl2,y
        sta     etx
        lda     ay,x
        lsr
        clc
        adc     dytbl2,y
        sta     ety
        ; dx = |ttx - etx| (etx can be $FF/28 through a tunnel mouth: fine,
        ; the wrap candidate scores as far away, which the arcade also
        ; effectively does at mouths)
        lda     ttx
        sec
        sbc     etx
        bpl     gt3
        eor     #$FF
        adc     #1
gt3:    and     #$1F
        tay
        lda     sqtbl_lo,y
        sta     gd2
        lda     sqtbl_hi,y
        sta     gd2+1
        lda     tty
        sec
        sbc     ety
        bpl     gt4
        eor     #$FF
        adc     #1
gt4:    and     #$1F
        tay
        lda     gd2
        clc
        adc     sqtbl_lo,y
        sta     gd2
        lda     gd2+1
        adc     sqtbl_hi,y
        sta     gd2+1
        ; strict less-than keeps the first (highest-priority) on ties
        lda     gd2+1
        cmp     gbest+1
        bcc     gt_new
        bne     gt_old
        lda     gd2
        cmp     gbest
        bcs     gt_old
gt_new: lda     gd2
        sta     gbest
        lda     gd2+1
        sta     gbest+1
        ldy     gci
        lda     gcand,y
        sta     gpick
gt_old: ldy     gci
        iny
        cpy     gcn
        beq     :+
        jmp     gt2
:       lda     gpick
        sta     adir,x
        rts

; ---- calc_target: X = ghost. Chase/scatter target -> ttx/tty ----
calc_target:
        lda     sched_state
        and     #1
        bne     ct_chase
        cpx     #3              ; scatter: Ivy/Sable head for their corners
        bne     ct_sable_sc
        lda     #26
        sta     ttx
        lda     #23
        sta     tty
        rts
ct_sable_sc:
        cpx     #4
        bne     ct_chase        ; (Bruiser/Pixie never get here: randomised)
        lda     #1
        sta     ttx
        lda     #23
        sta     tty
        rts
ct_chase:
        lda     ax              ; player cell
        lsr
        sta     ttx
        lda     ay
        lsr
        sta     tty
        lda     ax+1            ; Bruiser's cell (Ivy's vector base)
        lsr
        sta     gbx
        lda     ay+1
        lsr
        sta     gby
        cpx     #1
        bne     ct2
        rts                     ; Bruiser: her cell, done
ct2:    cpx     #4
        bne     ct3
        ; Sable: her cell if further than 8 cells (d^2 > 64), else corner
        lda     ax,x
        lsr
        sec
        sbc     ttx
        bpl     ct41
        eor     #$FF
        adc     #1
ct41:   and     #$1F
        tay
        lda     sqtbl_lo,y
        sta     gd2
        lda     sqtbl_hi,y
        sta     gd2+1
        lda     ay,x
        lsr
        sec
        sbc     tty
        bpl     ct42
        eor     #$FF
        adc     #1
ct42:   and     #$1F
        tay
        lda     gd2
        clc
        adc     sqtbl_lo,y
        sta     gd2
        lda     gd2+1
        adc     sqtbl_hi,y
        bne     ct_far          ; high byte set: > 255 >> 64
        lda     gd2
        cmp     #65
        bcs     ct_far
        lda     #1              ; near: retreat target = home corner
        sta     ttx
        lda     #23
        sta     tty
ct_far: rts
ct3:    ; Pixie (n=4) / Ivy (n=2): n cells ahead, with the arcade up-quirk
        ; (facing up also shifts n left)
        lda     #4
        cpx     #2
        beq     ct5
        lda     #2
ct5:    sta     gnn
        ldy     adir            ; player's facing
        cpy     #DIR_UP
        bne     ct6
        lda     ttx             ; quirk: up also pulls the target left
        sec
        sbc     gnn
        sta     ttx
        lda     tty
        sec
        sbc     gnn
        sta     tty
        jmp     ct7
ct6:    lda     dxtbl2,y        ; +/-1 or 0
        beq     ct61
        bmi     ct62
        lda     ttx
        clc
        adc     gnn
        sta     ttx
        jmp     ct61
ct62:   lda     ttx
        sec
        sbc     gnn
        sta     ttx
ct61:   lda     dytbl2,y
        beq     ct7
        bmi     ct63
        lda     tty
        clc
        adc     gnn
        sta     tty
        jmp     ct7
ct63:   lda     tty
        sec
        sbc     gnn
        sta     tty
ct7:    cpx     #3
        beq     ct8
        jmp     ct_clamp        ; Pixie: done (clamped below)
ct8:    ; Ivy: double the vector from Bruiser to the intermediate point
        lda     ttx
        asl
        sec
        sbc     gbx             ; caller pre-loads Bruiser's cell? no —
        sta     ttx             ; compute here:
        lda     tty
        asl
        sec
        sbc     gby
        sta     tty
ct_clamp:                       ; clamp signed results into the maze
        lda     ttx
        bpl     cl1
        lda     #0
        sta     ttx
cl1:    lda     ttx
        cmp     #MAZE_W
        bcc     cl2
        lda     #MAZE_W-1
        sta     ttx
cl2:    lda     tty
        bpl     cl3
        lda     #0
        sta     tty
cl3:    lda     tty
        cmp     #MAZE_H
        bcc     cl4
        lda     #MAZE_H-1
        sta     tty
cl4:    rts

; ---- sched_tick: the scatter/chase clock (paused during blue time) ----
sched_tick:
        lda     frite_t
        ora     frite_t+1
        beq     st_go
        rts
st_go:  lda     sched_state
        cmp     #3
        beq     sc_slow         ; permanent chase: a ~17-minute idle timer
        lda     sched_t
        bne     sc1
        lda     sched_t+1
        beq     sc_adv
        dec     sched_t+1
sc1:    dec     sched_t
        rts
sc_slow:lda     sched_t         ; state 3 just reloads itself on expiry
        bne     sc1
        lda     sched_t+1
        bne     sc1
sc_adv: inc     sched_state
        lda     sched_state
        cmp     #4
        bcc     sc2
        lda     #3
        sta     sched_state
sc2:    tay                     ; note: Y = new state (1..3)
        lda     schedlo-1,y
        sta     sched_t
        lda     schedhi-1,y
        sta     sched_t+1
        jmp     rev_all

; ---- rev_all: every active ghost reverses (schedule edges, energizers) --
rev_all:
        txa
        pha
        ldx     #1
rv1:    lda     gstate,x
        cmp     #GST_NORM
        beq     rv2
        cmp     #GST_FRIGHT
        bne     rv3
rv2:    lda     adir,x
        tay
        lda     opptbl,y
        sta     adir,x
        lda     #$FF            ; reversal invalidates the per-tile decision
        sta     gdecx,x         ; latch so the ghost re-decides where it is
rv3:    inx
        cpx     #5
        bne     rv1
        pla
        tax
        rts

; ---- death_tick: the swoon (spec §8) — freeze, ghosts vanish, she spins
; through the four mouth glyphs, swoons to a half-block, blanks, respawns.
; She does NOT do the other game's fold-open collapse.
death_tick:
        inc     death_t
        lda     death_t
        cmp     #1
        bne     dth1
        ldx     #4              ; ghosts vanish instantly
dtv:    jsr     erase_blob
        dex
        bne     dtv
        rts
dth1:   cmp     #45
        bcc     dth_out         ; the stunned freeze
        bne     dth2
        ldx     #0              ; spin begins: lift her, remember the cell
        jsr     erase_blob
        jsr     blob_addr
        lda     (PTR2),y
        sta     dsave
dth2:   lda     death_t
        cmp     #109
        bcs     dth3
        lsr                     ; spin: jaw glyph rotates every 8 jiffies
        lsr
        lsr
        and     #3
        tay
        lda     mouthtblA,y
        jmp     dth_paint
dth3:   cmp     #141
        bcs     dth_respawn
        ldy     death_t
        lda     #G_HALF_B       ; the swoon: she sinks...
        cpy     #125
        bcc     dth_paint
        lda     #G_SPACE        ; ...and is gone
dth_paint:
        pha
        ldx     #0
        jsr     blob_addr
        pla
        sta     (PTR2),y
dth_out:rts
dth_respawn:
        ldx     #0
        jsr     blob_addr
        lda     dsave           ; put back whatever she died on
        sta     (PTR2),y
        dec     lives
        jsr     drawlives
        lda     lives
        bne     dtr1
        inc     gameover_ev
        lda     #2              ; out of lives: the GAME OVER flow
        sta     game_state
        lda     #0
        sta     death_t
        rts
dtr1:   jsr     player_init
        jsr     ghost_init
        lda     #1
        sta     gdmode          ; arcade post-death global house counters
        lda     #0
        sta     gdcnt
        sta     frite_t
        sta     frite_t+1
        sta     elvl            ; elroy suspended until Sable is out again
        sta     game_state
        sta     death_t
        jmp     jsync

; ---- lfsr: 16-bit xorshift step; returns A (never all-zero) ----
lfsr:   lda     rng
        asl
        rol     rng+1
        bcc     lf1
        eor     #$2D            ; x^16 + x^14 + x^13 + x^11 taps
lf1:    sta     rng
        eor     rng+1
        rts

        .segment "RODATA"
; ghost glyphs: reverse-video initials
G_BRUISER = 2+128
G_PIXIE   = 16+128
G_IVY     = 9+128
G_SABLE   = 19+128
glimit:  .byte 0, 0, 0, 30, 60  ; house dot limits (board 1; index=actor)
glimitG: .byte 0, 0, 7, 17, 32  ; post-death global-counter limits
glyphtbl:.byte 0, G_BRUISER, G_PIXIE, G_IVY, G_SABLE
GSPD_FRIGHT = $28               ; frightened 50% (board-1 class)
elroybump: .byte 0, 4, 8        ; +5% / +10% of $50 by elroy stage
; blue time by board 1-21, in jiffies (spec §9 measured seconds x60)
bluelo:  .byte <360,<300,<240,<180,<120,<300,<120,<120,<60,<240
         .byte <120,<60,<60,<180,<60,<60,0,<60,0,0,0
bluehi:  .byte >360,>300,>240,>180,>120,>300,>120,>120,>60,>240
         .byte >120,>60,>60,>180,>60,>60,0,>60,0,0,0
; warning-flash window = flashes*28 jiffies: 5 flashes normally, 3 on the
; short boards 9/12/13/15/16/18 (spec §9)
flashtbl:.byte 140,140,140,140,140,140,140,140,84,140
         .byte 140,84,84,140,84,84,140,84,140,140,140
schedlo: .byte <1200, <300, <61200  ; chase1 20s, scatter2 5s, "forever"
schedhi: .byte >1200, >300, >61200
sqtbl_lo: .repeat 32, n
          .byte <(n*n)
          .endrepeat
sqtbl_hi: .repeat 32, n
          .byte >(n*n)
          .endrepeat

        .segment "BSS"
gstate: .res NACT
gon:    .res 1                  ; ghost world enable (tests park it)
gdcnt:  .res 1                  ; dots counted for the preferred captive
gtimeout:.res 2
sched_state:.res 1              ; 0 scat1, 1 chase1, 2 scat2, 3 chase-ever
sched_t:.res 2
rng:    .res 2
gcand:  .res 4
gcn:    .res 1
gdir:   .res 1
gci:    .res 1
gd2:    .res 2
gbest:  .res 2
gpick:  .res 1
ttx:    .res 1
tty:    .res 1
gnn:    .res 1
gbx:    .res 1                  ; Bruiser's cell (for Ivy), set per decide
gby:    .res 1
gprex:  .res 1                  ; ghost pre-step position (swap-past check)
gprey:  .res 1
gdecx:  .res NACT               ; where this ghost last decided (per-tile latch)
gdecy:  .res NACT
frite_t:.res 2                  ; frightened jiffies remaining
fchain: .res 1                  ; ghosts eaten this blue period
elvl:   .res 1                  ; cruise elroy stage 0/1/2
gdmode: .res 1                  ; 1 = post-death global house counters
board:  .res 1                  ; current board, saturated at 21 for tables
lives:  .res 1
game_state: .res 1              ; 0 playing, 1 dying/respawn
death_t:.res 1
dsave:  .res 1                  ; cell content under the death animation
gameover_ev: .res 1             ; incremented on last-life loss (T12 hooks)
