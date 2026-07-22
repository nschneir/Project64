Write a 6502 assembly program in ca65 syntax for the Commodore 64 that
shows a round hardware sprite (sprite 0) sweeping horizontally across the
screen under jiffy-clock pacing, prints `SPRITE BALL` as HUD text in
screen RAM (with color RAM set), and mirrors the sprite's x position to a
labeled `ballx` byte so tests can assert on motion. Include a BASIC SYS
stub so RUN starts it after loading to $0801.
