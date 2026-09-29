---
title: Never find a program in the current folder, which is the user's project
stage: H
area: lib
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [79]
findings: []
platforms: [windows, macos]
commit: "fix: io-guard never finds a program in the project's own folder"
---

## Why

CI on GitHub's Windows runner failed task 79's test on 2026-09-29: `proc.on_path("tool", {"PATH": ";<empty>"})`
returned `.\tool.EXE`, a file planted in the current folder. Python's `shutil.which` searches the current folder
first on Windows, even with `path=` given, unless `NoDefaultCurrentDirectoryInExePath` is set. The lead's machine
sets it to 1, so the test passed here.

Task 79's measurement was wrong for the same reason. Its hijack test ran with the variable inherited, so both of
its runs were protected. Rerun without it on Windows 10 and Python 3.14.0, a copy of `hostname.exe` named
`git.exe` in the parent's current folder ran in place of the real git on PATH, and one named for a program PATH
lacks started too. On a machine without the variable, CreateProcess searches the parent's current folder before
PATH. io-guard's server runs in the project, so before task 79 a repository shipping `git.exe` at its root had it
run by every hook's git call. Task 79 routed every bare name through `on_path`, which still found the planted
file through `shutil.which`.

## What changed

- `lib/proc.py`: `on_path` looks for the file in each absolute PATH folder itself, with PATHEXT's extensions on
  Windows, and never calls `shutil.which`. An empty or relative entry, such as `.`, is passed over. `run` and
  `background` start the full path it gives, so CreateProcess and `execv` do no search.
- `lib/runs.py`: `io.run`'s bash, pwsh, powershell and node come from `proc.on_path`, not `shutil.which`.
- Tests: `tests/lib/test_proc.py` plants `tool` in the current folder and removes
  `NoDefaultCurrentDirectoryInExePath` from the environment, and finds nothing for no entry, an empty entry,
  `.` and a relative folder. It failed all four on the old code and passes on the new. A program on PATH comes
  back as its full path.
- Docs: `docs/design/architecture.md` (`proc.on_path`).

Evidence:

- `python tests/run_all.py` ran 915 tests, all passing.
- `live-format`, `live-verify-output` and `live-trust` passed on Claude Code 2.1.283: clang-format and Python
  start through the new lookup.
- macOS waits in task 36, and CI's macOS runner covers the POSIX branch.
