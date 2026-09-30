---
title: Start git, the verify and format commands and every other program where the Bash tool finds it
stage: I
area: runtime
created: 2026-09-30
status: open
depends-on: [149]
findings: [SHL-3]
platforms: [windows]
commit: "fix: every program io-guard starts is found as the Bash tool finds it"
---

## Why

Found by Fable's review of task 149 on 2026-09-30, which the lead asked for because finding a program on Windows
keeps coming back: task 142 for a bash body, task 149 for an `io.run` argv. Task 149 made `io.run` look in the
tool folders of the Bash tool's bash, before PATH, as the Bash tool's shell does. Three other paths still start a
program by its bare name on the Windows PATH that Claude Code gives io-guard's server, which holds
`C:\Windows\system32` and `Git\cmd` and none of Git's tool folders:

1. **git itself.** `lib/git.py:19` and `:109` start a bare `git` with `env=None`, so the server's own PATH.
   Git for Windows' installer offers "Use Git from Git Bash only", which puts no Git folder on PATH. The hooks
   run under `sh pyrun`, Git Bash, and find git. The server does not, so `io.format`'s changed lines, `io.stage`
   and every git call the server makes fail with "git is not on PATH", while `probe.json` holds
   `mingw64\bin\git.EXE`. Fable read this and did not run it: this machine has `Git\cmd` on PATH.
2. **The user's verify and format commands.** `checks/verify_command.py:49` and `mcp/tools_format.py:221`
   start them through `proc.run` with `ctx.env`. A verify key naming `sed`, `diff` or `awk` fails "not on PATH"
   where the Bash tool runs it, and one naming `find` or `sort` starts Windows' own program.
3. **The first session on a machine.** `hooks/entry.py:48`: `config_stamp` covers the config and trust files,
   not `probe.json`. A server context built before the first SessionStart wrote the probe keeps `bash` as None
   for the session, so task 149's folders never reach it.

## What to build

- One way to start a program by name, `runs.start` or its successor, used by `lib.git`, `verify.command`,
  `io.format` and `io.run` alike, with the probe's bash's tool folders passed in.
- `lib.git` starts the probe's git when PATH has none.
- A session's context picks up `probe.json` once the session probe writes it.

## Where

`lib/git.py`, `lib/proc.py`, `lib/runs.py`, `checks/verify_command.py`, `mcp/tools_format.py`, `hooks/entry.py`.

## Done when

- A test starts git, a verify command and a format command with a PATH that holds none of Git's folders, and
  each is found where the Bash tool finds it.
- A test shows a context built before `probe.json` exists gains the probe's bash once it does.
