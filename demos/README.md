# Demos — prompts to try with your AI agent

Each demo here is a ready-to-run prompt for an AI coding agent set up with
this toolset (see [docs/agent-setup.md](../docs/agent-setup.md)). Give one to
your agent and watch it write, run, and debug real Commodore 64 software on
the emulated machine.

**The catalogue lives in the [main README](../README.md#demos--try-it-with-your-ai-agent)**
— full descriptions, screenshots, and ▶ Play links for the built ones.
This page is the map of the directory itself.

## Test demos

Graded exercises; start at 01 if you're new.

| Demo | Description |
|------|-------------|
| [01 Guess the number](01-guess-the-number/PROMPT.md) | The write→run→verify loop end to end |
| [02 Bouncing beach ball](02-bouncing-ball/PROMPT.md) | A hardware sprite, proved from the VIC-II registers |
| [03 Sieve benchmark](03-sieve-benchmark/PROMPT.md) | BASIC vs. assembly, timed off the jiffy clock |
| [04 Debug hunt](04-debug-hunt/PROMPT.md) | A dashboard broken in three layers, found with the debugger |
| [05 Bach's Invention No. 13](05-bach-invention/PROMPT.md) | Three SID voices, proved by audio capture and a piano roll |

## Game demos

Full games, each with its own fidelity bar and evidence protocol.

| Demo | Description |
|------|-------------|
| [Snake](snake/PROMPT.md) | Arcade Snake on a custom hires charset |
| [Invaders](invaders/PROMPT.md) | The 1978 arcade original, to an arcade-fidelity spec |
| [Ms. Muncher](ms-muncher/PROMPT.md) | A maze chase with four boards and per-ghost AI |
| [La Galaxia](la-galaxia/PROMPT.md) | A fixed shooter in Spanish, with sprite multiplexing |

## Miscellaneous cool stuff

Audiovisual builds that aren't games.

| Demo | Description |
|------|-------------|
| [1812](1812/PROMPT.md) | Shapes painted to Tchaikovsky's *1812 Overture* |
| [Fugue No. 2 in C Minor](fugue/PROMPT.md) | Bach's BWV 847 while its score scrolls past |
| [Amiga Ball](amiga_ball/PROMPT.md) | The 1984 Boing Ball, on four multicolor sprites |

## Where the work goes

Every demo is a directory holding its prompt in `PROMPT.md` and a `README.md`
describing it. The prompt is named `PROMPT.md`, not `README.md`, so that what
you give the agent is never confused with documentation *about* the demo.

The test demos keep nothing else: the agent writes the program wherever it
likes, proves it on a live session, and nothing is committed — the run itself
is the deliverable.

Every demo outside that tier keeps everything: sources, plan, `AUDIT.md`,
`evidence/`, and the artefact the prompt asked for, so `invaders.d64`,
`snake.d64`, `ms-muncher.d64`, `la-galaxia.d64`, `1812.d64`, `amiga_ball.d64`
and `fugue.d64` all run in stock VICE without a checkout of this toolset.

## Shipping a new demo

A demo prompt's "Ship it" section tells its author to `c64 package` the demo
and write a `README.md`. **Committing the `.prg` that step produces obliges
more than the prompt says**, and every obligation below is enforced by a test
in `tests/test_docs_demos.py` — this list exists so the author meets it as a
checklist rather than as a red suite, one failure at a time (the demo that
prompted it tripped all five):

1. **A `play.html` `DEMOS` entry.** The roster test counts every demo
   directory with a committed `.prg`; a new one must appear on the play page
   in the roster's order
   (`test_play_page_registry_is_the_runnable_demos_in_the_roster_order`).
2. **A second, hand-written entry in `play.html`'s `<noscript>` fallback** —
   one `.prg` and one `.d64` link per demo
   (`test_every_demo_file_play_html_serves_exists_and_is_tracked`, which also
   requires every served file to be git-tracked).
3. **A description byte-identical to `index.html`'s** for the same demo
   (`test_play_page_describes_each_game_the_way_the_landing_page_does`), and
   a row in the main `README.md`'s catalogue — the three markdown surfaces
   share one roster (`test_demo_roster_matches_across_readme_site_and_demos_readme`).
4. **Tile art under the demo's own `evidence/`** — the play entry's `image:`
   must name a committed file.
5. **If the demo captures audio:** the scored/silent split is counted and
   phrased by `test_exactly_one_captured_audio_score_lists_no_sounding_note`
   and `test_the_sites_the_failure_message_names_still_say_it` — read both
   docstrings before committing `evidence/audio/`.

Also standing, for every demo with a `test.yaml` naming an `.s` source and a
committed `.prg`: the binary must be byte-identical to a rebuild of the
committed sources (`test_demo_prg_is_a_build_of_the_committed_sources`), so
rebuild and re-run the demo's spec after any source edit, however cosmetic
it looks.
