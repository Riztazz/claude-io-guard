---
title: Keep deeply nested input from turning io-guard's checks off
stage: I
area: lib
created: 2026-09-29
status: open
depends-on: [97]
findings: []
platforms: [windows, macos]
commit: "fix: deeply nested input no longer turns io-guard's checks off"
---

## Why

The code review of 2026-09-29: slice A item 3, slice B items 5 and 15.

- `lib/shell.py`'s scanner recurses once per `$(`. `"$(" * 1000 + "true" + ")" * 1000 + "; sed -i s/a/b/
  README.md"` raises `RecursionError`, and `shell.writes`, `transport.body`, `shell.lint` and `win.paths` fail
  open. At depth 600 the same command is refused with `SHELL_WRITE`. Rerun on Windows on 2026-09-29: depth 600
  gave DENY, depth 1000 OBSERVE. `commit.policy` uses the same scan, so a 2 KB prefix turns the commit policy
  off too.
- `json.loads` of a project's `.claude/io-guard.json` holding `[` 100,000 times raises `RecursionError`, and a
  5,000-digit integer a bare `ValueError`. Neither is caught in `lib/config.py`, so every hook in that project
  fails open with one `GUARD_ERROR` a session. `lib/rules.py` reads a project's `settings.json` the same way,
  with no size cap, and `io.run` then errors.

## What to build

- The scanner keeps a depth, and a string past a cap, 100 levels, is unread (task 97's rule): the checks that
  need its words ask or refuse, and none fails open.
- `config.load` and `rules.rules_in` catch `RecursionError` and `ValueError`, and report the file as broken the
  way a bad value is reported, naming the file. `settings.json` is read with the same 256 KB cap as the config.
- Tests for each.

## Where

`lib/shell.py`, `lib/config.py`, `lib/rules.py`, `lib/events.py` (`from_fields`, already fails open, check
it stays so).

## Done when

- The depth-1000 command is refused with `SHELL_WRITE`, and the two broken config files each give the config
  error message, not `GUARD_ERROR`.
