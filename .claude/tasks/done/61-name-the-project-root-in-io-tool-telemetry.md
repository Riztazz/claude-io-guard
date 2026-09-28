---
title: Name the project root in an io tool's telemetry, as the hooks do
stage: I
area: telemetry
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [57]
findings: []
platforms: [windows, macos]
commit: "fix: an io tool's telemetry names the project, not the working folder"
---

## Why

`python tools/report.py --days 1` on 2026-09-28 listed `ioguard` with 170 lines and `open` with 153 among the
projects. All 356 lines of those two names are hook lines, from 12:12 to 13:11 UTC, before task 57 installed.
Since task 57 a hook's line names `(ctx.project or event.cwd).name`, the project root (`checks/pipeline.py`,
`record`), so those names stop on their own.

An io tool's line still named `call.cwd.name` (`mcp/toolspec.py`, the telemetry line of a call). The server's
`call.cwd` is `CLAUDE_PROJECT_DIR`, the folder the session started in. A session started in a subfolder of a
project would put its hook lines under the root's name and its io tool lines under the subfolder's.

## What to build

- `mcp/toolspec.py` names the project as the pipeline does, through one function both call.
- A test: an io tool call from a subfolder of a project records the project root's name.

## Where

`plugins/io-guard/scripts/ioguard/mcp/toolspec.py`, `plugins/io-guard/scripts/ioguard/checks/pipeline.py`,
`tests/mcp/`.

## Done when

- A session's hook lines and io tool lines carry the same project name from any subfolder.

## What changed

- `lib/context.py`: `Context.project_name(cwd)`, the root's folder name, else the working folder's.
- `checks/pipeline.py` and `mcp/toolspec.py` both call it. The io tool line took `call.cwd.name` before.
- Tests: `tests/mcp/test_toolspec.py` (1: an `io.read` from `<root>/sub` records the root's name).
- Docs: none needed. `docs/design/architecture.md` already says telemetry names the project by the root.

Evidence:

- `python tests/run_all.py` from Git Bash ran 859 tests, all passing, up from 858.
- Not run live: the telemetry line holds no text a session shows, and the installed plugin gets the change only
  after the next plugin update.
