# Launching Python

io-guard is written in Python, and Claude Code installs nothing for a plugin, so io-guard runs on the Python
already on your machine. It needs Python 3.14 or later.

## How io-guard finds Python

One launcher, `scripts/pyrun`, starts Python for everything io-guard runs: the io server once per session, and
the two command hooks at the start of a session and of each turn. All three run the same interpreter. It tries
these in order:

| | Windows | macOS |
|---|---|---|
| 1 | `IOGUARD_PYTHON`, when you've set it | `IOGUARD_PYTHON`, when you've set it |
| 2 | `py -3`, the launcher python.org installs | `python3` |
| 3 | `python` | `python` |

On Windows, `python3` isn't tried. On most machines it's the Microsoft Store's install stub, which prints "Python
was not found" and exits. With Python from the Microsoft Store there's no `py`, and `python` is the Store's own
Python.

The server's command is `${CLAUDE_PLUGIN_ROOT}/scripts/pyrun`. On Windows, Claude Code runs that name through
`cmd.exe`, which picks `pyrun.cmd`. On macOS it runs `pyrun`, a POSIX `sh` script. The hooks run
`sh pyrun` on both, under Git Bash on Windows. `pyrun.cmd` looks commands up on your `PATH` only, never in the
project folder the server starts in, so a `python.bat` in a repository you clone never runs.

`pyrun` hands every argument to the Python it picks, so `pyrun --help` prints Python's own help. To see what a
script does, run it with `--help` instead: `pyrun hook.py --help` or `pyrun ioguard_mcp.py --help`.

## Name your Python

Set `IOGUARD_PYTHON` to the full path of your interpreter when the list above doesn't find Python 3.14. The
`env` block of `~/.claude/settings.json` reaches the terminal and the desktop app alike:

```json
{
  "env": {
    "IOGUARD_PYTHON": "C:/Python314/python.exe"
  }
}
```

A user environment variable works too. The server and the hooks both read it, so one value covers all three.

io-guard has no plugin setting for this. Claude Code keeps a plugin's settings under the plugin's name, and the
desktop app loads some plugins under a second name, `io-guard@inline`, where a saved setting isn't found.
`IOGUARD_PYTHON` is the same under every name.

## When Python is missing or too old

io-guard never blocks a tool call because of its own launch. What you see depends on what went wrong:

- **No Python found:** the server doesn't start, and `/mcp` shows "io-guard found no Python. Install Python
  3.14 or later, or set IOGUARD_PYTHON to its full path." On a Windows machine with no Python, `python` is
  usually the Store stub, and `/mcp` shows its "Python was not found" instead.
- **`IOGUARD_PYTHON` names no program:** the server doesn't start, and `/mcp` quotes the value.
- **Python older than 3.14:** the session-start hook says so once, naming the interpreter and the fix.

Claude Code then runs the session without the io server. Each tool call still runs, unchecked, and io-guard
says the server is down once, at the start of your next turn.

## Git for Windows

On Windows, the two command hooks run `sh`, which comes with Git for Windows. Without it, Claude Code runs
hooks through PowerShell, where those two hooks fail, and the io server still checks every tool call. Claude
Code's own Bash tool needs Git Bash as well.

## What each hook path costs

Each row is one headless session making 100 Bash calls, timed from the hook's start to its answer in Claude
Code's own event stream, with the `claude` CLI 2.1.283 on Windows 10 and Python 3.14.0, on 2026-09-28.
`tools/probes/run_probe.py` runs them as `launch-mcp`, `launch-exec` and `launch-pyrun`. The first two answer
from the probes' own small plugin, and the third runs io-guard's `hook.py`. No other plugin's hook runs on the
call: the probes turn off an installed io-guard.

| Path | p50 | p95 | Max |
|---|---|---|---|
| An `mcp_tool` hook on a running server | 1.2 ms | 1.6 ms | 5.2 ms |
| A command hook that starts Python on a small script, in exec form | 54.5 ms | 58.2 ms | 62.8 ms |
| A command hook through `sh pyrun` and `py -3`, running `hook.py` | 300.5 ms | 307.9 ms | 313.3 ms |

The desktop app's 2.1.281 timed the first path at 1.2 ms at p50 and 1.4 ms at p95. That's the hook's own
cost, a server that answers at once. io-guard's checks come on top: its PreToolUse on a Bash call took 39.5 ms
at p50 and 45.2 ms at p95 in the same kind of session. `python tools/report.py` shows the checks' time on your
own sessions.

io-guard uses the first path for every tool call, and the other two only at the start of a session and of each
turn. Most of the third row is `hook.py` itself, which imports the whole check pipeline: 197 ms at p50 over 20
starts outside Claude Code, 156 ms of it imports, measured on 2026-09-28. `sh pyrun` adds 36 ms, of which
`py -3` is about 14. Setting `IOGUARD_PYTHON` skips `py`.

The hook at the start of each turn only checks that the io server is running. When the server wrote its
heartbeat in the last 10 seconds, `hook.py` answers before it loads the pipeline. Through `sh pyrun`, that
answer took 120 ms at p50 over 15 starts on 2026-10-01, against 270 ms for the full pipeline in the same
checkout. A server that has gone quiet still gets the full pipeline, which tells you it's down.

The io server starts through `pyrun.cmd` and `py -3` in 395 to 411 ms on this machine, and in 231 to 248 ms
with `IOGUARD_PYTHON` naming `python.exe`. That's once per session.

## Why there's no command-hook fallback

Every Claude Code release io-guard supports, 2.1.281 and later, runs `mcp_tool` hooks
([`compat.md`](compat.md)). A fallback would have nowhere to live anyway. Your own settings can't name the
plugin's folder, and `/hooks` is read-only, so it can't switch the plugin's hooks off.
