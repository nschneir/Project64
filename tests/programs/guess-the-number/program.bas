10 poke 53280,0:poke 53281,11:poke 646,1
20 print "{clr}"
30 x=rnd(-1)
40 print "    * guess the number *"
50 print
60 n=int(rnd(1)*100)+1:c=0
70 print "i am thinking of a number from 1 to 100"
80 print
90 input "your guess";g
100 c=c+1
110 if g>n then print "too high":goto 90
120 if g<n then print "too low":goto 90
130 print "you got it in";c;"guesses!"
140 print
150 input "play again (y/n)";a$
160 if a$="y" then 20
170 if a$="n" then print "bye":end
180 goto 150
