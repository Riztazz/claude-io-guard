---
title: Stop shell.lint refusing valid commands, and check python -c behind its flags
stage: I
area: checks
created: 2026-09-29
status: open
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
