---
title: Spare a script in an ignored folder the new-file warning
stage: I
area: transport
created: 2026-09-29
status: done
depends-on: []
findings: [GIT-1]
platforms: [windows, macos]
commit: "fix: shell.writes leaves a script in an ignored folder alone"
---

## Why

Low. shell.writes warns when a shell command creates a script file inside a repository, with "This command
creates the script <path> inside the repository, where git sees it as a new file." The check asks only
whether the path is in a repository and not tracked (`ShellWrites.in_repository` and `lib.context.tracked`
in `plugins/io-guard/scripts/ioguard/checks/shell_writes.py`). A path under a gitignored folder is neither,
so it gets the warning too, and the warning's claim is false: git never lists an ignored file as new.

Seen on 2026-09-29 in this repository's own session, during task 129: `cp <scratchpad>/probe_unused.py
workbench/probe_unused.py` drew the warning, and `git check-ignore -v workbench/probe_unused.py` answers
`.gitignore:7:/workbench/`. `workbench/` is where the lead keeps byte-exact copies to test on, and other
projects keep build and cache folders the same way.

## What to build

- `GitPort` gains a question for whether git ignores a path, `git check-ignore -q` through `lib.git.GIT`,
  answered as True, False, or None when git cannot say, with the fake answering from a set the test gives.
- shell.writes warns about a new script only when git neither tracks nor ignores it. The answer is cached
  with `tracked`'s, and cleared on the same git command.

## Done when

- A test: a script created under an ignored folder gets no warning, and one under a folder git does not
  ignore still gets it.
- The suite passes, and a replay shows the SHELL_WRITE warnings drop only for ignored paths.

## What changed

The claim held, with one name moved: `tracked` lives in `lib/session.py` since task 135, not `lib.context`.
One part of "What to build" did not hold as written: `git check-ignore` refuses `--literal-pathspecs`, which
`lib.git.FLAGS`, `GIT` before task 151, passed on every call ("pathspec magic not supported by this command: 'literal'"). check-ignore
takes paths, never patterns, so it runs with the two `-c` options alone, now `CONFIG`, and every other call
keeps `FLAGS`, the options with `--literal-pathspecs`.

- `GitPort.is_ignored(path)`, in `lib/ports.py`. `Git.is_ignored` runs `git check-ignore -q` and answers exit
  0 as True and 1 as False, and raises `GitError` for anything else. `FakeGit` answers from an `ignored` set,
  and the replay's `SnapshotGit` asks git once per path.
- `Git.folder` is now the nearest folder at or above a path that exists, so git can answer for a script in a
  folder the same command creates, which `check-ignore` needs and `root` gains.
- `lib/session.py`: `ignored(path, git, session)` caches git's answer as `tracked` does, and
  `SessionState.forget_git` clears both on a command that runs git, in place of `shell.writes` clearing the one
  dict itself.
- `checks/shell_writes.py` warns about a new script only when git neither tracks nor ignores it. When git
  cannot say, the warning stays, as before.

The tests, each seen failing first:

- `tests/checks/test_shell_writes.py`: a script under an ignored folder draws no warning, and one under a
  folder git does not ignore still does. After a git command, the ignore answer is asked again.
- `tests/lib/test_git.py`: in a real repository with `/build/` ignored, `is_ignored` answers True for
  `build/new/x.py`, a path under a folder that does not exist yet, and False for a tracked file and a new one.

Evidence:

- `python tests/run_all.py`: 1,128 tests, OK, 2 skipped, against 1,125 at task 150.
- Replay over the corpus, HEAD against this change, all 22 checks: `shell.writes` warnings on calls that ran
  went from 29 to 28, on failed calls stayed 3, and its refusals did not move. No other check changed. A
  replay of `shell.writes` alone with the ignore check turned off lists the 29: one script's folder is in its
  project's `.gitignore`, which `git check-ignore -v` confirms, and the other 28 are not ignored. So the
  warnings drop only for ignored paths.
- `live-script-write`, `live-empty` and `live-touched` passed on the CLI 2.1.283.

Docs: `docs/design/architecture.md` names `GitPort.is_ignored`, `ignored` in `session.py`'s row, and the
warning's new condition in `shell_writes.py`'s row. The module docstring says the same.

Checked on Windows 10 on 2026-09-30. macOS is covered by CI only.
