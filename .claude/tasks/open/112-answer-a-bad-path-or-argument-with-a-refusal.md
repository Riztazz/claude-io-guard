---
title: Answer a path or an argument the system rejects with a refusal, not GUARD_ERROR
stage: I
area: lib
created: 2026-09-29
status: open
depends-on: []
findings: [PTH-1]
platforms: [windows, macos]
commit: "fix: a path or argument the system rejects gets a refusal, not GUARD_ERROR"
---

## Why

The code review of 2026-09-29: slice C item 11 and slice B item 14. `lib/context.py` `LiveFs.stat` catches only
`FileNotFoundError`. On Windows a name holding `?`, `*`, `"`, `|` or a NUL, or one longer than 255 characters,
raises `OSError` WinError 123, and on macOS a path through a file raises `NotADirectoryError`. `io.read`,
`io.edit` and `write.location` then fail with `GUARD_ERROR`. `io.run` does the same for a NUL in argv, a `=`
in an environment key, and a lone surrogate in `code`.

## What to build

- `LiveFs.stat` answers `None` for any `OSError` that means the path cannot exist, and logs the reason.
- `io.run` checks its argv, env and code before it starts anything, and refuses a bad one with
  `INVALID_ARGUMENTS` naming the field.
- A test per input.

## Where

`lib/context.py`, `mcp/tools_run.py`.

## Done when

- Each input gets `PATH_NOT_FOUND` or `INVALID_ARGUMENTS`, never `GUARD_ERROR`.
