---
title: Report what the guard fixed and refused
stage: G
area: runtime
created: 2026-09-27
status: open
depends-on: [07]
findings: []
platforms: [windows, macos]
commit: "feat: a report of the guard's fixes and refusals by code and project"
---

## Why

Failure classes nobody has found yet will show up in the telemetry, as refusals, warnings and `GUARD_ERROR`s. A
weekly report makes them visible, so nobody has to hunt through transcripts again.

## What to build

`tools/report.py`, and a `/io-guard:report` command if commands fit the plugin. It merges the per-session files in
`${CLAUDE_PLUGIN_DATA}/events/<YYYY-MM>/` (D13) and prints:
- counts by code, severity, tool, project and platform
- latency percentiles
- the most common command shapes behind refusals
- every `GUARD_ERROR`
- what one tool use cost end to end, grouped by `trace_id`

Any tool result built from it returns counts and percentiles only, never command heads or paths, because a tool
result lands in the model's context.

## Where

`tools/report.py`, `ioguard/cli/`. Optionally `plugins/io-guard/commands/report.md`.

## Done when

- The report runs in CI on both platforms, on a generated week of telemetry.
- A week of real data fits on one screen.
