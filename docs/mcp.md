# `c64-tools` MCP reference — the CLI↔MCP map

`c64-tools-mcp` is a stdio MCP server exposing the same session, build, and
debug operations as the `c64` command line. It is installed with the package
and takes no arguments; [`docs/agent-setup.md`](agent-setup.md) has the config
block for each agent. Every tool describes itself — the description an MCP
client shows *is* the per-tool reference, so this page does not repeat it.
What it does instead is state which CLI command each tool twins and where the
two differ, one row per registered tool. Both halves are checked by
`tests/test_docs_readme.py`: every registered tool must appear here, and every
command named in the tables must still exist in the CLI.

For what the commands themselves do — arguments, semantics, worked examples —
read [`docs/cli.md`](cli.md); it applies unchanged to the tools.

## Conventions

- **Names map mechanically.** The command path becomes the tool name with
  underscores: `c64 disk ls` → `c64_disk_ls`, `c64 break add` →
  `c64_break_add`, `c64 sprite from-png` → `c64_sprite_from_png`. The rows
  below only carry a note where that rule does not produce the answer.
- **Parameter names, not parameter order.** An option's long spelling becomes
  the parameter with hyphens as underscores (`--cart-type` → `cart_type`,
  `--peak-hz` → `peak_hz`), and a positional argument keeps its name. Where a
  Python keyword or a collision forced a different word — `--from` → `src`,
  `--as` → `encoding`, `--format` → `fmt` — the row says so. Position is not
  part of the map: `c64_build`'s `output` is last in its signature while
  `c64_package`'s is second, and both spell the CLI's `-o` the same way.
- **Sessions are shared.** Tools and commands read the same session registry
  under `~/.c64-tools/sessions/` (`$C64_TOOLS_HOME` overrides the base), so an
  agent can start a machine with a tool and inspect it from a shell, or the
  reverse. Every session-bound tool takes an optional `session` name — the
  CLI's `--session`/`-s` — and defaults to the single running session.
- **Payloads are the CLI's `--json`.** A tool returns the object the twinned
  command prints under `--json`, key for key. The CLI's human rendering has no
  MCP counterpart, so options that only shape printed text (`c64 mem read
  --decimal`) have no parameter here; where the printed text is the useful
  output rather than a rendering of the payload, the tool returns it as an
  extra key instead (see `c64_sprite_encode` and `c64_charset_encode`).
- **Sessions the tools start are headless and warp.** `c64 session start`
  makes both a flag; the tools hardcode them, because an MCP client is an
  automation and not someone watching a window (the reasoning is commented in
  `src/c64lib/mcp_server.py`). Everything else about the session is the same
  machine.
- **Errors raise; timeouts do not.** A tool that fails raises, and the message
  is the text the command would have printed on its way to exit 1. A wait that
  times out is the case where the two sides genuinely differ: the CLI exits 1,
  while all four `c64_wait_*` tools return `{"fired": null, ...}` as data —
  carrying the last screen, the last PCs, or `"machine": "running"` where
  those apply — so a client can inspect what the program actually did instead
  of parsing an error string.
- **The stopped-state rule is identical.** `c64_step`, `c64_finish`,
  `c64_until`, and a fired `c64_wait_break` leave the machine halted until
  `c64_continue` or an explicitly-resuming tool, across as many calls as you
  like.

## The map

### Sessions and status

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_session_start` | `c64 session start` | headless and warp are always on, not flags; `--disk` is `disk` |
| `c64_session_ensure` | `c64 session ensure` | same: headless and warp are always on when it boots |
| `c64_session_list` | `c64 session list` | — |
| `c64_session_stop` | `c64 session stop` | — |
| `c64_session_reset` | `c64 session reset` | — |
| `c64_status` | `c64 status` | — |

### Screen

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_screen_text` | `c64 screen` | the command's default mode; `--style`, `--numbered`, `--ansi-reverse` carry over |
| `c64_screen_codes` | `c64 screen --codes` | a mode flag on the command, a separate tool here |
| `c64_screenshot` | `c64 screen --png` | `--png PATH` is the required `path` |

