---
title: Start git, the verify and format commands and every other program where the Bash tool finds it
stage: I
area: runtime
created: 2026-09-30
status: done
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

## What changed

All three held. Each is fixed, and each has a test that failed first.

1. **git.** `Git` takes its program, and `lib/git.py`'s `GIT` became `FLAGS`, the options alone, since each
   `Git` now names its own program. `Context.live` gives it `runs.git_program`: git by name when PATH holds it,
   as before, else from the Bash tool's tool folders, else the probe's git, else by name, so the start error
   says git is missing. `within` keeps the program. On this machine PATH holds `Git\cmd`, so nothing changes
   here.
2. **The verify and format commands.** `checks/verify_command.py` and `mcp/tools_format.py` start their
   command through `runs.start`, as `io.run` does since task 149: a bare name is looked for in the Bash tool's
   tool folders before PATH. A command neither holds starts as before, and `proc.run` names it missing.
   `runs.tool_folders` gives all three callers the same list: the probe's bash's folders that exist, and none
   off Windows.
3. **The first session's probe.** `hooks/entry.py`'s stamp covers `probe.json` beside the config files, so the
   context is built again, keeping the session's state, once the SessionStart probe writes it.

The tests:

- `tests/lib/test_runs.py`: `tool_folders` names only folders that exist, and none off Windows. `git_program`
  takes PATH's git, then the tool folders', then the probe's, then the name. Both failed first as missing.
- `tests/lib/test_git.py`: a `Git` given git's full path answers, a budgeted copy keeps it, and a `Git` given a
  missing program fails. It failed first: `Git` took no program.
- `tests/hooks/test_entry.py`: a probe written after the first call reaches the next, and the session's state
  survives. It failed first with `bash` None.
- `tests/checks/test_verify_command.py` and `tests/mcp/test_tools_format.py`, on Windows with Git: `grep` as a
  verify command and `tr` as a format command run with a PATH that holds none of Git's tool folders. Run against
  HEAD's two call sites, both failed. They pass now.
- The Git-free PATH and Git's bash these tests and `tests/mcp/test_tools_run.py` use are in
  `tests/support/shells.py`, `without_git_tools` and `git_bash`.

Evidence:

- `python tests/run_all.py`: 1,124 tests, OK, 2 skipped, against 1,118 at task 149.
- `live-run-tools`, `live-format`, `live-verify`, `live-stage`, `live-touched` and `live-empty` passed on the
  CLI 2.1.283. `live-format` and `live-stage` run the server's git, and `live-verify` its verify step.

Not checked live: a machine whose PATH has no git at all. This machine has `Git\cmd` on PATH, and the probes
run with it.

Docs: `docs/design/architecture.md` names `Git(program)`, `runs.tool_folders` and `runs.git_program`, says
which callers use `runs.start`, and says the hooks' context is built again when `probe.json` changes.

Checked on Windows 10 on 2026-09-30. macOS is covered by CI only.
