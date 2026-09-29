---
title: Add the telemetry stats to the dashboard page
stage: H
area: mcp
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
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

## What changed

The lead asked for this task on 2026-09-29, before task 31's measurement, which waits until 2026-10-12.

- `lib/telemetry_summary.py`, new: the summing that `cli/report.py` did, moved and not copied. `Summary`,
  `files`, `summarise` with an optional project, `page_data` and `page`. A summary also keeps the counts per
  day and per check, and each code's last 20 lines. `page` is the one route to the page's data, for the page
  server and for the file alike.
- `cli/report.py` prints only. `static_page` writes the page with every project's stats inlined as
  `window.IOGUARD_STATIC`, and `cli/main.py` takes `report --html FILE`.
- `lib/results.py`: `meanings()`, each code's summary, fix, severity and layer, for the page's code detail.
- `mcp/dashboard_http.py` answers `GET /api/stats?days=&scope=`, behind the same token and `Host` check.
  `mcp/tools_dashboard.py` clamps the days to 1 to 90 and filters to the project unless `scope=all`.
- `ui/dashboard.html`: a Settings and Stats switch. Stats has 1, 7 and 30 days, this project or all, the totals,
  an SVG bar per day, the codes table with a detail per code, the checks, the time taken, and the projects. A
  file with inlined data shows the stats alone and sends no ping.
- **A change from the plan:** the page reads its stats from the page server, not from `io.dashboard` with
  `scope: "details"`. The details then never pass through a tool result, so no command head can reach the
  model's context.
- **Not built:** the snapshots and the restore button. A restore from the page would skip the permission
  prompt that `restore.ask` puts on `io.restore`. Task 71 holds it.
- Tests: `tests/cli/test_report.py` covers the file, whose data survives a command that holds `</script>`, and
  one project's lines over every day. `tests/mcp/test_tools_dashboard.py` covers this project's stats against
  all projects. `tests/cli/test_main.py` covers `report --html`.
- Docs: `.claude/tasks/context.md` (D34), `docs/design/architecture.md` (the tree, the dashboard page, the
  report), `README.md` (the Stats
  switch, `--html`), `CLAUDE.md` (the `--html` running line), and `docs/architecture.svg` (the dashboard box's
  hover text and flow D's last step). The drawing's script had not parsed since 47d8901, which wrote an
  unescaped apostrophe into flow C's text. That one character is fixed too.

Evidence:

- `python tests/run_all.py` ran 897 tests, all passing.
- The Stats view in the browser pane, served from this checkout over the lead's real telemetry, read only. This
  project showed 6 sessions, 4,147 lines, 5 bars and 12 codes. PIPE_HIDES_EXIT opened to its meaning and 20
  lines. All projects showed 35 sessions, 6,628 lines and the Projects section.
- `python tools/report.py --days 7 --html <file>` wrote 68,270 bytes, ASCII, whose inlined data read back as
  35 sessions, 6,824 lines, 8 days, 16 codes and 59 meanings.
- The drawing, served on localhost: the script compiles, each of the 5 flows plays with an arrow lit, and the
  dashboard box's hover shows the new text.
- Not seen as a screenshot: the pane did not draw while the app sat behind another window. macOS waits in
  task 36.
