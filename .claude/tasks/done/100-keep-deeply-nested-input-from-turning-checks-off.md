---
title: Keep deeply nested input from turning io-guard's checks off
stage: I
area: lib
created: 2026-09-29
status: done
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

## What changed

- `lib/shell.py`: `Scanner.substitution` enters each `$(` one level deeper, and past `MAX_NESTING` (100)
  stops the scan and sets `Scan.too_deep`. The scanner uses at most three stack frames a level, so it never
  meets Python's recursion limit. The text after the stop keeps the plain state, so every check still reads
  its words as commands.
- `checks/lint.py` and `lib/results.py`: a new code, `COMMAND_TOO_DEEP`, refused, which names the limit and
  tells the agent to put the inner commands in a script file. `rules.inner` treats a too-deep string as
  unread.
- `lib/config.py`: a file whose JSON is nested or numbered past what Python parses is dropped whole with the
  config message `The file is JSON io-guard cannot read: ...`, like a file that is not JSON.
  `lib/rules.py` `rules_in` and `lib/events.py` `from_fields` catch `RecursionError` too.
- The task asked for a 256 KB cap on a settings file. That was left out: a settings file dropped for its size
  loses its deny rules for `io.run`, while Claude Code still applies them to Bash, which is worse than
  reading it.
- Tests, each failing first: the scanner at 100, 600 and 1000 levels, bare and inside double quotes
  (`tests/lib/test_shell.py`), the depth-1000 `sed -i` refused with no check failing open
  (`tests/checks/test_lint.py`), a 100,000-bracket file and a 5,000-digit number in a project config
  (`tests/lib/test_config.py`) and in a settings file (`tests/lib/test_rules.py`). `tools/ioguard.py check`
  on the depth-1000 command answers `SHELL_WRITE`, where it let it through before. The suite is 981, all
  passing, on Windows.
- `plugins/io-guard/skills/io-guard/SKILL.md`: the code table, from `python tools/skill.py`.
- Docs: `docs/design/architecture.md` (the code table and `scan`).
- Checked on Windows on 2026-09-29. Not checked live: a command this deep is not one a session sends, and the
  unit tests run the real scanner. macOS waits in task 36.
