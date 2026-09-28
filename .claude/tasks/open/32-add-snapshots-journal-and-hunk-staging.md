---
title: Add snapshots, an edit journal and hunk staging
stage: H
area: mcp
created: 2026-09-27
status: open
depends-on: [18, 23, 31]
findings: [GIT-4, GIT-6, VFY-6, BYT-9, BYT-10]
platforms: [windows, macos]
commit: "feat: snapshot files before a task, journal every write, and stage by hunk"
---

## Why

Three workarounds show what is missing:

- **No undo for a batch.** Agents copied files into before-folders first: 722 files in one, and 105, 79 and 37 in
  others.
- **No proof of a comment-only pass.** Agents wrote comment-stripping checkers to show that a pass changed no code.
- **No record of which edit belongs to which task.** To split one session's work into commits, SmartTablesHost
  replayed its own transcript with five scripts.

It comes after the measurement (D20), so task 31's numbers can reshape it.

## What to build

- **Journal.** The hooks record every write through Edit, Write or an io tool in io-guard's folder: the file,
  the hunk ranges, the tool, the time, and an optional task tag.
- **`io.snapshot(paths[], tag)` and `io.restore(tag, paths?)`.** The before-copies live in io-guard's folder,
  under a handle that expires after seven days (`docs/design/architecture.md`, section 7). A restore over newer
  edits elicits the user's yes first.
- **`io.compare(tag, mode)`.** Shows whether the code is unchanged, ignoring comments or ignoring include lines
  (VFY-6).
- **`io.stage(file, hunks[])`.** Stages the chosen hunks through `git apply --cached --recount` and keeps the index
  bytes exact (BYT-10). It never commits.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_history.py`, `tests/mcp/test_tools_history.py`.

## Done when

- A batch across 10 files restores exactly: every file's hash matches its before-copy.
- Staging 2 of 3 hunks leaves the third unstaged, and `git diff --cached` shows exactly those 2.
