# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for a
vulnerability.

Use GitHub's private reporting: go to the repository's **Security** tab →
**Report a vulnerability** (GitHub Security Advisories). If that is unavailable,
open a regular issue asking for a private contact channel *without* including
any details of the vulnerability.

We aim to acknowledge a report within a few days. Please give us a reasonable
window to release a fix before any public disclosure.

## Supported versions

Security fixes are applied to the latest `main`; there are no separately
maintained release branches.

## Scope and threat model

Project64 is a local developer tool that drives the VICE emulator; it is
**not** a network service and handles no user credentials. Understanding what
it does with your machine helps you assess risk:

- **Local emulator monitor.** Each session launches `x64sc` and speaks to its
  binary monitor over a TCP socket bound to `127.0.0.1` on an OS-assigned
  port. Anything already able to run code on your machine could connect to
  that socket and control the emulated machine (read/write emulated memory,
  set breakpoints, feed input). This is loopback-only and no worse than local
  code execution you already have, but it is an intentional local interface.
- **External toolchain execution.** The tools invoke `x64sc`, `petcat`,
  `c1541`, `cartconv` (VICE), and `ca65`/`ld65` (cc65), located via `PATH` or
  the `C64_TOOLS_*` environment variables. As with any build tool, a poisoned
  `PATH` or a malicious `C64_TOOLS_CA65`/`C64_TOOLS_X64SC` value would run
  attacker-controlled binaries. Only run in an environment whose `PATH` and
  those variables you trust.
- **Filesystem access (CLI and MCP).** Commands and MCP tools read and write
  files you point them at — assembling/tokenizing source, writing `.prg`/
  label/PNG/disk-image/cartridge outputs, and copying files in and out of disk
  images. Some of it edits a named image *in place* — renaming and scratching
  files, writing raw sectors, and repairing the BAM — and `c64 disk build`
  replaces its output image wholesale. They do not restrict paths, so treat
  their file arguments with the same care as any shell command's.
- **Designed to be driven by AI agents.** When an AI agent operates these
  tools, it acts with your filesystem and shell permissions. Review what an
  agent is asked to do, and prefer running agents in a workspace scoped to
  this project. The emulated 6502 program itself is fully sandboxed inside
  VICE and cannot affect the host.

What is **out of scope**: the behavior of programs *inside* the emulator (they
run in VICE's sandbox), and issues in VICE or cc65 themselves (report those to
their respective projects). Commodore ROM images are never bundled or
committed — the tools read ROM bytes only from the emulator you installed.
