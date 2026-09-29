---
title: Reset the stats from the page, and delete telemetry past its retention
stage: H
area: ui
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [66]
findings: []
platforms: [windows, macos]
commit: "feat: the stats page resets its count, and old telemetry expires"
---

## Why

On 2026-09-29 the lead asked how a user resets the stats. The only way was to delete the telemetry folder by
hand, and `telemetry.retention_days`, 90 by default, is declared in `lib/config.py` but read nowhere, so no
telemetry file is ever deleted. The lead chose both a reset that hides and one that deletes.

## What to build

- **Start from now.** A button on the Stats view saves the current time in io-guard's folder, and the page
  counts only the lines after it. Nothing is deleted. The page says "Counting from <time>" with a Show
  everything button that clears the mark. The mark covers every project, and `tools/report.py` and
  `tools/measure.py` ignore it, since task 31 needs every line.
- **Delete all.** A second button deletes every telemetry file after two confirmations. The first names the
  sessions and lines it deletes and says it cannot be undone. It deletes the files of every project, whatever
  the page's scope, since a session's file holds lines of more than one project.
- **Retention.** The io server deletes each telemetry file older than `telemetry.retention_days` once when it
  starts. 0 keeps every file. The key's description says so.
- Both buttons are a `POST` of JSON to the page server, behind its token, as a setting is.

## Where

`plugins/io-guard/ui/dashboard.html`, `plugins/io-guard/scripts/ioguard/mcp/dashboard_http.py`,
`plugins/io-guard/scripts/ioguard/mcp/tools_dashboard.py`, `plugins/io-guard/scripts/ioguard/lib/telemetry.py`
or `lib/telemetry_summary.py`, `plugins/io-guard/scripts/ioguard/lib/config.py`, and the server's start.

## Done when

- In the browser pane, over a copy of the lead's telemetry, Start from now zeroes the counts and Show everything
  brings them back, and Delete all empties the copy's folder after both confirmations.
- A file older than the retention is gone after the server starts, and a newer one stays.

## What changed

- `lib/telemetry.py`: `session_files`, `expire` and `erase`, with `removed` deleting the files and each emptied
  month folder before the current one. A file another process holds open stays, and the log names it.
  `lib/telemetry_summary.files` lists through `session_files`.
- `mcp/server.py`: `expire_telemetry` runs once in a thread of its own when the server starts, with the user's
  `telemetry.retention_days`. `lib/config.py`: the key is the user's alone now, and its description says what 0
  does.
- `mcp/dashboard_http.py`: `Dashboard` takes a table of GET routes and one of POST routes, in place of three
  named callables. `POST /api/stats/from` and `POST /api/stats/delete` join them.
- `mcp/tools_dashboard.py`: `counted_from`, `count_from` and `delete_all`, and the mark in `stats-from.json` in
  io-guard's folder. `telemetry_summary.page` counts from the mark and says what the folder holds on disk.
- `ui/dashboard.html`: Start from now and Delete all... on the Stats view, a "Counting from" line with Show
  everything, and the two confirmations drawn in the page. A file from `report.py --html` shows neither.
- Tests: `tests/lib/test_telemetry.py` covers 89 and 91 days against 90, 0 days, and erase keeping this month's
  folder. `tests/mcp/test_server.py` covers the user's retention at the server. `tests/mcp/test_tools_dashboard.py`
  covers the mark hiding and showing a line, and a delete refused without its confirmation then deleting two
  projects' files. The page test also reads the paths `post` calls.
- Docs: `.claude/tasks/context.md` (D35), `docs/design/architecture.md` (the tree, the page's routes and reset,
  the retention thread and the telemetry row), `README.md` (resetting the stats, the retention) and
  `docs/architecture.svg` (flow D's third step).

Evidence:

- `python tests/run_all.py` ran 903 tests, all passing, up from 897.
- The page from this checkout in the browser pane, over a copy of the lead's telemetry: all projects counted
  7,034 lines, Start from now counted 0 and said where it counts from, and Show everything counted 7,034 again.
  Delete all... asked "35 files, 4.4 MB", Cancel left it, and Delete... then Delete for good answered "Deleted 35
  telemetry files". The copy held 0 files and only this month's folder, and the lead's own folder still held
  35. A screenshot shows the first confirmation above the stats.
- The shipped `ioguard_mcp.py`, started on a temporary folder with a 100-day-old and a 2-day-old file, left only
  the 2-day-old one, removed the old month's folder, and exited 0.
- The drawing, served on localhost: the script compiles, and flow D plays with its new step.
- macOS waits in task 36.
