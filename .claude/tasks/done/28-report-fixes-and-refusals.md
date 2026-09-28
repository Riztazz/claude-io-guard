---
title: Report what the guard fixed and refused
stage: G
area: runtime
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
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

## What changed

- **`ioguard/cli/report.py`**, run as `python tools/report.py [--data FOLDER ...] [--days 7]` or the cli's
  `report` command. It merges every session file of the days asked, from each installed io-guard's data
  folder unless `--data` names one, and leaves out `io-guard-inline`, the probes' `--plugin-dir` folder. One
  screen holds the calls by event, tool, project and platform, the codes split into fixed, warned and refused,
  p50, p90, p99 and max of a hook call, an io tool call and one tool use summed across its `trace_id`, the
  command shapes behind refusals, such as `sed -i`, and each kind of `GUARD_ERROR` with its count. Every line
  stops at 110 characters, and a torn line from a crash is counted as unreadable and skipped.
- **`Report.counts()`** holds what a tool result may carry: counts and percentiles, with no command, path,
  project or error text. The dashboard (task 33) reads it.
- **No `/io-guard:report` command.** A command's output lands in the model's context, and the report holds
  command shapes and error hashes. The counts-only view arrives in the app with the dashboard.
- `cli/main.py`'s replay branch names its result `replayed`, so the new `report` module is not shadowed.
- Tests: 690 before, 697 after, all passing, from `python tests/run_all.py`. `tests/cli/test_report.py`
  generates a week of 84 sessions across a month boundary, 3,864 lines, and checks the merge, the period, the
  one-screen fit at 30 lines, a torn line, command shapes, `counts()` and the data folders. CI runs it on
  Windows and macOS.
- **Evidence.** The only real telemetry on this machine is the probes', because io-guard is not installed in
  the desktop app: 88 sessions and 915 lines over 2026-09-27 and 2026-09-28 gave 30 lines, none wider than 110,
  with `GUARD_ERROR` from the test checks, `SHELL_WRITE` 7 and `POWERSHELL_TRAP` 7 refused, and a hook call at
  p50 3.2 ms. A real week waits for the install in task 30.
- **Docs:** `docs/design/architecture.md` sections 1 and 9, the README's "Work on it", and `CLAUDE.md`'s
  "Running things". The drawing names no report.
- Checked on Windows on 2026-09-28. macOS runs the tests in CI only.
