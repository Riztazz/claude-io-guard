---
title: Keep checking under a permission mode io-guard does not know
stage: I
area: hooks
created: 2026-09-29
status: done
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

## What changed

- `lib/events.py`: `PermissionMode.UNKNOWN` and `PermissionMode.named`, as `Tool.named` does for tools. A mode
  io-guard does not know reads as `UNKNOWN`, and its text stays in `Event.raw`. An empty mode reads as
  `default`, as before.
- `hooks/entry.py`: under `UNKNOWN` the answer takes `transport.rewrite_mode.default`, and
  `with_mode_message` adds `io-guard does not know the permission mode <name>, so it checks each call as in
  default mode and asks before it changes a command.` to the user message, once a session per mode.
- Tests, failing first: a Bash event with the mode `turbo` gets `ask` from the rewrite check twice, and the
  message once (`tests/hooks/test_entry.py`). `tests/hooks/test_hook_py.py`'s unreadable event is now an
  unknown `hook_event_name`, since an unknown mode is readable. The suite of 1,016 passes on Windows, 2
  skipped.
- `live-answers` passed on the CLI 2.1.283, so the known modes answer as before.
- Docs: `docs/design/architecture.md` (`PermissionMode`, the paragraph on unreadable events),
  `docs/settings.md` (the rewrite modes).
- Checked on Windows on 2026-09-29. No Claude Code release sends a mode io-guard does not know, so the
  message has not been seen live.
