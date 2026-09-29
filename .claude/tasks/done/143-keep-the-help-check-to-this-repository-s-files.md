---
title: Keep the help check to the files this repository writes
stage: I
area: infra
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: the help check counts only this repository's own files"
---

## Why

Found on 2026-09-29 in an hour of back-to-back suite runs on Windows. Run 048 of the second loop failed with
nothing in this repository changing:

```
FAIL: test_every_script_prints_its_usage_for_help_and_does_nothing_else (tests.test_meta.EveryScriptAnswersHelp...)
AssertionError: Lists differ: ['.claude/tools/shared/__pycache__/record_window.cpython-314.pyc'] != []
```

`tests/test_meta.py` `stats()` lists every file `git ls-files --cached --others` gives, ignored ones
included, before and after running each script with `--help`, and fails on any that changed. That list takes
in `.claude/tools/shared/`, a link into the lead's kit, which another project's session writes to whenever it
runs one of the kit's scripts: here the `.pyc` of `record_window.py`. The test runs its scripts with
`PYTHONDONTWRITEBYTECODE=1`, so the file was not the test's. The same check failed in the first loop on
`workbench/io-guard-home/sessions/<id>.alive`, a probe session's heartbeat written while it ran.

## What to build

- `stats()` leaves out the kit's linked folders (`.claude/tools/shared`, `.claude/rules/shared`, the linked
  skills), `workbench/`, and every `__pycache__` folder. None is a place a `--help` of this repository's
  scripts would write, and each is written by other processes.
- A test: a file written under a left-out folder during the check does not fail it, and one written under
  `plugins/` still does.

## Where

`tests/test_meta.py` (`stats`, `EveryScriptAnswersHelp`).

## Done when

- An hour of back-to-back suite runs with other sessions active shows no failure of this check.

## What changed

- `tests/test_meta.py`: `watched(name)` leaves out any path with a `__pycache__` part, anything under
  `workbench/`, and any path whose real location is outside the checkout, which covers every link into the
  kit without naming them. `stats()` counts only watched files. A file this repository's scripts could write,
  under `plugins/`, `tools/` or `reports/`, is still watched.
- Tests, failing first on the missing helper: three paths other processes write are left out and three of
  this repository's are watched; `.claude/tools/shared/record_window.py`, behind the kit's link, is left out,
  a case that skips where the link does not exist, as on CI. It ran here. The suite of 1,061 passes on
  Windows, 2 skipped.
- Not checked yet: the done-when hour. The second loop was already running when this landed, so its later
  runs use the new check, and its count is the first evidence.
- Docs: none describe the help check's file scan.
- Checked on Windows on 2026-09-29.
