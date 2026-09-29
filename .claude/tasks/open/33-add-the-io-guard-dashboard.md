---
title: Add the io-guard dashboard as an MCP App, with a text and HTML fallback
stage: H
area: mcp
created: 2026-09-27
status: open
depends-on: [23, 28]
findings: []
platforms: [windows, macos]
commit: "feat: the io-guard dashboard, as an MCP App and as a local page"
---

## Why

Telemetry is only useful when the lead can see it. The lead reads by seeing (the kit's `presenting.md`), so a table
of counts in a terminal is not enough. MCP Apps render interactive HTML inline in the conversation, where the
client supports them (D10). Task 03 found that neither the desktop Code tab nor the CLI fetches an App's `ui://`
resource, so neither renders one (`context.md`, "Hooks and MCP", row 16). Cowork is not checked. Every view
therefore also exists as text and as a local page. It comes after the measurement (D20).

## What to build

- **`io.dashboard(scope?, since?)`**, a read-only tool. Its `structuredContent` holds counts and percentiles only,
  because a tool result lands in the model's context. The page fetches the details itself with
  `scope: "details"`, which the model does not call. Its definition carries
  `_meta.ui.resourceUri: "ui://io-guard/dashboard"`.
- **The `ui://io-guard/dashboard` resource.** A single HTML file with inline CSS and JS and no external origins,
  served as `text/html;profile=mcp-app`. It shows:
  - fixes and refusals by code, check, project and platform over time
  - the latency percentiles
  - a list of recent events, where clicking an event shows its evidence and fix
  - the checks each project has on, and the rewrite mode per permission mode (D12), where a toggle calls
    `io.config` after the user confirms in the dashboard
  - the snapshots, with a restore button that calls `io.restore` and asks the user first

  It talks to the host over the MCP Apps postMessage protocol, implemented directly with no framework dependency.
- **`io.config(scope, key, value)`**: writes the user's config or `<project>/.claude/io-guard.json` through
  `lib.bytesio.write_atomic`, and refuses what the scope may not set (`docs/design/architecture.md`, section 5).
- **`tools/report.py --html <file>`**: renders the same page from the same data into a standalone file that opens
  in any browser. It is one template, shared by both uses.

## Decisions, 2026-09-29

The lead picked these after seeing three mockups: a page in the browser pane, a native window, and text in chat.

- **Surface:** a local page that the io server serves on `127.0.0.1`, which Claude opens in the desktop app's
  browser pane and any browser opens elsewhere, plus `io.config`, so a setting also changes by asking in chat.
  The MCP App stays for a client that renders one, since neither Code tab nor CLI does today.
- **First version:** the settings. The checks on or off, the rewrite mode per permission mode, and the lists.
  The stats come after task 31's measurement (D20), in task 66.
- **Files:** a switch picks the user's `config.json` or the project's `.claude/io-guard.json`. A key the project
  may not set shows, and can't be changed, under the project.

The phases, each its own commit:

1. `io.config(scope, key, value)`, the write both surfaces share, with its tests.
2. `io.dashboard`: the io server serves the page and a JSON API on `127.0.0.1`, behind a token in the URL, and
   the tool answers with the URL and a text summary.
3. The page: `ui/dashboard.html`, one file with inline CSS and JS, and a live check in the browser pane.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_dashboard.py`, `plugins/io-guard/ui/dashboard.html`, `tools/report.py`.

## Done when

- The page opens as a local file from `tools/report.py --html` on Windows, with a week of real telemetry.
- In a client with MCP Apps, `io.dashboard` renders inline and a toggle round-trips to the config file. Record which
  clients rendered it in task 04's matrix.
- In Claude Code, `io.dashboard` returns readable text.
