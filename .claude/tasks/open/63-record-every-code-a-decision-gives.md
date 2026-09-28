---
title: Record every code a decision gives, not only its first
stage: I
area: telemetry
created: 2026-09-28
status: open
depends-on: [28]
findings: []
platforms: [windows, macos]
commit: "fix: telemetry counts every code a decision gives"
---

## Why

On 2026-09-28 this repository's session got `TOUCHED_BY_SHELL` and `SHELL_WRITE` together, from one
`shell.touched` decision after a Bash call. `python tools/report.py --days 1` then listed `TOUCHED_BY_SHELL` 29
times and no `SHELL_WRITE` at all.

`checks/pipeline.py`, where a decision is recorded, writes one telemetry line per decision, with
`decision.results[0]`'s code alone. Every later result is lost. That hides `SHELL_WRITE` and the drift codes
`shell.touched` adds after `TOUCHED_BY_SHELL`, and any second result of any check. The end-of-task report rule in
`.claude/rules/this-repo.md` reads these counts, so a code that fires second is never reviewed.

## What to build

- One line per result, each with its own code and severity, the decision's latency on the first line only, so the
  report's timings don't double. Or one line with every code in a list. Pick one, and keep `tools/report.py`
  reading the lines already written, since `TELEMETRY_SCHEMA` is read back in full.
- A test: a decision with two results records both codes, and the report counts both.
- `docs/design/architecture.md`, section 9, says which.

## Where

`plugins/io-guard/scripts/ioguard/checks/pipeline.py`, `plugins/io-guard/scripts/ioguard/cli/report.py`,
`tests/checks/test_pipeline.py`, `tests/cli/test_report.py`.

## Done when

- A `SHELL_WRITE` given second in a decision shows in the report's count.
