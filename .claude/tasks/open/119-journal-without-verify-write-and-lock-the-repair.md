---
title: Journal writes without verify.write, and take the file lock for the repair
stage: I
area: checks
created: 2026-09-29
status: open
depends-on: []
findings: [GIT-4]
platforms: [windows, macos]
commit: "fix: the journal runs without verify.write, and its repair takes the file lock"
---

## Why

The code review of 2026-09-29, slice A items 19 and 20, both by reading.

- `checks/journal_write.py` reads the PreToolUse snapshot `verify.write` keeps, but declares `after=()`. With
  `checks.verify.write.enabled` false, nothing is journaled, and `io.stage` by tag finds nothing.
- `checks/verify_write.py`'s repair calls `write_atomic` without `lib.locks.file_lock`, unlike the io tools
  (D13), so an `io.edit` of the same file from another session's server can land between the check's read
  and its write, and be overwritten.

## What to build

- The snapshot the journal needs is kept by whichever of the two checks is on, or by a small step both use.
  The journal declares the order it needs.
- The repair reads and writes the file inside `file_lock`, and gives up with a warning when the file changed
  since the check read it.
- A test for each.

## Where

`checks/journal_write.py`, `checks/verify_write.py`, `checks/registry.py`.

## Done when

- With `verify.write` off, an Edit is journaled, and the repair test holds the lock.
