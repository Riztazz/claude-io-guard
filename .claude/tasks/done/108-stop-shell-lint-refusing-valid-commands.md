---
title: Stop shell.lint refusing valid commands, and check python -c behind its flags
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: [SHL-1, SHW-6]
platforms: [windows, macos]
commit: "fix: shell.lint refuses only what bash or PowerShell would refuse"
---

## Why

The code review of 2026-09-29: slice A items 8, 9 and 10, slice B item 16. Rerun with `tools/ioguard.py check`
on Windows on 2026-09-29:

| Command | Answer | Wrong because |
|---|---|---|
| `wait-on http://localhost:3000`, `start-server`, `format-patch` | `DIALECT_MISMATCH`, refused | `CMDLET` takes any `<verb>-<letters>` as a cmdlet, whether or not the program exists |
| `echo "${ENV:-dev}"`, `"$ENV:8080"` | `DIALECT_MISMATCH`, refused | `BASH_EXPANDS` matches `${env:` without case |
| `python2 -c "print 'x'"`, `py -2 -c ...` | `INLINE_SCRIPT_INVALID`, refused | compiled with io-guard's own 3.14 |
| `python -X utf8 -c "print('hello'"` | nothing | `PYTHON_C` wants flags of letters and digits, so `-X utf8`, `-W ignore` and `-Bc` hide the body: not compiled, not moved |

## What to build

- `CMDLET` matches only the verbs PowerShell approves with a noun that starts upper case, as a cmdlet is
  written, or a name io-guard knows is a cmdlet. A name found on `PATH` is never a cmdlet.
- `BASH_EXPANDS` is case-sensitive: `$env:` only.
- The compile check runs only for a Python 3 command: `python`, `python3`, `py -3` or `py` with no version.
  `python2` and `py -2` are left alone.
- `PYTHON_C` takes `-X <option>`, `-W <option>` and grouped flags such as `-Bc`, for `transport.body` and the
  compile check alike.
- A replay over the corpus: the refusals each change removes, and any it adds, in `## What changed`.

## Where

`checks/lint.py`, `lib/shell.py` (`PYTHON_C`), `checks/transport_body.py`.

## Done when

- Every row gives the right answer, and the replay shows no new false refusal.

## What changed

- `checks/lint.py`: `CMDLET` matches an approved verb and a noun that starts upper case, as PowerShell
  writes a cmdlet, and `COMMON_CMDLETS` names 39 cmdlets matched in any case, so `get-childitem .` is still
  refused while `wait-on`, `start-server` and `test-runner` run. `BASH_EXPANDS` and `POWERSHELL_ONLY` need a
  letter or `_` after `env:`, so `${ENV:-dev}` and `$ENV:8080` pass and `$Env:PATH` is still refused. The
  build kept case-insensitive `$Env:` over the task's `$env:` only, since PowerShell reads both.
  `python3()` leaves out `python2` and `py -2`, for heredoc, `-c` and named bodies alike.
- `lib/shell.py`: `PYTHON_C` takes `-X <option>` and `-W <option>` and a `-c` closing a group such as
  `-Bc`. `transport.body` and the compile check both read it through `inline_bodies`.
- Tests, each failing first: the task's rows as bash and their real cmdlets as refused, a body behind
  `-X`, `-W` and `-Bc` refused for not compiling, and a Python 2 body passing (`tests/checks/test_lint.py`).
  `inline_bodies` finds the body behind `-X dev -W error::DeprecationWarning -Ic` (`tests/lib/test_shell.py`),
  4 errors on HEAD's code. The suite of 1,008 passes on Windows, 2 skipped.
- Replay: `shell.lint` and `transport.body` over every recorded Bash and PowerShell call, HEAD against the
  change, per record: 1,035 results each and none changed. The corpus holds none of the task's forms, and
  `tools/ioguard.py check` gave the right answer for all six rows on the change and the wrong one on HEAD.
- `live-skill` passed on the CLI 2.1.283: `Get-ChildItem` sent to Bash still met `DIALECT_MISMATCH`, beside
  `SHELL_WRITE`, `MSYS_PATH`, `POWERSHELL_TRAP` and `TRAILING_BACKSLASH_QUOTE`.
- Docs: `docs/design/architecture.md` (the package tree, `shell.scan`).
- Checked on Windows on 2026-09-29.
