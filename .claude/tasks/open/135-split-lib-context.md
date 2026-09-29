---
title: Split lib.context into the modules it holds
stage: I
area: runtime
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: lib.context split by operation"
---

## Why

Low. `plugins/io-guard/scripts/ioguard/lib/context.py` is 550 lines and holds six kinds of thing, where the
`engineering` skill asks for a module named for its operation, so a helper has a findable home.

- Lines 46-82: the `GitPort`, `FsPort` and `Clock` protocols.
- Lines 85-150: `Probe`, `Snapshot` and `ShellSnapshot`, the values checks keep between hooks.
- Lines 158-273: `SessionState`, with its file-shared warned set through `session_file` and
  `first_in_file` at lines 383-398.
- Lines 276-358: `SystemClock` and `LiveFs`, the live ports.
- Lines 409-444: where io-guard's and Claude Code's folders are, `claude_folder`, `home_folder`,
  `memory_file` and `project_root`.
- Lines 447-491: the config layering, `config_layers`, `trusted`, `config_stamp` and `load_probe`, which
  read `lib.config` and `lib.trust`.
- Lines 494-550: `Context` itself.

A search for "where is Claude Code's folder" lands on `context.py` only because task 122 moved two copies
into it, and `lib/rules.py:33`, `lib/runs.py:11` and `lib/probing.py:13` import `context` for one name each.
Every import of `context` pulls in `config`, `git`, `locks`, `telemetry` and `trust`, so `probing` imports
the whole config loader to type a `ToolVersion`.

## What to build

- `lib/folders.py`: `claude_folder`, `home_folder`, `memory_file`, `project_root`, `session_file`.
- `lib/ports.py`: the three protocols, `LiveFs`, `SystemClock`, `newlines`, `read_or_none`.
- `lib/session.py`: `SessionState`, `first_in_file`, and the two snapshot types it keeps.
- `lib/probe.py`, or `lib/probing.py`: `Probe`, `ToolVersion`, `load_probe`.
- `lib/config.py` takes `config_layers`, `trusted` and `config_stamp`, since they are the layering.
- `lib/context.py` keeps `Context` and imports the rest.
- Every importer names the new module, and `docs/design/architecture.md` section 1 and section 4 list them.

## Where

`lib/context.py` and the modules above, every module that imports from `context`, `tests/lib/test_context.py`,
`docs/design/architecture.md`.

## Done when

- `lib/context.py` is under 120 lines and holds `Context` alone.
- The suite passes, `tests/test_layout.py` included.
