---
title: Read the environment, the disk and the project through the context
stage: I
area: runtime
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: lib and checks read the environment through the context"
---

## Why

Medium. The `io-guard-dev` skill says a check reads `ctx.env` and `ctx.fs`, never `os.environ` or the disk,
so a test sets both. Three places step around the context, and each is a place a test cannot reach.

- `plugins/io-guard/scripts/ioguard/lib/runs.py:26-33`, `interpreter`, searches the process environment:
  `proc.on_path("bash", os.environ)`, and the same for `pwsh`, `powershell` and `node`. Every caller holds a
  context with the environment in it: `checks/run_rules.py:38`, `checks/commit_policy.py:55` and
  `mcp/tools_run.py:209` all call `runs.argv_of(given, ctx.probe, ctx.platform)`. D39 says io-guard starts a
  program only from the environment's PATH, found by its own lookup, and here the environment is the
  process's, not the one the context carries, so a test of `run.rules` cannot put a `bash` on PATH.
- `plugins/io-guard/scripts/ioguard/checks/trust_ask.py:44-54`, `inside`, reads the disk itself:
  `path.is_file() and path.resolve().is_relative_to(project.resolve())`. The check's other reads go through
  `ctx.fs`, which has `stat` and `link_target` for this, and a test with a `FakeFs` cannot make a held command
  name a file inside the project.
- `plugins/io-guard/scripts/ioguard/checks/journal_write.py:35` names the journal line's project from
  `ctx.env.get("CLAUDE_PROJECT_DIR") or ""`, while telemetry names it through `ctx.project_name`
  (`lib/context.py:536-538`, called from `checks/pipeline.py:90` and `mcp/toolspec.py:277`). D31 says
  `CLAUDE_PROJECT_DIR` names only the folder the session started in, and one session works in several
  repositories, so a journal line written from a second repository carries the first one's folder.

## What to build

- `runs.interpreter` and `runs.argv_of` take the environment as an argument, and the three callers pass
  `ctx.env`.
- `trust_ask.inside` asks `ctx.fs` whether the word names a file, and compares through the resolved paths
  `lib.paths` gives, with the platform from the context.
- `journal_write.record_write` names the project as telemetry does, through `ctx.project_name`, or records
  the root `ctx.project` holds, and the journal's docstring says which.
- A test for each: `run.rules` with a fake environment whose PATH holds the interpreter, `trust_ask.inside`
  with a `FakeFs` file inside the project, and a journal line written from a folder outside the session's
  first project.

## Where

`lib/runs.py`, `checks/run_rules.py`, `checks/commit_policy.py`, `mcp/tools_run.py`, `checks/trust_ask.py`,
`checks/journal_write.py`, `lib/journal.py`, and their tests.

## Done when

- A grep of `plugins/io-guard/scripts/ioguard/lib` and `checks` for `os.environ` finds only `Context.live`.
- A grep of `checks` for `.is_file()` and `.resolve()` finds nothing.
- The suite passes.
