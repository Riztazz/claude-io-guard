---
title: Guard where writes land, and explain locks
stage: C
area: bytes
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-27
depends-on: [10, 15]
findings: [PTH-5, STL-3, LCK-1, LCK-4]
platforms: [windows, macos]
commit: "feat: refuse device names and read-only files, and name what holds a locked file"
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

- **Allowed roots, dropped by the lead on 2026-09-27 (D27).** The plan was to refuse a write outside the project,
  the scratchpad, the memory folder and the user's extra roots with `OUTSIDE_WRITE_ROOT`. Replay showed 3.7% of
  recorded writes land in another repository on purpose, so no write is refused for where it lands.
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

## What changed

Checked on Windows 10 on 2026-09-27, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **The write-roots rule was not built.** Replay over 23,734 recorded Edit and Write calls: 880 (3.7%) landed in
  another repository or a folder outside any, 610 of them in auto mode, and almost all on purpose. The lead chose
  to drop the rule (D27) over four options. PTH-3 left the findings, and `OUTSIDE_WRITE_ROOT` left the plan.
- **`checks/location.py`, `write.location`, before an Edit or Write.** It refuses a file named for a Windows device,
  such as `nul.txt`, on Windows only (`RESERVED_NAME`). It refuses a read-only file (`READ_ONLY`), with
  `git lfs lock <path>` as the step when git marks the file lockable. A path through a junction or symbolic link
  into another repository goes ahead with a `LINKED_PATH` note naming that repository. When the session's own
  repository tracks such a path, a second `LINKED_PATH` warns once per session that a discard, stash or branch
  switch writes through the link. The first write to a file dirty at session start gets a line saying so.
- **`write.locks`, after an Edit or Write fails with EPERM, EBUSY or EACCES.** `FILE_LOCKED` names each process that
  holds the file, and says when none is left or when the platform could not answer.
- **`lib/locks.py`** is new: `holders` asks the Restart Manager through `ctypes` on Windows and `lsof -F pc` on
  macOS, and `Process` moved there from `lib/context.py`. `lib/paths.py` gained `reserved` and `link_target`.
  `FsPort` gained `link_target`, and `LiveFs.holders` now answers. The fakes gained links and more repository
  roots. `results.py` adds `LINKED_PATH`, `READ_ONLY` and `FILE_LOCKED`.
- **`tools/probes/`:** `live-read-only` and `live-locked`. A setup file can be made read-only, and a child Python
  can hold a file open, sharing reads only, for the length of the run.

Evidence:
- `python tests/run_all.py` ran 467 tests, all passing, against 453 after task 18. On this machine
  `test_a_child_that_holds_the_file_is_named` runs the real Restart Manager, which named the child `Python`
  with its process id in 95 to 104 ms. `test_link_target_follows_a_linked_folder_and_leaves_a_plain_path` runs a
  real junction.
- `run_probe.py verdicts`: `live-read-only` and `live-locked` pass on 2.1.281 and 2.1.283. The Edit of the
  read-only, lockable `Hero.uasset` was refused with `READ_ONLY: Hero.uasset is read-only. Lock it with git lfs
  lock Hero.uasset from the repository root, then call Edit again.` The Edit of a held `keep.txt` failed with the
  baseline's `EPERM: operation not permitted, rename`, and the model saw `FILE_LOCKED: Python (process 42544)
  holds keep.txt open, so the Edit tool could not replace it. Close that program or wait for it, then call the
  same tool again, never a shell write.`
- The same Edit succeeded while the holder shared both reads and writes, as Python's `open` does. Only a holder
  that shares reads alone, as an editor or a build does, makes the rename fail.
- Replay does not cover these checks: the corpus holds no file system, and no recorded Edit or Write named a
  device.

Docs updated: `architecture.md` sections 1 to 5, the write-roots key and its scope sentence removed. `context.md`:
D27, PTH-3 in the catalog, and a task 19 paragraph. `live-checks.md`, `compat.md`, the README's status line, a row
in "What it fixes" and the project-file sentence, `CLAUDE.md`'s layout, and D1 to D27 in the `io-guard-dev` skill
and `.claude/tasks/README.md`. The drawing still holds: location stays one of the check concerns it names.

Not checked:
- macOS, live or in CI until the lead pushes: the `lsof` path and the live holder test run on the macOS runner.
  The local macOS path simulation cannot run `link_target`, which calls the host's own `realpath`.
- `LINKED_PATH` in a live session. Its logic has unit tests, and the link itself is resolved by a real junction
  in `test_paths`, but no probe wrote through one.
- Task 30 still names "the kit as an extra write root" on line 36. It holds another session's uncommitted edits,
  so this task left it for that session.
