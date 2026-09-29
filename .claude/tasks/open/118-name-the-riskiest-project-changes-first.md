---
title: Name the project changes that matter most first
stage: I
area: lib
created: 2026-09-29
status: open
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
