---
title: Catch a script file that writes a file git tracks
stage: I
area: checks
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [12, 21, 46]
findings: [SHW-1]
platforms: [windows, macos]
commit: "feat: warn when an interpreter's script file writes a tracked file"
---

## Why

`shell.writes` reads the writes in a heredoc, a `python -c` body and a body `transport.body` moved into a file
(`checks/shell_writes.py`, `bash_writes`, lines 77 to 84). A script file the agent wrote earlier and then runs
by its path is never read, and a target it takes from its arguments is a variable, which `SCRIPT_WRITE` (line
29) cannot match anyway. In CLICKER on 2026-09-28,
`python <scratchpad>/fmt_hunks.py --apply Source/CLICKER/Tests/NetSphereReachTests.cpp` ran clang-format and
rewrote that tracked file through `open( path, "w" )`. The command passed with no `SHELL_WRITE`, and the only
code after it was `TOUCHED_BY_SHELL`, which reads as neutral. io.format did the same job with every check on.

This repository's own session did the same on 2026-09-28. Its scratchpad scripts rewrote tracked docs, such as
`README.md` and `docs/design/architecture.md`, and each run got only `TOUCHED_BY_SHELL`. The agent took that as
the expected answer and never asked whether the guard should have said more.

## What to build

- Before the run: when an interpreter runs a script file, read that file as `moved_bodies` reads a moved body.
  A write in it whose target is a literal tracked path is refused as today. A write whose target is not a
  literal, in a script run with a tracked file among its arguments, gets a `SHELL_WRITE` warning that names
  `io.edit`, or `io.format` when the script runs a formatter.
- After the run: `shell.touched` names a tracked file whose bytes an interpreter's script changed as a
  `SHELL_WRITE` warning, not a bare `TOUCHED_BY_SHELL`.
- Tests: a script file with a literal tracked target, one that writes `sys.argv[1]` given a tracked path, and
  one that writes only the scratchpad, which passes.
- A replay over the corpus before it ships. Read every warning of a call that succeeded, and put the counts in
  `## What changed`.

Task 46 changes what the same after-run report says about a change to git's index only, so this task goes after it.

## Where

`plugins/io-guard/scripts/ioguard/checks/shell_writes.py`, `checks/touched.py`, `tests/checks/`.

## Done when

- `python <scratchpad>/rewrite.py <tracked file>`, where `rewrite.py` opens its first argument for writing, gets
  a `SHELL_WRITE` warning before it runs, and a `SHELL_WRITE` warning after it changes the file.

## What changed

- `lib/shell.py`: `script_run` and `ScriptRun`, the script file an interpreter runs and the words after it,
  past its flags, with `-c`, `-m`, `-`, `-e` and a bare interpreter running none. `INTERPRETERS` moved here
  from `checks/shell_writes.py`.
- `checks/shell_writes.py`: `script_files` reads each script file a command runs, up to 1 MiB. A literal write
  in it to a tracked file is refused as a heredoc body's is, and the refusal names `io.edit`. A script that
  writes to a path it does not spell out, given a tracked file, gets a `SHELL_WRITE` warning naming `io.edit`,
  or `io.format` when the script names a formatter. `located` follows each cd once, for the redirects and the
  scripts both.
- `checks/touched.py`: after a command that ran a script file, the tracked files it changed get `SHELL_WRITE`
  beside `TOUCHED_BY_SHELL`.
- Tests: `tests/lib/test_shell.py` (the script and its arguments), `tests/checks/test_shell_writes.py` (4) and
  `tests/checks/test_touched.py` (1).
- `tools/probes/run_probe.py`: `live-script-write`.
- Docs: `docs/design/architecture.md` (the layout line and `script_run`), `docs/live-checks.md`,
  `docs/compat.md`.

Evidence:

- `python tests/run_all.py` ran 841 tests, all passing, up from 835.
- `live-script-write` passed on 2.1.281 and 2.1.283: the warning before the run, and the two after it.
- The replay: 18,966 recorded Bash calls ran a script file, and 4,860 of those scripts are still on disk. With
  real git at each recorded folder, the new rules refused nothing and warned twice, both on calls that ran. Both
  gave a tracked SmartTablesHost `.cpp` file to a scratch `to_crlf.py` that rewrites line endings, which is the
  write this task exists to name. `tools/replay.py` cannot run this, since it gives checks no file system, so a
  scratch script ran `shell.writes` itself.
- Not covered: a script run through PowerShell, and a script whose writes sit in a module it imports.
- Checked on Windows on 2026-09-28.
