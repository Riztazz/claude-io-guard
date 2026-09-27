---
title: Tell the agent which files a shell command changed
stage: D
area: stale
created: 2026-09-27
status: open
depends-on: [03, 10, 16]
findings: [STL-1, BYT-2, GIT-2, GIT-7]
platforms: [windows, macos]
commit: "feat: mark files a shell command changed as needing a fresh read"
---

## Why

A formatter, a script or git can change a file behind the agent's back:
- At best, the next Edit fails with "modified since read".
- At worst, a script has rewritten every line ending without anyone noticing (BYT-2).

The agent needs to hear which files a command changed.

## What to build

- **Before the command** (PreToolUse on Bash and PowerShell). Take a cheap snapshot, which is the primary source:
  - `git status --porcelain`, from the watchdog's cache when the server runs it
  - the modification times of the tracked files the agent has read this session (the read set from task 16)
- **After the command** (PostToolUse). Compare against the snapshot:
  - **Changed files the agent has read** get `TOUCHED_BY_SHELL` context: "re-read before editing: X, Y".
  - **New untracked files** are listed (GIT-2).
  - **Every changed file** is compared against its last profile with task 18's code, so a script that rewrote the
    endings is caught.
- **`bashEditDiff` is a secondary source** where task 03 confirms it. It counts only with `bashEditDiffEnabled: true`
  in user settings, so the README's settings snippet carries that line (task 34).
- **Stay under 200 ms on the Unreal repositories.** Skip the untracked-file scan of `Content/` and other LFS-heavy
  trees, as set in `skip_trees`.

## Where

`plugins/io-guard/scripts/ioguard/checks/touched.py`, `tests/checks/test_touched.py`.

## Done when

- Live on Windows: `clang-format -i` on a file the agent has read produces the re-read notice.
- Live on Windows: a script that converts a file's endings is reported.
- Latency is measured on CLICKER and stays under the 200 ms budget.
