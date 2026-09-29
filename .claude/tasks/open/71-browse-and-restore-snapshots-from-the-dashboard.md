---
title: Browse the snapshots on the dashboard page, and restore one after a confirmation
stage: H
area: ui
created: 2026-09-29
status: open
depends-on: [66]
findings: []
platforms: [windows, macos]
commit: "feat: the dashboard lists the snapshots and restores one after a confirmation"
---

## Why

Task 66 planned the snapshots on the dashboard page, with a restore button. It left them out: a restore from
the page would skip the permission prompt that the `restore.ask` check puts on `io.restore`, and that prompt is
the user's only chance to stop a restore that drops work.

## What to build

- A Snapshots view on the page: each snapshot with its time, its files and its reason, newest first, read
  through the page server behind its token.
- A restore that shows the files it will overwrite and asks the user on the page before it writes. The page's
  confirmation stands in for the harness prompt, and it says the same thing the prompt says.
- A diff of one file against its snapshot, the way `io.compare` shows it.

## Where

`plugins/io-guard/ui/dashboard.html`, `plugins/io-guard/scripts/ioguard/mcp/dashboard_http.py`,
`plugins/io-guard/scripts/ioguard/mcp/tools_dashboard.py`, and `mcp/tools_history.py` for the restore itself.

## Done when

- The page lists a real project's snapshots, and a restore from it writes nothing until the user confirms on
  the page.
