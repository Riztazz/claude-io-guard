---
title: Delete the code nothing reads, and the copies of one helper
stage: I
area: runtime
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: delete the code nothing reads"
---

## Why

The code review of 2026-09-29: slice A item 23 and slice B item 17.

- `checks/pipeline.py` `Pipeline.order` only passes its argument through.
- `lib/config.py`'s merge appends a list whose key ends in `extra`, and no key does. The module's docstring
  still describes it.
- Found on 2026-09-29 during task 98: Claude Code's folder, `CLAUDE_CONFIG_DIR` or `~/.claude`, is worked
  out three times: `lib/context.py` `claude_folder`, `checks/heartbeat.py` (line 80) and `lib/rules.py`
  `settings_files` (line 96).

## What to build

- Delete `order` and the `extra` branch, and fix the docstring. The script reads moved to task 103.
- `heartbeat.py` and `rules.py` call `claude_folder`, and their copies go. The heartbeat's copy reads the home
  folder from the environment it is given, `USERPROFILE` or `HOME`, where `claude_folder` calls
  `Path.home()`. The one kept reads the given environment, so a test sets it, and tasks 98 and 99's callers
  pass `ctx.env` already.

## Where

`checks/pipeline.py`, `lib/config.py`, `checks/heartbeat.py`, `lib/rules.py`.

## Done when

- The tests pass, and a grep finds no caller of what was deleted.
