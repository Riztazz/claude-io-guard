---
title: Probe the platform at session start and set safe defaults
stage: B
area: transport
created: 2026-09-27
status: open
depends-on: [03, 08]
findings: [SHW-4, SHL-2, SHL-3, OUT-4, OUT-5, STL-3]
platforms: [windows, macos]
commit: "feat: learn the platform at session start and give every shell UTF-8 defaults"
---

## Why

Several checks depend on the platform:
- The backslash halving and the 8 KB cut exist on Windows only (#92543).
- The Windows budget shrinks as the command wrapper grows (#95653).
- A cp1252 console crashes Python prints: 34 charmap errors, and one live while this plan was written.

A SessionStart probe measures once, and every later check reads the result.

## What to build

A SessionStart check, run as a command hook through `hook.sh`, because `CLAUDE_ENV_FILE` belongs to a hook
process. It writes `${CLAUDE_PLUGIN_DATA}/probe.json` with the `Probe` fields in `docs/design/architecture.md`,
section 2:
- the OS, and the Claude Code version where the event exposes it
- which tools are present: Git Bash and its version, pwsh, python, git
- Python's console encoding, and whether the file system ignores case
- the project's dirty files at session start, for STL-3 and task 19

It also sets two things for later checks:
- **The transport budget.** On Windows the default is 6,000 bytes of command, counting each apostrophe as 4 bytes,
  and `transport.budget_bytes` configures it. `SessionState.budget_override` holds a lower value that task 22
  learns from a failure. On macOS there is no budget unless task 36 finds one. When a Claude Code version fixes
  #92543, the probe's version check retires the rule.
- **Environment defaults for later shell calls.** Set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` everywhere. On
  Windows, also set `DOTNET_CLI_UI_LANGUAGE=en` and `VSLANG=1033`. There are three routes:
  1. `CLAUDE_ENV_FILE`, if task 03 confirms it
  2. otherwise a prefix that task 11 adds to the Python commands it rewrites
  3. otherwise a settings `env` block in the README's snippet (task 34)

**Do not set `MSYS_NO_PATHCONV=1` globally.** Agents run `python /c/Users/...` hundreds of times, and those paths
need Git Bash's conversion. Task 14 handles slash arguments one command at a time.

## Where

`plugins/io-guard/scripts/ioguard/checks/session_probe.py`, `lib/platform.py`, and
`${CLAUDE_PLUGIN_DATA}/probe.json` at run time.

## Done when

- `probe.json` is written at session start on Windows, in under 300 ms.
- On Windows, a Python run through the Bash tool prints U+2192 without an error, once the defaults apply.
- Task 19 can read the list of files that were dirty at session start.
- The probe's tests pass in CI on both platforms. Its live run on the Mac waits in task 36.
