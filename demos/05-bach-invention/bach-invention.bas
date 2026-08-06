10 rem j.s. bach - invention no.13 in a minor, bwv 784, bars 1-17
12 rem upper part on sid voice 1, lower on voice 2, noise drums on 3
14 rem notes: the mutopia lilypond edition (public domain), encoded
16 rem as run-length data below and derived to sid frequencies at run
18 rem time from the ntsc clock.  timing: one sixteenth = 8 raster
20 rem frames, counted with a single wait on $d011 - never the jiffy
22 rem clock, which runs at 60.00 hz against the frame's 59.826.
24 rem evidence: score.yaml is the reference the capture is diffed
26 rem against; both files come out of one parse of the source.
40 print "{clr}bwv 784 - invention 13 - preparing"
50 rem --- hot variables first: basic searches the table linearly ---
60 i=0:d=53265:mk=128
70 c1=54276:f1=54272:g1=54273
80 c2=54283:f2=54279:g2=54280
90 c3=54290:g3=54287
100 nt=272
110 rem --- note table: hz = reg16 * clock / 2^24, ntsc clock ---
120 kc=16777216/1022727
130 dim fl%(84),fh%(84)
140 for m=38 to 84
150 fr=440*2^((m-69)/12)
160 nf=int(fr*kc+.5)
170 fh%(m)=int(nf/256):fl%(m)=nf-fh%(m)*256
180 next m
190 rem --- one array per register the tick loop pokes ---
200 dim o%(272),p%(272),q%(272),t%(272)
210 dim u%(272),v%(272),x%(272),y%(272)
220 dim a%(272),b%(272)
230 rem --- expand voice 1 (run length: note,ticks; note 0 = rest) ---
240 read ne:tk=0:lp=0:lq=0
250 for ev=1 to ne
260 read cd,ln
270 for k=1 to ln
280 if cd=0 then o%(tk)=64:t%(tk)=64:goto 320
290 if k>1 then o%(tk)=65:t%(tk)=65:goto 320
300 lp=fl%(cd):lq=fh%(cd)
310 o%(tk)=64:t%(tk)=65
320 p%(tk)=lp:q%(tk)=lq:tk=tk+1
330 next k
340 next ev
350 rem --- expand voice 2 ---
360 read ne:tk=0:lp=0:lq=0
370 for ev=1 to ne
380 read cd,ln
390 for k=1 to ln
400 if cd=0 then u%(tk)=32:y%(tk)=32:goto 440
410 if k>1 then u%(tk)=33:y%(tk)=33:goto 440
420 lp=fl%(cd):lq=fh%(cd)
430 u%(tk)=32:y%(tk)=33
440 v%(tk)=lp:x%(tk)=lq:tk=tk+1
450 next k
460 next ev
470 rem --- voice 3: one noise hit a beat, dark on beat 1 ---
480 for tk=0 to 271
490 bt=tk-int(tk/16)*16
500 a%(tk)=96:if bt<4 then a%(tk)=16
510 b%(tk)=128:if tk=int(tk/4)*4 then b%(tk)=129
520 next tk
530 rem --- the closing tick: every gate down, nothing left sounding ---
540 o%(nt)=64:t%(nt)=64:p%(nt)=p%(nt-1):q%(nt)=q%(nt-1)
550 u%(nt)=32:y%(nt)=32:v%(nt)=v%(nt-1):x%(nt)=x%(nt-1)
560 a%(nt)=16:b%(nt)=128
570 rem --- sid: silence it, then set up the three instruments ---
580 for m=54272 to 54296:poke m,0:next m
590 poke 54277,8:poke 54278,4:rem v1 a=0 d=8 s=0 r=4 - plucked
600 poke 54274,0:poke 54275,8:rem v1 pulse width $0800
610 poke 54284,10:poke 54285,6:rem v2 a=0 d=10 s=0 r=6 - more body
620 poke 54291,4:poke 54292,0:rem v3 a=0 d=4 s=0 r=0 - short hit
630 poke 54286,0:rem v3 frequency low byte stays 0
640 poke 54296,15:rem volume 15, filter off
650 rem --- a silent lead-in, so the capture can be armed ---
660 print "ready - playing bwv 784"
670 tt=ti
680 if ti-tt<480 goto 680
690 tt=ti
700 for i=0 to nt
710 wait d,mk:rem frame 0
720 poke c1,o%(i):poke f1,p%(i)
730 wait d,mk:rem frame 1
740 poke g1,q%(i):poke c1,t%(i)
750 wait d,mk:rem frame 2
760 poke c2,u%(i):poke f2,v%(i)
770 wait d,mk:rem frame 3
780 poke g2,x%(i):poke c2,y%(i)
790 wait d,mk:rem frame 4
800 poke g3,a%(i):poke c3,b%(i)
810 wait d,mk:rem frame 5
820 wait d,mk:rem frame 6
830 wait d,mk:rem frame 7
840 next i
850 tt=ti-tt
860 for m=54272 to 54296:poke m,0:next m
870 print "ticks";nt+1;"jiffies";tt;"want";(nt+1)*8;"frames"
880 end
1000 data 194,0,1,64,1,69,1,72,1,71,1,64,1,71,1,74,1,72,2,76,2,68,2,76,2,69,1
1010 data 64,1,69,1,72,1,71,1,64,1,71,1,74,1,72,2,69,2,0,5,76,1,72,1,76,1,69,1
1020 data 72,1,64,1,67,1,65,2,69,2,74,2,77,3,74,1,71,1,74,1,67,1,71,1,62,1,65
1030 data 1,64,2,67,2,72,2,76,3,72,1,69,1,72,1,65,2,74,3,71,1,67,1,71,1,64,2
1040 data 72,3,69,1,65,1,69,1,62,2,71,2,72,2,0,7,67,1,72,1,76,1,74,1,67,1,74,1
1050 data 77,1,76,2,79,2,71,2,79,2,72,1,67,1,72,1,76,1,74,1,67,1,74,1,77,1,76
1060 data 2,72,2,79,2,76,2,84,1,81,1,76,1,81,1,72,1,76,1,69,1,72,1,74,2,78,2
1070 data 81,2,84,2,83,1,79,1,74,1,79,1,71,1,74,1,67,1,71,1,72,2,76,2,79,2,83
1080 data 2,81,1,78,1,75,1,78,1,71,1,75,1,66,1,69,1,67,2,79,3,76,1,72,1,76,1
1090 data 69,2,78,3,74,1,71,1,74,1,67,2,76,3,72,1,69,1,72,1,66,1,79,1,78,1,76
1100 data 1,75,1,78,1,71,1,75,1,76,2,0,7,79,1,82,1,79,1,76,1,79,1,73,1,76,1,79
1110 data 1,76,1,73,1,76,1,69,1,0,4,77,1,81,1,77,1,74,1,77,1,71,1,74,1,77,1,74
1120 data 1,71,1,74,1,67,1,0,4,76,1,79,1,76,1,72,1,76,1,69,1,72,1,75,1,72,1,69
1130 data 1,72,1,66,1,0,4,74,1,77,1,74,1,71,1,74,1,68,1,71,1,74,1,71,1,68,1,71
1140 data 1,64,1,0,3
1150 data 194,45,2,57,4,56,2,57,1,52,1,57,1,60,1,59,1,52,1,59,1,62,1,60,2,57,2
1160 data 56,2,52,2,57,1,52,1,57,1,60,1,59,1,52,1,59,1,62,1,60,2,57,2,60,2,57
1170 data 2,62,1,57,1,53,1,57,1,50,1,53,1,45,1,48,1,47,2,50,2,55,2,59,3,55,1
1180 data 52,1,55,1,48,1,52,1,43,1,47,1,45,2,48,2,50,1,53,1,47,1,50,1,43,2,47
1190 data 2,48,1,52,1,45,1,48,1,41,2,38,2,43,1,55,1,53,1,55,1,48,1,55,1,60,1
1200 data 64,1,62,1,55,1,62,1,65,1,64,2,60,2,59,2,55,2,60,1,55,1,60,1,64,1,62
1210 data 1,55,1,62,1,65,1,64,2,60,2,0,5,67,1,64,1,67,1,60,1,64,1,55,1,59,1,57
1220 data 2,60,2,64,2,67,2,66,1,69,1,62,1,66,1,57,1,62,1,54,1,57,1,55,2,59,2
1230 data 62,2,66,2,64,1,67,1,60,1,64,1,55,1,60,1,52,1,55,1,54,2,57,2,59,2,63
1240 data 2,0,1,64,1,60,1,64,1,57,1,60,1,64,1,67,1,66,1,62,1,59,1,62,1,55,1,59
1250 data 1,62,1,66,1,64,1,60,1,57,1,60,1,54,1,57,1,60,3,59,1,60,1,57,1,59,2
1260 data 47,2,52,1,64,1,59,1,55,1,52,1,47,1,43,1,47,1,40,2,52,2,55,2,58,2,49
1270 data 2,0,3,67,1,65,1,64,1,62,2,50,2,53,2,56,2,47,2,0,3,65,1,64,1,62,1,60
1280 data 2,48,2,52,2,54,2,45,2,0,3,64,1,63,1,61,1,59,2,47,2,50,2,53,2,44,2,0
1290 data 3,62,1,60,1,59,1
