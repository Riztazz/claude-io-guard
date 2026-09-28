---
title: Leave a change to git's index alone in shell.touched
stage: I
area: checks
created: 2026-09-28
status: open
depends-on: [21]
findings: []
platforms: [windows, macos]
commit: "fix: name only files a shell command changed on disk"
---

## Why

`shell.touched` compares git status before and after a Bash or PowerShell command, and names every path whose
status code changed as a file the command changed. The status code holds two halves, the index and the working
tree, so `git add` and `git commit`, which change only the index, get `TOUCHED_BY_SHELL` for every file they
stage or commit, with the step to delete any new file the task does not need. This session saw it on
2026-09-28 after `git add` of 25 files ("This command changed .claude/tasks/context.md, ... CLAUDE.md,
README.md ... and 17 more") and after a `git commit` ("This command changed CLAUDE.md").

## What to build

- Compare the working-tree half of each status code, and untracked paths, never the index half alone.
- A test for `git add`, `git commit` and `git reset` of a file whose bytes did not change, each naming nothing,
  beside the existing test for a command that does change a tracked file.
- A replay over the corpus's recorded `git add` and `git commit` calls, with the count before and after.

## Where

`plugins/io-guard/scripts/ioguard/checks/touched.py`, `tests/checks/test_touched.py`.

## Done when

- `git add`, `git commit` and `git reset` of files whose bytes did not change get no `TOUCHED_BY_SHELL`.