### Keyboard

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_key_type` | `c64 key type` | — |
| `c64_key_hold` | `c64 key hold` | `KEYNAME` is `key`, `--at` is `at` |

### Memory

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_mem_read` | `c64 mem read` | also covers `c64 mem get`, whose bytes it returns under `values`; `--as` is `encoding`, and `--decimal` shapes printed text only |
| `c64_mem_write` | `c64 mem write` | no `--stdin` batch form (see below) |
| `c64_mem_find` | `c64 mem find` | — |

### Registers

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_reg_get` | `c64 reg` | the CLI reads registers from the bare group; there is no `c64 reg get` |
| `c64_reg_set` | `c64 reg set` | — |

### Breakpoints and watchpoints

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_break_add` | `c64 break add` | `--once` is the CLI's own alias for `--temporary`, so only `temporary` exists here |
| `c64_break_list` | `c64 break list` | — |
| `c64_break_remove` | `c64 break remove` | one command under four spellings — `c64 break rm`, `c64 watch remove`, `c64 watch rm` are the same removal, so this tool removes watchpoints too; `CK_ID` is `checkpoint_id` |
| `c64_break_enable` | `c64 break enable` | `CK_ID` is `checkpoint_id` |
| `c64_break_disable` | `c64 break disable` | `CK_ID` is `checkpoint_id` |
| `c64_break_clear` | `c64 break clear` | — |
| `c64_watch_add` | `c64 watch add` | `--load`/`--store` are `on_load`/`on_store` |
| `c64_watch_clear` | `c64 watch clear` | — |

### Execution control

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_step` | `c64 step` | — |
| `c64_finish` | `c64 finish` | — |
| `c64_continue` | `c64 continue` | — |
| `c64_until` | `c64 until` | — |
| `c64_call` | `c64 call` | `REF` is `routine`; `--a`/`--x`/`--y` are `a`/`x`/`y` |
| `c64_profile` | `c64 profile` | `REF` is `routine` |

### Waiting

One command with four mutually exclusive condition flags becomes four tools,
each taking its own condition. On all four, a timeout returns
`{"fired": null, ...}` rather than exiting 1.

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_wait_text` | `c64 wait --text` | — |
| `c64_wait_mem` | `c64 wait --mem` | the `ADDR<op>VALUE` string is split into `addr`, `op`, and `equals` |
| `c64_wait_break` | `c64 wait --break` | `--break ID` is `checkpoint_id` |
| `c64_wait_idle` | `c64 wait --idle` | — |

### Building and packaging

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_build` | `c64 build` | `-o` is `output`; `--area` is `areas` (a list) |
| `c64_package` | `c64 package` | `--format` is `fmt`, `--cart-type` is `cart_type`, `--area` is `areas` |

### BASIC

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_basic_tokenize` | `c64 basic tokenize` | — |
| `c64_basic_detokenize` | `c64 basic detokenize` | — |
| `c64_basic_check` | `c64 basic check` | `SOURCE` is `source_path` |
| `c64_basic_type` | `c64 basic type` | takes the program text inline as `text`; the CLI types it from a file |

### Loading and running

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_load` | `c64 load` | `--run/--no-run` is the boolean `run` (default true, as on the CLI) |
| `c64_run` | `c64 run` | — |

### Disk images

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_disk_create` | `c64 disk create` | `--id` is `disk_id` |
| `c64_disk_ls` | `c64 disk ls` | — |
| `c64_disk_put` | `c64 disk put` | — |
| `c64_disk_get` | `c64 disk get` | `dest` is required; the CLI's `DEST` is optional, defaulting to `NAME.prg` |
| `c64_disk_boot` | `c64 disk boot` | — |
| `c64_disk_rename` | `c64 disk rename` | — |
| `c64_disk_rm` | `c64 disk rm` | also covers the alias `c64 disk delete` |
| `c64_disk_block_read` | `c64 disk block read` | `-o` is `output` |
| `c64_disk_block_write` | `c64 disk block write` | `--from` is `src` (`from` is a Python keyword) |
| `c64_disk_validate` | `c64 disk validate` | — |
| `c64_disk_build` | `c64 disk build` | `-o` is `output` |

