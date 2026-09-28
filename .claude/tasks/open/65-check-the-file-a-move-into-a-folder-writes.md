---
title: Check the file a mv or cp into a folder writes, not the folder
stage: I
area: checks
created: 2026-09-28
status: open
depends-on: [12]
findings: []
platforms: [windows, macos]
commit: "fix: a mv or cp into a folder writes the file it lands as"
---

## Why

On 2026-09-28 this repository's session ran
`mv .claude/tasks/open/64-find-why-the-io-server-exits-on-its-own.md .claude/tasks/done/`, a task file git did
not track yet, into a folder of tracked files. `shell.writes` refused it:

```
SHELL_WRITE: This command writes C:/Users/felia/Desktop/projs/claude_io_guard/.claude/tasks/done, which git
tracks, through mv, so the write skips io-guard's byte checks and Claude Code's checkpoints. Use the Edit tool
to change it, or the Write tool to replace it whole.
```

The file `mv` writes is `.claude/tasks/done/64-find-why-the-io-server-exits-on-its-own.md`, new and untracked.
`bash_writes` in `checks/shell_writes.py` takes the last argument of `cp` or `mv` as the target, and
`tracked` then asks git about the folder, which it answers as tracked. The fix the refusal names cannot move a
file either.

## What to build

- When the last argument of `cp` or `mv` is a folder, by a trailing slash or by being one on disk, the target
  is each source's name inside it. `cp -t folder` and `mv -t folder` name the folder first.
- `tracked` answers for a file. A folder is never a write target.
- A test for each: a move of an untracked file into a tracked folder passes, and a move onto a tracked file
  inside it is still refused.
- Replay: the refusals of `cp` and `mv` before and after, in `## What changed`.

## Where

`plugins/io-guard/scripts/ioguard/checks/shell_writes.py`, `tests/checks/test_shell_writes.py`.

## Done when

- A `mv` of a new file into a folder of tracked files runs with no `SHELL_WRITE`.
