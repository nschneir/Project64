# Using Project64 with AI coding agents

This toolset is built to be driven by an AI agent. Debugging state persists
across commands: when the agent halts the machine at a breakpoint, it stays
halted while the agent inspects memory, registers, and screen in separate tool
calls. There are two ways an agent can use it — pick either or both:

- **The CLI** — every `c64` command takes `--json` (the binary lives at
  `.venv/bin/c64` in a source checkout). Works with *any* agent that can
  run shell commands; nothing to configure.
- **The MCP server** — `c64-tools-mcp` exposes the same session, build, and
  debug operations as MCP tools over stdio, returning the same structured
  data the CLI's `--json` does. CLI and MCP share the same sessions, so they
  mix freely. Every CLI capability has an MCP twin, so an MCP-wired agent
  needs no shell.
  Every `c64 disk` and `c64 cart` verb has an MCP twin; `c64 watch remove` is
  the same command as `c64 break remove`, so `c64_break_remove` covers it.

Either way, the agent should read
[`skills/c64-development/SKILL.md`](../skills/c64-development/SKILL.md) (the
workflows and pitfalls) before starting — the per-agent steps below make that
happen automatically.

The MCP config used by several agents below is this one block:

```json
{
  "mcpServers": {
    "c64-tools": { "command": "c64-tools-mcp" }
  }
}
```

Setup was verified against each agent's docs in **July 2026**; if something
has moved, check the agent's current MCP documentation.

## Any agent with a shell (simplest — works everywhere)

1. Install (see the [README](../README.md#install)) — that's the whole setup.
2. Start your task prompt with: *"Read docs/cli.md and
   skills/c64-development/SKILL.md, then …"*

## Claude Code

1. From the repo root, install the skills so Claude discovers them
   automatically:

   ```
   mkdir -p .claude/skills && cp -R skills/* .claude/skills/
   ```

2. (Optional) Add the MCP server: `claude mcp add c64-tools -- c64-tools-mcp`
3. Ask for what you want — e.g. paste a prompt from [`demos/`](../demos/).

No `CLAUDE.md` edits are needed: installed skills load on demand, and the MCP
tools describe themselves.

## OpenAI Codex

1. Add the MCP server: `codex mcp add c64-tools -- c64-tools-mcp`
   (or add `[mcp_servers.c64_tools]` with `command = "c64-tools-mcp"` to
   `~/.codex/config.toml`).
2. Codex has no skills mechanism, so tell it where the docs are: add one line
   to the repo's `AGENTS.md` — *"For Commodore 64 work, first read
   skills/c64-development/SKILL.md and docs/cli.md."*
3. Paste a prompt from [`demos/`](../demos/).

## Cursor

1. Create `.cursor/mcp.json` in the repo (or `~/.cursor/mcp.json` globally)
   containing the JSON block above.
2. Create a rule (`.cursor/rules/c64.mdc`) — or a plain `AGENTS.md` — with the
   same one-liner: *"For Commodore 64 work, first read
   skills/c64-development/SKILL.md and docs/cli.md."*
3. Paste a prompt from [`demos/`](../demos/).

## Gemini CLI

1. Add the JSON block above to `.gemini/settings.json` in the repo (or
   `~/.gemini/settings.json` globally).
2. Add the same read-the-skill one-liner to `GEMINI.md`.
3. Paste a prompt from [`demos/`](../demos/).

## Google Antigravity

1. Open the MCP store → **Manage MCP Servers** → **View raw config** and add
   the JSON block above (the file is `~/.gemini/config/mcp_config.json`).
2. Add the read-the-skill one-liner to `AGENTS.md`.
3. Paste a prompt from [`demos/`](../demos/).

## Crush

Crush spells the block `mcp` rather than `mcpServers` and wants an explicit
transport type, so it needs its own snippet instead of the JSON block above:

1. Create `crush.json` in the repo root (`.crush.json` is checked first;
   `~/.config/crush/crush.json` is the global fallback) containing:

   ```json
   {
     "$schema": "https://charm.land/crush.json",
     "mcp": {
       "c64-tools": { "type": "stdio", "command": "c64-tools-mcp" }
     }
   }
   ```

2. Install the skills — Crush implements the Agent Skills standard and reads
   `.crush/skills`, `.agents/skills`, `.claude/skills`, and `.cursor/skills`
   from the project, so if you already ran the Claude Code copy above there is
   nothing to do. Otherwise:

   ```
   mkdir -p .crush/skills && cp -R skills/* .crush/skills/
   ```

3. Paste a prompt from [`demos/`](../demos/).

Crush also loads project context files on its own — `CRUSH.md`, `AGENTS.md`,
and `CLAUDE.md` are all on its default list — so the read-the-skill one-liner
from the Codex step works here too if you'd rather not copy skills at all.

By default Crush asks before every tool call. Pre-approve the ones you get
tired of confirming under `permissions.allowed_tools`, using the
`mcp_<server>_<tool>` name (e.g. `mcp_c64-tools_c64_screen_text`) — matching is
exact, so there is no wildcard for a whole server. `crush --yolo` skips every
prompt; that means the emulator *and* your shell, so treat it accordingly.
