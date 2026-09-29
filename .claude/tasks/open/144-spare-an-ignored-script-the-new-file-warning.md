---
title: Spare a script in an ignored folder the new-file warning
stage: I
area: transport
created: 2026-09-29
status: open
depends-on: []
findings: [GIT-1]
platforms: [windows, macos]
commit: "fix: shell.writes leaves a script in an ignored folder alone"
---

## Why

Low. shell.writes warns when a shell command creates a script file inside a repository, with "This command
creates the script <path> inside the repository, where git sees it as a new file." The check asks only
whether the path is in a repository and not tracked (`ShellWrites.in_repository` and `lib.context.tracked`
in `plugins/io-guard/scripts/ioguard/checks/shell_writes.py`). A path under a gitignored folder is neither,
so it gets the warning too, and the warning's claim is false: git never lists an ignored file as new.

Seen on 2026-09-29 in this repository's own session, during task 129: `cp <scratchpad>/probe_unused.py
workbench/probe_unused.py` drew the warning, and `git check-ignore -v workbench/probe_unused.py` answers
`.gitignore:7:/workbench/`. `workbench/` is where the lead keeps byte-exact copies to test on, and other
projects keep build and cache folders the same way.

## What to build

- `GitPort` gains a question for whether git ignores a path, `git check-ignore -q` through `lib.git.GIT`,
  answered as True, False, or None when git cannot say, with the fake answering from a set the test gives.
- shell.writes warns about a new script only when git neither tracks nor ignores it. The answer is cached
  with `tracked`'s, and cleared on the same git command.

## Done when

- A test: a script created under an ignored folder gets no warning, and one under a folder git does not
  ignore still gets it.
- The suite passes, and a replay shows the SHELL_WRITE warnings drop only for ignored paths.
