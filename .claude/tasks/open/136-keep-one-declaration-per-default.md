---
title: Keep one declaration for each default and each command list
stage: I
area: runtime
created: 2026-09-29
status: open
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
