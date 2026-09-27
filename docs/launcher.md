# Launching Python

io-guard is written in Python, and Claude Code installs nothing for a plugin, so io-guard runs on the Python
already on your machine. No interpreter name works on every machine. On Windows, `python` is the real one and
`python3` is often the Microsoft Store stub. On macOS, `python3` is there and `python` may not be.

## Set the interpreter

io-guard's one setting for this is the Python interpreter, and its default is `python3`. On Windows with Python
from python.org, run `/plugin configure io-guard` and set it to `python`. Whatever you set has to start Python
3.14 or later.

## What starts Python

Two things do, once each per session:

| What | Started by | Which Python |
|---|---|---|
| The io server, which answers every guarded tool call | `.mcp.json`, from `${user_config.python}` | Your setting, or `python3` when you haven't set one |
| The SessionStart hook, and the per-turn heartbeat once task 23 adds it | `hook.sh`, a POSIX `sh` script | Your setting, then `python3`, `python` and `py -3`, skipping the Store stub under `WindowsApps` |

Every tool call goes to the running server through an `mcp_tool` hook, so no call starts Python.

## What each hook path costs

Each row is one headless session making 100 Bash calls, timed from the hook's start to its answer in Claude
Code's own event stream. The runs used the `claude` CLI 2.1.283 on Windows 10 with Python 3.14.0, on
2026-09-27. `tools/probes/run_probe.py` runs them as `launch-mcp`, `launch-exec` and `launch-hooksh`.

| Path | p50 | p95 | Max |
|---|---|---|---|
| An `mcp_tool` hook on the running server | 1.2 ms | 1.6 ms | 4.5 ms |
| A command hook that starts Python directly, in exec form | 53.4 ms | 58.0 ms | 61.6 ms |
| A command hook through `hook.sh`, which starts Git Bash and then Python | 129.8 ms | 139.1 ms | 142.5 ms |

io-guard uses the first path for every tool call. All three fit the 300 ms budget, and the first leaves nearly
all of it for the checks. On the desktop app's bundled 2.1.281, ten calls each gave the same order: 1.5, 57.1
and 89.7 ms at p50, the last for shell form without `hook.sh`.

## When Python is missing or too old

io-guard never blocks a tool call because of its own launch. It tells you once, at the start of the session:

- **No Python at all:** `hook.sh` answers with a message saying so, and naming the fix.
- **A setting that doesn't start Python 3.14 or later**, the default `python3` on a Windows machine with only
  the Store stub included: the message quotes the setting and says the io server is off.

Claude Code then starts the session without the io server. Each guarded tool call still runs, and Claude Code
adds its own notice to it: `MCP server 'plugin:io-guard:io' not connected`.

## Why there's no command-hook fallback

Every Claude Code release io-guard supports, 2.1.281 and later, runs `mcp_tool` hooks
([`compat.md`](compat.md)). A fallback would have nowhere to live anyway. Your own settings can't name the
plugin's folder, and `/hooks` is read-only, so it can't switch the plugin's hooks off.
