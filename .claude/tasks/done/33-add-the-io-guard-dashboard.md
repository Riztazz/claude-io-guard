---
title: Add the io-guard dashboard as an MCP App, with a text and HTML fallback
stage: H
area: mcp
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [23, 28]
findings: []
platforms: [windows, macos]
commit: "feat: the settings page, one list with each project's override under each option"
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
- **Files:** both the user's `config.json` and the project's `.claude/io-guard.json`. After seeing the page's
  mockup the lead changed the layout: no switch between the two, but one list where each option shows yours,
  and under it the project's override. The page is plain black and white, with a light and a dark theme, a
  tooltip on each option, and a short help line under each.

The phases, each its own commit:

1. `io.config(scope, key, value)`, the write both surfaces share, with its tests.
2. `io.dashboard`: the io server serves the page and a JSON API on `127.0.0.1`, behind a token in the URL, and
   the tool answers with the URL and a text summary.
3. The page: `ui/dashboard.html`, one file with inline CSS and JS, and a live check in the browser pane.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_dashboard.py`, `plugins/io-guard/ui/dashboard.html`, `tools/report.py`.

## Done when

- The settings page opens from `io.dashboard` in the desktop app's browser pane, and a change on it reaches the
  config file and the next tool call.
- In Claude Code, `io.dashboard` returns readable text. The stats, `tools/report.py --html` and the MCP App are
  task 66's.

## What changed

Three commits: a5d25dc `io.config`, 9cc03e0 `io.dashboard` and its server, and this one, the page.

- `lib/config_edit.py`: one setting placed where its file keeps its neighbours, or removed with each object it
  empties.
- `hooks/entry.py`, `lib/context.py`: a session's context loads again when a config file's time or size moved
  (D33), so a change applies from the next call. `config_layers` and `config_stamp` are the one list of files.
- `mcp/tools_dashboard.py`: `io.config`, and `setting`, the one write the page shares. `io.dashboard` starts the
  page server per project and names the checks the project turned off. `settings` gives the page every key
  with its doc, type, choices, default, the user's and the project's value, what applies, and the check
  descriptions for the group headings.
- `mcp/dashboard_http.py`: the page and its API on `127.0.0.1`, behind the URL's token and a `Host` test,
  changes by JSON `POST` only.
- `ui/dashboard.html`: the page as the lead approved it. One list grouped by check, rewrite modes first in
  Claude Code's order, `enabled` first in each check. A switch, choice buttons, a number box, chips or a JSON
  box by type. A help line, `?` for the whole text, a tooltip with the key and default. "This project" under
  each option, with "Same as yours" or "Override". A value the project may not pick is greyed with its reason.
  A refused change shows the loader's message and the saved value again. Light and dark, from the system or
  the pick at the top. ASCII, no outside origin, and every value set as text.
- `lib/results.py`: `CONFIG_REFUSED`.
- Tests: `tests/lib/test_config_edit.py` (6), `tests/mcp/test_tools_dashboard.py` (12), and
  `tests/hooks/test_entry.py` (1, the reload).
- Probes: `live-config` and `live-dashboard`.
- Docs: `docs/design/architecture.md` (the tree, `io.config`, the dashboard page, the ui resource, the codes,
  the config row), `README.md` (Configure it, the tools table), `docs/compat.md`, `docs/architecture.svg` (the
  dashboard box), `.claude/tasks/context.md` (D33), the skill's tables, `CLAUDE.md`.

Evidence:

- `python tests/run_all.py` from Git Bash ran 889 tests, all passing, up from 870 before the task.
- `live-config` and `live-dashboard` passed on 2.1.281 and 2.1.283 on Windows on 2026-09-29.
- The page, served from this checkout over copies of the lead's two config files, in the desktop app's browser
  pane: 86 settings in 28 groups. The tooltip showed `transport.rewrite_mode.auto, default "refuse"`. An
  override of auto mode wrote `"auto": "refuse"` into the project copy's `transport` object and greyed `allow`.
  A project `transport.budget_bytes` of 9000 showed the loader's "may lower this number and not raise it past
  6000" and went back to 6000. Turning `shell.lint` off and adding `Content/**` to `skip_trees` wrote both into
  the user copy. Light and dark both drew, from the pick and from the scheme.
- Not seen: the page in the lead's own session, which needs the plugin update. A save rewrites the whole file
  as two-space JSON, so a hand-wrapped list comes back one item per line, as the README says.
