---
title: Add the telemetry stats to the dashboard page
stage: H
area: mcp
created: 2026-09-29
status: open
depends-on: [31, 33]
findings: []
platforms: [windows, macos]
commit: "feat: the dashboard shows what io-guard fixed, warned about and refused"
---

## Why

Task 33 builds the dashboard page with the settings first, as the lead chose on 2026-09-29. The stats wait for
task 31's measurement (D20), so the page shows numbers the measurement has already checked.

## What to build

- A stats tab on the page from task 33: fixes, warnings and refusals by code, check, project and platform over
  time, the latency percentiles, and the recent events, where clicking one shows its evidence and fix.
- The page reads the same data as `tools/report.py`, through `io.dashboard` with `scope: "details"`, which the
  page calls and the model does not. A tool result carries counts and percentiles only.
- `tools/report.py --html <file>` renders the same page into a standalone file.
- The snapshots, with a restore button that calls `io.restore` and asks the user first.

## Where

`plugins/io-guard/ui/dashboard.html`, `plugins/io-guard/scripts/ioguard/mcp/tools_dashboard.py`,
`plugins/io-guard/scripts/ioguard/cli/report.py`.

## Done when

- The stats tab shows a week of real telemetry in the browser pane, and `tools/report.py --html` writes the
  same page as a file.
