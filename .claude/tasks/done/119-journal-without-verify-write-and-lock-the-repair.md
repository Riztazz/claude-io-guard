---
title: Journal writes without verify.write, and take the file lock for the repair
stage: I
area: checks
created: 2026-09-29
status: done
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

## What changed

- `checks/verify_write.py`: `write_snapshot` is the one step that keeps a write's snapshot, called by
  verify.write, and by journal.write when verify.write is off. The repair reads and writes inside
  `lib.locks.file_lock`, waits `REPAIR_WAIT_S`, 2 s, for a holder, and gives up when the lock stays held or
  the file changed since the check read it. Giving up leaves the loss to the comparison, which reports it as
  `EOL_MISMATCH` or `BOM_CHANGED`.
- `checks/journal_write.py`: runs at PreToolUse too, and declares `after` conform.write and conform.edit, the
  order it needs for the input the tool runs with. With verify.write off it keeps the snapshot and takes it
  at PostToolUse. With verify.write on it peeks, as before.
- `lib/locks.py`: `lock_folder` moved here from `mcp/in_place.py`, which now calls it, since a check may not
  import `mcp`.
- Tests, each failing first: with `checks.verify.write.enabled` false, an Edit is journaled with line 2 and
  the snapshot is taken (`tests/checks/test_journal_write.py`); a repair while the test holds the file lock
  writes nothing and reports `EOL_MISMATCH` and `BOM_CHANGED`; a repair after another write landed leaves
  that write (`tests/checks/test_verify_write.py`). The two repair tests first failed on missing names, so a
  temporary copy with `create=True` on the patches showed the behaviour failing too: the repair wrote over
  the held lock and over the other write. The suite of 1,037 passes on Windows, 2 skipped.
- `live-verify` passed on the CLI 2.1.283.
- Docs: `docs/design/architecture.md` (the package tree, `lib.locks`, the journal's writers, the repair).
- Checked on Windows on 2026-09-29.
