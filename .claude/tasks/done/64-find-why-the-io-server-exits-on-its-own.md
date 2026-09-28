---
title: Keep another session's process kill from taking io-guard's server with it
stage: I
area: mcp
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [23]
findings: []
platforms: [windows, macos]
commit: "feat: warn before a command stops other sessions' processes"
---

## Why

On 2026-09-28, after the lead restarted the desktop app onto build 1576e6c, this repository's session got:

```
SERVER_DOWN: io-guard's io server last answered at 20:05:34, so the tool calls since then ran without its
checks. Claude Code starts it again at the next tool call, and /mcp shows why when it cannot.
```

The warning was true. Claude Code's MCP log for the session,
`~/AppData/Local/claude-cli-nodejs/Cache/C--Users-felia-Desktop-projs-claude-io-guard/mcp-logs-plugin-io-guard-io/`,
file `2026-09-28T17-54-07-874Z.jsonl`, shows the server starting and closing with no `Terminating MCP server
process tree` line, so the server left on its own:

| Started (UTC) | Closed (UTC) | Claude Code's line |
|---|---|---|
| 17:54:07 | 18:03:51 | `connection closed after 582s (cleanly)`, the app restart |
| 18:04:34 | 18:05:38 | `connection closed after 64s (cleanly)` |
| 18:09:29 | 18:09:37 | `connection closed after 8s (cleanly)` |
| 18:09:44 | | |

The session's `.alive` file said `"stopped": null` for the one that died at 18:05, so it never ran its clean
stop. CLICKER's log shows a 64-second life at 17:46:56 to 17:48:02 too, on the old build f86e86e, so the
update did not start this. No tool call ran without the server that time: Claude Code started it again at the
next hook call. Each restart costs about 300 ms, and each gap at a prompt costs a `SERVER_DOWN` warning.

## The cause, found on 2026-09-28

Another session on the machine killed it. The lead's session `70c24645`, in another project, restarted its own
local web server with this PowerShell call, four times:

```
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -match "server.py" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

io-guard's server runs as `python.exe .../io-guard/<version>/scripts/server.py`, so every session's io-guard
server matched. Each kill came about 2 seconds before a close in the MCP log:

| That session's call (UTC) | io-guard's close (UTC) |
|---|---|
| 18:03:49 | 18:03:51, after 582 s |
| 18:05:36 | 18:05:38, after 64 s |
| 18:09:36 | 18:09:37, after 8 s |
| 18:11:49 | 18:11:51, after 126 s |

CLICKER's 17:48:02 close is a different one: Claude Code logged `Terminating MCP server process tree`, its own
stop. A forced stop runs no clean stop, which is why the `.alive` file kept `"stopped": null`.

## What to build

- A shell check that warns before a command stops processes picked by name or by a command-line match, such
  as `Stop-Process -Name`, a `Get-CimInstance` filter piped into `Stop-Process`, `taskkill /IM`, `pkill -f` and
  `killall`. Those reach every session's processes. The fix it names is the process's own id or its port.
  Replay it before it ships.
- A server script name less generic than `server.py`, so a match meant for one project's server misses
  io-guard's. `.mcp.json`, the tests, the probes and the docs name it.
- `SERVER_DOWN` can say the server's process ended with no clean stop, which is what a kill leaves.

## Where

`plugins/io-guard/scripts/server.py`, `plugins/io-guard/.mcp.json`, `plugins/io-guard/scripts/ioguard/checks/lint.py`,
`plugins/io-guard/scripts/ioguard/lib/`, `.claude/tasks/context.md`.

## Done when

- A command that kills by name or by command-line match gets a warning with the pid route, and a kill of
  `server.py` processes leaves io-guard's server running.

## What changed

Two commits, as the lead chose both fixes.

The rename, `fix: name the io server's script so a kill aimed at server.py misses it`:

- `plugins/io-guard/scripts/server.py` is now `ioguard_mcp.py`, moved with `git mv`, and its docstring says why
  the name carries no `server.py`. `.mcp.json` starts it.
- `tests/test_plugin_files.py`, `tests/mcp/test_server.py`, `tests/support/injected.py` and
  `tests/support/inject/sitecustomize.py` name it.
- Docs: `docs/design/architecture.md` (the tree, the `.mcp.json` sample, section 11's table),
  `docs/launcher.md`.

The warning, `feat: warn before a command stops other sessions' processes`:

- `lib/kills.py`, new: `broad_stop(command, code)`. It finds the stop in the blanked command and reads the
  names it gives from the command itself, at the same offsets, since a name often sits in quotes.
- `lib/shell.py`: `blanked`, the bash counterpart of `pwsh.blanked`.
- `lib/results.py`: `STOPS_BY_MATCH`, a warning. `checks/lint.py` gives it for Bash and PowerShell, with the
  route by id or by port.
- The rule, narrowed twice on the corpus's evidence (D32):
  1. Any stop by name or by a listing flagged 453 of 62,100 recorded Bash and PowerShell calls. The 436 the
     next step drops stop one application by name, most of them the editor and its helpers, and none names a
     shared runtime.
  2. A stop by a shared runtime's name or by a command-line match flagged 17. Two were a stop by a literal id
     beside a listing that only printed, now left alone. Eleven were a `Win32_Process` listing already
     narrowed by `Name like` to one application, now left alone too.
  3. The rule as shipped flags 4: a `CommandLine -like '*http.server 8791*'`, a `pkill -f "http.server 8731"`,
     a `CommandLine -match 'UnrealBuildTool|...'` over every process, and a `Name like 'python%'` listing with
     a command-line match. Each is a match that another session's process can meet.
- Tests: `tests/lib/test_kills.py` (2, over 38 shapes), `tests/checks/test_lint.py` (2), and
  `tests/lib/test_shell.py` (1, `blanked`).
- Docs: `docs/design/architecture.md` (the tree, the codes table), `README.md` (a row in What it fixes),
  `.claude/tasks/context.md` (D32), and the plugin skill's code table from `tools/skill.py`.

Not built: a `SERVER_DOWN` that says a kill ended the server. A forced stop and a crash leave the same
`.alive` file, so the warning could not tell them apart.

Evidence:

- `python tests/run_all.py` from Git Bash ran 869 tests, all passing, up from 864.
- `live-empty`, `live-server` and `live-server-down` passed on 2.1.283 on Windows on 2026-09-28 with the
  renamed script.
- `python tools/ioguard.py check` on the command that killed the servers gives `STOPS_BY_MATCH` and lets it
  run.
- Not run live: the warning in a session. `shell.lint`'s warnings already reach the model live
  (`live-answers`), and the offline check runs the same pipeline.
