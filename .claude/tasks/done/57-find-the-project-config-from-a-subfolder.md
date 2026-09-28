---
title: Find the project's config when the session works in a subfolder
stage: I
area: runtime
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
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
- A project's layers govern the project's own files. On 2026-09-28 an Edit of Claude Code's own
  `~/.claude/projects/<project>/memory/MEMORY.md` from this repository's session got `NON_ASCII_ADDED`, from
  this repository's `ascii_only`, for the em dash that file's own format uses. A file outside the project root
  takes the user's layer alone.
- Tests: a session in a subfolder of a project gets the project's layers, and one outside any project gets none.

## Where

`plugins/io-guard/scripts/ioguard/hooks/entry.py`, `lib/context.py`, `checks/pipeline.py`, `tests/hooks/`.

## Done when

- A Write of a non-ASCII `.py` line from `plugins/io-guard/scripts/ioguard` as the working folder gets
  `NON_ASCII_ADDED`, as it does from the repository root.

## What changed

- `lib/context.py`: `project_root(cwd)`, and `Context.project` and `Context.outside`, the config with the
  project's layers left out. `Context.for_file(path)` gives a call on a file outside the root that config.
- `hooks/entry.py`: `LiveContexts` keys each Context by session and project root, and loads the root's
  layers. `run_event` runs each call with `ctx.for_file(event.file_path)`, and names the config message's
  project by the root. The io tools reach the same Contexts through `hooks.bridge`, so they get the root too.
- `checks/pipeline.py`: telemetry's `project` is the root's name.
- Decision D31 in `context.md`: the walk up from `cwd`, not `CLAUDE_PROJECT_DIR`, with the reason.
- Tests: `tests/hooks/test_entry.py` (a subfolder gets the project's `ascii_only`, a file outside gets none)
  and `tests/lib/test_context.py` (the nearest config or repository ends the walk).
- `tools/probes/run_probe.py`: `live-subfolder-config`.
- Docs: `docs/design/architecture.md` (the config layers), `README.md` (Configure it), `docs/live-checks.md`,
  `docs/compat.md`, `.claude/tasks/context.md`.

Evidence:

- `python tests/run_all.py` ran 849 tests, all passing, up from 847.
- `live-subfolder-config` passed on 2.1.281 and 2.1.283, and again on 2.1.283 after its prompt source went
  ASCII: after `cd sub`, a Write of `name = "café"` to `sub/x.py` got `NON_ASCII_ADDED` from the root's
  `.claude/io-guard.json`. Before the change the config was looked for in `sub/.claude/` and not found.
- Not built: an io tool's call on a file outside the project still runs with the project's config. Only the
  hooks take `for_file`.
- The done-when above runs in this repository's desktop session once the plugin is updated.
- Checked on Windows on 2026-09-28.