### Cartridges

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_cart_build` | `c64 cart build` | `-o` is `output` |
| `c64_cart_info` | `c64 cart info` | — |
| `c64_cart_verify` | `c64 cart verify` | — |
| `c64_cart_dump` | `c64 cart dump` | `-o` is `output` (required on both sides) |
| `c64_cart_bank` | `c64 cart bank` | — |
| `c64_cart_convert` | `c64 cart convert` | `--type` is `cart_type` |

### Sprites and charsets

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_sprite_status` | `c64 sprite status` | — |
| `c64_sprite_show` | `c64 sprite show` | — |
| `c64_sprite_png` | `c64 sprite png` | `--out`/`-o` is `path` (required on both sides) |
| `c64_sprite_from_png` | `c64 sprite from-png` | the ca65 rows come back in the payload under `rows`, so `--out`/`-o` has no counterpart |
| `c64_sprite_encode` | `c64 sprite encode` | returns the text the CLI prints under `rendered`, which supersedes `--out`/`-o`; `--format` is `fmt` |
| `c64_charset_encode` | `c64 charset encode` | same `rendered` key, superseding `--out`/`-o`; `--first-code` is `first_code` |

### ROM tools

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_rom_info` | `c64 rom info` | — |
| `c64_rom_disasm` | `c64 rom disasm` | also covers the top-level alias `c64 disasm`; the tool keeps the older name, so there is no `c64_disasm` |

### Audio

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_audio_record` | `c64 audio record` | `--start PATH` and `--stop` become `action="start"` with `path`, or `action="stop"` |
| `c64_sid_log` | `c64 audio sidlog` | renamed: the tool is named for what it logs |
| `c64_audio_capture` | `c64 audio capture` | — |
| `c64_sid_report` | `c64 audio report` | renamed to match `c64_sid_log`; `--peak-hz` is `peak_hz` |
| `c64_audio_score` | `c64 audio score` | — |

### Test runner

| Tool | CLI | Divergence |
|------|-----|------------|
| `c64_test_run` | `c64 test run` | — |
| `c64_test_programs` | `c64 test programs` | — |

## What the CLI has and the tools do not

Every CLI capability has a tool, so an MCP-wired agent never needs a shell.
Three things still exist only on the command line, and none of them is a
capability an agent is missing:

- **`c64 help`.** It prints a command's usage text. An MCP client already
  lists every tool with its description and its parameter schema, which is
  the same information delivered by the protocol itself.
- **The aliases.** `c64 break rm`, `c64 watch remove`, `c64 watch rm`,
  `c64 disk delete`, and top-level `c64 disasm` are second spellings of
  commands that already have a tool (`c64_break_remove`, `c64_disk_rm`,
  `c64_rom_disasm`). Typing conveniences do not need duplicate tools; a
  second name for one operation would only make the roster ambiguous.
- **`c64 mem write --stdin`.** It reads `REF V1 V2 …` lines from stdin so a
  shell heredoc can do many writes in one process — a way around the CLI's
  per-invocation startup cost, which the server does not have. The tool
  writes one range per call, and a client that wants twenty makes twenty
  calls in a live process.

The stdout-redirect options are the same kind of thing rather than a gap:
`--out`/`-o` on `c64 sprite encode`, `c64 charset encode`, and
`c64 sprite from-png` write the printed rows to a file, and the tools return
those rows in the payload instead — which is where a client wants them.
