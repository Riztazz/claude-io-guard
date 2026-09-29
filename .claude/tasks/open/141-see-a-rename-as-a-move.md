---
title: See a rename the command names as a move, not new files
stage: I
area: checks
created: 2026-09-29
status: open
depends-on: []
findings: [GIT-2, GIT-7]
platforms: [windows, macos]
commit: "fix: shell.touched sees a named rename as a move"
---

## Why

Found on 2026-09-29, numbering the code review's tasks. A loop of `mv "fable-$s.md" "$n-$s.md"` renamed 12
untracked files, and got:

```
TOUCHED_BY_SHELL: This command created 129-move-shared-mechanism-out-of-checks.md, 130-name-a-program-once.md,
... and 4 more. Delete any new file the task does not need, and keep the rest on purpose.
```

The command names `mv`, so every file it made is one it moved, and the advice to delete new files is wrong.
`checks/touched.py` `moves` pairs a path that left with one that arrived only when both have the same file
name, so a rename, which changes the name, reads as a deletion and a new file. The files were untracked, so
git shows no rename, and the deletion side is `vanished`.

## What to build

- When the command names a move, and as many paths left as arrived, pair them, in the order the command names
  them where it can be read, else by size. A pair is a rename, which needs no advice.
- A test: two untracked files renamed by `mv` in one command name nothing, or `moved a to b`, and never
  `created`.

## Where

`checks/touched.py` (`moves`, `names_a_move`).

## Done when

- The case above gets no delete advice, and `live-touched-move` still passes.
