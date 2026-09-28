---
title: Name no deletion when a command only staged a rename another command made
stage: I
area: checks
created: 2026-09-28
status: open
depends-on: [46]
findings: []
platforms: [windows, macos]
commit: "fix: a rename's old path is a listed file, missing before and after"
---

## Why

On 2026-09-28 this repository's session ran `git mv .claude/tasks/open/44-... .claude/tasks/done/44-...`, and
`shell.touched` rightly said it changed the new path and deleted the old one. `git status` then showed
`RM open/44 -> done/44`. The next command was `git add .claude/tasks/done/44-...`, plus `awk` and `grep`, which
delete nothing. `shell.touched` still said:

```
TOUCHED_BY_SHELL: This command deleted .claude/tasks/open/44-build-the-offline-check-command.md. Delete any
new file the task does not need, and keep the rest on purpose.
```

After the `git add`, git lists the pair as `A done/44` and `D open/44`. `D open/44` is new in the status, and
`checks/touched.py` skips a new entry only when its path is in `before.listed` with the same stat. The snapshot
lists a rename under its new path alone, so the old path is missing from `before.listed`, and the check calls it
deleted.

## What to build

- The snapshot lists a rename's old path too, with its stat, which is none. A path missing before and after the
  command is then skipped by the stat test that already exists.
- A test in `tests/checks/test_touched.py`: a status with `R  old -> new` before and `A new`, `D old` after,
  with `old` missing on disk throughout, reports nothing.

## Where

`plugins/io-guard/scripts/ioguard/checks/touched.py`, and where the snapshot parses `git status -z`.

## Done when

- A `git add` that only stages a rename made earlier gets no `TOUCHED_BY_SHELL`.
