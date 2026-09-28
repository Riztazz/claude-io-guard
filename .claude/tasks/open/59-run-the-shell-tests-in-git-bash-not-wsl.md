---
title: Run the shell tests in Git Bash on Windows, never in WSL's bash
stage: I
area: tests
created: 2026-09-28
status: open
depends-on: []
findings: []
platforms: [windows]
commit: "test: run the shell tests in the bash Claude Code runs"
---

## Why

On 2026-09-28 `python tests/run_all.py` from PowerShell failed 10 tests, and the same run from Git Bash passed
all 858. `tests/lib/test_shell.py` takes `shutil.which("bash")` and `tests/hooks/test_launcher.py` takes
`shutil.which("sh") or shutil.which("bash")`. From PowerShell the PATH has no Git Bash, so `bash` is
`C:\Windows\System32\bash.exe`, WSL's launcher. On this machine it prints
`<3>WSL (37 - Relay) ERROR: CreateProcessCommon:81...` and runs nothing:

- `AMovedCommandRunsTheSame`: 2 failures, where both sides print WSL's error with a different process number.
- `PyrunUnderSh`: 5 failures and 3 errors, where stdout is empty.

`tests.lib.test_shell.AMovedCommandRunsTheSame` alone, from PowerShell, passed. What differs in the full run is
not known yet.

WSL's bash is never the shell these tests stand for. Claude Code's Bash tool runs Git Bash on Windows
(`docs/compat.md`, the Git Bash 5.2.37 row).

## What to build

- One helper in `tests/support/` that finds Git Bash on Windows: the bash beside `git.exe`'s install, or
  `CLAUDE_CODE_GIT_BASH_PATH`, and never a bash under `System32`. On macOS it stays `shutil.which`.
- Both test files use it. With no Git Bash found, the tests skip and say why.
- Find why the class passes alone and fails in the full run, and write it here.

## Where

`tests/lib/test_shell.py`, `tests/hooks/test_launcher.py`, `tests/support/`.

## Done when

- `python tests/run_all.py` passes the same count from PowerShell and from Git Bash on Windows.
