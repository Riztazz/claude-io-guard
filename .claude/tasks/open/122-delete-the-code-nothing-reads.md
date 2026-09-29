---
title: Delete the code nothing reads
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

- `checks/shell_writes.py` calls `script_files` twice for each Bash command, once in the refusal and once for
  `shell.touched.scripted`, so each script is read twice.
- `checks/pipeline.py` `Pipeline.order` only passes its argument through.
- `lib/config.py`'s merge appends a list whose key ends in `extra`, and no key does. The module's docstring
  still describes it.

## What to build

- Read the scripts once per call. Delete `order` and the `extra` branch, and fix the docstring.

## Where

`checks/shell_writes.py`, `checks/pipeline.py`, `lib/config.py`.

## Done when

- The tests pass, and a grep finds no caller of what was deleted.
