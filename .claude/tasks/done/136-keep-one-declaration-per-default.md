---
title: Keep one declaration for each default and each command list
stage: I
area: runtime
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: one declaration for each default"
---

## Why

Low. Three values have a declaration in code beside their declaration as a config default, and two lists
of build commands overlap without reading each other. D16 says every policy value is a config key with its
default in code, and the engineering skill says parallel tables are generated from one declaration.

- `plugins/io-guard/scripts/ioguard/checks/pipeline.py:29-30`: `soft_ms: int = 300` and
  `hard_ms: int = 2000` in `Budget`, and `plugins/io-guard/scripts/ioguard/lib/config.py:131-133`:
  `"pipeline.soft_ms": ConfigKey(int, 300, ...)` and `"pipeline.hard_ms": ConfigKey(int, 2000, ...)`.
  `tests/checks/test_pipeline.py:22` builds `Budget()` bare, so the dataclass defaults are the ones tested,
  and a change to the config default leaves them behind.
- `plugins/io-guard/scripts/ioguard/mcp/server.py:36`: `WORKERS = 4`, the default of `Server(...)`, and
  `lib/config.py:165`: `"io.server.workers": ConfigKey(int, 4, ...)`. `server.main` at line 221 passes the
  config's value, so `WORKERS` serves only a caller that leaves it out.
- `plugins/io-guard/scripts/ioguard/checks/lint.py:48-51`, `BUILD_COMMANDS`, and
  `plugins/io-guard/scripts/ioguard/checks/command_results.py:57-59`, `BUILDS` and `RUNS`, both name `make`,
  `cmake --build`, `ninja`, `msbuild`, `dotnet build`, `cargo build`, `go build`, `gradle`, `gradlew`, `mvn`
  and `tsc`. `shell.lint` uses its list for a pipe that hides an exit code, and `shell.results` for a build
  that failed. A build tool added to one list is missed by the other check.

## What to build

- `Budget` takes its defaults from the `ConfigKey` defaults, or has none and every caller builds it from a
  config, `tests/checks/test_pipeline.py` included.
- `Server` reads its worker count from the config key's default when none is given, or takes no default.
- One list of build commands, in a `lib` module or in `config.GLOBAL_KEYS`, which `shell.lint` extends with
  its test runners and `shell.results` reads as `builds`. Each check's key keeps its own doc and its
  project override.

## Where

`checks/pipeline.py`, `mcp/server.py`, `checks/lint.py`, `checks/command_results.py`, `lib/config.py`,
`tests/checks/test_pipeline.py`, `docs/settings.md` if a key's default text changes.

## Done when

- A grep for `300` and `2000` under `plugins/io-guard/scripts` finds each once, in `lib/config.py`.
- The suite passes.

## What changed

Validated on 2026-09-30 before building: all three were there, at `checks/pipeline.py:29-30`,
`mcp/server.py:37` and `lib/config.py:133,135,167`, and the two lists at `checks/lint.py:49-52` and
`checks/command_results.py:60-61`. The done-when's grep for `300` and `2000` finds other facts with the same
numbers: shell.results' `line_chars`, `cli/corpus.py`'s `RESULT_CHARS`, `mcp/tools_format.py`'s
`MESSAGE_CHARS`, verify.command's `output_chars`, a replay sample's width, and `cli/measure.py`'s D16 target
of a hook p95 within 300 ms, which is the goal task 31 measures, not the pipeline's budget. So the test below
checks the budget's declarations by their shape instead.

- `pipeline.Budget` takes its two defaults from `GLOBAL_KEYS["pipeline.soft_ms"]` and `["pipeline.hard_ms"]`,
  so a bare `Budget()` in a test is the configured budget.
- `mcp.server.Server` takes its worker count from `GLOBAL_KEYS["io.server.workers"]`, and `WORKERS` is gone.
- `lib/shell.py` holds `BUILDS`, the one list of build commands, beside `matching`, which reads such lists.
  `shell.results` gives a copy of it as its `builds` default, and `shell.lint` builds `build_commands` from it
  and its own `TEST_RUNNERS`. Each key keeps its own doc and its project override. shell.lint's default lists
  the same 23 commands as before, the builds first.

`EachDefaultIsTheConfigsOwn` in `tests/test_declarations.py`, 2 tests, came first: a bare Budget equals the
configured one, a Server's default worker count is the key's, no number stands beside a key, every build
shell.results knows shell.lint knows, and the build list is spelled once. It failed on the three numbers and on
the second list.

Docs: none. `docs/settings.md` names `make`, `npm test` and `pytest` as examples, all still in the defaults,
and `python tools/skill.py --check` passes.

Evidence, on Windows on 2026-09-30:

- The suite: 1,097 tests, 1,095 before, OK with 2 skipped.
- Live, Claude Code 2.1.283, from this checkout: `live-empty`, `live-server` and `live-server-modern` (the
  server and its workers), `live-pipe-once` (shell.lint's build commands) and `live-results` (shell.results)
  pass.
