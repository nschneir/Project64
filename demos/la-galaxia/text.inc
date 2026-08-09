; text.inc -- every string the player sees, as screen codes.
;
; All in-game text is Spanish, in the arcade register: short, uppercase,
; no articles.  The `scrtext` macro maps ASCII to screen codes and uses six
; lowercase letters as aliases for the glyphs the ROM has not got and this
; game's charset does: a e i o u -> the accented capitals, n -> N-tilde,
; and `?` -> the inverted exclamation mark.  Accents are drawn everywhere
; they belong, never mixed with unaccented spellings.

        .segment "ENGINE"

t_title:    scrline "LA GALAXIA"
t_sub:      scrline "HOMENAJE ARCADE 1981"
t_1p:       scrline "ESPACIO  UN JUGADOR"
t_2p:       scrline "X  DOS JUGADORES"
; The playfield window is 24 columns (PFCOL..PFCOL+PFW-1), so no line drawn
; inside it may be longer than 24 -- the controls used to be one 27-character
; line and ran straight over the right-hand bezel rail.
t_ctrl1:    scrline "A D MOVER"
t_ctrl2:    scrline "ESPACIO DISPARAR"
t_record2:  scrline "ReCORD"

; The left HUD panel is six columns wide (0-5); the bezel grille and rail own
; 6 and 7.  "JUGADOR" is seven and overwrote the grille, so the panel says
; JUG. 1 / JUG. 2.
t_jug1:     scrline "JUG. 1"
t_jug2:     scrline "JUG. 2"
t_puntos:   scrline "PUNTOS"
; "record" without its accent is the English word.  The Spanish loanword
; is *record* with an acute E -- and the charset draws it, so it gets it.
t_record:   scrline "ReCORD"
t_etapa:    scrline "ETAPA"
t_naves:    scrline "NAVES"

; ---- the cold open (§1a) --------------------------------------------------
; The narration is ENGLISH -- the documented exception to the all-Spanish
; rule: it is the narrator speaking, not the cabinet (PROMPT.md §1a).  The
; lines are pre-wrapped for the 10-character 4x bitmap rows, no word broken.
t_cold1:    scrline "IN THE"
t_cold2:    scrline "BACK OF A"
t_cold3:    scrline "MEXICO"
t_cold4:    scrline "CITY"
t_cold5:    scrline "ARCADE,"
t_cold6:    scrline "BEHIND THE"
t_cold7:    scrline "BROKEN"
t_cold8:    scrline "PINBALL"
t_cold9:    scrline "MACHINES,"
t_cold10:   scrline "SITS A"
t_cold11:   scrline "FORGOTTEN"
t_cold12:   scrline "RELIC..."
; ... and its pinned instruction is Spanish like the rest of the game,
; pre-split for two 2x rows.
t_pulsa1:   scrline "PULSA ESPACIO PARA"
t_pulsa2:   scrline "COMENZAR TU VIAJE"

t_desafio:  scrline "ETAPA DE DESAFiO"
t_aciertos: scrline "ACIERTOS"
t_de40:     scrline "DE 40"
t_perfecto: scrline "?PERFECTO!"
t_bonif:    scrline "BONIFICACIoN 10000"
t_gameover: scrline "JUEGO TERMINADO"
t_preparado: scrline "PREPARADO"
t_rescate:  scrline "?RESCATE!"
