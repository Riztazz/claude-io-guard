---
title: Make io.snapshot keep every file it matches, and io.restore put back a deleted folder
stage: I
area: mcp
created: 2026-09-29
status: open
depends-on: []
findings: [GIT-6]
platforms: [windows, macos]
commit: "fix: io.snapshot keeps every file it matches and io.restore puts back deleted folders"
---

## Why

The code review of 2026-09-29, slice C items 1, 2 and 7.

- **A glob snapshot can be silently partial.** `mcp/tools_history.py` `gathered` filters
  `ctx.fs.files_under(cwd, limit)`, which stops the walk after `max_files + 1` files, before the pattern is
  applied. With 4,990 `.txt` and 10 `.py` in `a/` and 5 `.py` in `z/`, `io.snapshot ["**/*.py"]` answered
  "Kept 11 files". `z/*.py` in a project with more than 5,000 earlier files answered `PATH_NOT_FOUND`. A literal
  name holding `[`, `?` or `*`, such as `[id].tsx`, counts as a glob and matches nothing.
- **io.restore cannot restore into a deleted folder.** `write_atomic` calls `mkstemp` in the missing folder,
  and `restore` catches only `PermissionError`, so it ends in `GUARD_ERROR`. With several files, the earlier
  ones are restored and the error does not say which.
- **Expired snapshots stay.** `snapshots.sweep` runs only inside a later `io.snapshot`, not in the server's
  `expire` at start, so a snapshot outlives the seven days its result states. A snapshot cut short by a crash
  has no manifest and is never deleted.

## What to build

- `gathered` matches the pattern during the walk and counts only matches against `max_files`. A path that
  exists as written is taken literally before it is tried as a glob.
- `restore` makes the missing folders, and any failure names the files it restored and the one it could not.
- `server.expire` calls `snapshots.sweep`, which also deletes a snapshot folder with no manifest once it is
  older than a day.
- A test per case.

## Where

`mcp/tools_history.py`, `lib/context.py` (`files_under`), `lib/snapshots.py`, `mcp/server.py` (`expire`).

## Done when

- The three cases above behave as built, and `live-restore` still passes.
