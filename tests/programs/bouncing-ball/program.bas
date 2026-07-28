10 rem bouncing beach ball - multicolor hardware sprite 0
20 rem shape authored as ascii art, encoded by c64 sprite encode
30 rem state for tests: $02 edges-seen mask, 251 count, 252 last edge,
40 rem 253/254 direction signs (1 = right / down). $02 and 251-254 are
50 rem the zero-page bytes verified free under basic.
60 poke 53280,0 : poke 53281,6 : print "{clr}"
70 sc=1024 : cr=55296
80 gosub 500 : rem shape into block 13
90 gosub 600 : rem playfield border + hud
100 poke 2040,13 : rem $07f8: sprite 0 pointer, block 13 = 832/64
110 poke 53276,1 : rem $d01c: sprite 0 multicolor on
120 poke 53285,1 : rem $d025: bit-pair 01 -> white
130 poke 53286,0 : rem $d026: bit-pair 11 -> black rim
140 poke 53287,2 : rem $d027: bit-pair 10 -> sprite color, red
150 rem playfield limits: the character border is row 0/24, col 0/39
160 xl=32 : xr=312 : yt=58 : yb=221
170 x=296 : y=200 : dx=4 : dy=3
180 poke 53248,x and 255 : poke 53264,-(x>255) : poke 53249,y
190 poke 2,0 : poke 251,0 : poke 252,0 : poke 253,1 : poke 254,1
200 poke 53269,1 : rem $d015: enable sprite 0
210 rem --- main loop: move, bounce, publish state
220 x=x+dx : bf=0
230 if x>=xr then x=xr : dx=-dx : e=2 : eb=2 : bf=1
240 if x<=xl then x=xl : dx=-dx : e=1 : eb=1 : bf=1
250 y=y+dy
260 if y>=yb then y=yb : dy=-dy : e=4 : eb=8 : bf=1
270 if y<=yt then y=yt : dy=-dy : e=3 : eb=4 : bf=1
280 poke 53248,x and 255 : poke 53264,-(x>255) : poke 53249,y
290 if bf=1 then gosub 900
300 goto 220
500 rem 63 shape bytes -> 832 ($0340, the cassette buffer)
510 for i=0 to 62 : read a : poke 832+i,a : next
520 return
600 rem playfield border, graphics characters + color ram
610 cl=3
620 for c=1 to 38
630 poke sc+c,64 : poke cr+c,cl
640 poke sc+960+c,64 : poke cr+960+c,cl
650 next
660 for r=1 to 23
670 poke sc+r*40,93 : poke cr+r*40,cl
680 poke sc+r*40+39,93 : poke cr+r*40+39,cl
690 next
700 poke sc,79 : poke cr,cl : poke sc+39,80 : poke cr+39,cl
710 poke sc+960,76 : poke cr+960,cl : poke sc+999,122 : poke cr+999,cl
720 t$="bounces"
730 for i=1 to len(t$) : poke sc+41+i,asc(mid$(t$,i))-64 : poke cr+41+i,1 : next
740 for i=0 to 4 : poke cr+53+i,1 : next
750 return
900 rem bounce bookkeeping. $02 saturates at 15 once all four edges are
910 rem seen, so a test can wait on it without racing a moving counter.
920 poke 2,peek(2) or eb
930 bc=(bc+1) and 255 : poke 251,bc : poke 252,e
940 poke 253,-(dx>0) : poke 254,-(dy>0)
950 n$=str$(bc)
960 poke sc+53,32 : poke sc+54,32 : poke sc+55,32
970 for i=2 to len(n$) : poke sc+51+i,asc(mid$(n$,i)) : next
980 return
1000 rem beach ball, 12x21 multicolor: 01=white 10=red 11=black rim
1010 data 0,255,0
1020 data 3,90,192
1030 data 13,90,176
1040 data 5,90,160
1050 data 53,90,172
1060 data 37,90,164
1070 data 233,90,151
1080 data 233,90,151
1090 data 234,90,87
1100 data 234,153,87
1110 data 234,165,87
1120 data 234,153,87
1130 data 234,90,87
1140 data 233,90,151
1150 data 233,90,151
1160 data 37,90,164
1170 data 53,90,172
1180 data 5,90,160
1190 data 13,90,176
1200 data 3,90,192
1210 data 0,255,0
