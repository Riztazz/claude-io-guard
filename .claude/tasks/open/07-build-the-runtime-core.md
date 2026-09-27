---
title: "Build the runtime core: events, context, results, config, the registry and the pipeline"
stage: A
area: runtime
created: 2026-09-27
status: open
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
