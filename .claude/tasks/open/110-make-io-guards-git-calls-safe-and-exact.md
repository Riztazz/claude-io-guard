---
title: Make io-guard's git calls run no repository hook and read paths exactly
stage: I
area: lib
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: io-guard's git calls run no repository hook and read paths exactly"
---

## Why

The code review of 2026-09-29: slice A items 7 and 11, slice B items 10 and 11.

- **A repository's `core.fsmonitor` runs.** io-guard's `git status` and `rev-parse` run in any repository a
  command names, and git runs the `core.fsmonitor` program from that repository's `.git/config`. A scratch
  repository with `core.fsmonitor = python hook.py` created the hook's marker file after `Git().root()` and
  `.status()`. A `.git/config` arrives with a repository handed over as a folder or an archive, not with a
  clone.
- **A path's tracked answer never changes.** `checks/shell_writes.py` `tracked()` caches git's answer per path
  for the session. `echo x > new.py`, untracked and cached false, then a commit of it, then
  `sed -i ... new.py` was not refused.
- **A rename in the worktree column breaks the status parse.** `lib/git.py` `parse_status` reads the original
  path only for `R` or `C` in the index column. After `mv a.txt b.txt; git add -N b.txt`, git gives a
  worktree rename, and the parse returned a garbage entry `path='xt'`.
- **A file name is read as a pathspec.** `is_tracked` passes `path.name` to `git ls-files --error-unmatch`.
  With `i.tsx` tracked, the untracked `[id].tsx` counts as tracked, and `shell.writes` would refuse a write
  to it.

## What to build

- Every git call io-guard makes adds `-c core.fsmonitor=false` beside `core.quotepath=false`, and
  `--literal-pathspecs` wherever it passes a path.
- `parse_status` reads the original path for `R` or `C` in either column.
- The tracked cache holds for one hook call, or is dropped after any `git` command the session runs.
- A test per case, the fsmonitor one with a marker file.

## Where

`lib/git.py`, `checks/shell_writes.py`, `checks/touched.py`.

## Done when

- The four cases behave as built, and `live-touched` still passes.
