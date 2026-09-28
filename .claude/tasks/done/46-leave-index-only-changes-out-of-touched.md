---
title: Leave a change to git's index alone in shell.touched
stage: I
area: checks
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [21]
findings: []
platforms: [windows, macos]
commit: "fix: name only files a shell command changed on disk"
---

## Why

`shell.touched` compares git status before and after a Bash or PowerShell command, and names every path whose
status code changed as a file the command changed. The status code holds two halves, the index and the working
tree, so `git add` and `git commit`, which change only the index, get `TOUCHED_BY_SHELL` for every file they
stage or commit, with the step to delete any new file the task does not need. This session saw it on
2026-09-28 after `git add` of 25 files ("This command changed .claude/tasks/context.md, ... CLAUDE.md,
README.md ... and 17 more") and after a `git commit` ("This command changed CLAUDE.md").

## What to build

- Compare the working-tree half of each status code, and untracked paths, never the index half alone.
- A test for `git add`, `git commit` and `git reset` of a file whose bytes did not change, each naming nothing,
  beside the existing test for a command that does change a tracked file.
- A replay over the corpus's recorded `git add` and `git commit` calls, with the count before and after.

## Where

`plugins/io-guard/scripts/ioguard/checks/touched.py`, `tests/checks/test_touched.py`.

## Done when

- `git add`, `git commit` and `git reset` of files whose bytes did not change get no `TOUCHED_BY_SHELL`.

## What changed

The first bullet above was wrong, so it was not built. `git add` changes the working-tree half too: ` M`
becomes `M `, because the working tree now matches the index. What tells a write from an index change is the
file itself.

- `lib/context.py`: `ShellSnapshot.listed`, the size and time of each file git status listed before the
  command.
- `checks/touched.py`: a listed file whose code moved while its size and time did not is left out, as `git add`,
  `git commit` and `git reset` leave one. So is a name git removed from the index while the file stays on disk,
  as `git rm --cached` leaves its `D ` and `??`.
- Tests: `tests/checks/test_touched.py`, the four index cases naming nothing, and a listed file whose bytes
  moved still named.
- `tools/probes/run_probe.py`: `live-touched-index`. It uses `git reset`, not `git commit`, because the probe's
  model reads the lead's global rule against committing without a grant, and refused on 2.1.281.
- Docs: `docs/design/architecture.md` (`ShellSnapshot`), `docs/live-checks.md`, `docs/compat.md`.

Evidence:

- `python tests/run_all.py` ran 835 tests, all passing, up from 833.
- `live-touched-index` passed on 2.1.281 and 2.1.283: the command that created `n.txt` was named once, and
  `git add` and `git reset` were not. `live-touched` passed again on both.
- Not run: the replay over the corpus. `tools/replay.py` gives checks no file system, so `shell.touched` sees
  no stat there.
- Left as it was: a file that was clean before a command and changed only in the index, as `git reset --soft`
  leaves one, is still named, because only listed files have a size and time from before.
- Checked on Windows on 2026-09-28.
