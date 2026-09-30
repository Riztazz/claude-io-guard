---
title: Read the environment, the disk and the project through the context
stage: I
area: runtime
created: 2026-09-29
status: done
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

## What changed

Validated on 2026-09-30 before building: all three claims held, at new places after task 129.
`interpreter` read `os.environ` at `lib/runs.py:27-34`, and `run.rules` now reaches it through `runs.judge`,
which already took the environment. `inside` had moved to `lib/trust.py:51`. The journal's project came from
`CLAUDE_PROJECT_DIR` at two sites, `checks/journal_write.py:47` and `mcp/in_place.py:187`.

One criterion was rewritten. `lib/proc.py:75`, `located`, falls back to the process's environment when a
caller passes none, by its contract. `lib.git` and the `lsof` lookup in `lib.locks` rely on it for the programs
io-guard starts for itself. So `os.environ` in `lib` and `checks` is now `Context.live` and that one documented
fallback. No check or tool reaches it with a context in hand.

- `runs.interpreter` and `runs.argv_of` take the environment, and `commit_policy`, `tools_run` and
  `runs.judge` pass `ctx.env`.
- `inside` takes the file system port and the platform. It reads each word from the project through
  `paths.normalise`, so `..` counts, and follows links through `fs.link_target`. `listed`, `inside` and
  `untrusted` moved from `lib/trust.py` to a new `lib/waiting.py`: `lib/context.py` imports `lib.trust` for the
  approval store, so `trust` could not import `FsPort`. `trust.py` keeps the store.
- `journal.record_write` names the written file's own project, `project_root(path.parent)`, by D31's rule, and
  takes no project from its two callers.

Tests first, each failing on the missing input:

- `test_an_interpreter_comes_from_the_environment_the_call_is_given` in `tests/lib/test_runs.py` puts a `node`
  on a temporary PATH.
- `tests/lib/test_waiting.py` gives a `FakeFs` a file inside the project, one reached by `..`, one through a
  link out of it, a missing one and a folder.
- `test_a_write_names_the_project_of_the_file_it_wrote` in `tests/lib/test_journal.py` writes in two
  repositories.

Docs: `docs/design/architecture.md` section 1 lists `waiting.py` and a slimmer `trust.py`, and the journal
section says whose project a line names.

Evidence, on Windows on 2026-09-30:

- The suite: 1,079 tests, 1,076 before, OK with 2 skipped.
- The greps: `checks` holds no `.is_file()` or `.resolve()`, and `os.environ` in `lib` and `checks` is the
  two places above.
- Live, Claude Code 2.1.283, from this checkout: `live-run-body` (a bash body's interpreter), `live-trust` (the
  prompt's inside words), `live-stage` (the journal) and `live-format` pass. The journal line `live-trust`'s
  Write left names that probe's own work folder as its project.

Seen along the way, for task 141: renaming the new, untracked `lib/held.py` to `lib/waiting.py` with `mv`
drew TOUCHED_BY_SHELL "This command created lib/waiting.py. Delete any new file the task does not need", and
SHELL_WRITE's scratch script warning. That is task 141's case, live, on 2026-09-30.
