---
title: Name the project changes that matter most first
stage: I
area: lib
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: the settings message names the changes that matter first"
---

## Why

The code review of 2026-09-29, slice B item 9. D43's once-a-session message names up to `CHANGES_NAMED`, 8, of
the project's changes to the user's settings, sorted by key. A project that changes eight
`checks.shell.results.*` keys and `pipeline.hard_ms: 0`, which skips every check, shows the eight and hides the
last as "and 1 more".

## What to build

- The message names first the keys that turn checks off or skip them: a check's `enabled` set false,
  `pipeline.*` and a budget lowered. Then the rest, by key.
- A test with the case above: `pipeline.hard_ms` is named.

## Where

`lib/config.py` (`LoadReport.user_message`).

## Done when

- The test passes, and `live-project-override` still shows the message.

## What changed

- `lib/config.py`: `LoadReport.user_message` sorts the changes with a check's `enabled` set false and every
  `pipeline.*` key first, then the rest by key. A check turned on is not moved up.
- Test, failing first: eight `checks.shell.results.*` changes, `pipeline.hard_ms` 0, `checks.shell.lint.enabled`
  false and `checks.shell.writes.enabled` true. The message names lint's `enabled` and `pipeline.hard_ms`
  first, then the results keys, and counts `3 more` (`tests/lib/test_config.py`). The suite of 1,034 passes on
  Windows, 2 skipped.
- `live-project-override` passed on the CLI 2.1.283.
- Docs: `docs/design/architecture.md` (the order the message names changes in).
- Checked on Windows on 2026-09-29.
