; title.s -- the attract screen and the hidden stage-select keys.
;
; The digit keys start a one-player game on stages 1-9, and `0` on stage 10.
; They are undocumented on screen: nothing on the title screen mentions them.
; They exist so a reviewer -- and the evidence protocol -- can reach the
; first challenging stage and the transforming enemies without playing there,
; and they are listed in AUDIT.md's evidence section for exactly that reason.
;
; The chosen stage is the real stage number: the HUD shows it, the difficulty
; tier applies to it, and play continues from there as if the player had
; arrived normally.  Score starts at zero, lives at three, and the fighter is
; single -- the stage select grants nothing but the stage.

        .segment "ENGINE"

TITLEROW = 6

; titlereset -- the cheap half: no drawing, so it fits in a tick.  The screen
; itself is rebuilt by the step machine that sttitle drives.
titlereset:
        lda     #0
        sta     plalive
        sta     pldual
        sta     plstate
        sta     SPRENA
        lda     #$FF
        sta     beamslot
        jsr     clearshots
        jsr     titletext
        lda     #1
        sta     mus_on
        lda     #0
        sta     mus_ord
        sta     mus_row
        sta     mus_tick
        rts

titletext:
        lda     #COL_YELLOW
        sta     txtcol
        lda     #TITLEROW
        sta     scrrow
        lda     #PFCOL+7
        sta     scrcol
        lda     #<t_title
        ldx     #>t_title
        jsr     prstr

        lda     #COL_CYAN
        sta     txtcol
        lda     #TITLEROW+2
        sta     scrrow
        lda     #PFCOL+2
        sta     scrcol
        lda     #<t_sub
        ldx     #>t_sub
        jsr     prstr

        lda     #COL_WHITE
        sta     txtcol
        lda     #TITLEROW+6
        sta     scrrow
        lda     #PFCOL+2                ; (24-19)/2
        sta     scrcol
        lda     #<t_1p
        ldx     #>t_1p
        jsr     prstr
        lda     #TITLEROW+8
        sta     scrrow
        lda     #PFCOL+4
        sta     scrcol
        lda     #<t_2p
        ldx     #>t_2p
        jsr     prstr

        lda     #COL_DKGREY
        sta     txtcol
        lda     #TITLEROW+13
        sta     scrrow
        lda     #PFCOL+7                ; (24-9)/2
        sta     scrcol
        lda     #<t_ctrl1
        ldx     #>t_ctrl1
        jsr     prstr
        lda     #TITLEROW+15
        sta     scrrow
        lda     #PFCOL+4                ; (24-16)/2
        sta     scrcol
        lda     #<t_ctrl2
        ldx     #>t_ctrl2
        jmp     prstr

; ---- the title state -----------------------------------------------------
sttitle:
        lda     stinit
        beq     st0x
        lda     #0
        sta     stinit
        jsr     screenstart
        lda     #1
        sta     sbactive
st0x:   lda     sbactive
        beq     st1x
        jsr     screenstep
        bcc     st9x                    ; still rebuilding the screen
        lda     #0
        sta     sbactive
        jsr     titletext
        rts
st1x:   jsr     drawhud
        ; the hidden stage select: a digit starts a one-player game there
        lda     stage_select
        beq     st2x
        lda     #1
        sta     players
        jmp     startgame
st2x:   lda     input_edge
        and     #IN_ST1
        beq     st3x
        lda     #1
        sta     players
        lda     #0
        sta     stage_select
        jmp     startgame
st3x:   lda     input_edge
        and     #IN_ST2
        beq     st9x
        lda     #2
        sta     players
        lda     #0
        sta     stage_select
        jmp     startgame
st9x:   rts
