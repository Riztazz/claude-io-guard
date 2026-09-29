---
title: Keep checking under a permission mode io-guard does not know
stage: I
area: hooks
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: a new permission mode keeps io-guard's checks on"
---

## Why

The code review of 2026-09-29, slice A item 16. `lib/events.py` raises `EventError` for a `permission_mode`
it does not know, and `hooks/entry.py` `run_event` then answers `{}` for every call. A Claude Code release
that adds a mode would turn every check off, the asks included, with one debug line and no message to the user.

## What to build

- An unknown mode is kept as its text. The checks treat it as `default` for the rewrite mode, the one that
  asks, and io-guard tells the user once a session that it met a mode it does not know.
- A test with a made-up mode: the checks run, and the message goes out once.

## Where

`lib/events.py`, `hooks/entry.py`, the rewrite-mode lookup in `checks/`.

## Done when

- A hook event with an unknown mode gets the same checks as `default`, and the user is told once.
