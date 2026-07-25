Write a Commodore BASIC program for the Commodore 64 (BASIC 2.0) that plays
guess-the-number: pick a random number from 1 to 100, prompt `YOUR GUESS?`,
answer `TOO HIGH`, `TOO LOW`, or `YOU GOT IT IN n GUESSES!`, then offer to
play again. Give it its own look by setting the border and background
colors (POKE 53280 and 53281).

Seed the generator on its own line with `RND(-1)` so the sequence is
reproducible — a random program cannot be pinned by a static test until it
is seeded.
