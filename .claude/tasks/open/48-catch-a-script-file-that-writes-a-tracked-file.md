---
title: Catch a script file that writes a file git tracks
stage: I
area: checks
created: 2026-09-28
status: open
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
