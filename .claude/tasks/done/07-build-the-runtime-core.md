---
title: "Build the runtime core: events, context, results, config, the registry and the pipeline"
stage: A
area: runtime
created: 2026-09-27
status: open
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [03, 05]
findings: []
platforms: [windows, macos]
commit: "feat: the check pipeline, its registry, results, config and telemetry"
---

## Why

Every check in the later stages needs the same plumbing: an event, a context, a decision, one failure shape, the
config and the telemetry. Built once in `lib` and `checks/`, each check stays one small class that a test can run
without a harness.

## What to build

`docs/design/architecture.md`, sections 2 to 5 and 9, is the design, and every signature there is a contract.

- **`lib/events.py`, `lib/context.py`, `lib/decisions.py`:** `Event` with both constructors, the ports, `Probe`,
  `SessionState`, `Context.live` and `Context.fake`, `Verdict`, `Rewrite`, `Decision` and `compose`.
- **`lib/results.py`:** `CodeSpec`, `CODES`, `Code`, `Result`, `Fix` and `render`. Settle the final code list from
  the draft in `context.md` and the additions in the architecture, and generate the enum from `CODES`.
- **`lib/config.py`:** the four layers, `validate` with the nearest known key, the scope rule that a project file
  never widens, and every policy value as a key with its default in code (D16). That includes
  `pipeline.soft_ms` 300, `pipeline.hard_ms` 2,000, and `transport.rewrite_mode` with D12's defaults.
- **`lib/telemetry.py`:** one JSONL file per session under `events/<YYYY-MM>/` (D13), the schema in section 9, and
  the trace context.
- **`checks/base.py`, `checks/registry.py`, `checks/pipeline.py`:** `Check`, `CheckMeta`, `Cost`, `Registry` with
  its validation at registration, an empty `default_registry()`, and `Pipeline` with its eight steps: select,
  order, run and chain, resolve conflicts, stop on a refusal, hold the budget, fail open (D7), merge.

## Where

`plugins/io-guard/scripts/ioguard/lib/`, `plugins/io-guard/scripts/ioguard/checks/`, `tests/lib/`, `tests/checks/`.

## Done when

- The pipeline tests pass in CI on both platforms: ordering, composition, a conflict dropped with
  `REWRITE_CONFLICT`, a refusal that stops the run, both budget limits, and the fixed point on a fake rewrite check.
- A deliberately broken check logs `GUARD_ERROR` once, and the pipeline goes on to the next check.
- `tests/test_meta.py` fails for a code in `CODES` that no test produces, and for a registered check without a test
  module.
- A config file with an unknown key is dropped whole, and the message names the file, the key and the nearest
  known key.

## Blocked on

**CI on the lead's next push.** Every Done-when line passes on Windows, below. The first line asks for CI on both
platforms, and this commit has not been pushed yet.

## What changed so far

- **`plugins/io-guard/scripts/ioguard/`**, the package, with `PLUGIN_VERSION`, `CONFIG_SCHEMA`, `CHECK_API` and
  `TELEMETRY_SCHEMA` in `__init__.py`.
- **`lib/`:**
  - `events.py`: `Event` with `from_hook_json`, `from_fields` and `with_tool_input`. `tool_input` is read-only,
    and an unreadable event raises `EventError`.
  - `context.py`: the ports as protocols, `Probe`, `SessionState` with its lock and `first_time`, and
    `Context.live` and `Context.fake`. `fakes.py` holds the fake file system, git and clock.
  - `decisions.py`: `Verdict`, `Rewrite`, `Decision`, `compose`. A rewrite that changes a field it did not
    declare raises `RewriteError`.
  - `results.py`: `CodeSpec`, `CODES`, `Code`, `Fix`, `Result` with `to_json` and `render`.
  - `config.py`: the four layers, `validate` with the nearest known key, the scope rule, and the keys the
    runtime reads: `schema`, `pipeline.soft_ms` 300, `pipeline.hard_ms` 2,000, `transport.rewrite_mode.*` with
    D12's defaults, and `telemetry.*`.
  - `telemetry.py`: one JSONL file per session under `events/<YYYY-MM>/`, the section 9 schema, and
    `trace_from`.
  - `bytesio.py`, `proc.py` and `git.py` for the live ports, and minimal `platform.py` and `paths.py`, which
    tasks 10 and 14 extend. `LiveFs.holders` raises until task 19 builds `lib.locks`.
- **`checks/`:** `base.py` with `Check`, `CheckMeta` and `Cost`, `registry.py` with its validation and the
  empty `CHECKS`, and `pipeline.py` with the eight steps. The pipeline also enforces `CheckMeta.writes`.
- **Three decisions, recorded in `docs/design/architecture.md`:**
  - `CODES` holds only the codes something produces, today the pipeline's `GUARD_ERROR`, `REWRITE_CONFLICT`
    and `BUDGET_EXCEEDED`. The task asked for the final list there and for a meta test that fails on a code no
    test produces, and those cannot both hold before the checks exist. The settled list is a table in section
    2, with the task that adds each code.
  - `ConfigKey` lives in `lib.config`, because `lib` validates it and cannot import `checks`.
  - A config key enters with the code that reads it, so `verify`, `write_roots.extra` and the others arrive
    with their checks.
- **The security issue, handled at the lead's request:** a project's `io-guard.json` could have added `verify`
  commands, which io-guard would run on every write. D24 in `context.md` now says a project file never makes
  io-guard run a program. Sections 5 and 12 of the design say so, task 18 carries it as a build step and a
  Done-when test, and task 30 moves each project's verify command into the lead's own config. Task 25 gained a
  note on `noise_patterns`, the project-set regexes that could stall a call.
- **Tests, 159 in all, up from 36:** `tests/lib/` for every `lib` module, `tests/checks/test_registry.py` and
  `tests/checks/test_pipeline.py`, `tests/test_layout.py` for the import rule, and `tests/support/checks.py` and
  `tests/support/meta.py`. `tests/test_meta.py` gained the code and check scans, each with a test proving it
  reports the case it exists for.
- **A bug found while writing:** `parse_ranges` read a hunk with no count through `re.findall`, which gives an
  empty string for a group that did not match. The first draft compared with `None`, and a test now covers the
  one-line hunk.
- **Docs:** `docs/design/architecture.md` sections 2 to 5 and 12, `context.md` (D24 and the codes heading),
  `.claude/tasks/README.md` and the `io-guard-dev` skill (D1 to D24), `CLAUDE.md`, and tasks 18, 25 and 30.
  The drawing needed nothing.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27: `python tests/run_all.py` ran 159 tests, all
passing. The four Done-when cases pass as tests: the pipeline cases in `test_pipeline.py` (ordering,
composition, `REWRITE_CONFLICT`, a refusal, both budget limits, the fixed point), `GUARD_ERROR` once per
session with the run going on, the two meta scans, and the dropped config file in `test_config.py`.

Not checked: CI on either platform (Blocked on).
