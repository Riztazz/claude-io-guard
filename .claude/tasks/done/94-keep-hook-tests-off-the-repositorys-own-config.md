---
title: Keep the hook tests off this repository's own .claude/io-guard.json
stage: I
area: tests
created: 2026-09-29
status: done
depends-on: [84]
findings: []
platforms: [windows, macos]
commit: "test: the hook tests run in a project of their own"
---

## Why

CI failed on 2026-09-29, macOS runner, 958 tests, 2 failures, 9 skipped:

```
FAIL: test_a_broken_check_answers_the_other_checks_and_warns_the_user (tests.hooks.test_hook_py.EveryEventGetsItsAnswer...)
AssertionError: False is not true : the user hears of the broken check

FAIL: test_with_nothing_to_say_every_recorded_event_answers_an_empty_object (...) (event='PreToolUse')
AssertionError: {'systemMessage': "This project's .claude/[185 chars]0)."} != {}
- {'systemMessage': "This project's .claude/io-guard.json changes 2 of your io-guard settings here:
  checks.shell.lint.build_commands a list of 15 (yours a list of 23); checks.verify.write.ascii_only a list of
  21 (yours a list of 0)."}
```

`tests/hooks/test_hook_py.py` runs `hook.py` with this repository as the project, so it loads the committed
`.claude/io-guard.json`. Task 84's message naming a project's changes now comes first in `systemMessage`, so
the empty answer is not empty and the `GUARD_ERROR` line is no longer at the start. The same suite passes on
Windows here, and why it does is part of this task: the lead's uncommitted `.claude/io-guard.json` and the
runner's home folder both differ.

## What to build

- The hook tests run with a temporary project folder as the event's `cwd` and `CLAUDE_PROJECT_DIR`, or with
  a copy of the event pointing there, so no repository file reaches them.
- Search the other tests that start `hook.py` or the server with `cwd=REPO` for the same leak.

## Done when

- `python tests/run_all.py` passes with this repository's committed `.claude/io-guard.json` in place, and CI
  is green on both runners.

## What changed

- The cause: the recorded events' `cwd` is `C:\project`. Windows reads it as absolute, a folder that does not
  exist, so `project_root` stops there and loads no project file. macOS reads it as a relative path, and
  `hook.py` ran with the repository as its working folder, so `project_root` climbed to this repository and
  loaded its `.claude/io-guard.json`, whose changes task 84's message now names.
- `tests/hooks/test_hook_py.py`: `hook` runs `hook.py` with the test's empty io-guard folder as its working
  folder. The other tests that start `hook.py`, in `tests/hooks/test_launcher.py`, give absolute temporary
  folders as `cwd`, so they need nothing.
- Docs: none states this.

Evidence:

- Reproduced on Windows: the recorded PreToolUse with `cwd` set to the relative `project`, run from the
  repository, answered `{"systemMessage": "This project's .claude/io-guard.json changes 5 of your io-guard
  settings here: ..."}`, and run from an empty folder answered `{}`.
- `python tests/run_all.py`: 961 tests, OK. CI on the macOS runner is to confirm after the push.

Checked on Windows 10 on 2026-09-29. Not checked: the macOS runner itself, until CI runs.
