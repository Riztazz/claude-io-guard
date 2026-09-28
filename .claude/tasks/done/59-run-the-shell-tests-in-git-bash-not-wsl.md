---
title: Run the shell tests in Git Bash on Windows, never in WSL's bash
stage: I
area: tests
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
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

## What changed

Why the class passed alone: WSL's `bash.exe` fails every call on this machine, with
`<3>WSL (13 - Relay) ERROR: CreateProcessCommon:818: execvpe(/bin/bash) failed`. The test compares the
moved command's output with the original's. Run alone, both printed that error with the same WSL process number,
so the two matched and the test passed having run nothing. In the full run the numbers differed.

- `tests/support/shells.py`, new: `bash()` and `sh()`. On Windows, `CLAUDE_CODE_GIT_BASH_PATH`, then the PATH
  with the session probe's `NOT_BASH` folders left out, then `bin/bash.exe` or `bin/sh.exe` in git's install
  folder. Elsewhere, `shutil.which`.
- `tests/lib/test_shell.py` and `tests/hooks/test_launcher.py` use them. `run_bash` asserts the command exited 0,
  so a shell that runs nothing fails and names itself.
- Docs: the `io-guard-dev` skill's list of `tests/support/` helpers.

Evidence:

- From PowerShell, `shells.bash()` is `C:\Program Files\Git\bin\bash.exe`, and `python tests/run_all.py` ran
  864 tests, all passing, with 9 skips. From Git Bash, it is `C:\Program Files\Git\usr\bin\bash.EXE`, with the
  same 864 and 9.
- With `CLAUDE_CODE_GIT_BASH_PATH` set to `C:\Windows\System32\bash.exe`, both `AMovedCommandRunsTheSame`
  comparisons fail on `run_bash`'s exit code, quoting WSL's error.
