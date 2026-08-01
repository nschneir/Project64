# Snake — the prompt

A complete arcade Snake for the Commodore 64 in 6502 assembly, written
straight to screen memory and color RAM. The prompt calls for a title
screen in large PETSCII, a bordered playfield on a custom character set
with deliberate color, `$CB` held-key steering, SID effects with every
write shadowed in RAM, a SCORE/LEVEL status line where the snake speeds up
and changes color per level, a game over, and a high score that survives
into the next game — then an audit-and-improve loop, evidence frames
captured from the stopped machine, a `test.yaml` regression spec, and a
packaged `snake.d64`.

`PROMPT.md` was drafted with Claude's help from human direction, and a
human edited the result. It is all this directory holds today. Snake passed
an earlier C64 dogfood run as a lightweight test demo, where nothing was
committed and the run itself was the deliverable; the prompt has since been
promoted to a game demo that keeps its whole solution — plan, sources,
audit, evidence frames, regression spec, and packaged disk. None of that
exists yet, so the demo awaits a run under the new prompt. When it lands,
this directory will look the way a finished run looks in
[`demos/invaders/`](../invaders/).
