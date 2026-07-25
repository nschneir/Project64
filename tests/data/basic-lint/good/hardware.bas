10 poke 53280,0:poke 53281,15:poke 65535,255
20 print chr$(0)chr$(255)peek(53280)
30 def fn sq(x)=x*x:print fn sq(9)
40 dim a(20):a(20)=1:ti$="000000"
50 t=ti:s=st:print t;s
60 for i=0 to 20:read a(i):next:print tab(255)spc(0)
70 end
80 data 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21
