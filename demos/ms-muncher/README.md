# Ms. Muncher — the prompt

An arcade-faithful maze chase for the Commodore 64 — original name, cast,
art, and music, recreating the arcade original's rules, timing, and
structure. The prompt calls for four rotating mazes on a custom multicolor
charset, six hardware sprites, the real per-ghost targeting (including the
randomized scatter openings that defeat pattern play), a travelling bonus
fruit, three animated intermission acts, and a three-voice SID score.

`PROMPT.md` was drafted with Claude's help from detailed human direction,
and a human edited the result. It is all this directory holds today — no
code has been generated from it yet. When the prompt is run, the plan
(`PLAN.md`), the sources, the fidelity audit, the regression spec, the
evidence frames, and the packaged disk will land here, the way a finished
run looks in [`demos/invaders/`](../invaders/).

## The hidden keys

The prompt specifies three undocumented keys, active on the title screen
only: `1`, `2`, and `3` jump straight into intermission acts 1–3 (they
meet / the chase / the delivery), returning to the title when the act
ends. They exist so a reviewer can reach the cut scenes without playing
nine boards, and the fidelity audit is required to list them in its
evidence.
