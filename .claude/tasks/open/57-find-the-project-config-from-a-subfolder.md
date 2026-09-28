---
title: Find the project's config when the session works in a subfolder
stage: I
area: runtime
created: 2026-09-28
status: open
depends-on: [07, 08]
findings: []
platforms: [windows, macos]
commit: "fix: load the project config from the project root, not the working folder"
---

## Why

A hook's `cwd` is the session's working folder, and a Bash `cd` moves it. io-guard builds a Context per `cwd`
(`hooks/entry.py`, `LiveContexts.get`, line 45) and reads the project layers from `<cwd>/.claude/io-guard.json`
and `<cwd>/.claude/io-guard.local.json` (`lib/context.py`, `Context.live`, lines 357 and 358). A missing file is
skipped with no word (`lib/config.py`, line 265).

This repository's session `7eeb509f-baa1-4e42-8aec-4f8fd98fdc99` on 2026-09-28 worked 180 events from
`plugins/io-guard/scripts/ioguard` and 176 from `.claude/tasks/open`, after a `cd` in a Bash call. For those 356
of its 1,072 events, the repository's `.claude/io-guard.json`, which lists the extensions kept ASCII, was not
loaded. The telemetry names each of those events after the subfolder, as projects `ioguard` and `open`
(`checks/pipeline.py`, line 89).

## What to build

- The project root is the nearest folder at or above `cwd` that holds `.claude/io-guard.json` or
  `.claude/io-guard.local.json`, else the repository root git names, else `cwd`. Decide between that and
  `CLAUDE_PROJECT_DIR` when the MCP server has it, and record which one in `context.md`.
- The Context, the config message and the telemetry's `project` all use that root.
- Tests: a session in a subfolder of a project gets the project's layers, and one outside any project gets none.

## Where

`plugins/io-guard/scripts/ioguard/hooks/entry.py`, `lib/context.py`, `checks/pipeline.py`, `tests/hooks/`.

## Done when

- A Write of a non-ASCII `.py` line from `plugins/io-guard/scripts/ioguard` as the working folder gets
  `NON_ASCII_ADDED`, as it does from the repository root.
