---
title: Guard where writes land, and explain locks
stage: C
area: bytes
created: 2026-09-27
status: open
depends-on: [10, 15]
findings: [PTH-3, PTH-5, STL-3, LCK-1, LCK-4]
platforms: [windows, macos]
commit: "feat: refuse writes outside the allowed roots and name what holds a locked file"
---

## Why

Writes go wrong in four ways when the location is wrong:

- **Wrong checkout.** A write can land in another checkout of the same repository (PTH-3).
- **Linked folders.** In each project that uses the lead's kit, `.claude/skills/<name>`, `.claude/rules/shared`
  and `.claude/tools/shared` are junctions into the kit, and so are the plugin's folders in the Unreal projects.
  One edit there changes every linked repository, and checkpoint rewind skips linked paths.
- **Read-only files.** Writing a read-only LFS asset raises an editor modal that blocks the session.
- **Locked files.** The Edit tool's temp-file rename failed with EPERM 3 times.

## What to build

**Before Edit or Write** (PreToolUse Edit|Write):

- **Allowed roots.** Writes may land in the project, the session scratchpad, the memory folder, and any extra
  roots listed in the user's config. Refuse anything else with `OUTSIDE_WRITE_ROOT`. A project file cannot add a
  root (`docs/design/architecture.md`, section 5).
- **Links.** Resolve junctions and symlinks. When a path resolves into another repository, allow the write and
  add `LINKED_PATH` context that names the repository that owns the file.
- **Tracked links.** When git tracks a file whose path resolves through a link, warn once per session with
  `LINKED_PATH`: a discard, stash or branch switch writes through the link into the other repository
  (`context.md`, "Git through a junction").
- **Reserved names (PTH-5).** Refuse with `RESERVED_NAME`.
- **Read-only files.** Refuse with `READ_ONLY` and the unlock step: `git lfs lock <path>` when the file is
  LFS-lockable.
- **Dirty files.** Before the first write to a file that was already dirty at session start (task 10), warn.

**After a failed Edit or Write** (PostToolUseFailure with EPERM or EBUSY):

- Name the process that holds the file with `lib.locks.holders`: the Restart Manager API through `ctypes` on
  Windows, `lsof` on macOS.
- Say to retry or close that process (`FILE_LOCKED`).
- Never fall back to a script write.

## Where

`plugins/io-guard/scripts/ioguard/checks/location.py`, `lib/locks.py`, `lib/paths.py`,
`tests/checks/test_location.py`.

## Done when

- Live on Windows: a read-only file gets the unlock hint, and a file held open by another process gets that
  process's name.
- The `lsof` path passes its tests in CI on the macOS runner. Its live check waits in task 36.
