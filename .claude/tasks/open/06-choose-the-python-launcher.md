---
title: Start the server and the two command hooks the same way on both platforms
stage: A
area: runtime
created: 2026-09-27
status: open
depends-on: [03]
findings: [SHL-3]
platforms: [windows, macos]
commit: "feat: start the guard's Python the same way on Windows and macOS"
---

## Why

No interpreter name works on both platforms. On Windows `python.exe` is the real interpreter and `python3` is the
Microsoft Store stub on the lead's machine. On macOS `python3` exists and `python` may not. Claude Code installs
no Python packages for a plugin, so nothing can be installed for us. With the one-process runtime (D13) only two
things start Python: the io server, and the command hooks for SessionStart and the per-turn heartbeat.

## What to build

`docs/design/architecture.md`, section 6, "The launcher across Windows and macOS", is the design.

- **The server** starts from `plugins/io-guard/.mcp.json` with `"command": "${user_config.python}"`, which defaults
  to `python3` (D15), and `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8` and `IOGUARD_DATA` in its `env`.
- **`scripts/hook.sh`**, POSIX sh, runs under Git Bash on Windows and `sh` on macOS. It finds an interpreter with
  `command -v` in the order `python3`, `python`, `py -3`, skips any path under `WindowsApps`, and runs `hook.py`
  with the event name. With no interpreter it prints a `systemMessage` naming the fix and exits 0.
- **The fallback**, for a harness where task 03 item 12 fails: every tool event as a shell-form command hook through
  `hook.sh`. The README carries it as a settings snippet.
- **The first real hook:** a no-op PreToolUse on `Bash|PowerShell|Edit|Write|Read` that writes one JSONL line per
  call to `${CLAUDE_PLUGIN_DATA}`. It proves the wiring, and task 08 replaces it.
- **Measure** 100 no-op calls through each path: the `mcp_tool` hook on task 03's probe server, the command hook
  through `hook.sh`, and the exec form. Record p50 and p95 in `docs/launcher.md`.

## Where

`plugins/io-guard/.mcp.json`, `plugins/io-guard/hooks/hooks.json`, `plugins/io-guard/scripts/hook.sh`,
`plugins/io-guard/scripts/hook.py`, `docs/launcher.md`.

## Done when

- One `hooks.json` and one `.mcp.json` start the no-op hook and a stub server on Windows, with the lead's
  `userConfig.python` set to `python`.
- The chosen path's p95 fits the 300 ms budget (D16), and `docs/launcher.md` holds the numbers for all three.
- A missing or wrong interpreter gives one clear warning per session and never blocks the tool call (D7).
- `hook.sh` passes `sh -n` in CI on the macOS runner. Its live start on the Mac waits in task 36.
