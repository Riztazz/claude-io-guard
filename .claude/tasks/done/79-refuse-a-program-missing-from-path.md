---
title: Start a program named without a folder only from where PATH holds it
stage: H
area: lib
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: io-guard starts only a program PATH holds"
---

## Why

Fable's review of 2026-09-29 read that `probing.program` fell back to the bare name when PATH did not hold a
program, and that `io.format` and `verify.command` then passed it to `proc.run`. It judged that Windows'
CreateProcess would then search the parent process's current folder, the project, so a repository shipping
`clang-format.exe` would have it run. The lead asked for it to be fixed, and for the wider question, whether a
bare `git` or `taskkill` could be taken over the same way, to be answered.

Measured on Windows 10 with Python 3.14.0, neither reproduced. A copy of `hostname.exe` named `git.exe` in the
parent's current folder lost to the real git on PATH, and one named for a program PATH lacks did not start
("The system cannot find the file specified"), with and without `NoDefaultCurrentDirectoryInExePath`. The fall-
through is still fragile: an empty PATH entry means the current folder to macOS's `execvp`, and the search
order is the operating system's and Python's to change. So the fix went in as a guard.

## What changed

- `lib/proc.py`: `on_path`, moved from `probing.find`, skips empty PATH entries. `located` gives a bare name's
  place on PATH, a path as given, or None. `run` answers a start error, "<name> is not on PATH, so io-guard did
  not start it.", and `background` raises `FileNotFoundError`, for a bare name PATH lacks, before anything
  starts. `Pump.stop` runs `taskkill` through `run`.
- `probing.find` and `probing.program` went, and `io.format`, `verify.command`, `session_probe` and
  `tests/support/shells.py` use `proc` directly. A PATH lookup costs 1.4 ms here, against 19 ms for a git call,
  so there is no cache.
- Tests: `tests/lib/test_proc.py` (a skipped folder, an empty PATH entry, a planted program PATH lacks never
  starting in `run` or `background`, a path running as given), with the two lookup tests moved from
  `tests/lib/test_probing.py`. `tests/checks/test_session_probe.py` patches `proc.on_path`.
- Docs: `docs/design/architecture.md` (the tree and `proc`'s signatures).

Evidence:

- `python tests/run_all.py` ran 913 tests, all passing, up from 911: four new, two moved.
- `live-format` and `live-verify-output` passed on Claude Code 2.1.283: clang-format and Python still start
  through the lookup.
- macOS waits in task 36.
